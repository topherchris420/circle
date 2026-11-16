#!/usr/bin/env python3
"""Independently verify a CIRCLE First Light evidence bundle.

First Light is CIRCLE's physical-sensor demonstration: a phone camera measures
the optical pulse (PPG) through a fingertip or a known-input optical phantom,
quality gates decide whether that evidence is good enough to act on, a bounded
adaptive sound follows the measurement, a deliberate sensor fault is
introduced, and the system must refuse. The browser (``site/first-light-core.js``)
records every frame and every decision in a bundle.

This file is the second, independent implementation of the published
specification (``docs/first-light.md``). It shares no code with the browser
implementation; it needs only the Python 3.11+ standard library, so a reviewer
can download it alone and run it:

    python verify_first_light.py first-light-bundle.zip
    python verify_first_light.py first-light-bundle.zip --source butppg-2.0.0.zip

It reports four results, each named, never implied:

  integrity  INTEGRITY_OK | INTEGRITY_FAILURE | INSUFFICIENT_EVIDENCE
             every file matches the SHA-256 the manifest records; nothing extra
  replay     REPLAY_MATCH | REPLAY_DIVERGENCE | VERSION_MISMATCH
             every gate, decision, and feedback command rebuilt from raw frames
  protocol   PROTOCOL_PASS | PROTOCOL_FAIL
             the preregistered criteria for the bundle's mode, judged from raw
             evidence (and from the independent reference where one exists);
             with --pool, judged over all windows of several sessions at once
  source     SOURCE_MATCH | SOURCE_MISMATCH | NOT_CHECKED
             recorded-reference bundles only: frames and reference rebuilt from
             the public dataset download, byte for byte

The overall verdict is VERIFIED only when integrity, replay, and protocol all
pass (and source, when checked). A VERIFIED bundle shows the record is
complete, reproduces from its own raw frames, and met its preregistered
criteria. It does NOT show that a camera pulse is a medical measurement, that
the sound has any effect on a person, or that the frames were not fabricated
before the manifest was written: hashes detect change, they do not
authenticate a source. The --source check closes that gap only for bundles
built from the public dataset.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys
import zipfile

VERIFIER_VERSION = "1.0.0"
BUNDLE_SCHEMA = "circle-first-light-bundle/1"
PROTOCOL_SCHEMA = "circle-first-light-protocol/1"

# --------------------------------------------------------------------------------------------
# The published algorithm (docs/first-light.md, "Algorithm"). A bundle that declares anything
# else is a VERSION_MISMATCH: the verifier will not judge a record against rules it did not
# publish, and a bundle cannot loosen its own gates.
# Thresholds marked "calibrated" were chosen on the BUT PPG calibration subjects only
# (docs/first-light-benchmark.json) and locked before the held-out subjects were analysed.
# --------------------------------------------------------------------------------------------
ALGORITHM = {
    "id": "first-light-algorithm/1",
    "grid_hz": 50,                 # resampling grid for the pulse waveform
    "window_us": 8_000_000,        # evidence window per evaluation
    "step_us": 1_000_000,          # evaluation cadence
    "first_eval_us": 9_000_000,    # first nominal evaluation, after the first frame
    "highpass_len": 75,            # centered moving average removed (1.5 s)
    "lowpass_len": 7,              # centered moving average applied (0.14 s)
    "lag_min": 15,                 # 200 bpm
    "lag_max": 75,                 # 40 bpm
    "harmonic_ratio": 0.7,         # calibrated: earliest autocorrelation peak within 70 % of the best
    "min_frames": 120,             # 15 frames per second over the window
    "max_gap_us": 250_000,         # longest tolerated frame gap, including window edges
    "contact_red_min": 100_000,    # frame red mean, milli-units (fingertip lit by torch)
    "contact_red_permille": 550,   # red share of r+g+b, permille
    "green_min": 5_000,            # block mean green, milli-units: below is underexposed
    "green_max": 250_000,          # above is saturated
    "step_max": 0.05,              # calibrated: largest 1-s block step / window mean green
    "periodicity_min": 0.65,       # calibrated: autocorrelation at the pulse lag
    "rate_min_bpm": 50.0,         # calibrated: slower readings were mostly half-rate errors
    "rate_max_bpm": 180.0,
}

FEEDBACK = {
    "id": "first-light-feedback/1",
    "max_level": 0.3,              # commanded output level ceiling (0..1)
    "fade_steps": 3,               # evaluations to reach the ceiling after silence
    "tempo_slew_bpm": 6.0,         # largest tempo change per evaluation while audible
    "brightness_low_bpm": 50.0,    # brightness 0 at or below
    "brightness_span_bpm": 70.0,   # brightness 1 at or above low + span
}

GATES = ("FRAMES", "CONTACT", "EXPOSURE", "STEADY", "PERIODIC", "RATE")

# Preregistered acceptance criteria, per mode. Fixed here, not read from the bundle.
# criteria/1 required action on >= 0.5 of expert-good windows; that number was set without data and
# round 1 failed it (evidence/first-light/round-1). criteria/2 restates the recorded-reference bars
# from calibration subjects' continuous sessions (precision 0.978, expert-poor refused 0.993,
# expert-good acted 0.232) and was committed before its held-out test ran
# (evidence/first-light/round-2/PREREGISTRATION.md). The live bars are unchanged.
CRITERIA = {
    "id": "first-light-criteria/2",
    "live": {
        "min_acts_before_fault": 5,
        "min_fault_us": 2_000_000,
        "max_refusal_latency_us": 1_500_000,
    },
    "live-phantom": {"rate_tolerance_bpm": 2.0, "min_fraction_within": 0.9},
    "recorded-reference": {
        "rate_tolerance_bpm": 5.0,
        "min_fraction_within": 0.9,
        "min_refused_poor": 0.95,
        "min_acted_good": 0.15,
        "min_reference_beats": 5,
    },
}

MODES = ("live-finger", "live-phantom", "recorded-reference")
FEATURE_TOLERANCE = 1e-9            # relative; both implementations use the same IEEE-754 operations
BUT_PPG_SHA256 = "9b910fc884f63eca1c5d3a00c5710f838e0053dce94f8a02196bd0adc2ffa33c"


# ============================================================================================
# Analysis (spec: "Algorithm")
# ============================================================================================
def contact(r: int, g: int, b: int) -> bool:
    """A frame is in contact when it is bright and red-dominant (exact integer arithmetic)."""
    return r >= ALGORITHM["contact_red_min"] and 1000 * r >= ALGORITHM["contact_red_permille"] * (r + g + b)


def _moving_average(values: list[float], length: int) -> list[float]:
    half = length // 2
    n = len(values)
    prefix = [0.0] * (n + 1)
    for i in range(n):
        prefix[i + 1] = prefix[i] + values[i]
    out = [0.0] * n
    for j in range(n):
        a = j - half if j - half > 0 else 0
        b = j + half if j + half < n - 1 else n - 1
        out[j] = (prefix[b + 1] - prefix[a]) / (b - a + 1)
    return out


def pulse_rate(grid: list[float]) -> tuple[float | None, float | None]:
    """Autocorrelation pulse rate and periodicity of a resampled green-channel window."""
    cfg = ALGORITHM
    trend = _moving_average(grid, cfg["highpass_len"])
    detrended = [grid[j] - trend[j] for j in range(len(grid))]
    smooth = _moving_average(detrended, cfg["lowpass_len"])
    half = cfg["highpass_len"] // 2
    z = [-v for v in smooth[half:len(smooth) - half]]
    n = len(z)
    r = {}
    for lag in range(cfg["lag_min"] - 1, cfg["lag_max"] + 2):
        sab = saa = sbb = 0.0
        for i in range(n - lag):
            a = z[i]
            b = z[i + lag]
            sab += a * b
            saa += a * a
            sbb += b * b
        den = math.sqrt(saa * sbb)
        r[lag] = sab / den if den > 0 else 0.0
    candidates = [lag for lag in range(cfg["lag_min"], cfg["lag_max"] + 1) if r[lag] > r[lag - 1] and r[lag] >= r[lag + 1]]
    if not candidates:
        return None, None
    best = max(r[lag] for lag in candidates)
    if best <= 0:
        return None, best
    bar = cfg["harmonic_ratio"] * best
    lag = min(lag for lag in candidates if r[lag] >= bar)
    den = r[lag - 1] - 2 * r[lag] + r[lag + 1]
    delta = 0.5 * (r[lag - 1] - r[lag + 1]) / den if den < 0 else 0.0
    return 60 * cfg["grid_hz"] / (lag + delta), r[lag]


def evaluate(frames: list[tuple[int, int, int, int]], end: int, cutoff: int) -> dict:
    """Evaluate the window ending at ``cutoff``; ``frames[:end]`` are the frames at or before it."""
    cfg = ALGORITHM
    start = cutoff - cfg["window_us"]
    lo = end
    while lo > 0 and frames[lo - 1][0] >= start:
        lo -= 1
    window = frames[lo:end]
    gates = {name: None for name in GATES}
    features = {"frames": len(window), "max_gap_us": None, "out_of_contact": None, "red_permille_min": None,
                "green_block_min": None, "green_block_max": None, "step": None, "periodicity": None,
                "rate_bpm": None}
    reasons: list[str] = []
    if window:
        edges = [window[0][0] - start, cutoff - window[-1][0]]
        gaps = [window[i + 1][0] - window[i][0] for i in range(len(window) - 1)]
        features["max_gap_us"] = max(edges + gaps)
    frames_ok = len(window) >= cfg["min_frames"] and features["max_gap_us"] is not None \
        and features["max_gap_us"] <= cfg["max_gap_us"]
    gates["FRAMES"] = "pass" if frames_ok else "fail"
    if not frames_ok:
        reasons.append("FRAME_GAP" if window and len(window) >= cfg["min_frames"] else "TOO_FEW_FRAMES")
        return {"gates": gates, "features": features, "reasons": reasons}

    out = sum(1 for _, r, g, b in window if not contact(r, g, b))
    features["out_of_contact"] = out
    features["red_permille_min"] = min((1000 * r) // (r + g + b) if r + g + b else 0 for _, r, g, b in window)
    gates["CONTACT"] = "pass" if out == 0 else "fail"
    if out:
        reasons.append("NO_CONTACT")

    sums = [0] * 8
    counts = [0] * 8
    for t, _, g, _ in window:
        block = (t - start) // 1_000_000
        block = 7 if block > 7 else block
        sums[block] += g
        counts[block] += 1
    means = [sums[k] / counts[k] for k in range(8)]
    features["green_block_min"] = min(means)
    features["green_block_max"] = max(means)
    under = any(sums[k] < cfg["green_min"] * counts[k] for k in range(8))
    over = any(sums[k] > cfg["green_max"] * counts[k] for k in range(8))
    gates["EXPOSURE"] = "fail" if under or over else "pass"
    if under:
        reasons.append("UNDEREXPOSED")
    if over:
        reasons.append("SATURATED")

    total = sum(sums)
    mean = total / sum(counts)
    step = max(abs(means[k + 1] - means[k]) for k in range(7)) / mean if mean > 0 else math.inf
    features["step"] = step if math.isfinite(step) else None
    gates["STEADY"] = "pass" if step <= cfg["step_max"] else "fail"
    if gates["STEADY"] == "fail":
        reasons.append("UNSTEADY")

    period_us = 1_000_000 // cfg["grid_hz"]
    m = cfg["window_us"] // period_us
    grid = []
    a = lo - 1 if lo > 0 else 0
    for j in range(m):
        when = cutoff - (m - 1 - j) * period_us
        while a + 1 < end and frames[a + 1][0] <= when:
            a += 1
        ta, va = frames[a][0], frames[a][2]
        if a + 1 < end and ta < when:
            tb, vb = frames[a + 1][0], frames[a + 1][2]
            grid.append(va + (vb - va) * ((when - ta) / (tb - ta)))
        else:
            grid.append(float(va))
    rate, periodicity = pulse_rate(grid)
    features["periodicity"] = periodicity
    features["rate_bpm"] = rate
    gates["PERIODIC"] = "pass" if periodicity is not None and periodicity >= cfg["periodicity_min"] else "fail"
    if gates["PERIODIC"] == "fail":
        reasons.append("NOT_PERIODIC")
    gates["RATE"] = "pass" if rate is not None and cfg["rate_min_bpm"] <= rate <= cfg["rate_max_bpm"] else "fail"
    if gates["RATE"] == "fail":
        reasons.append("IMPLAUSIBLE_RATE")
    return {"gates": gates, "features": features, "reasons": reasons}


def schedule(frames: list[tuple[int, int, int, int]]):
    """Yield (k, nominal, cutoff, end) for each evaluation the specification schedules."""
    if not frames:
        return
    t0, last = frames[0][0], frames[-1][0]
    k = 0
    end = 0
    while True:
        nominal = t0 + ALGORITHM["first_eval_us"] + k * ALGORITHM["step_us"]
        if nominal > last:
            return
        while end < len(frames) and frames[end][0] <= nominal:
            end += 1
        yield k, nominal, frames[end - 1][0], end
        k += 1


def run_controller(frames: list[tuple[int, int, int, int]]) -> tuple[list[dict], list[dict]]:
    """Rebuild every decision and feedback command from raw frames (spec: "Controller", "Feedback")."""
    decisions, feedback = [], []
    state = "ACQUIRING"
    last_fail = None
    tempo = None
    level = 0.0
    fb = FEEDBACK
    for k, nominal, cutoff, end in schedule(frames):
        result = evaluate(frames, end, cutoff)
        passed = all(v == "pass" for v in result["gates"].values())
        fresh = last_fail is None or cutoff - ALGORITHM["window_us"] >= last_fail
        reasons = list(result["reasons"])
        if passed and fresh:
            decision, state = "ACT", "ADAPTING"
            rate = result["features"]["rate_bpm"]
        else:
            if not passed:
                last_fail = cutoff
            else:
                reasons.append("AWAITING_CLEAN_WINDOW")
            decision = "REFUSE"
            state = "ACQUIRING" if state == "ACQUIRING" else "REFUSING"
            rate = None
        decisions.append({"k": k, "nominal_us": nominal, "cutoff_us": cutoff, "decision": decision,
                          "state": state, "gates": result["gates"], "reasons": reasons,
                          "features": result["features"], "rate_bpm": rate})
        if decision == "ACT":
            if tempo is None:
                tempo = rate
            else:
                change = rate - tempo
                limit = fb["tempo_slew_bpm"]
                tempo = tempo + (limit if change > limit else -limit if change < -limit else change)
            level = min(fb["max_level"], level + fb["max_level"] / fb["fade_steps"])
            brightness = (tempo - fb["brightness_low_bpm"]) / fb["brightness_span_bpm"]
            brightness = 0.0 if brightness < 0 else 1.0 if brightness > 1 else brightness
            feedback.append({"k": k, "t_us": cutoff, "audible": True, "level": level, "tempo_bpm": tempo,
                             "brightness": brightness})
        else:
            tempo = None
            level = 0.0
            feedback.append({"k": k, "t_us": cutoff, "audible": False, "level": 0.0, "tempo_bpm": None,
                             "brightness": None})
    return decisions, feedback


# ============================================================================================
# Bundle reading and integrity
# ============================================================================================
class Bundle:
    def __init__(self, path: Path):
        self.path = path
        self.files: dict[str, bytes] = {}
        if path.is_dir():
            for item in sorted(path.rglob("*")):
                if item.is_file():
                    self.files[item.relative_to(path).as_posix()] = item.read_bytes()
        else:
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if not info.is_dir():
                        self.files[info.filename] = archive.read(info)

    def json(self, name: str):
        return json.loads(self.files[name].decode("utf-8"))


def check_integrity(bundle: Bundle) -> tuple[str, list[str]]:
    if "manifest.json" not in bundle.files:
        return "INSUFFICIENT_EVIDENCE", ["manifest.json is missing"]
    try:
        manifest = bundle.json("manifest.json")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return "INSUFFICIENT_EVIDENCE", [f"manifest.json unreadable: {exc}"]
    if manifest.get("schema") != BUNDLE_SCHEMA:
        return "INSUFFICIENT_EVIDENCE", [f"unknown bundle schema {manifest.get('schema')!r}"]
    listed = manifest.get("files") or {}
    problems = []
    for required in ("protocol.json", "raw/frames.csv", "decisions.json", "feedback.json"):
        if required not in listed:
            problems.append(f"the manifest does not list {required}")
    if problems:
        return "INSUFFICIENT_EVIDENCE", problems
    for name, meta in sorted(listed.items()):
        data = bundle.files.get(name)
        if data is None:
            problems.append(f"{name} is listed but missing")
        elif hashlib.sha256(data).hexdigest() != meta.get("sha256") or len(data) != meta.get("bytes"):
            problems.append(f"{name} does not match its recorded SHA-256")
    for name in sorted(set(bundle.files) - set(listed) - {"manifest.json"}):
        problems.append(f"{name} is present but not in the manifest")
    if problems:
        missing = all("missing" in p for p in problems)
        return ("INSUFFICIENT_EVIDENCE" if missing else "INTEGRITY_FAILURE"), problems
    return "INTEGRITY_OK", []


def read_frames(data: bytes) -> list[tuple[int, int, int, int]]:
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
    if not rows or rows[0] != ["t_us", "r", "g", "b"]:
        raise ValueError("raw/frames.csv must start with the header t_us,r,g,b")
    frames = []
    for number, row in enumerate(rows[1:], 2):
        if len(row) != 4 or not all(cell.lstrip("-").isdigit() for cell in row):
            raise ValueError(f"raw/frames.csv line {number}: expected four integers")
        t, r, g, b = (int(cell) for cell in row)
        if frames and t <= frames[-1][0]:
            raise ValueError(f"raw/frames.csv line {number}: time does not increase")
        if not all(0 <= v <= 255_000 for v in (r, g, b)):
            raise ValueError(f"raw/frames.csv line {number}: channel outside 0..255000")
        frames.append((t, r, g, b))
    return frames


# ============================================================================================
# Replay comparison
# ============================================================================================
def _close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return abs(a - b) <= FEATURE_TOLERANCE * max(1.0, abs(a), abs(b))


def compare_replay(recorded_decisions, recorded_feedback, decisions, feedback) -> list[str]:
    problems = []
    if len(recorded_decisions) != len(decisions):
        problems.append(f"the bundle records {len(recorded_decisions)} evaluations; the raw frames schedule {len(decisions)}")
    for mine, theirs in zip(decisions, recorded_decisions):
        k = mine["k"]
        for key in ("k", "nominal_us", "cutoff_us", "decision", "state", "gates", "reasons"):
            if theirs.get(key) != mine[key]:
                problems.append(f"evaluation {k}: {key} recorded {theirs.get(key)!r}, rebuilt {mine[key]!r}")
        if not _close(theirs.get("rate_bpm"), mine["rate_bpm"]):
            problems.append(f"evaluation {k}: rate recorded {theirs.get('rate_bpm')!r}, rebuilt {mine['rate_bpm']!r}")
        for name, value in mine["features"].items():
            if not _close((theirs.get("features") or {}).get(name), value):
                problems.append(f"evaluation {k}: feature {name} recorded "
                                f"{(theirs.get('features') or {}).get(name)!r}, rebuilt {value!r}")
        if len(problems) > 20:
            break
    if len(recorded_feedback) != len(feedback):
        problems.append(f"the bundle records {len(recorded_feedback)} feedback commands; rebuilt {len(feedback)}")
    for mine, theirs in zip(feedback, recorded_feedback):
        for key in ("k", "t_us", "audible"):
            if theirs.get(key) != mine[key]:
                problems.append(f"feedback {mine['k']}: {key} recorded {theirs.get(key)!r}, rebuilt {mine[key]!r}")
        for key in ("level", "tempo_bpm", "brightness"):
            if not _close(theirs.get(key), mine[key]):
                problems.append(f"feedback {mine['k']}: {key} recorded {theirs.get(key)!r}, rebuilt {mine[key]!r}")
        if len(problems) > 40:
            break
    return problems


# ============================================================================================
# Preregistered protocol criteria (spec: "Acceptance criteria")
# ============================================================================================
def _criterion(cid: str, passed: bool, measured, required, detail: str) -> dict:
    return {"id": cid, "result": "PASS" if passed else "FAIL", "measured": measured, "required": required,
            "detail": detail}


def _window_frames(frames, cutoff):
    start = cutoff - ALGORITHM["window_us"]
    return [f for f in frames if start <= f[0] <= cutoff]


def live_criteria(frames, decisions, feedback, mode: str, reference: dict | None) -> list[dict]:
    """Judge a live session from raw evidence alone: the verifier finds the fault itself."""
    c = CRITERIA["live"]
    out = []
    first_act = next((d for d in decisions if d["decision"] == "ACT"), None)
    # The fault: the first run of out-of-contact frames, after the first ACT, lasting >= min_fault_us.
    fault = None
    if first_act is not None:
        run_start = None
        for i, (t, r, g, b) in enumerate(frames):
            if t <= first_act["cutoff_us"]:
                continue
            if not contact(r, g, b):
                run_start = t if run_start is None else run_start
                ends_here = i + 1 == len(frames) or contact(*frames[i + 1][1:])
                if ends_here and t - run_start >= c["min_fault_us"]:
                    fault = (run_start, t)
                    break
                if ends_here:
                    run_start = None
    acts_before = sum(1 for d in decisions if d["decision"] == "ACT" and (fault is None or d["cutoff_us"] < fault[0]))
    out.append(_criterion("L1_ACTED_ON_GOOD_EVIDENCE", acts_before >= c["min_acts_before_fault"], acts_before,
                          f">= {c['min_acts_before_fault']}",
                          "ACT decisions before the fault: the system did respond when evidence was good."))
    out.append(_criterion("L2_FAULT_PRESENT", fault is not None,
                          None if fault is None else round((fault[1] - fault[0]) / 1e6, 3),
                          f">= {c['min_fault_us'] / 1e6:g} s of out-of-contact frames after the first ACT",
                          "Found by the verifier in raw/frames.csv, not taken from the page's prompts."))
    if fault is None:
        for cid in ("L3_REFUSED_IN_TIME", "L4_NO_ACT_ON_BAD_FRAMES", "L5_SILENT_WHILE_REFUSED", "L6_CLEAN_RECOVERY"):
            out.append(_criterion(cid, False, None, "a fault", "No deliberate fault was found to judge."))
    else:
        onset, ended = fault
        refusal = next((d for d in decisions if d["cutoff_us"] >= onset and d["decision"] == "REFUSE"), None)
        latency = None if refusal is None else refusal["cutoff_us"] - onset
        out.append(_criterion("L3_REFUSED_IN_TIME", latency is not None and latency <= c["max_refusal_latency_us"],
                              None if latency is None else round(latency / 1e6, 3),
                              f"<= {c['max_refusal_latency_us'] / 1e6:g} s",
                              "Time from the first out-of-contact frame to the first REFUSE decision."))
        bad_acts = [d["k"] for d in decisions if d["decision"] == "ACT"
                    and any(not contact(r, g, b) for _, r, g, b in _window_frames(frames, d["cutoff_us"]))]
        out.append(_criterion("L4_NO_ACT_ON_BAD_FRAMES", not bad_acts, len(bad_acts), "0",
                              "ACT decisions whose evidence window contains any out-of-contact frame."))
        resumed = next((d for d in decisions if d["cutoff_us"] > ended and d["decision"] == "ACT"), None)
        silent_until = resumed["cutoff_us"] if resumed else math.inf
        loud = [f["k"] for f in feedback if (f["audible"] or f["level"] > 0) and
                (decisions[f["k"]]["decision"] == "REFUSE" or
                 onset + c["max_refusal_latency_us"] <= f["t_us"] < silent_until)]
        out.append(_criterion("L5_SILENT_WHILE_REFUSED", not loud, len(loud), "0",
                              "Audible feedback commands during refusal or after the refusal deadline."))
        fresh = resumed is not None and resumed["cutoff_us"] - ALGORITHM["window_us"] > ended
        out.append(_criterion("L6_CLEAN_RECOVERY", fresh,
                              None if resumed is None else round((resumed["cutoff_us"] - ended) / 1e6, 3),
                              "ACT resumes, with a window that starts after the last fault frame",
                              "Seconds from the end of the fault to the first ACT after it."))
    if mode == "live-phantom":
        p = CRITERIA["live-phantom"]
        truth = (reference or {}).get("rate_bpm")
        acts = [d for d in decisions if d["decision"] == "ACT"]
        within = [d for d in acts if truth is not None and abs(d["rate_bpm"] - truth) <= p["rate_tolerance_bpm"]]
        fraction = len(within) / len(acts) if acts else 0.0
        out.append(_criterion("P1_PHANTOM_ACCURACY", truth is not None and bool(acts) and fraction >= p["min_fraction_within"],
                              round(fraction, 4), f">= {p['min_fraction_within']} within ±{p['rate_tolerance_bpm']:g} bpm",
                              f"ACT rates against the phantom's programmed {truth} bpm."))
    return out


def reference_rate(qrs_us: list[int], start: int, end: int) -> tuple[float | None, int]:
    beats = [t for t in qrs_us if start <= t <= end]
    if len(beats) < 2:
        return None, len(beats)
    intervals = sorted(beats[i + 1] - beats[i] for i in range(len(beats) - 1))
    n = len(intervals)
    median = intervals[n // 2] if n % 2 else (intervals[n // 2 - 1] + intervals[n // 2]) / 2
    return 60_000_000 / median, len(beats)


def recorded_rows(decisions, reference: dict) -> list[dict]:
    """One row per evaluation: the experts' label for its window and the ECG rate over the same window."""
    segments = reference["segments"]
    qrs = reference["qrs_us"]
    rows = []
    for d in decisions:
        start, end = d["cutoff_us"] - ALGORITHM["window_us"], d["cutoff_us"]
        inside = [s for s in segments if s["end_us"] >= start and s["start_us"] <= end]
        labels = {s["quality"] for s in inside}
        label = "good" if labels == {1} else "poor" if labels == {0} else "mixed"
        ref, beats = reference_rate(qrs, start, end)
        rows.append({"k": d["k"], "cutoff_us": end, "label": label, "decision": d["decision"],
                     "rate_bpm": d["rate_bpm"], "reference_bpm": ref, "reference_beats": beats,
                     "error_bpm": None if ref is None or d["rate_bpm"] is None else d["rate_bpm"] - ref})
    return rows


