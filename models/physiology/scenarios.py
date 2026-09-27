"""Adversarial scenario families and system-level checks for the closed loop.

A good twin tries to break CIRCLE. Each scenario injects a disturbance that
tests one concrete system assumption, and declares where in (true) time the
evidence is impaired. System checks then judge the closed loop against hidden
truth rather than against its own quality gates: the controller does not get
to grade its own homework.

    clean              everything behaves; guidance should start after the stressor
    motion_heavy       sustained limb motion during recovery makes PPG unreliable
    poor_contact       an EDA electrode lifts, then optical coupling collapses
    timing_fault       extreme oscillator errors plus the longest observable FIFO stall
    sensor_loss        the PPG head stops answering for 14 s (one channel disappears)
    feedback_artifact  the haptic actuator contaminates the optical and EDA channels
    ambiguous          a heart-rate rise with no electrodermal change: one system
                       mimics arousal through a different pathway

This module is scoring-side: it reads twin truth and must never be imported by
the pipeline, controller, evidence, audit, or ledger modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable

import numpy as np

from .controller import replay
from .experiment import SessionConfig, SessionRun
from .sensors import RigConfig
from .twin import CardiacDrive, MotionEpisode, ProtocolPhase, TwinConfig, DEFAULT_MOTION

WARRANTED_AROUSAL = 0.5       # latent arousal (twin units) at which guidance is warranted
UNWARRANTED_AROUSAL = 0.35    # below this, starting guidance is an unwarranted intervention
RESPONSE_WINDOW_S = 20.0      # a warranted, observable state must be acted on within this time
IMPAIRING_ACTIONS = ("START_PACED_BREATHING", "STOP_RELEASED")


@dataclass(frozen=True)
class Scenario:
    name: str
    tests: str
    configure: Callable[[int], SessionConfig]
    impairments: tuple[tuple[str, float, float], ...] = ()   # (kind, true start, true end)
    expect_intervention: bool = True
    expected_gate_reasons: tuple[str, ...] = ()
    expected_actions: tuple[str, ...] = field(default=())


def _twin(seed: int, **changes: Any) -> TwinConfig:
    return replace(TwinConfig(seed=seed), **changes)


def _clean(seed: int) -> SessionConfig:
    return SessionConfig(twin=_twin(seed), scenario="clean")


def _motion_heavy(seed: int) -> SessionConfig:
    motion = DEFAULT_MOTION[:2] + (MotionEpisode("TYPING", 236.0, 22.0, 0.34), MotionEpisode("GESTURE", 268.0, 14.0, 0.45),
                                   MotionEpisode("POSTURE_SHIFT", 318.0, 3.5, 0.26))
    return SessionConfig(twin=_twin(seed, motion=motion), scenario="motion_heavy")


def _poor_contact(seed: int) -> SessionConfig:
    rig = RigConfig(eda_contact_loss=((236.0, 262.0),), ppg_coupling_loss=((272.0, 296.0, 0.10),))
    return SessionConfig(twin=_twin(seed), rig=rig, scenario="poor_contact")


def _timing_fault(seed: int) -> SessionConfig:
    rig = RigConfig(device_clock_ppm=80.0, ppg_clock_error_ppm=-9000.0, imu_clock_error_ppm=4000.0,
                    ppg_fifo_stall_at_s=241.0, ppg_fifo_stall_s=0.44)
    return SessionConfig(twin=_twin(seed), rig=rig, scenario="timing_fault")


def _sensor_loss(seed: int) -> SessionConfig:
    return SessionConfig(twin=_twin(seed), rig=RigConfig(ppg_detach=(244.0, 258.0)), scenario="sensor_loss")


def _feedback_artifact(seed: int) -> SessionConfig:
    rig = RigConfig(haptic_ppg_coupling_per_g=0.35, haptic_eda_coupling_us_per_g=0.6)
    return SessionConfig(twin=_twin(seed), rig=rig, scenario="feedback_artifact")


def _ambiguous(seed: int) -> SessionConfig:
    phases = (ProtocolPhase("REST_BASELINE", 0.0, 60.0), ProtocolPhase("BREATH_HOLD", 60.0, 90.0),
              ProtocolPhase("SETTLE", 90.0, 110.0), ProtocolPhase("QUIET_TASK", 110.0, 230.0),
              ProtocolPhase("RECOVERY", 230.0, 360.0))
    drive = (CardiacDrive("NON_SYMPATHETIC_HR_RISE", 236.0, 70.0, 16.0),)
    return SessionConfig(twin=_twin(seed, phases=phases, cardiac_drive=drive), scenario="ambiguous")


SCENARIOS: dict[str, Scenario] = {s.name: s for s in (
    Scenario("clean", "The loop acts on a warranted, well-observed state and releases on its own.", _clean),
    Scenario("motion_heavy", "Motion gating: no decision may rest on motion-corrupted PPG.", _motion_heavy,
             (("MOTION", 236.0, 258.0), ("MOTION", 268.0, 282.0)), expected_gate_reasons=("MOTION_EXCESSIVE",)),
    Scenario("poor_contact", "Contact faults are recognized as faults, not as calm physiology.", _poor_contact,
             (("EDA_CONTACT", 236.0, 262.0), ("PPG_COUPLING", 272.0, 296.0)),
             expected_gate_reasons=("EDA_CONTACT_LOST", "PPG_COUPLING_CHANGED")),
    Scenario("timing_fault", "Timestamp reconstruction and exact loss accounting survive extreme clocks and stalls.",
             _timing_fault),
    Scenario("sensor_loss", "A vanished channel produces stale-data holds and an exact declared gap.", _sensor_loss,
             (("PPG_LOSS", 244.0, 258.0),), expected_gate_reasons=("DATA_STALE",)),
    Scenario("feedback_artifact", "The intervention's own artifact neither breaks execution evidence nor fools the loop.",
             _feedback_artifact),
    Scenario("ambiguous", "One physiological system alone cannot trigger an intervention.", _ambiguous,
             expect_intervention=False, expected_actions=("HOLD_SIGNALS_DISAGREE",)),
)}


def _overlaps(a0: float, a1: float, intervals: list[tuple[float, float]]) -> bool:
    return any(a0 < b1 and b0 < a1 for b0, b1 in intervals)


def _impaired(cutoff: float, window_s: float, recent_s: float, tolerated: float, intervals: list[tuple[float, float]]) -> bool:
    """Truth-impaired evidence: corrupted at the cutoff, or over more than the tolerated share of the window."""
    if _overlaps(cutoff - recent_s, cutoff, intervals):
        return True
    covered = sum(max(0.0, min(cutoff, b) - max(cutoff - window_s, a)) for a, b in intervals)
    return covered > tolerated * window_s


def system_checks(run: SessionRun, scenario: Scenario) -> dict[str, Any]:
    """Judge the closed loop as a system against hidden truth. Returns checks plus details."""
    clock = run.rig.clock
    true_s = lambda device_us: float(clock.to_true_s(device_us))  # noqa: E731
    twin = run.twin
    c = run.config.controller
    motion = [(m.start_s - 0.5, m.start_s + m.duration_s + 0.5) for m in run.config.twin.motion]
    impaired = motion + [(a, b) for _, a, b in scenario.impairments]
    checks: list[dict[str, Any]] = []

    def check(check_id: str, label: str, passed: bool, detail: Any = None) -> None:
        checks.append({"id": check_id, "label": label, "passed": bool(passed), "detail": detail})

    # Replay and temporal lawfulness.
    replayed = replay(run.raw, c, run.evaluation_end_us)
    check("replay_match", "Replay reconstructs every decision exactly",
          [e.comparable() for e in replayed] == [e.comparable() for e in run.evaluations])
    unlawful = []
    for ev in run.evaluations:
        for r in ev.source_sequence_ranges:
            stream = run.raw.streams[r["stream_id"]]
            a = int(np.searchsorted(stream.sequence, r["first_sequence"]))
            b = int(np.searchsorted(stream.sequence, r["last_sequence"], side="right"))
            if stream.available_us[a:b].max() > ev.decision_time_us or stream.device_time_us[a:b].max() > ev.input_cutoff_us:
                unlawful.append(ev.decision_time_us)
            if stream.sequence[b - 1] - stream.sequence[a] != b - 1 - a:
                unlawful.append(ev.decision_time_us)
    check("temporally_lawful", "No decision used a sample taken after its cutoff, unavailable, or across a gap",
          not unlawful, {"violations": sorted(set(unlawful))[:5]})

    truth_lost = sorted(tuple(x) for x in run.rig.timing_truth()["ppg_lost_sequences"])
    declared = sorted((g.first_sequence, g.last_sequence) for g in run.raw.gaps)
    check("gaps_exact", "Declared gaps equal true sample loss", declared == truth_lost,
          {"declared": declared, "true": truth_lost})

    # Execution evidence.
    commands = [h for h in run.analysis.haptic if not h.get("sham")]
    observed = sum(1 for h in commands if "physical_onset_s" in h and "electrical_onset_s" in h)
    check("execution_observed", "Every actuated cue has electrical and independent physical evidence",
          observed == len(commands), {"cues": len(commands), "observed": observed})

    # Decisions judged against truth.
    def arousal(t: float) -> float:
        return float(np.interp(t, twin.t_grid[:twin._n], twin.arousal[:twin._n]))

    acted_on_impaired, unwarranted, gate_reasons, actions = [], [], set(), []
    for ev in run.evaluations:
        gate_reasons.update(ev.gate_reasons)
        if ev.action:
            actions.append(ev.action)
        cutoff = true_s(ev.input_cutoff_us)
        if ev.action in IMPAIRING_ACTIONS and _impaired(cutoff, c.hr_window_s, c.recent_clean_s, c.max_motion_fraction, impaired):
            acted_on_impaired.append({"t_s": round(true_s(ev.decision_time_us), 2), "action": ev.action})
        if ev.action == "START_PACED_BREATHING" and arousal(cutoff) < UNWARRANTED_AROUSAL:
            unwarranted.append({"t_s": round(true_s(ev.decision_time_us), 2), "latent_arousal": round(arousal(cutoff), 3)})
    check("no_action_on_impaired_evidence", "No start or release decided on truth-impaired evidence "
          "(corrupted at the cutoff or over > 20 % of the heart-rate window)",
          not acted_on_impaired, acted_on_impaired)
    check("no_unwarranted_intervention", "No guidance started when latent arousal was low", not unwarranted, unwarranted)

    # Timeliness: once guidance is warranted and the evidence is observable, the
    # loop should start within trigger_consecutive + 2 such evaluations.
    arm = next((e.device_time_us for e in run.raw.events if e.kind == f"PHASE_START:{c.arm_phase}"), None)
    qualifying, started, late_at = 0, None, None
    allowance = c.trigger_consecutive + 2
    for ev in run.evaluations:
        cutoff = true_s(ev.input_cutoff_us)
        if ev.action == "START_PACED_BREATHING" and started is None:
            started = true_s(ev.decision_time_us)
        if arm is None or ev.device_time_us < arm or started is not None:
            continue
        observable = not _overlaps(cutoff - c.feature_window_s, cutoff, impaired)
        qualifying = qualifying + 1 if observable and arousal(cutoff) >= WARRANTED_AROUSAL else 0
        if qualifying >= allowance and late_at is None:
            late_at = true_s(ev.decision_time_us)
    if scenario.expect_intervention:
        check("timely_response", f"Guidance starts within {allowance} evaluations of a warranted, observable state",
              late_at is None, {"late_at_s": round(late_at, 2) if late_at else None,
                                "started_s": round(started, 2) if started else None})
    else:
        check("refrained", "No guidance started in a scenario where none is warranted", started is None,
              {"started_s": round(started, 2) if started else None})

    detected = []
    for kind, a, b in scenario.impairments:
        flagged = any(ev.gate_reasons and _overlaps(true_s(ev.window_start_us), true_s(ev.input_cutoff_us), [(a, b)])
                      for ev in run.evaluations)
        detected.append({"impairment": kind, "start_s": a, "end_s": b, "flagged": flagged})
    if detected:
        check("impairments_flagged", "Every injected impairment raised a quality-gate failure",
              all(d["flagged"] for d in detected), detected)
    missing_reasons = sorted(set(scenario.expected_gate_reasons) - gate_reasons)
    missing_actions = sorted(set(scenario.expected_actions) - set(actions))
    if scenario.expected_gate_reasons or scenario.expected_actions:
        check("expected_abstention", "The expected abstention reasons appear in the record",
              not missing_reasons and not missing_actions, {"missing_reasons": missing_reasons, "missing_actions": missing_actions})

    decisions = [(round(true_s(e.decision_time_us), 1), e.action) for e in run.evaluations
                 if e.action and not e.action.startswith("HOLD_")]
    holds: dict[str, int] = {}
    for ev in run.evaluations:
        if ev.action and ev.action.startswith("HOLD_"):
            for reason in (ev.gate_reasons if ev.action == "HOLD_QUALITY" else [ev.action[5:]]):
                holds[reason] = holds.get(reason, 0) + 1
    return {"scenario": scenario.name, "tests": scenario.tests, "seed": run.config.twin.seed,
            "arm": "ACTIVE" if run.config.actuate else "SHAM", "checks": checks,
            "passed": all(ch["passed"] for ch in checks), "decisions": decisions, "holds_by_reason": dict(sorted(holds.items())),
            "gate_reasons_seen": sorted(gate_reasons)}
