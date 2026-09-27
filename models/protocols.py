"""Experiment protocols: proposal -> validation -> human authorization -> execution -> measurement.

An AI model (or a person) may propose a protocol. It becomes executable only
after two separate steps:

  1. Deterministic validation against CIRCLE's contracts and policy. Quality
     gates may only be tightened; the causality margin cannot be touched; a
     matched sham arm is mandatory; outcomes come from a fixed menu whose
     evidence class is explicit; confirmatory seeds must be held out.
  2. Human authorization bound to the protocol's canonical SHA-256. Changing a
     single byte of the protocol voids the authorization.

From this repository the only executable target is SIMULATION. Proposals
targeting phantoms, bench hardware, or people are rejected here; those targets
are governed by hardware/review-gates.json and by approvals outside software.

More capable models get more analytical resolution, not more authority.
"""

from __future__ import annotations

from dataclasses import fields, replace
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator

from models.physiology.controller import ControllerConfig, replay
from models.physiology.experiment import SessionRun, run_session
from models.physiology.scenarios import SCENARIOS

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts/experiment-protocol.schema.json"
DEVELOPMENT_SEEDS = range(0, 30)
DEFAULTS = ControllerConfig()

# Gate settings may only move in the stricter direction.
TIGHTEN_ONLY = {
    "min_beat_coverage": "increase", "max_motion_fraction": "decrease", "stale_after_s": "decrease",
    "min_eda_contact_fraction": "increase", "recent_clean_s": "increase", "agreement_z": "increase",
"max_quality_failures_in_program": "decrease", "ppg_coupling_band": "increase",
}
DECISION_OVERRIDES = {"trigger_index", "release_index", "trigger_consecutive", "release_consecutive", "min_program_s",
                      "max_program_s", "refractory_s", "max_programs"}

# Outcome menu. The evidence class says what kind of claim the number can support.
OUTCOMES = {
    "recovery_arousal_index_mean": ("CONTROLLER_DERIVED", "Mean controller arousal index over evaluations in the armed phase"),
    "recovery_motion_fraction": ("PIPELINE_DERIVED", "Mean IMU motion fraction over evaluations in the armed phase"),
    "recovery_hr_bpm": ("PIPELINE_DERIVED", "Median pipeline heart rate over 10 s windows in the armed phase"),
    "recovery_resp_rate_bpm": ("PIPELINE_DERIVED", "Median pipeline respiratory rate in the armed phase"),
    "quality_holds": ("CONTROLLER_RECORD", "Evaluations whose action was a hold"),
    "recovery_latent_arousal_mean": ("TWIN_TRUTH", "Twin latent arousal over the armed phase (true only under the twin's assumed model)"),
}


class ProtocolError(ValueError):
    """A protocol cannot be executed."""


def canonical_sha256(document: dict[str, Any]) -> str:
    data = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def validate(protocol: dict[str, Any]) -> dict[str, Any]:
    """Deterministic validation. Returns {status, problems, protocol_sha256}."""
    problems = [f"{'/'.join(map(str, e.path)) or 'protocol'}: {e.message}"
                for e in Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).iter_errors(protocol)]
    if problems:
        return {"status": "REJECTED", "problems": problems, "protocol_sha256": None}
    if protocol["target"] != "SIMULATION":
        gate = {"ELECTRONIC_PHANTOM": "ELECTRONIC_PHANTOM_VALIDATION (no phantom executor exists)",
                "HARDWARE_BENCH": "POWERED_BENCH_TEST gates in hardware/review-gates.json",
                "HUMAN_PARTICIPANT": "HUMAN_CONNECTION gates and HUMAN_RESEARCH_APPROVAL"}[protocol["target"]]
        problems.append(f"target {protocol['target']} is not executable from this repository; governed by {gate}")
    if protocol["proposed_by"]["kind"] == "AI_MODEL" and not protocol["proposed_by"].get("model_version"):
        problems.append("an AI-proposed protocol must name its model_version")
    if protocol["scenario"] not in SCENARIOS:
        problems.append(f"unknown scenario {protocol['scenario']}")
    arms = {a["id"]: a["actuate"] for a in protocol["arms"]}
    if arms != {"ACTIVE": True, "SHAM": False}:
        problems.append("arms must be one actuated ACTIVE arm and one non-actuated SHAM arm sharing seeds")
    overrides = protocol["decision_rule"].get("overrides", {})
    for key in sorted(set(overrides) - DECISION_OVERRIDES):
        problems.append(f"decision override {key} is not permitted (causality margin and gates cannot be relaxed here)")
    for key, value in protocol["quality_gates"].items():
        if key not in TIGHTEN_ONLY:
            problems.append(f"unknown quality gate {key}")
            continue
        default = getattr(DEFAULTS, key)
        looser = value < default if TIGHTEN_ONLY[key] == "increase" else value > default
        if looser:
            problems.append(f"quality gate {key}={value} is looser than the default {default}")
    try:
        controller_config(protocol)
    except (ValueError, TypeError) as exc:
        problems.append(f"controller configuration invalid: {exc}")
    ids = [o["id"] for o in protocol["outcomes"]]
    if len(ids) != len(set(ids)):
        problems.append("outcome ids must be unique")
    for outcome in protocol["outcomes"]:
        if outcome["metric"] not in OUTCOMES:
            problems.append(f"outcome metric {outcome['metric']} is not in the menu {sorted(OUTCOMES)}")
    primaries = [o for o in protocol["outcomes"] if o["role"] == "PRIMARY"]
    if len(primaries) != 1:
        problems.append("exactly one PRIMARY outcome is required")
    tested = [o for o in protocol["outcomes"] if o["role"] != "SAFETY"]
    if len(tested) > 1 and protocol["analysis_plan"]["correction"] != "HOLM":
        problems.append("more than one tested outcome requires HOLM correction")
    development = sorted(set(protocol["seeds"]) & set(DEVELOPMENT_SEEDS))
    if development:
        problems.append(f"seeds {development} were used to develop the methods; confirmatory runs need held-out seeds")
    return {"status": "VALID_FOR_SIMULATION" if not problems else "REJECTED", "problems": problems,
            "protocol_sha256": canonical_sha256(protocol)}


