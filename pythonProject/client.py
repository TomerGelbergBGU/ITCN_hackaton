import socket
import threading
import time
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
            return None, None

        print(f"Listening on UDP port {self.udp_port}...")

        while True:
            try:
                data, addr = udp_client.recvfrom(1024)

                # --- תיקון 1: קבלת טאפל ולא מילון ---
                server_port, server_name = Protocol.unpack_offer(data)

                if server_name:
                    print(f"\nReceived offer from server '{server_name}' at {addr[0]}")
                    return addr[0], server_port
            except Exception as e:
                # הוספתי הדפסה כדי שתראה אם יש שגיאות
                # print(f"UDP Error: {e}")
                continue

    def connect_and_play(self, ip, port):
        """Connects via TCP and handles the game loop."""
        print(f"Connecting to {ip}:{port}...")

        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.connect((ip, port))

            print(f"Sending handshake: Name={self.player_name}")

            # --- תיקון 2: הסדר הנכון של הארגומנטים ---
            # קודם השם (string), אחר כך מספר הסיבובים (int)
            req_msg = Protocol.pack_request(self.player_name, self.requested_rounds)

            self.tcp_socket.sendall(req_msg)

            self.game_active = True

            listen_thread = threading.Thread(target=self.listen_to_server, daemon=True)
            listen_thread.start()

            self.user_input_loop()

        except Exception as e:
            print(f"Connection error: {e}")
            import traceback
            traceback.print_exc()  # זה ידפיס לך בדיוק איפה הבעיה אם תקרה שוב
        finally:
            if self.tcp_socket:
                self.tcp_socket.close()
            print("Disconnected from server. Searching for new server...\n")
            self.game_active = False

    def listen_to_server(self):
        """Listens for messages from the server."""

        # משתנה שיחזיק את הודעת הסיום
        # ברירת המחדל: סיום רגיל
        end_msg = "\nRound ended. Press Enter to continue..."

        try:
            while self.game_active:
                data = self.tcp_socket.recv(1024)

                if not data:
                    print("\nServer closed the connection.")
                    self.game_active = False
                    break

                status, rank, suit = Protocol.unpack_game_state(data)

                # המרת קלפים לטקסט
                ranks_map = {1: 'Ace', 11: 'Jack', 12: 'Queen', 13: 'King'}
                suits_map = {0: 'Spades', 1: 'Hearts', 2: 'Diamonds', 3: 'Clubs'}
                r_str = ranks_map.get(rank, str(rank))
                s_str = suits_map.get(suit, 'Unknown')
                card_str = f"[{r_str} of {s_str}]"

                if status == 0:  # ACTIVE
                    self.cards_seen_in_round += 1
                    print(f"Server: You got {card_str}")
                    if self.cards_seen_in_round >= 2:
                        print("Your move (1-Hit, 2-Stand): ", end="", flush=True)

                else:  # WIN/LOSS/TIE
                    self.cards_seen_in_round = 0
                    res_map = {1: "DRAW", 2: "YOU LOST!", 3: "YOU WON!"}
                    result = res_map.get(status, "Unknown Result")
                    print(f"\n=== Game Over: {result} (Dealer had: {card_str}) ===")

        except (ConnectionResetError, ConnectionAbortedError):
            print("\n\nError: The server disconnected unexpectedly!")
            self.game_active = False
            # משנים את הודעת הסיום למשהו שמתאים לניתוק
            end_msg = "\nConnection lost. Please press Enter to return to main menu..."

        except socket.error as e:
            print(f"\n\nNetwork Error: {e}")
            self.game_active = False
            end_msg = "\nNetwork Error. Press Enter to continue..."

        except Exception as e:
            print(f"\n\nGeneral Error: {e}")
            self.game_active = False
            end_msg = "\nError occurred. Press Enter to continue..."

        # מדפיסים את ההודעה המתאימה (רגילה או שגיאה)
        print(end_msg)

    def user_input_loop(self):
        while self.game_active:
            try:
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

                self.tcp_socket.sendall(Protocol.pack_action(action))
            except:
                break


if __name__ == "__main__":
    client = GameClient()
    client.start()