"""Independent audit of an exported physiology run directory.

The auditor trusts nothing it did not recompute. It verifies artifact hashes,
the session contract, raw-content bindings, re-runs the full pipeline from the
raw bundle, replays every closed-loop decision, checks that no decision used
evidence from its future, walks each intervention's execution chain, and
rebuilds the closed-loop ledger.

The result names one explicit replay status. A divergence is surfaced, never
reconciled:

  REPLAY_MATCH                every decision and command re-derived exactly
  REPLAY_DIVERGENCE           replay disagrees with the record (first divergence reported)
  TIMING_VIOLATION            a decision cites evidence taken after its cutoff or
                              not yet available at its decision time
  VERSION_MISMATCH            the recorded analysis code differs from the code auditing it
  EVIDENCE_INTEGRITY_FAILURE  hashes, CRCs, contract, or raw bindings do not hold
  MISSING_SOURCE              an artifact the replay needs is absent or unreadable
  INSUFFICIENT_EVIDENCE       the session lacks what replay needs (no controller
                              configuration or no recorded evaluations)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from models.session_records import SessionRecordError, load_session
from .controller import replay
from .evidence import (EVENT_KIND_FLAG, analysis_document, controller_config_from_records, evaluation_record,
                       raw_session_from_bundle, source_digest)
from .ledger import build_ledger
from .pipeline import analyze
from .streams import RawSession

REPLAY_STATUSES = ("REPLAY_MATCH", "REPLAY_DIVERGENCE", "TIMING_VIOLATION", "VERSION_MISMATCH",
                   "EVIDENCE_INTEGRITY_FAILURE", "MISSING_SOURCE", "INSUFFICIENT_EVIDENCE")
NOTE = "Hashes and CRC-32C detect accidental change; they do not authenticate authorship."


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strip_crc(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k != "crc32c"}


def _result(status: str, checks: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"valid": status == "REPLAY_MATCH" and all(c["passed"] for c in checks.values()),
            "replay_status": status, "checks": checks, "authentication_verified": False, "note": NOTE, **extra}


def temporal_violations(records: list[dict[str, Any]], raw: RawSession) -> list[str]:
    """Decisions citing samples taken after their input cutoff or unavailable at decision time.

    Applies to every record that declares decision_time_us, whatever produced it:
    deterministic logic, a statistical model, or an AI model. No layer gets a time machine.
    """
    problems = []
    for record in records:
        decided, cutoff = record.get("decision_time_us"), record.get("input_cutoff_us")
        if decided is None:
            continue
        label = f"{record['record_type']}:{record.get('decision_id') or record['device_time_start_us']}"
        if cutoff is not None and cutoff > decided:
            problems.append(f"{label}: input cutoff {cutoff} after decision time {decided}")
        for r in record.get("source_sequence_ranges", []):
            stream = raw.streams.get(r["stream_id"])
            if stream is None:
                continue
            a = int(np.searchsorted(stream.sequence, r["first_sequence"]))
            b = int(np.searchsorted(stream.sequence, r["last_sequence"], side="right"))
            if b <= a:
                continue
            assert stream.available_us is not None
            newest_taken = int(stream.device_time_us[a:b].max())
            newest_available = int(stream.available_us[a:b].max())
            if cutoff is not None and newest_taken > cutoff:
                problems.append(f"{label}: {r['stream_id']} sample taken at {newest_taken} after cutoff {cutoff}")
            if newest_available > decided:
                problems.append(f"{label}: {r['stream_id']} sample available at {newest_available} after decision {decided}")
    return problems


def execution_chain_problems(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Recompute every intervention's execution stages from the events they cite."""
    events = {f"{r['stream_id']}#{r['sequence']}": r for r in records if r["record_type"] == "EVENT" and "sequence" in r}
    decision_records = {r["decision_id"] for r in records if r["record_type"] == "MODEL_RESULT" and "decision_id" in r}

    def kind(event_id: str) -> str | None:
        event = events.get(event_id)
        return next((f[len(EVENT_KIND_FLAG):] for f in event["status_flags"] if f.startswith(EVENT_KIND_FLAG)), None) if event else None

    chains, problems = [], []
    for record in records:
        if record["record_type"] != "INTERVENTION":
            continue
        decision = record["decision_id"]
        missing = [e for e in record["actuation_evidence_ids"] if e not in events]
        chain = record.get("execution_chain", [])
        commanded = sum(1 for e in events.values() if e.get("decision_id") == decision
                        and kind(f"{e['stream_id']}#{e['sequence']}") == "HAPTIC_COMMAND")
        stages = {"PHYSICALLY_OBSERVED": 0, "ELECTRICAL_ONSET_OBSERVED": 0, "COMMAND_ONLY": 0}
        for link in chain:
            stages[link["stage"]] += 1
            t_cmd = events[link["command_id"]]["device_time_start_us"] if link["command_id"] in events else None
            expected = (("command_id", "HAPTIC_COMMAND"), ("electrical_onset_id", "HAPTIC_ELECTRICAL_ONSET"),
                        ("physical_observation_id", "HAPTIC_PHYSICAL_OBSERVATION"))
            for key, want in expected:
                if key in link and kind(link[key]) != want:
                    problems.append(f"{decision} cue {link['cue_index']}: {key} is {kind(link[key])}, not {want}")
                if key != "command_id" and key in link and t_cmd is not None and link[key] in events \
                        and events[link[key]]["device_time_start_us"] < t_cmd:
                    problems.append(f"{decision} cue {link['cue_index']}: {key} precedes its command")
            observation = events.get(link.get("physical_observation_id", ""))
            if observation is not None and not any(r["stream_id"] == "imu" for r in observation.get("source_sequence_ranges", [])):
                problems.append(f"{decision} cue {link['cue_index']}: physical observation cites no IMU samples")
        if not record["decision_id"] in decision_records:
            problems.append(f"{decision}: no recorded decision")
        if missing:
            problems.append(f"{decision}: unresolved evidence {missing}")
        if len(chain) != commanded:
            problems.append(f"{decision}: {commanded} commands but {len(chain)} execution links")
        chains.append({"decision_id": decision, "cues": len(chain), "stages": stages,
                       "decision_recorded": decision in decision_records, "missing": missing})
    return chains, problems


