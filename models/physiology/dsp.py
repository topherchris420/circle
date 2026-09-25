"""Linear-phase FIR filtering and small signal utilities (NumPy only).

Every filter here is a symmetric, odd-length FIR (windowed sinc, or a Gaussian
where overshoot matters). Zero-phase application convolves once and removes
the exact (N - 1) / 2 sample group delay, so detected event times are not
shifted by filtering. The closed-loop controller applies these filters only to
windows that end before its decision margin, so no future sample is used.
"""

from __future__ import annotations

import math

import numpy as np


def _odd_taps(numtaps: int) -> int:
    if isinstance(numtaps, bool) or not isinstance(numtaps, int) or numtaps < 3:
        raise ValueError("numtaps must be an integer >= 3")
    return numtaps if numtaps % 2 else numtaps + 1


def _check_band(cutoff_hz: float, fs_hz: float) -> None:
    if not (math.isfinite(cutoff_hz) and math.isfinite(fs_hz)) or not 0 < cutoff_hz < fs_hz / 2:
        raise ValueError("cutoff must be finite and inside (0, fs/2)")


def fir_lowpass(cutoff_hz: float, fs_hz: float, numtaps: int) -> np.ndarray:
    """Blackman-windowed sinc low-pass with exactly unity DC gain."""
    _check_band(cutoff_hz, fs_hz)
    n = _odd_taps(numtaps)
    m = np.arange(n) - (n - 1) / 2
    taps = np.sinc(2 * cutoff_hz / fs_hz * m) * np.blackman(n)
    return taps / taps.sum()


def gaussian_lowpass(cutoff_hz: float, fs_hz: float) -> np.ndarray:
    """Gaussian smoothing kernel with its -3 dB point at cutoff_hz.

    Unlike a long windowed sinc, an all-positive kernel cannot overshoot, so a
    step in slope (the onset of a skin conductance response) is smoothed
    without Gibbs ringing that would masquerade as a dip or a small response.
    """
    _check_band(cutoff_hz, fs_hz)
    sigma = math.sqrt(math.log(2.0)) / (2 * math.pi * cutoff_hz) * fs_hz
    half = int(math.ceil(4 * sigma))
    m = np.arange(-half, half + 1)
    taps = np.exp(-0.5 * (m / sigma) ** 2)
    return taps / taps.sum()


def fir_bandpass(low_hz: float, high_hz: float, fs_hz: float, numtaps: int) -> np.ndarray:
    if not low_hz < high_hz:
        raise ValueError("low_hz must be below high_hz")
    return fir_lowpass(high_hz, fs_hz, numtaps) - fir_lowpass(low_hz, fs_hz, numtaps)


def group_delay_samples(taps: np.ndarray) -> int:
    return (len(taps) - 1) // 2


def filter_zero_phase(x: np.ndarray, taps: np.ndarray) -> np.ndarray:
    """Apply a symmetric FIR without phase shift, padding edges by odd reflection."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 1:
        raise ValueError("x must be one-dimensional")
    if len(x) == 0:
        return x.copy()
    half = group_delay_samples(taps)
    pad = min(half, len(x) - 1)
    if pad > 0:
        head = 2 * x[0] - x[pad:0:-1]
        tail = 2 * x[-1] - x[-2:-pad - 2:-1]
        padded = np.concatenate([head, x, tail])
    else:
        padded = x
    # Pad further with edge values if the signal is shorter than the filter.
    extra = half - pad
    if extra > 0:
        padded = np.concatenate([np.full(extra, padded[0]), padded, np.full(extra, padded[-1])])
    full = np.convolve(padded, taps, mode="full")
    start = 2 * half
    return full[start:start + len(x)]


def moving_average(x: np.ndarray, width: int) -> np.ndarray:
    """Centered moving average with shrinking windows at the edges."""
    x = np.asarray(x, dtype=np.float64)
    if width <= 1 or len(x) == 0:
        return x.copy()
    csum = np.concatenate([[0.0], np.cumsum(x)])
    half = width // 2
    idx = np.arange(len(x))
    lo = np.clip(idx - half, 0, len(x))
    hi = np.clip(idx - half + width, 0, len(x))
    return (csum[hi] - csum[lo]) / (hi - lo)


def rolling_extreme(x: np.ndarray, width: int, mode: str) -> np.ndarray:
    """Centered rolling minimum or maximum (O(n * width), fine for short windows)."""
    x = np.asarray(x, dtype=np.float64)
    if width <= 1 or len(x) == 0:
        return x.copy()
    half = width // 2
    padded = np.concatenate([np.full(half, x[0]), x, np.full(width - half - 1, x[-1])])
    windows = np.lib.stride_tricks.sliding_window_view(padded, width)
    return windows.min(axis=1) if mode == "min" else windows.max(axis=1)


def contiguous_runs(sequence: np.ndarray) -> list[tuple[int, int]]:
    """Index ranges [start, stop) over which integer sequence numbers step by one."""
    sequence = np.asarray(sequence)
    if len(sequence) == 0:
        return []
    breaks = np.flatnonzero(np.diff(sequence) != 1) + 1
    edges = np.concatenate([[0], breaks, [len(sequence)]])
    return [(int(a), int(b)) for a, b in zip(edges[:-1], edges[1:])]


def mask_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Index ranges [start, stop) where a boolean mask is true."""
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return []
    padded = np.concatenate([[False], mask, [False]])
    change = np.flatnonzero(padded[1:] != padded[:-1])
    return [(int(a), int(b)) for a, b in zip(change[0::2], change[1::2])]


def parabolic_peak_offset(y_prev: float, y_peak: float, y_next: float) -> float:
    """Sub-sample offset in [-0.5, 0.5] of a local maximum from three samples."""
    denom = y_prev - 2 * y_peak + y_next
    if denom >= 0:
        return 0.0
    return float(np.clip(0.5 * (y_prev - y_next) / denom, -0.5, 0.5))
