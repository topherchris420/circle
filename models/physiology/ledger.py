"""Closed-loop evidence ledger and session passport, derived only from session records.

The ledger answers two different questions for every intervention and keeps
them apart:

  Why did the system act?        decision time, input cutoff, gate results,
                                 formula components, exact source ranges.
  What shows the action happened? command -> electrical onset -> independent
                                 physical observation, each its own event.

It never answers "did the intervention work?". Within-session before/after
changes are not effect evidence; the matched counterfactual in a twin run is
evidence only under the twin's assumed response model.

Because the ledger is a pure function of session.ndjson, the auditor rebuilds
it and requires an exact match.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

LEDGER_SCHEMA = "circle-closed-loop-ledger/1"
COMPONENTS = (("hr", "hr_z", "weight_hr"), ("scl", "scl_z", "weight_scl"), ("scr_rate", "scr_z", "weight_scr"))
INTERPRETATION = (
    "No record in this session asserts that an intervention changed physiology. Execution evidence shows that "
    "commands were issued and, where stated, physically observed. Attributing later signal changes to the "
    "intervention requires a matched control (sham arm, randomized timing, or counterfactual); in a twin run the "
    "counterfactual is valid only under the twin's assumed response model and is not evidence of human effect."
)


def _flag(record: dict[str, Any], prefix: str) -> str | None:
    return next((f[len(prefix):] for f in record["status_flags"] if f.startswith(prefix)), None)


def _flags(record: dict[str, Any], prefix: str) -> list[str]:
    return [f[len(prefix):] for f in record["status_flags"] if f.startswith(prefix)]


def build_ledger(records: list[dict[str, Any]]) -> dict[str, Any]:
    header = next(r for r in records if r["record_type"] == "SESSION_HEADER")
    config_record = next(r for r in records if r["record_type"] == "CONFIG_CHANGE" and "CONTROLLER_CONFIG" in r["status_flags"])
    config = config_record["payload"]
    evaluations_raw = sorted((r for r in records if r["record_type"] == "MODEL_RESULT" and "CONTROLLER_EVALUATION" in r["status_flags"]),
                             key=lambda r: r["decision_time_us"])
    events = {f"{r['stream_id']}#{r['sequence']}": r for r in records if r["record_type"] == "EVENT" and "sequence" in r}

    evaluations = []
    for i, r in enumerate(evaluations_raw):
        p = r["payload"]
        formula = {}
        for name, z_key, w_key in COMPONENTS:
            if z_key in p:
                formula[name] = {"z": p[z_key], "weight": config[w_key], "contribution": round(p[z_key] * config[w_key], 6)}
        evaluations.append({
            "id": f"EVAL-{i:03d}", "decision_time_us": r["decision_time_us"], "input_cutoff_us": r["input_cutoff_us"],
            "window_start_us": r["device_time_start_us"], "state_after": _flag(r, "STATE:"), "action": _flag(r, "ACTION:"),
            "decision_id": r.get("decision_id"), "gate": _flags(r, "GATE_FAIL:") or ["PASS"],
            "arousal_index": p.get("arousal_index"), "formula": formula,
            "features": {k: v for k, v in sorted(p.items()) if not k.endswith("_z") and k != "arousal_index"},
            "source_sequence_ranges": r["source_sequence_ranges"], "record_crc32c": r["crc32c"],
        })

    interventions = {r["decision_id"]: r for r in records if r["record_type"] == "INTERVENTION"}
    decisions = []
    for i, ev in enumerate(evaluations):
        if not ev["decision_id"]:
            continue
        entry: dict[str, Any] = {"decision_id": ev["decision_id"], "action": ev["action"], "evaluation": ev["id"],
                                 "decision_time_us": ev["decision_time_us"], "input_cutoff_us": ev["input_cutoff_us"],
                                 "why": _why(evaluations, i, config)}
        commands = sorted((e for e in events.values() if e.get("decision_id") == ev["decision_id"]
                           and _flag(e, "EVENT_KIND:") in ("HAPTIC_COMMAND", "HAPTIC_COMMAND_SHAM")),
                          key=lambda e: e["device_time_start_us"])
        entry["commands"] = len(commands)
        if ev["action"] == "START_PACED_BREATHING":
            intervention = interventions.get(ev["decision_id"])
            if intervention is not None:
                entry["execution_chain"] = [_link_detail(link, events) for link in intervention["execution_chain"]]
                entry["execution"] = _flag(intervention, "EXECUTION:")
            elif commands and all(_flag(e, "EVENT_KIND:") == "HAPTIC_COMMAND_SHAM" for e in commands):
                entry["execution"] = "NOT_ACTUATED_SHAM_ARM"
            else:
                entry["execution"] = "NO_INTERVENTION_RECORD"
        decisions.append(entry)

    holds = Counter(reason for ev in evaluations if ev["action"] and ev["action"].startswith("HOLD_") for reason in
                    (ev["gate"] if ev["action"] == "HOLD_QUALITY" else [ev["action"][5:]]))
    gate_failures = Counter(reason for ev in evaluations for reason in ev["gate"] if reason != "PASS")
    return {
        "schema": LEDGER_SCHEMA,
        "provenance": "DERIVED_FROM_SESSION_RECORDS",
        "passport": passport(records),
        "controller": {"version": _flag(config_record, "CONTROLLER_VERSION:"), "trigger_index": config["trigger_index"],
                       "release_index": config["release_index"], "decision_margin_s": config["decision_margin_s"],
                       "agreement_z": config["agreement_z"]},
        "evaluations": evaluations,
        "decisions": decisions,
        "holds_by_reason": dict(sorted(holds.items())),
        "gate_failures_by_reason": dict(sorted(gate_failures.items())),
        "interpretation": INTERPRETATION,
        "arm": next((f for f in header["status_flags"] if f.startswith("ARM_")), None),
    }


def _link_detail(link: dict[str, Any], events: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"cue_index": link["cue_index"], "stage": link["stage"]}
    command = events.get(link["command_id"])
    t_cmd = command["device_time_start_us"] if command else None
    out["command"] = {"id": link["command_id"], "device_time_us": t_cmd}
    for key, name in (("electrical_onset_id", "electrical_onset"), ("physical_observation_id", "physical_observation")):
        if key in link:
            event = events.get(link[key])
            t = event["device_time_start_us"] if event else None
            detail: dict[str, Any] = {"id": link[key], "device_time_us": t,
                                      "latency_from_command_us": (t - t_cmd) if t is not None and t_cmd is not None else None}
            if event and "source_sequence_ranges" in event:
                detail["source_sequence_ranges"] = event["source_sequence_ranges"]
                detail["provenance"] = event["provenance"]
            out[name] = detail
        else:
            out[name] = None
    return out


def _agreement(ev: dict[str, Any], config: dict[str, Any]) -> str:
    f, formula = ev["features"], ev["formula"]
    cardio = f"cardiovascular: HR z {formula['hr']['z']:.2f} >= {config['agreement_z']:.1f}" if f.get("cardiovascular_agrees") else "cardiovascular not elevated"
    electro = (f"electrodermal: SCL z {formula['scl']['z']:.2f} >= {config['agreement_z']:.1f}" if f.get("electrodermal_agrees")
               else "electrodermal not elevated")
    return f"both systems agree ({cardio}; {electro})"


def _why(evaluations: list[dict[str, Any]], i: int, config: dict[str, Any]) -> str:
    ev = evaluations[i]
    action = ev["action"] or ""
    index = ev["arousal_index"]
    if action == "START_PACED_BREATHING":
        needed = int(config["trigger_consecutive"])
        run = [e["arousal_index"] for e in evaluations[max(0, i - needed + 1):i + 1]]
        parts = [f"arousal index {', '.join(f'{x:.2f}' for x in run)} >= trigger {config['trigger_index']:.2f} "
                 f"for {needed} consecutive evaluations",
                 _agreement(ev, config),
                 "all quality gates passed",
                 f"inputs taken <= {ev['input_cutoff_us']} us, decided at {ev['decision_time_us']} us"]
        return "; ".join(parts)
    if action == "STOP_RELEASED":
        return (f"after >= {config['min_program_s']:.0f} s of guidance, arousal index fell below release "
                f"{config['release_index']:.2f} for {int(config['release_consecutive'])} consecutive evaluations "
                f"(latest {index:.2f})")
    if action == "STOP_MAX_DURATION":
        return f"guidance reached its {config['max_program_s']:.0f} s limit"
    if action == "STOP_QUALITY_LOST":
        return (f"quality gates failed for {int(config['max_quality_failures_in_program'])} consecutive evaluations "
                f"({', '.join(ev['gate'])}); a loop that cannot observe its effect was stopped")
    return action


def passport(records: list[dict[str, Any]], extra: dict[str, str] | None = None) -> dict[str, str]:
    """Compact identity and evidence status of a session (see passport_text)."""
    header = next(r for r in records if r["record_type"] == "SESSION_HEADER")
    flags = set(header["status_flags"])
    config_record = next(r for r in records if r["record_type"] == "CONFIG_CHANGE" and "CONTROLLER_CONFIG" in r["status_flags"])
    streams = [r for r in records if r["record_type"] == "STREAM_DESCRIPTOR"]
    evaluations = [r for r in records if r["record_type"] == "MODEL_RESULT" and "CONTROLLER_EVALUATION" in r["status_flags"]]
    interventions = [r for r in records if r["record_type"] == "INTERVENTION"]
    holds = sum(1 for r in evaluations if (_flag(r, "ACTION:") or "").startswith("HOLD_"))
    decisions = sum(1 for r in evaluations if "decision_id" in r)
    gate_failed = sum(1 for r in evaluations if _flags(r, "GATE_FAIL:"))
    cues = sum(len(r["execution_chain"]) for r in interventions)
    observed = sum(1 for r in interventions for link in r["execution_chain"] if link["stage"] == "PHYSICALLY_OBSERVED")
    sham_commands = sum(1 for r in records if r["record_type"] == "EVENT" and "EVENT_KIND:HAPTIC_COMMAND_SHAM" in r["status_flags"])
    out = {
        "SESSION": _flag(header, "SESSION_ID:") or "unnamed",
        "MODE": "SIMULATED" if "SIMULATED_DATA" in flags else "RECORDED",
        "ARM": "ACTIVE" if "ARM_ACTIVE" in flags else "SHAM" if "ARM_SHAM" in flags else "UNSPECIFIED",
        "SCENARIO": _flag(header, "SCENARIO:") or "unspecified",
        "HARDWARE": "Rev B forward model (no hardware built)" if "PHYSIOLOGY_TWIN" in flags else "unspecified",
        "PIPELINE": _flag(header, "PIPELINE_VERSION:") or "unknown",
        "CONTROLLER": _flag(config_record, "CONTROLLER_VERSION:") or "unknown",
        "SEED": str(int(header["payload"]["seed"])) if "seed" in header.get("payload", {}) else "n/a",
        "INPUT": f"{len(streams)} streams ({', '.join(r['stream_id'] for r in streams)})",
        "GAPS": f"{sum(1 for r in records if r['record_type'] == 'GAP')} declared",
        "EVALUATIONS": f"{len(evaluations)} ({decisions} decisions, {gate_failed} failed a quality gate, {holds} held an action)",
        "INTERVENTIONS": (f"{len(interventions)} program(s), {observed}/{cues} cues physically observed" if interventions
                          else f"none actuated ({sham_commands} sham commands logged)" if sham_commands else "none"),
        "HUMAN DATA": "NONE" if "NOT_HUMAN_DATA" in flags else "UNSPECIFIED",
        "HARDWARE DRIVEN": "NONE" if "PHYSIOLOGY_TWIN" in flags else "UNSPECIFIED",
    }
    out.update(extra or {})
    return out


def passport_text(values: dict[str, str]) -> str:
    width = max(len(k) for k in values)
    return "\n".join(f"{k + ':':<{width + 1}} {v}" for k, v in values.items()) + "\n"
