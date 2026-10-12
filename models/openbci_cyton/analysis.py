"""What a Cyton session can establish, computed from its raw records alone.

Phantom. The ADS1299 can connect every channel to an internal square wave or
short its inputs (activateAllChannelsToTestCondition). Nothing from a body can
reach a channel in either condition, so these runs are electronic phantoms with
known truth from the datasheet and the firmware. Only what the sources make
exact is judged:

  TEST_SIGNAL_PERIOD_EXACT     the square wave and the ADC share fCLK, so its
                               edges recur every 256 (SLOW) or 128 (FAST) ADC
                               samples, whatever the oscillator's error. Every
                               period between crossings in a contiguous run
                               must be that count to within 0.05 sample. This
                               checks the whole chain: ADC, PIC32, radios,
                               dongle, USB, framing, and sign extension.
  TEST_SIGNAL_TWO_LEVELS       away from edges the wave sits on two levels; the
                               spread on each is under 1 % of the step
  TEST_SIGNAL_CHANNEL_AGREEMENT  one signal feeds every channel: each step is
                               within the datasheet's 2 % test-signal accuracy
                               of the median channel
  TEST_SIGNAL_2X_OVER_1X       the 2x setting is twice the 1x (4 %: two 2 % terms)
  TEST_SIGNAL_AMPLITUDE        REPORTED, not judged: the datasheet states the
                               amplitude two incompatible ways (protocol.py)
  SHORTED_INPUT_NOISE          input-referred noise with the inputs shorted,
                               against the datasheet's 0.14 uVrms (gain 24,
                               250 SPS); a channel over five times that fails.
                               The factor of five is CIRCLE's margin, not TI's.
  SAMPLE_CLOCK_RATE            the ADC's rate against the host clock, within the
                               datasheet's +-2.5 % (+-0.5 % at 25 degC is noted)
  CLOCK_PROBES_CONSISTENT      markers sent by the host and seen in the data
                               bound the mapping from below; receipts from above
  REGISTERS_READ_BACK          the ADC's registers, read over "?", hold the
                               configuration the scaling assumes
  FRAMING_ALL_LOSSES_DECLARED  every missing sample was declared by the bridge

The verdict is FAIL when any judged check fails, INCOMPLETE when a check
could not be evaluated (too short a segment, too few periods), and PASS only
when every check that can be judged was judged and passed.

Channel quality and ECG are measurements of a person when electrodes are
attached. They are labeled as such and claim nothing clinical: the R-peak
detector is a Pan-Tompkins-style energy detector scored only against the
simulator's known beats, and RMSSD here is not a clinical HRV measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from models.acquisition.clock import MinimumDelayClock, bound_mapping
from models.physiology.streams import Gap, RawSession, Stream

from . import protocol as p
from .streams import DAISY_STREAM, EXG_STREAM

PERIOD_TOLERANCE_SAMPLES = 0.05
PLATEAU_SPREAD_LIMIT = 0.01
NOISE_LIMIT_FACTOR = 5.0
RATIO_TOLERANCE = 2 * p.TEST_SIGNAL_ACCURACY


@dataclass(frozen=True)
class Run:
    """Rows of one stream whose ADC samples follow each other with nothing lost in between."""

    start: int
    stop: int
    epoch: int


def runs(stream: Stream, step: int = 1) -> list[Run]:
    if not len(stream):
        return []
    epoch, index = stream.columns["epoch"], stream.columns["sample_index"]
    breaks = np.flatnonzero((np.diff(epoch) != 0) | (np.diff(index) != step)) + 1
    starts = np.concatenate([[0], breaks])
    stops = np.concatenate([breaks, [len(stream)]])
    return [Run(int(a), int(b), int(epoch[a])) for a, b in zip(starts, stops)]


def microvolts(stream: Stream, channel: str, descriptors: dict[str, float]) -> np.ndarray:
    return stream.columns[channel].astype(np.float64) * descriptors[f"{channel}_uv_per_count"]


def ranges(stream: Stream, rows: Iterable[int] | slice | None = None) -> list[dict[str, Any]]:
    seq = stream.sequence if rows is None else stream.sequence[rows]
    values = np.unique(np.asarray(seq, dtype=np.int64))
    if not len(values):
        return []
    breaks = np.flatnonzero(np.diff(values) != 1) + 1
    return [{"stream_id": stream.name, "first_sequence": int(r[0]), "last_sequence": int(r[-1])}
            for r in np.split(values, breaks) if len(r)]


def check(check_id: str, status: str, criterion: str, source: str, **measured: Any) -> dict[str, Any]:
    return {"id": check_id, "status": status, "criterion": criterion, "source": source, "measured": measured}


# ----------------------------------------------------------- square wave
def square_wave(pieces: list[tuple[np.ndarray, np.ndarray]], period: int, step: int) -> dict[str, float] | None:
    """Levels, step, crossing regularity, and plateau spread of a test signal over one epoch.

    `pieces` are the epoch's contiguous runs as (sample_index, microvolts). Crossings are found inside runs;
    periods are measured between any two rising crossings of the epoch, because the unwrapped sample index
    stays exact across a declared loss.
    """
    uv_all = np.concatenate([uv for _, uv in pieces]) if pieces else np.zeros(0)
    if len(uv_all) < 2 * period // step:
        return None
    low_ref, high_ref = np.percentile(uv_all, [5, 95])
    high_all = uv_all >= (low_ref + high_ref) / 2
    if high_all.all() or not high_all.any():
        return None
    level_low, level_high = float(np.median(uv_all[~high_all])), float(np.median(uv_all[high_all]))
    mid = (level_low + level_high) / 2
    rising: list[float] = []
    plateau_low: list[np.ndarray] = []
    plateau_high: list[np.ndarray] = []
    crossings = 0
    for index, uv in pieces:
        if len(uv) < 2:
            continue
        a, b = uv[:-1] - mid, uv[1:] - mid
        cross = np.flatnonzero((a < 0) != (b < 0))
        crossings += len(cross)
        position = index[cross] + step * (mid - uv[cross]) / (uv[cross + 1] - uv[cross])
        rising += list(position[b[cross] >= 0])
        near = np.zeros(len(uv), dtype=bool)
        for c in cross:
            near[max(c - 3 // step - 1, 0):c + 3 // step + 3] = True
        near[:3 // step + 1] = near[-(3 // step + 1):] = True          # a run's ends may sit on an unseen edge
        plateau_low.append(uv[~near & (uv < mid)])
        plateau_high.append(uv[~near & (uv >= mid)])
    rising_sorted = np.sort(np.array(rising))
    deviations, spanned = [], 0
    for first, second in zip(rising_sorted[:-1], rising_sorted[1:]):
        periods = round((second - first) / period)
        if periods >= 1:
            deviations.append((second - first) - periods * period)
            spanned += periods
    low = np.concatenate(plateau_low) if plateau_low else np.zeros(0)
    high = np.concatenate(plateau_high) if plateau_high else np.zeros(0)
    spread = max(float(np.std(low)) if len(low) else 0.0, float(np.std(high)) if len(high) else 0.0)
    return {"level_low_uv": level_low, "level_high_uv": level_high, "step_uv": level_high - level_low,
            "periods_checked": float(spanned),
            "max_period_deviation_samples": float(np.max(np.abs(deviations))) if deviations else float("nan"),
            "plateau_spread_uv": spread, "crossings": float(crossings)}


def _segment_rows(stream: Stream, epochs: set[int]) -> list[Run]:
    return [r for r in runs(stream, 2 if stream.name in (EXG_STREAM, DAISY_STREAM) and _daisy(stream) else 1)
            if r.epoch in epochs]


def _daisy(stream: Stream) -> bool:
    index = stream.columns["sample_index"]
    return len(index) > 1 and bool(np.all(np.diff(index)[np.diff(stream.columns["epoch"]) == 0] % 2 == 0))


def _exg_streams(raw: RawSession) -> list[Stream]:
    return [raw.streams[n] for n in (EXG_STREAM, DAISY_STREAM) if n in raw.streams and len(raw.streams[n])]


def _channels(stream: Stream) -> list[str]:
    return [c for c in stream.columns if c.startswith("ch")]


def phantom_scorecard(raw: RawSession, segments: list[dict[str, Any]], clocks: list[MinimumDelayClock],
                      probes: list[tuple[int, int, int]], register_problems: list[str]) -> dict[str, Any]:
    """Every judged and reported check over the phantom segments. `probes`: (epoch, sample_index, sent_us)."""
    checks: list[dict[str, Any]] = []
    steps: dict[str, dict[str, float]] = {}
    for seg in segments:
        label = seg["label"]
        signal = p.TEST_SIGNALS.get(label)
        if signal is None:
            continue
        epochs = set(seg["epochs"])
        per_channel: dict[str, dict[str, float]] = {}
        noise: dict[str, dict[str, float]] = {}
        for stream in _exg_streams(raw):
            step = 2 if _daisy(stream) else 1
            desc = raw.descriptors[stream.name]
            segment_runs = _segment_rows(stream, epochs)
            if signal.frequency in ("SLOW", "FAST"):
                for epoch in sorted({r.epoch for r in segment_runs}):
                    mine = [r for r in segment_runs if r.epoch == epoch]
                    for channel in _channels(stream):
                        uv_all = microvolts(stream, channel, desc)
                        pieces = [(stream.columns["sample_index"][r.start:r.stop].astype(np.float64),
                                   uv_all[r.start:r.stop]) for r in mine]
                        result = square_wave(pieces, p.TEST_SIGNAL_PERIOD_SAMPLES[signal.frequency], step)
                        if result and (channel not in per_channel
                                       or result["periods_checked"] > per_channel[channel]["periods_checked"]):
                            per_channel[channel] = result
                continue
            for run in segment_runs:
                rows = slice(run.start, run.stop)
                for channel in _channels(stream):
                    uv = microvolts(stream, channel, desc)[rows]
                    if signal.input_type == "SHORTED" and len(uv) >= 250 // step:
                        windows = [uv[i:i + 250 // step] for i in range(0, len(uv) - 250 // step + 1, 250 // step)]
                        detrended = uv - np.polyval(np.polyfit(np.arange(len(uv)), uv, 1), np.arange(len(uv)))
                        current = noise.get(channel)
                        if current is None or len(uv) > current["samples"]:
                            noise[channel] = {"uvrms": float(np.std(detrended)), "samples": float(len(uv)),
                                              "uvpp_median_1s": float(np.median([np.ptp(w) for w in windows]))}
                    elif signal.frequency == "DC":
                        per_channel[channel] = {"mean_uv": float(np.mean(uv)), "std_uv": float(np.std(uv))}
        if signal.frequency in ("SLOW", "FAST"):
            expected = p.TEST_SIGNAL_PERIOD_SAMPLES[signal.frequency]
            measured = [r["max_period_deviation_samples"] for r in per_channel.values() if r["periods_checked"]]
            worst = max(measured, default=float("nan"))
            enough = bool(per_channel) and min(r["periods_checked"] for r in per_channel.values()) >= 3
            status = ("FAIL" if measured and worst > PERIOD_TOLERANCE_SAMPLES else
                      "PASS" if enough else "NOT_EVALUATED")
            checks.append(check(f"TEST_SIGNAL_PERIOD_EXACT:{label}", status,
                                f"every rising-edge period is {expected} ADC samples to within "
                                f"{PERIOD_TOLERANCE_SAMPLES} sample, on every channel, over at least 3 periods",
                                "datasheet CONFIG2 CAL_FREQ and CONFIG1 DR share fCLK",
                                worst_deviation_samples=worst, channels=len(per_channel),
                                periods_min=min((r["periods_checked"] for r in per_channel.values()), default=0.0)))
            spreads = {c: r["plateau_spread_uv"] / r["step_uv"] for c, r in per_channel.items() if r["step_uv"] > 0}
            checks.append(check(f"TEST_SIGNAL_TWO_LEVELS:{label}",
                                "PASS" if spreads and max(spreads.values()) <= PLATEAU_SPREAD_LIMIT else
                                "FAIL" if spreads else "NOT_EVALUATED",
                                f"spread on each level under {PLATEAU_SPREAD_LIMIT:.0%} of the step", "CIRCLE criterion",
                                worst_spread_fraction=max(spreads.values(), default=float("nan"))))
            step_values = {c: r["step_uv"] for c, r in per_channel.items()}
            if step_values:
                median = float(np.median(list(step_values.values())))
                worst_rel = max(abs(v / median - 1) for v in step_values.values()) if median else float("inf")
                checks.append(check(f"TEST_SIGNAL_CHANNEL_AGREEMENT:{label}",
                                    "PASS" if worst_rel <= p.TEST_SIGNAL_ACCURACY else "FAIL",
                                    f"each channel's step within {p.TEST_SIGNAL_ACCURACY:.0%} of the median channel",
                                    "datasheet test signal accuracy +-2 %", median_step_uv=median,
                                    worst_relative_difference=worst_rel))
                steps[label] = step_values
                k = signal.amplitude_k
                checks.append(check(f"TEST_SIGNAL_AMPLITUDE:{label}", "REPORTED",
                                    "not judged: the datasheet's register table and electrical table disagree",
                                    "datasheet CONFIG2 CAL_AMP; electrical characteristics", median_step_uv=median,
                                    half_step_over_register_table=median / 2 / (p.TEST_SIGNAL_AMPLITUDE_REGISTER_TABLE_V[k] * 1e6),
                                    half_step_over_electrical_table=median / 2 / (p.TEST_SIGNAL_AMPLITUDE_ELECTRICAL_TABLE_V[k] * 1e6)))
            seg["result"] = per_channel
        elif signal.input_type == "SHORTED":
            limit = NOISE_LIMIT_FACTOR * p.NOISE_GAIN24_250SPS_UVRMS
            worst = max((v["uvrms"] for v in noise.values()), default=float("nan"))
            checks.append(check("SHORTED_INPUT_NOISE", "PASS" if noise and worst <= limit else
                                "FAIL" if noise else "NOT_EVALUATED",
                                f"every channel under {limit:.2f} uVrms ({NOISE_LIMIT_FACTOR:g}x the datasheet's "
                                f"{p.NOISE_GAIN24_250SPS_UVRMS} uVrms; the factor is CIRCLE's margin)",
                                "datasheet Table 4, gain 24, 250 SPS", worst_uvrms=worst,
                                median_uvpp_1s=float(np.median([v["uvpp_median_1s"] for v in noise.values()]))
                                if noise else float("nan"), datasheet_uvpp=p.NOISE_GAIN24_250SPS_UVPP))
            seg["result"] = noise
        elif signal.frequency == "DC":
            checks.append(check("TEST_SIGNAL_DC", "REPORTED", "not judged: amplitude as for the pulses",
                                "datasheet CONFIG2 CAL_FREQ = 11",
                                median_uv=float(np.median([r["mean_uv"] for r in per_channel.values()]))
                                if per_channel else float("nan")))
            seg["result"] = per_channel
    pairs = [(steps[a], steps[b]) for a, b in (("pulse-2x-slow", "pulse-1x-slow"), ("pulse-2x-fast", "pulse-1x-fast"))
             if a in steps and b in steps]
    if pairs:
        ratios = [two[c] / one[c] for two, one in pairs for c in one if c in two and one[c] > 0]
        worst = max(abs(r / 2 - 1) for r in ratios)
        checks.append(check("TEST_SIGNAL_2X_OVER_1X", "PASS" if worst <= RATIO_TOLERANCE else "FAIL",
                            f"2x step / 1x step = 2 to within {RATIO_TOLERANCE:.0%} on every channel",
                            "datasheet CONFIG2 CAL_AMP", ratio_min=min(ratios), ratio_max=max(ratios)))
    checks += clock_checks(clocks, probes)
    checks.append(check("REGISTERS_READ_BACK", "PASS" if not register_problems else "FAIL",
                        "the ADC registers hold the configuration the scaling assumes", "\"?\" register dump",
                        problems=len(register_problems)))
    undeclared = [g for g in _gaps(raw) if g.cause.startswith(("UNDECLARED", "HOST_"))]
    checks.append(check("FRAMING_ALL_LOSSES_DECLARED", "PASS" if not undeclared else "FAIL",
                        "every missing sample declared by the bridge with its cause", "ingestion boundary",
                        gaps=len(_gaps(raw)), undeclared=len(undeclared)))
    statuses = {c["status"] for c in checks}
    verdict = ("FAIL" if "FAIL" in statuses else "INCOMPLETE" if "NOT_EVALUATED" in statuses or "PASS" not in statuses
               else "PASS")
    return {"verdict": verdict, "checks": checks, "segments": [{k: v for k, v in s.items()} for s in segments]}


def _gaps(raw: RawSession) -> list[Gap]:
    return [g for g in raw.gaps if g.stream_id in (EXG_STREAM, DAISY_STREAM)]


# ----------------------------------------------------------------- clock
def clock_bounds(clocks: list[MinimumDelayClock], probes: list[tuple[int, int, int]]) -> list[dict[str, float]]:
    out = []
    for number, clock in enumerate(clocks):
        if clock.count < 2:
            continue
        mine = [(i, sent) for e, i, sent in probes if e == number]
        bounds = bound_mapping(clock.hx, clock.hy, [i for i, _ in mine], [s - p.NOMINAL_PERIOD_US for _, s in mine],
                               clock.bounds, mean_tick=clock.tick_sum / clock.count)
        entry = bounds.to_dict(p.NOMINAL_PERIOD_US)
        entry.update({"epoch": float(number), "first_tick": float(clock.first_tick), "last_tick": float(clock.last_tick),
                      "samples": float(clock.count),
                      "duration_s": (clock.last_tick - clock.first_tick) * bounds.slope_us / 1e6})
        out.append(entry)
    return out


def clock_checks(clocks: list[MinimumDelayClock], probes: list[tuple[int, int, int]]) -> list[dict[str, Any]]:
    mapped = [b for b in clock_bounds(clocks, probes) if b["duration_s"] >= 2.0]
    if not mapped:
        return [check("SAMPLE_CLOCK_RATE", "NOT_EVALUATED", "needs an epoch of at least 2 s", "datasheet")]
    longest = max(mapped, key=lambda b: b["duration_s"])
    ppm = longest["ppm"]
    out = [check("SAMPLE_CLOCK_RATE", "PASS" if abs(ppm) <= p.OSCILLATOR_TOLERANCE_FULL * 1e6 else "FAIL",
                 f"ADC rate within +-{p.OSCILLATOR_TOLERANCE_FULL:.1%} of 250 SPS against the host clock",
                 "datasheet internal clock accuracy", ppm=ppm, rate_hz=1e6 / longest["slope_us"],
                 within_25c_tolerance=float(abs(ppm) <= p.OSCILLATOR_TOLERANCE_25C * 1e6),
                 epoch_duration_s=longest["duration_s"])]
    probed = [b for b in mapped if b["probes"] >= 2]
    if probed:
        widths = [b["width_us"] for b in probed if "width_us" in b]
        out.append(check("CLOCK_PROBES_CONSISTENT", "PASS" if all(b["consistent"] for b in probed) else "FAIL",
                         "one line lies under every receipt and over every marker probe (less one sample of slack)",
                         "MinimumDelayClock and bound_mapping", probes=sum(b["probes"] for b in probed),
                         worst_width_us=max(widths) if widths else float("nan")))
    return out


# ------------------------------------------------------- channel quality
def channel_quality(raw: RawSession) -> list[dict[str, Any]]:
    """Per channel: railed fraction, flatness, band RMS (1-40 Hz), and line-noise share (49-51 and 59-61 Hz)."""
    out = []
    for stream in _exg_streams(raw):
        desc = raw.descriptors[stream.name]
        fs = desc["nominal_rate_hz"]
        longest = max(runs(stream, 2 if _daisy(stream) else 1), key=lambda r: r.stop - r.start)
        rows = slice(longest.start, longest.stop)
        for channel in _channels(stream):
            codes = stream.columns[channel]
            railed = float(np.mean((codes >= p.ADC_MAX_CODE - 1) | (codes <= p.ADC_MIN_CODE + 1)))
            uv = microvolts(stream, channel, desc)[rows]
            entry = {"stream": stream.name, "channel": channel, "railed_fraction": railed, "rows": len(stream),
                     "ranges": ranges(stream, rows)}
            if len(uv) >= fs * 2:
                spectrum = np.abs(np.fft.rfft((uv - uv.mean()) * np.hanning(len(uv)))) ** 2
                freq = np.fft.rfftfreq(len(uv), 1 / fs)
                band = (freq >= 1) & (freq <= 40)
                line = ((freq >= 49) & (freq <= 51)) | ((freq >= 59) & (freq <= 61))
                total = float(spectrum[(freq >= 1) & (freq <= fs / 2 - 1)].sum()) or 1.0
                filtered = np.fft.irfft(np.where(band, np.fft.rfft(uv - uv.mean()), 0), len(uv))
                entry.update({"band_rms_uv": float(np.std(filtered)), "line_noise_share": float(spectrum[line].sum() / total),
                              "std_uv": float(np.std(uv)), "flat": float(np.std(uv) < 0.5)})
            out.append(entry)
    return out


# ------------------------------------------------------------------- ECG
def _bandpass(x: np.ndarray, fs: float, low: float, high: float) -> np.ndarray:
    spectrum = np.fft.rfft(x - np.mean(x))
    freq = np.fft.rfftfreq(len(x), 1 / fs)
    taper = np.clip((freq - low + 1) / 2, 0, 1) * np.clip((high + 2 - freq) / 4, 0, 1)
    return np.fft.irfft(spectrum * taper, len(x))


def r_peaks(uv: np.ndarray, fs: float) -> np.ndarray:
    """Fractional row positions of R peaks in one contiguous run (Pan-Tompkins-style energy detector)."""
    if len(uv) < fs * 3:
        return np.zeros(0)
    filtered = _bandpass(uv, fs, 5.0, 18.0)
    energy = np.gradient(filtered) ** 2
    width = max(int(round(0.15 * fs)), 1)
    integrated = np.convolve(energy, np.ones(width) / width, mode="same")
    threshold = 0.3 * np.percentile(integrated, 99)
    refractory = int(round(0.3 * fs))
    candidates = np.flatnonzero((integrated[1:-1] > threshold) & (integrated[1:-1] >= integrated[:-2])
                                & (integrated[1:-1] > integrated[2:])) + 1
    peaks: list[int] = []
    for c in candidates:
        if peaks and c - peaks[-1] < refractory:
            if integrated[c] > integrated[peaks[-1]]:
                peaks[-1] = int(c)
            continue
        peaks.append(int(c))
    if not peaks:
        return np.zeros(0)
    polarity = 1.0 if np.median([filtered[max(k - width, 0):k + width].max() for k in peaks]) >= \
        np.median([-filtered[max(k - width, 0):k + width].min() for k in peaks]) else -1.0
    reach = int(round(0.1 * fs))
    out = []
    for k in peaks:
        lo, hi = max(k - reach, 1), min(k + reach, len(uv) - 2)
        j = lo + int(np.argmax(polarity * filtered[lo:hi + 1]))
        y0, y1, y2 = polarity * filtered[j - 1:j + 2]
        denom = y0 - 2 * y1 + y2
        out.append(j + (0.5 * (y0 - y2) / denom if denom < 0 else 0.0))
    return np.unique(np.round(np.array(out), 6))


HOLE_GUARD_S = 0.05                   # a beat this close to a filled hole is not reported (half a QRS)
BRIDGEABLE_HOLE_S = 0.04              # shorter than any QRS: an interval may span a hole this short


def ecg_beats(raw: RawSession, channel: str, clocks: list[MinimumDelayClock]) -> dict[str, Any]:
    """R peaks on one channel, with times from each epoch's clock and intervals from the ADC's sample count.

    Detection runs over each epoch with lost samples filled by linear interpolation, which only the filters
    see: the sample index is exact across a declared loss, so one lost packet need not cost a beat. A peak
    within HOLE_GUARD_S of a filled sample is dropped, never reported from invented data.
    """
    stream = next((s for s in _exg_streams(raw) if channel in s.columns), None)
    if stream is None:
        declared = any(channel in s.columns for s in raw.streams.values())
        return {"stream": None, "channel": channel, "beats": [], "detections": [],
                "unavailable": "the channel holds no samples" if declared else "the board has no such channel"}
    desc = raw.descriptors[stream.name]
    fs = desc["nominal_rate_hz"]
    step = 2 if _daisy(stream) else 1
    uv = microvolts(stream, channel, desc)
    epoch_col, index_col = stream.columns["epoch"], stream.columns["sample_index"]
    beats = []
    guard = int(round(HOLE_GUARD_S * fs))
    for epoch in np.unique(epoch_col):
        rows = np.flatnonzero(epoch_col == epoch)
        slots = (index_col[rows] - index_col[rows[0]]) // step
        filled = np.full(int(slots[-1]) + 1, np.nan)
        filled[slots] = uv[rows]
        hole = np.isnan(filled)
        if hole.all() or len(filled) < fs * 3:
            continue
        known = np.flatnonzero(~hole)
        filled[hole] = np.interp(np.flatnonzero(hole), known, filled[known])
        near_hole = np.convolve(hole.astype(float), np.ones(2 * guard + 1), mode="same") > 0
        clock = clocks[int(epoch)] if int(epoch) < len(clocks) else None
        line = clock.line() if clock is not None else None
        for pos in r_peaks(filled, fs):
            slot = int(round(pos))
            guarded = bool(near_hole[min(slot, len(near_hole) - 1)])
            index = float(index_col[rows[0]]) + pos * step
            row = int(rows[np.searchsorted(slots, slot)]) if slot in set(slots.tolist()) else \
                int(rows[min(np.searchsorted(slots, slot), len(rows) - 1)])
            missing_before = int(np.sum(hole[:slot]))
            time_us = float(line.at(index)) if line is not None else float(stream.device_time_us[row])
            beats.append({"epoch": int(epoch), "row": row, "sample_index": index, "time_us": time_us,
                          "holes_before": missing_before, "near_hole": guarded,
                          "tick_us": line.slope_us if line is not None else p.NOMINAL_PERIOD_US})
    reported = [b for b in beats if not b["near_hole"]]
    return {"stream": stream.name, "channel": channel, "beats": reported, "detections": beats, "rate_hz": fs,
            "step": step, "dropped_near_holes": len(beats) - len(reported)}


def hrv_windows(raw: RawSession, ecg: dict[str, Any], window_s: float = 60.0, min_pairs: int = 20) -> list[dict[str, Any]]:
    """RMSSD per window over successive beats; an interval never spans an epoch change or a hole a beat could hide in."""
    stream = raw.streams[ecg["stream"]]
    detections = ecg["detections"]
    bridgeable = BRIDGEABLE_HOLE_S * ecg["rate_hz"]
    intervals = []
    for a, b in zip(detections[:-1], detections[1:]):
        if a["near_hole"] or b["near_hole"] or a["epoch"] != b["epoch"] \
                or b["holes_before"] - a["holes_before"] > bridgeable:
            continue
        rr_ms = (b["sample_index"] - a["sample_index"]) * a["tick_us"] / 1e3
        if 300 <= rr_ms <= 2000:
            intervals.append((a, b, rr_ms))
    if len(intervals) < 2:
        return []
    width = window_s * 1e6
    t0 = intervals[0][0]["time_us"]
    out = []
    for w in sorted({int((b["time_us"] - t0) // width) for _, b, _ in intervals}):
        inside = [iv for iv in intervals if int((iv[1]["time_us"] - t0) // width) == w]
        pairs = [(x, y) for x, y in zip(inside[:-1], inside[1:]) if x[1] is y[0]]
        if len(pairs) < min_pairs:
            continue
        rr = np.array([iv[2] for iv in inside])
        diffs = np.array([y[2] - x[2] for x, y in pairs])
        first_row, last_row = inside[0][0]["row"], inside[-1][1]["row"]
        out.append({"t0": int(stream.device_time_us[first_row]), "t1": int(stream.device_time_us[last_row]),
                    "decided": int(stream.available_us[last_row]), "ranges": ranges(stream, slice(first_row, last_row + 1)),
                    "payload": {"rmssd_ms": float(np.sqrt(np.mean(diffs ** 2))), "mean_rr_ms": float(rr.mean()),
                                "mean_hr_bpm": float(60_000 / rr.mean()), "successive_pairs": float(len(pairs)),
                                "intervals": float(len(inside)), "window_s": window_s}})
    return out


def score_beats(detected_us: np.ndarray, truth_s: np.ndarray, tolerance_ms: float = 50.0) -> dict[str, float]:
    """Sensitivity and positive predictivity against known beats, after removing the constant latency offset."""
    truth_us = np.asarray(truth_s) * 1e6
    detected_us = np.asarray(detected_us, dtype=np.float64)
    if not len(detected_us):
        return {"sensitivity": 0.0, "ppv": 0.0, "offset_ms": float("nan"), "timing_rms_ms": float("nan")}
    lo, hi = detected_us.min() - 1e6, detected_us.max() + 1e6
    truth_us = truth_us[(truth_us >= lo) & (truth_us <= hi)]
    nearest = truth_us[np.clip(np.searchsorted(truth_us, detected_us), 1, len(truth_us) - 1)]
    before = truth_us[np.clip(np.searchsorted(truth_us, detected_us) - 1, 0, len(truth_us) - 1)]
    error = np.where(np.abs(detected_us - nearest) < np.abs(detected_us - before), detected_us - nearest,
                     detected_us - before)
    offset = float(np.median(error))
    hit = np.abs(error - offset) <= tolerance_ms * 1e3
    covered = truth_us[(truth_us >= detected_us.min() - tolerance_ms * 1e3) & (truth_us <= detected_us.max())]
    return {"sensitivity": float(hit.sum() / max(len(covered), 1)), "ppv": float(hit.mean()), "offset_ms": offset / 1e3,
            "timing_rms_ms": float(np.sqrt(np.mean((error[hit] - offset) ** 2)) / 1e3) if hit.any() else float("nan")}
