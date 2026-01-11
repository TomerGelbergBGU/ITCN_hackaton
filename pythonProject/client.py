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
        self.rounds_played = 0

        # True = תורי, False = תור הדילר
        self.my_turn = True

    def calculate_hand(self, cards):
        """Calculates hand value handling Aces."""
        value = 0
        aces = 0
        for r in cards:
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

    def start(self):
        print("=== Welcome to High-Tech Blackjack Client ===")

        while not self.player_name:
            self.player_name = input("Enter your player name: ").strip()

        while self.requested_rounds <= 0:
            try:
                self.requested_rounds = int(input("How many rounds? "))
            except ValueError:
                pass

        print(f"OK, {self.player_name}. Looking for a server...")

        while self.running:
            server_ip, server_port = self.find_server()
            if server_ip:
                self.connect_and_play(server_ip, server_port)

    def find_server(self):
        udp_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_client.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            udp_client.bind(("", self.udp_port))
        except:
            import time;
            time.sleep(1)
            return None, None

        print(f"Listening on UDP port {self.udp_port}...")
        while True:
            try:
                data, addr = udp_client.recvfrom(1024)
                port, name = Protocol.unpack_offer(data)
                if name:
                    print(f"\nFound server '{name}' at {addr[0]}")
                    udp_client.close()
                    return addr[0], port
            except:
                continue

    def connect_and_play(self, ip, port):
        print(f"Connecting to {ip}:{port}...")
        self.rounds_played = 0
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.connect((ip, port))

            self.tcp_socket.sendall(Protocol.pack_request(self.player_name, self.requested_rounds))
            self.game_active = True

            threading.Thread(target=self.listen_to_server, daemon=True).start()
            self.user_input_loop()

        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            if self.tcp_socket: self.tcp_socket.close()
            self.game_active = False
            print("Disconnected. Searching for new server...\n")

    def listen_to_server(self):
        """Listens for server messages."""
        my_hand = []
        dealer_hand = []
        dealer_display = []

        try:
            while self.game_active:
                # 1. Receive packet
                data = Protocol.recv_exactly(self.tcp_socket, 9)
                status, rank, suit = Protocol.unpack_game_state(data)

                # Format card string
                r_s = {1: 'Ace', 11: 'Jack', 12: 'Queen', 13: 'King'}.get(rank, str(rank))
                s_s = {0: 'Spades', 1: 'Hearts', 2: 'Diamonds', 3: 'Clubs'}.get(suit, '?')
                card_str = f"[{r_s} of {s_s}]"

                if status == 0:  # --- ACTIVE ROUND ---
                    if len(my_hand) < 2:
                        # 2 קלפים ראשונים שלי
                        my_hand.append(rank)
                        val = self.calculate_hand(my_hand)
                        print(f"Server: You got {card_str} | Total: {val}")

                        # מקרה קצה: בלאקג'ק על ההתחלה (21)
                        if len(my_hand) == 2 and val == 21:
                            print("Blackjack! Waiting for dealer...")
                            self.my_turn = False

                    elif len(dealer_hand) == 0:
                        # קלף ראשון של דילר
                        dealer_hand.append(rank)
                        dealer_display.append(card_str)
                        print(f"Dealer shows: {card_str}")

                        # אם לא סיימתי את התור שלי (כי הגעתי ל21), מבקש קלט
                        if self.my_turn:
                            print("Your move (1-Hit, 2-Stand): ", end="", flush=True)
                    else:
                        # המשך משחק
                        if self.my_turn:
                            my_hand.append(rank)
                            val = self.calculate_hand(my_hand)
                            print(f"Server: You got {card_str} | Total: {val}")

                            # === התיקון הקריטי כאן ===
                            # אם הגעתי ל-21 או עברתי, התור עובר לדילר אוטומטית
                            if val >= 21:
                                self.my_turn = False
                                print("Automatic Stand (21 or Bust). Waiting for dealer...")
                            else:
                                print("Your move (1-Hit, 2-Stand): ", end="", flush=True)
                        else:
                            # תור הדילר
                            dealer_hand.append(rank)
                            dealer_display.append(card_str)
                            print(f"Dealer draws: {card_str}")

                else:  # --- ROUND OVER ---
                    # Logic fix for last card duplication
                    my_val = self.calculate_hand(my_hand)
                    # אם הקלף האחרון הוא לא שלי (כי עמדתי), נוסיף לדילר
                    if my_val <= 21 and not self.my_turn:
                        is_dup = False
                        if dealer_display and dealer_display[-1] == card_str:
                            is_dup = True
                        if not is_dup:
                            dealer_hand.append(rank)
                            dealer_display.append(card_str)

                    print("\n" + "=" * 40)
                    res = {1: "DRAW", 2: "YOU LOST!", 3: "YOU WON!"}.get(status, "RESULT")
                    print(f"=== {res} ===")
                    print(f"YOUR:   {my_val}")
                    print(f"DEALER: {self.calculate_hand(dealer_hand)} {dealer_display}")
                    print("=" * 40)

                    self.rounds_played += 1
                    if self.rounds_played < self.requested_rounds:
                        print("Starting next round...")
                    else:
                        print("Final round finished. Waiting for server to close connection...")

                    # RESET
                    my_hand = []
                    dealer_hand = []
                    dealer_display = []
                    self.my_turn = True

        except Exception:
            self.game_active = False
            print("\nServer disconnected. Press Enter to return to menu...")

    def user_input_loop(self):
        while self.game_active:
            try:
                choice = input()
                if not self.game_active: break
                if not choice.strip(): continue

                if choice == '1':
                    # בדיקה מקומית - אם כבר אי אפשר למשוך
                    if not self.my_turn:
                        print("Wait for dealer...")
                        continue
                    self.tcp_socket.sendall(Protocol.pack_action("Hit"))

                elif choice == '2':
                    if not self.my_turn: continue
                    self.my_turn = False
                    self.tcp_socket.sendall(Protocol.pack_action("Stand"))
                else:
                    print("Invalid (1 or 2)")
            except:
                break


if __name__ == "__main__":
    client = GameClient()
    client.start()