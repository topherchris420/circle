"""A deterministic consent timeline; only the demo owns a disposable private key.

Run: python tools/run_authority_demo.py
Frames 0..5: telemetry, proposal, two waiting frames, consent, resumed telemetry.
The key/UUID constants are TEST fixtures, never credentials for real consent.
"""

from __future__ import annotations

from collections import deque
import hashlib
from pathlib import Path
import sys
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from circle_authority import (ActionEnvelope, CircleAuthority, CircleEvent, HumanConsentEvent,
                              Mutation, RestrictedActionEvent, TelemetryEvent, canonical_json)


def run_demo() -> tuple[list[str], dict[str, int]]:
    # Fixed demo fixtures make repeated runs byte-identical. Real signing happens
    # in a separate human-controlled signer, after displaying the bound envelope.
    demo_signer = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    action_id = UUID("8f136ffc-7dd2-4e27-8ab1-21186598b620")
    state: dict[str, int] = {"heart_rate": 0, "simulated_feedback_level": 0}
    history_hash = hashlib.sha256(b"circle-authority-demo/genesis").hexdigest()

    def observe(event: TelemetryEvent) -> None:
        nonlocal history_hash
        if event.name != "heart_rate":
            raise ValueError("unknown telemetry channel")
        state[event.name] = event.value
        history_hash = hashlib.sha256(bytes.fromhex(history_hash) +
                                     canonical_json(state).encode("utf-8")).hexdigest()

    def execute(action: ActionEnvelope, frame: int, timestamp_us: int) -> None:
        # Validate first, then perform one in-memory simulation mutation.
        parameters = action.mutation.parameters()
        value = parameters.get("level")
        if action.mutation.operation != "SET_SIMULATED_FEEDBACK" or type(value) is not int:
            raise ValueError("unsupported mutation")
        state["simulated_feedback_level"] = value

    authority = CircleAuthority(demo_signer.public_key(), execute, observe)
    incoming: deque[CircleEvent] = deque()
    replay_payloads: list[str] = []
    for frame in range(6):
        timestamp_us = frame * 10_000
        incoming.append(TelemetryEvent("heart_rate", 70 + frame))
        if frame == 1:
            action = ActionEnvelope(Mutation("SET_SIMULATED_FEEDBACK", '{"level":2}'),
                                    timestamp_us, history_hash, action_id)
            incoming.append(RestrictedActionEvent(action))
        if frame == 4:
            incoming.append(HumanConsentEvent(action_id, demo_signer.sign(action_id.bytes)))
        result = authority.step(frame, timestamp_us, incoming)
        replay_payloads.extend(result.replay_payloads)
        if frame in (1, 2, 3):
            assert state["simulated_feedback_level"] == 0
            assert action_id in authority.pending_registry
        if frame >= 4:
            assert state["simulated_feedback_level"] == 2
            assert not authority.pending_registry
    return replay_payloads, state


def main() -> int:
    logs, state = run_demo()
    # Persistence/printing is outside the authority step. These strings can be
    # handed unchanged to the host's append-only authority replay writer.
    for payload in logs:
        print(payload)
    print(canonical_json({"final_simulated_state": state}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
