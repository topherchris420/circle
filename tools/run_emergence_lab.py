"""Run the CIRCLE Emergence Lab simulation (IONS-X Deep Emergence)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.emergence.engine import (
    CFG,
    DEFAULT_GIF_FPS,
    DEFAULT_OUTPUT,
    EXPERIMENTS,
    LiveDashboard,
    LongitudinalMetricsRecorder,
    RunResult,
    TelemetryTargetField,
    apply_experiment,
    apply_runtime_options,
    calibrate_control_threshold,
    on_gpu,
    rng,
    run_simulation,
    save_animation,
    set_seed,
    write_metrics_sidecar,
)
from models.emergence.bridge import CircleSessionRecordAdapter, CircleTelemetryBridge


def positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the CIRCLE Emergence Lab (IONS-X Deep Emergence) simulation."
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use a smaller, faster configuration for quick runs and tests.",
    )
    parser.add_argument(
        "--experiment",
        choices=tuple(EXPERIMENTS),
        help="Named hyperparameter bundle (balanced, quick, arv, coherence, dense-agents).",
    )
    parser.add_argument("--frames", type=positive_int, help="Number of animation frames.")
    parser.add_argument("--agents", type=positive_int, help="Number of autonomous operators.")
    parser.add_argument("--field-res", type=positive_int, dest="field_res", help="2D field grid resolution.")
    parser.add_argument(
        "--preset",
        choices=("synthetic", "baseline", "empirical"),
        default="synthetic",
        help="Run mode: synthetic sandbox, baseline null control, or empirical CSV telemetry.",
    )
    parser.add_argument("--input-data", type=Path, help="CSV input telemetry file.")
    parser.add_argument(
        "--circle-session",
        type=Path,
        help="CIRCLE session record JSON or NDJSON input file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output path (.html for animation, .gif for video).",
    )
    parser.add_argument("--fps", type=positive_int, default=DEFAULT_GIF_FPS, help="Frames per second for .gif output.")
    parser.add_argument("--seed", type=int, help="Random seed for deterministic reproducibility.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Stream live metrics to console during simulation.",
    )
    parser.add_argument(
        "--no-metrics-sidecar",
        action="store_true",
        help="Do not write <output>.metrics.json sidecar summary.",
    )
    parser.add_argument(
        "--export-session-records",
        type=Path,
        help="Export compliant CIRCLE MODEL_INFERRED session records to specified JSON path.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    apply_runtime_options(args)

    target_field: TelemetryTargetField | None = None
    calibration_threshold: float | None = None

    if args.circle_session is not None:
        bridge = CircleTelemetryBridge(field_res=CFG.FIELD_RES)
        raw_text = args.circle_session.read_text(encoding="utf-8").strip()
        if raw_text.startswith("["):
            records = json.loads(raw_text)
        else:
            records = [json.loads(line) for line in raw_text.splitlines() if line.strip()]
        target_field = bridge.from_records(records, source_name=str(args.circle_session))
    elif args.input_data is not None:
        target_field = TelemetryTargetField.from_csv(args.input_data, CFG.FIELD_RES, rng)
    elif args.preset == "baseline":
        target_field = TelemetryTargetField.from_null_control(CFG.FRAMES, CFG.FIELD_RES, rng)
        calibration_threshold = calibrate_control_threshold(target_field, CFG.CORR_WINDOW, confidence=0.95)
        target_field = target_field.control_only_view(rng)
    elif args.preset == "empirical":
        raise ValueError("--preset empirical requires --input-data or --circle-session")

    if target_field is not None and args.frames is None:
        CFG.FRAMES = target_field.frame_count

    recorder = LongitudinalMetricsRecorder() if args.preset in {"baseline", "empirical"} or args.circle_session else None

    artifacts = run_simulation(
        target_field=target_field,
        preset=args.preset,
        recorder=recorder,
        calibrated_threshold=calibration_threshold,
        live=getattr(args, "live", False),
    )

    output_path = save_animation(artifacts.animation, args.output, fps=args.fps, dashboard=artifacts.dashboard)

    result = RunResult(
        output_path=output_path,
        frames=CFG.FRAMES,
        agents=CFG.AGENTS,
        field_res=CFG.FIELD_RES,
        on_gpu=on_gpu,
        seed=CFG.SEED,
        preset=args.preset,
        experiment=getattr(args, "experiment", None) or "balanced",
        calibration_threshold=artifacts.calibration_threshold,
    )

    if artifacts.metrics is not None and not getattr(args, "no_metrics_sidecar", False):
        result.summary_path = write_metrics_sidecar(result, artifacts.metrics)

    if args.export_session_records is not None and artifacts.metrics is not None:
        session_record = CircleSessionRecordAdapter.create_model_result_record(
            run_result=result,
            metrics=artifacts.metrics,
            device_time_start_us=0,
            device_time_end_us=int(result.frames * 20_000),
        )
        args.export_session_records.parent.mkdir(parents=True, exist_ok=True)
        args.export_session_records.write_text(json.dumps(session_record, indent=2) + "\n", encoding="utf-8")
        print(f"Exported CIRCLE session record: {args.export_session_records}")

    print(
        f"CIRCLE Emergence run complete: {result.output_path} "
        f"({result.frames} frames, {result.agents} agents, {result.field_res}x{result.field_res}, "
        f"discoveries: {artifacts.metrics.total_discoveries if artifacts.metrics else 0})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
