"""Live R.A.I.N. connector: ask the real proposer, in the contract it defines.

Lop Nur Twin's research runtime answers bounded proposals (``POST
/api/rain/proposal``): the host frames a question with fixed options — each an
``{id, description}`` object — and R.A.I.N. returns a validated
``proposal-choice`` carrying the selected option id, its reason, and the
engines consulted. That fits CIRCLE's rule exactly: R.A.I.N. chooses among
host-framed options; it can never invent a protocol field, relax a gate, or
edit the arms.

Every answer records what priority-2 asks for: the reasoning (``reason``),
the model version (``attempts[].engine/model``), the composed protocol, and
CIRCLE's validation verdict on it. If R.A.I.N. is unreachable, callers fall
back to the deterministic stand-in — recorded as such, never swapped
silently.
"""

from __future__ import annotations

import json
import re
from typing import Any
import urllib.request

RAIN_DEPLOYMENT = "https://lop-nur-twin.vercel.app"
CONNECT_TIMEOUT_S = 90

# Host-framed design choices. Option ids must match ^[A-Za-z][A-Za-z0-9_]{0,63}$.
QUESTIONS: dict[str, dict[str, Any]] = {
    "cue_period_s": {
        "question": "CIRCLE closed-loop physiology asks: which paced-breathing cue period (seconds) "
                   "should this experiment test against its matched sham arm?",
        "options": [(v, f"{v} second cue period") for v in (8, 9, 10, 11, 12)],
        "values": [8, 9, 10, 11, 12],
    },
    "min_beat_coverage": {
        "question": "CIRCLE asks: which beat-coverage quality gate (minimum fraction of the heart-rate "
                   "window covered by valid beats) should the controller require? Tighter is safer; "
                   "too tight may never act.",
        "options": [(v, f"require at least {v} beat coverage") for v in (0.7, 0.75, 0.8)],
        "values": [0.7, 0.75, 0.8],
    },
    "scenario": {
        "question": "CIRCLE asks: which disturbance scenario should the experiment run on? 'clean' is "
                   "rest-to-recovery; 'interrupted' briefly obscures a warranted state with motion.",
        "options": [(v, f"the {v} scenario") for v in ("clean", "interrupted")],
        "values": ["clean", "interrupted"],
    },
}


def _option_id(key: str, value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_]", "_", f"{key}_{value}").strip("_")
    return ("opt_" + text)[:64]


def ask_rain(choices: dict[str, Any], base_url: str = RAIN_DEPLOYMENT,
             timeout_s: int = CONNECT_TIMEOUT_S) -> dict[str, Any]:
    """Ask the live R.A.I.N. runtime to choose, for each design question.

    Returns {answers, reasoning, attempts} or raises RuntimeError carrying the
    deployment's own error text.
    """
    answers: dict[str, Any] = {}
    reasoning: dict[str, Any] = {}
    attempts: dict[str, Any] = {}
    session_id = "c1c1e0000000000000000000000000f"  # hex per contract
    for key, spec in QUESTIONS.items():
        import hashlib
        # One lab session per question: the server rate-limits repeat ops within
        # a session, and each question is its own deliberation.
        session_id = hashlib.md5(("circle-session-" + key).encode("utf-8")).hexdigest()
        request_id = hashlib.md5(("circle-" + key).encode("utf-8")).hexdigest()  # HEX32 per contract
        payload = json.dumps({
            "question": spec["question"],
            "options": [{"id": _option_id(key, value), "description": description}
                        for value, description in spec["options"]],
            "session": session_id,
            "request_id": request_id,
        }).encode("utf-8")
        request = urllib.request.Request(f"{base_url.rstrip('/')}/api/rain/proposal",
                                        data=payload, headers={"Content-Type": "application/json"},
                                        method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                document = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - reported verbatim for the record
            raise RuntimeError(f"R.A.I.N. proposal for {key} failed: {exc}") from exc
        decision = document.get("decision") if isinstance(document, dict) else None
        selected = (decision or {}).get("selected")
        reason = (decision or {}).get("reason")
        if selected is None:
            # An honest non-choice: R.A.I.N. names why it proposed nothing
            # (e.g. its decision engine is off). Record it, never guess one.
            raise RuntimeError(f"R.A.I.N. made no choice for {key}: reason {reason!r} "
                               f"(enable its decision engine, e.g. RAIN_DECISION_MODE=jev with "
                               "RAIN_DECISION_REMOTE_ALLOWED=true and a TYPESAFE_API_KEY)")
        matched = next((value for value, _ in spec["options"]
                        if _option_id(key, value) == selected), None)
        if matched is None:
            raise RuntimeError(f"R.A.I.N. selected {selected!r} for {key}, which is not among the "
                               f"offered options")
        answers[key] = matched
        reasoning[key] = {"selected": selected, "reason": (decision or {}).get("reason"),
                          "decision_id": (decision or {}).get("decision_id"),
                          "envelope_hash": (decision or {}).get("envelope_hash")}
        attempts[key] = [{"engine": a.get("engine"), "model": a.get("model"),
                          "confidence": a.get("confidence")} for a in (decision or {}).get("attempts", [])]
    return {"answers": answers, "reasoning": reasoning, "attempts": attempts,
            "provenance": {"proposer": "R.A.I.N. (lop-nur-twin live runtime)",
                          "endpoint": f"{base_url.rstrip('/')}/api/rain/proposal"}}


def build_rain_protocol(answers: dict[str, Any], seeds: list[int], index: int) -> dict[str, Any]:
    """A CIRCLE protocol composed from R.A.I.N.'s bounded choices."""
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
