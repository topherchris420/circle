"""Independent audit of an exported physiology run directory.

The auditor trusts nothing it did not recompute. It verifies artifact hashes,
the session contract, raw-content bindings, re-runs the full pipeline from the
raw bundle, replays every closed-loop decision, and walks each intervention's
evidence chain back to device-recorded events and exact sample ranges.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from models.session_records import load_session
from .controller import replay
from .evidence import (EVENT_KIND_FLAG, analysis_document, controller_config_from_records, evaluation_record,
                       raw_session_from_bundle, source_digest)
from .pipeline import analyze


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strip_crc(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k != "crc32c"}


def audit_run(directory: Path) -> dict[str, Any]:
    directory = Path(directory)
    checks: dict[str, dict[str, Any]] = {}

    def check(name: str, ok: bool, detail: Any = None) -> None:
        checks[name] = {"passed": bool(ok), **({"detail": detail} if detail is not None else {})}

    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    mismatched = [path for path, entry in manifest["artifacts"].items()
                  if not (directory / path).is_file() or _sha256(directory / path) != entry["sha256"]]
    check("artifact_hashes", not mismatched, {"artifacts": len(manifest["artifacts"]), "mismatched": mismatched})

    records = load_session(directory / "session.ndjson")
    check("session_contract", True, {"records": len(records)})

    raw, content_hashes = raw_session_from_bundle(directory, records)
    bound = {}
    for record in records:
        if record["record_type"] == "STREAM_DESCRIPTOR":
            flag = next(f for f in record["status_flags"] if f.startswith("CONTENT_SHA256:"))
            bound[record["stream_id"]] = flag.split(":", 1)[1]
    check("raw_content_bound", bound == content_hashes, {name: h[:16] for name, h in content_hashes.items()})

    model_ids = {r["model"]["artifact_id"] for r in records if "model" in r}
    current = source_digest()
    check("pipeline_source_matches", model_ids == {current},
          {"recorded": sorted(model_ids), "current": current})

    analysis = analyze(raw)
    recomputed = analysis_document(analysis)
    stored = json.loads((directory / "analysis.json").read_text(encoding="utf-8"))
    recomputed_json = json.loads(json.dumps(recomputed, sort_keys=True, allow_nan=False))
    check("analysis_rederived", recomputed_json == stored,
          {"windows": len(stored.get("windows", [])), "beats": len(stored["beats"]["t_s"]), "scrs": len(stored["eda"]["scrs"])})

    config, end_us = controller_config_from_records(records)
    replayed = replay(raw, config, end_us)
    model_id = current
    recorded_evals = [_strip_crc(r) for r in records
                      if r["record_type"] == "MODEL_RESULT" and "CONTROLLER_EVALUATION" in r["status_flags"]]
    rederived_evals = [_strip_crc(evaluation_record(ev, model_id)) for ev in replayed]
    recorded_evals.sort(key=lambda r: r["device_time_end_us"])
    commands = sorted(r["device_time_start_us"] for r in records if r["record_type"] == "EVENT"
                      and any(f in (EVENT_KIND_FLAG + "HAPTIC_COMMAND", EVENT_KIND_FLAG + "HAPTIC_COMMAND_SHAM") for f in r["status_flags"]))
    replay_cues = sorted(t for ev in replayed for t in ev.cues_device_us)
    decisions = [r["decision_id"] for r in rederived_evals if "decision_id" in r]
    check("decisions_replayed", recorded_evals == rederived_evals and commands == replay_cues,
          {"evaluations": len(rederived_evals), "decisions": decisions, "cue_commands": len(replay_cues)})

    # Lineage: every source range lies on recorded samples and never spans a gap.
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
                  and stream.sequence[b] == r["last_sequence"]
                  and stream.sequence[b] - stream.sequence[a] == b - a)
            if not ok:
                lineage_errors.append(f"{record['record_type']}@{record['device_time_start_us']}:{r}")
    check("lineage_on_recorded_samples", not lineage_errors, {"errors": lineage_errors[:5]})

    # Intervention evidence chains.
    evidence_ids = {f"{r['stream_id']}#{r['sequence']}" for r in records if r["record_type"] == "EVENT" and "sequence" in r}
    decision_records = {r["decision_id"] for r in records if r["record_type"] == "MODEL_RESULT" and "decision_id" in r}
    chains = []
    for record in records:
        if record["record_type"] != "INTERVENTION":
            continue
        missing = [e for e in record["actuation_evidence_ids"] if e not in evidence_ids]
        chains.append({"decision_id": record["decision_id"], "evidence": len(record["actuation_evidence_ids"]),
                       "decision_recorded": record["decision_id"] in decision_records, "missing": missing})
    check("intervention_chains", all(c["decision_recorded"] and not c["missing"] for c in chains), chains)

    return {"valid": all(c["passed"] for c in checks.values()), "checks": checks,
            "authentication_verified": False,
            "note": "Hashes and CRC-32C detect accidental change; they do not authenticate authorship."}
