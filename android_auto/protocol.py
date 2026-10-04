"""How the board tells the phone, over Bluetooth, which Wi-Fi to join and where
to connect for wireless Android Auto. No D-Bus here, so the tests run on any PC.

On the RFCOMM channel each message is 2 bytes payload length and 2 bytes
message id (both big-endian), then the payload: a protobuf (proto2) message.
The few fields needed are encoded here by hand, after the .proto files of
WirelessAndroidAutoDongle (github.com/nisargjhaveri/WirelessAndroidAutoDongle, MIT).

The board sends WifiStartRequest (its address and port), the phone asks with
WifiInfoRequest, the board answers WifiInfoResponse (the access point), the phone
reports back (WifiStartResponse, WifiConnectStatus) and opens the TCP connection."""

import struct

WIFI_START_REQUEST = 1
WIFI_INFO_REQUEST = 2
WIFI_INFO_RESPONSE = 3
WIFI_VERSION_REQUEST = 4
WIFI_VERSION_RESPONSE = 5
WIFI_CONNECT_STATUS = 6
WIFI_START_RESPONSE = 7
NAMES = {WIFI_START_REQUEST: "WifiStartRequest", WIFI_INFO_REQUEST: "WifiInfoRequest",
         WIFI_INFO_RESPONSE: "WifiInfoResponse", WIFI_VERSION_REQUEST: "WifiVersionRequest",
         WIFI_VERSION_RESPONSE: "WifiVersionResponse", WIFI_CONNECT_STATUS: "WifiConnectStatus",
         WIFI_START_RESPONSE: "WifiStartResponse"}

WPA2_PERSONAL = 8   # SecurityMode
DYNAMIC = 1         # AccessPointType, as the dongle sends it


def frame(message_id, payload):
    return struct.pack(">HH", len(payload), message_id) + payload


def wifi_start_request(ip, port):
    return frame(WIFI_START_REQUEST, _text(1, ip) + _number(2, port))


def wifi_info_response(ssid, key, bssid):
    return frame(WIFI_INFO_RESPONSE, _text(1, ssid) + _text(2, key) + _text(3, bssid)
                 + _number(4, WPA2_PERSONAL) + _number(5, DYNAMIC))


def read_message(read):
    """The next message as (message id, payload), or None when the channel closed.
    read(n) returns up to n bytes, b"" at the end (like a socket's recv)."""
    header = _read_exactly(read, 4)
    if header is None:
        return None
    length, message_id = struct.unpack(">HH", header)
    payload = _read_exactly(read, length)
    return None if payload is None else (message_id, payload)


def fields(payload):
    """A protobuf message as {field number: value}, for the log: varints as
    numbers, length-delimited fields as bytes."""
    out, i = {}, 0
    while i < len(payload):
        key, i = _read_varint(payload, i)
        number, wire_type = key >> 3, key & 7
        if wire_type == 0:
            out[number], i = _read_varint(payload, i)
        elif wire_type == 2:
            size, i = _read_varint(payload, i)
            out[number], i = payload[i:i + size], i + size
        else:
            raise ValueError(f"unexpected protobuf wire type {wire_type}")
    return out


def _varint(n):
    out = bytearray()
    while True:
        out.append(n & 0x7F | (0x80 if n > 0x7F else 0))
        n >>= 7
        if not n:
            return bytes(out)


def _read_varint(data, i):
    n = shift = 0
    while True:
        byte = data[i]
        i += 1
        n |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return n, i


def _number(field, value):
    return _varint(field << 3) + _varint(value)


def _text(field, value):
    data = value.encode()
    return _varint(field << 3 | 2) + _varint(len(data)) + data


def _read_exactly(read, n):
    data = b""
    while len(data) < n:
        chunk = read(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data
