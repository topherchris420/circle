"""Run a closed-loop CIRCLE session against the physiological twin.

The loop is strictly causal. At each controller evaluation time T (device
clock) the twin has generated physiology only up to T, the rig has recorded
only samples whose physical instant precedes T - 0.5 s, and the controller
reads only samples at least decision_margin old. Cues it schedules reach the
body through the haptic hardware model at their physical onset time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .controller import ClosedLoopController, ControllerConfig, Evaluation
from .pipeline import Analysis, analyze
from .sensors import HapticOutcome, RigConfig, SensorRig
from .streams import RawSession
from .twin import HapticCue, PhysiologyTwin, TwinConfig

ACQUISITION_LAG_S = 0.5


@dataclass(frozen=True)
class SessionConfig:
    twin: TwinConfig = field(default_factory=TwinConfig)
    rig: RigConfig = field(default_factory=RigConfig)
    controller: ControllerConfig = field(default_factory=ControllerConfig)
    actuate: bool = True


@dataclass
class SessionRun:
    config: SessionConfig
    raw: RawSession
    analysis: Analysis
    evaluations: list[Evaluation]
    haptic: list[HapticOutcome]
    controller_baseline: dict[str, float]
    controller_baseline_window_us: tuple[int, int]
    controller_baseline_ranges: list[dict[str, Any]]
    evaluation_end_us: int
    twin: PhysiologyTwin
    rig: SensorRig

    def truth(self) -> dict[str, Any]:
        """Hidden ground truth (twin physiology + exact timing). Scoring only."""
        truth = self.twin.truth()
        timing = self.rig.timing_truth()
        truth["timing"] = {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in timing.items()}
        return truth


def run_session(config: SessionConfig | None = None) -> SessionRun:
    config = config or SessionConfig()
    twin = PhysiologyTwin(config.twin)
    rig = SensorRig(twin, config.rig)
    controller = ClosedLoopController(config.controller)
    c = config.controller
    duration = config.twin.duration_s
    markers = sorted([(p.start_s, f"PHASE_START:{p.name}") for p in config.twin.phases]
                     + [(t, "STIMULUS") for t in twin.stimuli])
    next_marker = 0

    def log_markers_through(t_true: float) -> None:
        nonlocal next_marker
        while next_marker < len(markers) and markers[next_marker][0] <= t_true:
            rig.log_protocol_marker(markers[next_marker][1], markers[next_marker][0])
            next_marker += 1

    log_markers_through(0.0)
    anchor = min(e.device_time_us for e in rig.events)
    period = int(round(c.evaluation_period_s * 1e6))
    margin = int(round(c.decision_margin_s * 1e6))
    evaluations: list[Evaluation] = []
    outcomes: list[HapticOutcome] = []
    t_dev = anchor + period
    last_evaluated = anchor
    while True:
        t_true = float(rig.clock.to_true_s(t_dev))
        if t_true > duration - ACQUISITION_LAG_S:
            break
        log_markers_through(t_true)
        twin.advance_to(t_true)
        rig.acquire_until(t_true - ACQUISITION_LAG_S)
        session = rig.raw_session()
        _assert_complete_through(rig, t_dev - margin)
        evaluation = controller.evaluate(session, t_dev)
        last_evaluated = t_dev
        if evaluation is not None:
            evaluations.append(evaluation)
            for cue_us in evaluation.cues_device_us:
                cue_number = _cue_number(evaluations, evaluation.program, cue_us)
                outcome = rig.command_haptic(cue_us, config.actuate, evaluation.program or 0, cue_number)
                outcomes.append(outcome)
                if config.actuate:
                    program_start = min(o.truth["physical_onset_true_s"] for o in outcomes
                                        if o.truth["program"] == evaluation.program and "physical_onset_true_s" in o.truth)
                    twin.add_cues([HapticCue(evaluation.program or 0, cue_number, outcome.truth["physical_onset_true_s"],
                                             program_start, True)])
        t_dev += period
    log_markers_through(duration)
    twin.advance_to(duration)
    rig.acquire_until(duration - ACQUISITION_LAG_S)
    raw = rig.raw_session()
    if controller.baseline is None or controller.baseline_window_us is None:
        raise ValueError("Session ended before the controller baseline could be established")
    return SessionRun(config, raw, analyze(raw), evaluations, outcomes, dict(controller.baseline),
                      controller.baseline_window_us, list(controller.baseline_ranges), last_evaluated, twin, rig)


def _cue_number(evaluations: list[Evaluation], program: int | None, cue_us: int) -> int:
    cues = sorted(cue for ev in evaluations if ev.program == program for cue in ev.cues_device_us)
    return cues.index(cue_us)


def _assert_complete_through(rig: SensorRig, device_us: int) -> None:
    """Causality guard: every sample stamped <= device_us must already be recorded."""
    pending = {
        "eda": rig.eda_dev, "ppg": rig.ppg_dev, "imu": rig.imu_dev,
    }
    for name, stamps in pending.items():
        rendered = rig._rendered[name]
        if rendered < len(stamps) and stamps[rendered] <= device_us:
            raise RuntimeError(f"Controller would miss {name} samples not yet recorded at decision time")
