"""Non-blocking, frame-driven human consent for deterministic CIRCLE mutations.

The host supplies time, UUIDs, an ordered deque and deterministic callbacks.
This module never reads a clock, generates randomness, waits, or writes a file.
Only a dequeued HumanConsentEvent may discharge a registered restricted action.
Replay strings use CIRCLE's sorted, compact, ASCII-escaped JSON convention.

Consent signs exactly ``action_id.bytes`` (16 bytes, not its textual spelling).
Consequently UUIDs must never be reused or rebound across sessions. Persist the
UUID-to-envelope binding and terminal IDs with the host's replay/checkpoint.
This is an in-memory consent gate, not durable exactly-once delivery or hardware
authorization. Callbacks must be bounded, deterministic, in-memory operations;
I/O, key custody and immutable log persistence belong outside the step loop.
"""

from __future__ import annotations

from base64 import b64encode
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
import hashlib
from itertools import islice
import json
import re
from types import MappingProxyType
from typing import TypeAlias
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def canonical_json(value: object) -> str:
    """Serialize finite JSON data identically for hashing and replay."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _nonnegative_integer(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


class ActionState(str, Enum):
    PENDING_SIGNATURE = "PENDING_SIGNATURE"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class Mutation:
    """An operation plus a canonical JSON object, with no mutable nested values.

    ``parameters()`` returns a fresh copy: a caller cannot change a pending
    envelope by modifying the original dict or a decoded copy.
    """

    operation: str
    parameters_json: str = "{}"

    def __post_init__(self) -> None:
        if not isinstance(self.operation, str) or not self.operation.strip():
            raise ValueError("operation must be a nonempty string")
        parameters = json.loads(self.parameters_json)
        if not isinstance(parameters, dict):
            raise ValueError("mutation parameters must be a JSON object")
        object.__setattr__(self, "parameters_json", canonical_json(parameters))

    def parameters(self) -> dict[str, object]:
        return json.loads(self.parameters_json)


@dataclass(frozen=True)
class ActionEnvelope:
    mutation: Mutation
    timestamp_us: int
    state_history_hash: str
    action_id: UUID
    signature: bytes | None = None

    def __post_init__(self) -> None:
        _nonnegative_integer(self.timestamp_us, "timestamp_us")
        if not isinstance(self.mutation, Mutation) or not isinstance(self.action_id, UUID):
            raise TypeError("mutation and action_id must be Mutation and UUID instances")
        if not isinstance(self.state_history_hash, str) or not re.fullmatch(
                r"[0-9a-f]{64}", self.state_history_hash):
            raise ValueError("state_history_hash must be a lowercase SHA-256 hex digest")
        if self.signature is not None and not isinstance(self.signature, bytes):
            raise TypeError("signature must be immutable bytes or None")

    def unsigned_payload(self) -> dict[str, object]:
        return {"action_id": str(self.action_id), "timestamp_us": self.timestamp_us,
                "state_history_hash": self.state_history_hash,
                "mutation": {"operation": self.mutation.operation,
                             "parameters": self.mutation.parameters()}}

    @property
    def envelope_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.unsigned_payload()).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TelemetryEvent:
    """Non-restricted observation; never interpreted as a mutation command."""

    name: str
    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip() or type(self.value) is not int:
            raise ValueError("telemetry requires a nonempty name and an integer value")


@dataclass(frozen=True)
class RestrictedActionEvent:
    action: ActionEnvelope

    def __post_init__(self) -> None:
        if not isinstance(self.action, ActionEnvelope):
            raise TypeError("restricted events require an ActionEnvelope")


@dataclass(frozen=True)
class HumanConsentEvent:
    action_id: UUID
    signature: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.action_id, UUID) or not isinstance(self.signature, bytes):
            raise TypeError("consent requires a UUID and immutable signature bytes")


CircleEvent: TypeAlias = TelemetryEvent | RestrictedActionEvent | HumanConsentEvent
MutationExecutor: TypeAlias = Callable[[ActionEnvelope, int, int], None]
TelemetryObserver: TypeAlias = Callable[[TelemetryEvent], None]


def verify_human_consent(event: HumanConsentEvent, master_public_key: Ed25519PublicKey) -> bool:
    """Pure Ed25519 verification over the action UUID's exact 16-byte encoding."""
    if len(event.signature) != 64:
        return False
    try:
        master_public_key.verify(event.signature, event.action_id.bytes)
    except InvalidSignature:
        return False
    return True


