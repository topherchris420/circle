"""Session records for an acquisition the closed loop refused.

When a source cannot satisfy the pipeline's input contract
(models/physiology/loop.py), nothing is measured, inferred, decided, or
actuated. That is still a result worth keeping: which source was offered, what
it could and could not supply, what its link did, and why the loop refused.
refusal_session() states it in the ordinary session-record contract, so it
loads, validates, and gets a passport like any other session:

  SESSION_HEADER    source identity, hardware, SDK version, timebase
  CONFIG_CHANGE     the controller configuration the experiment would have used
  EVENT             each link observation (LINK_STATE...), never physiological
  FAULT             one per unmet input-contract requirement, with its cause
  SESSION_TRAILER   TERMINATED:INSUFFICIENT_EVIDENCE and counts

Such a source has no device clock, so times are microseconds on the host's
monotonic clock from the start of the attempt (TIMEBASE:HOST_MONOTONIC).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from models.physiology.controller import CONTROLLER_VERSION, ControllerConfig
from models.physiology.evidence import EVENT_KIND_FLAG, SCHEMA_VERSION, dumps, software_revision
from models.physiology.ledger import passport, passport_text
from models.physiology.loop import Capabilities
from models.physiology.streams import DeviceEvent
from models.session_records import seal_record

PROVENANCES = ("RAW_MEASURED", "SIMULATED")


def _record(record_type: str, provenance: str, t0: int, t1: int, flags: list[str], **fields: Any) -> dict[str, Any]:
    record = {"schema_version": SCHEMA_VERSION, "record_type": record_type, "provenance": provenance,
              "device_time_start_us": int(t0), "device_time_end_us": int(max(t0, t1)),
              "status_flags": list(dict.fromkeys(flags)), "crc32c": "00000000"}
    record.update({k: v for k, v in fields.items() if v is not None})
    return seal_record(record)


def refusal_session(capabilities: Capabilities, problems: list[str], link_events: list[DeviceEvent],
                    controller: ControllerConfig, session_id: str, provenance: str,
                    extra_flags: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Sealed records of an attempt the input contract refused before any acquisition."""
    if provenance not in PROVENANCES:
        raise ValueError(f"provenance must be one of {PROVENANCES}")
    if not problems:
        raise ValueError("a refusal needs the reasons it was refused")
    mode = "SIMULATED_DATA" if provenance == "SIMULATED" else "LIVE_ACQUISITION"
    end_us = max([e.device_time_us for e in link_events] + [0])
    header_flags = [mode, f"SESSION_ID:{session_id}", f"SOURCE:{capabilities.source}",
                    f"SOURCE_HARDWARE:{capabilities.hardware}", f"SOURCE_SDK_VERSION:{capabilities.sdk_version or 'NONE'}",
                    f"SOURCE_CONNECTION:{capabilities.connection_state}", "TIMEBASE:HOST_MONOTONIC",
                    *(["NO_PHYSIOLOGICAL_STREAMS"] if not capabilities.signals else []),
                    "NOT_HUMAN_DATA", "NO_HARDWARE_DRIVEN", *extra_flags]
    records = [
        _record("SESSION_HEADER", provenance, 0, 0, header_flags, stream_id="session",
                payload={"signals_offered": len(capabilities.signals), "actuators_offered": len(capabilities.actuators)}),
        _record("CONFIG_CHANGE", provenance, 0, 0,
                ["CONTROLLER_CONFIG", f"CONTROLLER_VERSION:{CONTROLLER_VERSION}", f"BASELINE_PHASE:{controller.baseline_phase}",
                 f"ARM_PHASE:{controller.arm_phase}", "EVALUATION_END_US:0", "NEVER_EVALUATED"],
                stream_id="controller", payload=controller.numeric_payload()),
    ]
    for event in sorted(link_events, key=lambda e: (e.device_time_us, e.stream_id, e.sequence)):
        payload = {k: float(v) for k, v in event.attributes}
        records.append(_record("EVENT", provenance, event.device_time_us, event.device_time_us,
                               [EVENT_KIND_FLAG + event.kind, "LINK_STATE", "NOT_PHYSIOLOGICAL", "TIMEBASE:HOST_MONOTONIC"],
                               stream_id=event.stream_id, sequence=event.sequence, payload=payload or None))
    for i, problem in enumerate(problems):
        records.append(_record("FAULT", "DERIVED", end_us, end_us, ["INPUT_CONTRACT_UNMET", "REFUSED_BEFORE_ACQUISITION"],
                               stream_id="input_contract", sequence=i, cause=problem))
    records.append(_record("SESSION_TRAILER", provenance, end_us, end_us,
                           [mode, "TERMINATED:INSUFFICIENT_EVIDENCE", "NO_EVALUATIONS", "NO_INTERVENTIONS"],
                           stream_id="session", payload={"evaluations": 0, "interventions": 0, "faults": len(problems),
                                                         "link_events": len(link_events)}))
    return records


def write_refusal(directory: Path, records: list[dict[str, Any]], capabilities: Capabilities,
                  details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write session.ndjson, passport.txt, and a manifest binding them by SHA-256."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    trailer = records[-1]
    reason = next(f.split(":", 1)[1] for f in trailer["status_flags"] if f.startswith("TERMINATED:"))
    documents = {
        "session.ndjson": "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in records).encode("utf-8"),
        "passport.txt": passport_text(passport(records, {"SOURCE": capabilities.source, "TERMINATED": reason})).encode("utf-8"),
    }
    for name, data in documents.items():
        (directory / name).write_bytes(data)
    manifest = {
        "schema": "circle-acquisition-attempt/1",
        "release_class": "ENGINEERING_REVIEW_ONLY",
        "terminated": reason,
        "capabilities": capabilities.to_dict(),
        "refusal": [r["cause"] for r in records if r["record_type"] == "FAULT"],
        "software_revision": software_revision(),
        **(details or {}),
        "artifacts": {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                      for name, data in sorted(documents.items())},
    }
    (directory / "manifest.json").write_bytes(dumps(manifest))
    return manifest
