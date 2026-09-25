"""Score pipeline outputs against twin ground truth.

Scoring conventions (documented in docs/physiology-pipeline.md):
  * Pipeline device times are mapped to laboratory time with the pipeline's
    OWN SYNC clock fit, never with the hidden device-clock truth.
  * Beats: truth fiducial = observable systolic maximum; +/-50 ms tolerance;
    one-to-one nearest matching. Samples near declared gaps and session edges
    are excluded; motion-free statistics are reported separately.
  * SCRs: truth onsets closer than 1 s are merged (unresolvable); scorable
    truth has amplitude >= 0.05 uS and lies outside motion episodes; motion-
    confounded detections are withheld, not claimed; +/-1 s onset tolerance.
  * Targets tagged SPEC come from CIRCLE documents; targets tagged TWIN are
    software regression targets for this twin, not clinical accuracy claims.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from .pipeline import heart_rate_series, rmssd_ms

SCR_MERGE_AFTER_PEAK_S = 0.5


@dataclass(frozen=True)
class Check:
    id: str
    label: str
    value: float | None
    target: str
    unit: str
    source: str
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        value = None if self.value is None or not math.isfinite(self.value) else round(float(self.value), 6)
        return {"id": self.id, "label": self.label, "value": value, "target": self.target,
                "unit": self.unit, "source": self.source, "passed": bool(self.passed)}


def _match(truth: np.ndarray, detected: np.ndarray, tolerance: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Greedy one-to-one matching by increasing distance. Returns (truth_hit, det_hit, errors)."""
    truth = np.asarray(truth, dtype=np.float64)
    detected = np.asarray(detected, dtype=np.float64)
    pairs = []
    order = np.argsort(detected)
    sorted_det = detected[order]
    for i, x in enumerate(truth):
        lo = np.searchsorted(sorted_det, x - tolerance)
        hi = np.searchsorted(sorted_det, x + tolerance, side="right")
        for j in range(lo, hi):
            pairs.append((abs(sorted_det[j] - x), i, int(order[j])))
    pairs.sort()
    truth_hit = np.zeros(len(truth), dtype=bool)
    det_hit = np.zeros(len(detected), dtype=bool)
    errors = np.full(len(truth), np.nan)
    for _, i, j in pairs:
        if not truth_hit[i] and not det_hit[j]:
            truth_hit[i] = det_hit[j] = True
            errors[i] = detected[j] - truth[i]
    return truth_hit, det_hit, errors


def _pairs(truth: np.ndarray, detected: np.ndarray, tolerance: float) -> list[tuple[int, int]]:
    """(truth index, detected index) pairs from the same one-to-one matching as _match."""
    pairs = []
    for i, x in enumerate(truth):
        for j, y in enumerate(detected):
            if abs(y - x) <= tolerance:
                pairs.append((abs(y - x), i, j))
    pairs.sort()
    used_t, used_d, out = set(), set(), []
    for _, i, j in pairs:
        if i not in used_t and j not in used_d:
            used_t.add(i)
            used_d.add(j)
            out.append((i, j))
    return out


def _outside(t: np.ndarray, intervals: list[tuple[float, float]], pad: float = 0.0) -> np.ndarray:
    keep = np.ones(len(t), dtype=bool)
    for a, b in intervals:
        keep &= ~((t >= a - pad) & (t <= b + pad))
    return keep


def _iou(truth: list[tuple[float, float]], found: list[tuple[float, float]]) -> float:
    grid = np.arange(0.0, max([b for _, b in truth + found] + [1.0]) + 1.0, 0.05)
    a = ~_outside(grid, truth)
    b = ~_outside(grid, found)
    union = np.sum(a | b)
    return float(np.sum(a & b) / union) if union else float("nan")


