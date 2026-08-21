"""CIRCLE Emergence Research Module (IONS-X Deep Emergence Lab).

Provides ATOM multi-agent spatial field simulation, empirical causal discovery,
environmental moderation dynamics, and CIRCLE biosignal telemetry adaptation.
"""

from .engine import (
    CFG,
    EXPERIMENTS,
    CHANNEL_NAMES,
    COVARIATE_NAMES,
    Agent,
    EnvironmentalModerators,
    RealWorldModerator,
    PerformanceMetrics,
    LongitudinalMetricsRecorder,
    TelemetryTargetField,
    RunResult,
    SimulationArtifacts,
    LiveDashboard,
    run_simulation,
    evolve_fields,
    calibrate_control_threshold,
    set_seed,
    apply_experiment,
    build_run_summary,
    write_metrics_sidecar,
    save_animation,
)
from .bridge import (
    CircleTelemetryBridge,
    CircleSessionRecordAdapter,
    compute_crc32c,
    CIRCLE_STREAM_MAPPINGS,
)

__all__ = [
    "CFG",
    "EXPERIMENTS",
    "CHANNEL_NAMES",
    "COVARIATE_NAMES",
    "Agent",
    "EnvironmentalModerators",
    "RealWorldModerator",
    "PerformanceMetrics",
    "LongitudinalMetricsRecorder",
    "TelemetryTargetField",
    "RunResult",
    "SimulationArtifacts",
    "LiveDashboard",
    "run_simulation",
    "evolve_fields",
    "calibrate_control_threshold",
    "set_seed",
    "apply_experiment",
    "build_run_summary",
    "write_metrics_sidecar",
    "save_animation",
    "CircleTelemetryBridge",
    "CircleSessionRecordAdapter",
    "compute_crc32c",
    "CIRCLE_STREAM_MAPPINGS",
]
