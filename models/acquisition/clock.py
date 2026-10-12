"""Host-to-device clock mapping from what a host can actually observe.

A device that numbers its samples on its own oscillator (an ADC's data-ready,
a FIFO's sample counter) states exact intervals in its own ticks, but not when
a tick happened on the host's clock, and not how long a tick really is: an
internal oscillator may be off by a fraction of a percent. The host observes
two kinds of event, and each bounds the mapping from one side:

  receipt   sample k arrived at host time y. It was taken no later than that:
            T(k) <= y. Every receipt is an upper bound.
  probe     the host sent something at host time y that the device stamped
            into sample k (a marker, a trigger echo). The sample was taken no
            earlier than the send, less any slack the device's own handling
            allows: T(k) >= y - slack. Every probe is a lower bound.

Over a stretch where the oscillator is steady, T(k) = a + s * k, and the bounds
are linear constraints on (a, s). Only hull vertices can bind: the lower convex
hull of the receipts and the upper convex hull of the probes.

  MinimumDelayClock   online, causal: the line under every receipt so far that
                      minimizes the total delay it implies (Moon, Skelly and
                      Towsley, "Estimation and removal of clock skew from
                      network delay measurements", IEEE INFOCOM 1999). It
                      touches the receipts' lower hull at their mean tick, so
                      it never places a sample after it was received.
  bound_mapping       offline: the interval of T(k) at a chosen tick, and of
                      the tick length, consistent with every receipt and probe
                      and the oscillator's stated tolerance. Without probes the
                      lower side is unbounded, and is reported as such: a
                      constant transport latency cannot be seen from receipts.

Nothing here assumes a latency distribution. The estimate is the mapping with
the least delay the receipts allow; the bounds are what the observations prove.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


def _cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def lower_hull(x: Sequence[float], y: Sequence[float]) -> list[int]:
    """Indices of the lower convex hull of points sorted by x (Andrew's monotone chain)."""
    hull: list[int] = []
    for i in range(len(x)):
        while len(hull) >= 2 and _cross((x[hull[-2]], y[hull[-2]]), (x[hull[-1]], y[hull[-1]]), (x[i], y[i])) <= 0:
            hull.pop()
        hull.append(i)
    return hull


def upper_hull(x: Sequence[float], y: Sequence[float]) -> list[int]:
    return lower_hull(x, [-v for v in y])


@dataclass(frozen=True)
class Line:
    """Host time T(k) = offset_us + slope_us * (k - tick0)."""

    tick0: float
    offset_us: float
    slope_us: float

    def at(self, tick: float | np.ndarray) -> float | np.ndarray:
        return self.offset_us + self.slope_us * (np.asarray(tick, dtype=np.float64) - self.tick0)

    def ppm(self, nominal_slope_us: float) -> float:
        """How much longer a tick is than nominal, in parts per million (positive: the device runs slow)."""
        return (self.slope_us / nominal_slope_us - 1.0) * 1e6


def _supporting_offset(xs: np.ndarray, ys: np.ndarray, slope: float, tick0: float) -> float:
    """The highest line of this slope that stays under every point, as its value at tick0."""
    return float(np.min(ys - slope * (xs - tick0)))


def minimum_delay_line(ticks: Sequence[float], receipts_us: Sequence[float],
                       slope_bounds_us: tuple[float, float] | None = None) -> Line:
    """Offline Moon-Skelly-Towsley estimate over ticks sorted ascending (ties allowed)."""
    x = np.asarray(ticks, dtype=np.float64)
    y = np.asarray(receipts_us, dtype=np.float64)
    if len(x) == 0:
        raise ValueError("no receipts")
    order = np.lexsort((y, x))
    x, y = x[order], y[order]
    keep = np.concatenate([[True], np.diff(x) > 0])        # one receipt per tick: the earliest
    x, y = x[keep], y[keep]
    hull = lower_hull(x, y)
    return _line_at_mean(x[hull], y[hull], float(np.mean(x)), slope_bounds_us)


def _line_at_mean(hx: np.ndarray, hy: np.ndarray, mean: float, bounds: tuple[float, float] | None) -> Line:
    if len(hx) == 1:
        slope = float(np.mean(bounds)) if bounds else 0.0
        return Line(mean, _supporting_offset(hx, hy, slope, mean), slope)
    j = int(np.searchsorted(hx, mean, side="right"))
    j = min(max(j, 1), len(hx) - 1)
    slope = float((hy[j] - hy[j - 1]) / (hx[j] - hx[j - 1]))
    if bounds is not None:
        slope = float(np.clip(slope, bounds[0], bounds[1]))
    return Line(mean, _supporting_offset(hx, hy, slope, mean), slope)


class MinimumDelayClock:
    """Causal minimum-delay mapping over one stretch of a device's ticks.

    Ticks must not decrease. A receipt for a tick already seen keeps the earlier
    of the two. The current line never lies above any receipt added so far.
    """

    def __init__(self, nominal_slope_us: float, tolerance: float) -> None:
        if nominal_slope_us <= 0 or not 0 <= tolerance < 1:
            raise ValueError("need a positive nominal tick length and a tolerance in [0, 1)")
        self.nominal_slope_us = float(nominal_slope_us)
        self.bounds = (nominal_slope_us * (1 - tolerance), nominal_slope_us * (1 + tolerance))
        self.hx: list[float] = []
        self.hy: list[float] = []
        self.count = 0
        self.tick_sum = 0.0
        self.first_tick: float | None = None
        self.last_tick: float | None = None

    def add(self, tick: float, receipt_us: float) -> None:
        tick, receipt_us = float(tick), float(receipt_us)
        if self.last_tick is not None and tick < self.last_tick:
            raise ValueError("ticks must not decrease within one stretch of a clock")
        if self.last_tick is not None and tick == self.last_tick:
            if receipt_us < self.hy[-1]:
                self.hy[-1] = receipt_us
                self._repair()
            return
        self.count += 1
        self.tick_sum += tick
        if self.first_tick is None:
            self.first_tick = tick
        self.last_tick = tick
        self.hx.append(tick)
        self.hy.append(receipt_us)
        self._repair()

    def _repair(self) -> None:
        hx, hy = self.hx, self.hy
        while len(hx) >= 3 and _cross((hx[-3], hy[-3]), (hx[-2], hy[-2]), (hx[-1], hy[-1])) <= 0:
            del hx[-2], hy[-2]

    def line(self) -> Line | None:
        if not self.count:
            return None
        return _line_at_mean(np.asarray(self.hx), np.asarray(self.hy), self.tick_sum / self.count, self.bounds)


@dataclass(frozen=True)
class MappingBounds:
    """What the observations prove about T(tick) and the tick length."""

    tick: float
    estimate_us: float               # the minimum-delay line at `tick`
    latest_us: float | None          # T(tick) can be no later than this (receipts)
    earliest_us: float | None        # and no earlier than this (probes), or None: unbounded
    slope_us: float
    slope_min_us: float | None
    slope_max_us: float | None
    receipts: int                    # receipts on the lower hull (the only ones that can bind)
    probes: int
    consistent: bool                 # False: no line satisfies every receipt and probe

    @property
    def width_us(self) -> float | None:
        if self.latest_us is None or self.earliest_us is None:
            return None
        return self.latest_us - self.earliest_us

    def to_dict(self, nominal_slope_us: float) -> dict[str, float]:
        out = {"tick": self.tick, "estimate_us": self.estimate_us, "slope_us": self.slope_us,
               "ppm": (self.slope_us / nominal_slope_us - 1) * 1e6, "hull_receipts": self.receipts,
               "probes": self.probes, "consistent": float(self.consistent)}
        for key in ("latest_us", "earliest_us", "slope_min_us", "slope_max_us", "width_us"):
            value = getattr(self, key)
            if value is not None:
                out[key] = float(value)
        if self.slope_min_us is not None and self.slope_max_us is not None:
            out["ppm_min"] = (self.slope_min_us / nominal_slope_us - 1) * 1e6
            out["ppm_max"] = (self.slope_max_us / nominal_slope_us - 1) * 1e6
        return out


def bound_mapping(receipt_ticks: Sequence[float], receipts_us: Sequence[float], probe_ticks: Sequence[float],
                  probes_us: Sequence[float], slope_bounds_us: tuple[float, float], tick: float | None = None,
                  mean_tick: float | None = None, tolerance_us: float = 1e-6) -> MappingBounds:
    """Every line a + s * (k - tick) with receipts above it, probes below it, and s within its bounds.

    The receipts may be only the lower hull of all receipts (MinimumDelayClock
    keeps it); then pass the mean tick of all of them, which places the
    minimum-delay estimate. The feasible set is a convex polygon in (s, a); its
    extreme values of a and s are attained at vertices, which are pairwise
    intersections of hull constraints and slope bounds.
    """
    rx, ry = np.asarray(receipt_ticks, dtype=np.float64), np.asarray(receipts_us, dtype=np.float64)
    px, py = np.asarray(probe_ticks, dtype=np.float64), np.asarray(probes_us, dtype=np.float64)
    if not len(rx):
        raise ValueError("bounding a mapping needs at least one receipt")
    order = np.lexsort((ry, rx))
    rx, ry = rx[order], ry[order]
    keep = np.concatenate([[True], np.diff(rx) > 0])
    rx, ry = rx[keep], ry[keep]
    lower = lower_hull(rx, ry)
    estimate = _line_at_mean(rx[lower], ry[lower], float(np.mean(rx)) if mean_tick is None else float(mean_tick),
                             slope_bounds_us)
    tick = estimate.tick0 if tick is None else float(tick)
    if len(px):
        order = np.lexsort((-py, px))
        px, py = px[order], py[order]
        keep = np.concatenate([np.diff(px) > 0, [True]])   # one probe per tick: the latest send
        px, py = px[keep], py[keep]
        upper = upper_hull(px, py)
    else:
        upper = []
    # Constraint rows: sign * (a + s * d) <= sign * c, i.e. a <= c - s d (receipts) or a >= c - s d (probes).
    d = np.concatenate([rx[lower] - tick, px[upper] - tick]) if upper else rx[lower] - tick
    c = np.concatenate([ry[lower], py[upper]]) if upper else ry[lower]
    sign = np.concatenate([np.ones(len(lower)), -np.ones(len(upper))])
    smin, smax = slope_bounds_us
    candidates: list[tuple[float, float]] = []
    for s in (smin, smax):
        candidates += [(s, float(ci - s * di)) for ci, di in zip(c, d)]
    di, dj = np.meshgrid(d, d, indexing="ij")
    ci, cj = np.meshgrid(c, c, indexing="ij")
    with np.errstate(divide="ignore", invalid="ignore"):
        s = (ci - cj) / (di - dj)
    mask = np.triu(np.isfinite(s), 1) & (s >= smin) & (s <= smax)
    candidates += [(float(sv), float(cv - sv * dv)) for sv, cv, dv in zip(s[mask], ci[mask], di[mask])]
    feasible = [(sv, av) for sv, av in candidates
                if np.all(sign * (av + sv * d) <= sign * c + tolerance_us)]
    est_at = float(estimate.at(tick))
    if not feasible:
        return MappingBounds(tick, est_at, None, None, estimate.slope_us, None, None, len(lower), len(px), False)
    slopes = np.array([f[0] for f in feasible])
    offsets = np.array([f[1] for f in feasible])
    latest = float(offsets.max())
    earliest = float(offsets.min()) if upper else None
    slope_min = float(slopes.min()) if upper else None
    slope_max = float(slopes.max()) if upper else None
    return MappingBounds(tick, est_at, latest, earliest, estimate.slope_us, slope_min, slope_max, len(lower), len(px),
                         True)