@dataclass(frozen=True)
class ActionRecord:
    envelope: ActionEnvelope
    state: ActionState = ActionState.PENDING_SIGNATURE
    execution_frame: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class FrameResult:
    frame: int
    processed_events: int
    replay_payloads: tuple[str, ...]


class CircleAuthority:
    """Single-owner event reducer; pending consent is state, never a wait.

    FIFO order and the event budget are part of the replay contract. Only the
    queue snapshot present at step entry is eligible; callback-injected events
    wait for the next frame. Unknown/terminal UUID consent is logged and ignored;
    an invalid signature for a pending UUID rejects that action permanently.
    A failed executor is rejected and never retried. Executors must validate
    before committing their in-memory mutation (no partially applied effects).
    """

    def __init__(self, master_public_key: Ed25519PublicKey,
                 execute: MutationExecutor, observe: TelemetryObserver, *,
                 max_events_per_frame: int = 64, max_pending_actions: int = 1024) -> None:
        if not isinstance(master_public_key, Ed25519PublicKey):
            raise TypeError("register an Ed25519 human master public key")
        for value, name in ((max_events_per_frame, "max_events_per_frame"),
                            (max_pending_actions, "max_pending_actions")):
            _nonnegative_integer(value, name)
            if value == 0:
                raise ValueError(f"{name} must be positive")
        self._public_key = master_public_key
        raw_key = master_public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self._key_id = hashlib.sha256(raw_key).hexdigest()
        self._execute = execute
        self._observe = observe
        self._event_budget = max_events_per_frame
        self._pending_limit = max_pending_actions
        self._actions: dict[UUID, ActionRecord] = {}
        self._pending: dict[UUID, ActionRecord] = {}
        self._last_frame = -1
        self._last_timestamp_us = -1
        self._stepping = False
        self._sequence = 0
        self._replay_head = "0" * 64

    @property
    def pending_registry(self) -> Mapping[UUID, ActionRecord]:
        return MappingProxyType(self._pending)

    @property
    def action_registry(self) -> Mapping[UUID, ActionRecord]:
        """Includes terminal UUID tombstones: IDs cannot be registered again."""
        return MappingProxyType(self._actions)

    def _log(self, frame: int, timestamp_us: int, kind: str,
             record: ActionRecord | None = None, **details: object) -> str:
        body: dict[str, object] = {
            "schema": "circle-authority-replay/1", "sequence": self._sequence,
            "previous_record_hash": self._replay_head, "frame": frame,
            "timestamp_us": timestamp_us, "kind": kind, "human_master_key_id": self._key_id,
            **details,
        }
        if record is not None:
            action = record.envelope
            body.update({"action": action.unsigned_payload(), "envelope_hash": action.envelope_hash,
                         "state": record.state.value, "execution_frame": record.execution_frame,
                         "reason": record.reason, "signature_b64": (
                             b64encode(action.signature).decode("ascii") if action.signature is not None else None)})
        digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
        payload = canonical_json({**body, "record_hash": digest})
        self._replay_head = digest
        self._sequence += 1
        return payload

    def _restricted(self, action: ActionEnvelope, frame: int, timestamp_us: int) -> str:
        existing = self._actions.get(action.action_id)
        if existing is not None:
            return self._log(frame, timestamp_us, "ACTION_IGNORED", existing,
                             event_reason="UUID_ALREADY_REGISTERED",
                             attempted_envelope_hash=action.envelope_hash)
        reason = None
        if action.signature is not None:
            reason = "SIGNATURE_MUST_ARRIVE_AS_CONSENT_EVENT"
        elif action.timestamp_us > timestamp_us:
            reason = "ACTION_FROM_FUTURE"
        elif len(self._pending) >= self._pending_limit:
            reason = "PENDING_REGISTRY_FULL"
        record = ActionRecord(action, ActionState.REJECTED if reason else ActionState.PENDING_SIGNATURE,
                              reason=reason)
        self._actions[action.action_id] = record
        if reason is None:
            self._pending[action.action_id] = record
        return self._log(frame, timestamp_us, "ACTION_REGISTERED", record)

    def _consent(self, event: HumanConsentEvent, frame: int, timestamp_us: int) -> str:
        pending = self._pending.pop(event.action_id, None)
        attempted_signature = b64encode(event.signature).decode("ascii")
        if pending is None:
            return self._log(frame, timestamp_us, "CONSENT_IGNORED", self._actions.get(event.action_id),
                             action_id=str(event.action_id), event_reason="UUID_NOT_PENDING",
                             attempted_signature_b64=attempted_signature)
        if not verify_human_consent(event, self._public_key):
            record = replace(pending, state=ActionState.REJECTED, reason="INVALID_SIGNATURE")
        else:
            signed_action = replace(pending.envelope, signature=event.signature)
            # Reserve the terminal ID before calling trusted application code.
            record = ActionRecord(signed_action, ActionState.REJECTED, reason="EXECUTION_FAILED")
            self._actions[event.action_id] = record
            try:
                self._execute(signed_action, frame, timestamp_us)
            except Exception:
                # Stable reason, no environment-dependent exception strings; no retry.
                pass
            else:
                record = ActionRecord(signed_action, ActionState.EXECUTED, execution_frame=frame)
        self._actions[event.action_id] = record
        return self._log(frame, timestamp_us, "CONSENT_PROCESSED", record,
                         attempted_signature_b64=attempted_signature)

    def step(self, frame: int, timestamp_us: int, incoming: deque[CircleEvent]) -> FrameResult:
        """Process bounded FIFO work and return replay strings for host persistence.

        Frames must be contiguous from zero; device time must strictly increase.
        Producers must inject events between steps, not concurrently mutate the
        deque. Record each event's arrival frame/order and these time inputs for
        replay. Rebuild a fresh application state when replaying mutations.
        """
        if self._stepping:
            raise RuntimeError("step is not reentrant")
        _nonnegative_integer(frame, "frame")
        _nonnegative_integer(timestamp_us, "timestamp_us")
        if frame != self._last_frame + 1 or timestamp_us <= self._last_timestamp_us:
            raise ValueError("frames must be contiguous and device time must strictly increase")
        count = min(len(incoming), self._event_budget)
        if any(not isinstance(event, (RestrictedActionEvent, HumanConsentEvent, TelemetryEvent))
               for event in islice(incoming, count)):
            raise TypeError("unsupported CIRCLE event")
        # Detach the batch so producers inside callbacks cannot change this frame.
        batch = tuple(incoming.popleft() for _ in range(count))
        self._last_frame, self._last_timestamp_us = frame, timestamp_us
        self._stepping = True
        logs: list[str] = []
        try:
            for event in batch:
                if isinstance(event, RestrictedActionEvent):
                    logs.append(self._restricted(event.action, frame, timestamp_us))
                elif isinstance(event, HumanConsentEvent):
                    logs.append(self._consent(event, frame, timestamp_us))
                elif isinstance(event, TelemetryEvent):
                    try:
                        self._observe(event)
                    except Exception:
                        logs.append(self._log(frame, timestamp_us, "TELEMETRY_REJECTED",
                                              name=event.name, value=event.value,
                                              event_reason="OBSERVER_FAILED"))
                    else:
                        logs.append(self._log(frame, timestamp_us, "TELEMETRY",
                                              name=event.name, value=event.value))
        finally:
            self._stepping = False
        return FrameResult(frame, count, tuple(logs))
