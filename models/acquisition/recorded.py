"""A recorded evidence bundle as a source of device records.

RecordedSource replays an exported run directory (session.ndjson plus
raw/*.csv.gz) through the same closed loop that produced it. Before anything
reaches the loop it checks that each raw stream matches the SHA-256 bound in
its STREAM_DESCRIPTOR record: unverified data is not replayed.

A recording cannot respond to a new cue, so its only honest actuator is
NullActuator (target NONE): decisions are re-derived and the commands they
would have issued are collected beside the ones the record holds; nothing is
actuated. tools/audit_physiology_run.py goes further and rebuilds every derived
record. This answers the narrower question: fed this recording through the
acquisition boundary, does the loop decide exactly as recorded?

To replay a recording of your own, write it in this bundle format (see
docs/hardware-sources.md). CIRCLE ships no human recordings.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from models.physiology.evidence import EVENT_KIND_FLAG, controller_config_from_records, raw_session_from_bundle
from models.physiology.loop import ActuatorCapability, Capabilities, LoopResult, NullActuator, SignalCapability
from models.physiology.streams import STREAM_COLUMNS, RawSession
from models.session_records import load_session


def _flag(record: dict[str, Any], prefix: str) -> str | None:
    return next((f[len(prefix):] for f in record["status_flags"] if f.startswith(prefix)), None)


class RecordedSource:
    """An exported run directory, verified, as a HardwareSource."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.records = load_session(self.directory / "session.ndjson")
        self.raw, content = raw_session_from_bundle(self.directory, self.records)
        descriptors = [r for r in self.records if r["record_type"] == "STREAM_DESCRIPTOR"]
        bound = {r["stream_id"]: _flag(r, "CONTENT_SHA256:") for r in descriptors}
        mismatched = sorted(name for name in content if bound.get(name) != content[name])
        if mismatched:
            raise ValueError(f"raw content of {mismatched} does not match the SHA-256 bound in the session record; "
                             "unverified data is not replayed")
        self.provenance = {r["stream_id"]: r["provenance"] for r in descriptors}
        self.controller_config, self.evaluation_end_us = controller_config_from_records(self.records)
        self.header = next(r for r in self.records if r["record_type"] == "SESSION_HEADER")

    def capabilities(self) -> Capabilities:
        d = self.raw.descriptors
        return Capabilities(
            source=f"recording:{_flag(self.header, 'SESSION_ID:') or self.directory.name}", connected=None,
            connection_state="RECORDED",
            signals=tuple(SignalCapability(name, STREAM_COLUMNS.get(name, tuple(stream.columns)),
                                           d.get(name, {}).get("nominal_rate_hz"), self.provenance.get(name, "UNKNOWN"),
                                           tuple(sorted(d.get(name, {}).items())))
                          for name, stream in self.raw.streams.items()),
            actuators=(ActuatorCapability("replay", "NONE", ("RECORDED_COMMANDS_COMPARED",),
                                          "A recording cannot respond to cues; commands are compared, not sent"),),
            sdk_version=None, hardware=_flag(self.header, "HARDWARE_MODEL:") or "as recorded",
            authentication="NOT_APPLICABLE",
            limitations=("A replay shows what the controller would decide on recorded data; it cannot show a response "
                         "to a cue the recording never received.",))

    def start(self) -> int | None:
        markers = sorted(e.device_time_us for e in self.raw.events_of("PHASE_START:"))
        return markers[0] if markers else None

    def advance(self, device_time_us: int) -> bool:
        return device_time_us <= self.evaluation_end_us

    def view(self, device_time_us: int) -> RawSession:
        return self.raw.until(device_time_us)

    def complete_through_us(self) -> float:
        return math.inf

    def finish(self) -> RawSession:
        return self.raw

    def compare(self, result: LoopResult, actuator: NullActuator) -> dict[str, Any]:
        """Replayed decisions and commands against those the record holds."""
        recorded = [(r["decision_time_us"], _flag(r, "ACTION:"), r.get("decision_id"))
                    for r in self.records if r["record_type"] == "MODEL_RESULT" and "CONTROLLER_EVALUATION" in r["status_flags"]]
        recorded.sort()
        replayed = [(ev.decision_time_us, ev.action, ev.decision_id) for ev in result.evaluations]
        commands = sorted(r["device_time_start_us"] for r in self.records if r["record_type"] == "EVENT" and any(
            f in (EVENT_KIND_FLAG + "HAPTIC_COMMAND", EVENT_KIND_FLAG + "HAPTIC_COMMAND_SHAM") for f in r["status_flags"]))
        first = next((i for i, (a, b) in enumerate(zip(recorded, replayed)) if a != b), None)
        if first is None and len(recorded) != len(replayed):
            first = min(len(recorded), len(replayed))
        return {"evaluations_recorded": len(recorded), "evaluations_replayed": len(replayed),
                "decisions_match": first is None, "first_divergence": first,
                "commands_recorded": len(commands), "commands_replayed": len(actuator.commands),
                "commands_match": commands == sorted(c[0] for c in actuator.commands)}

