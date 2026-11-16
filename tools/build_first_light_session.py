"""Select and package First Light's recorded session from the public BUT PPG dataset.

The recorded session is one unedited stretch of a real smartphone-camera
fingertip recording from a held-out person, during which the person was asked
to disturb the measurement on purpose (press harder, move the finger on the
lens, walk, cough, laugh, change the light, talk), with rest in between. Every
10-second segment carries the dataset experts' quality label and a chest-ECG
reference recorded at the same time.

The session is chosen by a mechanical rule, from labels and continuity only,
never from First Light's own results:

  1. Held-out people (odd subject ids), fingertip, three-channel records.
  2. Join consecutive record numbers into runs while each seam is continuous:
     |first green sample of the next record - last green sample of this one|
     <= 6 x the median absolute sample-to-sample green change of this record.
     (The dataset cut longer recordings into 10-second segments.)
  3. Trim each run to start and end on an expert-good rest segment.
  4. Keep runs that contain at least one expert-poor deliberate perturbation.
  5. Take the longest; ties go to the lowest subject id, then the earliest record.

Writes ``site/first-light-recording.js`` (frames, reference, and this
provenance) for the browser, which replays it through exactly the code a live
camera session uses.

Usage: python tools/build_first_light_session.py --source butppg-2.0.0.zip
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

OUTPUT = ROOT / "site" / "first-light-recording.js"
SEAM_FACTOR = 6


def continuous(previous: list[tuple[int, int, int]], following: list[tuple[int, int, int]]) -> bool:
    steps = [abs(previous[i + 1][1] - previous[i][1]) for i in range(len(previous) - 1)]
    typical = statistics.median(steps)
    return abs(following[0][1] - previous[-1][1]) <= SEAM_FACTOR * max(typical, 1)


def candidate_runs(source: v.ButPpg):
    annotations = source.table("quality-hr-ann.csv")
    info = source.table("subject-info.csv")
    by_subject: dict[int, list[str]] = {}
    for record in sorted(annotations):
        subject = int(record[:3])
        if subject % 2 == 1 and info[record]["Ear/finger"] == "1":
            by_subject.setdefault(subject, []).append(record)
    for subject, ids in sorted(by_subject.items()):
        cache = {}
        for record in ids:
            try:
                cache[record] = source.ppg(record)
            except ValueError:
                pass
        run: list[str] = []
        for record in ids + [None]:
            joins = (record is not None and run and record in cache and int(record[3:]) == int(run[-1][3:]) + 1
                     and continuous(cache[run[-1]], cache[record]))
            if joins:
                run.append(record)
                continue
            if run:
                yield subject, run, annotations, info
            run = [record] if record in cache else []


def select(source: v.ButPpg) -> tuple[list[str], dict]:
    rest_good = lambda r, a, i: a[r]["Quality"] == "1" and i[r]["Motion"] == "0"
    best, considered = None, 0
    for subject, run, annotations, info in candidate_runs(source):
        while run and not rest_good(run[0], annotations, info):
            run = run[1:]
        while run and not rest_good(run[-1], annotations, info):
            run = run[:-1]
        if not any(annotations[r]["Quality"] == "0" and info[r]["Motion"] != "0" for r in run):
            continue
        considered += 1
        key = (len(run), -subject, -int(run[0][3:]))
        if best is None or key > best[0]:
            best = (key, run)
    records = best[1]
    return records, {"rule": __doc__.split("never from First Light's own results:")[1].split("Writes")[0].strip(),
                     "runs_meeting_rule": considered, "chosen": f"{records[0]}-{records[-1][3:]}",
                     "records": len(records), "seam_factor": SEAM_FACTOR}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    digest = hashlib.sha256(args.source.read_bytes()).hexdigest()
    if digest != v.BUT_PPG_SHA256:
        raise SystemExit(f"{args.source} is not BUT PPG 2.0.0 (SHA-256 {digest})")
    source = v.ButPpg(args.source)
    records, selection = select(source)
    frames_csv, reference = v.build_recorded_session(source, records)
    recording = {"schema": "circle-first-light-recording/1", "selection": selection,
                 "frames_csv": frames_csv.decode("utf-8"), "reference": reference}
    args.output.write_text(
        "/* CIRCLE First Light: a real smartphone-camera fingertip recording (BUT PPG 2.0.0, CC BY 4.0,\n"
        " * doi:10.13026/bvsb-mz80), selected by tools/build_first_light_session.py. Generated; do not edit. */\n"
        "window.FIRST_LIGHT_RECORDING = " + json.dumps(recording, separators=(",", ":")) + ";\n", encoding="utf-8")
    lines = frames_csv.count(b"\n") - 1
    print(f"selected {selection['chosen']} ({len(records)} segments, {lines} frames) of "
          f"{selection['runs_meeting_rule']} runs meeting the rule")
    for s in reference["segments"]:
        print(f"  {s['record']}  quality {s['quality']}  motion {s['motion']}  ECG-annotated {s['reference_hr_bpm']:g} bpm")
    print(f"wrote {args.output} ({args.output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
