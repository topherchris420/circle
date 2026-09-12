"""Run the CIRCLE Emergence Lab simulation (IONS-X Deep Emergence)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.emergence import engine
from models.emergence.bridge import CircleSessionRecordAdapter, CircleTelemetryBridge
from models.session_records import load_session


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
        choices=tuple(engine.EXPERIMENTS),
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
        default=engine.DEFAULT_OUTPUT,
        help="Output path (.html for animation, .gif for video).",
    )
    parser.add_argument("--fps", type=positive_int, default=engine.DEFAULT_GIF_FPS, help="Frames per second for .gif output.")
    parser.add_argument("--seed", type=int, help="Random seed for deterministic reproducibility.")
    parser.add_argument("--headless", action="store_true", help="Evaluate all frames and write metrics without rendering an animation.")
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
    args = parser.parse_args(argv)
    if args.output.suffix.lower() not in {".html", ".gif"}:
        parser.error("--output must use .html or .gif (headless mode uses its .metrics.json sibling)")
    if args.input_data is not None and args.circle_session is not None:
        parser.error("Choose either --input-data or --circle-session")
    if args.preset == "baseline" and (args.input_data is not None or args.circle_session is not None):
        parser.error("--preset baseline generates a null control and cannot take input telemetry")
    if args.headless and args.no_metrics_sidecar:
        parser.error("--headless requires the metrics sidecar")
    destinations = [args.output, args.output.with_suffix(".metrics.json")]
    if args.export_session_records is not None:
        destinations.append(args.export_session_records)
    inputs = [path for path in (args.input_data, args.circle_session) if path is not None]
    paths = [path.resolve() for path in destinations + inputs]
    if len(paths) != len(set(paths)):
        parser.error("Input, animation, metrics, and session record paths must differ")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = engine.apply_runtime_options(args)
    target_field = None
    records = None
    calibration_threshold = None
    preset = args.preset
    bridge = CircleTelemetryBridge(field_res=config.FIELD_RES, seed=config.SEED)
    if args.circle_session is not None:
        records = load_session(args.circle_session)
        target_field = bridge.from_records(records, source_name=str(args.circle_session))
        preset = "empirical"
    elif args.input_data is not None:
        import pandas as pd
        target_field = bridge.from_dataframe(pd.read_csv(args.input_data), source_name=str(args.input_data))
        preset = "empirical"
    elif preset == "baseline":
        import numpy as np
        random_state = np.random.RandomState(config.SEED)
        target_field = engine.TelemetryTargetField.from_null_control(config.FRAMES, config.FIELD_RES, random_state)
        calibration_threshold = engine.calibrate_control_threshold(target_field, config.CORR_WINDOW, confidence=0.95)
        target_field = target_field.control_only_view(random_state)
    elif preset == "empirical":
        raise ValueError("--preset empirical requires --input-data or --circle-session")

    if target_field is not None:
        frames = target_field.frame_count if args.frames is None else min(config.FRAMES, target_field.frame_count)
        config = config.with_options(FRAMES=frames)
    recorder = engine.LongitudinalMetricsRecorder(output_dir=args.output.parent) if preset in {"baseline", "empirical"} else None
    artifacts = engine.run_simulation(
        target_field=target_field, preset=preset, recorder=recorder,
        calibrated_threshold=calibration_threshold, live=args.live,
        config=config, render=not args.headless,
    )
    output_path = args.output
    if not args.headless:
        output_path = engine.save_animation(artifacts.animation, output_path, fps=args.fps, dashboard=artifacts.dashboard)
    elif artifacts.dashboard is not None:
        artifacts.dashboard.close()
    result = engine.RunResult(
        output_path=output_path, frames=config.FRAMES, agents=config.AGENTS,
        field_res=config.FIELD_RES, on_gpu=engine.on_gpu, seed=config.SEED,
        preset=preset, experiment=args.experiment or ("quick" if args.quick else "balanced"),
        calibration_threshold=artifacts.calibration_threshold,
    )
    if not args.no_metrics_sidecar:
        result.summary_path = engine.write_metrics_sidecar(result, artifacts.metrics)
        if target_field is not None:
            summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
            summary["input"] = {
                "source": target_field.source,
                "channel_sources": target_field.channel_sources,
                "generated_control": target_field.generated_control,
            }
            result.summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if recorder is not None:
        result.metrics_path, result.metadata_path = recorder.save_summary({
            "preset": preset, "frames": config.FRAMES, "agents": config.AGENTS,
            "field_res": config.FIELD_RES, "seed": config.SEED,
            "source": target_field.source, "calibration_threshold": calibration_threshold,
        })
    if args.export_session_records is not None:
        start_us = 0
        end_us = (result.frames - 1) * 20_000
        source_ids = None
        source_ranges = None
        status_flags = ["OK", "SIMULATED_INPUT" if preset != "empirical" else "TELEMETRY_INPUT"]
        if target_field is not None:
            start_us = int(target_field.timestamps.iloc[0].value // 1000)
            end_us = int(target_field.timestamps.iloc[result.frames - 1].value // 1000)
            if target_field.generated_control:
                status_flags.append("GENERATED_NULL_CONTROL")
        if records is not None:
            used = [r for r in records if r["record_type"] == "SAMPLE_CHUNK"
                    and start_us <= r["device_time_start_us"] <= end_us]
            source_ids = sorted({r["stream_id"] for r in used})
            source_ranges = [{
                "stream_id": stream,
                "first_sequence": min(r["sequence"] for r in used if r["stream_id"] == stream),
                "last_sequence": max(r["sequence"] for r in used if r["stream_id"] == stream),
            } for stream in source_ids]
            status_flags.extend(sorted({r["provenance"] + "_INPUT" for r in used}))
        session_record = CircleSessionRecordAdapter.create_model_result_record(
            run_result=result, metrics=artifacts.metrics, device_time_start_us=start_us,
            device_time_end_us=end_us, source_stream_ids=source_ids,
            source_sequence_ranges=source_ranges, status_flags=status_flags,
            artifact_id="sha256:" + hashlib.sha256((result.summary_path or result.output_path).read_bytes()).hexdigest(),
        )
        args.export_session_records.parent.mkdir(parents=True, exist_ok=True)
        args.export_session_records.write_text(json.dumps(session_record, indent=2) + "\n", encoding="utf-8")
        print(f"Exported CIRCLE session record: {args.export_session_records}")
    print(
        f"CIRCLE Emergence run complete: {result.summary_path if args.headless else result.output_path} "
        f"({result.frames} frames, {result.agents} agents, {result.field_res}x{result.field_res}, "
        f"seed: {result.seed}, discoveries: {artifacts.metrics.total_discoveries})"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(f"Emergence run failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
