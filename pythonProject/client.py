import socket
import threading
from protocol import Protocol


class GameClient:
    def __init__(self):
        self.udp_port = 13122
        self.tcp_socket = None
        self.running = True
        self.game_active = False

        self.player_name = ""
        self.requested_rounds = 0
        self.cards_seen_in_round = 0

    def calculate_hand(self, cards):
        """
        Calculates the value of a hand (list of ranks).
        Handles Aces (1 or 11) correctly.
        """
        value = 0
        aces = 0
        for r in cards:
            if r == 1:  # Ace
                aces += 1
                value += 11
            elif r >= 10:  # Face cards (J, Q, K)
                value += 10
            else:
                value += r

        # אם עברנו את 21 ויש לנו אסים, נהפוך אותם מ-11 ל-1
        while value > 21 and aces > 0:
            value -= 10
            aces -= 1
        return value

    def get_user_params(self):
        """Show menu and get user configuration."""
        print("=== Welcome to High-Tech Blackjack Client ===")
        while not self.player_name:
            self.player_name = input("Enter your player name: ").strip()

        while self.requested_rounds <= 0:
            try:
                rounds_str = input("How many rounds do you want to play? (e.g. 3): ")
                self.requested_rounds = int(rounds_str)
            except ValueError:
                print("Please enter a valid number.")

        print(f"OK, {self.player_name}. Looking for a server...")

    def start(self):
        self.get_user_params()
        print("Client started listening for offers...")
        while self.running:
            server_ip, server_port = self.find_server()
            if server_ip and server_port:
                self.connect_and_play(server_ip, server_port)

    def find_server(self):
        """Listens for UDP broadcast offers."""
        udp_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_client.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            udp_client.bind(("", self.udp_port))
        except Exception as e:
            print(f"UDP Bind Error: {e}")
            # במקרה של שגיאה ב-Bind עדיף לצאת או לנסות שוב עם השהיה
            import time
            time.sleep(1)
            return None, None

        print(f"Listening on UDP port {self.udp_port}...")

        while True:
            try:
                data, addr = udp_client.recvfrom(1024)

                # unpacking returns (port, name)
                server_port, server_name = Protocol.unpack_offer(data)

                if server_name:
                    print(f"\nReceived offer from server '{server_name}' at {addr[0]}")
                    udp_client.close()  # סוגרים את ה-UDP לפני המעבר ל-TCP
                    return addr[0], server_port
            except Exception as e:
                continue

    def connect_and_play(self, ip, port):
        """Connects via TCP and handles the game loop."""
        print(f"Connecting to {ip}:{port}...")

        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.connect((ip, port))

            print(f"Sending handshake: Name={self.player_name}")

            # שליחת הודעת פתיחה (שם + מספר סיבובים)
            req_msg = Protocol.pack_request(self.player_name, self.requested_rounds)
            self.tcp_socket.sendall(req_msg)

            self.game_active = True

            # הפעלת האזנה לשרת ב-Thread נפרד כדי שה-Input לא יתקע את קבלת ההודעות
            listen_thread = threading.Thread(target=self.listen_to_server, daemon=True)
            listen_thread.start()

            # לולאת ה-Input רצה ב-Main Thread
            self.user_input_loop()

        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            if self.tcp_socket:
                self.tcp_socket.close()
            print("Disconnected from server. Searching for new server...\n")
            self.game_active = False

    def listen_to_server(self):
        """Listens for messages, tracks both hands, and explains the result."""

        my_hand_ranks = []
        dealer_hand_ranks = []

        # רשימה חדשה לשמירת *השמות* של קלפי הדילר להדפסה יפה בסוף
        dealer_cards_display = []

        end_msg = "\nRound ended. Press Enter to continue..."

        try:
            while self.game_active:
                data = self.tcp_socket.recv(1024)
                if not data:
                    print("\nServer closed the connection.")
                    self.game_active = False
                    break

                status, rank, suit = Protocol.unpack_game_state(data)

                # המרות טקסט
                ranks_map = {1: 'Ace', 11: 'Jack', 12: 'Queen', 13: 'King'}
                suits_map = {0: 'Spades', 1: 'Hearts', 2: 'Diamonds', 3: 'Clubs'}
                r_str = ranks_map.get(rank, str(rank))
                s_str = suits_map.get(suit, 'Unknown')
                card_str = f"[{r_str} of {s_str}]"

                # --- לוגיקה לפי סטטוס ---

                if status == 0:  # ACTIVE (קלף שלי)
                    self.cards_seen_in_round += 1
                    my_hand_ranks.append(rank)
                    my_score = self.calculate_hand(my_hand_ranks)

                    print(f"Server: You got {card_str} | Your Total: {my_score}")

                    # אם תורי לשחק (יש לי קלפים, ולדילר יש קלף פתוח)
                    if len(my_hand_ranks) >= 2 and len(dealer_hand_ranks) > 0:
                        if my_score < 21:
                            print("Your move (1-Hit, 2-Stand): ", end="", flush=True)

                elif status == 4:  # STATUS_DEALER (קלף דילר)
                    dealer_hand_ranks.append(rank)
                    dealer_cards_display.append(card_str)  # שומרים את השם להדפסה בסוף

                    print(f"Dealer shows: {card_str}")

                    # שואלים את השחקן רק אם זה הקלף *הראשון* של הדילר
                    if len(dealer_hand_ranks) == 1:
                        my_score = self.calculate_hand(my_hand_ranks)
                        if len(my_hand_ranks) >= 2 and my_score < 21:
                            print("Your move (1-Hit, 2-Stand): ", end="", flush=True)

                else:  # WIN (3) / LOSS (2) / DRAW (1) - סיום משחק
                    self.cards_seen_in_round = 0

                    my_final = self.calculate_hand(my_hand_ranks)
                    dealer_final = self.calculate_hand(dealer_hand_ranks)

                    print("\n" + "=" * 50)  # קו מפריד ארוך יותר
                    res_text = {1: "DRAW", 2: "YOU LOST!", 3: "YOU WON!"}.get(status, "RESULT")
                    print(f"=== GAME OVER: {res_text} ===")
                    print("=" * 50)

                    # --- ההדפסה המסודרת החדשה ---
                    print(f"YOUR SCORE:   {my_final}")

                    # חיבור כל קלפי הדילר למחרוזת אחת יפה
                    dealer_cards_str = ", ".join(dealer_cards_display)
                    print(f"DEALER HAND:  {dealer_cards_str}")
                    print(f"DEALER SCORE: {dealer_final}")
                    print("-" * 50)

                    if my_final > 21:
                        print("Reason: You Busted (went over 21).")
                    elif dealer_final > 21:
                        print("Reason: Dealer Busted! You win.")
                    elif my_final > dealer_final:
                        print("Reason: Your score is higher than the Dealer's.")
                    elif my_final < dealer_final:
                        print("Reason: Dealer's score is higher.")
                    else:
                        print("Reason: Scores are equal.")
                    print("=" * 50)

                    # איפוס רשימות
                    my_hand_ranks = []
                    dealer_hand_ranks = []
                    dealer_cards_display = []

        except (ConnectionResetError, ConnectionAbortedError):
            print("\n\nError: The server disconnected unexpectedly!")
            self.game_active = False
            end_msg = "\nConnection lost. Press Enter to return..."

        except Exception as e:
            print(f"\n\nGeneral Error: {e}")
            self.game_active = False

        print(end_msg)

    def user_input_loop(self):
        """
        לולאה שרצה ב-Main Thread ומחכה לקלט מהמשתמש.
        ברגע שהמשחק נגמר (game_active=False), הלולאה תישבר כשהמשתמש ילחץ Enter.
        """
        while self.game_active:
            try:
                # ה-input כאן הוא "חוסם" (Blocking).
                # אם השרת מתנתק, אנחנו צריכים שהמשתמש ילחץ Enter כדי לשחרר את החסימה ולצאת מהלולאה.
                choice = input()

                if not self.game_active: break

                action = ""
                if choice == '1':
                    action = "Hit"
                elif choice == '2':
                    action = "Stand"
                else:
                    print("Invalid choice. Enter 1 or 2.")
                    continue

                if self.tcp_socket:
                    self.tcp_socket.sendall(Protocol.pack_action(action))
            except Exception:
                break


if __name__ == "__main__":
    client = GameClient()
    client.start()