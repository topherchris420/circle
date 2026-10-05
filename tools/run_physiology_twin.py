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
from models.physiology.evidence import (analysis_document, build_session_records, dumps, software_revision,
                                        source_digest, write_raw_bundle)
from models.physiology.experiment import SessionConfig, SessionRun, run_session
from models.physiology.ledger import build_ledger, passport, passport_text
from models.physiology.pipeline import PIPELINE_VERSION
from models.physiology.scenarios import SCENARIOS, system_checks
from models.physiology.report import build_report
from models.physiology.twin import TwinConfig
from models.physiology.validation import score


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def export_run(run: SessionRun, output: Path, counterfactual: SessionRun | None, with_report: bool = True,
               extra_documents: dict[str, bytes] | None = None) -> dict:
    """Write the self-auditing run directory; extra_documents join it and its manifest (hashed like the rest)."""
    output.mkdir(parents=True, exist_ok=True)
    raw_entries = write_raw_bundle(run.raw, output / "raw")
    analysis = run.analysis
    records = build_session_records(run, raw_entries, analysis)
    session_bytes = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in records).encode("utf-8")
    truth = run.truth()
    scorecard = score(run, truth)
    replayed = replay(run.raw, run.config.controller, run.evaluation_end_us)
    replay_identical = [a.comparable() for a in replayed] == [b.comparable() for b in run.evaluations]
    ledger = build_ledger(records)
    session_passport = passport(records, {"REPLAY AT EXPORT": "REPLAY_MATCH" if replay_identical else "REPLAY_DIVERGENCE",
                                          "SCORECARD": f"{sum(c['passed'] for c in scorecard['checks'])}/{len(scorecard['checks'])} "
                                                       "twin checks passed (simulation only)",
                                          "AUDIT": "not part of export; run tools/audit_physiology_run.py"})
    documents = {
        "session.ndjson": session_bytes,
        "closed_loop_ledger.json": dumps(ledger),
        "passport.txt": passport_text(session_passport).encode("utf-8"),
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
                          for e in counterfactual.evaluations if e.action and not e.action.startswith("HOLD_")],
        })
    if with_report:
        documents["report.html"] = build_report(run, truth, scorecard, counterfactual, records, replay_identical).encode("utf-8")
    documents.update(extra_documents or {})
    for name, data in documents.items():
        (output / name).write_bytes(data)
    artifacts = {path: {"sha256": entry["sha256"], "bytes": entry["bytes"], "content_sha256": entry["content_sha256"],
                        "rows": entry["rows"]} for path, entry in raw_entries.items()}
    artifacts.update({name: {"sha256": _sha(data), "bytes": len(data)} for name, data in documents.items()})
    config = run.config
    run_config = {"arm": "ACTIVE" if config.actuate else "SHAM", "twin": asdict(config.twin),
                  "rig": asdict(config.rig), "controller": asdict(config.controller),
                  **({"acquisition": list(config.acquisition)} if config.acquisition else {})}
    manifest = {
        "schema": "circle-physiology-run/1",
        "release_class": "ENGINEERING_REVIEW_ONLY",
        "provenance": "SIMULATED",
        "generated_by": "tools/run_physiology_twin.py",
        "pipeline_version": PIPELINE_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "pipeline_source": source_digest(),
        "software_revision": software_revision(),
        "config_sha256": _sha(json.dumps(run_config, sort_keys=True, separators=(",", ":")).encode("utf-8")),
        "environment": {"python": platform.python_version(), "numpy": np.__version__},
        "config": run_config,
        "session_id": config.session_id,
        "scenario": config.scenario,
        "passport": session_passport,
        "decision_replay": {"evaluations": len(run.evaluations), "identical": replay_identical,
                            "status": "REPLAY_MATCH" if replay_identical else "REPLAY_DIVERGENCE"},
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
    failures: list[dict] = []
    for seed in seeds:
        twin = TwinConfig(seed=seed) if duration is None else TwinConfig(seed=seed, duration_s=duration)
        run = run_session(SessionConfig(twin=twin))
        card = score(run, run.truth())
        for check in card["checks"]:
            values.setdefault(check["id"], []).append(check["value"])
            passes[check["id"]] = passes.get(check["id"], 0) + int(check["passed"])
            meta[check["id"]] = {k: check[k] for k in ("label", "target", "unit", "source")}
            if not check["passed"]:
                failures.append({"seed": seed, "check": check["id"], "label": check["label"],
                                 "value": check["value"], "target": check["target"], "unit": check["unit"]})
        print(f"seed {seed}: {sum(c['passed'] for c in card['checks'])}/{len(card['checks'])} checks passed", flush=True)
    summary = {}
    for key, vals in values.items():
        arr = np.array([np.nan if v is None else v for v in vals], dtype=float)
        target = meta[key]["target"].strip()
        lower_is_better = target.startswith("<=") or target == "== 0"
        summary[key] = {**meta[key], "mean": float(np.nanmean(arr)),
                        "worst": float(np.nanmax(arr) if lower_is_better else np.nanmin(arr)),
                        "pass_rate": passes[key] / len(seeds)}
    total = sum(len(values[k]) for k in values)
    return {"provenance": "SIMULATED", "seeds": seeds, "checks": summary,
            "checks_run": total, "checks_passed": total - len(failures),
            "failures": failures,
            "all_passed": not failures}


def scenario_suite(names: list[str], seeds: list[int]) -> dict:
    """Run adversarial scenarios and judge the closed loop against hidden truth."""
    results = []
    for name in names:
        scenario = SCENARIOS[name]
        for seed in seeds:
            run = run_session(scenario.configure(seed))
            result = system_checks(run, scenario)
            results.append(result)
            failed = [c["id"] for c in result["checks"] if not c["passed"]]
            print(f"{name:<18} seed {seed:<4} {'PASS' if result['passed'] else 'FAIL ' + ','.join(failed):<40} "
                  f"decisions {result['decisions'] or 'none'}  holds {result['holds_by_reason'] or 'none'}", flush=True)
    return {"provenance": "SIMULATED", "note": "System-level checks judged against twin truth; not evidence of hardware "
            "or human behavior.", "scenarios": {n: SCENARIOS[n].tests for n in names}, "seeds": seeds,
            "controller_version": CONTROLLER_VERSION, "pipeline_source": source_digest(),
            "runs": len(results), "runs_passed": sum(r["passed"] for r in results),
            "by_scenario": scenario_summary(results),
            "results": results, "all_passed": all(r["passed"] for r in results)}


def scenario_summary(results: list[dict]) -> dict:
    """Per-scenario pass counts with every failure retained: seed, failed checks, their details, and the decisions."""
    summary: dict[str, dict] = {}
    for r in results:
        entry = summary.setdefault(r["scenario"], {"runs": 0, "passed": 0, "failures": []})
        entry["runs"] += 1
        entry["passed"] += int(r["passed"])
        if not r["passed"]:
            entry["failures"].append({"seed": r["seed"], "failed_checks": [c["id"] for c in r["checks"] if not c["passed"]],
                                      "details": {c["id"]: c["detail"] for c in r["checks"] if not c["passed"]},
                                      "decisions": [list(d) for d in r["decisions"]]})
    return dict(sorted(summary.items()))


def corpus(result: dict) -> dict:
    """Compact, frozen expected outcomes: any behavioral change must update this file deliberately."""
    return {"provenance": "SIMULATED", "note": "Regenerate with: python tools/run_physiology_twin.py --scenarios "
            "--output outputs/scenarios --corpus tests/fixtures/scenario-outcomes.json",
            "outcomes": {f"{r['scenario']}@{r['seed']}": {
                "passed": r["passed"], "failed_checks": [c["id"] for c in r["checks"] if not c["passed"]],
                "decisions": [list(d) for d in r["decisions"]], "holds_by_reason": r["holds_by_reason"]}
                for r in result["results"]}}


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
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="clean",
                        help="Adversarial scenario for a single exported run (default clean)")
    parser.add_argument("--scenarios", nargs="*", metavar="NAME",
                        help="Run the adversarial scenario suite (all scenarios if no names) and write scenarios.json")
    parser.add_argument("--scenario-seeds", type=int, nargs="+", default=[7], help="Seeds for --scenarios")
    parser.add_argument("--corpus", type=Path, help="With --scenarios: also write the compact regression corpus here")
    parser.add_argument("--summary", type=Path,
                        help="With --scenarios: also write the per-scenario summary (failures retained) here, e.g. for docs/")
    parser.add_argument("--summary-note", default="", help="With --summary: a note recording what the seeds are and why")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    try:
        if args.scenarios is not None:
            names = args.scenarios or list(SCENARIOS)
            unknown = sorted(set(names) - set(SCENARIOS))
            if unknown:
                raise ValueError(f"Unknown scenarios {unknown}; choose from {sorted(SCENARIOS)}")
            result = scenario_suite(names, args.scenario_seeds)
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "scenarios.json").write_bytes(dumps(result))
            if args.corpus:
                args.corpus.parent.mkdir(parents=True, exist_ok=True)
                args.corpus.write_bytes(dumps(corpus(result)))
            if args.summary:
                seeds = args.scenario_seeds
                compact = (f"{seeds[0]}..{seeds[-1]}" if seeds == list(range(seeds[0], seeds[-1] + 1)) else
                           " ".join(map(str, seeds)))
                args.summary.parent.mkdir(parents=True, exist_ok=True)
                args.summary.write_bytes(dumps({
                    "provenance": "SIMULATED",
                    "generated_by": f"python tools/run_physiology_twin.py --scenarios --scenario-seeds {compact}",
                    "controller_version": result["controller_version"], "pipeline_source": result["pipeline_source"],
                    "note": args.summary_note, "seeds": result["seeds"], "runs": result["runs"],
                    "runs_passed": result["runs_passed"], "by_scenario": result["by_scenario"]}))
            passed = sum(r["passed"] for r in result["results"])
            print(f"Scenario suite: {passed}/{len(result['results'])} runs passed every system check")
            return 0 if result["all_passed"] else 1
        if args.benchmark:
            seeds = list(range(args.benchmark_start, args.benchmark_start + args.benchmark))
            result = benchmark(seeds, args.duration)
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "benchmark.json").write_bytes(dumps(result))
            for key, entry in result["checks"].items():
                print(f"  {entry['label']:<52} mean {entry['mean']:>10.4f}  worst {entry['worst']:>10.4f}  "
                      f"target {entry['target']:<8} pass {entry['pass_rate']:.0%}")
            for failure in result["failures"]:
                print(f"  FAILED seed {failure['seed']}: {failure['label']} = {failure['value']} "
                      f"(target {failure['target']} {failure['unit']})".rstrip())
            print(f"Benchmark over {len(seeds)} seeds: {result['checks_passed']}/{result['checks_run']} checks passed"
                  f"{'' if result['all_passed'] else ' (failures retained above and in benchmark.json)'}")
            return 0 if result["all_passed"] else 1
        config = SCENARIOS[args.scenario].configure(args.seed)
        if args.duration is not None:
            config = replace(config, twin=replace(config.twin, duration_s=args.duration))
        config = replace(config, actuate=not args.sham)
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
        print(f"  audit replay status: {result['replay_status']}")
        ok = ok and result["valid"]
    print(f"  elapsed {time.perf_counter() - started:.1f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