def audit_run(directory: Path) -> dict[str, Any]:
    directory = Path(directory)
    checks: dict[str, dict[str, Any]] = {}

    def check(name: str, ok: bool, detail: Any = None) -> None:
        checks[name] = {"passed": bool(ok), **({"detail": detail} if detail is not None else {})}

    # ---------------------------------------------------------------- sources
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        records = load_session(directory / "session.ndjson")
    except FileNotFoundError as exc:
        check("sources_present", False, str(exc))
        return _result("MISSING_SOURCE", checks)
    except (SessionRecordError, ValueError) as exc:
        check("session_contract", False, str(exc))
        return _result("EVIDENCE_INTEGRITY_FAILURE", checks)
    mismatched = [path for path, entry in manifest["artifacts"].items()
                  if not (directory / path).is_file() or _sha256(directory / path) != entry["sha256"]]
    check("artifact_hashes", not mismatched, {"artifacts": len(manifest["artifacts"]), "mismatched": mismatched})
    check("session_contract", True, {"records": len(records)})
    try:
        raw, content_hashes = raw_session_from_bundle(directory, records)
    except FileNotFoundError as exc:
        check("sources_present", False, str(exc))
        return _result("MISSING_SOURCE", checks)
    except (ValueError, StopIteration) as exc:
        check("raw_content_bound", False, f"{type(exc).__name__}: {exc}")
        return _result("EVIDENCE_INTEGRITY_FAILURE", checks)
    bound = {r["stream_id"]: next(f for f in r["status_flags"] if f.startswith("CONTENT_SHA256:")).split(":", 1)[1]
             for r in records if r["record_type"] == "STREAM_DESCRIPTOR"}
    check("raw_content_bound", bound == content_hashes, {name: h[:16] for name, h in content_hashes.items()})
    integrity_ok = not mismatched and bound == content_hashes

    model_ids = {r["model"]["artifact_id"] for r in records if "model" in r}
    current = source_digest()
    check("pipeline_source_matches", model_ids == {current}, {"recorded": sorted(model_ids), "current": current})

    # ------------------------------------------------------------- re-derive
    analysis = analyze(raw)
    stored_path = directory / "analysis.json"
    stored = json.loads(stored_path.read_text(encoding="utf-8")) if stored_path.is_file() else None
    recomputed = json.loads(json.dumps(analysis_document(analysis), sort_keys=True, allow_nan=False))
    check("analysis_rederived", recomputed == stored,
          {"windows": len(recomputed["windows"]), "beats": len(recomputed["beats"]["t_s"]), "scrs": len(recomputed["eda"]["scrs"])})

    violations = temporal_violations(records, raw)
    check("temporal_lawfulness", not violations,
          {"decisions_checked": sum(1 for r in records if "decision_time_us" in r), "violations": violations[:5]})

    lineage_errors = []
    for record in records:
        for r in record.get("source_sequence_ranges", []):
            stream = raw.streams.get(r["stream_id"])
            if stream is None:
                lineage_errors.append(f"unknown stream {r['stream_id']}")
                continue
            a = int(np.searchsorted(stream.sequence, r["first_sequence"]))
            b = int(np.searchsorted(stream.sequence, r["last_sequence"]))
            ok = (a < len(stream) and b < len(stream) and stream.sequence[a] == r["first_sequence"]
                  and stream.sequence[b] == r["last_sequence"] and stream.sequence[b] - stream.sequence[a] == b - a)
            if not ok:
                lineage_errors.append(f"{record['record_type']}@{record['device_time_start_us']}:{r}")
    check("lineage_on_recorded_samples", not lineage_errors, {"errors": lineage_errors[:5]})

    chains, chain_problems = execution_chain_problems(records)
    check("execution_chains", not chain_problems, {"interventions": chains, "problems": chain_problems[:5]})

    ledger_path = directory / "closed_loop_ledger.json"
    if ledger_path.is_file():
        rebuilt = json.loads(json.dumps(build_ledger(records), sort_keys=True, allow_nan=False))
        check("ledger_rederived", rebuilt == json.loads(ledger_path.read_text(encoding="utf-8")))

    # ---------------------------------------------------------------- replay
    try:
        config, end_us = controller_config_from_records(records)
    except (StopIteration, KeyError, ValueError, TypeError) as exc:
        check("decisions_replayed", False, f"controller configuration unusable: {exc}")
        return _result("INSUFFICIENT_EVIDENCE", checks)
    recorded_evals = sorted((_strip_crc(r) for r in records
                             if r["record_type"] == "MODEL_RESULT" and "CONTROLLER_EVALUATION" in r["status_flags"]),
                            key=lambda r: r["device_time_end_us"])
    replayed = replay(raw, config, end_us)
    rederived = [_strip_crc(evaluation_record(ev, current)) for ev in replayed]
    commands = sorted(r["device_time_start_us"] for r in records if r["record_type"] == "EVENT"
                      and any(f in (EVENT_KIND_FLAG + "HAPTIC_COMMAND", EVENT_KIND_FLAG + "HAPTIC_COMMAND_SHAM") for f in r["status_flags"]))
    replay_cues = sorted(t for ev in replayed for t in ev.cues_device_us)
    divergence = None
    for i in range(max(len(recorded_evals), len(rederived))):
        a = recorded_evals[i] if i < len(recorded_evals) else None
        b = rederived[i] if i < len(rederived) else None
        if a != b:
            divergence = {"index": i, "decision_time_us": (a or b or {}).get("decision_time_us"),
                          "fields": sorted(k for k in set(a or {}) | set(b or {}) if (a or {}).get(k) != (b or {}).get(k))}
            break
    commands_match = commands == replay_cues
    check("decisions_replayed", divergence is None and commands_match,
          {"evaluations": len(rederived), "decisions": [r["decision_id"] for r in rederived if "decision_id" in r],
           "cue_commands": len(replay_cues), "commands_match": commands_match, "first_divergence": divergence})

    if not integrity_ok or not checks["analysis_rederived"]["passed"] or not checks["lineage_on_recorded_samples"]["passed"] \
            or not checks["execution_chains"]["passed"] or not checks.get("ledger_rederived", {"passed": True})["passed"]:
        status = "EVIDENCE_INTEGRITY_FAILURE"
    elif not checks["pipeline_source_matches"]["passed"]:
        status = "VERSION_MISMATCH"
    elif violations:
        status = "TIMING_VIOLATION"
    elif divergence is not None or not commands_match:
        status = "REPLAY_DIVERGENCE"
    elif not recorded_evals:
        status = "INSUFFICIENT_EVIDENCE"
    else:
        status = "REPLAY_MATCH"
    return _result(status, checks)
