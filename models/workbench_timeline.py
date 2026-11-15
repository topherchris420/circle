"""Timeline view over a completed session's exported evidence bundle.

The Resonance Workbench dashboard renders this document. It is a *view*, not a
new source of truth: every series comes from the run's audited export
(``analysis.json``, ``closed_loop_ledger.json``, ``manifest.json``) and the
independent audit result, and the adaptive feedback events are recomputed
deterministically from the controller evaluations the ledger already preserved.

Consequences kept explicit:

- Nothing here can disagree with the exported evidence without being visible:
  each block names the artifact and hash it was read from.
- The HRV series is a presentation-layer derivation (successive intervals of
  exported, good-quality beats) and is labeled as such; it is not the scored
  pipeline metric.
- Feedback events are recomputed from evidence on every request, so a replay
  of the same bundle yields byte-identical events and a comparable digest.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from models.physiology.feedback import FEEDBACK_VERSION, FeedbackConfig, feedback_events, events_digest
from models.workbench import feedback_config

SCHEMA = "circle-resonance-timeline/1"
HRV_WINDOW_S = 60.0
HRV_STEP_S = 30.0
HRV_MIN_IBIS = 6
HRV_MAX_IBI_S = 2.5

# Keys of the ledger evaluation records the workbench forwards to the browser.
EVALUATION_KEYS = ("id", "decision_time_us", "input_cutoff_us", "window_start_us", "state_after", "action",
                   "decision_id", "gate", "arousal_index", "formula", "features", "record_crc32c")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_sha(directory: Path, name: str) -> str:
    return "sha256:" + hashlib.sha256((directory / name).read_bytes()).hexdigest()


class _LedgerEvaluation:
    """Adapter: ledger evaluation documents through the feedback mapping."""

    def __init__(self, record: dict[str, Any]) -> None:
        self.decision_time_us = int(record["decision_time_us"])
        self.input_cutoff_us = int(record["input_cutoff_us"])
        self.gate_reasons = tuple(r for r in record["gate"] if r != "PASS")
        self.features = dict(record["features"])
        self.state = str(record.get("state_after") or "")
        self.decision_id = record.get("decision_id")


def _hrv_series(beats: dict[str, Any]) -> list[dict[str, Any]]:
    """RMSSD over rolling windows of exported good-quality beat intervals.

    Deterministic presentation-layer derivation from ``analysis.json`` beats:
    successive differences of GOOD-quality consecutive beat times, kept when
    physiologically plausible (0.33–2.5 s) and within 25% of a local
    median. Windows with too few intervals are withheld rather than
    extrapolated.
    """
    t = [float(x) for x in beats["t_s"]]
    quality = list(beats["quality"])
    intervals: list[tuple[float, float]] = []  # (end_time_s, ibi_s)
    for i in range(1, len(t)):
        if quality[i] != "GOOD" or quality[i - 1] != "GOOD":
            continue
        ibi = t[i] - t[i - 1]
        if not 0.33 <= ibi <= HRV_MAX_IBI_S:
            continue
        intervals.append((t[i], ibi))
    if not intervals:
        return []
    values = [ibi for _, ibi in intervals]
    keep = [True] * len(values)
    for k in range(len(values)):
        lo, hi = max(0, k - 4), min(len(values), k + 5)
        med = sorted(values[lo:hi])[ (hi - lo) // 2 ]
        if med > 0 and abs(values[k] - med) > 0.25 * med:
            keep[k] = False
    intervals = [pair for pair, ok in zip(intervals, keep) if ok]
    if not intervals:
        return []
    out = []
    start = intervals[0][0] - HRV_WINDOW_S
    end = intervals[-1][0]
    w0 = start
    while w0 + HRV_WINDOW_S <= end + 1e-9:
        w1 = w0 + HRV_WINDOW_S
        inside = [ibi for t_end, ibi in intervals if w0 < t_end <= w1]
        entry = {"window_start_s": round(w0, 3), "window_end_s": round(w1, 3)}
        if len(inside) >= HRV_MIN_IBIS:
            successive = [inside[i + 1] - inside[i] for i in range(len(inside) - 1)]
            if successive:
                entry["rmssd_ms"] = round(math.sqrt(sum(d * d for d in successive) / len(successive)) * 1000.0, 2)
                entry["ibis"] = len(inside)
                entry["label"] = f"RMSSD, {int(HRV_WINDOW_S)} s window, {len(inside)} good-quality intervals"
            else:
                entry["label"] = "withheld: single interval in window"
        else:
            entry["label"] = f"withheld: fewer than {HRV_MIN_IBIS} good-quality intervals"
        out.append(entry)
        w0 += HRV_STEP_S
    return out


def _cues(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """Haptic cue evidence from the ledger's decision execution chains."""
    cues = []
    for decision in ledger["decisions"]:
        for link in decision.get("execution_chain") or []:
            cue = {"decision_id": decision["decision_id"], "cue_index": link["cue_index"], "stage": link["stage"],
                   "command_time_us": link["command"]["device_time_us"]}
            onset = link.get("electrical_onset")
            if onset:
                cue["electrical_onset_us"] = onset["device_time_us"]
                if cue["command_time_us"] is not None and onset["device_time_us"] is not None:
                    cue["onset_latency_us"] = onset["device_time_us"] - cue["command_time_us"]
            observation = link.get("physical_observation")
            if observation:
                cue["physical_observation_us"] = observation["device_time_us"]
            cues.append(cue)
    return sorted(cues, key=lambda c: c["command_time_us"] or 0)


