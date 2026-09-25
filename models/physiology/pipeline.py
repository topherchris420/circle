"""CIRCLE physiology pipeline: raw Rev B records in, lineage-preserving physiology out.

Inputs are a RawSession only: integer codes, firmware sequence numbers, native
device timestamps, declared gaps, and device-logged events. Nothing here
imports or reads the twin. Every function is deterministic, so replaying the
exported raw bundle reproduces every output bit for bit.

Methods (all classical and citable):
  * Clock: least-squares device-time vs laboratory 1 PPS mapping.
  * IMU: gravity separation by low-pass, dynamic-acceleration RMS motion
    detection, tilt; haptic vibration onset by high-pass envelope.
  * EDA: code -> conductance through the front-end equation; trough-to-peak
    SCR detection on the derivative of low-passed conductance; tonic level by
    interpolation between inter-response anchors.
  * PPG: 0.5-8 Hz linear-phase band-pass; systolic peaks by two event-related
    moving averages (Elgendi et al. 2013); template-correlation quality;
    physiological IBI screening; HR, RMSSD; respiration from the
    respiratory-induced intensity variation (RIIV) with breath detection;
    ratio-of-ratios SpO2 with IMU motion gating.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np

from .dsp import (contiguous_runs, filter_zero_phase, fir_bandpass, fir_lowpass, gaussian_lowpass,
                  mask_runs, moving_average, parabolic_peak_offset, rolling_extreme)
from .streams import RawSession, Stream

PIPELINE_VERSION = "1.0.0"
SPO2_CURVE = (110.0, 25.0)  # Uncalibrated empirical SpO2 = a - b * R.


# ----------------------------------------------------------------- clock
@dataclass(frozen=True)
class ClockFit:
    slope_us_per_s: float
    offset_us: float
    residual_rms_us: float
    residual_max_us: float
    pulses: int

    @property
    def ppm(self) -> float:
        return (self.slope_us_per_s / 1e6 - 1.0) * 1e6

    def lab_seconds(self, device_us: np.ndarray | float) -> np.ndarray:
        return (np.asarray(device_us, dtype=np.float64) - self.offset_us) / self.slope_us_per_s

    def to_dict(self) -> dict[str, float]:
        return {"ppm": self.ppm, "offset_us": self.offset_us, "residual_rms_us": self.residual_rms_us,
                "residual_max_us": self.residual_max_us, "pulses": self.pulses}


def fit_clock(sync: Stream) -> ClockFit:
    """Map device microseconds to laboratory seconds from captured 1 PPS edges."""
    if len(sync) < 2:
        raise ValueError("At least two SYNC pulses are required for a clock mapping")
    lab = sync.columns["lab_pulse_index"].astype(np.float64)
    dev = sync.device_time_us.astype(np.float64)
    lab_c = lab - lab.mean()
    slope = float(np.dot(lab_c, dev - dev.mean()) / np.dot(lab_c, lab_c))
    offset = float(dev.mean() - slope * lab.mean())
    residual = dev - (offset + slope * lab)
    return ClockFit(slope, offset, float(np.sqrt(np.mean(residual ** 2))), float(np.max(np.abs(residual))), len(sync))


# -------------------------------------------------------------- utilities
def _seconds(us: np.ndarray) -> np.ndarray:
    return np.asarray(us, dtype=np.float64) / 1e6


def _interp_time(index_float: np.ndarray, device_us: np.ndarray) -> np.ndarray:
    """Device seconds at fractional sample indices (timestamps are not uniform)."""
    return np.interp(index_float, np.arange(len(device_us)), _seconds(device_us))


def _time_segments(t: np.ndarray, max_step_s: float) -> list[tuple[int, int]]:
    """Index ranges [start, stop) with no time step larger than max_step_s."""
    if len(t) == 0:
        return []
    breaks = np.flatnonzero(np.diff(t) > max_step_s) + 1
    edges = np.concatenate([[0], breaks, [len(t)]])
    return [(int(a), int(b)) for a, b in zip(edges[:-1], edges[1:])]


def _in_intervals(t: np.ndarray, intervals: list[tuple[float, float]]) -> np.ndarray:
    t = np.asarray(t, dtype=np.float64)
    out = np.zeros(t.shape, dtype=bool)
    for a, b in intervals:
        out |= (t >= a) & (t <= b)
    return out


# -------------------------------------------------------------------- IMU
def imu_physical(imu: Stream, descriptor: dict[str, float]) -> tuple[np.ndarray, np.ndarray]:
    accel = np.column_stack([imu.columns[k] for k in ("ax_lsb", "ay_lsb", "az_lsb")]) / descriptor["accel_lsb_per_g"]
    gyro = np.column_stack([imu.columns[k] for k in ("gx_lsb", "gy_lsb", "gz_lsb")]) / descriptor["gyro_lsb_per_dps"]
    return accel, gyro


def analyze_motion(imu: Stream, descriptor: dict[str, float]) -> dict[str, Any]:
    """Motion intensity (g RMS), motion episodes, and tilt at 50 Hz."""
    empty = {"t_s": np.zeros(0), "intensity_g": np.zeros(0), "gyro_dps": np.zeros(0),
             "tilt_deg": np.zeros(0), "flag": np.zeros(0, dtype=bool), "episodes": []}
    block = int(round(descriptor["nominal_rate_hz"] / 50.0))
    n = (len(imu) // block) * block
    if n < block * 50:
        return empty
    accel, gyro = imu_physical(imu, descriptor)
    fs = descriptor["nominal_rate_hz"] / block
    t = _seconds(imu.device_time_us[:n]).reshape(-1, block).mean(axis=1)
    lp20 = fir_lowpass(20.0, descriptor["nominal_rate_hz"], 101)
    a = np.column_stack([filter_zero_phase(accel[:, i], lp20)[:n].reshape(-1, block).mean(axis=1) for i in range(3)])
    w = np.column_stack([gyro[:n, i].reshape(-1, block).mean(axis=1) for i in range(3)])
    gravity_lp = fir_lowpass(0.4, fs, 301)
    gravity = np.column_stack([filter_zero_phase(a[:, i], gravity_lp) for i in range(3)])
    dynamic = np.linalg.norm(a - gravity, axis=1)
    gyro_hp = w - np.column_stack([filter_zero_phase(w[:, i], gravity_lp) for i in range(3)])
    intensity = np.sqrt(moving_average(dynamic ** 2, int(fs * 0.5)))
    gyro_mag = np.sqrt(moving_average(np.sum(gyro_hp ** 2, axis=1), int(fs * 0.5)))
    raw_flag = (intensity > 0.03) | (gyro_mag > 20.0)
    episodes = []
    for a_i, b_i in mask_runs(raw_flag):
        if (b_i - a_i) / fs >= 0.4:
            episodes.append([t[a_i] - 0.75, t[b_i - 1] + 0.75])
    merged: list[list[float]] = []
    for ep in episodes:
        if merged and ep[0] <= merged[-1][1] + 0.5:
            merged[-1][1] = max(merged[-1][1], ep[1])
        else:
            merged.append(ep)
    tilt = np.degrees(np.arccos(np.clip(gravity[:, 2] / np.maximum(np.linalg.norm(gravity, axis=1), 1e-9), -1, 1)))
    return {"t_s": t, "intensity_g": intensity, "gyro_dps": gyro_mag, "tilt_deg": tilt,
            "flag": _in_intervals(t, [tuple(e) for e in merged]),
            "episodes": [(float(a_), float(b_)) for a_, b_ in merged]}


def _carrier_envelope(accel: np.ndarray, fs: float, carrier_hz: float) -> np.ndarray:
    """Amplitude of a known-frequency vibration from four consecutive samples.

    A second difference removes gravity and slow limb motion; for a sinusoid of
    known angular step w, two consecutive samples x0, x1 determine its
    amplitude exactly: A^2 = (x0^2 + x1^2 - 2 x0 x1 cos w) / sin^2 w.
    Element k describes samples k..k+3.
    """
    w = 2 * math.pi * carrier_hz / fs
    if abs(math.sin(w)) < 0.2:
        raise ValueError("Carrier too close to DC or Nyquist for two-sample amplitude estimation")
    d2 = np.diff(accel, n=2, axis=0)
    a2 = (d2[1:] ** 2 + d2[:-1] ** 2 - 2 * d2[1:] * d2[:-1] * math.cos(w)) / math.sin(w) ** 2
    gain = (2 * math.sin(w / 2)) ** 2  # second-difference gain at the carrier
    return np.sqrt(np.clip(a2.sum(axis=1), 0, None)) / gain


def detect_haptic_vibration(imu: Stream, descriptor: dict[str, float], session: RawSession) -> list[dict[str, Any]]:
    """Physical haptic onset observed by the on-board IMU (50 % envelope crossing)."""
    onsets = {(e.attribute("program"), e.attribute("cue_index")): e for e in session.events_of("HAPTIC_ELECTRICAL_ONSET")}
    results = []
    if not len(imu):
        return results
    fs = descriptor["nominal_rate_hz"]
    accel, _ = imu_physical(imu, descriptor)
    t = _seconds(imu.device_time_us)
    for command in session.events_of("HAPTIC_COMMAND"):
        if command.kind != "HAPTIC_COMMAND":
            continue
        key = (command.attribute("program"), command.attribute("cue_index"))
        t_cmd = command.device_time_us / 1e6
        lo = int(np.searchsorted(t, t_cmd - 0.05))
        hi = int(np.searchsorted(t, t_cmd + 0.15))
        record: dict[str, Any] = {"program": key[0], "cue_index": key[1], "command_s": t_cmd,
                                  "command_evidence": command.evidence_id}
        onset_event = onsets.get(key)
        if onset_event is not None:
            record["electrical_onset_s"] = onset_event.device_time_us / 1e6
            record["electrical_evidence"] = onset_event.evidence_id
        carrier, pulse_ms = command.attribute("lra_hz"), command.attribute("pulse_ms")
        if hi - lo < 40 or carrier is None or pulse_ms is None:
            results.append(record)
            continue
        env = _carrier_envelope(accel[lo:hi], fs, carrier)
        # Each estimate spans four samples; assign it to their center.
        tt = t[lo:lo + len(env)] + 1.5 / fs
        pre = env[tt < t_cmd]
        noise = float(np.median(pre)) if len(pre) else 0.0
        steady_window = (tt >= t_cmd + 0.02) & (tt <= t_cmd + min(0.05, pulse_ms / 1000 - 0.005))
        steady = float(np.median(env[steady_window])) if steady_window.any() else 0.0
        if steady > max(8 * noise, 0.01):
            level = 0.5 * steady
            crossing = np.flatnonzero((tt >= t_cmd) & (env >= level))
            idx = int(crossing[0])
            frac = (level - env[idx - 1]) / (env[idx] - env[idx - 1]) if idx > 0 and env[idx - 1] < level else 0.0
            onset_s = tt[idx - 1] + frac * (tt[idx] - tt[idx - 1]) if idx > 0 else tt[idx]
            record.update({"physical_onset_s": float(onset_s), "steady_amplitude_g": steady,
                           "imu_sequence_first": int(imu.sequence[lo]), "imu_sequence_last": int(imu.sequence[hi - 1])})
        results.append(record)
    return results


# -------------------------------------------------------------------- EDA
def eda_conductance_us(codes: np.ndarray, descriptor: dict[str, float]) -> np.ndarray:
    """Invert the four-wire front end: sensed limit-network voltage -> skin conductance."""
    full = 2 ** (int(descriptor["adc_bits"]) - 1)
    v_sense = np.asarray(codes, dtype=np.float64) / full * descriptor["vref_v"] / descriptor["pga_gain"]
    v_exc, r_lim = descriptor["excitation_v"], descriptor["series_limit_ohm"]
    v_sense = np.clip(v_sense, 1e-9, v_exc * (1 - 1e-9))
    r_skin = r_lim * (v_exc / v_sense - 1.0)
    return 1e6 / r_skin


SCR_MIN_AMPLITUDE_US = 0.04
SCR_MIN_RISE_S = 0.6
SCR_MIN_SLOPE_BUMP_US_PER_S = 0.02
SCR_RECOVERY_TAU_S = 3.0


def _slope_bumps(slope: np.ndarray, fs: float) -> list[tuple[int, int, float]]:
    """SCRs as bumps in the conductance slope: (onset index, end-of-rise index, amplitude uS).

    Each response adds a transient bump to the slope, even when it rides on the
    decay of an earlier response and the conductance itself never turns
    upward. Amplitude is the bump's area above the pre-onset slope, which for
    an isolated response equals its trough-to-peak rise. A response starting
    during the rising limb of another merges with it (no separate trough).
    """
    n = len(slope)
    peaks = np.flatnonzero((slope[1:-1] > slope[:-2]) & (slope[1:-1] >= slope[2:])) + 1
    curvature = moving_average(np.gradient(slope) * fs, int(fs * 0.25))
    out: list[tuple[int, int, float]] = []
    last_end = 0
    for p in peaks:
        if p <= last_end:
            continue
        lo = max(last_end, p - int(1.5 * fs))
        m = lo + int(np.argmin(slope[lo:p + 1]))
        # Baseline: the pre-bump slope. A negative slope is the recovery of an
        # earlier response, which relaxes exponentially toward zero (generic
        # recovery time constant, not fitted per response).
        stop = min(n - 1, p + int(6.0 * fs))
        idx = np.arange(m, stop + 1)
        if slope[m] < 0:
            base = slope[m] * np.exp(-(idx - m) / (SCR_RECOVERY_TAU_S * fs))
        else:
            base = np.full(len(idx), slope[m])
        excess = slope[m:stop + 1] - base
        k = p - m
        height = excess[k]
        if height < SCR_MIN_SLOPE_BUMP_US_PER_S:
            continue
        # A response is a transient excess that falls back quickly; a mismatch
        # between the true and assumed recovery only drifts slowly.
        if excess[k:k + int(2.5 * fs)].min() > 0.4 * height:
            continue
        below = np.flatnonzero(excess[k:] <= 0)
        if not len(below):
            continue
        end = p + int(below[0])
        # Onset time at maximum curvature: an SCR starts with an abrupt slope
        # change, distinguishable from the slow relaxation of an earlier decay.
        onset = m + int(np.argmax(curvature[m:p + 1]))
        amplitude = float(np.sum(excess[:end - m + 1]) / fs)
        rise = (end - onset) / fs
        if amplitude >= SCR_MIN_AMPLITUDE_US and SCR_MIN_RISE_S <= rise <= 4.0:
            out.append((onset, end, amplitude))
            last_end = end
    return out


def analyze_eda(eda: Stream, descriptor: dict[str, float], motion_episodes: list[tuple[float, float]]) -> dict[str, Any]:
    fs = descriptor["nominal_rate_hz"]
    empty = {"t_s": np.zeros(0), "conductance_us": np.zeros(0), "tonic_us": np.zeros(0), "scrs": []}
    if len(eda) < fs * 10:
        return empty
    t = _seconds(eda.device_time_us) - descriptor["timestamp_minus_sample_center_us"] / 1e6
    g = eda_conductance_us(eda.columns["code"], descriptor)
    g_lp = filter_zero_phase(g, gaussian_lowpass(1.2, fs))
    slope = moving_average(np.gradient(g_lp) * fs, int(fs * 0.25))
    n = len(g_lp)
    scrs = []
    for onset, end, amplitude in _slope_bumps(slope, fs):
        onset_s, peak_s = float(t[onset]), float(t[end])
        confounded = any(a - 0.5 <= onset_s <= b or a <= peak_s <= b for a, b in motion_episodes)
        scrs.append({"onset_s": onset_s, "peak_s": peak_s, "amplitude_us": amplitude,
                     "rise_s": (end - onset) / fs, "motion_confounded": bool(confounded),
                     "sequence_first": int(eda.sequence[onset]), "sequence_last": int(eda.sequence[end])})
    # Tonic: interpolate across samples outside response windows, anchored at troughs.
    anchor = np.ones(n, dtype=bool)
    for scr in scrs:
        anchor &= ~((t >= scr["onset_s"] + 0.05) & (t <= scr["peak_s"] + 5.0))
    for a, b in motion_episodes:
        anchor &= ~((t >= a) & (t <= b))
    if anchor.sum() >= 2:
        tonic = np.interp(t, t[anchor], rolling_extreme(g_lp, int(fs), "min")[anchor])
    else:
        tonic = rolling_extreme(g_lp, int(fs * 8), "min")
    tonic = moving_average(tonic, int(fs * 4))
    return {"t_s": t, "conductance_us": g_lp, "tonic_us": tonic, "scrs": scrs}


# -------------------------------------------------------------------- PPG
PPG_BAND = (0.5, 8.0, 601)
APNEA_ENVELOPE_S = 6.0


def _elgendi_peaks(x: np.ndarray, fs: float) -> np.ndarray:
    """Systolic peak indices by two event-related moving averages (Elgendi 2013)."""
    y = np.clip(x, 0, None) ** 2
    ma_peak = moving_average(y, int(round(0.111 * fs)))
    ma_beat = moving_average(y, int(round(0.667 * fs)))
    blocks = mask_runs(ma_peak > ma_beat + 0.02 * float(np.mean(y)))
    peaks = []
    for a, b in blocks:
        if b - a >= int(round(0.111 * fs)):
            peaks.append(a + int(np.argmax(x[a:b])))
    peaks_arr = np.array(peaks, dtype=np.int64)
    if len(peaks_arr) < 2:
        return peaks_arr
    keep = [int(peaks_arr[0])]
    for p in peaks_arr[1:]:
        if (p - keep[-1]) / fs < 0.3:
            if x[p] > x[keep[-1]]:
                keep[-1] = int(p)
        else:
            keep.append(int(p))
    return np.array(keep, dtype=np.int64)


def detect_beats(ppg: Stream, descriptor: dict[str, float], motion_episodes: list[tuple[float, float]]) -> dict[str, Any]:
    """Beat times (device s), per-beat quality, and pulse amplitude from IR counts."""
    fs = descriptor["nominal_rate_hz"]
    taps = fir_bandpass(PPG_BAND[0], PPG_BAND[1], fs, PPG_BAND[2])
    times, quality, amplitude, segment_id, seq = [], [], [], [], []
    bp_all = np.full(len(ppg), np.nan)
    for sid, (a, b) in enumerate(contiguous_runs(ppg.sequence)):
        if b - a < fs * 4:
            continue
        ir = ppg.columns["ir_counts"][a:b].astype(np.float64)
        bp = filter_zero_phase(-ir, taps)
        shape = filter_zero_phase(-ir, fir_lowpass(15.0, fs, 61))
        bp_all[a:b] = bp
        peaks = _elgendi_peaks(bp, fs)
        if not len(peaks):
            continue
        half_before, half_after = int(0.25 * fs), int(0.45 * fs)
        snippets, valid_idx = [], []
        for k, p in enumerate(peaks):
            if half_before <= p < len(bp) - half_after:
                snippets.append(bp[p - half_before:p + half_after])
                valid_idx.append(k)
        corr = np.zeros(len(peaks))
        if snippets:
            snips = np.array(snippets)
            for j, k in enumerate(valid_idx):
                lo, hi = max(0, j - 15), min(len(snips), j + 16)
                template = np.median(snips[lo:hi], axis=0)
                c = np.corrcoef(snips[j], template)[0, 1]
                corr[k] = c if np.isfinite(c) else 0.0
        dc = float(np.mean(ir))
        for k, p in enumerate(peaks):
            # Refine the fiducial on a shape-preserving 15 Hz low-pass: the 8 Hz
            # band edge would bias the sharp systolic maximum by ~10 ms.
            lo_r, hi_r = max(1, p - 4), min(len(shape) - 1, p + 5)
            j = lo_r + int(np.argmax(shape[lo_r:hi_r]))
            offset = parabolic_peak_offset(shape[j - 1], shape[j], shape[j + 1]) if 0 < j < len(shape) - 1 else 0.0
            t_beat = float(_interp_time(np.array([a + j + offset]), ppg.device_time_us)[0])
            trough = bp[max(0, p - int(0.4 * fs)):p + 1].min()
            edge = (p < 1.0 * fs) or (p > len(bp) - 1.0 * fs)
            if any(lo_ <= t_beat <= hi_ for lo_, hi_ in motion_episodes):
                q = "MOTION"
            elif edge:
                q = "EDGE"
            elif corr[k] < 0.85:
                q = "LOW_TEMPLATE_CORRELATION"
            else:
                q = "GOOD"
            times.append(t_beat)
            quality.append(q)
            amplitude.append(float((bp[p] - trough) / dc * 100.0))
            segment_id.append(sid)
            seq.append(int(ppg.sequence[a + p]))
    times_arr = np.array(times)
    quality_arr = np.array(quality, dtype=object)
    good = quality_arr == "GOOD"
    seg = np.array(segment_id)
    ibi_start, ibi_end, ibi_valid = [], [], []
    for k in range(1, len(times_arr)):
        if seg[k] == seg[k - 1] and good[k] and good[k - 1]:
            ibi = times_arr[k] - times_arr[k - 1]
            ibi_start.append(times_arr[k - 1])
            ibi_end.append(times_arr[k])
            ibi_valid.append(0.33 <= ibi <= 1.8)
    ibi_start_a, ibi_end_a = np.array(ibi_start), np.array(ibi_end)
    ibi = ibi_end_a - ibi_start_a
    valid = np.array(ibi_valid, dtype=bool)
    if len(ibi) >= 3:
        for k in range(len(ibi)):
            lo, hi = max(0, k - 4), min(len(ibi), k + 5)
            med = np.median(ibi[lo:hi])
            if abs(ibi[k] - med) > 0.25 * med:
                valid[k] = False
    return {"t_s": times_arr, "quality": quality_arr, "pulse_amplitude_pct": np.array(amplitude),
            "sequence": np.array(seq, dtype=np.int64),
            "ibi_start_s": ibi_start_a, "ibi_end_s": ibi_end_a, "ibi_s": ibi, "ibi_valid": valid,
            "bandpassed": bp_all}


def heart_rate_series(beats: dict[str, Any], t_grid: np.ndarray) -> np.ndarray:
    """Instantaneous HR (bpm) on a grid from valid IBIs; NaN where unsupported."""
    ibi, valid = beats["ibi_s"], beats["ibi_valid"]
    out = np.full(len(t_grid), np.nan)
    if valid.sum() < 2:
        return out
    mid = 0.5 * (beats["ibi_start_s"][valid] + beats["ibi_end_s"][valid])
    hr = 60.0 / ibi[valid]
    out = np.interp(t_grid, mid, hr)
    # Unsupported where the nearest valid IBI midpoint is more than 3 s away.
    right = np.clip(np.searchsorted(mid, t_grid), 1, len(mid) - 1)
    nearest = np.minimum(np.abs(t_grid - mid[right - 1]), np.abs(mid[right] - t_grid))
    out[nearest > 3.0] = np.nan
    return out


def rmssd_ms(beats: dict[str, Any], t0: float, t1: float) -> float:
    ibi, valid, end = beats["ibi_s"], beats["ibi_valid"], beats["ibi_end_s"]
    diffs = []
    for k in range(1, len(ibi)):
        if valid[k] and valid[k - 1] and t0 <= end[k] <= t1 and math.isclose(beats["ibi_start_s"][k], end[k - 1]):
            diffs.append(ibi[k] - ibi[k - 1])
    if len(diffs) < 5:
        return float("nan")
    return float(np.sqrt(np.mean(np.square(diffs))) * 1000.0)


def _prominent_peaks(x: np.ndarray, min_prominence: float, window: int) -> list[int]:
    """Local maxima whose topographic prominence (within +/- window) exceeds a threshold.

    Each side's base is the minimum between the peak and the nearest higher
    sample on that side (or the window edge); prominence is the height above
    the higher of the two bases.
    """
    peaks = []
    n = len(x)
    for k in range(1, n - 1):
        if not (x[k] >= x[k - 1] and x[k] > x[k + 1]):
            continue
        bases = []
        for direction in (-1, 1):
            j, lowest = k + direction, x[k]
            limit = max(0, k - window) if direction < 0 else min(n - 1, k + window)
            while (j >= limit if direction < 0 else j <= limit) and x[j] <= x[k]:
                lowest = min(lowest, x[j])
                j += direction
            bases.append(lowest)
        if x[k] - max(bases) >= min_prominence:
            peaks.append(k)
    return peaks


def analyze_respiration(ppg: Stream, descriptor: dict[str, float], motion_episodes: list[tuple[float, float]]) -> dict[str, Any]:
    """Breaths from the respiratory-induced intensity variation (RIIV) of IR counts."""
    fs = descriptor["nominal_rate_hz"]
    block = int(round(fs / 10))
    t_all, riiv_all = [], []
    for a, b in contiguous_runs(ppg.sequence):
        n = ((b - a) // block) * block
        if n < block * 80:
            continue
        ir = ppg.columns["ir_counts"][a:a + n].astype(np.float64).reshape(-1, block).mean(axis=1)
        tt = _seconds(ppg.device_time_us[a:a + n]).reshape(-1, block).mean(axis=1)
        low = filter_zero_phase(ir, fir_lowpass(0.6, 10.0, 161))
        trend = moving_average(low, 200)
        riiv = (low - trend) / np.mean(ir)
        t_all.append(tt)
        riiv_all.append(riiv)
    if not t_all:
        return {"t_s": np.zeros(0), "riiv": np.zeros(0), "envelope": np.zeros(0), "breaths_s": np.zeros(0),
                "apnea": [], "rate_t_s": np.zeros(0), "rate_bpm": np.zeros(0)}
    t = np.concatenate(t_all)
    riiv = np.concatenate(riiv_all)
    usable = ~_in_intervals(t, motion_episodes)
    scale = float(np.median(np.abs(riiv[usable] - np.median(riiv[usable])))) if usable.any() else 0.0
    breaths: list[float] = []
    segment_of: list[int] = []
    for sid, (a, b) in enumerate(_time_segments(t, max_step_s=0.2)):
        seg_t, seg_x, seg_ok = t[a:b], riiv[a:b], usable[a:b]
        peaks = _prominent_peaks(seg_x, 1.2 * scale, window=40)
        last = -np.inf
        for k in peaks:
            if seg_ok[k] and seg_t[k] - last >= 1.5:
                breaths.append(float(seg_t[k]))
                segment_of.append(sid)
                last = seg_t[k]
    breaths_a = np.array(breaths)
    # Apnea is cessation, not slow breathing: the respiratory envelope (6 s
    # peak-to-peak) collapses below 25 % of its motion-free median for >= 10 s.
    half = APNEA_ENVELOPE_S / 2
    envelope = np.zeros(len(t))
    for a, b in _time_segments(t, max_step_s=0.2):
        width = int(round(APNEA_ENVELOPE_S * 10))
        envelope[a:b] = rolling_extreme(riiv[a:b], width, "max") - rolling_extreme(riiv[a:b], width, "min")
    reference = float(np.median(envelope[usable])) if usable.any() else 0.0
    quiet = (envelope < 0.25 * reference) & usable
    apnea = []
    for a, b in mask_runs(quiet):
        # A centered window shrinks the quiet run by half a window at each end.
        start, stop = float(t[a]) - half, float(t[b - 1]) + half
        if stop - start >= 10.0:
            apnea.append((start, stop))
    rate_t, rate = [], []
    for k in range(1, len(breaths_a)):
        if segment_of[k] != segment_of[k - 1]:
            continue  # never measure an interval across a sequence gap
        interval = breaths_a[k] - breaths_a[k - 1]
        span_motion = any(a <= breaths_a[k] and b >= breaths_a[k - 1] for a, b in motion_episodes)
        span_apnea = any(a < breaths_a[k] and b > breaths_a[k - 1] for a, b in apnea)
        if not span_motion and not span_apnea and interval <= 20.0:
            rate_t.append(0.5 * (breaths_a[k] + breaths_a[k - 1]))
            rate.append(60.0 / interval)
    return {"t_s": t, "riiv": riiv, "envelope": envelope, "breaths_s": breaths_a, "apnea": apnea,
            "rate_t_s": np.array(rate_t), "rate_bpm": np.array(rate)}


def analyze_spo2(ppg: Stream, descriptor: dict[str, float], motion_episodes: list[tuple[float, float]],
                 window_s: float = 4.0, hop_s: float = 1.0) -> dict[str, Any]:
    """Ratio-of-ratios SpO2 per window, reported naive and IMU/quality gated."""
    fs = descriptor["nominal_rate_hz"]
    taps = fir_bandpass(PPG_BAND[0], PPG_BAND[1], fs, PPG_BAND[2])
    a_curve, b_curve = SPO2_CURVE
    out_t, naive, gated, ratio = [], [], [], []
    for a, b in contiguous_runs(ppg.sequence):
        if b - a < fs * 8:
            continue
        red = ppg.columns["red_counts"][a:b].astype(np.float64)
        ir = ppg.columns["ir_counts"][a:b].astype(np.float64)
        red_bp, ir_bp = filter_zero_phase(red, taps), filter_zero_phase(ir, taps)
        t = _seconds(ppg.device_time_us[a:b])
        w, h = int(window_s * fs), int(hop_s * fs)
        edge = int(2.0 * fs)
        for s in range(0, len(t) - w + 1, h):
            e = s + w
            ac_r, ac_i = np.std(red_bp[s:e]), np.std(ir_bp[s:e])
            dc_r, dc_i = np.mean(red[s:e]), np.mean(ir[s:e])
            if ac_i <= 0 or dc_r <= 0 or dc_i <= 0:
                continue
            r = (ac_r / dc_r) / (ac_i / dc_i)
            value = a_curve - b_curve * r
            center = float(0.5 * (t[s] + t[e - 1]))
            perfusion = ac_i / dc_i
            corr = np.corrcoef(red_bp[s:e], ir_bp[s:e])[0, 1]
            ok = (s >= edge and e <= len(t) - edge and perfusion > 0.001 and corr > 0.9
                  and not any(lo <= t[e - 1] and hi >= t[s] for lo, hi in motion_episodes))
            out_t.append(center)
            naive.append(value)
            ratio.append(r)
            gated.append(value if ok else np.nan)
    gated_a = np.array(gated)
    smoothed = gated_a.copy()
    for k in range(len(gated_a)):
        window = gated_a[max(0, k - 2):k + 3]
        window = window[np.isfinite(window)]
        smoothed[k] = np.median(window) if np.isfinite(gated_a[k]) and len(window) else np.nan
    return {"t_s": np.array(out_t), "naive_pct": np.array(naive), "gated_pct": smoothed, "ratio": np.array(ratio)}


# ---------------------------------------------------------------- summary
@dataclass
class Analysis:
    clock: ClockFit
    motion: dict[str, Any]
    eda: dict[str, Any]
    beats: dict[str, Any]
    respiration: dict[str, Any]
    spo2: dict[str, Any]
    haptic: list[dict[str, Any]]
    windows: list[dict[str, Any]] = field(default_factory=list)


def analyze(session: RawSession, window_s: float = 10.0) -> Analysis:
    """Full offline analysis of a raw session."""
    d = session.descriptors
    clock = fit_clock(session.streams["sync"])
    motion = analyze_motion(session.streams["imu"], d["imu"])
    episodes = motion["episodes"]
    eda = analyze_eda(session.streams["eda"], d["eda"], episodes)
    beats = detect_beats(session.streams["ppg"], d["ppg"], episodes)
    resp = analyze_respiration(session.streams["ppg"], d["ppg"], episodes)
    spo2 = analyze_spo2(session.streams["ppg"], d["ppg"], episodes)
    haptic = detect_haptic_vibration(session.streams["imu"], d["imu"], session)
    analysis = Analysis(clock, motion, eda, beats, resp, spo2, haptic)
    analysis.windows = summarize_windows(session, analysis, window_s)
    return analysis


def _stream_ranges(stream: Stream, t0_us: int, t1_us: int) -> list[dict[str, int]]:
    window = stream.window(t0_us, t1_us - 1)
    return [{"stream_id": stream.name, "first_sequence": int(window.sequence[a]), "last_sequence": int(window.sequence[b - 1])}
            for a, b in contiguous_runs(window.sequence)]


def summarize_windows(session: RawSession, analysis: Analysis, window_s: float) -> list[dict[str, Any]]:
    """Fixed windows of derived physiology, each with exact source sequence ranges."""
    ppg = session.streams["ppg"]
    if not len(ppg):
        return []
    starts = [s.device_time_us[0] for s in session.streams.values() if len(s) and s.name != "sync"]
    ends = [s.device_time_us[-1] for s in session.streams.values() if len(s) and s.name != "sync"]
    t0_us, t_end_us = int(max(starts)), int(min(ends))
    step = int(window_s * 1e6)
    beats, eda, spo2, resp, motion = analysis.beats, analysis.eda, analysis.spo2, analysis.respiration, analysis.motion
    windows = []
    for w0 in range(t0_us, t_end_us - step + 1, step):
        w1 = w0 + step
        a, b = w0 / 1e6, w1 / 1e6
        payload: dict[str, float] = {}
        in_w = (beats["t_s"] >= a) & (beats["t_s"] < b)
        good = in_w & (beats["quality"] == "GOOD")
        payload["beats_detected"] = int(in_w.sum())
        payload["beats_good"] = int(good.sum())
        valid = beats["ibi_valid"] & (beats["ibi_end_s"] >= a) & (beats["ibi_end_s"] < b)
        if valid.sum() >= 3:
            payload["hr_bpm"] = round(float(60.0 / np.mean(beats["ibi_s"][valid])), 3)
        amp = beats["pulse_amplitude_pct"][good]
        if len(amp):
            payload["pulse_amplitude_pct"] = round(float(np.median(amp)), 5)
        e_in = (eda["t_s"] >= a) & (eda["t_s"] < b)
        if e_in.any():
            payload["scl_us"] = round(float(np.mean(eda["tonic_us"][e_in])), 5)
            payload["conductance_us"] = round(float(np.mean(eda["conductance_us"][e_in])), 5)
        scr_in = [s for s in eda["scrs"] if a <= s["onset_s"] < b]
        payload["scr_count"] = sum(1 for s in scr_in if not s["motion_confounded"])
        payload["scr_motion_confounded"] = sum(1 for s in scr_in if s["motion_confounded"])
        r_in = (resp["rate_t_s"] >= a) & (resp["rate_t_s"] < b)
        if r_in.any():
            payload["resp_rate_bpm"] = round(float(np.median(resp["rate_bpm"][r_in])), 3)
        payload["apnea_s"] = round(sum(max(0.0, min(b, y) - max(a, x)) for x, y in resp["apnea"]), 3)
        s_in = (spo2["t_s"] >= a) & (spo2["t_s"] < b) & np.isfinite(spo2["gated_pct"])
        if s_in.any():
            payload["spo2_pct"] = round(float(np.median(spo2["gated_pct"][s_in])), 3)
        m_in = (motion["t_s"] >= a) & (motion["t_s"] < b)
        payload["motion_fraction"] = round(float(np.mean(motion["flag"][m_in])), 4) if m_in.any() else 0.0
        ranges = []
        for name in ("eda", "ppg", "imu"):
            ranges.extend(_stream_ranges(session.streams[name], w0, w1))
        windows.append({"device_time_start_us": w0, "device_time_end_us": w1, "payload": payload,
                        "source_sequence_ranges": ranges})
    return windows
