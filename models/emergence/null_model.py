"""Null-model backbone for exploratory ATOM correlation searches.

"An agent discovered a correlation" is not evidence of anything until it is
compared with what the identical procedure finds by chance. Operators sample
smooth, autocorrelated fields with overlapping windows, so raw discovery counts
are large even between unrelated channels.

This module re-runs the exact discovery rule (Pearson |r| above the per-frame
threshold on each agent's last CORR_WINDOW observations) on circular-shift
surrogates: each channel of each agent's observation series is rotated by an
independent random offset. Autocorrelation and marginal distributions survive;
cross-channel alignment does not. The observed counts are then compared with the
surrogate distribution:

  * total discoveries: one-sided Monte Carlo p-value (Phipson & Smyth 2010, never zero);
  * each channel pair: p-value against the surrogate maximum over all pairs
    (a max-statistic, family-wise error control across the six pairs);
  * pairs involving the control channel are reported separately as a
    false-positive gauge.

In synthetic mode the generator injects known couplings (ch0 <- ch1 always,
ch3 <- ch2 during coherence windows), so the engine can also be scored against
known truth: does it find the injected pairs, and only those?
"""

from __future__ import annotations

from itertools import combinations
from typing import Any, Sequence

import numpy as np

PAIRS = tuple(combinations(range(4), 2))
SYNTHETIC_INJECTED = {(0, 1), (2, 3)}


def _pair_counts(series: np.ndarray, thresholds: np.ndarray, window: int) -> np.ndarray:
    """Discoveries per channel pair for one agent's (T, C) series, exactly as Agent.discover counts them."""
    t, c = series.shape
    if t < window:
        return np.zeros(len(PAIRS), dtype=np.int64)
    windows = np.lib.stride_tricks.sliding_window_view(series, window, axis=0)  # (T-W+1, C, W)
    centered = windows - windows.mean(axis=2, keepdims=True)
    norms = np.linalg.norm(centered, axis=2)
    usable = np.isfinite(norms) & (norms > 0)
    normalized = np.where(usable[..., None], centered / np.where(usable, norms, 1.0)[..., None], 0.0)
    corr = np.clip(np.einsum("fiw,fjw->fij", normalized, normalized), -1.0, 1.0)
    thresh = thresholds[window - 1:]
    counts = np.zeros(len(PAIRS), dtype=np.int64)
    for k, (i, j) in enumerate(PAIRS):
        hit = usable[:, i] & usable[:, j] & (np.abs(corr[:, i, j]) > thresh)
        counts[k] = int(hit.sum())
    return counts


def discovery_counts(history: np.ndarray, thresholds: Sequence[float], window: int) -> np.ndarray:
    """Per-pair discovery counts summed over agents. history: (frames, agents, channels)."""
    thresholds = np.asarray(thresholds, dtype=np.float64)
    return sum((_pair_counts(history[:, a, :], thresholds, window) for a in range(history.shape[1])),
               np.zeros(len(PAIRS), dtype=np.int64))


def circular_shift_null(history: Sequence[np.ndarray] | np.ndarray, thresholds: Sequence[float], window: int,
                        surrogates: int, seed: int, synthetic: bool = False) -> dict[str, Any]:
    """Compare observed discoveries with circular-shift surrogates of the same observations."""
    history = np.asarray(history, dtype=np.float64)
    frames, agents, channels = history.shape
    observed = discovery_counts(history, thresholds, window)
    result: dict[str, Any] = {"method": "CIRCULAR_SHIFT_SURROGATE", "surrogates": int(surrogates), "window": int(window),
                              "observed_total": int(observed.sum())}
    if frames < 2 * window + 1 or surrogates < 1:
        result.update({"status": "INSUFFICIENT_LENGTH" if frames < 2 * window + 1 else "NOT_RUN",
                       "note": f"Circular-shift surrogates need at least {2 * window + 1} frames; got {frames}."})
        return result
    rng = np.random.default_rng(seed)
    null = np.zeros((surrogates, len(PAIRS)), dtype=np.int64)
    for s in range(surrogates):
        shifted = np.empty_like(history)
        for a in range(agents):
            for ch in range(channels):
                shifted[:, a, ch] = np.roll(history[:, a, ch], int(rng.integers(window, frames - window + 1)))
        null[s] = discovery_counts(shifted, thresholds, window)
    totals, pair_max = null.sum(axis=1), null.max(axis=1)
    pairs = {}
    for k, (i, j) in enumerate(PAIRS):
        entry = {"observed": int(observed[k]), "null_mean": round(float(null[:, k].mean()), 3),
                 "p_fwer": round((1 + int(np.sum(pair_max >= observed[k]))) / (surrogates + 1), 6),
                 "involves_control": 3 in (i, j)}
        if synthetic:
            entry["injected_by_generator"] = (i, j) in SYNTHETIC_INJECTED
        pairs[f"ch{i}-ch{j}"] = entry
    p_total = (1 + int(np.sum(totals >= observed.sum()))) / (surrogates + 1)
    result.update({
        "status": "COMPUTED",
        "null_total_mean": round(float(totals.mean()), 3),
        "null_total_p95": float(np.percentile(totals, 95)),
        "p_total": round(p_total, 6),
        "excess_over_null_mean": round(float(observed.sum() - totals.mean()), 3),
        "pairs": pairs,
        "pairs_significant_fwer_0_05": sorted(k for k, v in pairs.items() if v["p_fwer"] < 0.05),
        "interpretation": ("Counts are exploratory. A pair is distinguishable from chance alignment only if its FWER "
                           "p-value is small; even then it is a correlation in model fields, not a causal or physical claim."),
    })
    if synthetic:
        found = {k for k in result["pairs_significant_fwer_0_05"]}
        injected = {f"ch{i}-ch{j}" for i, j in SYNTHETIC_INJECTED}
        result["known_truth_score"] = {"injected_pairs": sorted(injected), "injected_found": sorted(found & injected),
                                       "false_pairs_found": sorted(found - injected)}
    return result
