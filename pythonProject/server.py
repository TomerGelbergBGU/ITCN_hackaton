import socket
import threading
import time
import random
from protocol import Protocol

# --- Game Constants ---
SUITS = [0, 1, 2, 3]  # Spades, Hearts, Diamonds, Clubs
RANKS = list(range(1, 14))  # 1-13 (Ace=1, J=11, Q=12, K=13)

# Protocol Status Codes
STATUS_ACTIVE = 0
STATUS_DRAW = 1
STATUS_LOSS = 2
STATUS_WIN = 3


class GameServer:
    def __init__(self, server_name="Team Dealer"):
        self.server_name = server_name
        self.running = True

        # 1. Setup Network Info
        self.server_ip = self._get_local_ip()

        # 2. Setup TCP Socket
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.bind(('0.0.0.0', 0))
        self.server_port = self.tcp_socket.getsockname()[1]
        self.tcp_socket.listen(5)

        print(f"Server started on IP: {self.server_ip}, TCP Port: {self.server_port}")

        # Start Broadcast Thread
        threading.Thread(target=self.broadcast_offers, daemon=True).start()

    def _get_local_ip(self):
        """Finds local IP without hardcoding '8.8.8.8' in logic flow."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((Protocol.TEST_IP_FOR_INTERFACE, Protocol.TEST_PORT_FOR_INTERFACE))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def broadcast_offers(self):
        """Broadcasts UDP offers every 1 second."""
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        packet = Protocol.pack_offer(self.server_port, self.server_name)
        dest_addr = (Protocol.BROADCAST_IP, Protocol.SERVER_PORT)

        print(f"Broadcasting offers to {dest_addr}...")

        while self.running:
            try:
                udp_sock.sendto(packet, dest_addr)
                time.sleep(1)
            except Exception as e:
                print(f"Broadcast error: {e}")
                time.sleep(1)

    def start(self):
        """Main loop: Accept TCP connections."""
        print("Waiting for clients...")
        while self.running:
            try:
                conn, addr = self.tcp_socket.accept()
                print(f"New connection from {addr}")
                threading.Thread(target=self.handle_client, args=(conn,), daemon=True).start()
            except Exception as e:
                print(f"Accept error: {e}")

    def handle_client(self, conn):
        try:
            # 1. Receive Request
            data = Protocol.recv_exactly(conn, Protocol.REQUEST_MSG_SIZE)
            rounds, player_name = Protocol.unpack_request(data)
            print(f"Player '{player_name}' connected for {rounds} rounds.")

            # 2. Game Loop
            for i in range(1, rounds + 1):
                # print(f"--- Round {i} for {player_name} ---")
                self.play_round(conn)

            print(f"Finished games with {player_name}. Closing.")

        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            conn.close()

    def calculate_hand(self, cards):
        value = 0
        aces = 0
        for r, s in cards:
            if r == 1:
                aces += 1; value += 11
            elif r >= 10:
                value += 10
            else:
                value += r

        while value > 21 and aces > 0:
            value -= 10
            aces -= 1
        return value

    def play_round(self, conn):
        deck = [(r, s) for r in RANKS for s in SUITS]
        random.shuffle(deck)

        player_cards = [deck.pop(), deck.pop()]
        dealer_cards = [deck.pop(), deck.pop()]

        # Send initial cards (Player 1, Player 2, Dealer 1)
        # Note: Dealer's second card is hidden
        initial_sends = [
            (player_cards[0], STATUS_ACTIVE),
            (player_cards[1], STATUS_ACTIVE),
            (dealer_cards[0], STATUS_ACTIVE)
        ]

        for card, status in initial_sends:
            conn.sendall(Protocol.pack_game_state(status, card[0], card[1]))
            time.sleep(0.05)  # Small buffer for network stability

        # --- Player Turn ---
        player_active = True

        # Quick check for Blackjack (21)
        if self.calculate_hand(player_cards) == 21:
            player_active = False

        while player_active:
            try:
                data = Protocol.recv_exactly(conn, Protocol.CLIENT_MSG_SIZE)
                action = Protocol.unpack_action(data)

                if action == "Hit":
                    new_card = deck.pop()
                    player_cards.append(new_card)
                    conn.sendall(Protocol.pack_game_state(STATUS_ACTIVE, new_card[0], new_card[1]))

                    if self.calculate_hand(player_cards) >= 21:
                        player_active = False  # Busted or 21
                else:
                    player_active = False  # Stand

            except Exception:
                return  # Connection lost

        # --- Dealer Turn ---
        # Reveal hidden card
        conn.sendall(Protocol.pack_game_state(STATUS_ACTIVE, dealer_cards[1][0], dealer_cards[1][1]))

        player_val = self.calculate_hand(player_cards)
        dealer_val = self.calculate_hand(dealer_cards)

        # Dealer draws only if player didn't bust
        if player_val <= 21:
            while dealer_val < 17:
                time.sleep(0.5)  # Simulate thinking
                new_card = deck.pop()
                dealer_cards.append(new_card)
                dealer_val = self.calculate_hand(dealer_cards)
                conn.sendall(Protocol.pack_game_state(STATUS_ACTIVE, new_card[0], new_card[1]))

        # --- Result ---
        status = STATUS_DRAW
        if player_val > 21:
            status = STATUS_LOSS
        elif dealer_val > 21:
            status = STATUS_WIN
        elif player_val > dealer_val:
            status = STATUS_WIN
        elif player_val < dealer_val:
            status = STATUS_LOSS

        # Send FINAL result packet (with dummy cards or last card, doesn't matter much here)
        # We re-send the last dealer card just to conform to format, but status is key.
        last_card = dealer_cards[-1]
        conn.sendall(Protocol.pack_game_state(status, last_card[0], last_card[1]))


if __name__ == "__main__":
    srv = GameServer()
    srv.start()