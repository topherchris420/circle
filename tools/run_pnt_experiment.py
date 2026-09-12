"""Run a seeded PNT estimator benchmark and export its measured simulation errors."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.pnt.bridge import CirclePNTSessionRecordAdapter
from models.pnt.experiment import PNTExperimentConfig, run_experiment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=10.0, help="Simulation duration (s)")
    parser.add_argument("--dt", type=float, default=0.01, help="Time step (s)")
    parser.add_argument("--seed", type=int, default=42, help="Reproducible sensor noise seed")
    parser.add_argument("--output-session-record", type=Path, default=Path("outputs/pnt_session_record.json"))
    parser.add_argument("--output-metrics", type=Path, help="Metrics and trace JSON (defaults to <record>.metrics.json)")
    args = parser.parse_args(argv)
    metrics_path = args.output_metrics or args.output_session_record.with_suffix(".metrics.json")
    if metrics_path.resolve() == args.output_session_record.resolve():
        parser.error("Session record and metrics paths must differ")
    try:
        config = PNTExperimentConfig(duration_s=args.duration, dt_s=args.dt, seed=args.seed)
        result = run_experiment(config)
        payload = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        metrics = result["metrics"]["reference_aided"]
        record = CirclePNTSessionRecordAdapter.create_model_result_record(
            experiment_id=result["experiment"], duration_s=config.duration_s, dt_s=config.dt_s,
            position_rmse_m=metrics["position_rmse_m"], velocity_rmse_m_s=metrics["velocity_rmse_m_s"],
            drift_rate_m_hr=metrics["final_error_per_hour_m"],
            artifact_id="sha256:" + hashlib.sha256(payload).hexdigest(),
        )
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_session_record.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_bytes(payload)
        args.output_session_record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError) as exc:
        print(f"PNT experiment failed: {exc}", file=sys.stderr)
        return 1
    print(f"Exported PNT metrics: {metrics_path}")
    print(f"Exported CIRCLE PNT session record: {args.output_session_record}")
    print(f"Simulated position RMSE: classical={result['metrics']['classical']['position_rmse_m']:.6f} m; reference-aided={metrics['position_rmse_m']:.6f} m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
