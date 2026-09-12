# Reproducible experiments and session replay

> **ENGINEERING REVIEW ONLY** — These tools evaluate software models and saved telemetry. They do not operate hardware or authorize human connection.

## Run an experiment without rendering

```bash
python tools/run_emergence_lab.py --quick --headless --seed 42 \
  --output outputs/emergence.html \
  --export-session-records outputs/emergence-record.json
python tools/check_session.py outputs/emergence-record.json
```

`--headless` evaluates every frame and writes `outputs/emergence.metrics.json`. Omit it to also render the HTML animation. Both modes use the same simulation. Rendering, scrubbing, and repeated animation exports do not advance the model or change its discovery counts.

Each invocation starts from its requested configuration and owns its simulation RNG. Metrics report the actual seed, frame count, agent count, and grid size. Identical inputs and settings reproduce numerical results within the same Python, NumPy, and compute environment. Metrics JSON contains no wall-clock timestamp; output paths remain part of its metadata. HTML/GIF bytes, longitudinal log filenames, and results across different library versions or CPU/GPU backends are not promised to be identical.

## Replay the supplied synthetic telemetry

```bash
python tools/check_session.py experiments/emergence/telemetry.example.ndjson
python tools/run_emergence_lab.py --headless --agents 24 --field-res 16 \
  --circle-session experiments/emergence/telemetry.example.ndjson \
  --output outputs/replay.html --export-session-records outputs/replay-record.json
```

The example is explicitly `SIMULATED`. Replayed results remain `MODEL_INFERRED` and retain input provenance in status flags. They also retain the original device times and the exact sequence ranges used, including when `--frames` selects a shorter prefix. A model record's `artifact_id` contains the SHA-256 of its metrics JSON (or animation when metrics are explicitly disabled).

`--input-data data.csv` accepts aligned telemetry rows. Recognized channels include `ppg_red`, `ppg_ir`, `eda_raw`, `eda_conductance`, and `imu_accel_x`. Use integer `device_time_us` or strictly increasing `timestamp` values. Without timestamps, the bridge generates a relative clock at its configured sampling rate (50 Hz by default); it does not establish a hardware timebase.

Missing values, non-finite samples, duplicate columns, duplicate timestamps, and reversed timestamps fail with an error. A DataFrame's index labels do not change its samples. Supplied `control_baseline` or `sham_control` values are retained. If neither exists, a seeded synthetic null control is generated and identified in the metrics and exported status flags. Entirely absent non-control channels are zero-valued model inputs; the recorded `channel_sources` mapping distinguishes them from supplied measurements.

Several sensor columns can map to one ATOM channel. The canonical channel name takes precedence, followed by the stable alias order in `CIRCLE_STREAM_MAPPINGS`. The optical default selects `ppg_red` before `ppg_ir`; the selected mapping is exported. To choose a different source through the Python API:

```python
from models.emergence.bridge import CircleTelemetryBridge

bridge = CircleTelemetryBridge(
    seed=42,
    channel_sources={"optical_ir": "ppg_ir", "em_rf": "imu_accel_z"},
)
target = bridge.from_dataframe(dataframe)
```

All original columns remain available in `target.input_values`. No averaging across different physical units is implied by this channel selection. ATOM uses pairwise correlations on normalized spatial model fields; these results do not establish causality or measure subjective experience. Normalization uses the selected input segment and is intended for offline analysis.

## Session JSON profile

`models.session_records` validates actual records against Draft 2020-12 JSON Schema, followed by semantic checks for time ordering, lineage coverage, sequence ranges, and CRC-32C. The reader accepts a single JSON object, an array, or NDJSON. It rejects duplicate JSON keys, non-finite values, reversed ranges, overlapping source ranges, and corrupt checksums.

The additive 2.1 telemetry snapshot profile gives `SAMPLE_CHUNK` these required fields:

| Field | Meaning |
| --- | --- |
| `stream_id` | Source stream identifier |
| `sequence` | Nonnegative, monotonically increasing sample sequence |
| `payload` | Nonempty mapping of channel names to finite numeric values |
| `device_time_start_us`, `device_time_end_us` | Equal timestamps for this one aligned snapshot |

Existing model-result records remain compatible. Old unstructured telemetry dictionaries must be wrapped as valid snapshots before session replay. Binary multi-sample chunk layouts are outside this JSON profile.

Create a checksummed snapshot using `seal_record`:

```python
from models.session_records import seal_record

record = seal_record({
    "schema_version": "2.1.0",
    "record_type": "SAMPLE_CHUNK",
    "provenance": "SIMULATED",
    "device_time_start_us": 0,
    "device_time_end_us": 0,
    "status_flags": ["SYNTHETIC_DEMO"],
    "stream_id": "demo",
    "sequence": 0,
    "payload": {"ppg_red": 100.0, "eda_raw": 2.0},
})
```

Sequence ranges use inclusive endpoints. A stream may start at a nonzero sequence when loading an excerpt. Subsequent missing sequences require a `GAP` with that `stream_id`, exact dropped endpoints, and a cause. The auditor accepts declared gaps; emergence replay requires a gap-free segment and does not interpolate over loss. Different streams can be interleaved and are joined at equal native timestamps. Missing channel values after that join are rejected.

CRC-32C covers compact, sorted-key, ASCII-escaped UTF-8 JSON with the `crc32c` field omitted (`allow_nan=False`). It detects accidental corruption, not intentional tampering. The auditor's canonical content SHA-256 supports comparisons across JSON formatting; it is not a signature or an authenticated chain of custody.

## PNT benchmark with ground truth

```bash
python tools/run_pnt_experiment.py --duration 10 --dt 0.01 --seed 42 \
  --output-session-record outputs/pnt-record.json
python tools/check_session.py outputs/pnt-record.json
```

This runs the implemented 15-state bias-aiding estimator and a classical baseline against the same simulated IMU samples. The trajectory has known initial position and velocity, translation without rotation, constant accelerometer bias, Gaussian sensor noise, and a 2 Hz reference accelerometer. The output metrics and trace live in `outputs/pnt-record.metrics.json`; the session record references their SHA-256.

Position RMSE is `sqrt(mean(sum((estimated_position - truth_position)^2)))`, computed over every integration step. Velocity RMSE uses the same definition. Final position error is also reported. `final_error_per_hour_m` scales the endpoint error by duration; it is not a fitted drift rate. A decimated trace is exported for longer runs, while errors always use every step.

The reference update estimates IMU bias from synchronized IMU minus reference specific force. A configurable squared Mahalanobis threshold rejects outliers before state mutation. Linear solves and Joseph-form covariance updates avoid explicit matrix inversion. The estimator's `state_summary()` now names covariance-derived quantities `position_uncertainty_rss_m` and `velocity_uncertainty_rss_m_s`; these replace the misleading `*_rmse_*` keys. Actual RMSE requires ground truth and is supplied by the benchmark.

The reference is a Gaussian sensor model. Quantum-state propagation, atom fringes, gradiometer fusion, clock fusion, large rotations, and hardware accuracy are not validated by this benchmark. Exported records no longer claim calibrated navigation or list sensors that were not simulated.

## Verification scopes

```bash
python tools/verify_release.py --software-only
# Requires the exact KiCad version in toolchain.json:
python tools/verify_release.py
```

Software-only success reports `SOFTWARE_VERIFIED`, `software_verified: true`, and `verified: false`. A full run without KiCad reports `INCOMPLETE` and exits nonzero. Full verification checks the executable version, writes new ERC/DRC reports into an empty temporary directory, and evaluates their structure, source, version, and allowlists before publishing them. An old checked-in report cannot satisfy a failed fresh run.