def score(run: Any, truth: dict[str, Any]) -> dict[str, Any]:
    """Return {sections: {...}, checks: [...]} for one SessionRun."""
    an = run.analysis
    clock = an.clock
    lab = lambda device_s: clock.lab_seconds(np.asarray(device_s, dtype=np.float64) * 1e6)  # noqa: E731
    to_device_s = lambda lab_s: (clock.offset_us + np.asarray(lab_s, dtype=np.float64) * clock.slope_us_per_s) / 1e6  # noqa: E731
    timing = truth["timing"]
    rig = run.rig
    ppg_t = rig.ppg_all_t
    gap_windows = [(float(ppg_t[a]), float(ppg_t[b])) for a, b in timing["ppg_lost_sequences"]]
    motion_truth = [(m["start_s"], m["start_s"] + m["duration_s"]) for m in truth["motion_episodes"]]
    t_first = 5.0
    t_last = rig.horizon_s - 2.0
    sections: dict[str, Any] = {}
    checks: list[Check] = []

    # ---------------------------------------------------------------- timing
    def pct(values: list[float], q: float) -> float:
        return float(np.percentile(np.abs(np.asarray(values, dtype=np.float64)), q))

    eda_err, imu_err, ppg_err = timing["eda_edge_error_us"], timing["imu_edge_error_us"], timing["ppg_sample_error_us"]
    declared = sorted((g.first_sequence, g.last_sequence) for g in run.raw.gaps)
    sections["timing"] = {
        "clock_ppm_estimate": clock.ppm, "clock_ppm_truth": timing["device_clock_ppm"],
        "clock_ppm_error": clock.ppm - timing["device_clock_ppm"],
        "clock_offset_error_us": clock.offset_us - timing["device_boot_offset_s"] * 1e6,
        "sync_residual_rms_us": clock.residual_rms_us,
        "eda_edge_p999_us": pct(eda_err, 99.9), "eda_edge_max_us": pct(eda_err, 100),
        "imu_edge_p999_us": pct(imu_err, 99.9), "imu_edge_max_us": pct(imu_err, 100),
        "ppg_sample_p50_us": pct(ppg_err, 50), "ppg_sample_max_us": pct(ppg_err, 100),
        "declared_gaps": declared, "true_lost_ranges": [tuple(x) for x in timing["ppg_lost_sequences"]],
    }
    ts = sections["timing"]
    checks += [
        Check("clock_ppm", "SYNC clock-rate estimate error", abs(ts["clock_ppm_error"]), "<= 0.1", "ppm", "TWIN", abs(ts["clock_ppm_error"]) <= 0.1),
        Check("edge_p999", "EDA/IMU edge timestamp P99.9", max(ts["eda_edge_p999_us"], ts["imu_edge_p999_us"]), "<= 10", "us", "SPEC validation-plan.md",
              max(ts["eda_edge_p999_us"], ts["imu_edge_p999_us"]) <= 10),
        Check("edge_max", "EDA/IMU edge timestamp max", max(ts["eda_edge_max_us"], ts["imu_edge_max_us"]), "<= 25", "us", "SPEC validation-plan.md",
              max(ts["eda_edge_max_us"], ts["imu_edge_max_us"]) <= 25),
        Check("ppg_fifo", "PPG FIFO timestamp reconstruction max", ts["ppg_sample_max_us"], "<= 1000", "us", "SPEC timing-and-data-model.md",
              ts["ppg_sample_max_us"] <= 1000),
        Check("gaps_exact", "Declared GAP ranges equal true sample loss", float(declared == sorted(ts["true_lost_ranges"])), "== 1", "bool", "SPEC timing-and-data-model.md",
              declared == sorted(ts["true_lost_ranges"])),
    ]

    # ----------------------------------------------------------------- beats
    beats = an.beats
    truth_beats = np.array([b["systolic_s"] for b in truth["beats"]])
    det_lab = lab(beats["t_s"])
    scorable = (truth_beats > t_first) & (truth_beats < t_last) & _outside(truth_beats, gap_windows, pad=1.5)
    det_scorable = (det_lab > t_first) & (det_lab < t_last) & _outside(det_lab, gap_windows, pad=1.5)
    tb, db = truth_beats[scorable], det_lab[det_scorable]
    hit, dhit, err = _match(tb, db, 0.05)
    clean_t = _outside(tb, motion_truth, pad=0.5)
    clean_d = _outside(db, motion_truth, pad=0.5)
    hit_c, dhit_c, err_c = _match(tb[clean_t], db[clean_d], 0.05)

    def f1(tp: int, n_truth: int, n_det: int) -> tuple[float, float, float]:
        se = tp / n_truth if n_truth else float("nan")
        ppv = tp / n_det if n_det else float("nan")
        return se, ppv, (2 * se * ppv / (se + ppv) if se + ppv else 0.0)

    se_all, ppv_all, f1_all = f1(int(hit.sum()), len(tb), len(db))
    se_c, ppv_c, f1_c = f1(int(hit_c.sum()), int(clean_t.sum()), int(clean_d.sum()))
    e_ms = err_c[np.isfinite(err_c)] * 1000
    sections["beats"] = {"truth": len(tb), "detected": len(db), "sensitivity": se_all, "ppv": ppv_all, "f1": f1_all,
                         "motion_free_sensitivity": se_c, "motion_free_ppv": ppv_c, "motion_free_f1": f1_c,
                         "fiducial_bias_ms": float(np.median(e_ms)) if len(e_ms) else float("nan"),
                         "fiducial_p95_abs_ms": float(np.percentile(np.abs(e_ms), 95)) if len(e_ms) else float("nan"),
                         "quality_counts": {q: int(np.sum(beats["quality"] == q)) for q in sorted(set(beats["quality"]))}}
    checks.append(Check("beat_f1", "PPG beat F1 (motion-free, +/-50 ms)", f1_c, ">= 0.99", "", "TWIN", f1_c >= 0.99))
    checks.append(Check("beat_f1_all", "PPG beat F1 (all, incl. motion)", f1_all, ">= 0.95", "", "TWIN", f1_all >= 0.95))

    # -------------------------------------------------------------- HR, HRV
    ibi_mid = 0.5 * (truth_beats[1:] + truth_beats[:-1])
    truth_hr = 60.0 / np.diff(truth_beats)
    grid = np.arange(math.ceil(t_first) + 5, math.floor(t_last), 1.0)
    grid = grid[_outside(grid, gap_windows, pad=2.0)]
    est = heart_rate_series(beats, to_device_s(grid))
    ref = np.interp(grid, ibi_mid, truth_hr)
    ok = np.isfinite(est)
    hr_err = np.abs(est[ok] - ref[ok])
    windows_rmssd = []
    for w0 in np.arange(10.0, t_last - 60.0, 60.0):
        in_w = (truth_beats[1:] >= w0) & (truth_beats[1:] < w0 + 60)
        ibis = np.diff(truth_beats)[in_w]
        truth_rmssd = float(np.sqrt(np.mean(np.diff(ibis) ** 2)) * 1000) if len(ibis) > 5 else float("nan")
        est_rmssd = rmssd_ms(beats, float(to_device_s(w0)), float(to_device_s(w0 + 60)))
        windows_rmssd.append({"start_s": float(w0), "truth_ms": truth_rmssd, "estimate_ms": est_rmssd})
    rm = np.array([[w["truth_ms"], w["estimate_ms"]] for w in windows_rmssd if math.isfinite(w["estimate_ms"]) and math.isfinite(w["truth_ms"])])
    rmssd_mae = float(np.mean(np.abs(rm[:, 1] - rm[:, 0]))) if len(rm) else float("nan")
    sections["heart_rate"] = {"mae_bpm": float(np.mean(hr_err)) if len(hr_err) else float("nan"),
                              "p95_abs_bpm": float(np.percentile(hr_err, 95)) if len(hr_err) else float("nan"),
                              "coverage": float(ok.mean()) if len(ok) else 0.0,
                              "rmssd_windows": windows_rmssd, "rmssd_mae_ms": rmssd_mae}
    checks.append(Check("hr_mae", "Heart rate MAE (1 Hz)", sections["heart_rate"]["mae_bpm"], "<= 1.0", "bpm", "TWIN", sections["heart_rate"]["mae_bpm"] <= 1.0))
    checks.append(Check("rmssd_mae", "RMSSD MAE (60 s windows)", rmssd_mae, "<= 5", "ms", "TWIN", rmssd_mae <= 5))

    # ----------------------------------------------------------- respiration
    tt = np.array(truth["t_s"])
    resp = an.respiration
    rt = lab(resp["rate_t_s"])
    truth_rr = np.interp(rt, tt, np.array(truth["resp_rate_bpm"]))
    hold = np.array(truth["breath_hold"]) > 0.5
    hold_runs = []
    if hold.any():
        idx = np.flatnonzero(hold)
        splits = np.flatnonzero(np.diff(idx) > 1)
        for seg in np.split(idx, splits + 1):
            hold_runs.append((float(tt[seg[0]]), float(tt[seg[-1]])))
    use = _outside(rt, hold_runs, pad=5.0) & _outside(rt, motion_truth, pad=2.0) & (truth_rr > 1.0)
    rr_err = np.abs(resp["rate_bpm"][use] - truth_rr[use])
    apnea_found = [(float(lab(a)), float(lab(b))) for a, b in resp["apnea"]]
    apnea_iou = _iou(hold_runs, apnea_found) if hold_runs else float("nan")
    sections["respiration"] = {"rate_mae_bpm": float(np.mean(rr_err)) if len(rr_err) else float("nan"), "rate_points": int(use.sum()),
                               "apnea_truth": hold_runs, "apnea_detected": apnea_found, "apnea_iou": apnea_iou}
    checks.append(Check("resp_mae", "Respiratory rate MAE (RIIV breaths)", sections["respiration"]["rate_mae_bpm"], "<= 1.0", "breaths/min", "TWIN",
                        sections["respiration"]["rate_mae_bpm"] <= 1.0))
    if hold_runs:
        checks.append(Check("apnea_iou", "Breath-hold (apnea) interval IoU", apnea_iou, ">= 0.85", "", "TWIN", apnea_iou >= 0.85))

    # ------------------------------------------------------------------ SpO2
    spo2 = an.spo2
    st = lab(spo2["t_s"])
    truth_s = np.interp(st, tt, np.array(truth["spo2_pct"]))
    g = np.isfinite(spo2["gated_pct"])
    bias = float(np.mean(spo2["gated_pct"][g] - truth_s[g])) if g.any() else float("nan")
    false_naive = int(np.sum((spo2["naive_pct"] < 92.0) & (truth_s >= 94.0)))
    false_gated = int(np.sum((spo2["gated_pct"] < 92.0) & (truth_s >= 94.0)))
    nadir_t = float(tt[int(np.argmin(truth["spo2_pct"]))])
    near = g & (np.abs(st - nadir_t) <= 5.0)
    sections["spo2"] = {"gated_mae_pct": float(np.mean(np.abs(spo2["gated_pct"][g] - truth_s[g]))) if g.any() else float("nan"),
                        "gated_bias_pct": bias, "gated_coverage": float(g.mean()) if len(g) else 0.0,
                        "gated_mae_bias_corrected_pct": float(np.mean(np.abs(spo2["gated_pct"][g] - truth_s[g] - bias))) if g.any() else float("nan"),
                        "false_desaturation_windows_naive": false_naive, "false_desaturation_windows_gated": false_gated,
                        "naive_min_pct": float(np.min(spo2["naive_pct"])) if len(st) else float("nan"),
                        "truth_nadir_pct": float(np.min(truth["spo2_pct"])), "truth_nadir_s": nadir_t,
                        "estimated_drop_pct": float(np.nanmedian(spo2["gated_pct"][g & (st < 55)]) - np.min(spo2["gated_pct"][near])) if near.any() else float("nan"),
                        "truth_drop_pct": float(np.median(np.array(truth["spo2_pct"])[tt < 55]) - np.min(truth["spo2_pct"]))}
    checks.append(Check("spo2_mae", "SpO2 MAE, gated (includes uncalibrated bias)", sections["spo2"]["gated_mae_pct"], "<= 2.0", "%", "TWIN",
                        sections["spo2"]["gated_mae_pct"] <= 2.0))
    checks.append(Check("spo2_false_desat", "False desaturation windows after IMU gating", float(false_gated), "== 0", "windows", "TWIN", false_gated == 0))

    # ------------------------------------------------------------------- EDA
    eda = an.eda
    truth_scr = sorted(truth["scrs"], key=lambda s: s["onset_s"])
    onset_all = np.array([s["onset_s"] for s in truth_scr])
    peak_all = np.array([s["peak_s"] for s in truth_scr])
    amp_all = np.array([s["amplitude_us"] for s in truth_scr])
    # Two responses fuse (no trough between them) when one begins on the other's
    # rising limb or within 0.5 s of its peak, below the 1.2 Hz analysis
    # bandwidth. Fused responses are not counted as missable; a detection may
    # still match any true response when computing PPV.
    resolvable = np.ones(len(truth_scr), dtype=bool)
    for i in range(len(truth_scr)):
        for j in range(len(truth_scr)):
            if i != j and onset_all[j] <= onset_all[i] < peak_all[j] + SCR_MERGE_AFTER_PEAK_S:
                resolvable[i] = resolvable[j] = False
    in_range = (onset_all > t_first + 5) & (onset_all < t_last - 5)
    motion_free = np.array([all(s["peak_s"] + 1.0 < a or s["onset_s"] - 1.0 > b for a, b in motion_truth) for s in truth_scr], dtype=bool)
    scorable_scr = in_range & motion_free & (amp_all >= 0.05) & resolvable
    clean = [s for s in eda["scrs"] if not s["motion_confounded"]]
    confounded = [s for s in eda["scrs"] if s["motion_confounded"]]
    det_on = lab([s["onset_s"] for s in clean]) if clean else np.zeros(0)
    det_in = (det_on > t_first + 5) & (det_on < t_last - 5)
    hit_t, _, err_s = _match(onset_all[scorable_scr], det_on[det_in], 1.0)
    _, det_any, _ = _match(onset_all[in_range], det_on[det_in], 1.0)
    conf_on = lab([s["onset_s"] for s in confounded]) if confounded else np.zeros(0)
    _, conf_hit, _ = _match(onset_all, conf_on, 1.0)
    amp_errors = []
    det_amp = np.array([s["amplitude_us"] for s in clean])[det_in] if clean else np.zeros(0)
    for i, j in _pairs(onset_all[scorable_scr], det_on[det_in], 1.0):
        amp_errors.append(abs(det_amp[j] - amp_all[scorable_scr][i]) / amp_all[scorable_scr][i])
    amp_error = float(np.median(amp_errors)) if amp_errors else float("nan")
    se_scr = float(hit_t.mean()) if len(hit_t) else float("nan")
    ppv_scr = float(det_any.mean()) if len(det_any) else float("nan")
    et = lab(eda["t_s"])
    scl_ref = np.interp(et, tt, np.array(truth["scl_tonic_us"]))
    keep = (et > t_first + 10) & (et < t_last - 5)
    scl_mae = float(np.mean(np.abs(eda["tonic_us"][keep] - scl_ref[keep])))
    sections["eda"] = {"truth_scorable": int(scorable_scr.sum()), "truth_total": len(truth_scr),
                       "truth_fused": int((~resolvable).sum()),
                       "detected_clean": len(clean), "detected_motion_confounded": len(confounded),
                       "confounded_matching_truth": int(conf_hit.sum()),
                       "confounded_artifacts_withheld": int(len(conf_hit) - conf_hit.sum()),
                       "sensitivity": se_scr, "ppv": ppv_scr,
                       "onset_bias_s": float(np.nanmedian(err_s)) if np.isfinite(err_s).any() else float("nan"),
                       "amplitude_median_relative_error": amp_error, "scl_mae_us": scl_mae}
    checks.append(Check("scr_sensitivity", "SCR sensitivity (>= 0.05 uS, motion-free)", se_scr, ">= 0.85", "", "TWIN", se_scr >= 0.85))
    checks.append(Check("scr_ppv", "SCR positive predictive value", ppv_scr, ">= 0.90", "", "TWIN", ppv_scr >= 0.90))
    checks.append(Check("scr_amplitude", "SCR amplitude error (median, relative)", amp_error, "<= 0.15", "", "TWIN", amp_error <= 0.15))
    checks.append(Check("scl_mae", "Tonic skin conductance MAE", scl_mae, "<= 0.10", "uS", "TWIN", scl_mae <= 0.10))

    # ---------------------------------------------------------------- motion
    found = [(float(lab(a)), float(lab(b))) for a, b in an.motion["episodes"]]
    motion_iou = _iou(motion_truth, found)
    sections["motion"] = {"truth": motion_truth, "detected": found, "iou": motion_iou}
    checks.append(Check("motion_iou", "Motion episode IoU (IMU)", motion_iou, ">= 0.60", "", "TWIN", motion_iou >= 0.60))

    # ---------------------------------------------------------------- haptic
    truth_haptic = {(h["program"], h["cue_index"]): h for h in timing["haptic"]}
    lat_e, lat_p, phys_err = [], [], []
    for h in an.haptic:
        key = (h["program"], h["cue_index"])
        if "electrical_onset_s" in h:
            lat_e.append((h["electrical_onset_s"] - h["command_s"]) * 1000)
        if "physical_onset_s" in h:
            lat_p.append((h["physical_onset_s"] - h["command_s"]) * 1000)
            if key in truth_haptic:
                phys_err.append((h["physical_onset_s"] * 1e6 - truth_haptic[key]["physical_onset_exact_device_us"]) / 1000)
    sections["haptic"] = {"cues": len(an.haptic), "electrical_latency_ms_median": float(np.median(lat_e)) if lat_e else float("nan"),
                          "physical_latency_ms_median": float(np.median(lat_p)) if lat_p else float("nan"),
                          "physical_onset_error_ms_max_abs": float(np.max(np.abs(phys_err))) if phys_err else float("nan"),
                          "physical_onset_error_ms_median": float(np.median(phys_err)) if phys_err else float("nan"),
                          "imu_sample_period_ms": 1000.0 / run.raw.descriptors["imu"]["nominal_rate_hz"]}
    if phys_err:
        worst = sections["haptic"]["physical_onset_error_ms_max_abs"]
        checks.append(Check("haptic_physical", "IMU-observed haptic onset error (max)", worst, "<= 5.0", "ms", "TWIN (2 IMU samples)", worst <= 5.0))

    # ---------------------------------------------------------- arousal/loop
    ev_t = np.array([lab(e.window_end_us / 1e6) for e in run.evaluations if "arousal_index" in e.features])
    ev_i = np.array([e.features["arousal_index"] for e in run.evaluations if "arousal_index" in e.features])
    truth_a = np.interp(ev_t, tt, np.array(truth["arousal"]))
    r = float(np.corrcoef(ev_i, truth_a)[0, 1]) if len(ev_i) > 3 else float("nan")
    sections["closed_loop"] = {"evaluations": len(run.evaluations), "arousal_index_vs_truth_r": r,
                               "decisions": [{"t_lab_s": float(lab(e.device_time_us / 1e6)), "action": e.action, "decision_id": e.decision_id}
                                             for e in run.evaluations if e.action and e.action != "HOLD_QUALITY"],
                               "quality_holds": sum(1 for e in run.evaluations if e.action == "HOLD_QUALITY")}
    checks.append(Check("arousal_tracking", "Controller arousal index vs latent truth (Pearson r)", r, ">= 0.85", "", "TWIN", r >= 0.85))
    return {"sections": sections, "checks": [c.to_dict() for c in checks],
            "passed": all(c.passed for c in checks), "check_count": len(checks)}
