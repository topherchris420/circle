"""Self-contained interactive session report (one HTML file, no network needed for data).

The report is a polygraph: every recovered channel on one shared, zoomable
time axis, drawn over hidden ground truth, with the closed-loop evidence
chain, the scorecard, and the matched counterfactual arm. Static sections
are rendered here in Python so the report reads completely without script;
the canvas charts are drawn by the embedded script.
"""

from __future__ import annotations

from html import escape
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .pipeline import _carrier_envelope, heart_rate_series, imu_physical

TEMPLATE_DIR = Path(__file__).resolve().parent / "report_assets"

GROUPS = [
    ("Timing and integrity", ("clock_ppm", "edge_p999", "edge_max", "ppg_fifo", "gaps_exact")),
    ("Cardiac", ("beat_f1", "beat_f1_all", "hr_mae", "rmssd_mae")),
    ("Respiration", ("resp_mae", "apnea_iou")),
    ("Oxygen saturation", ("spo2_mae", "spo2_false_desat")),
    ("Electrodermal", ("scr_sensitivity", "scr_ppv", "scr_amplitude", "scl_mae")),
    ("Motion and haptics", ("motion_iou", "haptic_physical")),
    ("Closed loop", ("arousal_tracking",)),
]


def _r(x: float, digits: int) -> float | None:
    return round(float(x), digits) if x is not None and math.isfinite(float(x)) else None


def _segments(t: np.ndarray, v: np.ndarray, rate: float, digits: int, max_gap: float | None = None) -> list[dict[str, Any]]:
    """Resample (t, v) to uniform segments, splitting at gaps and non-finite values."""
    t = np.asarray(t, dtype=float)
    v = np.asarray(v, dtype=float)
    ok = np.isfinite(t) & np.isfinite(v)
    out: list[dict[str, Any]] = []
    if ok.sum() < 2:
        return out
    idx = np.flatnonzero(ok)
    breaks = np.flatnonzero((np.diff(idx) > 1) | (np.diff(t[idx]) > (max_gap or 3.0 / rate))) + 1
    for part in np.split(idx, breaks):
        if len(part) < 2 or t[part[-1]] - t[part[0]] < 1.0 / rate:
            continue
        grid = np.arange(t[part[0]], t[part[-1]], 1.0 / rate)
        values = np.interp(grid, t[part], v[part])
        out.append({"t0": round(float(grid[0]), 4), "dt": 1.0 / rate, "v": [round(float(x), digits) for x in values]})
    return out


def _intervals(pairs: list[tuple[float, float]]) -> list[list[float]]:
    return [[round(float(a), 3), round(float(b), 3)] for a, b in pairs]


def _fmt(value: float | None, digits: int = 2) -> str:
    return "—" if value is None or not math.isfinite(value) else f"{value:.{digits}f}"


def _value_text(check: dict[str, Any]) -> str:
    v, unit = check["value"], check["unit"]
    if v is None:
        return "—"
    if unit == "bool":
        return "yes" if v >= 1 else "no"
    if unit == "windows":
        return f"{v:.0f}"
    if unit == "ppm":
        return f"{v:.4f} ppm"
    if unit == "us":
        return f"{v:.1f} µs"
    if unit == "ms":
        return f"{v:.2f} ms"
    if unit in ("bpm", "%", "breaths/min"):
        return f"{v:.2f} {unit.replace('breaths/min', '/min')}"
    if unit == "uS":
        return f"{v:.3f} µS"
    return f"{v:.3f}"


def _target_text(check: dict[str, Any]) -> str:
    target = check["target"].replace("<=", "≤").replace(">=", "≥").replace("==", "=")
    unit = {"us": "µs", "uS": "µS", "bool": "", "breaths/min": "/min", "windows": ""}.get(check["unit"], check["unit"])
    if check["unit"] == "bool":
        target = "exact"
    return f"{target} {unit}".strip()


