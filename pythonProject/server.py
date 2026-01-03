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
        deck = []  # 1. מתחילים עם רשימה ריקה

        # 2. לולאה חיצונית: עוברת על כל הדרגות (1 עד 13)
        for r in RANKS:
            # 3. לולאה פנימית: לכל דרגה, עוברת על כל 4 הצורות (0 עד 3)
            for s in SUITS:
                card_tuple = (r, s)  # יוצרים זוג (tuple), למשל: (7, 2)
                deck.append(card_tuple)  # מוסיפים את הקלף לחפיסה

        # בשלב הזה יש לנו 52 קלפים מסודרים.
        # עכשיו מערבבים אותם:
        random.shuffle(deck)

        return deck

    def calculate_hand(self, cards):
        """
        Calculates hand value properly handling Aces.
        cards: list of tuples (rank, suit)
        """
        value = 0
        aces = 0

        for rank, suit in cards:
            if rank == 1:  # אם זה אס
                aces += 1  # תזכור שיש לנו אס שאפשר אולי לשדרג אח"כ
                value += 1  # תוסיף לניקוד רק 1 בינתיים
            elif rank > 10:  # אם זה נסיך, מלכה או מלך (11, 12, 13)
                value += 10  # בבלאק ג'ק הם שווים 10
            else:  # כל שאר המספרים (2 עד 10)
                value += rank  # הערך הוא המספר עצמו

        # Upgrade Aces from 1 to 11 if it doesn't bust
        # כל עוד (יש לי אסים לשדרג) וגם (אם אני אשדרג לא אעבור את 21)
        while aces > 0 and value + 10 <= 21:
            value += 10  # תוסיף 10 לערך (כך ה-1 שכבר חישבנו הופך ל-11)
            aces -= 1  # תוריד אס אחד מהמונה (כי השתמשנו בו כשדרוג)

        return value

    def handle_client(self, conn):
        """Orchestrates the game for a single connected client."""
        try:
            # 1. Handshake: Read exactly 38 bytes for Request
            data = conn.recv(38)  # Size of FMT_REQUEST
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
        """Runs a single round of Blackjack."""
        deck = self.get_deck()
        player_cards = [deck.pop(), deck.pop()]
        dealer_cards = [deck.pop(), deck.pop()]

        # --- Player's Turn ---

        # Send the initial 2 cards to the client
        for card in player_cards:
            msg = Protocol.pack_game_state(STATUS_ACTIVE, card[0], card[1])
            conn.sendall(msg)
            time.sleep(0.1)

        player_active = True

        while player_active:
            player_val = self.calculate_hand(player_cards)

            # אם השחקן הגיע ל-21 (או התחיל עם 21), הולכים ישר לדילר
            if player_val >= 21:
                break

            try:
                # Wait for player decision
                data = conn.recv(10)
                if not data: break  # Client disconnected

                action = Protocol.unpack_action(data)

                if action == "Hit":
                    new_card = deck.pop()
                    player_cards.append(new_card)

                    # --- התיקון הקוסמטי: בדיקת Bust מיידית ---
                    new_val = self.calculate_hand(player_cards)
                    if new_val > 21:
                        # השחקן נשרף. נשלח לו את הקלף ששרף אותו עם סטטוס הפסד
                        # וכך הלקוח לא ישאל "מה המהלך הבא"
                        msg = Protocol.pack_game_state(STATUS_LOSS, new_card[0], new_card[1])
                        conn.sendall(msg)
                        print(f"Round Over. Player busted immediately with {new_val}")
                        return  # סיום הפונקציה כאן ועכשיו

                    # אם לא נשרף - שולחים כרגיל וממשיכים
                    msg = Protocol.pack_game_state(STATUS_ACTIVE, new_card[0], new_card[1])
                    conn.sendall(msg)

                else:  # Stand
                    player_active = False

            except ValueError:
                print("Garbage data received")
                break

        # --- Dealer's Turn & Result ---
        # הקוד הזה ירוץ רק אם השחקן עשה Stand או הגיע ל-21 בדיוק (לא נשרף ב-Hit)

        player_val = self.calculate_hand(player_cards)
        dealer_val = self.calculate_hand(dealer_cards)

        # Dealer draws if player didn't bust (למרות שאם הוא כאן הוא כנראה לא נשרף, אלא אם זה באג)
        if player_val <= 21:
            while dealer_val < 17:
                dealer_cards.append(deck.pop())
                dealer_val = self.calculate_hand(dealer_cards)

        # Determine Winner
        status = STATUS_TIE

        if player_val > 21:
            status = STATUS_LOSS
        elif dealer_val > 21:
            status = STATUS_WIN
        elif player_val > dealer_val:
            status = STATUS_WIN
        elif player_val < dealer_val:
            status = STATUS_LOSS
        else:
            status = STATUS_TIE

        # Send Final Result with Dealer's last card
        last_dealer_card = dealer_cards[-1]
        end_msg = Protocol.pack_game_state(status, last_dealer_card[0], last_dealer_card[1])
        conn.sendall(end_msg)

        print(f"Round Over. Result: {status} (P:{player_val} vs D:{dealer_val})")


if __name__ == "__main__":
    server = GameServer()
    server.start()