"""Run First Light's pooled recorded-session test on the public BUT PPG dataset.

For every session of the chosen split (see ``tools/build_first_light_session.py``):

  1. rebuild its frames and ECG reference from the dataset archive;
  2. run the browser implementation (``site/first-light-core.js``, under Node) to
     produce the evidence bundle exactly as the page would;
  3. verify that bundle with the independent Python implementation: integrity,
     replay of every decision, and a byte-for-byte source rebuild.

The preregistered criteria (``first-light-criteria/2``) are then judged over
all windows of all sessions together. Coverage differs widely between people,
so a rate measured on one person says little about the system.

  --split calibration   even subject ids: where the bars were derived
  --split held-out      odd subject ids except round 1's person: the test

The held-out run writes ``evidence/first-light/round-2/result.json``. The
recordings the page replays are written by ``tools/build_first_light_session.py
--page`` and their bundles by ``tools/build_first_light_bundle.js``.

Usage: python tools/run_first_light_round.py --source butppg-2.0.0.zip --split held-out
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_first_light_session as sessions  # noqa: E402
import verify_first_light as v  # noqa: E402

ROUND = ROOT / "evidence" / "first-light" / "round-2"


def run(source_path: Path, split: str) -> dict:
    source = sessions.open_source(source_path)
    found = sessions.sessions(source, split)
    chosen = sessions.showcase(found)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for records in found:
            selection = {"rule": sessions.RULE, "sessions_in_test_set": len(found),
                         "chosen": sessions.name(records), "records": len(records),
                         "how": "record numbers and seam continuity only"}
            doc = sessions.recording(source, records, selection)
            (work / f"{sessions.name(records)}.recording.json").write_text(json.dumps(doc), encoding="utf-8")
        subprocess.run(["node", str(ROOT / "tools" / "build_first_light_bundle.js"), "--batch", str(work)], check=True)
        results = [v.verify(work / f"{sessions.name(records)}.zip", source_path) for records in found]
    pooled = v.pool(results)
    rows = []
    for records, r in zip(found, results):
        windows = r.get("windows", [])
        good = [w for w in windows if w["label"] == "good"]
        poor = [w for w in windows if w["label"] == "poor"]
        judged = [w for w in windows if w["decision"] == "ACT"
                  and w["reference_beats"] >= v.CRITERIA["recorded-reference"]["min_reference_beats"]]
        rows.append({
            "session": sessions.name(records), "subject": int(records[0][:3]), "records": len(records),
            "bundle_sha256": r.get("bundle_sha256"), "integrity": r.get("integrity"), "replay": r.get("replay"),
            "source": r.get("source"), "evaluations": r.get("evaluations"), "acts": r.get("acts"),
            "acts_within_tolerance": f"{sum(1 for w in judged if abs(w['error_bpm']) <= 5.0)}/{len(judged)}",
            "good_windows_acted": f"{sum(1 for w in good if w['decision'] == 'ACT')}/{len(good)}",
            "poor_windows_refused": f"{sum(1 for w in poor if w['decision'] == 'REFUSE')}/{len(poor)}",
            "session_verdict": r.get("verdict")})
    return {"schema": "circle-first-light-round/1", "round": 2, "split": split,
            "algorithm": v.ALGORITHM["id"], "criteria": v.CRITERIA["id"], "session_rule": sessions.RULE,
            "dataset": {"name": "BUT PPG", "version": "2.0.0", "doi": "10.13026/bvsb-mz80",
                        "archive_sha256": v.BUT_PPG_SHA256},
            "page_session": sessions.name(chosen), "pooled": pooled, "sessions": rows}


def report(doc: dict) -> None:
    pooled = doc["pooled"]
    print(f"{doc['split']}: {pooled['sessions']} sessions · {pooled['windows']} windows · {pooled['acts']} ACT")
    for c in pooled["criteria"]:
        print(f"  {c['result']}  {c['id']:<34} measured {c['measured']}  (required {c['required']})  {c['detail']}")
    for problem in pooled["problems"]:
        print(f"  problem: {problem}")
    replays = sum(1 for s in doc["sessions"] if s["replay"] == "REPLAY_MATCH")
    sources = sum(1 for s in doc["sessions"] if s["source"] == "SOURCE_MATCH")
    print(f"  replay match {replays}/{len(doc['sessions'])} · source match {sources}/{len(doc['sessions'])}")
    print(f"POOLED VERDICT: {pooled['verdict']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help="butppg-2.0.0.zip from PhysioNet")
    parser.add_argument("--split", choices=("calibration", "held-out"), required=True)
    parser.add_argument("--output", type=Path, default=None, help="where to write the result JSON")
    args = parser.parse_args(argv)
    held = args.split == "held-out"
    doc = run(args.source, args.split)
    output = args.output or (ROUND / ("result.json" if held else "calibration.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    report(doc)
    print(f"written to {output}")
    return 0 if doc["pooled"]["verdict"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
