"""The closed loop, run against any source of device records.

The controller reads one thing: a RawSession, the device records firmware held
in memory at the decision time. Anything that can produce those records
lawfully can drive the loop:

  the twin's Rev B forward model                 models/physiology/experiment.py
  a recorded evidence bundle                     models/acquisition/recorded.py
  a live device behind the ingestion boundary    models/acquisition/live.py

A source owns acquisition and time; an actuator owns what a scheduled cue does.
The loop owns neither. It schedules evaluations on the device clock, hands the
controller exactly what the source held at each evaluation time, and passes
each scheduled cue to the actuator, so one decision procedure serves
simulation, replay, and hardware alike.

Two boundaries are enforced here instead of being trusted to callers:

  * Input contract. Before the first evaluation the source must provide every
    stream the pipeline reads (eda, ppg, imu, sync) with its columns and the
    descriptor constants the pipeline needs. A source that cannot is refused
    with InsufficientEvidence and its reasons. The loop never substitutes,
    imputes, or simulates a missing measurement.
  * Actuation targets. Cues may reach a SIMULATED actuator, or none (NONE:
    decisions are recorded and nothing is actuated). Hardware and human targets
    are refused: software in this repository grants no powered-bench or human
    actuation (hardware/review-gates.json). An OPERATOR_CHANNEL (a message to a
    person or an assistant) is refused for cues because its delivery is
    untimed and never physically observed: it cannot close a loop.

Sources and actuators describe themselves with Capabilities: what they can
actually supply, never what a caller hopes they supply.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Protocol

from .controller import ClosedLoopController, Evaluation
from .streams import STREAM_COLUMNS, RawSession

REVIEW_GATES = Path(__file__).resolve().parents[2] / "hardware/review-gates.json"

# Descriptor constants the pipeline and controller read, per stream.
REQUIRED_DESCRIPTOR_KEYS: dict[str, tuple[str, ...]] = {
    "eda": ("nominal_rate_hz", "adc_bits", "vref_v", "pga_gain", "excitation_v", "series_limit_ohm",
            "timestamp_minus_sample_center_us"),
    "ppg": ("nominal_rate_hz", "full_scale_counts"),
    "imu": ("nominal_rate_hz", "accel_lsb_per_g", "gyro_lsb_per_dps"),
    "sync": (),
}

ACTUATION_TARGETS = ("SIMULATED", "NONE", "HARDWARE_BENCH", "HUMAN_CONNECTED", "OPERATOR_CHANNEL")
CLOSED_LOOP_TARGETS = ("SIMULATED", "NONE")
_TARGET_AUTHORIZATION = {"HARDWARE_BENCH": "POWERED_BENCH_TEST", "HUMAN_CONNECTED": "HUMAN_CONNECTION"}


class InsufficientEvidence(ValueError):
    """The source cannot provide what the pipeline and controller read."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


class ActuationRefused(ValueError):
    """An actuator's target may not receive closed-loop cues from this repository."""


# ------------------------------------------------------------- capabilities
@dataclass(frozen=True)
class SignalCapability:
    """One stream a source can actually supply."""

    stream_id: str
    columns: tuple[str, ...]
    nominal_rate_hz: float | None
    provenance: str
    descriptor: tuple[tuple[str, float], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"stream_id": self.stream_id, "columns": list(self.columns), "nominal_rate_hz": self.nominal_rate_hz,
                "provenance": self.provenance, "descriptor": dict(self.descriptor)}


@dataclass(frozen=True)
class ActuatorCapability:
    """One output a source's environment offers, and the evidence each command leaves behind."""

    actuator_id: str
    target: str
    evidence: tuple[str, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if self.target not in ACTUATION_TARGETS:
            raise ValueError(f"unknown actuation target {self.target!r}")

    @property
    def closed_loop(self) -> bool:
        return self.target in CLOSED_LOOP_TARGETS

    def to_dict(self) -> dict[str, Any]:
        return {"actuator_id": self.actuator_id, "target": self.target, "evidence": list(self.evidence),
                "closed_loop": self.closed_loop, "description": self.description}


@dataclass(frozen=True)
class Capabilities:
    """What a source and its environment actually support, as discovered."""

    source: str
    connected: bool | None
    connection_state: str
    signals: tuple[SignalCapability, ...]
    actuators: tuple[ActuatorCapability, ...]
    sdk_version: str | None
    hardware: str
    authentication: str
    limitations: tuple[str, ...]

    @property
    def sampling(self) -> dict[str, float | None]:
        return {s.stream_id: s.nominal_rate_hz for s in self.signals}

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "connected": self.connected, "connection_state": self.connection_state,
                "signals": [s.to_dict() for s in self.signals], "actuators": [a.to_dict() for a in self.actuators],
                "sampling": self.sampling, "sdk_version": self.sdk_version, "hardware": self.hardware,
                "authentication": self.authentication, "limitations": list(self.limitations)}


# --------------------------------------------------------------- contracts
def _contract_problems(columns: dict[str, set[str]], descriptors: dict[str, set[str]]) -> list[str]:
    problems = []
    for name, needed in STREAM_COLUMNS.items():
        if name not in columns:
            problems.append(f"stream {name} is missing (the pipeline reads {', '.join(needed)})")
            continue
        absent = [c for c in needed if c not in columns[name]]
        if absent:
            problems.append(f"stream {name} lacks columns {absent}")
        if name not in descriptors:
            problems.append(f"stream {name} has no descriptor")
            continue
        absent = [k for k in REQUIRED_DESCRIPTOR_KEYS[name] if k not in descriptors[name]]
        if absent:
            problems.append(f"stream {name} descriptor lacks {absent}")
    return problems