def judge_recorded(rows: list[dict], loud_refused: int) -> list[dict]:
    """The recorded-reference criteria over a set of window rows: one session, or many pooled."""
    c = CRITERIA["recorded-reference"]
    acts = [r for r in rows if r["decision"] == "ACT" and r["reference_beats"] >= c["min_reference_beats"]]
    within = [r for r in acts if abs(r["error_bpm"]) <= c["rate_tolerance_bpm"]]
    fraction = len(within) / len(acts) if acts else 0.0
    out = [_criterion("R1_ACCURACY_VS_ECG", bool(acts) and fraction >= c["min_fraction_within"], round(fraction, 4),
                      f">= {c['min_fraction_within']} of ACT rates within ±{c['rate_tolerance_bpm']:g} bpm of ECG",
                      f"{len(within)} of {len(acts)} ACT decisions, against the chest-ECG beat times of the same window.")]
    poor = [r for r in rows if r["label"] == "poor"]
    refused = [r for r in poor if r["decision"] == "REFUSE"]
    share = len(refused) / len(poor) if poor else 0.0
    out.append(_criterion("R2_REFUSED_WHAT_EXPERTS_REJECTED", bool(poor) and share >= c["min_refused_poor"], round(share, 4),
                          f">= {c['min_refused_poor']}",
                          f"{len(refused)} of {len(poor)} windows lying wholly inside segments the dataset's experts "
                          "labelled unusable were refused."))
    good = [r for r in rows if r["label"] == "good"]
    acted = [r for r in good if r["decision"] == "ACT"]
    share = len(acted) / len(good) if good else 0.0
    out.append(_criterion("R3_ACTED_WHEN_EVIDENCE_WAS_GOOD", bool(good) and share >= c["min_acted_good"], round(share, 4),
                          f">= {c['min_acted_good']}",
                          f"{len(acted)} of {len(good)} windows wholly inside expert-good segments acted. "
                          "A system that always refuses cannot pass."))
    out.append(_criterion("R4_SILENT_WHILE_REFUSED", loud_refused == 0, loud_refused, "0",
                          "Audible feedback commands issued with a REFUSE decision."))
    return out


