"""A deterministic stand-in for the musegadget service, for tests and demonstrations.

SimulatedGadgetService listens on a real Unix socket and speaks the Linux
SDK's local protocol the way musegadget's Service._local_request does: the same
request validation, in the same order, with the same reply strings. So
LocalSocketClient is exercised against the protocol, not against a mock of
itself. It never contacts Meta or any network.

A script decides how each successive connection is treated (then `default`):

  ack             the service holds a Muse session: a well-formed message is
                  accepted and acknowledged with a fake message id
  not_connected   the service has no live Muse session (disconnected, or not
                  yet reconnected after one of the SDK's backoff waits)
  error           the SDK reports a failure while forwarding
  drop            the connection closes without a reply
  malformed       the reply is not JSON
  stall           no reply at all (the client must time out)

Malformed requests are refused exactly as the SDK refuses them, whatever the
script says. Stopping the service removes the socket (the gadget disappears);
starting another on the same path brings it back (it reconnects).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import threading
from typing import Any

from .sdk import MAX_LOCAL_REQUEST, REPLY_BAD_SESSION_ID, REPLY_EXPECTED_MESSAGE, REPLY_NOT_CONNECTED, SESSION_ID_RE

BEHAVIORS = ("ack", "not_connected", "error", "drop", "malformed", "stall")


class SimulatedGadgetService:
    """A scripted musegadget local-socket service on a real Unix socket."""

    def __init__(self, path: Path | str, script: list[str] | tuple[str, ...] = (), default: str = "ack") -> None:
        unknown = sorted((set(script) | {default}) - set(BEHAVIORS))
        if unknown:
            raise ValueError(f"unknown behaviors {unknown}; choose from {BEHAVIORS}")
        self.path = Path(path)
        self._script = list(script)
        self.default = default
        self.accepted: list[dict[str, Any]] = []
        self.connections = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "SimulatedGadgetService":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def start(self) -> None:
        if self.path.exists():
            self.path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.path))
        os.chmod(self.path, 0o660)
        server.listen(16)
        server.settimeout(0.05)
        self._server = server
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, name="simulated-musegadget", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._server is not None:
            self._server.close()
        if self.path.exists():
            self.path.unlink()
        self._server = self._thread = None

    def _next_behavior(self) -> str:
        with self._lock:
            self.connections += 1
            return self._script.pop(0) if self._script else self.default

    def _serve(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            behavior = self._next_behavior()
            threading.Thread(target=self._handle, args=(conn, behavior), daemon=True).start()

    def _handle(self, conn: socket.socket, behavior: str) -> None:
        with conn:
            conn.settimeout(10)
            try:
                line = conn.makefile("rb").readline(MAX_LOCAL_REQUEST + 1)
            except OSError:
                return
            if behavior == "drop":
                return
            if behavior == "stall":
                self._stop.wait(30)
                return
            if behavior == "malformed":
                conn.sendall(b"this is not json\n")
                return
            reply = self._reply(line, behavior)
            try:
                conn.sendall(json.dumps(reply).encode() + b"\n")
            except OSError:
                return

    def _reply(self, line: bytes, behavior: str) -> dict[str, Any]:
        # Mirrors musegadget.service.Service._local_request (and _handle_local's error wrapping).
        try:
            request = json.loads(line)
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        message = request.get("message") if isinstance(request, dict) else None
        if not isinstance(message, str) or not message.strip():
            return {"ok": False, "error": REPLY_EXPECTED_MESSAGE}
        session_id = request.get("session_id")
        if session_id is not None and not (isinstance(session_id, str) and SESSION_ID_RE.fullmatch(session_id)):
            return {"ok": False, "error": REPLY_BAD_SESSION_ID}
        if behavior == "not_connected":
            return {"ok": False, "error": REPLY_NOT_CONNECTED}
        if behavior == "error":
            return {"ok": False, "error": "ConnectionError: session ended"}
        with self._lock:
            self.accepted.append({"message": message, "session_id": session_id})
            number = len(self.accepted)
        return {"ok": True, "status": 200, "response": {"message_id": f"simulated-{number:04d}"}}