def controller_config(protocol: dict[str, Any]) -> ControllerConfig:
    kinds = {f.name: f.type for f in fields(ControllerConfig)}
    values: dict[str, Any] = {}
    for key, value in {**protocol["decision_rule"].get("overrides", {}), **protocol["quality_gates"]}.items():
        values[key] = int(value) if str(kinds.get(key)) == "int" else float(value)
    if "cue_period_s" in protocol["intervention"]:
        values["cue_period_s"] = float(protocol["intervention"]["cue_period_s"])
    return replace(DEFAULTS, **values)


def authorize(protocol: dict[str, Any], reviewer: str, date: str) -> dict[str, Any]:
    """A human's authorization, bound to this exact protocol. Never produced automatically."""
    result = validate(protocol)
    if result["status"] != "VALID_FOR_SIMULATION":
        raise ProtocolError("cannot authorize a protocol that failed validation: " + "; ".join(result["problems"]))
    if not reviewer.strip():
        raise ProtocolError("authorization requires a named human reviewer")
    return {"schema": "circle-protocol-authorization/1", "protocol_id": protocol["protocol_id"],
            "protocol_sha256": result["protocol_sha256"], "target": "SIMULATION", "authorized_by": reviewer.strip(),
            "authorized_on": date,
            "statement": "Authorizes execution against the simulation twin only. Grants no hardware or human use."}


def _outcome(run: SessionRun, metric: str) -> float:
    c = run.config.controller
    arm = next(e.device_time_us for e in run.raw.events if e.kind == f"PHASE_START:{c.arm_phase}")
    evals = [e for e in run.evaluations if e.device_time_us >= arm]
    if metric == "recovery_arousal_index_mean":
        values = [e.features["arousal_index"] for e in evals if "arousal_index" in e.features]
        return float(np.mean(values)) if values else float("nan")
    if metric == "recovery_motion_fraction":
        return float(np.mean([e.features.get("motion_fraction", 1.0) for e in evals])) if evals else float("nan")
    if metric == "recovery_hr_bpm":
        values = [w["payload"]["hr_bpm"] for w in run.analysis.windows if w["device_time_start_us"] >= arm and "hr_bpm" in w["payload"]]
        return float(np.median(values)) if values else float("nan")
    if metric == "recovery_resp_rate_bpm":
        resp = run.analysis.respiration
        mask = resp["rate_t_s"] >= arm / 1e6
        return float(np.median(resp["rate_bpm"][mask])) if mask.any() else float("nan")
    if metric == "quality_holds":
        return float(sum(1 for e in run.evaluations if e.action and e.action.startswith("HOLD_")))
    if metric == "recovery_latent_arousal_mean":
        twin = run.twin
        start = float(run.rig.clock.to_true_s(arm))
        grid = twin.t_grid[:twin._n]
        return float(np.mean(twin.arousal[:twin._n][grid >= start]))
    raise ProtocolError(f"unknown metric {metric}")


