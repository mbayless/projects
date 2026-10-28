"""Minimal Minecraft RCON client (standard library only).

RCON is the server's remote command interface: send a command as text, get its
reply as text. Protocol: https://minecraft.wiki/w/RCON
"""
import socket
import struct

LOGIN, COMMAND = 3, 2


class RconError(Exception):
    pass


class RconAuthError(RconError):
    """Wrong password. Retrying won't help."""


class Rcon:
    def __init__(self, host, port, password, timeout=5):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self._id = 0
        if self._send(LOGIN, password)[0] == -1:
            raise RconAuthError("RCON login failed: check RCON_PASSWORD in minecraft/.env")

    def _send(self, kind, text):
        self._id += 1
        body = struct.pack("<ii", self._id, kind) + text.encode("utf-8") + b"\x00\x00"
        self.sock.sendall(struct.pack("<i", len(body)) + body)
        size = struct.unpack("<i", self._read(4))[0]
        reply_id, _ = struct.unpack("<ii", self._read(8))
        payload = self._read(size - 8)[:-2]
        return reply_id, payload.decode("utf-8", "replace")

    def _read(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise RconError("Server closed the RCON connection")
            data += chunk
        return data

    def run(self, command):
        """Run one command (no leading slash) and return the server's reply."""
        return self._send(COMMAND, command)[1]

    def close(self):
        self.sock.close()
