"""Run a closed-loop CIRCLE session against the physiological twin and export its evidence.

Writes a self-auditing run directory (see docs/physiology-pipeline.md):
session.ndjson, raw/*.csv.gz, analysis.json, truth.json, scorecard.json,
report.html, and manifest.json. Everything is SIMULATED; nothing here drives
hardware or involves a person.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from models.physiology.audit import audit_run
from models.physiology.controller import CONTROLLER_VERSION, replay
from models.physiology.evidence import (analysis_document, build_session_records, dumps, source_digest,
                                        write_raw_bundle)
from models.physiology.experiment import SessionConfig, SessionRun, run_session
from models.physiology.pipeline import PIPELINE_VERSION
from models.physiology.report import build_report
from models.physiology.twin import TwinConfig
from models.physiology.validation import score


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def export_run(run: SessionRun, output: Path, counterfactual: SessionRun | None, with_report: bool = True) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    raw_entries = write_raw_bundle(run.raw, output / "raw")
    analysis = run.analysis
    records = build_session_records(run, raw_entries, analysis)
    session_bytes = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in records).encode("utf-8")
    truth = run.truth()
    scorecard = score(run, truth)
    replayed = replay(run.raw, run.config.controller, run.evaluation_end_us)
    replay_identical = [a.comparable() for a in replayed] == [b.comparable() for b in run.evaluations]
    documents = {
        "session.ndjson": session_bytes,
        "analysis.json": dumps(analysis_document(analysis)),
        "truth.json": dumps(compact_truth(truth)),
        "scorecard.json": dumps(scorecard),
    }
    if counterfactual is not None:
        documents["counterfactual.json"] = dumps({
            "provenance": "SIMULATED", "arm": "SHAM" if run.config.actuate else "ACTIVE",
            "note": "Same seed and noise; decisions logged but cues not actuated. The difference reflects "
                    "the twin's ASSUMED response model, not evidence of efficacy.",
            "truth": {k: counterfactual.twin.truth()[k] for k in ("t_s", "arousal", "hr_bpm", "resp_rate_bpm", "entrainment")},
            "decisions": [{"device_time_us": e.device_time_us, "action": e.action, "decision_id": e.decision_id}
                          for e in counterfactual.evaluations if e.action and e.action != "HOLD_QUALITY"],
        })
    if with_report:
        documents["report.html"] = build_report(run, truth, scorecard, counterfactual, records, replay_identical).encode("utf-8")
    for name, data in documents.items():
        (output / name).write_bytes(data)
    artifacts = {path: {"sha256": entry["sha256"], "bytes": entry["bytes"], "content_sha256": entry["content_sha256"],
                        "rows": entry["rows"]} for path, entry in raw_entries.items()}
    artifacts.update({name: {"sha256": _sha(data), "bytes": len(data)} for name, data in documents.items()})
    config = run.config
    manifest = {
        "schema": "circle-physiology-run/1",
        "release_class": "ENGINEERING_REVIEW_ONLY",
        "provenance": "SIMULATED",
        "generated_by": "tools/run_physiology_twin.py",
        "pipeline_version": PIPELINE_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "pipeline_source": source_digest(),
        "environment": {"python": platform.python_version(), "numpy": np.__version__},
        "config": {"arm": "ACTIVE" if config.actuate else "SHAM", "twin": asdict(config.twin),
                   "rig": asdict(config.rig), "controller": asdict(config.controller)},
        "decision_replay": {"evaluations": len(run.evaluations), "identical": replay_identical},
        "scorecard": {"passed": sum(c["passed"] for c in scorecard["checks"]), "total": len(scorecard["checks"])},
        "artifacts": dict(sorted(artifacts.items())),
    }
    (output / "manifest.json").write_bytes(dumps(manifest))
    return {"manifest": manifest, "scorecard": scorecard, "records": len(records)}


def compact_truth(truth: dict) -> dict:
    """truth.json without per-sample timing arrays (summarized as percentiles)."""
    timing = dict(truth["timing"])
    for key in ("eda_edge_error_us", "imu_edge_error_us", "ppg_sample_error_us"):
        errors = np.abs(np.asarray(timing.pop(key), dtype=float))
        timing[key.replace("_us", "_abs_us")] = {q: float(np.percentile(errors, p)) for q, p in
                                                 (("p50", 50), ("p99", 99), ("p99_9", 99.9), ("max", 100))}
    return {"provenance": "SIMULATED", "warning": "Ground truth for scoring only; never pipeline input.",
            **{k: v for k, v in truth.items() if k != "timing"}, "timing": timing}


def benchmark(seeds: list[int], duration: float | None) -> dict:
    """Score many seeds without exporting; reports mean, worst, and pass rate per check."""
    values: dict[str, list] = {}
    meta: dict[str, dict] = {}
    passes: dict[str, int] = {}
    for seed in seeds:
        twin = TwinConfig(seed=seed) if duration is None else TwinConfig(seed=seed, duration_s=duration)
        run = run_session(SessionConfig(twin=twin))
        card = score(run, run.truth())
        for check in card["checks"]:
            values.setdefault(check["id"], []).append(check["value"])
            passes[check["id"]] = passes.get(check["id"], 0) + int(check["passed"])
            meta[check["id"]] = {k: check[k] for k in ("label", "target", "unit", "source")}
        print(f"seed {seed}: {sum(c['passed'] for c in card['checks'])}/{len(card['checks'])} checks passed", flush=True)
    summary = {}
    for key, vals in values.items():
        arr = np.array([np.nan if v is None else v for v in vals], dtype=float)
        target = meta[key]["target"].strip()
        lower_is_better = target.startswith("<=") or target == "== 0"
        summary[key] = {**meta[key], "mean": float(np.nanmean(arr)),
                        "worst": float(np.nanmax(arr) if lower_is_better else np.nanmin(arr)),
                        "pass_rate": passes[key] / len(seeds)}
    return {"provenance": "SIMULATED", "seeds": seeds, "checks": summary,
            "all_passed": all(v["pass_rate"] == 1.0 for v in summary.values())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=7, help="Twin seed (default 7)")
    parser.add_argument("--duration", type=float, help="Session length in seconds (default: full 360 s protocol)")
    parser.add_argument("--output", type=Path, default=Path("outputs/physiology"), help="Run directory")
    parser.add_argument("--sham", action="store_true", help="Log decisions but do not actuate cues")
    parser.add_argument("--no-counterfactual", action="store_true", help="Skip the matched opposite-arm run")
    parser.add_argument("--no-report", action="store_true", help="Skip report.html")
    parser.add_argument("--audit", action="store_true", help="Independently audit the exported directory")
    parser.add_argument("--benchmark", type=int, metavar="N", help="Score N seeds instead of exporting one run")
    parser.add_argument("--benchmark-start", type=int, default=100, help="First benchmark seed (held out from development)")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    try:
        if args.benchmark:
            seeds = list(range(args.benchmark_start, args.benchmark_start + args.benchmark))
            result = benchmark(seeds, args.duration)
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "benchmark.json").write_bytes(dumps(result))
            for key, entry in result["checks"].items():
                print(f"  {entry['label']:<52} mean {entry['mean']:>10.4f}  worst {entry['worst']:>10.4f}  "
                      f"target {entry['target']:<8} pass {entry['pass_rate']:.0%}")
            print(f"Benchmark over {len(seeds)} held-out seeds: {'ALL CHECKS PASSED' if result['all_passed'] else 'FAILURES'}")
            return 0 if result["all_passed"] else 1
        twin = TwinConfig(seed=args.seed) if args.duration is None else TwinConfig(seed=args.seed, duration_s=args.duration)
        config = SessionConfig(twin=twin, actuate=not args.sham)
        run = run_session(config)
        counterfactual = None if args.no_counterfactual else run_session(replace(config, actuate=not config.actuate))
        exported = export_run(run, args.output, counterfactual, with_report=not args.no_report)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Physiology twin run failed: {exc}", file=sys.stderr)
        return 1
    manifest, card = exported["manifest"], exported["scorecard"]
    decisions = [(e.decision_id, e.action) for e in run.evaluations if e.decision_id]
    print(f"CIRCLE physiology twin: seed {args.seed}, {'ACTIVE' if config.actuate else 'SHAM'} arm, "
          f"{exported['records']} session records -> {args.output}")
    print(f"  decisions: {decisions or 'none'}; replay identical: {manifest['decision_replay']['identical']}")
    print(f"  scorecard: {manifest['scorecard']['passed']}/{manifest['scorecard']['total']} checks passed")
    for check in card["checks"]:
        if not check["passed"]:
            print(f"    FAILED {check['label']}: {check['value']} (target {check['target']} {check['unit']})")
    ok = card["passed"] and manifest["decision_replay"]["identical"]
    if args.audit:
        result = audit_run(args.output)
        for name, entry in result["checks"].items():
            print(f"  audit {name}: {'OK' if entry['passed'] else 'FAILED'}")
        ok = ok and result["valid"]
    print(f"  elapsed {time.perf_counter() - started:.1f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