def recorded_criteria(frames, decisions, feedback, reference: dict) -> tuple[list[dict], list[dict], int]:
    """Judge one recorded session against its independent ECG reference and the experts' labels."""
    rows = recorded_rows(decisions, reference)
    loud = sum(1 for f in feedback if (f["audible"] or f["level"] > 0) and decisions[f["k"]]["decision"] == "REFUSE")
    return judge_recorded(rows, loud), rows, loud


def pool(results: list[dict]) -> dict:
    """Judge the recorded-reference criteria over several sessions together (spec: "Pooled test").

    Every session must pass integrity and replay (and source, when checked) on its own; the
    preregistered bars are then applied to all windows of all sessions at once. Coverage differs
    widely between people, so a rate measured on one person says little about the system.
    """
    problems = []
    rows, loud = [], 0
    for r in results:
        if r.get("mode") != "recorded-reference":
            problems.append(f"{r['bundle']}: only recorded-reference bundles can be pooled")
        elif r.get("integrity") != "INTEGRITY_OK" or r.get("replay") != "REPLAY_MATCH" or r.get("source") == "SOURCE_MISMATCH":
            problems.append(f"{r['bundle']}: {r.get('verdict')}")
        else:
            rows.extend(r["windows"])
            loud += r["loud_refused"]
    criteria = judge_recorded(rows, loud) if not problems else []
    passed = bool(criteria) and all(c["result"] == "PASS" for c in criteria)
    return {"schema": "circle-first-light-pooled-verdict/1", "verifier_version": VERIFIER_VERSION,
            "criteria_id": CRITERIA["id"], "sessions": len(results), "windows": len(rows),
            "acts": sum(1 for r in rows if r["decision"] == "ACT"), "criteria": criteria, "problems": problems,
            "verdict": "VERIFIED" if passed else ("PROTOCOL_FAIL" if not problems else "NOT_VERIFIED")}


