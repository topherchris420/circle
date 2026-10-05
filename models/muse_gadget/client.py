"""Client for the musegadget service's local socket, the one door the SDK gives local programs.

Protocol (musegadget service.py, Service.serve_local and _local_request): connect
to a Unix socket owned by root and the gadget's run-as group (mode 0660), send
one JSON line {"message": "...", "session_id": "..."} (session_id optional,
naming a side chat), and read one JSON line back. The service forwards the text
to the Muse as a chat turn from this device and replies
{"ok": true, "status": ..., "response": ...} or {"ok": false, "error": "..."}.

An acknowledged message means the Muse service accepted a chat turn. It does
not mean a person read it, and anything the Muse answers appears in the Muse
app, written by an AI assistant.

Every outcome is classified and timed on the host's monotonic clock; a delivery
problem is a result, never an exception. probe() checks that a service is
listening and speaking the protocol by sending a request the service must
refuse, so a probe never reaches the Muse.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import stat
import time
from typing import Any, Callable

from .sdk import (MAX_LOCAL_REQUEST, REPLY_EXPECTED_MESSAGE, REPLY_NOT_CONNECTED, SESSION_ID_RE, socket_path)

MAX_REPLY_BYTES = 1024 * 1024
SEND_OUTCOMES = ("DELIVERED_ACK", "NOT_CONNECTED", "REJECTED", "INVALID_REQUEST", "SERVICE_ABSENT", "NOT_A_SOCKET",
                 "PERMISSION_DENIED", "CONNECTION_REFUSED", "CONNECTION_DROPPED", "TIMEOUT", "MALFORMED_REPLY")
PROBE_OUTCOMES = ("SERVICE_RESPONDING", "UNEXPECTED_REPLY", "SERVICE_ABSENT", "NOT_A_SOCKET", "PERMISSION_DENIED",
                  "CONNECTION_REFUSED", "CONNECTION_DROPPED", "TIMEOUT", "MALFORMED_REPLY")


@dataclass(frozen=True)
class Exchange:
    """One request to the service and how it ended."""

    outcome: str
    detail: str
    started_us: int
    finished_us: int
    reply: dict[str, Any] | None = None

    @property
    def round_trip_us(self) -> int:
        return self.finished_us - self.started_us


def _monotonic_us() -> int:
    return time.monotonic_ns() // 1000


class LocalSocketClient:
    """Talks to a musegadget service (or SimulatedGadgetService) over its Unix socket."""

    def __init__(self, path: Path | str | None = None, timeout_s: float = 10.0,
                 clock: Callable[[], int] = _monotonic_us,
                 opener: Callable[[str, float], socket.socket] | None = None) -> None:
        if not 0 < timeout_s <= 120:
            raise ValueError("timeout_s must be in (0, 120] s")
        self.path = Path(path) if path is not None else socket_path()
        self.timeout_s = timeout_s
        self.clock = clock
        self._opener = opener or _open_unix

    def probe(self) -> Exchange:
        """Is a service listening and speaking the protocol? Sends {} (refused by the service; nothing is forwarded)."""
        exchange = self._exchange(b"{}\n")
        if exchange.reply is None:
            return exchange
        if exchange.reply == {"ok": False, "error": REPLY_EXPECTED_MESSAGE}:
            return _with(exchange, "SERVICE_RESPONDING", "the service answered the protocol's refusal of an empty request")
        return _with(exchange, "UNEXPECTED_REPLY", f"an empty request drew {json.dumps(exchange.reply)[:200]}")

    def send(self, message: str, session_id: str | None = None) -> Exchange:
        """Post `message` to the Muse chat (a side chat when session_id is given)."""
        problem, line = None, b""
        if not isinstance(message, str) or not message.strip():
            problem = "message must be non-empty text"
        elif session_id is not None and not (isinstance(session_id, str) and SESSION_ID_RE.fullmatch(session_id)):
            problem = "session_id must be 1-64 letters, digits and dashes"
        else:
            line = json.dumps({"message": message, **({"session_id": session_id} if session_id else {})}).encode() + b"\n"
            if len(line) > MAX_LOCAL_REQUEST:
                problem = f"request is {len(line)} bytes; the service reads at most {MAX_LOCAL_REQUEST}"
        if problem:
            now = self.clock()
            return Exchange("INVALID_REQUEST", problem, now, now)
        exchange = self._exchange(line)
        if exchange.reply is None:
            return exchange
        if exchange.reply.get("ok") is True:
            return _with(exchange, "DELIVERED_ACK", "the Muse service accepted the chat turn")
        error = str(exchange.reply.get("error", ""))
        if error == REPLY_NOT_CONNECTED:
            return _with(exchange, "NOT_CONNECTED", "the gadget service has no live session with the Muse")
        return _with(exchange, "REJECTED", f"the service refused the message: {error[:300]}")

    def _exchange(self, line: bytes) -> Exchange:
        started = self.clock()

        def done(outcome: str, detail: str, reply: dict[str, Any] | None = None) -> Exchange:
            return Exchange(outcome, detail, started, self.clock(), reply)

        try:
            mode = os.stat(self.path).st_mode
        except FileNotFoundError:
            return done("SERVICE_ABSENT", f"no socket at {self.path}: the musegadget service is not running here")
        except PermissionError:
            return done("PERMISSION_DENIED", f"cannot inspect {self.path}")
        if not stat.S_ISSOCK(mode):
            return done("NOT_A_SOCKET", f"{self.path} exists but is not a socket")
        try:
            with self._opener(str(self.path), self.timeout_s) as sock:
                sock.sendall(line)
                with sock.makefile("rb") as stream:
                    raw = stream.readline(MAX_REPLY_BYTES + 1)
        except PermissionError:
            return done("PERMISSION_DENIED", "this account is not in the socket's group (root and the gadget's run-as "
                                             "group may connect)")
        except ConnectionRefusedError:
            return done("CONNECTION_REFUSED", f"nothing is listening on {self.path} (a stale socket?)")
        except (socket.timeout, TimeoutError):
            return done("TIMEOUT", f"no reply within {self.timeout_s:g} s")
        except (ConnectionResetError, BrokenPipeError) as exc:
            return done("CONNECTION_DROPPED", f"the service closed the connection ({type(exc).__name__})")
        except OSError as exc:
            return done("CONNECTION_DROPPED", f"{type(exc).__name__}: {exc}")
        if not raw:
            return done("CONNECTION_DROPPED", "the service closed the connection without replying")
        if len(raw) > MAX_REPLY_BYTES or not raw.endswith(b"\n"):
            return done("MALFORMED_REPLY", "the reply is not one complete line within the size limit")
        try:
            reply = json.loads(raw)
        except ValueError:
            return done("MALFORMED_REPLY", "the reply is not JSON")
        if not isinstance(reply, dict) or not isinstance(reply.get("ok"), bool):
            return done("MALFORMED_REPLY", "the reply is not an object with a boolean ok")
        return done("REPLIED", "the service replied", reply)


def _open_unix(path: str, timeout_s: float) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout_s)
    try:
        sock.connect(path)
    except BaseException:
        sock.close()
        raise
    return sock


def _with(exchange: Exchange, outcome: str, detail: str) -> Exchange:
    return Exchange(outcome, detail, exchange.started_us, exchange.finished_us, exchange.reply)