def input_problems(session: RawSession) -> list[str]:
    """Why `session` cannot feed the pipeline and controller (empty: it can)."""
    return _contract_problems({name: set(s.columns) for name, s in session.streams.items()},
                              {name: set(d) for name, d in session.descriptors.items()})


def capability_problems(capabilities: Capabilities) -> list[str]:
    """The same contract judged from what a source declares, before any acquisition."""
    return _contract_problems({s.stream_id: set(s.columns) for s in capabilities.signals},
                              {s.stream_id: {k for k, _ in s.descriptor} for s in capabilities.signals})


def actuation_refusal(target: str, gates_path: Path = REVIEW_GATES) -> str | None:
    """Why closed-loop cues may not reach `target` from this repository (None: they may)."""
    if target in CLOSED_LOOP_TARGETS:
        return None
    if target == "OPERATOR_CHANNEL":
        return ("an operator channel cannot carry closed-loop cues: its delivery is untimed, never physically "
                "observed, and passes through systems CIRCLE does not control")
    if target not in _TARGET_AUTHORIZATION:
        return f"unknown actuation target {target!r}"
    needed = _TARGET_AUTHORIZATION[target]
    try:
        gates = json.loads(gates_path.read_text(encoding="utf-8"))["gates"]
        blocking = [g["id"] for g in gates if needed in g["blocks"] and g["status"] != "CLOSED"]
        state = (f"{len(blocking)} open review gates block it ({', '.join(blocking)})" if blocking else
                 "its review gates are closed, but authorization still needs human sign-off outside software")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        state = f"the review gates could not be read ({type(exc).__name__}), so this fails closed"
    return f"{target} actuation needs {needed}, which software in this repository never grants: {state}"


# ---------------------------------------------------------------- the loop
class HardwareSource(Protocol):
    """Anything that produces device records the way Rev B firmware would."""

    def capabilities(self) -> Capabilities:
        """What this source can actually supply."""

    def start(self) -> int | None:
        """Begin acquisition; the device time of the first protocol marker (the schedule anchor), or None."""

    def advance(self, device_time_us: int) -> bool:
        """Acquire through device_time_us; False once the source has nothing more to give."""

    def view(self, device_time_us: int) -> RawSession:
        """The device records held in memory at device_time_us."""

    def complete_through_us(self) -> float:
        """Every sample taken at or before this device time is recorded or declared lost (math.inf: all)."""

    def finish(self) -> RawSession:
        """Stop acquiring and return the complete record."""


class HardwareActuator(Protocol):
    """What a scheduled cue does."""

    target: str

    def execute(self, command_device_us: int, program: int, cue_index: int) -> Any:
        """Carry out one scheduled cue and return its outcome."""


class NullActuator:
    """Target NONE: collects the cues decisions would issue and actuates nothing (replay, dry runs)."""

    target = "NONE"

    def __init__(self) -> None:
        self.commands: list[tuple[int, int, int]] = []

    def execute(self, command_device_us: int, program: int, cue_index: int) -> None:
        self.commands.append((command_device_us, program, cue_index))


@dataclass
class LoopResult:
    raw: RawSession
    evaluations: list[Evaluation]
    outcomes: list[Any]
    controller: ClosedLoopController
    evaluation_end_us: int


def run_closed_loop(source: HardwareSource, actuator: HardwareActuator, controller: ClosedLoopController) -> LoopResult:
    """Evaluate on the device clock until the source ends; send each scheduled cue to the actuator.

    Refuses before acquiring anything if the actuator's target may not receive
    cues, and before the first evaluation if the source cannot satisfy the
    pipeline's input contract. At each evaluation time T the source must hold
    every sample taken at or before the input cutoff (T - decision margin);
    otherwise the controller would decide on a record that later grows
    underneath it, so the loop stops instead of deciding.
    """
    refusal = actuation_refusal(actuator.target)
    if refusal:
        raise ActuationRefused(refusal)
    c = controller.config
    anchor = source.start()
    problems = input_problems(source.view(anchor if anchor is not None else 0))
    if anchor is None:
        problems.append("no protocol marker anchors the evaluation schedule")
    if problems:
        raise InsufficientEvidence(problems)
    period = int(round(c.evaluation_period_s * 1e6))
    margin = int(round(c.decision_margin_s * 1e6))
    evaluations: list[Evaluation] = []
    outcomes: list[Any] = []
    t_dev = anchor + period
    last_evaluated = anchor
    while source.advance(t_dev):
        session = source.view(t_dev)
        complete = source.complete_through_us()
        if complete < t_dev - margin:
            raise RuntimeError(f"Controller would miss samples not yet recorded at decision time "
                               f"(complete through {complete} us, input cutoff {t_dev - margin} us)")
        evaluation = controller.evaluate(session, t_dev)
        last_evaluated = t_dev
        if evaluation is not None:
            evaluations.append(evaluation)
            for cue_us in evaluation.cues_device_us:
                cue_number = _cue_number(evaluations, evaluation.program, cue_us)
                outcomes.append(actuator.execute(cue_us, evaluation.program or 0, cue_number))
        t_dev += period
    return LoopResult(source.finish(), evaluations, outcomes, controller, last_evaluated)


def _cue_number(evaluations: list[Evaluation], program: int | None, cue_us: int) -> int:
    cues = sorted(cue for ev in evaluations if ev.program == program for cue in ev.cues_device_us)
    return cues.index(cue_us)