def sign_flip_p(differences: np.ndarray, direction: str, permutations: int, seed: int) -> float:
    """Paired sign-flip permutation p-value (exact up to 16 pairs, else Monte Carlo; never zero)."""
    d = differences[np.isfinite(differences)]
    if not len(d):
        return float("nan")
    observed = float(np.mean(d))

    def extreme(stat: float) -> bool:
        if direction == "DECREASE":
            return stat <= observed + 1e-12
        if direction in ("INCREASE", "NO_INCREASE"):
            return stat >= observed - 1e-12
        return abs(stat) >= abs(observed) - 1e-12

    if len(d) <= 16:
        stats = [float(np.mean(d * np.array(signs))) for signs in itertools.product((1, -1), repeat=len(d))]
        return sum(extreme(s) for s in stats) / len(stats)
    rng = np.random.default_rng(seed)
    count = sum(extreme(float(np.mean(d * rng.choice((1, -1), len(d))))) for _ in range(permutations))
    return (count + 1) / (permutations + 1)


def holm(p_values: dict[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values (monotone, capped at 1)."""
    ordered = sorted(p_values.items(), key=lambda kv: kv[1])
    adjusted, running = {}, 0.0
    for rank, (key, p) in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * p))
        adjusted[key] = running
    return adjusted


def execute(protocol: dict[str, Any], authorization: dict[str, Any]) -> dict[str, Any]:
    """Run an authorized protocol against the twin. Refuses anything else."""
    result = validate(protocol)
    if result["status"] != "VALID_FOR_SIMULATION":
        raise ProtocolError("protocol failed validation: " + "; ".join(result["problems"]))
    if authorization.get("protocol_sha256") != result["protocol_sha256"]:
        raise ProtocolError("PROTOCOL_CHANGED: authorization does not match this protocol's SHA-256")
    if authorization.get("target") != "SIMULATION" or not authorization.get("authorized_by"):
        raise ProtocolError("authorization must name a human reviewer and target SIMULATION")
    scenario = SCENARIOS[protocol["scenario"]]
    config = controller_config(protocol)
    per_seed, replays_match = [], True
    for seed in protocol["seeds"]:
        base = replace(scenario.configure(seed), controller=config)
        runs = {arm["id"]: run_session(replace(base, actuate=arm["actuate"])) for arm in protocol["arms"]}
        for run in runs.values():
            again = replay(run.raw, run.config.controller, run.evaluation_end_us)
            replays_match &= [e.comparable() for e in again] == [e.comparable() for e in run.evaluations]
        per_seed.append({"seed": seed, **{arm: {o["id"]: _outcome(run, o["metric"]) for o in protocol["outcomes"]}
                                          for arm, run in runs.items()}})
    plan = protocol["analysis_plan"]
    permutations = int(plan.get("permutations", 9999))
    stream_seed = int(result["protocol_sha256"][:8], 16)
    tests, raw_p = {}, {}
    for outcome in protocol["outcomes"]:
        d = np.array([s["ACTIVE"][outcome["id"]] - s["SHAM"][outcome["id"]] for s in per_seed], dtype=float)
        p = sign_flip_p(d, outcome["direction"], permutations, stream_seed)
        finite = d[np.isfinite(d)]
        sd = float(np.std(finite, ddof=1)) if len(finite) > 1 else float("nan")
        tests[outcome["id"]] = {"metric": outcome["metric"], "evidence_class": OUTCOMES[outcome["metric"]][0],
                                "role": outcome["role"], "direction": outcome["direction"], "n_pairs": int(len(finite)),
                                "mean_difference_active_minus_sham": float(np.mean(finite)) if len(finite) else float("nan"),
                                "paired_effect_size_dz": float(np.mean(finite) / sd) if sd and math.isfinite(sd) and sd > 0 else float("nan"),
                                "p_value": p}
        if outcome["role"] != "SAFETY":
            raw_p[outcome["id"]] = p
    adjusted = holm(raw_p) if plan["correction"] == "HOLM" else raw_p
    for key, entry in tests.items():
        alpha = plan["alpha"]
        if entry["role"] == "SAFETY":
            entry["conclusion"] = ("INCREASE_DETECTED" if entry["p_value"] < alpha
                                   else "NO_INCREASE_DETECTED (not a demonstration of equivalence)")
        else:
            entry["p_adjusted"] = adjusted[key]
            entry["conclusion"] = "SUPPORTED_IN_SIMULATION" if adjusted[key] < alpha else "NOT_SUPPORTED"
    return {"schema": "circle-protocol-result/1", "provenance": "SIMULATED", "protocol_id": protocol["protocol_id"],
            "protocol_sha256": result["protocol_sha256"], "authorized_by": authorization["authorized_by"],
            "scenario": protocol["scenario"], "seeds": protocol["seeds"], "replays_match": replays_match,
            "tests": tests, "per_seed": per_seed,
            "interpretation": ("Results hold only under the twin's assumed response model. TWIN_TRUTH outcomes are the "
                               "model's own latent variables. A supported simulation hypothesis validates the analytical "
                               "machinery and the protocol, not a physiological or human effect.")}