def build_report(run: Any, truth: dict[str, Any], scorecard: dict[str, Any], counterfactual: Any,
                 records: list[dict[str, Any]], replay_identical: bool = True, standalone: bool = True) -> str:
    data, static = _report_data(run, truth, scorecard, counterfactual, records, replay_identical)
    css = (TEMPLATE_DIR / "report.css").read_text(encoding="utf-8")
    script = (TEMPLATE_DIR / "report.js").read_text(encoding="utf-8")
    body = (TEMPLATE_DIR / "report.html").read_text(encoding="utf-8")
    for key, value in static.items():
        body = body.replace("{{" + key + "}}", value)
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    fonts = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
             '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400'
             '&family=JetBrains+Mono:wght@400;600&family=Saira+Semi+Condensed:wght@500;600;700&display=swap">')
    head = f"<title>CIRCLE Closed-Loop Session</title>\n{fonts}\n<style>\n{css}\n</style>\n"
    content = (f"{body}\n<script type=\"application/json\" id=\"session-data\">{payload}</script>\n"
               f"<script>\n{script}\n</script>\n")
    if not standalone:
        return head + content
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
            f"{head}</head>\n<body>\n{content}</body>\n</html>\n")


def _report_data(run: Any, truth: dict[str, Any], scorecard: dict[str, Any], counterfactual: Any,
                 records: list[dict[str, Any]], replay_identical: bool) -> tuple[dict[str, Any], dict[str, str]]:
    an = run.analysis
    clock = an.clock
    lab = lambda device_s: clock.lab_seconds(np.asarray(device_s, dtype=float) * 1e6)  # noqa: E731
    to_device_s = lambda lab_s: (clock.offset_us + np.asarray(lab_s, dtype=float) * clock.slope_us_per_s) / 1e6  # noqa: E731
    sections = scorecard["sections"]
    duration = float(run.rig.horizon_s)
    tt = np.array(truth["t_s"])
    ppg = run.raw.streams["ppg"]
    ppg_t = lab(ppg.device_time_us / 1e6)

    # ---------------------------------------------------------------- series
    beats = an.beats
    beat_t = lab(beats["t_s"])
    quality_code = {"GOOD": "G", "MOTION": "M", "EDGE": "E", "LOW_TEMPLATE_CORRELATION": "L"}
    systolic = np.array([b["systolic_s"] for b in truth["beats"]])
    grid = np.arange(2.0, duration, 0.5)
    hr_est = heart_rate_series(beats, to_device_s(grid))
    hr_truth = np.interp(grid, 0.5 * (systolic[1:] + systolic[:-1]), 60.0 / np.diff(systolic))
    resp = an.respiration
    spo2 = an.spo2
    spo2_t = lab(spo2["t_s"])
    eda = an.eda
    eda_t = lab(eda["t_s"])
    motion = an.motion
    evals = [e for e in run.evaluations if "arousal_index" in e.features]
    series = {
        "ppg": _segments(ppg_t, beats["bandpassed"], 50.0, 1, max_gap=0.05),
        "hr_est": _segments(grid, hr_est, 2.0, 2),
        "hr_truth": _segments(grid, hr_truth, 2.0, 2),
        "riiv": _segments(lab(resp["t_s"]), resp["riiv"] * 1000.0, 10.0, 3, max_gap=0.3),
        "rr_truth": _segments(tt, np.array(truth["resp_rate_bpm"]), 2.0, 2),
        "spo2_naive": _segments(spo2_t, spo2["naive_pct"], 1.0, 2, max_gap=1.5),
        "spo2_gated": _segments(spo2_t, spo2["gated_pct"], 1.0, 2, max_gap=1.5),
        "spo2_truth": _segments(tt, np.array(truth["spo2_pct"]), 2.0, 2),
        "eda": _segments(eda_t, eda["conductance_us"], 8.0, 4),
        "eda_tonic": _segments(eda_t, eda["tonic_us"], 4.0, 4),
        "eda_truth": _segments(tt, np.array(truth["scl_tonic_us"]), 2.0, 4),
        "motion": _segments(lab(motion["t_s"]), motion["intensity_g"], 10.0, 4),
        "arousal_truth": _segments(tt, np.array(truth["arousal"]), 2.0, 4),
    }
    points = {
        "rr_est": [[_r(t, 3), _r(v, 2)] for t, v in zip(lab(resp["rate_t_s"]), resp["rate_bpm"])],
        "breaths": [_r(t, 3) for t in lab(resp["breaths_s"])],
        "index": [[_r(lab(e.window_end_us / 1e6), 3), _r(e.features["arousal_index"], 3),
                   int(e.features.get("quality_ok", 0)), int(e.features.get("armed", 0))] for e in evals],
    }
    if counterfactual is not None:
        cf_truth = counterfactual.twin.truth()
        cf_sys = np.array([b["systolic_s"] for b in cf_truth["beats"]])
        cf_tt = np.array(cf_truth["t_s"])
        series["hr_cf"] = _segments(grid, np.interp(grid, 0.5 * (cf_sys[1:] + cf_sys[:-1]), 60.0 / np.diff(cf_sys)), 2.0, 2)
        series["rr_cf"] = _segments(cf_tt, np.array(cf_truth["resp_rate_bpm"]), 2.0, 2)
        series["arousal_cf"] = _segments(cf_tt, np.array(cf_truth["arousal"]), 2.0, 4)

    # ---------------------------------------------------------------- events
    stim = [_r(t, 3) for t in truth["stimuli_s"]]
    gaps = []
    for g in run.raw.gaps:
        before = ppg.sequence < g.first_sequence
        after = ppg.sequence > g.last_sequence
        if before.any() and after.any():
            gaps.append({"a": _r(ppg_t[before][-1], 3), "b": _r(ppg_t[after][0], 3),
                         "first": g.first_sequence, "last": g.last_sequence, "cause": g.cause})
    decisions = [{"t": _r(lab(e.device_time_us / 1e6), 3), "action": e.action, "id": e.decision_id}
                 for e in run.evaluations if e.decision_id]
    program_spans = []
    for d in decisions:
        if d["action"] == "START_PACED_BREATHING":
            stop = next((x["t"] for x in decisions if x["id"] == f"{d['id']}-STOP"), duration)
            program_spans.append([d["t"], stop])
    cues = []
    haptic_truth = {(h["program"], h["cue_index"]): h for h in truth["timing"]["haptic"]}
    for h in an.haptic:
        entry = {"t": _r(lab(h["command_s"]), 3)}
        if "electrical_onset_s" in h:
            entry["elec_ms"] = _r((h["electrical_onset_s"] - h["command_s"]) * 1000, 3)
        if "physical_onset_s" in h:
            entry["phys_ms"] = _r((h["physical_onset_s"] - h["command_s"]) * 1000, 3)
        key = (h["program"], h["cue_index"])
        if key in haptic_truth:
            entry["truth_ms"] = _r((haptic_truth[key]["physical_onset_exact_device_us"] / 1e6 - h["command_s"]) * 1000, 3)
        cues.append(entry)
    sham_cues = [_r(lab(e.device_time_us / 1e6), 3) for e in run.raw.events_of("HAPTIC_COMMAND_SHAM")]
    scr_det = [{"o": _r(lab(s["onset_s"]), 3), "p": _r(lab(s["peak_s"]), 3), "a": _r(s["amplitude_us"], 3),
                "w": int(s["motion_confounded"])} for s in eda["scrs"]]
    scr_truth = [{"o": _r(s["onset_s"], 3), "p": _r(s["peak_s"], 3), "a": _r(s["amplitude_us"], 3)} for s in truth["scrs"]]

    # ------------------------------------------------------------ micro trace
    micro = None
    if an.haptic and "physical_onset_s" in an.haptic[0]:
        h = an.haptic[0]
        imu = run.raw.streams["imu"]
        t_dev = imu.device_time_us / 1e6
        lo = int(np.searchsorted(t_dev, h["command_s"] - 0.02))
        hi = int(np.searchsorted(t_dev, h["command_s"] + 0.09))
        accel, _ = imu_physical(imu, run.raw.descriptors["imu"])
        command = run.raw.events_of("HAPTIC_COMMAND")[0]
        env = _carrier_envelope(accel[lo:hi], run.raw.descriptors["imu"]["nominal_rate_hz"], command.attribute("lra_hz"))
        env_t = (t_dev[lo:lo + len(env)] + 1.5 / run.raw.descriptors["imu"]["nominal_rate_hz"] - h["command_s"]) * 1000
        az = accel[lo:hi, 2] - np.median(accel[lo:lo + 8, 2])
        micro = {"raw_t": [_r(x, 3) for x in (t_dev[lo:hi] - h["command_s"]) * 1000], "raw": [_r(x, 4) for x in az],
                 "env_t": [_r(x, 3) for x in env_t], "env": [_r(x, 4) for x in env], **cues[0]}

    # ------------------------------------------------------------- chapters
    hold = sections["respiration"]
    spo2_s = sections["spo2"]
    fidget = next(((m["start_s"], m["start_s"] + m["duration_s"]) for m in truth["motion_episodes"] if m["label"] == "FIDGET"), None)
    phases = {p["name"]: (p["start_s"], p["end_s"]) for p in truth["phases"]}
    chapters = [{"id": "all", "label": "Whole session", "t0": 0.0, "t1": duration,
                 "caption": f"{duration / 60:.0f} minutes: rest, a 30 s breath hold, a stressor with {len(stim)} timed stimuli, "
                            f"then recovery with closed-loop haptic guidance. Hover to read every channel against ground truth."}]
    if hold["apnea_truth"] and hold["apnea_detected"]:
        (ta, tb), (da, db) = hold["apnea_truth"][0], hold["apnea_detected"][0]
        chapters.append({"id": "hold", "label": "Breath hold", "t0": ta - 12, "t1": tb + 24,
                         "caption": f"The optical breathing signal goes flat. Apnea detected {da:.1f}–{db:.1f} s from PPG alone "
                                    f"(truth {ta:.1f}–{tb:.1f} s). SpO₂ bottoms out about 11 s later because of circulatory "
                                    f"delay: estimated drop {spo2_s['estimated_drop_pct']:.1f} points, true drop "
                                    f"{spo2_s['truth_drop_pct']:.1f}."})
    if phases.get("STRESSOR"):
        s0 = phases["STRESSOR"][0]
        rest = np.nanmedian(hr_est[(grid > 10) & (grid < 55)])
        stress = np.nanmedian(hr_est[(grid > s0 + 30) & (grid < phases["STRESSOR"][1])])
        good = beats["quality"] == "GOOD"
        amp_rest = np.median(beats["pulse_amplitude_pct"][good & (beat_t > 10) & (beat_t < 55)])
        amp_stress = np.median(beats["pulse_amplitude_pct"][good & (beat_t > s0 + 30) & (beat_t < phases["STRESSOR"][1])])
        latencies = []
        for scr in scr_det:
            prior = [t for t in stim if t <= scr["o"]]
            if prior and 0.5 <= scr["o"] - prior[-1] <= 4.0 and not scr["w"]:
                latencies.append(scr["o"] - prior[-1])
        lat = f"{np.median(latencies):.1f} s" if latencies else "—"
        chapters.append({"id": "stress", "label": "Stressor", "t0": s0 - 8, "t1": s0 + 44,
                         "caption": f"Stimuli arrive every ~12 s. Heart rate rises from {rest:.0f} to {stress:.0f} bpm and skin "
                                    f"conductance climbs, with responses following stimuli by a median {lat}. Pulse amplitude "
                                    f"falls from {amp_rest:.2f} % to {amp_stress:.2f} % of DC as vessels constrict."})
    if fidget:
        in_f = (spo2_t >= fidget[0] - 2) & (spo2_t <= fidget[1] + 2)
        naive_min = float(np.min(spo2["naive_pct"][in_f])) if in_f.any() else float("nan")
        withheld = sections["eda"]["confounded_artifacts_withheld"]
        chapters.append({"id": "fidget", "label": "Hand movement", "t0": fidget[0] - 6, "t1": fidget[1] + 8,
                         "caption": f"The wrist moves. Naive SpO₂ drops to {naive_min:.1f} % because motion shifts red and IR "
                                    f"light equally, pushing the ratio toward 1. The IMU flags the episode, so gated SpO₂ is "
                                    f"withheld: {spo2_s['false_desaturation_windows_naive']} false-desaturation windows naive, "
                                    f"{spo2_s['false_desaturation_windows_gated']} gated. Across the session, {withheld} SCR-like "
                                    f"motion artifacts are withheld rather than reported."})
    if gaps:
        g = gaps[0]
        n = g["last"] - g["first"] + 1
        chapters.append({"id": "gap", "label": "FIFO overflow", "t0": g["a"] - 2.2, "t1": g["b"] + 2.2,
                         "caption": f"The optical FIFO overflowed while firmware was stalled. {n} samples were lost and "
                                    f"counted by OVF_COUNTER, so the session declares the exact range #{g['first']}–#{g['last']}. "
                                    f"Timestamps resume without a jump (worst PPG timestamp error "
                                    f"{sections['timing']['ppg_sample_max_us']:.0f} µs, limit 1000 µs)."})
    start = next((d for d in decisions if d["action"] == "START_PACED_BREATHING"), None)
    if start:
        stop = next((d for d in decisions if d["id"] == f"{start['id']}-STOP"), None)
        ev = next(e for e in run.evaluations if e.decision_id == start["id"])
        rr_pts = np.array([p for p in points["rr_est"] if p[0] and start["t"] + 20 <= p[0] <= (stop["t"] if stop else duration)])
        rr_text = f"{np.median(rr_pts[:, 1]):.1f}" if len(rr_pts) else "—"
        release = (f"The index then fell below 1.0 twice and released guidance at {stop['t']:.0f} s."
                   if stop else "Guidance ran to the end of the session.")
        cf_text = " The grey traces are the matched sham arm, with identical noise and no actuation." if counterfactual else ""
        chapters.append({"id": "loop", "label": "Closed loop", "t0": start["t"] - 18, "t1": min(duration, (stop["t"] if stop else duration) + 20),
                         "caption": f"Guidance is armed for recovery. The arousal index read {ev.features['arousal_index']:.1f}, above "
                                    f"2.0 on two evaluations in a row, so decision {start['id']} started paced breathing at "
                                    f"{start['t']:.0f} s. Breathing entrained to {rr_text}/min against a 6/min cue and heart-rate "
                                    f"swings grew. {release}{cf_text}"})

    data = {
        "duration": duration,
        "phases": [[p["name"], p["start_s"], min(p["end_s"], duration)] for p in truth["phases"]],
        "stimuli": stim, "gaps": gaps, "decisions": decisions, "program_spans": program_spans,
        "cues": cues, "sham_cues": sham_cues,
        "motion_detected": _intervals([(float(lab(a)), float(lab(b))) for a, b in motion["episodes"]]),
        "motion_truth": _intervals([(m["start_s"], m["start_s"] + m["duration_s"]) for m in truth["motion_episodes"]]),
        "apnea_detected": _intervals(hold["apnea_detected"]), "apnea_truth": _intervals(hold["apnea_truth"]),
        "beats": {"t": [_r(t, 3) for t in beat_t], "q": "".join(quality_code.get(q, "L") for q in beats["quality"])},
        "systolic": [_r(t, 3) for t in systolic if t <= duration],
        "scr": scr_det, "scr_truth": scr_truth,
        "series": series, "points": points, "chapters": chapters,
        "thresholds": {"trigger": run.config.controller.trigger_index, "release": run.config.controller.release_index},
        "micro": micro, "has_counterfactual": counterfactual is not None,
    }
    return data, _static_sections(run, truth, scorecard, counterfactual, records, replay_identical, decisions, cues, sections)