# ============================================================================================
# Rebuilding a recorded-reference bundle from the public dataset (spec: "Recorded session")
# ============================================================================================
def read_qrs(data: bytes) -> list[int]:
    """Beat sample numbers from a WFDB (MIT format) annotation file."""
    t, out, i = 0, [], 0
    while i + 1 < len(data):
        word = data[i] | (data[i + 1] << 8)
        i += 2
        code, interval = word >> 10, word & 0x3FF
        if code == 0 and interval == 0:
            break
        if code == 59:                               # SKIP: a 32-bit interval follows, high word first
            high = data[i] | (data[i + 1] << 8)
            low = data[i + 2] | (data[i + 3] << 8)
            i += 4
            t += (high << 16) | low
            continue
        if code == 63:                               # AUX: skip the auxiliary string
            i += (interval + 1) // 2 * 2
            continue
        if code in (60, 61, 62):                     # NUM, SUB, CHN carry no time
            continue
        t += interval
        out.append(t)
    return out


class ButPpg:
    """Read the BUT PPG 2.0.0 archive exactly as published on PhysioNet (CC BY 4.0)."""

    def __init__(self, path: Path):
        self.archive = zipfile.ZipFile(path)
        self.root = self.archive.namelist()[0].split("/")[0]
        self.sha256 = None

    def table(self, name: str) -> dict[str, dict]:
        text = self.archive.read(f"{self.root}/{name}").decode("utf-8-sig")
        return {row["ID"]: row for row in csv.DictReader(io.StringIO(text))}

    def file_sums(self) -> dict[str, str]:
        text = self.archive.read(f"{self.root}/SHA256SUMS.txt").decode("utf-8")
        sums = {}
        for line in text.splitlines():
            if line.strip():
                digest, name = line.split(maxsplit=1)
                sums[name.strip()] = digest
        return sums

    def read(self, name: str) -> bytes:
        return self.archive.read(f"{self.root}/{name}")

    def ppg(self, record: str) -> list[tuple[int, int, int]]:
        """Frame channel means in milli-units. Only the three-channel (R,G,B) layout is accepted."""
        header = self.read(f"{record}/{record}_PPG.hea").decode("utf-8").strip().splitlines()
        first = header[0].split()
        signals, samples = int(first[1]), int(first[3])
        if signals != 3:
            raise ValueError(f"{record}: not a three-channel PPG record")
        scale = []
        for line in header[1:4]:
            field = line.split()[2]
            gain = float(field.split("(")[0])
            baseline = int(field.split("(")[1].split(")")[0])
            scale.append((gain, baseline))
        data = self.read(f"{record}/{record}_PPG.dat")
        adc = struct.unpack(f"<{len(data) // 2}h", data)
        out = []
        for i in range(samples):
            values = []
            for c in range(3):
                gain, baseline = scale[c]
                physical = (adc[i * 3 + c] - baseline) / gain
                values.append(min(255_000, max(0, round(physical * 1000))))
            out.append(tuple(values))
        return out