def _settings_config(settings: dict) -> FeedbackConfig:
    """The FeedbackConfig bounded by a run's recorded settings."""
    return feedback_config(settings)


def build_timeline(run: dict, evidence: Path, audit: Path | None,
                   feedback_config_override: FeedbackConfig | None = None) -> dict[str, Any]:
    """Assemble the browser timeline document for a completed run."""
    # The run's own recorded settings bound the presentation; an explicit
    # override (tests) may only tighten to another valid config.
    feedback_config = feedback_config_override or _settings_config(run["settings"])
    analysis = _read(evidence / "analysis.json")
    ledger = _read(evidence / "closed_loop_ledger.json")
    manifest = _read(evidence / "manifest.json")

    evaluations = [{k: ev[k] for k in EVALUATION_KEYS if k in ev} for ev in ledger["evaluations"]]
    events = feedback_events([_LedgerEvaluation(ev) for ev in ledger["evaluations"]],
                             analysis.get("windows", []), feedback_config)

    beats = analysis["beats"]
    windows = [{"t_s": round((w["device_time_start_us"] + w["device_time_end_us"]) / 2e6, 3),
               **{k: v for k, v in w["payload"].items()}} for w in analysis.get("windows", [])]
    session = {
        "run_id": run["id"], "session_id": manifest["session_id"], "scenario": manifest["scenario"],
        "arm": "active" if run["settings"]["arm"] == "active" else "sham",
        "seed": run["settings"]["seed"], "created_at": run["created_at"],
        "compare": run["settings"]["compare"],
        "feedback_consent": {"audio": bool(run["settings"].get("consent", {}).get("audio", False))},
    }
    if audit is not None and audit.is_file():
        result = _read(audit)
        session["audit"] = {"valid": bool(result.get("valid")), "replay_status": result.get("replay_status")}
    else:
        session["audit"] = None
    return {
        "schema": SCHEMA,
        "session": session,
        "provenance": {
            "note": "Series are read from the run's exported evidence; feedback events are recomputed "
                    "deterministically from the ledger's controller evaluations.",
            "pipeline_version": manifest["pipeline_version"],
            "controller_version": manifest["controller_version"],
            "feedback_version": FEEDBACK_VERSION,
            "analysis_sha256": _artifact_sha(evidence, "analysis.json"),
            "ledger_sha256": _artifact_sha(evidence, "closed_loop_ledger.json"),
            "session_ndjson_sha256": _artifact_sha(evidence, "session.ndjson"),
            "scorecard": manifest["scorecard"],
            "decision_replay": manifest["decision_replay"],
        },
        "windows": windows,
        "hrv": {"derivation": "successive intervals of exported good-quality beats; presentation only",
                "window_s": HRV_WINDOW_S, "step_s": HRV_STEP_S, "series": _hrv_series(beats)},
        "beats": {"t_s": [round(float(x), 4) for x in beats["t_s"]], "quality": list(beats["quality"])},
        "motion_episodes": [[round(float(a), 3), round(float(b), 3)] for a, b in analysis["motion"]["episodes"]],
        "evaluations": evaluations,
        "decisions": ledger["decisions"],
        "cues": _cues(ledger),
        "holds_by_reason": ledger["holds_by_reason"],
        "gate_failures_by_reason": ledger["gate_failures_by_reason"],
        "feedback": {
            "version": FEEDBACK_VERSION,
            "config": {"max_gain": feedback_config.max_gain,
                      "breath_period_bounds_s": [feedback_config.breath_period_min_s,
                                                 feedback_config.breath_period_max_s],
                      "guide_breath_period_s": feedback_config.guide_breath_period_s,
                      "modalities": list(feedback_config.modalities)},
            "events": [e.to_dict() for e in events],
            "digest": events_digest(events),
        },
    }
