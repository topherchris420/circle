"""Live R.A.I.N. connector: ask the real proposer, in the contract it defines.

Lop Nur Twin's research runtime answers bounded proposals: the host frames a
question with fixed options, and R.A.I.N. returns a validated choice with
its reasoning (`POST /api/rain/proposal`). That fits CIRCLE's rule exactly —
R.A.I.N. may choose among host-framed options; it can never invent a protocol
field, relax a gate, or edit the arms.

This module frames protocol design as three bounded choices (cue period, gate
tightening, scenario), asks a live R.A.I.N. deployment, and records its
answer and reasoning as the proposal's provenance. If R.A.I.N. is not
reachable, callers fall back to the deterministic stand-in — recorded as such.
"""

from __future__ import annotations

import json
from typing import Any
import urllib.request

RAIN_DEPLOYMENT = "https://lop-nur-twin.vercel.app"
CONNECT_TIMEOUT_S = 60

QUESTIONS = {
    "cue_period_s": {
        "question": "CIRCLE asks: which paced-breathing cue period (seconds) should this closed-loop "
                   "physiology experiment test against its matched sham arm?",
        "options": [8, 9, 10, 11, 12],
    },
    "min_beat_coverage": {
        "question": "CIRCLE asks: which beat-coverage quality gate (minimum fraction of the heart-rate "
                   "window covered by valid beats) should the controller require? Tighter is safer, "
                   "too tight may never act.",
        "options": [0.7, 0.75, 0.8],
    },
    "scenario": {
        "question": "CIRCLE asks: which disturbance scenario should the experiment run on? 'clean' is "
                   "rest-to-recovery; 'interrupted' briefly obscures a warranted state with motion.",
        "options": ["clean", "interrupted"],
    },
}


def rain_proposal(base_url: str = RAIN_DEPLOYMENT, timeout_s: int = CONNECT_TIMEOUT_S) -> dict[str, Any]:
    """Ask the live R.A.I.N. runtime to choose, for each design question."""
    try:
        return ask_rain({}, base_url, timeout_s)
    except RuntimeError:
        raise


def build_rain_protocol(answers: dict[str, Any], seeds: list[int], index: int) -> dict[str, Any]:
    """A CIRCLE protocol composed from R.A.I.N.'s bounded choices."""
    from tools.run_rain_bridge import REVIEWER  # noqa: F401 - documented shared reviewer
    return {
        "schema": "circle-experiment-protocol/1",
        "protocol_id": f"PROTO-A11C{index:04X}",
        "proposed_by": {"kind": "AI_MODEL",
                       "name": "R.A.I.N. (lop-nur-twin live runtime)",
                       "model_version": "lop-nur-twin deployment"},
        "hypothesis": f"R.A.I.N.-chosen configuration: cue period {answers.get('cue_period_s')} s, "
                      f"beat-coverage gate {answers.get('min_beat_coverage')}, scenario "
                      f"{answers.get('scenario')} lowers the recovery arousal proxy versus matched sham.",
        "rationale": "Composed from R.A.I.N.'s bounded choices among host-framed options; every field "
                     "CIRCLE validates is host-authored.",
        "target": "SIMULATION", "scenario": answers.get("scenario", "clean"),
        "arms": [{"id": "ACTIVE", "actuate": True}, {"id": "SHAM", "actuate": False}],
        "intervention": {"kind": "HAPTIC_PACED_BREATHING", "cue_period_s": answers.get("cue_period_s", 10)},
        "decision_rule": {"controller": "CIRCLE_CLOSED_LOOP_CONTROLLER", "overrides": {}},
        "quality_gates": {"min_beat_coverage": answers.get("min_beat_coverage", 0.7)},
        "outcomes": [
            {"id": "arousal_proxy", "metric": "recovery_arousal_index_mean", "role": "PRIMARY", "direction": "DECREASE"},
            {"id": "motion", "metric": "recovery_motion_fraction", "role": "SAFETY", "direction": "NO_INCREASE"},
        ],
        "seeds": list(seeds),
        "stopping_rule": {"kind": "FIXED_SAMPLE", "note": "Fixed seed pairs, chosen before any run."},
        "analysis_plan": {"test": "PAIRED_SIGN_FLIP_PERMUTATION", "alpha": 0.05, "correction": "HOLM",
                          "exclusions": "None."},
    }


def ask_rain(choices: dict[str, Any], base_url: str = RAIN_DEPLOYMENT,
             timeout_s: int = CONNECT_TIMEOUT_S) -> dict[str, Any]:
    """Ask the live R.A.I.N. runtime to choose, for each design question.

    Returns {answers: {question_key: chosen_option}, provenance: {...}} or
    raises RuntimeError with the deployment's own error text.
    """
    answers: dict[str, Any] = {}
    for key, spec in QUESTIONS.items():
        payload = json.dumps({
            "question": spec["question"],
            "options": spec["options"],
            "session": {"asker": "circle-research-bridge", "question_key": key},
            "request_id": f"circle-{key}",
        }).encode("utf-8")
        request = urllib.request.Request(f"{base_url.rstrip('/')}/api/rain/proposal",
                                        data=payload, headers={"Content-Type": "application/json"},
                                        method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                document = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - reported verbatim for the record
            raise RuntimeError(f"R.A.I.N. proposal for {key} failed: {exc}") from exc
        chosen = _extract_choice(document)
        if chosen not in spec["options"]:
            raise RuntimeError(f"R.A.I.N. chose {chosen!r} for {key}, which is not among the offered options")
        answers[key] = chosen
    return {"answers": answers, "provenance": {"proposer": "R.A.I.N. (lop-nur-twin live runtime)",
                                               "endpoint": f"{base_url.rstrip('/')}/api/rain/proposal",
                                               "raw": "recorded in the bridge report"}}


def _extract_choice(document: Any) -> Any:
    """Pull the chosen option from a proposal response, tolerating envelope shapes."""
    if isinstance(document, dict):
        for key in ("choice", "option", "answer", "selection"):
            if key in document:
                value = document[key]
                return value.get("option", value.get("choice", value)) if isinstance(value, dict) else value
        nested = document.get("proposal") or document.get("result")
        if nested is not None:
            return _extract_choice(nested)
        if "answer" in document.get("meeting", {}):
            return _extract_choice(document["meeting"])
    return document
