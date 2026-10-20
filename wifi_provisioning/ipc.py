"""Bounded newline-framed RPC over the restricted local Unix socket."""

import json
import socket
import time

SOCKET = "/run/qr-wifi/control.sock"
LIMIT = 8192


def decode_request(payload):
    try:
        request = json.loads(payload)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise ValueError("Invalid JSON request") from None
    if len(payload) > LIMIT or not isinstance(request, dict):
        raise ValueError("Invalid request size or structure")
    return request


def receive(connection):
    payload = b""
    deadline = time.monotonic() + 2
    while b"\n" not in payload:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Request timed out")
        connection.settimeout(remaining)
        chunk = connection.recv(1024)
        if not chunk:
            raise ValueError("Incomplete request")
        payload += chunk
        if len(payload) > LIMIT:
            raise ValueError("Request too large")
    return payload.split(b"\n", 1)[0]


def call(request):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(SOCKET)
        connection.sendall(json.dumps(request).encode() + b"\n")
        # Responses can include a full scan list, but remain bounded.
        payload = bytearray()
        while b"\n" not in payload:
            chunk = connection.recv(4096)
            if not chunk or len(payload) + len(chunk) > 262144:
                raise ValueError("Invalid service response")
            payload.extend(chunk)
        return json.loads(payload.split(b"\n", 1)[0])