def build_recorded_session(source: ButPpg, records: list[str]) -> tuple[bytes, dict]:
    """Concatenate consecutive segments of one recording into frames.csv and its reference."""
    annotations = source.table("quality-hr-ann.csv")
    info = source.table("subject-info.csv")
    sums = source.file_sums()
    lines = ["t_us,r,g,b"]
    segments, qrs_us = [], []
    index = 0
    for record in records:
        frames = source.ppg(record)
        start = index * 1_000_000 // 30
        for values in frames:
            lines.append(f"{index * 1_000_000 // 30},{values[0]},{values[1]},{values[2]}")
            index += 1
        end = (index - 1) * 1_000_000 // 30
        for beat in read_qrs(source.read(f"{record}/{record}.qrs")):
            qrs_us.append(start + beat * 1000)       # ECG at 1000 Hz: one sample is 1000 µs
        segments.append({"record": record, "start_us": start, "end_us": end,
                         "quality": int(annotations[record]["Quality"]),
                         "reference_hr_bpm": float(annotations[record]["HR"]),
                         "motion": info[record]["Motion"], "spot": "finger" if info[record]["Ear/finger"] == "1" else "ear",
                         "sha256": {"ppg_dat": sums.get(f"{record}/{record}_PPG.dat"),
                                    "ppg_hea": sums.get(f"{record}/{record}_PPG.hea"),
                                    "qrs": sums.get(f"{record}/{record}.qrs")}})
    reference = {"schema": "circle-first-light-reference/1", "kind": "but-ppg-ecg",
                 "dataset": {"name": "Brno University of Technology Smartphone PPG Database (BUT PPG)",
                             "version": "2.0.0", "doi": "10.13026/bvsb-mz80",
                             "url": "https://physionet.org/content/butppg/2.0.0/", "license": "CC BY 4.0",
                             "archive_sha256": BUT_PPG_SHA256},
                 "segments": segments, "qrs_us": qrs_us}
    return ("\n".join(lines) + "\n").encode("utf-8"), reference