def _static_sections(run: Any, truth: dict[str, Any], scorecard: dict[str, Any], counterfactual: Any,
                     records: list[dict[str, Any]], replay_identical: bool, decisions: list[dict[str, Any]],
                     cues: list[dict[str, Any]], sections: dict[str, Any]) -> dict[str, str]:
    checks = {c["id"]: c for c in scorecard["checks"]}
    passed = sum(c["passed"] for c in scorecard["checks"])
    rows = []
    for group, ids in GROUPS:
        present = [checks[i] for i in ids if i in checks]
        if not present:
            continue
        rows.append(f'<tr class="group"><th colspan="4" scope="rowgroup">{escape(group)}</th></tr>')
        for c in present:
            state = "pass" if c["passed"] else "fail"
            source = "Spec" if c["source"].startswith("SPEC") else "Twin"
            source_title = escape(c["source"])
            rows.append(
                f'<tr><th scope="row">{escape(c["label"])}</th>'
                f'<td class="num">{escape(_value_text(c))}</td>'
                f'<td class="num target">{escape(_target_text(c))} <abbr class="src src-{source.lower()}" title="{source_title}">{source}</abbr></td>'
                f'<td><span class="pill {state}">{"✓ Pass" if c["passed"] else "✕ Fail"}</span></td></tr>')
    types: dict[str, int] = {}
    for r in records:
        types[r["record_type"]] = types.get(r["record_type"], 0) + 1
    samples = sum(len(s) for n, s in run.raw.streams.items() if n != "sync")
    lost = sum(g.last_sequence - g.first_sequence + 1 for g in run.raw.gaps)
    arm = "Active" if run.config.actuate else "Sham"
    status = [
        ("Truth checks", f"{passed}/{len(scorecard['checks'])}", "pass" if passed == len(scorecard["checks"]) else "fail"),
        ("Decisions replayed", f"{len(run.evaluations)}/{len(run.evaluations)}" if replay_identical else "mismatch",
         "pass" if replay_identical else "fail"),
        ("Session records", f"{len(records)}", "neutral"),
        ("Raw samples", f"{samples:,}", "neutral"),
        ("Lost, declared exactly", f"{lost}", "neutral"),
    ]
    status_html = "".join(f'<div class="stat {k}"><dt>{escape(a)}</dt><dd>{escape(b)}</dd></div>' for a, b, k in status)

    # Evidence chain.
    start = next((e for e in run.evaluations if e.action == "START_PACED_BREATHING"), None)
    stop = next((e for e in run.evaluations if e.action and e.action.startswith("STOP")), None)
    lab = lambda us: float(run.analysis.clock.lab_seconds(us))  # noqa: E731
    chain = []
    if start is not None:
        f = start.features
        ranges = ", ".join(f'{r["stream_id"].upper()} #{r["first_sequence"]:,}–#{r["last_sequence"]:,}' for r in start.source_sequence_ranges)
        chain.append(("Evaluation", f"t = {lab(start.device_time_us):.1f} s",
                      f"Arousal index <b>{f['arousal_index']:.2f}</b> from heart rate z {f['hr_z']:.1f}, skin conductance z "
                      f"{f['scl_z']:.1f} and SCR rate z {f['scr_z']:.1f}. Signal quality passed: beat coverage "
                      f"{f['beat_coverage']:.0%}, no motion. Window ends 1 s before the decision.",
                      f"Source ranges: {ranges}"))
        chain.append(("Decision", start.decision_id,
                      "Second consecutive evaluation at or above the trigger index of 2.0, so the controller starts "
                      "paced breathing: one haptic cue every 10 s (6 breaths/min).",
                      "MODEL_RESULT record, MODEL_INFERRED, CRC-32C sealed"))
        elec = [c["elec_ms"] for c in cues if c.get("elec_ms") is not None]
        phys = [c["phys_ms"] for c in cues if c.get("phys_ms") is not None]
        err = [c["phys_ms"] - c["truth_ms"] for c in cues if c.get("phys_ms") is not None and c.get("truth_ms") is not None]
        if elec:
            chain.append(("Actuation", f"{len(cues)} cues",
                          f"Each GO command is followed by a TLV3201 current edge on GPIO46 after a median "
                          f"<b>{np.median(elec):.2f} ms</b>, and by vibration that the IMU observes after a median "
                          f"<b>{np.median(phys):.2f} ms</b>. Against hidden truth the physical onset error stays within "
                          f"{np.max(np.abs(err)):.2f} ms, about one 2.5 ms IMU sample.",
                          "EVENT records: command, electrical onset, completion, physical observation"))
        else:
            chain.append(("Sham arm", f"{len(cues) or len(run.raw.events_of('HAPTIC_COMMAND_SHAM'))} cues logged",
                          "Commands are logged but not actuated, so there is no electrical or physical evidence.",
                          "EVENT records: HAPTIC_COMMAND_SHAM"))
        if stop is not None:
            chain.append(("Release", stop.decision_id,
                          f"At t = {lab(stop.device_time_us):.1f} s the index read {stop.features.get('arousal_index', float('nan')):.2f}, "
                          "below the release level of 1.0 on two consecutive evaluations after the 60 s minimum.",
                          "MODEL_RESULT record with decision_id"))
        chain.append(("Audit", "re-derived",
                      f"{'All' if replay_identical else 'Not all'} {len(run.evaluations)} evaluations re-derive bit-for-bit from the "
                      "raw bundle alone. The INTERVENTION record lists every command, electrical onset and physical observation "
                      "by evidence id.",
                      "python tools/audit_physiology_run.py &lt;run directory&gt;"))
    chain_html = "".join(
        f'<li><div class="step-head"><span class="step-kind">{escape(k)}</span><span class="step-id">{escape(i)}</span></div>'
        f'<p>{body}</p><p class="step-meta">{meta}</p></li>' for k, i, body, meta in chain)

    # Counterfactual.
    cf_html = '<p class="muted">Run without <code>--no-counterfactual</code> to include the matched opposite arm.</p>'
    if counterfactual is not None and start is not None:
        cf_truth = counterfactual.twin.truth()
        tt = np.array(truth["t_s"])
        t0 = lab(start.device_time_us)
        this_label, other_label = ("Guided", "Sham") if run.config.actuate else ("Sham", "Guided")

        def at(values: list[float], t: float) -> float:
            return float(np.interp(t, tt, np.array(values)))

        def half_time(values: list[float]) -> float | None:
            arr = np.array(values)
            base = float(np.median(arr[(tt > 10) & (tt < 55)]))
            peak = at(values, t0)
            target = base + 0.5 * (peak - base)
            after = np.flatnonzero((tt >= t0) & (arr <= target))
            return float(tt[after[0]] - t0) if len(after) else None

        rows_cf = []
        for label, key, digits, unit in (("Latent arousal, +60 s", "arousal", 2, ""), ("Heart rate, +60 s", "hr_bpm", 1, " bpm")):
            rows_cf.append((label, f"{at(truth[key], t0 + 60):.{digits}f}{unit}", f"{at(cf_truth[key], t0 + 60):.{digits}f}{unit}"))
        rows_cf.append(("Breathing rate, +60 s", f"{at(truth['resp_rate_bpm'], t0 + 60):.1f} /min",
                        f"{at(cf_truth['resp_rate_bpm'], t0 + 60):.1f} /min"))
        h_this, h_other = half_time(truth["arousal"]), half_time(cf_truth["arousal"])
        rows_cf.append(("Arousal half-recovery", f"{h_this:.0f} s" if h_this else "not reached",
                        f"{h_other:.0f} s" if h_other else "not reached in session"))
        body_rows = "".join(f'<tr><th scope="row">{a}</th><td class="num">{b}</td><td class="num">{c}</td></tr>' for a, b, c in rows_cf)
        cf_html = (f'<table class="cf"><thead><tr><th scope="col">Twin ground truth after {start.decision_id}</th>'
                   f'<th scope="col">{this_label}</th><th scope="col">{other_label}</th></tr></thead><tbody>{body_rows}</tbody></table>'
                   '<p class="note">Both arms share every random draw, so they are identical until the first cue. The '
                   'difference is produced by the twin\'s assumed response to paced breathing. It demonstrates that the '
                   'evidence chain can resolve an effect; it is not evidence that the effect exists in people.</p>')
    seed = run.config.twin.seed
    arm_flag = "" if run.config.actuate else " --sham"
    return {
        "EYEBROW": escape(f"Simulated session · physiology twin · seed {seed} · {arm.lower()} arm"),
        "STATUS": status_html,
        "SCORE_ROWS": "".join(rows),
        "CHAIN": chain_html or '<li><p>No closed-loop decision was taken in this session.</p></li>',
        "COUNTERFACTUAL": cf_html,
        "RUN_COMMAND": escape(f"python tools/run_physiology_twin.py --seed {seed}{arm_flag} --output outputs/physiology --audit"),
        "AUDIT_COMMAND": escape("python tools/audit_physiology_run.py outputs/physiology"),
        "BENCH_COMMAND": escape("python tools/run_physiology_twin.py --benchmark 50"),
        "SEED": str(seed),
    }
