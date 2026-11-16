"""Calibrate and test First Light's quality gates on real smartphone-camera recordings.

Source: the Brno University of Technology Smartphone PPG Database (BUT PPG) 2.0.0,
PhysioNet, CC BY 4.0, doi:10.13026/bvsb-mz80. 50 people; 3,888 ten-second
recordings from Xiaomi Mi9 and Huawei P20 Pro cameras at 30 frames per second,
each with a chest-ECG reference and an expert quality label (good = heart rate
can be read reliably from the PPG; poor = it cannot).

The split is by person and was fixed before any analysis:

  calibration  even subject ids (100, 102, ... 148)   thresholds may be tuned here
  held-out     odd subject ids  (101, 103, ... 149)   analysed once, with locked thresholds

Only fingertip recordings in the three-channel layout are in scope (First Light
is a fingertip-on-lens protocol). Single-channel version-1 records cannot carry
the red/green contact test and are excluded; ear recordings are reported
separately as out-of-protocol use that the system should refuse.

Each record is evaluated once, by the published algorithm in
``tools/verify_first_light.py``, on the window from 1 s to 9 s. The reference
heart rate for that window comes from the ECG beat times (median RR, at least
five beats); the dataset's whole-record HR annotation is reported alongside.

Usage:
  python tools/run_first_light_benchmark.py --source butppg-2.0.0.zip [--output docs/first-light-benchmark.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_first_light as v  # noqa: E402

TOLERANCE_BPM = 5.0
MIN_BEATS = 5
WINDOW = (1_000_000, 9_000_000)

# The grid searched on calibration subjects. Contact and exposure thresholds were fixed a priori
# from the physics of a torch-lit fingertip and are not tuned.
GRID = {
    "harmonic_ratio": [0.9, 0.7],
    "lowpass_len": [7, 11, 15],
    "periodicity_min": [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85],
    "step_max": [0.02, 0.03, 0.05, 0.08],
    "rate_min_bpm": [40.0, 45.0, 50.0],
}

RULES = [
    {"id": "selection-rule/1", "status": "INFEASIBLE_ON_CALIBRATION",
     "rule": "Admitted-record precision >= 0.95 within ±5 bpm of the dataset's HR annotation, at least 30 admitted; "
             "then the most expert-good records admitted.",
     "note": "No grid point reached 0.95 on calibration (the best was 0.89). The dominant residual errors are "
             "half-rate readings where a motion or respiratory oscillation near 40-50 bpm outweighs a weak pulse. "
             "Revised once, before any held-out analysis."},
    {"id": "selection-rule/2", "status": "APPLIED",
     "rule": "Admitted-record precision >= 0.90 within ±5 bpm of the ECG beat rate over the same window "
             "(records with >= 5 reference beats), at least 30 admitted; then the most expert-good records "
             "admitted; ties to the higher periodicity threshold, lower step threshold, higher rate floor, higher "
             "harmonic ratio.",
     "note": "The window-matched ECG reference replaces the whole-record annotation because it measures the same "
             "8 seconds the algorithm sees."},
]


def records(source: v.ButPpg):
    annotations = source.table("quality-hr-ann.csv")
    info = source.table("subject-info.csv")
    for record in sorted(annotations):
        subject = int(record[:3])
        row = {"record": record, "subject": subject, "split": "calibration" if subject % 2 == 0 else "held-out",
               "quality": int(annotations[record]["Quality"]), "annotation_hr": float(annotations[record]["HR"]),
               "spot": "finger" if info[record]["Ear/finger"] == "1" else "ear", "motion": info[record]["Motion"]}
        try:
            ppg = source.ppg(record)
        except ValueError:
            row["excluded"] = "single-channel layout"
            yield row, None
            continue
        frames = [(i * 1_000_000 // 30, *ppg[i]) for i in range(len(ppg))]
        beats = [b * 1000 for b in v.read_qrs(source.read(f"{record}/{record}.qrs"))]
        row["ecg_hr"], row["ecg_beats"] = v.reference_rate(beats, *WINDOW)
        yield row, frames


def features(frames) -> dict:
    """Threshold-independent features, plus the rate under each harmonic ratio in the grid."""
    (_, _, cutoff, end), = list(v.schedule(frames))
    if cutoff != WINDOW[1]:
        raise AssertionError("BUT PPG frames are expected to put the first evaluation at 9 s")
    result = v.evaluate(frames, end, cutoff)
    out = {"gates": result["gates"], **{k: result["features"][k] for k in ("step", "out_of_contact")}}
    saved = dict(v.ALGORITHM)
    try:
        for ratio in GRID["harmonic_ratio"]:
            for lowpass in GRID["lowpass_len"]:
                v.ALGORITHM.update(harmonic_ratio=ratio, lowpass_len=lowpass)
                out[f"rate@{ratio}|{lowpass}"], out[f"periodicity@{ratio}|{lowpass}"] = (
                    v.evaluate(frames, end, cutoff)["features"][k] for k in ("rate_bpm", "periodicity"))
    finally:
        v.ALGORITHM.clear()
        v.ALGORITHM.update(saved)
    return out


def variant(params: dict) -> str:
    return f"{params['harmonic_ratio']}|{params['lowpass_len']}"


def admitted(row: dict, params: dict) -> bool:
    f = row["features"]
    rate, periodicity = f[f"rate@{variant(params)}"], f[f"periodicity@{variant(params)}"]
    return (f["gates"]["FRAMES"] == f["gates"]["CONTACT"] == f["gates"]["EXPOSURE"] == "pass"
            and f["step"] is not None and f["step"] <= params["step_max"]
            and periodicity is not None and periodicity >= params["periodicity_min"]
            and rate is not None and params["rate_min_bpm"] <= rate <= v.ALGORITHM["rate_max_bpm"])


def score(rows: list[dict], params: dict, reference: str = "ecg") -> dict:
    good = [r for r in rows if r["quality"] == 1]
    poor = [r for r in rows if r["quality"] == 0]
    chosen = [r for r in rows if admitted(r, params)]
    rate = lambda r: r["features"][f"rate@{variant(params)}"]
    if reference == "ecg":
        judged = [r for r in chosen if r["ecg_hr"] is not None and r["ecg_beats"] >= MIN_BEATS]
        errors = [rate(r) - r["ecg_hr"] for r in judged]
    else:
        judged = chosen
        errors = [rate(r) - r["annotation_hr"] for r in judged]
    within = sum(1 for e in errors if abs(e) <= TOLERANCE_BPM)
    return {"records": len(rows), "admitted": len(chosen), "judged": len(judged),
            "precision": round(within / len(judged), 4) if judged else None,
            "median_abs_error_bpm": round(statistics.median(abs(e) for e in errors), 2) if errors else None,
            "good_admitted": f"{sum(1 for r in chosen if r['quality'] == 1)}/{len(good)}",
            "good_coverage": round(sum(1 for r in chosen if r["quality"] == 1) / len(good), 4) if good else None,
            "poor_admitted": f"{sum(1 for r in chosen if r['quality'] == 0)}/{len(poor)}",
            "poor_refusal": round(1 - sum(1 for r in chosen if r["quality"] == 0) / len(poor), 4) if poor else None}


def grid_points():
    for ratio in GRID["harmonic_ratio"]:
        for lowpass in GRID["lowpass_len"]:
            for q in GRID["periodicity_min"]:
                for step in GRID["step_max"]:
                    for floor in GRID["rate_min_bpm"]:
                        yield {"harmonic_ratio": ratio, "lowpass_len": lowpass, "periodicity_min": q,
                               "step_max": step, "rate_min_bpm": floor}


def select(calibration: list[dict]) -> tuple[dict, list[dict]]:
    table = []
    for params in grid_points():
        s = score(calibration, params)
        table.append({**params, "admitted": s["admitted"], "precision": s["precision"],
                      "good_coverage": s["good_coverage"], "poor_refusal": s["poor_refusal"],
                      "annotation_precision": score(calibration, params, "annotation")["precision"]})
    feasible = [t for t in table if t["admitted"] >= 30 and t["precision"] is not None and t["precision"] >= 0.90]
    if not feasible:
        raise SystemExit("selection-rule/2 is infeasible on calibration")
    best = max(feasible, key=lambda t: (t["good_coverage"], t["periodicity_min"], -t["step_max"],
                                        t["rate_min_bpm"], t["harmonic_ratio"], -t["lowpass_len"]))
    return {k: best[k] for k in GRID}, table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help="butppg-2.0.0.zip from PhysioNet")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "first-light-benchmark.json")
    parser.add_argument("--calibrate-only", action="store_true", help="select thresholds; do not touch held-out")
    args = parser.parse_args(argv)
    digest = hashlib.sha256(args.source.read_bytes()).hexdigest()
    if digest != v.BUT_PPG_SHA256:
        raise SystemExit(f"{args.source} is not BUT PPG 2.0.0 (SHA-256 {digest})")
    source = v.ButPpg(args.source)

    rows, excluded, ear = {"calibration": [], "held-out": []}, [], {"calibration": [], "held-out": []}
    for row, frames in records(source):
        if frames is None:
            excluded.append(row["record"])
            continue
        if row["spot"] == "ear":
            if row["split"] == "held-out" and args.calibrate_only:
                continue
            row["features"] = features(frames)
            ear[row["split"]].append(row)
            continue
        if row["split"] == "held-out" and args.calibrate_only:
            continue
        row["features"] = features(frames)
        rows[row["split"]].append(row)

    selected, table = select(rows["calibration"])
    published = {k: v.ALGORITHM[k] for k in GRID}
    print("selected on calibration:", selected)
    if args.calibrate_only:
        print("published in verify_first_light.ALGORITHM:", published)
        return 0
    if selected != published:
        raise SystemExit(f"the published algorithm {published} is not the calibration selection {selected}; "
                         "update ALGORITHM in tools/verify_first_light.py and site/first-light-core.js together")

    held = rows["held-out"]
    by_condition = {}
    for motion in sorted({r["motion"] for r in held}):
        subset = [r for r in held if r["motion"] == motion]
        by_condition[motion] = score(subset, selected)
    wrong = []
    for r in held:
        if admitted(r, selected) and r["ecg_hr"] is not None and r["ecg_beats"] >= MIN_BEATS:
            rate = r["features"][f"rate@{variant(selected)}"]
            if abs(rate - r["ecg_hr"]) > TOLERANCE_BPM:
                wrong.append({"record": r["record"], "expert_quality": r["quality"], "motion": r["motion"],
                              "estimate_bpm": round(rate, 1), "ecg_bpm": round(r["ecg_hr"], 1),
                              "annotation_bpm": r["annotation_hr"]})
    doc = {
        "schema": "circle-first-light-benchmark/1",
        "algorithm": v.ALGORITHM["id"],
        "dataset": {"name": "BUT PPG", "version": "2.0.0", "doi": "10.13026/bvsb-mz80",
                    "url": "https://physionet.org/content/butppg/2.0.0/", "license": "CC BY 4.0",
                    "archive_sha256": digest},
        "split": "by person: even subject ids calibrate, odd subject ids are held out",
        "scope": "fingertip recordings, three-channel layout; one evaluation per record on the 1-9 s window",
        "excluded_single_channel_records": len(excluded),
        "reference": f"ECG median-RR rate over the same window (>= {MIN_BEATS} beats); ±{TOLERANCE_BPM:g} bpm counts as correct",
        "motion_codes": {"0": "rest", "1": "more pressure on the lens", "2": "finger moving on the lens",
                         "3": "walking", "4": "coughing", "5": "laughing", "6": "changing light", "7": "talking"},
        "selection_rules": RULES,
        "grid": GRID,
        "selected": selected,
        "calibration": score(rows["calibration"], selected),
        "calibration_vs_annotation": score(rows["calibration"], selected, "annotation"),
        "held_out": score(held, selected),
        "held_out_vs_annotation": score(held, selected, "annotation"),
        "held_out_by_condition": by_condition,
        "held_out_admitted_but_wrong": wrong,
        "ear_out_of_protocol": {split: f"{sum(1 for r in ear[split] if admitted(r, selected))}/{len(ear[split])} admitted"
                                for split in ear},
        "calibration_grid": table,
        "interpretation": ("Precision is the share of admitted records whose rate is within ±5 bpm of the ECG; "
                           "coverage is the share of expert-good records admitted; poor refusal is the share of "
                           "expert-poor records refused. A camera pulse rate is not a medical measurement."),
    }
    args.output.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("selected", "calibration", "held_out", "held_out_vs_annotation",
                                          "ear_out_of_protocol")}, indent=1))
    print(f"{len(wrong)} held-out records admitted but wrong; written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
