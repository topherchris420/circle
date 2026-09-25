"""Seeded, causal physiological twin with explicit ground truth.

The twin is a phenomenological model. It exists to give the CIRCLE signal
pipeline an input whose answers are known, so that beat detection, SCR
detection, timing reconstruction, and closed-loop behavior can be scored. It is
not a validated model of any person, and agreement with it is not evidence
about human physiology.

Mechanisms (each is a published, simplified model):
  * Latent arousal: first-order tracking of a protocol drive with asymmetric
    rise/decay time constants and diffusion noise.
  * Heartbeats: integral pulse frequency modulation (IPFM; Rompelman 1977,
    Mateo & Laguna 2000) of an instantaneous heart rate built from arousal,
    respiratory sinus arrhythmia (RSA), a 0.095 Hz Mayer wave, and
    Ornstein-Uhlenbeck noise. RSA amplitude grows near 0.1 Hz breathing, the
    resonance-frequency effect used in HRV biofeedback (Lehrer & Gevirtz 2014).
  * Pulse wave: per-beat asymmetric systolic wave plus a dicrotic wave,
    arriving one pulse arrival time (PAT) after each beat. Sympathetic
    activation shortens PAT and lowers amplitude (vasoconstriction).
  * Electrodermal activity: tonic level tracking arousal plus skin
    conductance responses shaped by a Bateman bi-exponential (Benedek &
    Kaernbach 2010), spontaneous (rate rises with arousal) and stimulus-locked
    (1.4-2.2 s latency).
  * SpO2: first-order oxygen store with an 11 s circulatory delay; a scripted
    breath-hold produces a small, delayed desaturation.
  * Motion: scripted limb-motion episodes (band-limited 0.8-4 Hz), a posture
    shift, and physiological tremor, coupled into PPG intensity and EDA
    electrode contact as artifacts.
  * Haptic paced breathing (closed loop): cues entrain respiration toward the
    cue rate with a phase-coupling term; entrainment speeds arousal decay.
    This response is an ASSUMPTION of the twin, not a finding.

All random numbers are drawn up front per grid step, per beat, and per
stimulus. Two runs with the same seed therefore share every noise sample and
differ only where the intervention changes the physiology (common random
numbers), which makes the sham arm a true counterfactual.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any

import numpy as np

from .dsp import fir_bandpass, filter_zero_phase

GRID_DT_S = 0.01
KINEMATIC_RATE_HZ = 400.0


@dataclass(frozen=True)
class ProtocolPhase:
    name: str
    start_s: float
    end_s: float


@dataclass(frozen=True)
class MotionEpisode:
    label: str
    start_s: float
    duration_s: float
    intensity_g: float


DEFAULT_PHASES = (
    ProtocolPhase("REST_BASELINE", 0.0, 60.0),
    ProtocolPhase("BREATH_HOLD", 60.0, 90.0),
    ProtocolPhase("SETTLE", 90.0, 110.0),
    ProtocolPhase("STRESSOR", 110.0, 230.0),
    ProtocolPhase("RECOVERY", 230.0, 360.0),
)

DEFAULT_MOTION = (
    MotionEpisode("REACH", 24.0, 4.0, 0.30),
    MotionEpisode("FIDGET", 158.0, 5.0, 0.38),
    MotionEpisode("POSTURE_SHIFT", 318.0, 3.5, 0.26),
)

PHASE_DRIVE = {
    "REST_BASELINE": 0.10,
    "BREATH_HOLD": 0.30,
    "SETTLE": 0.15,
    "STRESSOR": 0.88,
    "RECOVERY": 0.10,
}


@dataclass(frozen=True)
class PhysiologyParams:
    resting_hr_bpm: float = 64.0
    arousal_hr_gain_bpm: float = 24.0
    rsa_amplitude_bpm: float = 3.2
    rsa_resonance_gain: float = 2.4
    mayer_amplitude_bpm: float = 1.4
    resting_resp_rate_hz: float = 0.235
    resting_scl_us: float = 4.0
    spo2_baseline_pct: float = 97.6
    breath_hold_desaturation_pct: float = 3.4
    pace_rate_hz: float = 0.1
    pace_adherence: float = 0.85


@dataclass(frozen=True)
class TwinConfig:
    seed: int = 7
    duration_s: float = 360.0
    phases: tuple[ProtocolPhase, ...] = DEFAULT_PHASES
    motion: tuple[MotionEpisode, ...] = DEFAULT_MOTION
    stimulus_interval_s: float = 12.0
    physiology: PhysiologyParams = field(default_factory=PhysiologyParams)

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed < 2**32:
            raise ValueError("seed must be an integer in [0, 2**32)")
        if not math.isfinite(self.duration_s) or not 20.0 <= self.duration_s <= 3600.0:
            raise ValueError("duration_s must be within [20, 3600] seconds")
        previous_end = 0.0
        for phase in self.phases:
            if not phase.name or phase.name not in PHASE_DRIVE:
                raise ValueError(f"Unknown protocol phase: {phase.name!r}")
            if not (math.isfinite(phase.start_s) and math.isfinite(phase.end_s)) or phase.end_s <= phase.start_s:
                raise ValueError("Protocol phases must have finite, increasing bounds")
            if not math.isclose(phase.start_s, previous_end):
                raise ValueError("Protocol phases must be contiguous from t = 0")
            previous_end = phase.end_s
        if self.phases and self.phases[-1].end_s < self.duration_s:
            raise ValueError("Protocol phases must cover the full session")
        for episode in self.motion:
            if episode.start_s < 0 or episode.duration_s <= 0 or episode.start_s + episode.duration_s > self.duration_s:
                raise ValueError(f"Motion episode {episode.label} must lie inside the session")
            if not 0 < episode.intensity_g <= 2.0:
                raise ValueError("Motion intensity must be within (0, 2] g")
        if not math.isfinite(self.stimulus_interval_s) or self.stimulus_interval_s < 6.0:
            raise ValueError("stimulus_interval_s must be at least 6 s")

    def phase_at(self, t_s: float) -> str:
        for phase in self.phases:
            if phase.start_s <= t_s < phase.end_s:
                return phase.name
        return self.phases[-1].name


@dataclass(frozen=True)
class HapticCue:
    """A paced-breathing cue as experienced by the body (true time, seconds)."""
    program: int
    index: int
    perceived_s: float
    program_start_s: float
    actuated: bool


def _smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


class PhysiologyTwin:
    """Advance latent physiology causally; render continuous signals on demand."""

    def __init__(self, config: TwinConfig) -> None:
        self.config = config
        self.params = config.physiology
        n = int(round(config.duration_s / GRID_DT_S)) + 1
        self.n_grid = n
        self.t_grid = np.arange(n) * GRID_DT_S
        seeds = np.random.SeedSequence(config.seed).spawn(6)
        latent_rng, scr_rng, beat_rng, stim_rng, motion_rng, phase_rng = (np.random.default_rng(s) for s in seeds)

        # Pre-drawn noise: identical across arms that share a seed.
        self._latent_noise = latent_rng.standard_normal((n, 5))
        self._scr_uniform = scr_rng.random(n)
        self._scr_normal = scr_rng.standard_normal(n)
        self._scr_shape = scr_rng.uniform(-1.0, 1.0, (n, 2))
        max_beats = int(config.duration_s * 4) + 16
        self._beat_noise = beat_rng.standard_normal((max_beats, 3))
        self._mayer_phase = float(phase_rng.uniform(0, 2 * math.pi))

        self.drive = np.array([PHASE_DRIVE[config.phase_at(t)] for t in self.t_grid])
        hold = np.array([config.phase_at(t) == "BREATH_HOLD" for t in self.t_grid], dtype=float)
        self._hold_raw = hold

        self.stimuli = self._schedule_stimuli(stim_rng)
        self._stimulus_draws = stim_rng.random((len(self.stimuli), 3))
        self._stimulus_normals = stim_rng.standard_normal((len(self.stimuli), 3))
        self._build_kinematics(motion_rng)

        # Latent state on the grid (filled progressively).
        self.arousal = np.zeros(n)
        self.resp_phase = np.zeros(n)
        self.resp_amp = np.zeros(n)
        self.resp_rate_hz = np.zeros(n)
        self.hr_bpm = np.zeros(n)
        self.spo2 = np.zeros(n)
        self.scl = np.zeros(n)
        self.entrainment = np.zeros(n)
        self.hold = np.zeros(n)
        self._n = 0
        self._state = {
            "a": PHASE_DRIVE[config.phase_at(0.0)], "f_ou": 0.0, "hr_ou": 0.0,
            "s_ou": 0.0, "scl_ou": 0.0, "phi": 0.0, "cardiac": 0.35, "w": 0.0,
            "hold": 0.0, "boost": 0.0, "spo2": self.params.spo2_baseline_pct,
            "scl": self.params.resting_scl_us * (1 + 0.42 * PHASE_DRIVE[config.phase_at(0.0)]),
        }
        self.beats: list[dict[str, float]] = []
        self.scrs: list[dict[str, Any]] = []
        self._next_stimulus = 0
        self._pending_stimulus_scrs: list[tuple[float, int]] = []
        self._cues: list[HapticCue] = []

    # ------------------------------------------------------------------ setup
    def _schedule_stimuli(self, rng: np.random.Generator) -> list[float]:
        times: list[float] = []
        for phase in self.config.phases:
            if phase.name != "STRESSOR":
                continue
            t = phase.start_s + 6.0
            while t < phase.end_s - 4.0:
                times.append(round(t, 3))
                t += self.config.stimulus_interval_s + rng.uniform(-3.0, 3.0)
        return times

    def _build_kinematics(self, rng: np.random.Generator) -> None:
        fs = KINEMATIC_RATE_HZ
        n = int(round(self.config.duration_s * fs)) + 1
        t = np.arange(n) / fs
        self.k_t = t
        accel = np.zeros((n, 3))
        gyro = np.zeros((n, 3))
        band = fir_bandpass(0.8, 4.0, fs, 801)
        roll = np.full(n, math.radians(8.0))
        pitch = np.full(n, math.radians(-18.0))
        ppg_dc_shift = np.zeros(n)
        for episode in self.config.motion:
            start, stop = episode.start_s, episode.start_s + episode.duration_s
            ramp = 0.35
            env = _smoothstep((t - start) / ramp) * _smoothstep((stop - t) / ramp)
            span = (t > start - 3) & (t < stop + 3)
            for target, scale in ((accel, episode.intensity_g), (gyro, episode.intensity_g * 190.0)):
                noise = rng.standard_normal((span.sum(), 3))
                shaped = np.column_stack([filter_zero_phase(noise[:, i], band) for i in range(3)])
                inside = env[span] > 0.5
                rms = np.sqrt(np.mean(shaped[inside] ** 2, axis=0)) if inside.any() else np.ones(3)
                target[span] += shaped / np.maximum(rms, 1e-12) * scale * env[span, None] / math.sqrt(3)
            if episode.label == "POSTURE_SHIFT":
                s = _smoothstep((t - start) / episode.duration_s)
                roll = roll + s * math.radians(-20.0)
                pitch = pitch + s * math.radians(-17.0)
                ppg_dc_shift = ppg_dc_shift - 0.025 * s
        tremor_phase = rng.uniform(0, 2 * math.pi, 3)
        tremor = 0.0012 * np.sin(2 * math.pi * 9.5 * t[:, None] + tremor_phase)
        self.k_motion_accel = accel
        self.k_gyro = gyro
        self.k_roll = roll
        self.k_pitch = pitch
        self.k_tremor = tremor
        axis = np.array([0.6, 0.3, 0.74]) / np.linalg.norm([0.6, 0.3, 0.74])
        contact = np.array([0.2, 0.9, 0.4]) / np.linalg.norm([0.2, 0.9, 0.4])
        self.k_ppg_motion = 0.045 * accel @ axis + ppg_dc_shift
        self.k_eda_artifact = 0.42 * accel @ contact

    # --------------------------------------------------------------- dynamics
    @property
    def generated_until_s(self) -> float:
        return (self._n - 1) * GRID_DT_S if self._n else -GRID_DT_S

    def add_cues(self, cues: list[HapticCue]) -> None:
        for cue in cues:
            if cue.perceived_s <= self.generated_until_s:
                raise ValueError("A cue cannot be delivered into already generated physiology")
        self._cues.extend(cues)
        self._cues.sort(key=lambda c: c.perceived_s)

    def _active_cue(self, t: float) -> HapticCue | None:
        period = 1.0 / self.params.pace_rate_hz
        latest = None
        for cue in self._cues:
            if cue.perceived_s > t:
                break
            if cue.actuated:
                latest = cue
        if latest is not None and t - latest.perceived_s <= 1.5 * period:
            return latest
        return None

    def advance_to(self, t_end_s: float) -> None:
        """Generate latent physiology on the grid up to and including t_end_s."""
        p = self.params
        s = self._state
        dt = GRID_DT_S
        last = min(self.n_grid - 1, int(math.floor(t_end_s / dt + 1e-9)))
        mayer_w = 2 * math.pi * 0.095
        for k in range(self._n, last + 1):
            t = k * dt
            xi = self._latent_noise[k]
            drive = self.drive[k]
            # Stimulus bumps and scheduled stimulus-locked SCRs.
            while self._next_stimulus < len(self.stimuli) and self.stimuli[self._next_stimulus] <= t:
                i = self._next_stimulus
                s["a"] += 0.06
                u_respond, u_latency, _ = self._stimulus_draws[i]
                if u_respond < 0.9:
                    self._pending_stimulus_scrs.append((self.stimuli[i] + 1.4 + 0.8 * u_latency, i))
                self._next_stimulus += 1

            cue = self._active_cue(t)
            w_target = p.pace_adherence if cue is not None else 0.0
            tau_w = 6.0 if w_target > s["w"] else 12.0
            s["w"] += (w_target - s["w"]) / tau_w * dt
            w = s["w"]

            a = s["a"]
            target = drive - 0.08 * w
            tau = 12.0 if target > a else 40.0 / (1.0 + 1.2 * w)
            a += (target - a) / tau * dt + 0.03 * math.sqrt(2 * dt / 20.0) * xi[0]
            a = max(0.0, a)
            s["a"] = a
            a_c = min(a, 1.0)

            # Breath-hold gating with smooth onset/offset and recovery breaths.
            hold_target = self._hold_raw[k]
            if hold_target < s["hold"] and s["hold"] > 0.5:
                s["boost"] = 1.0
            s["hold"] += (hold_target - s["hold"]) / 0.6 * dt
            s["boost"] -= s["boost"] / 8.0 * dt
            hold = s["hold"]

            s["f_ou"] += -s["f_ou"] / 15.0 * dt + 0.012 * math.sqrt(2 * dt / 15.0) * xi[1]
            f_spont = p.resting_resp_rate_hz + 0.09 * a_c + s["f_ou"]
            f = (1 - w) * f_spont + w * p.pace_rate_hz
            coupling = 0.0
            if cue is not None:
                phi_cue = 2 * math.pi * p.pace_rate_hz * (t - cue.program_start_s)
                coupling = 0.8 * w * math.sin(phi_cue - s["phi"])
            phase_velocity = 2 * math.pi * f * (1 - hold) + coupling
            s["phi"] += phase_velocity * dt
            amp = (1 - hold) * (1 + 0.5 * w) * (1 + 0.35 * s["boost"])

            rsa = p.rsa_amplitude_bpm * (1 - 0.55 * a_c) * (1 + p.rsa_resonance_gain * math.exp(-((f - 0.1) / 0.035) ** 2)) * amp
            s["hr_ou"] += -s["hr_ou"] / 4.0 * dt + 0.9 * math.sqrt(2 * dt / 4.0) * xi[2]
            hr = (p.resting_hr_bpm + p.arousal_hr_gain_bpm * a - 5.0 * hold
                  + rsa * math.sin(s["phi"] - 0.35)
                  + p.mayer_amplitude_bpm * math.sin(mayer_w * t + self._mayer_phase) + s["hr_ou"])

            # IPFM beat generation with sub-step crossing interpolation.
            previous = s["cardiac"]
            s["cardiac"] += hr / 60.0 * dt
            if s["cardiac"] >= 1.0:
                frac = (1.0 - previous) / (s["cardiac"] - previous)
                self._emit_beat(t - dt + frac * dt, a_c, amp, s["phi"])
                s["cardiac"] -= 1.0

            s["s_ou"] += -s["s_ou"] / 60.0 * dt + 0.15 * math.sqrt(2 * dt / 60.0) * xi[3]
            delayed_hold = self.hold[k - 1100] if k >= 1100 else 0.0
            s_target = p.spo2_baseline_pct + s["s_ou"] - p.breath_hold_desaturation_pct * delayed_hold
            s["spo2"] += (s_target - s["spo2"]) / 7.0 * dt

            s["scl_ou"] += -s["scl_ou"] / 90.0 * dt + 0.15 * math.sqrt(2 * dt / 90.0) * xi[4]
            scl_target = p.resting_scl_us * (1 + 0.42 * a) + s["scl_ou"]
            s["scl"] += (scl_target - s["scl"]) / 25.0 * dt

            rate = (1.0 + 9.0 * a_c) / 60.0
            if self._scr_uniform[k] < rate * dt:
                amplitude = math.exp(math.log(0.10 * (1 + 1.2 * a_c)) + 0.55 * self._scr_normal[k])
                self._emit_scr(t, amplitude, self._scr_shape[k], "SPONTANEOUS")
            still_pending = []
            for onset, i in self._pending_stimulus_scrs:
                if onset <= t:
                    z = self._stimulus_normals[i]
                    amplitude = math.exp(math.log(0.28 * (1 + 0.8 * a_c)) + 0.45 * z[0])
                    self._emit_scr(onset, amplitude, np.clip(z[1:] / 3, -1, 1), "STIMULUS")
                else:
                    still_pending.append((onset, i))
            self._pending_stimulus_scrs = still_pending

            self.arousal[k] = a
            self.resp_phase[k] = s["phi"]
            self.resp_amp[k] = amp
            self.resp_rate_hz[k] = phase_velocity / (2 * math.pi)
            self.hr_bpm[k] = hr
            self.spo2[k] = s["spo2"]
            self.scl[k] = s["scl"]
            self.entrainment[k] = w
            self.hold[k] = hold
        self._n = max(self._n, last + 1)

    def _emit_beat(self, r_time: float, a_c: float, amp: float, phi: float) -> None:
        i = len(self.beats)
        z = self._beat_noise[i]
        pat = 0.265 - 0.045 * a_c + 0.004 * z[0]
        amplitude = (1 - 0.32 * a_c) * (1 - 0.10 * amp * math.cos(phi)) * (1 + 0.03 * z[1])
        ibi = r_time - self.beats[-1]["r_s"] if self.beats else 60.0 / self.params.resting_hr_bpm
        self.beats.append({"r_s": r_time, "peak_s": r_time + pat, "pat_s": pat, "amplitude": amplitude, "ibi_s": ibi})

    def _emit_scr(self, onset: float, amplitude: float, shape: np.ndarray, kind: str) -> None:
        tau1 = 0.7 * (1 + 0.15 * float(shape[0]))
        tau2 = 2.8 * (1 + 0.20 * float(shape[1]))
        t_peak = math.log(tau2 / tau1) * tau1 * tau2 / (tau2 - tau1)
        norm = math.exp(-t_peak / tau2) - math.exp(-t_peak / tau1)
        self.scrs.append({"onset_s": onset, "peak_s": onset + t_peak, "amplitude_us": amplitude,
                          "tau1_s": tau1, "tau2_s": tau2, "norm": norm, "kind": kind})

    # -------------------------------------------------------------- rendering
    def _check_rendered(self, t: np.ndarray, lookahead_s: float = 0.0) -> None:
        if len(t) and float(np.max(t)) + lookahead_s > self.generated_until_s + 1e-9:
            raise ValueError("Requested signal beyond generated physiology")

    def blood_volume(self, t: np.ndarray) -> np.ndarray:
        """Normalized pulsatile blood volume (dimensionless, ~0..1 per beat)."""
        t = np.asarray(t, dtype=np.float64)
        self._check_rendered(t, lookahead_s=0.45)
        out = np.zeros_like(t)
        if not len(t):
            return out
        lo, hi = t.min() - 1.6, t.max() + 0.45
        for beat in self.beats:
            if beat["peak_s"] < lo or beat["peak_s"] > hi:
                continue
            scale = math.sqrt(max(beat["ibi_s"], 0.3) / 0.9)
            tau = t - beat["peak_s"]
            sigma = np.where(tau < 0, 0.075 * scale, 0.17 * scale)
            wave = np.exp(-0.5 * (tau / sigma) ** 2)
            wave += 0.32 * np.exp(-0.5 * ((tau - 0.30 * scale) / (0.09 * scale)) ** 2)
            out += beat["amplitude"] * wave
        return out

    def respiration(self, t: np.ndarray) -> np.ndarray:
        t = np.asarray(t, dtype=np.float64)
        self._check_rendered(t)
        n = self._n
        phi = np.interp(t, self.t_grid[:n], self.resp_phase[:n])
        amp = np.interp(t, self.t_grid[:n], self.resp_amp[:n])
        return -amp * np.cos(phi)

    def spo2_at(self, t: np.ndarray) -> np.ndarray:
        t = np.asarray(t, dtype=np.float64)
        self._check_rendered(t)
        return np.interp(t, self.t_grid[:self._n], self.spo2[:self._n])

    def skin_conductance(self, t: np.ndarray, include_artifact: bool = True) -> np.ndarray:
        """Skin conductance in microsiemens (tonic + phasic [+ motion artifact])."""
        t = np.asarray(t, dtype=np.float64)
        self._check_rendered(t)
        out = np.interp(t, self.t_grid[:self._n], self.scl[:self._n])
        out = out + self.phasic_conductance(t)
        if include_artifact:
            out = out + np.interp(t, self.k_t, self.k_eda_artifact)
        return out

    def phasic_conductance(self, t: np.ndarray) -> np.ndarray:
        t = np.asarray(t, dtype=np.float64)
        out = np.zeros_like(t)
        if not len(t):
            return out
        lo, hi = t.min() - 40.0, t.max()
        for scr in self.scrs:
            if scr["onset_s"] < lo or scr["onset_s"] > hi:
                continue
            tau = np.clip(t - scr["onset_s"], 0, None)
            wave = (np.exp(-tau / scr["tau2_s"]) - np.exp(-tau / scr["tau1_s"])) / scr["norm"]
            out += scr["amplitude_us"] * np.where(t >= scr["onset_s"], wave, 0.0)
        return out

    def gravity_and_motion(self, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Body-frame specific force (g) and angular rate (deg/s) at the IMU."""
        t = np.asarray(t, dtype=np.float64)
        roll = np.interp(t, self.k_t, self.k_roll)
        pitch = np.interp(t, self.k_t, self.k_pitch)
        gravity = np.column_stack([-np.sin(pitch), np.sin(roll) * np.cos(pitch), np.cos(roll) * np.cos(pitch)])
        motion = np.column_stack([np.interp(t, self.k_t, self.k_motion_accel[:, i] + self.k_tremor[:, i]) for i in range(3)])
        gyro = np.column_stack([np.interp(t, self.k_t, self.k_gyro[:, i]) for i in range(3)])
        return gravity + motion, gyro

    def ppg_motion(self, t: np.ndarray) -> np.ndarray:
        return np.interp(np.asarray(t, dtype=np.float64), self.k_t, self.k_ppg_motion)

    # ------------------------------------------------------------------ truth
    def truth(self, decimate_hz: float = 10.0) -> dict[str, Any]:
        """Ground truth for scoring. Never passed to the signal pipeline."""
        n = self._n
        step = max(1, int(round(1 / (decimate_hz * GRID_DT_S))))
        idx = np.arange(0, n, step)
        motion_env = np.sqrt(np.sum(self.k_motion_accel ** 2, axis=1))
        beats = []
        for beat in self.beats:
            # Scoring fiducial: the observable systolic maximum of the rendered
            # wave (1 ms search), not the template parameter it came from.
            if beat["peak_s"] + 0.55 <= self.generated_until_s:
                fine = np.arange(beat["peak_s"] - 0.1, beat["peak_s"] + 0.1, 0.001)
                systolic = float(fine[int(np.argmax(self.blood_volume(fine)))])
            else:
                systolic = beat["peak_s"]
            beats.append({**{k: round(v, 6) for k, v in beat.items()}, "systolic_s": round(systolic, 6)})
        return {
            "grid_rate_hz": 1 / (GRID_DT_S * step),
            "t_s": self.t_grid[idx].round(4).tolist(),
            "arousal": self.arousal[idx].round(5).tolist(),
            "hr_bpm": self.hr_bpm[idx].round(4).tolist(),
            "resp_rate_bpm": (self.resp_rate_hz[idx] * 60).round(4).tolist(),
            "resp_amplitude": self.resp_amp[idx].round(5).tolist(),
            "spo2_pct": self.spo2[idx].round(4).tolist(),
            "scl_tonic_us": self.scl[idx].round(5).tolist(),
            "entrainment": self.entrainment[idx].round(5).tolist(),
            "breath_hold": self.hold[idx].round(5).tolist(),
            "beats": beats,
            "scrs": [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in s.items() if k != "norm"} for s in self.scrs],
            "stimuli_s": self.stimuli,
            "motion_episodes": [asdict(m) for m in self.config.motion],
            "phases": [asdict(p) for p in self.config.phases],
            "motion_magnitude_g_10hz": motion_env[:: int(KINEMATIC_RATE_HZ / 10)].round(5).tolist(),
        }
