"""Evidence export: contract-valid session records plus a hashed raw-sample bundle.

A run directory is self-auditing:

  session.ndjson   contracts/session-record.schema.json records: header,
                   stream descriptors, controller configuration, clock
                   mapping, protocol and haptic events, GAPs, windowed
                   MODEL_RESULTs with exact source sequence ranges, every
                   controller evaluation, INTERVENTIONs, trailer.
  raw/*.csv.gz     integer sensor codes, sequence numbers, and device
                   timestamps (deterministic gzip, mtime 0). The JSON session
                   profile carries one snapshot per record, so multi-sample
                   raw data lives here and is bound by SHA-256.
  analysis.json    every pipeline output, re-derivable from raw/ alone.

Nothing in session.ndjson or raw/ is ground truth; truth.json is separate.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from models.session_records import seal_record
from .controller import CONTROLLER_VERSION, ControllerConfig, Evaluation
from .pipeline import PIPELINE_VERSION, Analysis
from .streams import STREAM_COLUMNS, DeviceEvent, Gap, RawSession, Stream

SCHEMA_VERSION = "2.2.0"
PACKAGE_DIR = Path(__file__).resolve().parent
PIPELINE_SOURCES = ("dsp.py", "pipeline.py", "controller.py", "streams.py")
EVENT_KIND_FLAG = "EVENT_KIND:"


def source_digest(names: tuple[str, ...] = PIPELINE_SOURCES) -> str:
    """SHA-256 over the exact analysis source code (the 'model artifact')."""
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update((PACKAGE_DIR / name).read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _finite(payload: dict[str, Any]) -> dict[str, float]:
    out = {}
    for key, value in payload.items():
        if isinstance(value, bool):
            value = 1 if value else 0
        if isinstance(value, (int, float)) and math.isfinite(value):
            out[key] = value
    return out


# ------------------------------------------------------------------ raw bundle
def _csv_bytes(stream: Stream) -> bytes:
    header = ["sequence", "device_time_us", *STREAM_COLUMNS[stream.name]]
    matrix = np.column_stack([stream.sequence, stream.device_time_us,
                              *[stream.columns[c] for c in STREAM_COLUMNS[stream.name]]]).astype(np.int64)
    buffer = io.StringIO()
    buffer.write(",".join(header) + "\n")
    np.savetxt(buffer, matrix, fmt="%d", delimiter=",")
    return buffer.getvalue().encode("ascii")


def write_raw_bundle(raw: RawSession, directory: Path) -> dict[str, dict[str, Any]]:
    directory.mkdir(parents=True, exist_ok=True)
    entries = {}
    for name in STREAM_COLUMNS:
        content = _csv_bytes(raw.streams[name])
        packed = gzip.compress(content, compresslevel=9, mtime=0)
        path = directory / f"{name}.csv.gz"
        path.write_bytes(packed)
        entries[f"raw/{name}.csv.gz"] = {"sha256": hashlib.sha256(packed).hexdigest(),
                                         "content_sha256": hashlib.sha256(content).hexdigest(),
                                         "rows": len(raw.streams[name]), "bytes": len(packed)}
    return entries


def read_stream(path: Path, name: str) -> tuple[Stream, str]:
    content = gzip.decompress(path.read_bytes())
    lines = content.decode("ascii").splitlines()
    header = lines[0].split(",")
    expected = ["sequence", "device_time_us", *STREAM_COLUMNS[name]]
    if header != expected:
        raise ValueError(f"{path.name}: unexpected columns {header}")
    if len(lines) > 1:
        matrix = np.array(",".join(lines[1:]).split(","), dtype=np.int64).reshape(len(lines) - 1, len(header))
    else:
        matrix = np.zeros((0, len(header)), dtype=np.int64)
    stream = Stream(name, matrix[:, 0], matrix[:, 1], {c: matrix[:, i + 2] for i, c in enumerate(STREAM_COLUMNS[name])})
    return stream, hashlib.sha256(content).hexdigest()


# -------------------------------------------------------------- session records
def _record(record_type: str, provenance: str, t0: int, t1: int, flags: list[str], **fields: Any) -> dict[str, Any]:
    record = {"schema_version": SCHEMA_VERSION, "record_type": record_type, "provenance": provenance,
              "device_time_start_us": int(t0), "device_time_end_us": int(max(t0, t1)),
              "status_flags": list(dict.fromkeys(flags)), "crc32c": "00000000"}
    record.update({k: v for k, v in fields.items() if v is not None})
    return record


def _event_record(event: DeviceEvent, provenance: str, flags: list[str], decision_id: str | None = None) -> dict[str, Any]:
    payload = _finite(dict(event.attributes))
    return _record("EVENT", provenance, event.device_time_us, event.device_time_us,
                   [EVENT_KIND_FLAG + event.kind, *flags], stream_id=event.stream_id, sequence=event.sequence,
                   payload=payload or None, decision_id=decision_id)


def build_session_records(run: Any, raw_entries: dict[str, dict[str, Any]], analysis: Analysis) -> list[dict[str, Any]]:
    """Every record of the evidence session, sealed with CRC-32C."""
    raw: RawSession = run.raw
    config = run.config
    arm = "ARM_ACTIVE" if config.actuate else "ARM_SHAM"
    sim = ["SIMULATED_DATA", "PHYSIOLOGY_TWIN", "NOT_HUMAN_DATA"]
    markers = raw.events_of("PHASE_START:")
    start_us = min(e.device_time_us for e in markers)
    end_us = max(int(s.device_time_us[-1]) for s in raw.streams.values() if len(s))
    model_id = source_digest()
    ordered: list[tuple[int, int, dict[str, Any]]] = []

    def add(priority: int, record: dict[str, Any]) -> None:
        ordered.append((record["device_time_start_us"], priority, record))

    add(0, _record("SESSION_HEADER", "SIMULATED", start_us, start_us, [*sim, arm, f"PIPELINE_VERSION:{PIPELINE_VERSION}"],
                   stream_id="session", payload={"seed": config.twin.seed, "duration_s": config.twin.duration_s}))
    for name, stream in raw.streams.items():
        entry = raw_entries[f"raw/{name}.csv.gz"]
        add(1, _record("STREAM_DESCRIPTOR", "SIMULATED", int(stream.device_time_us[0]), int(stream.device_time_us[-1]),
                       [*sim, f"RAW_ARTIFACT:raw/{name}.csv.gz", f"CONTENT_SHA256:{entry['content_sha256']}", f"ROWS:{entry['rows']}"],
                       stream_id=name, payload=_finite(raw.descriptors[name])))
    add(2, _record("CONFIG_CHANGE", "SIMULATED", start_us, start_us,
                   ["CONTROLLER_CONFIG", f"CONTROLLER_VERSION:{CONTROLLER_VERSION}",
                    f"BASELINE_PHASE:{config.controller.baseline_phase}", f"ARM_PHASE:{config.controller.arm_phase}",
                    f"EVALUATION_END_US:{run.evaluation_end_us}", arm],
                   stream_id="controller", payload=config.controller.numeric_payload()))
    sync = raw.streams["sync"]
    add(3, _record("CLOCK_MAPPING", "DERIVED", int(sync.device_time_us[0]), int(sync.device_time_us[-1]),
                   ["DEVICE_TO_LAB_LINEAR_FIT", "LAB_REFERENCE_1PPS"], stream_id="sync",
                   payload=_finite(analysis.clock.to_dict()), source_stream_ids=["sync"],
                   source_sequence_ranges=[{"stream_id": "sync", "first_sequence": int(sync.sequence[0]),
                                            "last_sequence": int(sync.sequence[-1])}]))
    for event in raw.events_of("PHASE_START:") + raw.events_of("STIMULUS"):
        add(4, _event_record(event, "SIMULATED", sim))
    for gap in raw.gaps:
        add(5, _record("GAP", "SIMULATED", gap.device_time_us, gap.device_time_us, [*sim, "SAMPLE_LOSS_DECLARED"],
                       stream_id=gap.stream_id, dropped_first_sequence=gap.first_sequence,
                       dropped_last_sequence=gap.last_sequence, cause=gap.cause))
    for window in analysis.windows:
        ranges = window["source_sequence_ranges"]
        add(6, _record("MODEL_RESULT", "MODEL_INFERRED", window["device_time_start_us"], window["device_time_end_us"],
                       ["PHYSIOLOGY_WINDOW", "SIMULATED_INPUT"], stream_id="physiology_windows",
                       payload=_finite(window["payload"]),
                       source_stream_ids=sorted({r["stream_id"] for r in ranges}), source_sequence_ranges=ranges,
                       model={"name": "CIRCLE_PHYSIOLOGY_PIPELINE", "version": PIPELINE_VERSION, "artifact_id": model_id}))
    t0, t1 = run.controller_baseline_window_us
    ranges = run.controller_baseline_ranges
    add(7, _record("MODEL_RESULT", "MODEL_INFERRED", t0, t1, ["CONTROLLER_BASELINE", "SIMULATED_INPUT"],
                   stream_id="controller", payload=_finite(run.controller_baseline),
                   source_stream_ids=sorted({r["stream_id"] for r in ranges}), source_sequence_ranges=ranges,
                   model={"name": "CIRCLE_CLOSED_LOOP_CONTROLLER", "version": CONTROLLER_VERSION, "artifact_id": model_id}))
    for ev in run.evaluations:
        add(8, evaluation_record(ev, model_id))
    observations = {}
    for obs in analysis.haptic:
        if "physical_onset_s" not in obs:
            continue
        t = int(round(obs["physical_onset_s"] * 1e6))
        record = _record("EVENT", "DERIVED", t, t, [EVENT_KIND_FLAG + "HAPTIC_PHYSICAL_OBSERVATION", "IMU_VIBRATION_ENVELOPE", *sim],
                         stream_id="haptic_observations", sequence=len(observations),
                         payload=_finite({"program": obs["program"], "cue_index": obs["cue_index"],
                                          "latency_from_command_us": (obs["physical_onset_s"] - obs["command_s"]) * 1e6,
                                          "steady_amplitude_g": obs["steady_amplitude_g"]}),
                         decision_id=f"PBR-{int(obs['program'])}",
                         source_stream_ids=["imu"],
                         source_sequence_ranges=[{"stream_id": "imu", "first_sequence": obs["imu_sequence_first"],
                                                  "last_sequence": obs["imu_sequence_last"]}])
        observations[(obs["program"], obs["cue_index"])] = f"haptic_observations#{len(observations)}"
        add(10, record)
    programs: dict[float, list[DeviceEvent]] = {}
    for event in raw.events_of("HAPTIC_"):
        program = event.attribute("program")
        add(9, _event_record(event, "SIMULATED", [*sim, "SIMULATED_ACTUATION" if config.actuate else "SHAM_NOT_ACTUATED"],
                             decision_id=f"PBR-{int(program)}"))
        programs.setdefault(program, []).append(event)
    if config.actuate:
        for program, events in sorted(programs.items()):
            evidence = [e.evidence_id for e in events if e.kind in ("HAPTIC_COMMAND", "HAPTIC_ELECTRICAL_ONSET")]
            evidence += [observations[(program, e.attribute("cue_index"))] for e in events
                         if e.kind == "HAPTIC_COMMAND" and (program, e.attribute("cue_index")) in observations]
            commands = [e for e in events if e.kind == "HAPTIC_COMMAND"]
            add(11, _record("INTERVENTION", "INTERVENTION", min(e.device_time_us for e in events), max(e.device_time_us for e in events),
                            ["PACED_BREATHING_HAPTIC_CUES", "SIMULATED_ACTUATION", "NO_HARDWARE_DRIVEN"],
                            stream_id="interventions", decision_id=f"PBR-{int(program)}", actuation_evidence_ids=evidence,
                            payload={"program": program, "cues": len(commands),
                                     "cue_period_s": config.controller.cue_period_s}))
    counts = {f"samples_{name}": len(s) for name, s in raw.streams.items()}
    counts.update({"gaps": len(raw.gaps), "evaluations": len(run.evaluations), "haptic_events": len(raw.events_of("HAPTIC_"))})
    add(99, _record("SESSION_TRAILER", "SIMULATED", end_us, end_us, [*sim, arm], stream_id="session", payload=counts))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [seal_record(record) for _, _, record in ordered]


def evaluation_record(ev: Evaluation, model_id: str) -> dict[str, Any]:
    flags = ["CONTROLLER_EVALUATION", f"STATE:{ev.state}", "SIMULATED_INPUT"]
    if ev.action:
        flags.append(f"ACTION:{ev.action}")
    payload = _finite(ev.features)
    payload["cues_scheduled"] = len(ev.cues_device_us)
    if ev.program is not None:
        payload["program"] = ev.program
    ranges = ev.source_sequence_ranges
    return _record("MODEL_RESULT", "MODEL_INFERRED", ev.window_start_us, ev.device_time_us, flags,
                   stream_id="controller", payload=payload, decision_id=ev.decision_id,
                   source_stream_ids=sorted({r["stream_id"] for r in ranges}), source_sequence_ranges=ranges,
                   model={"name": "CIRCLE_CLOSED_LOOP_CONTROLLER", "version": CONTROLLER_VERSION, "artifact_id": model_id})


# ------------------------------------------------------------------ read back
def raw_session_from_bundle(directory: Path, records: list[dict[str, Any]]) -> tuple[RawSession, dict[str, str]]:
    """Rebuild exactly what the pipeline saw from raw/ plus device-recorded events."""
    streams, hashes = {}, {}
    for name in STREAM_COLUMNS:
        stream, content_hash = read_stream(directory / "raw" / f"{name}.csv.gz", name)
        streams[name] = stream
        hashes[name] = content_hash
    descriptors, gaps, events = {}, [], []
    for record in records:
        kind = record["record_type"]
        if kind == "STREAM_DESCRIPTOR":
            descriptors[record["stream_id"]] = dict(record["payload"])
        elif kind == "GAP":
            gaps.append(Gap(record["stream_id"], record["dropped_first_sequence"], record["dropped_last_sequence"],
                            record["device_time_start_us"], record["cause"]))
        elif kind == "EVENT" and record["provenance"] == "SIMULATED":
            event_kind = next(f[len(EVENT_KIND_FLAG):] for f in record["status_flags"] if f.startswith(EVENT_KIND_FLAG))
            events.append(DeviceEvent(record["stream_id"], record["sequence"], event_kind, record["device_time_start_us"],
                                      tuple(sorted(record.get("payload", {}).items()))))
    events.sort(key=lambda e: (e.device_time_us, e.stream_id, e.sequence))
    return RawSession(streams, descriptors, gaps, events), hashes


def controller_config_from_records(records: list[dict[str, Any]]) -> tuple[ControllerConfig, int]:
    record = next(r for r in records if r["record_type"] == "CONFIG_CHANGE" and "CONTROLLER_CONFIG" in r["status_flags"])
    values: dict[str, Any] = {}
    fields = ControllerConfig.__dataclass_fields__
    for key, value in record["payload"].items():
        field_type = str(fields[key].type)
        values[key] = int(value) if field_type == "int" else float(value)
    flags = {f.split(":", 1)[0]: f.split(":", 1)[1] for f in record["status_flags"] if ":" in f}
    values["baseline_phase"] = flags["BASELINE_PHASE"]
    values["arm_phase"] = flags["ARM_PHASE"]
    return ControllerConfig(**values), int(flags["EVALUATION_END_US"])


# --------------------------------------------------------------- analysis json
def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def analysis_document(analysis: Analysis) -> dict[str, Any]:
    """Every pipeline output (full resolution for events, key series)."""
    beats = analysis.beats
    return _jsonable({
        "pipeline_version": PIPELINE_VERSION,
        "clock": analysis.clock.to_dict(),
        "motion": {"episodes": analysis.motion["episodes"]},
        "eda": {"scrs": analysis.eda["scrs"]},
        "beats": {"t_s": beats["t_s"], "quality": list(beats["quality"]), "pulse_amplitude_pct": beats["pulse_amplitude_pct"],
                  "ibi_valid": beats["ibi_valid"]},
        "respiration": {"breaths_s": analysis.respiration["breaths_s"], "apnea": analysis.respiration["apnea"]},
        "spo2": {"t_s": analysis.spo2["t_s"], "naive_pct": analysis.spo2["naive_pct"], "gated_pct": analysis.spo2["gated_pct"]},
        "haptic": analysis.haptic,
        "windows": analysis.windows,
    })


def dumps(document: Any) -> bytes:
    return (json.dumps(document, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
