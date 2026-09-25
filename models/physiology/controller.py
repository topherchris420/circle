"""Causal closed-loop controller: sustained arousal -> haptic paced-breathing cues.

At each evaluation time T (device clock) the controller reads only raw
samples with device_time_us <= T - decision_margin. Every decision is a pure
function of those samples, the protocol markers logged before T, and the
controller's own earlier state. The online loop and an offline replay of the
exported raw bundle therefore produce identical decisions; tools audit this.

Arousal index (dimensionless):
    0.45 * z(HR) + 0.35 * z(SCL) + 0.20 * z(SCR rate)
with z-scores against the REST_BASELINE phase and conservative SD floors.
The index is an engineering trigger, not a validated psychological measure.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any

import numpy as np

from .dsp import contiguous_runs
from .pipeline import analyze_eda, analyze_motion, detect_beats
from .streams import RawSession

CONTROLLER_VERSION = "1.0.0"


@dataclass(frozen=True)
class ControllerConfig:
    evaluation_period_s: float = 5.0
    decision_margin_s: float = 1.0
    feature_window_s: float = 40.0
    hr_window_s: float = 20.0
    scr_window_s: float = 30.0
    scl_window_s: float = 10.0
    baseline_phase: str = "REST_BASELINE"
    arm_phase: str = "RECOVERY"
    baseline_skip_s: float = 10.0
    trigger_index: float = 2.0
    trigger_consecutive: int = 2
    release_index: float = 1.0
    release_consecutive: int = 2
    min_program_s: float = 60.0
    max_program_s: float = 150.0
    refractory_s: float = 60.0
    max_programs: int = 2
    cue_period_s: float = 10.0
    compute_latency_us: int = 850
    min_beat_coverage: float = 0.7
    max_motion_fraction: float = 0.2
    weight_hr: float = 0.45
    weight_scl: float = 0.35
    weight_scr: float = 0.20
    hr_sd_floor_bpm: float = 2.0
    scl_sd_floor_us: float = 0.25
    scr_rate_floor_per_min: float = 2.0

    def __post_init__(self) -> None:
        positive = ("evaluation_period_s", "decision_margin_s", "feature_window_s", "hr_window_s",
                    "scr_window_s", "scl_window_s", "min_program_s", "max_program_s", "cue_period_s")
        for name in positive:
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if max(self.hr_window_s, self.scr_window_s, self.scl_window_s) > self.feature_window_s:
            raise ValueError("Feature sub-windows must fit inside feature_window_s")
        if self.release_index >= self.trigger_index:
            raise ValueError("release_index must be below trigger_index (hysteresis)")
        if self.min_program_s > self.max_program_s:
            raise ValueError("min_program_s cannot exceed max_program_s")
        if self.decision_margin_s < 0.6:
            raise ValueError("decision_margin_s must cover PPG FIFO latency (>= 0.6 s)")

    def numeric_payload(self) -> dict[str, float]:
        return {k: float(v) for k, v in asdict(self).items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


@dataclass
class Evaluation:
    device_time_us: int
    window_start_us: int
    window_end_us: int
    features: dict[str, float]
    state: str
    action: str | None = None
    decision_id: str | None = None
    program: int | None = None
    cues_device_us: list[int] = field(default_factory=list)
    source_sequence_ranges: list[dict[str, Any]] = field(default_factory=list)

    def comparable(self) -> tuple:
        return (self.device_time_us, self.window_start_us, self.window_end_us,
                tuple(sorted(self.features.items())), self.state, self.action, self.decision_id,
                self.program, tuple(self.cues_device_us))


def _window_ranges(session: RawSession, t0: int, t1: int) -> list[dict[str, Any]]:
    ranges = []
    for name in ("eda", "ppg", "imu"):
        w = session.streams[name].window(t0, t1)
        ranges.extend({"stream_id": name, "first_sequence": int(w.sequence[a]), "last_sequence": int(w.sequence[b - 1])}
                      for a, b in contiguous_runs(w.sequence))
    return ranges


def window_features(session: RawSession, t0_us: int, t1_us: int, config: ControllerConfig) -> dict[str, float]:
    """Physiological features from raw samples inside [t0_us, t1_us] only."""
    d = session.descriptors
    end_s = t1_us / 1e6
    imu = session.streams["imu"].window(t0_us, t1_us)
    motion = analyze_motion(imu, d["imu"])
    episodes = motion["episodes"]
    beats = detect_beats(session.streams["ppg"].window(t0_us, t1_us), d["ppg"], episodes)
    eda = analyze_eda(session.streams["eda"].window(t0_us, t1_us), d["eda"], episodes)
    out: dict[str, float] = {}
    hr_from = end_s - config.hr_window_s
    valid = beats["ibi_valid"] & (beats["ibi_end_s"] >= hr_from) & (beats["ibi_start_s"] >= t0_us / 1e6)
    covered = float(np.sum(beats["ibi_s"][valid])) if valid.any() else 0.0
    out["beat_coverage"] = round(min(1.0, covered / config.hr_window_s), 6)
    if valid.sum() >= 3:
        out["hr_bpm"] = round(float(60.0 / np.mean(beats["ibi_s"][valid])), 6)
    if len(eda["t_s"]):
        recent = eda["t_s"] >= end_s - config.scl_window_s
        if recent.any():
            out["scl_us"] = round(float(np.mean(eda["tonic_us"][recent])), 6)
        scr = [s for s in eda["scrs"] if s["onset_s"] >= end_s - config.scr_window_s and not s["motion_confounded"]]
        out["scr_rate_per_min"] = round(len(scr) * 60.0 / config.scr_window_s, 6)
    if len(motion["t_s"]):
        recent = motion["t_s"] >= hr_from
        out["motion_fraction"] = round(float(np.mean(motion["flag"][recent])) if recent.any() else 0.0, 6)
    else:
        out["motion_fraction"] = 1.0
    return out


class ClosedLoopController:
    """Stateful, deterministic decision policy over raw device data."""

    def __init__(self, config: ControllerConfig | None = None) -> None:
        self.config = config or ControllerConfig()
        self.baseline: dict[str, float] | None = None
        self.baseline_ranges: list[dict[str, Any]] = []
        self.baseline_window_us: tuple[int, int] | None = None
        self.state = "IDLE"
        self.trigger_count = 0
        self.release_count = 0
        self.programs = 0
        self.program_start_us: int | None = None
        self.program_anchor_us: int | None = None
        self.next_cue = 0
        self.refractory_until_us: int | None = None

    # ------------------------------------------------------------ baseline
    def _compute_baseline(self, session: RawSession, bounds: tuple[int, int]) -> None:
        c = self.config
        t0 = bounds[0] + int(c.baseline_skip_s * 1e6)
        t1 = bounds[1] - int(c.decision_margin_s * 1e6)
        d = session.descriptors
        motion = analyze_motion(session.streams["imu"].window(t0, t1), d["imu"])
        beats = detect_beats(session.streams["ppg"].window(t0, t1), d["ppg"], motion["episodes"])
        eda = analyze_eda(session.streams["eda"].window(t0, t1), d["eda"], motion["episodes"])
        hr_windows, scl_windows = [], []
        step = int(c.scl_window_s * 1e6)
        for w0 in range(t0, t1 - step + 1, step):
            a, b = w0 / 1e6, (w0 + step) / 1e6
            valid = beats["ibi_valid"] & (beats["ibi_end_s"] >= a) & (beats["ibi_end_s"] < b)
            if valid.sum() >= 3:
                hr_windows.append(60.0 / float(np.mean(beats["ibi_s"][valid])))
            e_in = (eda["t_s"] >= a) & (eda["t_s"] < b)
            if e_in.any():
                scl_windows.append(float(np.mean(eda["tonic_us"][e_in])))
        if len(hr_windows) < 2 or len(scl_windows) < 2:
            raise ValueError("Baseline phase does not contain enough clean data for the controller")
        duration_min = (t1 - t0) / 60e6
        clean_scr = [s for s in eda["scrs"] if not s["motion_confounded"]]
        self.baseline = {
            "hr_bpm": round(float(np.mean(hr_windows)), 6),
            "hr_sd_bpm": round(max(float(np.std(hr_windows, ddof=1)), c.hr_sd_floor_bpm), 6),
            "scl_us": round(float(np.mean(scl_windows)), 6),
            "scl_sd_us": round(max(float(np.std(scl_windows, ddof=1)), c.scl_sd_floor_us), 6),
            "scr_rate_per_min": round(len(clean_scr) / duration_min, 6),
            "windows": float(len(hr_windows)),
        }
        self.baseline_window_us = (t0, t1)
        self.baseline_ranges = _window_ranges(session, t0, t1)

    # ------------------------------------------------------------ evaluate
    def evaluate(self, session: RawSession, t_us: int) -> Evaluation | None:
        """One scheduled evaluation at device time t_us (None before a baseline exists)."""
        c = self.config
        markers = {e.kind.split(":", 1)[1]: e.device_time_us for e in session.events_of("PHASE_START:") if e.device_time_us <= t_us}
        ordered = sorted(markers.items(), key=lambda kv: kv[1])
        if c.baseline_phase not in markers:
            return None
        names = [name for name, _ in ordered]
        i = names.index(c.baseline_phase)
        if i + 1 >= len(ordered):
            return None  # baseline phase has not ended yet
        margin = int(c.decision_margin_s * 1e6)
        end_us = t_us - margin
        if self.baseline is None:
            self._compute_baseline(session, (ordered[i][1], ordered[i + 1][1]))
        start_us = end_us - int(c.feature_window_s * 1e6)
        features = window_features(session, start_us, end_us, c)
        b = self.baseline
        assert b is not None
        z_hr = (features["hr_bpm"] - b["hr_bpm"]) / b["hr_sd_bpm"] if "hr_bpm" in features else float("nan")
        z_scl = (features["scl_us"] - b["scl_us"]) / b["scl_sd_us"] if "scl_us" in features else float("nan")
        scr_den = max(b["scr_rate_per_min"], c.scr_rate_floor_per_min)
        z_scr = (features["scr_rate_per_min"] - b["scr_rate_per_min"]) / scr_den if "scr_rate_per_min" in features else float("nan")
        quality_ok = (features["beat_coverage"] >= c.min_beat_coverage and features["motion_fraction"] <= c.max_motion_fraction
                      and all(math.isfinite(z) for z in (z_hr, z_scl, z_scr)))
        if all(math.isfinite(z) for z in (z_hr, z_scl, z_scr)):
            index = c.weight_hr * z_hr + c.weight_scl * z_scl + c.weight_scr * z_scr
            features.update({"hr_z": round(z_hr, 6), "scl_z": round(z_scl, 6), "scr_z": round(z_scr, 6),
                             "arousal_index": round(index, 6)})
        else:
            index = float("nan")
        features["quality_ok"] = 1.0 if quality_ok else 0.0
        armed = c.arm_phase in markers
        features["armed"] = 1.0 if armed else 0.0
        evaluation = Evaluation(t_us, start_us, end_us, features, self.state,
                                source_sequence_ranges=_window_ranges(session, start_us, end_us))
        self._step(evaluation, index, quality_ok, armed, t_us)
        return evaluation

    def _step(self, ev: Evaluation, index: float, quality_ok: bool, armed: bool, t_us: int) -> None:
        c = self.config
        if self.state == "REFRACTORY" and self.refractory_until_us is not None and t_us >= self.refractory_until_us:
            self.state = "IDLE"
            self.trigger_count = 0
        if self.state == "IDLE":
            if not armed:
                pass
            elif not quality_ok:
                ev.action = "HOLD_QUALITY"
            else:
                self.trigger_count = self.trigger_count + 1 if index >= c.trigger_index else 0
                if self.trigger_count >= c.trigger_consecutive and self.programs < c.max_programs:
                    self.programs += 1
                    self.state = "PROGRAM"
                    self.release_count = 0
                    self.program_start_us = t_us
                    self.program_anchor_us = t_us + c.compute_latency_us
                    self.next_cue = 0
                    ev.action = "START_PACED_BREATHING"
                    ev.decision_id = f"PBR-{self.programs}"
                    ev.program = self.programs
        elif self.state == "PROGRAM":
            assert self.program_anchor_us is not None
            elapsed = (t_us - self.program_anchor_us) / 1e6
            stop_reason = None
            if elapsed >= c.max_program_s:
                stop_reason = "STOP_MAX_DURATION"
            elif quality_ok and elapsed >= c.min_program_s:
                self.release_count = self.release_count + 1 if index < c.release_index else 0
                if self.release_count >= c.release_consecutive:
                    stop_reason = "STOP_RELEASED"
            if stop_reason:
                ev.action = stop_reason
                ev.decision_id = f"PBR-{self.programs}-STOP"
                ev.program = self.programs
                self.state = "REFRACTORY"
                self.refractory_until_us = t_us + int(c.refractory_s * 1e6)
        if self.state == "PROGRAM":
            assert self.program_anchor_us is not None
            ev.program = self.programs
            horizon = t_us + int(c.evaluation_period_s * 1e6) + c.compute_latency_us
            period = int(c.cue_period_s * 1e6)
            while self.program_anchor_us + self.next_cue * period < horizon:
                ev.cues_device_us.append(self.program_anchor_us + self.next_cue * period)
                self.next_cue += 1
        ev.state = self.state


def evaluation_times(session: RawSession, config: ControllerConfig, end_us: int) -> list[int]:
    """Deterministic evaluation schedule anchored on the first protocol marker."""
    markers = sorted(e.device_time_us for e in session.events_of("PHASE_START:"))
    if not markers:
        return []
    period = int(round(config.evaluation_period_s * 1e6))
    return list(range(markers[0] + period, end_us + 1, period))


def replay(session: RawSession, config: ControllerConfig, end_us: int) -> list[Evaluation]:
    """Re-derive every decision from a recorded raw session.

    end_us is the recorded last evaluation time; the schedule itself is
    re-derived from the first protocol marker and the evaluation period.
    """
    controller = ClosedLoopController(config)
    out = []
    for t in evaluation_times(session, config, end_us):
        ev = controller.evaluate(session.until(t), t)
        if ev is not None:
            out.append(ev)
    return out
