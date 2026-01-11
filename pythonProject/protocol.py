import socket
import struct


class Protocol:
    """
    Protocol class for the Blackijecky game.
    Handles all packet encoding (packing) and decoding (unpacking).
    Follows the strict format defined in the Hackathon assignment.
    """

    # --- Constants ---
    # Magic Cookie: 4 bytes, verifies packet validity (0xabcddcba)
    MAGIC_COOKIE = 0xabcddcba

    # Message Types
    MSG_TYPE_OFFER = 0x02
    MSG_TYPE_REQUEST = 0x03
    MSG_TYPE_PAYLOAD = 0x04

    # Network Constants
    SERVER_PORT = 13122  # The fixed UDP port clients listen on

    # --- Struct Formats (Big Endian '!') ---
    # Offer: Cookie(I), Type(B), ServerPort(H), ServerName(32s)
    FMT_OFFER = '!IBH32s'

    # Request: Cookie(I), Type(B), Rounds(B), ClientName(32s)
    FMT_REQUEST = '!IBB32s'

    # Payload (Client -> Server): Cookie(I), Type(B), Decision(5s)
    FMT_PAYLOAD_CLIENT = '!IB5s'

    # Payload (Server -> Client): Cookie(I), Type(B), Status(B), Rank(H), Suit(B)
    FMT_PAYLOAD_SERVER = '!IBBHB'

    # --- Helper Methods ---

    @staticmethod
    def recv_exactly(sock, size):
        """
        Helper function to receive exactly 'size' bytes.
        This prevents reading too much (coalescing) or too little (fragmentation).
        """
        data = b''
        while len(data) < size:
            try:
                chunk = sock.recv(size - len(data))
                if not chunk:
                    # אם קיבלנו 0 בייטים, סימן שהצד השני סגר את החיבור
                    raise ConnectionError("Connection closed remotely")
                data += chunk
            except socket.error as e:
                raise e
        return data

    @staticmethod
    def _pad_string(text, length):
        """Helper to pad/truncate a string to a fixed byte length."""
        encoded = text.encode('utf-8')
        if len(encoded) > length:
            return encoded[:length]
        return encoded.ljust(length, b'\x00')

    @staticmethod
    def _decode_string(bytes_data):
        """Helper to decode bytes to string, removing null padding."""
        return bytes_data.decode('utf-8').rstrip('\x00')

    # --- Packing Methods (Create Bytes) ---

    @staticmethod
    def pack_offer(server_port, server_name):
        padded_name = Protocol._pad_string(server_name, 32)
        return struct.pack(
            Protocol.FMT_OFFER,
            Protocol.MAGIC_COOKIE,
            Protocol.MSG_TYPE_OFFER,
            server_port,
            padded_name
        )

    @staticmethod
    def pack_request(player_name, num_rounds):
        padded_name = Protocol._pad_string(player_name, 32)
        return struct.pack(
            Protocol.FMT_REQUEST,
            Protocol.MAGIC_COOKIE,
            Protocol.MSG_TYPE_REQUEST,
            num_rounds,
            padded_name
        )

    @staticmethod
    def pack_action(action):
        if action == "Hit":
            action_str = "Hittt"
        elif action == "Stand":
            action_str = "Stand"
        else:
            raise ValueError(f"Invalid action: {action}")

        return struct.pack(
            Protocol.FMT_PAYLOAD_CLIENT,
            Protocol.MAGIC_COOKIE,
            Protocol.MSG_TYPE_PAYLOAD,
            action_str.encode('utf-8')
        )

    @staticmethod
    def pack_game_state(status, rank, suit):
        return struct.pack(
            Protocol.FMT_PAYLOAD_SERVER,
            Protocol.MAGIC_COOKIE,
            Protocol.MSG_TYPE_PAYLOAD,
            status,
            rank,
            suit
        )

    # --- Unpacking Methods (Parse Bytes) ---

    @staticmethod
    def unpack_offer(data):
        if len(data) != struct.calcsize(Protocol.FMT_OFFER):
            raise ValueError("Invalid offer packet size")

        cookie, msg_type, port, name_bytes = struct.unpack(Protocol.FMT_OFFER, data)

        if cookie != Protocol.MAGIC_COOKIE or msg_type != Protocol.MSG_TYPE_OFFER:
            raise ValueError("Invalid Packet Header")

        return port, Protocol._decode_string(name_bytes)

    @staticmethod
    def unpack_request(data):
        if len(data) != struct.calcsize(Protocol.FMT_REQUEST):
            raise ValueError("Invalid request packet size")

        cookie, msg_type, rounds, name_bytes = struct.unpack(Protocol.FMT_REQUEST, data)

        if cookie != Protocol.MAGIC_COOKIE or msg_type != Protocol.MSG_TYPE_REQUEST:
            raise ValueError("Invalid Packet Header")

        return rounds, Protocol._decode_string(name_bytes)

    @staticmethod
    def unpack_action(data):
        if len(data) != struct.calcsize(Protocol.FMT_PAYLOAD_CLIENT):
            raise ValueError("Invalid action packet size")

        cookie, msg_type, action_bytes = struct.unpack(Protocol.FMT_PAYLOAD_CLIENT, data)

        if cookie != Protocol.MAGIC_COOKIE or msg_type != Protocol.MSG_TYPE_PAYLOAD:
            raise ValueError("Invalid Packet Header")

        action_str = action_bytes.decode('utf-8')
        if action_str == "Hittt":
            return "Hit"
        return "Stand"

    @staticmethod
    def unpack_game_state(data):
        if len(data) != struct.calcsize(Protocol.FMT_PAYLOAD_SERVER):
            raise ValueError("Invalid game state packet size")

        cookie, msg_type, status, rank, suit = struct.unpack(Protocol.FMT_PAYLOAD_SERVER, data)

        if cookie != Protocol.MAGIC_COOKIE or msg_type != Protocol.MSG_TYPE_PAYLOAD:
            raise ValueError("Invalid Packet Header")

        return status, rank, suit