"""GameLink: TCP server end of the Sail connection.

Ported verbatim from the workshop (oot-dojo ootdojo/link.py).

The game connects to us. One client at a time. Thread-based; requests are
synchronous (send, block on matching response id), events accumulate in a
queue the caller can drain.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
from typing import Any, Optional

from .protocol import DEFAULT_PORT


class LinkError(RuntimeError):
    pass


class GameLink:
    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self._server: Optional[socket.socket] = None
        self._client: Optional[socket.socket] = None
        self._client_lock = threading.Lock()
        self._next_id = 1
        self._pending: dict[int, queue.Queue] = {}
        self._pending_lock = threading.Lock()
        self.events: queue.Queue = queue.Queue()
        self._running = False
        self._connected = threading.Event()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(1)
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        for sock in (self._client, self._server):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

    def wait_connected(self, timeout: float = 60.0) -> bool:
        return self._connected.wait(timeout)

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    # -- internals ---------------------------------------------------------

    def _accept_loop(self) -> None:
        while self._running:
            try:
                client, addr = self._server.accept()
            except OSError:
                return
            with self._client_lock:
                self._client = client
            self._connected.set()
            self._read_loop(client)
            self._connected.clear()
            with self._client_lock:
                self._client = None

    def _read_loop(self, client: socket.socket) -> None:
        buf = b""
        while self._running:
            try:
                data = client.recv(4096)
            except OSError:
                break
            if not data:
                break
            buf += data
            while b"\0" in buf:
                raw, buf = buf.split(b"\0", 1)
                if not raw.strip():
                    continue
                try:
                    msg = json.loads(raw.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue
                self._dispatch(msg)

    def _dispatch(self, msg: dict) -> None:
        if msg.get("type") == "dojo_event":
            self.events.put(msg)
            return
        msg_id = msg.get("id")
        with self._pending_lock:
            waiter = self._pending.pop(msg_id, None)
        if waiter is not None:
            waiter.put(msg)
        else:
            # Response nobody is waiting for; stash as event for visibility.
            self.events.put(msg)

    # -- API ---------------------------------------------------------------

    def request(self, payload: dict, timeout: float = 5.0) -> dict:
        """Send a request to the game and block for its response."""
        if not self.connected:
            raise LinkError("game not connected")

        with self._pending_lock:
            msg_id = self._next_id
            self._next_id += 1
            waiter: queue.Queue = queue.Queue(maxsize=1)
            self._pending[msg_id] = waiter

        payload = dict(payload)
        payload["id"] = msg_id
        raw = json.dumps(payload).encode("utf-8") + b"\0"

        with self._client_lock:
            client = self._client
        if client is None:
            raise LinkError("game disconnected")
        try:
            client.sendall(raw)
        except OSError as e:
            raise LinkError(f"send failed: {e}") from e

        try:
            return waiter.get(timeout=timeout)
        except queue.Empty:
            with self._pending_lock:
                self._pending.pop(msg_id, None)
            raise LinkError(f"timeout waiting for response to {payload.get('op', payload.get('type'))}")

    def drain_events(self) -> list[dict]:
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out
