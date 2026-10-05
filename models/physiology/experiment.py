"""Run a closed-loop CIRCLE session against the physiological twin.

The loop is strictly causal. At each controller evaluation time T (device
clock) the twin has generated physiology only up to T, the rig has recorded
only samples whose physical instant precedes T - 0.5 s, the controller is
handed only samples whose availability time (FIFO/DRDY read completion) is
<= T, and it uses only samples taken at least decision_margin before T. Cues it schedules reach the
body through the haptic hardware model at their physical onset time.

The twin and its Rev B forward model are one source of device records
(TwinSource) and the haptic chain is one actuator (TwinHapticActuator); the
loop itself is models/physiology/loop.py, shared with recorded and live sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np

from .controller import ClosedLoopController, ControllerConfig, Evaluation
from .loop import ActuatorCapability, Capabilities, SignalCapability, run_closed_loop
from .pipeline import Analysis, analyze
from .sensors import HapticOutcome, RigConfig, SensorRig, descriptors
from .streams import STREAM_COLUMNS, RawSession
from .twin import HapticCue, PhysiologyTwin, TwinConfig

ACQUISITION_LAG_S = 0.5


@dataclass(frozen=True)
class SessionConfig:
    twin: TwinConfig = field(default_factory=TwinConfig)
    rig: RigConfig = field(default_factory=RigConfig)
    controller: ControllerConfig = field(default_factory=ControllerConfig)
    actuate: bool = True
    scenario: str = "clean"
    # Session-header flags naming how records reached the controller when not
    # directly from the forward model (e.g. through the live ingestion boundary).
    acquisition: tuple[str, ...] = ()

    @property
    def session_id(self) -> str:
        return f"TWIN-{self.scenario.upper()}-S{self.twin.seed}-{'ACTIVE' if self.actuate else 'SHAM'}"


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
    controller_baseline_decided_us: int
    evaluation_end_us: int
    twin: PhysiologyTwin
    rig: SensorRig

    def truth(self) -> dict[str, Any]:
        """Hidden ground truth (twin physiology + exact timing). Scoring only."""
        truth = self.twin.truth()
        timing = self.rig.timing_truth()
        truth["timing"] = {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in timing.items()}
        return truth


class TwinSource:
    """The twin rendered through the Rev B forward model: a simulated source of device records.

    Time is true seconds inside and device microseconds outside. Advancing to
    device time T logs the protocol markers due by T, generates physiology up
    to T, and records every sample whose physical instant precedes T by
    ACQUISITION_LAG_S.
    """

    def __init__(self, twin: PhysiologyTwin, rig: SensorRig) -> None:
        self.twin, self.rig = twin, rig
        self._markers = sorted([(p.start_s, f"PHASE_START:{p.name}") for p in twin.config.phases]
                               + [(t, "STIMULUS") for t in twin.stimuli])
        self._next_marker = 0

    def _log_markers_through(self, t_true: float) -> None:
        while self._next_marker < len(self._markers) and self._markers[self._next_marker][0] <= t_true:
            self.rig.log_protocol_marker(self._markers[self._next_marker][1], self._markers[self._next_marker][0])
            self._next_marker += 1

    def capabilities(self) -> Capabilities:
        def rate(d: dict[str, float]) -> float:
            return d["nominal_rate_hz"] if "nominal_rate_hz" in d else 1.0 / d["nominal_period_s"]

        return Capabilities(
            source="circle-twin", connected=None, connection_state="NOT_APPLICABLE_SIMULATED",
            signals=tuple(SignalCapability(name, STREAM_COLUMNS[name], rate(d), "SIMULATED", tuple(sorted(d.items())))
                          for name, d in descriptors(self.rig.config).items()),
            actuators=(ActuatorCapability("haptic_lra", "SIMULATED",
                                          ("HAPTIC_COMMAND", "HAPTIC_ELECTRICAL_ONSET", "HAPTIC_PHYSICAL_OBSERVATION"),
                                          "DRV2605L + LRA forward model; TLV3201 current edge; IMU-observed vibration"),),
            sdk_version=None, hardware="Rev B forward model (no hardware built)", authentication="NOT_APPLICABLE",
            limitations=("The twin is phenomenological and not fitted to any person.",
                         "Sensor timing, oscillator, and latency parameters are assumptions until measured.",
                         "The paced-breathing response is assumed by the twin."))

    def start(self) -> int:
        self._log_markers_through(0.0)
        return min(e.device_time_us for e in self.rig.events)

    def advance(self, device_time_us: int) -> bool:
        t_true = float(self.rig.clock.to_true_s(device_time_us))
        if t_true > self.twin.config.duration_s - ACQUISITION_LAG_S:
            return False
        self._log_markers_through(t_true)
        self.twin.advance_to(t_true)
        self.rig.acquire_until(t_true - ACQUISITION_LAG_S)
        return True

    def view(self, device_time_us: int) -> RawSession:
        # The controller sees only what firmware held in memory at device_time_us.
        return self.rig.raw_session().until(device_time_us)

    def complete_through_us(self) -> float:
        """Causality guard: every sample stamped at or before this device time is already recorded."""
        bound = math.inf
        for name, stamps in (("eda", self.rig.eda_dev), ("ppg", self.rig.ppg_dev), ("imu", self.rig.imu_dev)):
            rendered = self.rig._rendered[name]
            if rendered < len(stamps):
                bound = min(bound, int(stamps[rendered]) - 1)
        return bound

    def finish(self) -> RawSession:
        duration = self.twin.config.duration_s
        self._log_markers_through(duration)
        self.twin.advance_to(duration)
        self.rig.acquire_until(duration - ACQUISITION_LAG_S)
        return self.rig.raw_session()


class TwinHapticActuator:
    """The Rev B haptic chain (DRV2605L, LRA, TLV3201) driving the twin.

    An actuated cue reaches the twin at its physical onset; a sham cue is
    commanded and logged but never actuated.
    """

    target = "SIMULATED"

    def __init__(self, twin: PhysiologyTwin, rig: SensorRig, actuate: bool) -> None:
        self.twin, self.rig, self.actuate = twin, rig, actuate
        self.outcomes: list[HapticOutcome] = []

    def execute(self, command_device_us: int, program: int, cue_index: int) -> HapticOutcome:
        outcome = self.rig.command_haptic(command_device_us, self.actuate, program, cue_index)
        self.outcomes.append(outcome)
        if self.actuate:
            program_start = min(o.truth["physical_onset_true_s"] for o in self.outcomes
                                if o.truth["program"] == program and "physical_onset_true_s" in o.truth)
            self.twin.add_cues([HapticCue(program, cue_index, outcome.truth["physical_onset_true_s"], program_start, True)])
        return outcome


def session_run(config: SessionConfig, result: Any, twin: PhysiologyTwin, rig: SensorRig) -> SessionRun:
    """Package a loop result over the twin as a SessionRun (the record the evidence export reads)."""
    controller = result.controller
    if controller.baseline is None or controller.baseline_window_us is None:
        raise ValueError("Session ended before the controller baseline could be established")
    return SessionRun(config, result.raw, analyze(result.raw), result.evaluations, result.outcomes,
                      dict(controller.baseline), controller.baseline_window_us, list(controller.baseline_ranges),
                      int(controller.baseline_decided_us or 0), result.evaluation_end_us, twin, rig)


def run_session(config: SessionConfig | None = None) -> SessionRun:
    config = config or SessionConfig()
    twin = PhysiologyTwin(config.twin)
    rig = SensorRig(twin, config.rig)
    result = run_closed_loop(TwinSource(twin, rig), TwinHapticActuator(twin, rig, config.actuate),
                             ClosedLoopController(config.controller))
    return session_run(config, result, twin, rig)