def check_source(bundle: Bundle, source_path: Path) -> tuple[str, list[str]]:
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if digest != BUT_PPG_SHA256:
        return "SOURCE_MISMATCH", [f"{source_path.name} is not the published BUT PPG 2.0.0 archive (SHA-256 {digest})"]
    reference = bundle.json("reference.json")
    records = [s["record"] for s in reference["segments"]]
    frames_csv, rebuilt = build_recorded_session(ButPpg(source_path), records)
    problems = []
    if frames_csv != bundle.files["raw/frames.csv"]:
        problems.append("raw/frames.csv differs from the frames rebuilt from the dataset")
    if rebuilt != reference:
        problems.append("reference.json differs from the reference rebuilt from the dataset")
    return ("SOURCE_MATCH" if not problems else "SOURCE_MISMATCH"), problems


# ============================================================================================
# Verify
# ============================================================================================
def verify(path: Path, source: Path | None = None) -> dict:
    result = {"schema": "circle-first-light-verdict/1", "verifier_version": VERIFIER_VERSION,
              "bundle": path.name, "integrity": None, "replay": None, "protocol": None,
              "source": "NOT_CHECKED", "problems": []}
    try:
        bundle = Bundle(path)
    except (OSError, zipfile.BadZipFile) as exc:
        result.update(integrity="INSUFFICIENT_EVIDENCE", verdict="INSUFFICIENT_EVIDENCE", problems=[str(exc)])
        return result
    integrity, problems = check_integrity(bundle)
    result["integrity"] = integrity
    if integrity != "INTEGRITY_OK":
        result.update(verdict=integrity, problems=problems)
        return result
    result["bundle_sha256"] = hashlib.sha256(bundle.files["manifest.json"]).hexdigest()
    try:
        protocol = bundle.json("protocol.json")
        frames = read_frames(bundle.files["raw/frames.csv"])
        recorded_decisions = bundle.json("decisions.json")
        recorded_feedback = bundle.json("feedback.json")
        reference = bundle.json("reference.json") if "reference.json" in bundle.files else None
    except (ValueError, KeyError, UnicodeDecodeError) as exc:
        result.update(integrity="INSUFFICIENT_EVIDENCE", verdict="INSUFFICIENT_EVIDENCE", problems=[str(exc)])
        return result
    mode = protocol.get("mode")
    result["mode"] = mode
    mismatch = []
    if protocol.get("schema") != PROTOCOL_SCHEMA:
        mismatch.append(f"protocol schema {protocol.get('schema')!r} is not {PROTOCOL_SCHEMA}")
    if mode not in MODES:
        mismatch.append(f"unknown mode {mode!r}")
    if protocol.get("algorithm") != ALGORITHM:
        mismatch.append(f"the bundle declares a different algorithm than the published {ALGORITHM['id']}")
    if protocol.get("feedback") != FEEDBACK:
        mismatch.append(f"the bundle declares a different feedback mapping than the published {FEEDBACK['id']}")
    if protocol.get("criteria") != CRITERIA["id"]:
        mismatch.append(f"the bundle names criteria {protocol.get('criteria')!r}, not {CRITERIA['id']}")
    if mode == "recorded-reference" and reference is None:
        mismatch.append("a recorded-reference bundle must carry reference.json")
    if mismatch:
        result.update(replay="VERSION_MISMATCH", verdict="VERSION_MISMATCH", problems=mismatch)
        return result

    decisions, feedback = run_controller(frames)
    divergence = compare_replay(recorded_decisions, recorded_feedback, decisions, feedback)
    result["replay"] = "REPLAY_DIVERGENCE" if divergence else "REPLAY_MATCH"
    result["problems"].extend(divergence)
    result["evaluations"] = len(decisions)
    result["acts"] = sum(1 for d in decisions if d["decision"] == "ACT")
    result["refusals"] = len(decisions) - result["acts"]
    result["frames"] = len(frames)
    result["duration_s"] = round((frames[-1][0] - frames[0][0]) / 1e6, 3) if frames else 0

    if mode == "recorded-reference":
        criteria, rows, loud = recorded_criteria(frames, decisions, feedback, reference)
        result["windows"] = rows
        result["loud_refused"] = loud
    else:
        criteria = live_criteria(frames, decisions, feedback, mode, reference)
    result["criteria"] = criteria
    result["protocol"] = "PROTOCOL_PASS" if all(c["result"] == "PASS" for c in criteria) else "PROTOCOL_FAIL"

    if source is not None:
        if mode != "recorded-reference":
            result["source"] = "NOT_APPLICABLE"
        else:
            result["source"], source_problems = check_source(bundle, source)
            result["problems"].extend(source_problems)

    failures = [v for v in (result["replay"], result["protocol"]) if v not in ("REPLAY_MATCH", "PROTOCOL_PASS")]
    if result["source"] == "SOURCE_MISMATCH":
        failures.append("SOURCE_MISMATCH")
    result["verdict"] = failures[0] if failures else "VERIFIED"
    return result


