"""Adaptive feedback mapping: causal physiological features to bounded synthesis parameters.

This module is the *deterministic bridge between evidence and presentation*. It
turns controller evaluations (which already carry their own lineage, input
cutoff, and quality-gate results) into a stream of feedback parameter events
that the browser's audio and visual engines render during session playback.

Design rules, mirroring the controller:

- An event can use only evidence that exists at the evaluation's input cutoff.
  The mapping is a pure function of the evaluation series and window summaries;
  it never looks at truth or later data.
- Quality gates come from the controller evaluation itself. When the gate fails,
  the event *holds* its previous parameters and is emitted with ``muted``
  reasons rather than inventing values. Missing features never become sound.
- Every parameter is bounded by ``FeedbackConfig`` limits that are validated on
  construction, so no input can produce an unsafe amplitude, an extreme
  breathing period, or an unbounded timbre.
- The mapping is versioned. ``FEEDBACK_VERSION`` changes whenever parameter
  semantics change, so replays can detect drift.

No claim is made that these parameters cause any physiological state. The
mapping is an engineering presentation layer over already-recorded evidence;
any effect in people would need its own matched control.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

FEEDBACK_VERSION = "1.0.0"

# Features an event needs before it may drive audible feedback. Keys follow
# window_features() in models/physiology/controller.py.
REQUIRED_FEATURES = ("hr_bpm", "scl_us", "scr_rate_per_min")


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


@dataclass(frozen=True)
class FeedbackConfig:
    """Bounded presentation settings. All limits are enforced, not advisory."""

    modalities: tuple[str, ...] = ("audio", "visual")
    # Absolute synthesis amplitude ceiling (linear gain). The browser engine
    # additionally clamps its master gain to this value and applies a limiter.
    max_gain: float = 0.5
    # Safe paced-breathing guidance range: 6 s..15 s per breath (4..10 bpm).
    breath_period_min_s: float = 6.0
    breath_period_max_s: float = 15.0
    # Guidance rate used when no valid respiration estimate exists.
    guide_breath_bpm: float = 6.0
    # Arousal-index value that maps to full intensity. The arousal index is the
    # controller's weighted z-score sum; 2.0 spans a broad elevated range.
    intensity_span: float = 2.0
    # Timbre (filter cutoff scale), rhythm, and stereo width ranges.
    brightness_min: float = 0.2
    brightness_max: float = 1.0
    tempo_min: float = 0.75
    tempo_max: float = 1.25
    spatial_min: float = 0.3
    spatial_max: float = 0.8

    def __post_init__(self) -> None:
        if not self.modalities or any(m not in ("audio", "visual") for m in self.modalities):
            raise ValueError("Feedback modalities must be drawn from audio and visual.")
        if not 0.0 < self.max_gain <= 0.5:
            raise ValueError("max_gain must be within (0, 0.5]; presentation stays quiet by default.")
        if not 4.0 <= self.breath_period_min_s < self.breath_period_max_s <= 20.0:
            raise ValueError("Breath guidance period must stay between 4 and 20 seconds.")
        if not 4.0 <= self.guide_breath_bpm <= 10.0:
            raise ValueError("Guide breathing rate must stay between 4 and 10 breaths per minute.")
        if not 0.5 < self.intensity_span <= 10.0:
            raise ValueError("intensity_span must be a positive, plausible arousal range.")
        if not 0.0 <= self.brightness_min < self.brightness_max <= 1.0:
            raise ValueError("Brightness must be a bounded 0..1 range.")
        if not 0.25 <= self.tempo_min < self.tempo_max <= 2.0:
            raise ValueError("Tempo must be a bounded, gentle range.")
        if not 0.0 <= self.spatial_min < self.spatial_max <= 1.0:
            raise ValueError("Spatial width must be a bounded 0..1 range.")

    @property
    def guide_breath_period_s(self) -> float:
        return 60.0 / self.guide_breath_bpm


@dataclass(frozen=True)
class FeedbackEvent:
    """One bounded parameter frame, traceable to the evaluation that produced it."""

    time_us: int
    input_cutoff_us: int
    # Quality-gate reasons copied from the evaluation (empty list: adequate).
    gate_reasons: tuple[str, ...]
    # True when the evidence was adequate for audible feedback.
    audible: bool
    # Bounded synthesis parameters (all 0..1 except breath_period_s).
    parameters: dict[str, float] = field(default_factory=dict)
    # Exact feature values the mapping read (provenance for the explorer).
    inputs: dict[str, float] = field(default_factory=dict)
    # Controller state and decision reference at this instant.
    state: str = ""
    decision_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_us": self.time_us,
            "input_cutoff_us": self.input_cutoff_us,
            "gate_reasons": list(self.gate_reasons),
            "audible": self.audible,
            "parameters": dict(self.parameters),
            "inputs": dict(self.inputs),
            "state": self.state,
            "decision_id": self.decision_id,
        }

    def comparable(self) -> tuple:
        return (self.time_us, self.input_cutoff_us, self.gate_reasons, self.audible,
                tuple(sorted(self.parameters.items())), tuple(sorted(self.inputs.items())),
                self.state, self.decision_id)


def _respiration_period(window: dict[str, Any] | None, config: FeedbackConfig) -> float | None:
    """Guidance period from a measured respiratory rate, when one exists.

    Only windows whose device span covers the event time are passed in, so a
    returned period is evidence that existed at or before the cutoff. Accepts
    both the analysis form (``payload`` key) and a flat summary.
    """
    if not window:
        return None
    payload = window.get("payload", window)
    rate = payload.get("resp_rate_bpm")
    if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
        return None
    return config.breath_period_max_s if rate < 4.0 else (
        config.breath_period_min_s if rate > 10.0 else 60.0 / float(rate))


def _parameters(features: dict[str, float], window: dict[str, Any] | None,
                config: FeedbackConfig) -> dict[str, float]:
    """Map causal features to bounded presentation parameters."""
    arousal = features.get("arousal_index")
    intensity = _clamp01((arousal if isinstance(arousal, (int, float)) else 0.0) / config.intensity_span)
    breath = _respiration_period(window, config) or config.guide_breath_period_s
    return {
        "intensity": round(intensity, 6),
        # Amplitude follows intensity but never exceeds the validated ceiling.
        "level": round(config.max_gain * (0.25 + 0.75 * intensity), 6),
        "brightness": round(config.brightness_min + (config.brightness_max - config.brightness_min) * intensity, 6),
        "tempo": round(config.tempo_min + (config.tempo_max - config.tempo_min) * intensity, 6),
        "spatial": round(config.spatial_min + (config.spatial_max - config.spatial_min) * intensity, 6),
        "breath_period_s": round(breath, 6),
    }


def feedback_events(evaluations: list[Any], windows: list[dict[str, Any]] | None = None,
                   config: FeedbackConfig | None = None) -> list[FeedbackEvent]:
    """Deterministic parameter-event stream from controller evaluations.

    ``evaluations`` are ``models.physiology.controller.Evaluation`` records (or
    the reconstructed records the workbench reads back from a session bundle);
    ``windows`` are offline window summaries such as ``analysis.windows``. A
    window contributes only when its span ends at or before the evaluation's
    input cutoff, keeping the mapping causal. When quality gates fail or a
    required feature is missing, the event holds the previous parameters with a
    zero level and names the reasons, so degraded evidence degrades the
    presentation instead of inventing it.
    """
    config = config or FeedbackConfig()
    events: list[FeedbackEvent] = []
    held: dict[str, float] = {}
    ordered_windows = sorted(windows or [], key=lambda w: w["device_time_end_us"])
    next_window = 0
    # Windows whose span has not yet been fully observed at a cutoff.
    pending: list[dict[str, Any]] = []

    for ev in evaluations:
        cutoff = int(ev.input_cutoff_us)
        while next_window < len(ordered_windows) and int(ordered_windows[next_window]["device_time_end_us"]) <= cutoff:
            pending.append(ordered_windows[next_window])
            next_window += 1
        gate = tuple(getattr(ev, "gate_reasons", ()))
        features = {k: v for k, v in dict(getattr(ev, "features", {})).items()
                    if isinstance(v, (int, float)) and math.isfinite(float(v))}
        missing = [key for key in REQUIRED_FEATURES if key not in features]
        reasons = gate + tuple(f"FEATURE_MISSING:{key}" for key in missing)
        window = pending[-1] if pending else None
        if reasons:
            parameters = dict(held)
            parameters["level"] = 0.0
            events.append(FeedbackEvent(int(ev.decision_time_us), cutoff, reasons, False,
                                       parameters, _subset(features), str(getattr(ev, "state", "")),
                                       getattr(ev, "decision_id", None)))
            continue
        parameters = _parameters(features, window, config)
        held = dict(parameters)
        events.append(FeedbackEvent(int(ev.decision_time_us), cutoff, (), True,
                                    parameters, _subset(features), str(getattr(ev, "state", "")),
                                    getattr(ev, "decision_id", None)))
    return events


def _subset(features: dict[str, float]) -> dict[str, float]:
    """The exact values the mapping reads; kept small so events stay reviewable."""
    keys = (*REQUIRED_FEATURES, "arousal_index", "motion_fraction", "clean_since_s",
            "beat_coverage", "eda_contact_fraction", "hr_z", "scl_z", "scr_z")
    return {k: round(float(features[k]), 6) for k in keys if k in features}


def events_digest(events: list[FeedbackEvent]) -> str:
    """Stable digest over the full comparable event stream (replay checks)."""
    import hashlib
    import json
    payload = json.dumps([e.to_dict() for e in events], sort_keys=True, allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def events_from_documents(documents: list[dict[str, Any]]) -> list[FeedbackEvent]:
    """Rebuild events from their JSON form (bundle or timeline round-trip)."""
    events = []
    for doc in documents:
        events.append(FeedbackEvent(
            int(doc["time_us"]), int(doc["input_cutoff_us"]), tuple(doc["gate_reasons"]), bool(doc["audible"]),
            {k: float(v) for k, v in doc["parameters"].items()},
            {k: float(v) for k, v in doc.get("inputs", {}).items()},
            str(doc.get("state", "")), doc.get("decision_id")))
    return events
