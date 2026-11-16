"""Enumerate First Light's recorded sessions from the public BUT PPG dataset.

A session is one unedited stretch of a real smartphone-camera fingertip
recording. The dataset cut longer recordings into 10-second records; a session
joins consecutive records back together wherever the seam is continuous. During
many sessions the person was asked to disturb the measurement on purpose (press
harder, move the finger on the lens, walk, cough, laugh, change the light,
talk), with rest in between. Every record carries the dataset experts' quality
label and a chest-ECG reference recorded at the same time.

Sessions are defined from record numbers and signal continuity only. Neither
the experts' labels nor First Light's own results take part:

  1. One person, fingertip, three-channel records.
  2. Join consecutive record numbers while each seam is continuous:
     |first green sample of the next record - last green sample of this one|
     <= 6 x the median absolute sample-to-sample green change of this record.
  3. Keep runs of at least 6 records (60 seconds).

Round 2's test set is every such session from held-out people (odd subject
ids), except person 135, whose recording was used in round 1.

The web page replays two of them, and says which is which:

  preregistered  the longest test session (ties: lowest subject id, then the
                 earliest record), fixed before the test ran
  illustration   chosen AFTER the test, by outcome, because it shows every
                 step: the shortest session whose own verdict is VERIFIED and
                 that contains a deliberate disturbance the experts rejected,
                 with at least five actions before it, none inside it, and at
                 least one after it. It is an example, not evidence of typical
                 performance; the evidence is the pooled test.

Usage:
  python tools/build_first_light_session.py --source butppg-2.0.0.zip --list
  python tools/build_first_light_session.py --source butppg-2.0.0.zip --page
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

SITE = ROOT / "site"
RESULT = ROOT / "evidence" / "first-light" / "round-2" / "result.json"
SEAM_FACTOR = 6
MIN_RECORDS = 6
ROUND_1_SUBJECTS = (135,)
RULE = "session-rule/2"


def continuous(previous: list[tuple[int, int, int]], following: list[tuple[int, int, int]]) -> bool:
    steps = [abs(previous[i + 1][1] - previous[i][1]) for i in range(len(previous) - 1)]
    typical = statistics.median(steps)
    return abs(following[0][1] - previous[-1][1]) <= SEAM_FACTOR * max(typical, 1)


def sessions(source: v.ButPpg, split: str) -> list[list[str]]:
    """Every session of the split ("held-out": odd subject ids except round 1's; "calibration": even)."""
    annotations = source.table("quality-hr-ann.csv")
    info = source.table("subject-info.csv")
    by_subject: dict[int, list[str]] = {}
    for record in sorted(annotations):
        subject = int(record[:3])
        wanted = subject % 2 == 1 and subject not in ROUND_1_SUBJECTS if split == "held-out" else subject % 2 == 0
        if wanted and info[record]["Ear/finger"] == "1":
            by_subject.setdefault(subject, []).append(record)
    found = []
    for _, ids in sorted(by_subject.items()):
        cache = {}
        for record in ids:
            try:
                cache[record] = source.ppg(record)
            except ValueError:
                pass                                  # single-channel layout: no contact test possible
        run: list[str] = []
        for record in ids + [None]:
            joins = (record is not None and run and record in cache and int(record[3:]) == int(run[-1][3:]) + 1
                     and continuous(cache[run[-1]], cache[record]))
            if joins:
                run.append(record)
                continue
            if len(run) >= MIN_RECORDS:
                found.append(run)
            run = [record] if record in cache else []
    return found


def showcase(found: list[list[str]]) -> list[str]:
    return max(found, key=lambda run: (len(run), -int(run[0][:3]), -int(run[0][3:])))


def name(run: list[str]) -> str:
    return f"{run[0]}-{run[-1][3:]}"


def recording(source: v.ButPpg, run: list[str], selection: dict) -> dict:
    frames_csv, reference = v.build_recorded_session(source, run)
    return {"schema": "circle-first-light-recording/1", "selection": selection,
            "frames_csv": frames_csv.decode("utf-8"), "reference": reference}


def open_source(path: Path) -> v.ButPpg:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != v.BUT_PPG_SHA256:
        raise SystemExit(f"{path} is not BUT PPG 2.0.0 (SHA-256 {digest})")
    return v.ButPpg(path)


def illustration(source: v.ButPpg, found: list[list[str]], verified: set[str]) -> list[str]:
    """The post-hoc example session (see the module docstring). Uses outcomes, and says so."""
    eligible = []
    for run in found:
        if name(run) not in verified:
            continue
        frames_csv, reference = v.build_recorded_session(source, run)
        decisions, _ = v.run_controller(v.read_frames(frames_csv))
        acts = [d["cutoff_us"] for d in decisions if d["decision"] == "ACT"]
        for segment in reference["segments"]:
            if segment["motion"] == "0" or segment["quality"] != 0:
                continue
            before = sum(1 for t in acts if t < segment["start_us"])
            inside = sum(1 for t in acts if segment["start_us"] <= t <= segment["end_us"])
            after = sum(1 for t in acts if t > segment["end_us"])
            if before >= 5 and inside == 0 and after >= 1:
                eligible.append(run)
                break
    return min(eligible, key=lambda run: (len(run), int(run[0][:3]), int(run[0][3:])))


def page_file(run_name: str) -> Path:
    return SITE / f"first-light-recording-{run_name}.js"


def write_page_recording(doc: dict) -> Path:
    output = page_file(doc["selection"]["chosen"])
    output.write_text(
        "/* CIRCLE First Light: a real smartphone-camera fingertip recording (BUT PPG 2.0.0, CC BY 4.0,\n"
        " * doi:10.13026/bvsb-mz80), built by tools/build_first_light_session.py. Generated; do not edit. */\n"
        "window.FIRST_LIGHT_RECORDINGS = window.FIRST_LIGHT_RECORDINGS || {};\n"
        f"window.FIRST_LIGHT_RECORDINGS[{json.dumps(doc['selection']['chosen'])}] = "
        + json.dumps(doc, separators=(",", ":")) + ";\n", encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--list", action="store_true", help="list the held-out test sessions and stop")
    parser.add_argument("--page", action="store_true", help="write the two recordings the web page replays")
    args = parser.parse_args(argv)
    source = open_source(args.source)
    found = sessions(source, "held-out")
    longest = showcase(found)
    print(f"{len(found)} held-out sessions under {RULE}; the longest is {name(longest)} ({len(longest)} records)")
    if args.list or not args.page:
        for run in found:
            print(f"  {name(run)}  {len(run)} records")
        return 0
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    verified = {row["session"] for row in result["sessions"] if row["session_verdict"] == "VERIFIED"}
    example = illustration(source, found, verified)
    roles = (
        (longest, "preregistered", "the longest held-out session, fixed before the test ran; "
                                   "record numbers and seam continuity only"),
        (example, "illustration", "chosen after the test, by outcome: the shortest individually VERIFIED session "
                                  "with a deliberate, expert-rejected disturbance that has at least five actions "
                                  "before it, none inside it, and at least one after it"),
    )
    for run, role, how in roles:
        selection = {"rule": RULE, "role": role, "sessions_in_test_set": len(found), "chosen": name(run),
                     "records": len(run), "how": how}
        output = write_page_recording(recording(source, run, selection))
        print(f"{role}: {name(run)} -> {output.relative_to(ROOT)} ({output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