def summary(result: dict) -> str:
    lines = [f"CIRCLE First Light verifier {result['verifier_version']} · {result['bundle']}"]
    if result.get("mode"):
        lines.append(f"  mode       {result['mode']}  ·  {result.get('frames', 0)} frames over "
                     f"{result.get('duration_s', 0)} s  ·  {result.get('acts', 0)} ACT / {result.get('refusals', 0)} REFUSE")
    for key in ("integrity", "replay", "protocol", "source"):
        if result.get(key):
            lines.append(f"  {key:<10} {result[key]}")
    for c in result.get("criteria", []):
        lines.append(f"    {c['result']}  {c['id']:<34} measured {c['measured']}  (required {c['required']})")
    for problem in result.get("problems", [])[:12]:
        lines.append(f"  problem: {problem}")
    lines.append(f"VERDICT: {result['verdict']}")
    lines.append("VERIFIED means complete, reproducible from its own raw frames, and within its preregistered "
                 "criteria. It is not a medical measurement and shows no effect on a person.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bundle", type=Path, nargs="+",
                        help="evidence bundle (.zip) or an extracted bundle directory; several with --pool")
    parser.add_argument("--source", type=Path, default=None,
                        help="the BUT PPG 2.0.0 archive, to rebuild a recorded-reference bundle from the public data")
    parser.add_argument("--pool", action="store_true",
                        help="judge the criteria over all given recorded-reference bundles together")
    parser.add_argument("--json", type=Path, default=None, help="also write the full verdict as JSON")
    args = parser.parse_args(argv)
    if len(args.bundle) > 1 and not args.pool:
        parser.error("give one bundle, or several with --pool")
    results = [verify(path, args.source) for path in args.bundle]
    if not args.pool:
        if args.json:
            args.json.write_text(json.dumps(results[0], indent=1) + "\n", encoding="utf-8")
        print(summary(results[0]))
        return 0 if results[0]["verdict"] == "VERIFIED" else 1
    pooled = pool(results)
    if args.json:
        args.json.write_text(json.dumps(pooled, indent=1) + "\n", encoding="utf-8")
    print(f"CIRCLE First Light verifier {VERIFIER_VERSION} · {pooled['sessions']} sessions pooled · "
          f"{pooled['windows']} windows · {pooled['acts']} ACT")
    for c in pooled["criteria"]:
        print(f"    {c['result']}  {c['id']:<34} measured {c['measured']}  (required {c['required']})")
    for problem in pooled["problems"][:12]:
        print(f"  problem: {problem}")
    print(f"POOLED VERDICT: {pooled['verdict']}")
    return 0 if pooled["verdict"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
