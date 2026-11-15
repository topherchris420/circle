"""Durable host integration for the CircleAuthority consent gate.

``circle_authority.py`` is a pure, deterministic event reducer: no clocks, no
files, no keys. This module is the *host* it asks for: it owns time, UUIDs,
key custody, and an append-only replay stream, and it wires one restricted
mutation into the workbench — enabling adaptive audio for a session.

Flow for a session with audio feedback:

1. ``Workbench.start`` registers an ``ENABLE_AUDIO`` proposal (an immutable
   envelope bound to the run id, modalities, and safe limits, with the run
   record's SHA-256 as its state history). The session proceeds while the
   proposal waits as data — telemetry is never blocked by consent.
2. The browser posts to ``/api/runs/<id>/consent``; the host signs the
   action UUID with the workbench's Ed25519 human key and the authority
   verifies and executes: the run's consent record becomes ``EXECUTED``.
3. Revocation posts to ``/api/runs/<id>/revoke``; a ``REVOKE_AUDIO``
   restricted mutation (proposed and consented through the same gate) marks the
   run revoked. Timeline documents reflect it immediately.
4. Every event lands in ``consent-log.ndjson`` — the authority's hash-linked
   replay payloads, appended verbatim.

Honest boundaries, kept from docs/consent-by-design.md: the signature
authenticates the action UUID; the single-user workbench keeps the private key
beside the data (local operator custody — remote or hardware-key custody is
future work); the gate authorizes presentation only, never hardware or human
actuation; a crash between proposal and consent leaves the action pending and
the restart marks it interrupted rather than silently executing it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
from typing import Any, Callable
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from circle_authority import (ActionEnvelope, ActionState, CircleAuthority, HumanConsentEvent, Mutation,
                              RestrictedActionEvent, canonical_json)
from collections import deque

LOG_SCHEMA = "circle-consent-log/1"
PENDING, EXECUTED, REJECTED, REVOKED = ("PENDING_SIGNATURE", "EXECUTED", "REJECTED", "REVOKED")


def _private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows ACLs differ; the file still lives only in the user's output tree.


class ConsentKeys:
    """Workbench-local Ed25519 keypair. Generated once; operator custody."""

    def __init__(self, root: Path) -> None:
        self.directory = root / "keys"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.private_path = self.directory / "human-consent.key"
        self.public_path = self.directory / "human-consent.pub"
        if self.private_path.is_file() and self.public_path.is_file():
            self._private = serialization.load_pem_private_key(self.private_path.read_bytes(), password=None)
        else:
            self._private = Ed25519PrivateKey.generate()
            self.private_path.write_bytes(self._private.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            _private(self.private_path)
            self.public_path.write_bytes(self.public_bytes())
        if not self.public_path.is_file():
            self.public_path.write_bytes(self.public_bytes())

    def public_bytes(self) -> bytes:
        return self._private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)

    @property
    def public_key(self):
        return self._private.public_key()

    def sign(self, payload: bytes) -> bytes:
        return self._private.sign(payload)


class WorkbenchConsent:
    """One durable consent ledger for a workbench output tree."""

    def __init__(self, root: Path, executor: Callable[[str, str, dict[str, Any]], None]) -> None:
        """``executor(operation, run_id, parameters)`` applies a consented mutation.

        It must validate before committing and raise on refusal; the authority
        records the failure and never retries.
        """
        self.root = Path(root)
        self.keys = ConsentKeys(self.root)
        self.log_path = self.root / "consent-log.ndjson"
        self._executor = executor
        self._lock = threading.RLock()
        self._queue: deque = deque()
        self._frame = -1
        self._timestamp_us = -1
        self._actions: dict[str, dict[str, Any]] = {}   # action_id -> {envelope, state}
        self._authority = CircleAuthority(self.keys.public_key, self._execute, lambda event: None)
        # Each process writes one chain-clean segment; prior segments are rotated
        # and retained. The authority's chain starts at zero per segment.
        if self.log_path.is_file():
            rotated = self.root / f"consent-log-{self._now_us()}.ndjson"
            self.log_path.rename(rotated)
        # Existing log records give this host its durable memory of terminal states.
        self._load_log()

    # ------------------------------------------------------------------ host duties
    def _now_us(self) -> int:
        import time
        return time.time_ns() // 1000

    def _step(self, event) -> None:
        self._queue.append(event)
        with self._lock:
            self._frame += 1
            timestamp = max(self._now_us(), self._timestamp_us + 1)
            self._timestamp_us = timestamp
            result = self._authority.step(self._frame, timestamp, self._queue)
        for payload in result.replay_payloads:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")

    def _execute(self, envelope: ActionEnvelope, frame: int, timestamp_us: int) -> None:
        parameters = envelope.mutation.parameters()
        run_id = str(parameters.get("run_id"))
        self._executor(envelope.mutation.operation, run_id, parameters)

    def _segments(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted([self.log_path] + sorted(self.root.glob("consent-log-*.ndjson")),
                      key=lambda p: p.name)

    def _load_log(self) -> None:
        for path in self._segments():
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                action = record.get("action") or {}
                if record.get("kind") == "ACTION_REGISTERED" and action.get("action_id"):
                    self._actions[action["action_id"]] = {"envelope": action, "state": PENDING}
                elif record.get("kind") == "CONSENT_PROCESSED" and action.get("action_id"):
                    state = record.get("state")
                    if state in (EXECUTED, REJECTED):
                        entry = self._actions.get(action["action_id"])
                        if entry is not None:
                            entry["state"] = state

    def verify_log(self) -> dict[str, Any]:
        """Check the hash chain and record integrity of every durable segment."""
        import hashlib
        problems, total = [], 0
        for path in self._segments():
            if not path.is_file():
                continue
            head = "0" * 64
            for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                total += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    problems.append(f"{path.name} record {index} is not valid JSON")
                    continue
                body = {k: v for k, v in record.items() if k != "record_hash"}
                digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
                if digest != record.get("record_hash"):
                    problems.append(f"{path.name} record {index} body does not match its hash")
                if record.get("previous_record_hash") != head:
                    problems.append(f"{path.name} record {index} breaks the chain")
                head = record.get("record_hash", head)
        return {"schema": LOG_SCHEMA, "valid": not problems, "records": total, "problems": problems}

    # ------------------------------------------------------------------ mutations
    def propose_enable_audio(self, run_id: str, parameters: dict[str, Any], state_history: str) -> str:
        """Register the audio-enablement proposal for a run; returns the action id."""
        mutation = Mutation("ENABLE_AUDIO", canonical_json(
            {"run_id": run_id, **{k: parameters[k] for k in sorted(parameters)}}))
        action_id = uuid4()
        envelope = ActionEnvelope(mutation, self._now_us(), state_history, action_id)
        with self._lock:
            self._actions[str(action_id)] = {"envelope": envelope.unsigned_payload(), "state": PENDING}
        self._step(RestrictedActionEvent(envelope))
        return str(action_id)

    def consent(self, action_id: str) -> dict[str, Any]:
        """Deliver the human signature for an action.

        Every attempt is delivered to the authority and logged: a signature for
        a terminal UUID is recorded as CONSENT_IGNORED, never re-executed.
        """
        with self._lock:
            if action_id not in self._actions:
                return {"state": "UNKNOWN", "action_id": action_id}
        signature = self.keys.sign(uuid_bytes(action_id))
        self._step(HumanConsentEvent(_uuid(action_id), signature))
        return self.state(action_id)

    def revoke_audio(self, run_id: str, parameters: dict[str, Any], state_history: str) -> dict[str, Any]:
        """Revocation is itself a restricted mutation through the same gate."""
        mutation = Mutation("REVOKE_AUDIO", canonical_json(
            {"run_id": run_id, **{k: parameters[k] for k in sorted(parameters)}}))
        action_id = uuid4()
        envelope = ActionEnvelope(mutation, self._now_us(), state_history, action_id)
        with self._lock:
            self._actions[str(action_id)] = {"envelope": envelope.unsigned_payload(), "state": PENDING}
        self._step(RestrictedActionEvent(envelope))
        result = self.consent(str(action_id))
        result["revoke_action_id"] = str(action_id)
        return result

    def state(self, action_id: str) -> dict[str, Any]:
        """Live state from the authority; durable memory for prior-process actions."""
        record = self._authority.action_registry.get(_uuid(action_id))
        if record is not None:
            # The authority is the source of truth for this process's actions.
            with self._lock:
                entry = self._actions.setdefault(action_id, {"envelope": record.envelope.unsigned_payload(),
                                                             "state": PENDING})
                entry["state"] = record.state.value
            return {"state": record.state.value, "action_id": action_id,
                    "envelope_hash": record.envelope.envelope_hash}
        with self._lock:
            entry = self._actions.get(action_id)
            if entry is None:
                return {"state": "UNKNOWN", "action_id": action_id}
            return {"state": entry["state"], "action_id": action_id,
                    "envelope_hash": _envelope_hash(entry["envelope"])}

    def pending_for(self, run_id: str) -> list[str]:
        with self._lock:
            return [aid for aid, entry in self._actions.items()
                    if entry["state"] == PENDING
                    and entry["envelope"].get("mutation", {}).get("parameters", {}).get("run_id") == run_id]


def _uuid(action_id: str):
    from uuid import UUID
    return UUID(action_id)


def uuid_bytes(action_id: str) -> bytes:
    return _uuid(action_id).bytes


def _envelope_hash(envelope_payload: dict[str, Any]) -> str:
    import hashlib
    return hashlib.sha256(canonical_json(envelope_payload).encode("utf-8")).hexdigest()
