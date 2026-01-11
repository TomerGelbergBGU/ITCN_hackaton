import socket
import threading
import time
import random
from protocol import Protocol

# --- Game Constants ---
SUITS = [0, 1, 2, 3]  # Spades, Hearts, Diamonds, Clubs
RANKS = list(range(1, 14))  # 1-13

# Status codes (Official only!)
STATUS_ACTIVE = 0
STATUS_TIE = 1
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

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start(self):
        # Start UDP Broadcast
        udp_thread = threading.Thread(target=self.broadcast_offers, daemon=True)
        udp_thread.start()

        # Main Loop
        try:
            while self.running:
                print("Waiting for clients...")
                client_sock, addr = self.tcp_socket.accept()
                print(f"New connection from {addr}")
                threading.Thread(target=self.handle_client, args=(client_sock,)).start()
        except KeyboardInterrupt:
            self.running = False

    def broadcast_offers(self):
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # BIND TO IP: Important for correct network interface selection
        try:
            udp_sock.bind((self.server_ip, 0))
        except:
            pass

        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        dest_addr = ('255.255.255.255', Protocol.SERVER_PORT)

        while self.running:
            try:
                msg = Protocol.pack_offer(self.server_port, self.server_name)
                udp_sock.sendto(msg, dest_addr)
                time.sleep(1)
            except:
                pass

    # --- Game Logic ---

    def get_deck(self):
        deck = [(r, s) for r in RANKS for s in SUITS]
        random.shuffle(deck)
        return deck

    def calculate_hand(self, cards):
        value = 0
        aces = 0
        for rank, suit in cards:
            if rank == 1:
                aces += 1
                value += 1
            elif rank > 10:
                value += 10
            else:
                value += rank
        while aces > 0 and value + 10 <= 21:
            value += 10
            aces -= 1
        return value

    def handle_client(self, conn):
        try:
            # 1. Handshake
            data = conn.recv(38)
            if not data: return
            num_rounds, player_name = Protocol.unpack_request(data)
            print(f"Player '{player_name}' connected for {num_rounds} rounds.")

            # 2. Play Rounds
            for i in range(num_rounds):
                print(f"--- Round {i + 1} for {player_name} ---")
                self.play_round(conn)

            print(f"Finished rounds for {player_name}.")
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            conn.close()

    def play_round(self, conn):
        deck = self.get_deck()
        player_cards = [deck.pop(), deck.pop()]
        dealer_cards = [deck.pop(), deck.pop()]

        # 1. Send Initial Cards (All STATUS 0)
        # Player Card 1
        conn.sendall(Protocol.pack_game_state(STATUS_ACTIVE, player_cards[0][0], player_cards[0][1]))
        time.sleep(0.05)
        # Player Card 2
        conn.sendall(Protocol.pack_game_state(STATUS_ACTIVE, player_cards[1][0], player_cards[1][1]))
        time.sleep(0.05)
        # Dealer Visible Card
        conn.sendall(Protocol.pack_game_state(STATUS_ACTIVE, dealer_cards[0][0], dealer_cards[0][1]))

        # 2. Player Turn
        player_active = True
        while player_active:
            if self.calculate_hand(player_cards) >= 21:
                break  # Auto stand/bust

            try:
                data = conn.recv(10)
                if not data: break
                action = Protocol.unpack_action(data)

                if action == "Hit":
                    new_card = deck.pop()
                    player_cards.append(new_card)

                    # Send new card (STATUS 0)
                    conn.sendall(Protocol.pack_game_state(STATUS_ACTIVE, new_card[0], new_card[1]))

                    if self.calculate_hand(player_cards) > 21:
                        # Busted! Send Loss immediately
                        conn.sendall(Protocol.pack_game_state(STATUS_LOSS, new_card[0], new_card[1]))
                        return
                else:
                    player_active = False  # Stand
            except:
                break

        # 3. Dealer Turn
        # Reveal hidden card (Send as STATUS 0)
        conn.sendall(Protocol.pack_game_state(STATUS_ACTIVE, dealer_cards[1][0], dealer_cards[1][1]))
        time.sleep(0.05)

        d_val = self.calculate_hand(dealer_cards)
        p_val = self.calculate_hand(player_cards)

        # Dealer draws
        while d_val < 17:
            new_card = deck.pop()
            dealer_cards.append(new_card)
            d_val = self.calculate_hand(dealer_cards)
            conn.sendall(Protocol.pack_game_state(STATUS_ACTIVE, new_card[0], new_card[1]))
            time.sleep(0.05)

        # 4. Result
        if d_val > 21:
            status = STATUS_WIN
        elif p_val > d_val:
            status = STATUS_WIN
        elif p_val < d_val:
            status = STATUS_LOSS
        else:
            status = STATUS_TIE

        last = dealer_cards[-1]
        conn.sendall(Protocol.pack_game_state(status, last[0], last[1]))


if __name__ == "__main__":
    server = GameServer()
    server.start()