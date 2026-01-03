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
    MAX_PACKET_SIZE = 1024  # Buffer size for reading packets

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
        """
        Creates the UDP broadcast message (Server -> Client).
        starting with the settings for the message, then the cookie
        that tells us that this is an actual message for us
        then the 02 that says offer (from the instructions)
        then the port that he want to send to the server
        that the padded name of the server
        """
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
        """
        Creates the TCP request message (Client -> Server).
        starting with the settings for the message, then the cookie
        that tells us that this is an actual message for us
        then the 03 that says request (from the instructions)
        then the amount of rounds that the client wants to play
        that the padded name of the client
        """
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
        """
        Creates the gameplay action message (Client -> Server).
        Action must be 'Hit' or 'Stand'. Format requires exactly 5 bytes.
        """
        if action == "Hit":
            action_str = "Hittt"
        elif action == "Stand":
            action_str = "Stand"
        else:
            # אם הגענו לכאן, המתכנת של הלקוח עשה טעות
            raise ValueError(f"Invalid action: {action}. Must be 'Hit' or 'Stand'.")

        return struct.pack(
            Protocol.FMT_PAYLOAD_CLIENT,
            Protocol.MAGIC_COOKIE,
            Protocol.MSG_TYPE_PAYLOAD,
            action_str.encode('utf-8')
        )

    @staticmethod
    def pack_game_state(status, rank, suit):
        """
        Creates the gameplay state message (Server -> Client).
        Includes status (win/loss/active) and card details.
        """
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
        """
        Parses UDP offer.
        Returns: (server_port, server_name)
        Raises: ValueError if cookie or type is invalid.
        """
        if len(data) != struct.calcsize(Protocol.FMT_OFFER):
            raise ValueError("Invalid offer packet size")

        cookie, msg_type, port, name_bytes = struct.unpack(Protocol.FMT_OFFER, data)

        if cookie != Protocol.MAGIC_COOKIE:
            raise ValueError("Invalid Magic Cookie")
        if msg_type != Protocol.MSG_TYPE_OFFER:
            raise ValueError("Invalid Message Type (Expected Offer)")

        return port, Protocol._decode_string(name_bytes)

    @staticmethod
    def unpack_request(data):
        """
        Parses TCP request.
        Returns: (num_rounds, player_name)
        """
        # Note: In TCP streams, ensure you read exactly the right amount of bytes first!
        if len(data) != struct.calcsize(Protocol.FMT_REQUEST):
            raise ValueError("Invalid request packet size")

        cookie, msg_type, rounds, name_bytes = struct.unpack(Protocol.FMT_REQUEST, data)

        if cookie != Protocol.MAGIC_COOKIE:
            raise ValueError("Invalid Magic Cookie")
        if msg_type != Protocol.MSG_TYPE_REQUEST:
            raise ValueError("Invalid Message Type (Expected Request)")

        return rounds, Protocol._decode_string(name_bytes)

    @staticmethod
    def unpack_action(data):
        """
        Parses client action (Server side).
        Returns: 'Hit' or 'Stand' (string)
        """
        if len(data) != struct.calcsize(Protocol.FMT_PAYLOAD_CLIENT):
            raise ValueError("Invalid action packet size")

        cookie, msg_type, action_bytes = struct.unpack(Protocol.FMT_PAYLOAD_CLIENT, data)

        if cookie != Protocol.MAGIC_COOKIE:
            raise ValueError("Invalid Magic Cookie")
        if msg_type != Protocol.MSG_TYPE_PAYLOAD:
            raise ValueError("Invalid Message Type (Expected Payload)")

        action_str = action_bytes.decode('utf-8')
        # Normalize "Hittt" back to "Hit" for internal logic
        if action_str == "Hittt":
            return "Hit"
        return "Stand"

    @staticmethod
    def unpack_game_state(data):
        """
        Parses server game state (Client side).
        Returns: (status, rank, suit)
        """
        if len(data) != struct.calcsize(Protocol.FMT_PAYLOAD_SERVER):
            raise ValueError("Invalid game state packet size")

        cookie, msg_type, status, rank, suit = struct.unpack(Protocol.FMT_PAYLOAD_SERVER, data)

        if cookie != Protocol.MAGIC_COOKIE:
            raise ValueError("Invalid Magic Cookie")
        if msg_type != Protocol.MSG_TYPE_PAYLOAD:
            raise ValueError("Invalid Message Type (Expected Payload)")

        return status, rank, suit