import socket
import struct


class Protocol:
    """
    Protocol class for the Blackijecky game.
    Handles all packet encoding/decoding and stores all constants.
    """

    # --- Network Constants ---
    SERVER_PORT = 13122
    BROADCAST_IP = '255.255.255.255'

    # IP used to determine local interface (Google DNS) - never actually connected to
    TEST_IP_FOR_INTERFACE = '8.8.8.8'
    TEST_PORT_FOR_INTERFACE = 80

    BUFFER_SIZE = 1024

    # --- Magic Cookie & Types ---
    MAGIC_COOKIE = 0xabcddcba
    MSG_TYPE_OFFER = 0x02
    MSG_TYPE_REQUEST = 0x03
    MSG_TYPE_PAYLOAD = 0x04

    # --- Struct Formats (Big Endian '!') ---
    # Offer: Cookie(I), Type(B), ServerPort(H), ServerName(32s)
    FMT_OFFER = '!IBH32s'

    # Request: Cookie(I), Type(B), Rounds(B), ClientName(32s)
    FMT_REQUEST = '!IBB32s'

    # Payload (Client -> Server): Cookie(I), Type(B), Decision(5s)
    FMT_PAYLOAD_CLIENT = '!IB5s'

    # Payload (Server -> Client): Cookie(I), Type(B), Status(B), Rank(B), Suit(B)
    # Note: Using 'B' for Rank/Suit is sufficient (1 byte)
    FMT_PAYLOAD_SERVER = '!IBBHB'

    # --- Dynamic Size Calculation ---
    # We calculate sizes automatically to avoid hard-coded numbers like 9, 10, 38
    OFFER_MSG_SIZE = struct.calcsize(FMT_OFFER)
    REQUEST_MSG_SIZE = struct.calcsize(FMT_REQUEST)
    CLIENT_MSG_SIZE = struct.calcsize(FMT_PAYLOAD_CLIENT)
    SERVER_MSG_SIZE = struct.calcsize(FMT_PAYLOAD_SERVER)

    @staticmethod
    def recv_exactly(sock, size):
        """Helper to ensure we receive exactly 'size' bytes (TCP handling)."""
        data = b''
        while len(data) < size:
            try:
                chunk = sock.recv(size - len(data))
                if not chunk:
                    raise ConnectionError("Connection closed remotely")
                data += chunk
            except socket.error as e:
                raise e
        return data

    @staticmethod
    def _pad_string(text, length):
        """Pads string with null bytes to fixed length."""
        encoded = text.encode('utf-8')
        return encoded[:length].ljust(length, b'\x00')

    @staticmethod
    def _decode_string(bytes_data):
        """Decodes string and strips null bytes."""
        return bytes_data.decode('utf-8').rstrip('\x00')

    # --- Packet Methods ---

    @staticmethod
    def pack_offer(server_port, server_name):
        return struct.pack(Protocol.FMT_OFFER, Protocol.MAGIC_COOKIE, Protocol.MSG_TYPE_OFFER, server_port,
                           Protocol._pad_string(server_name, 32))

    @staticmethod
    def unpack_offer(data):
        if len(data) != Protocol.OFFER_MSG_SIZE: raise ValueError("Invalid Size")
        cookie, mtype, port, name = struct.unpack(Protocol.FMT_OFFER, data)
        if cookie != Protocol.MAGIC_COOKIE or mtype != Protocol.MSG_TYPE_OFFER: raise ValueError("Invalid Header")
        return port, Protocol._decode_string(name)

    @staticmethod
    def pack_request(player_name, num_rounds):
        # We ensure num_rounds fits in 1 byte (though logic should handle limits)
        return struct.pack(Protocol.FMT_REQUEST, Protocol.MAGIC_COOKIE, Protocol.MSG_TYPE_REQUEST, num_rounds,
                           Protocol._pad_string(player_name, 32))

    @staticmethod
    def unpack_request(data):
        if len(data) != Protocol.REQUEST_MSG_SIZE: raise ValueError("Invalid Size")
        cookie, mtype, rounds, name = struct.unpack(Protocol.FMT_REQUEST, data)
        if cookie != Protocol.MAGIC_COOKIE or mtype != Protocol.MSG_TYPE_REQUEST: raise ValueError("Invalid Header")
        return rounds, Protocol._decode_string(name)

    @staticmethod
    def pack_action(action):
        # Normalize to 5 chars logic (Hittt/Stand)
        act = "Hittt" if action == "Hit" else "Stand"
        return struct.pack(Protocol.FMT_PAYLOAD_CLIENT, Protocol.MAGIC_COOKIE, Protocol.MSG_TYPE_PAYLOAD,
                           act.encode('utf-8'))

    @staticmethod
    def unpack_action(data):
        if len(data) != Protocol.CLIENT_MSG_SIZE: raise ValueError("Invalid Size")
        cookie, mtype, act = struct.unpack(Protocol.FMT_PAYLOAD_CLIENT, data)
        if cookie != Protocol.MAGIC_COOKIE or mtype != Protocol.MSG_TYPE_PAYLOAD: raise ValueError("Invalid Header")
        return "Hit" if act.decode('utf-8') == "Hittt" else "Stand"

    @staticmethod
    def pack_game_state(status, rank, suit):
        return struct.pack(Protocol.FMT_PAYLOAD_SERVER, Protocol.MAGIC_COOKIE, Protocol.MSG_TYPE_PAYLOAD, status, rank,
                           suit)

    @staticmethod
    def unpack_game_state(data):
        if len(data) != Protocol.SERVER_MSG_SIZE: raise ValueError("Invalid Size")
        cookie, mtype, status, rank, suit = struct.unpack(Protocol.FMT_PAYLOAD_SERVER, data)
        if cookie != Protocol.MAGIC_COOKIE or mtype != Protocol.MSG_TYPE_PAYLOAD: raise ValueError("Invalid Header")
        return status, rank, suit