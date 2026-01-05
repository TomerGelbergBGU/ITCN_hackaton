import socket
import threading
import time
import random
from protocol import Protocol

# --- Game Constants ---
SUITS = [0, 1, 2, 3]  # Spades, Hearts, Diamonds, Clubs
RANKS = list(range(1, 14))  # 1-13 (Ace=1, J=11, Q=12, K=13)

# Status codes for Game State
STATUS_ACTIVE = 0
STATUS_TIE = 1
STATUS_LOSS = 2
STATUS_WIN = 3
STATUS_DEALER_CARD = 4  # <-- הוספנו את זה כאן בצורה מסודרת


class GameServer:
    def __init__(self, server_name="Team Dealer"):
        self.server_name = server_name
        self.running = True

        # 1. Setup Network Info
        self.server_ip = self._get_local_ip()

        # 2. Setup TCP Socket (The Listener)
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.bind(('0.0.0.0', 0))  # Bind to 0 lets OS pick a free port
        self.server_port = self.tcp_socket.getsockname()[1]
        self.tcp_socket.listen(5)

        print(f"Server started on IP: {self.server_ip}, TCP Port: {self.server_port}")

    def _get_local_ip(self):
        """Try to find the actual local IP address (not 127.0.0.1)."""
        try:
            # Connect to a public DNS to find our outbound IP (doesn't actually send data)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start(self):
        """Main entry point: starts UDP broadcaster and TCP listener."""

        # Start UDP Broadcast in a separate thread
        udp_thread = threading.Thread(target=self.broadcast_offers, daemon=True)
        udp_thread.start()

        # Main Loop: Accept TCP connections
        try:
            while self.running:
                print("Waiting for clients...")
                client_sock, addr = self.tcp_socket.accept()
                print(f"New connection from {addr}")

                # Handle each client in a separate thread
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_sock,)
                )
                client_thread.start()
        except KeyboardInterrupt:
            print("Server stopping...")
            self.running = False

    def broadcast_offers(self):
        """Sends UDP Offer messages every 1 second."""
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # Enable Broadcast
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        dest_addr = ('255.255.255.255', Protocol.SERVER_PORT)  # Port 13122

        print(f"Broadcasting offers to {dest_addr}...")

        while self.running:
            try:
                msg = Protocol.pack_offer(self.server_port, self.server_name)
                udp_sock.sendto(msg, dest_addr)
                time.sleep(1)
            except Exception as e:
                print(f"Broadcast Error: {e}")

    # --- Game Logic Methods ---

    def get_deck(self):
        """Returns a shuffled list of (rank, suit) tuples."""
        deck = []
        for r in RANKS:
            for s in SUITS:
                card_tuple = (r, s)
                deck.append(card_tuple)
        random.shuffle(deck)
        return deck

    def calculate_hand(self, cards):
        """Calculates hand value properly handling Aces."""
        value = 0
        aces = 0

        for rank, suit in cards:
            if rank == 1:  # Ace
                aces += 1
                value += 1
            elif rank > 10:  # Face cards
                value += 10
            else:
                value += rank

        # Upgrade Aces from 1 to 11 if possible
        while aces > 0 and value + 10 <= 21:
            value += 10
            aces -= 1

        return value

    def handle_client(self, conn):
        """Orchestrates the game for a single connected client."""
        try:
            # 1. Handshake
            data = conn.recv(38)
            if not data:
                return

            try:
                num_rounds, player_name = Protocol.unpack_request(data)
                print(f"Player '{player_name}' connected for {num_rounds} rounds.")
            except ValueError as e:
                print(f"Invalid request: {e}")
                return

            # 2. Play Rounds
            for i in range(num_rounds):
                print(f"--- Round {i + 1} for {player_name} ---")
                self.play_round(conn)

            print(f"Finished rounds for {player_name}. Closing.")

        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            conn.close()

    def play_round(self, conn):
        """Runs a single round with full Dealer visibility logic."""
        deck = self.get_deck()
        player_cards = [deck.pop(), deck.pop()]
        dealer_cards = [deck.pop(), deck.pop()]  # D1 visible, D2 hidden

        # --- 1. שליחת קלפים ראשוניים ---

        # שליחת קלפי שחקן
        for card in player_cards:
            msg = Protocol.pack_game_state(STATUS_ACTIVE, card[0], card[1])
            conn.sendall(msg)
            time.sleep(0.1)

        # שליחת הקלף הראשון של הדילר
        # משתמשים בקבוע הגלובלי שהגדרנו למעלה
        msg = Protocol.pack_game_state(STATUS_DEALER_CARD, dealer_cards[0][0], dealer_cards[0][1])
        conn.sendall(msg)

        player_active = True

        # --- 2. תור השחקן ---
        while player_active:
            player_val = self.calculate_hand(player_cards)

            if player_val >= 21:
                break

            try:
                data = conn.recv(10)
                if not data: break
                action = Protocol.unpack_action(data)

                if action == "Hit":
                    new_card = deck.pop()
                    player_cards.append(new_card)

                    # בדיקת שריפה
                    if self.calculate_hand(player_cards) > 21:
                        # קודם שולחים את הקלף ששרף
                        msg = Protocol.pack_game_state(STATUS_ACTIVE, new_card[0], new_card[1])
                        conn.sendall(msg)
                        time.sleep(0.1)

                        # אחר כך שולחים הודעת הפסד
                        final_msg = Protocol.pack_game_state(STATUS_LOSS, new_card[0], new_card[1])
                        conn.sendall(final_msg)
                        return

                    # סתם קלף רגיל
                    msg = Protocol.pack_game_state(STATUS_ACTIVE, new_card[0], new_card[1])
                    conn.sendall(msg)

                else:  # Stand
                    player_active = False

            except Exception:
                break

        # --- 3. תור הדילר ---

        # חושפים את הקלף השני (המוסתר)
        msg = Protocol.pack_game_state(STATUS_DEALER_CARD, dealer_cards[1][0], dealer_cards[1][1])
        conn.sendall(msg)
        time.sleep(0.1)

        player_val = self.calculate_hand(player_cards)
        dealer_val = self.calculate_hand(dealer_cards)

        # הדילר מושך קלפים עד 17
        if player_val <= 21:
            while dealer_val < 17:
                new_card = deck.pop()
                dealer_cards.append(new_card)
                dealer_val = self.calculate_hand(dealer_cards)

                msg = Protocol.pack_game_state(STATUS_DEALER_CARD, new_card[0], new_card[1])
                conn.sendall(msg)
                time.sleep(0.1)

        # --- 4. חישוב תוצאה סופית ---
        status = STATUS_TIE
        if player_val > 21:
            status = STATUS_LOSS
        elif dealer_val > 21:
            status = STATUS_WIN  # דילר נשרף
        elif player_val > dealer_val:
            status = STATUS_WIN
        elif player_val < dealer_val:
            status = STATUS_LOSS
        else:
            status = STATUS_TIE

        last = dealer_cards[-1]
        end_msg = Protocol.pack_game_state(status, last[0], last[1])
        conn.sendall(end_msg)
        print(f"Game Over. P:{player_val} vs D:{dealer_val}")


if __name__ == "__main__":
    server = GameServer()
    server.start()