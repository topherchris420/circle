# The Resonance Workbench

The Resonance Workbench is CIRCLE's browser research interface: a precision
instrument view over the physiology pipeline's recorded evidence, with an
original adaptive audio engine, a responsive visual field, a consent-gated
session designer, and an evidence explorer. It extends — and does not replace —
the [classic workbench](workbench.md); both are served by
`python tools/run_workbench.py` (classic at `/`, Resonance at `/resonance`).

> [!WARNING]
> **ENGINEERING REVIEW ONLY.** Everything the Resonance Workbench displays is
> simulated evidence from the physiology twin. No hardware is connected, no
> person is measured, and no clinical, cognitive, or relaxation effect is
> claimed. Audio and visuals are a presentation of recorded evidence, not a
> demonstrated physiological intervention.

It was designed after a lawful, publicly observable study of commercial
neurotechnology and biofeedback products (see
[`docs/rea-research/`](rea-research/README.md)). The goal was not to imitate
them but to keep their good interaction patterns while providing what they
rarely do together: traceable measurements, explainable feedback decisions,
reproducible experiments, and explicit consent.

## Architecture

```
browser (/resonance)                       local server (tools/run_workbench.py)
┌────────────────────────────┐             ┌──────────────────────────────────┐
│ resonance.js   app + charts │  GET /api/runs/<id>/timeline                 │
│ audio-engine.js  pure       │ ─────────▶  models/workbench_timeline.py     │
│   scheduling (node-tested)  │             │  reads the run's exported bundle │
│ synth.js   Web Audio render │             │  (analysis.json, ledger,        │
│ visual.js  canvas field     │             │   manifest, audit.json)          │
└────────────────────────────┘             ┌─▼──────────────────────────────┐
                                           │ models/physiology/feedback.py   │
                                           │  deterministic, quality-gated   │
                                           │  parameter events (versioned)   │
                                           └─────────────────────────────────┘
```

Three boundaries matter:

1. **Evidence stays the authority.** The timeline is a *view* over the run's
   exported bundle; each block names the artifact and SHA-256 it was read
   from. Feedback events are recomputed from the ledger's controller
   evaluations on every request, so replaying the same bundle yields
   byte-identical events and a comparable digest.
2. **The mapping is deterministic and bounded.**
   [`models/physiology/feedback.py`](../models/physiology/feedback.py) turns
   causal evaluation features into bounded synthesis parameters (level,
   intensity, brightness, tempo, spatial width, breathing period). Quality
   gates come from the controller evaluation itself: when the gate fails or a
   required feature is missing, the event *holds* its previous parameters,
   sets its level to zero, and names its reasons. Nothing is invented.
3. **Audio is consent-gated and capped.** The browser engine is silent until a
   person allows audio in the session designer; the session records that
   choice, the server refuses an audio session without it, and the master gain
   is hard-capped by the session's `max_gain` ceiling with a limiter. Stop
   and mute controls stay visible during playback.

### The mapping, stated plainly

| Parameter | Derived from | Bound |
| --- | --- | --- |
| `intensity` | controller arousal index (weighted z-score sum) | 0–1 |
| `level` | 0.25 + 0.75 × intensity, times the session ceiling | ≤ `max_gain` ≤ 0.5 |
| `brightness` | intensity | 0.2–1.0 (filter cutoff scale) |
| `tempo` | intensity | 0.75–1.25 × |
| `spatial` | intensity | 0.3–0.8 (stereo width) |
| `breath_period_s` | measured respiration rate when causally available, else the guided rate | 6–15 s (4–10 breaths/min) |

No claim is made that any frequency or parameter causes a physiological state.
The breathing guidance follows the *measured* respiratory rate when the
evidence supports it — a presentation choice, not resonance locking.

## What each view shows

- **Design** — the 8-step session designer: scenario, arm (active/sham),
  seed, feedback modalities, safe limits, consent, run.
- **Dashboard** — synchronized timelines: heart rate (10 s windows), RMSSD
  (60 s windows, good-quality beats only, withheld windows labeled), respiration,
  EDA skin-conductance level, motion fraction with episode shading, a
  quality-gate strip per evaluation, and the feedback engine's level/intensity
  with muted regions shaded. Decision markers and cue ticks share the time
  axis; playback is scrubbable at 1–8×.
- **Feedback** — the audio engine controls (enable/mute/level/breathing) and
  the live parameter-mapping readout: exactly which features drive each
  parameter at the current position.
- **Field** — the visual feedback environment: restrained cymatic-inspired
  rings whose radius and texture follow intensity, brightness, and respiration
  phase. Reduced-motion preference renders per-event stills.
- **Evidence** — the explorer: pick any decision or evaluation and inspect
  the measurements available, decision time and input cutoff, quality gate,
  controller state, the rule text that authorized or withheld feedback, the
  requested feedback parameters, the execution chain (command → electrical
  onset → physical observation), and the replay verdicts.
- **History** — past sessions with scorecard and audit status; a click loads
  the timeline; evidence bundles remain downloadable from the classic view.

## Tests and benchmarks

- [`tests/test_feedback_mapping.py`](../tests/test_feedback_mapping.py) —
  bounds, gating, honest holds, determinism, round-trip.
- [`tests/test_workbench_timeline.py`](../tests/test_workbench_timeline.py) —
  the timeline as a faithful view over real exported evidence.
- [`tests/test_resonance_http.py`](../tests/test_resonance_http.py) — routes,
  consent enforcement at session start, timeline determinism over HTTP.
- [`tests/test_resonance_assets.py`](../tests/test_resonance_assets.py) —
  local-only assets, structure, accessibility markers, and the
  node property harness (`tests/js/audio_engine_harness.js`) when node exists.
- [`tools/run_resonance_benchmark.py`](../tools/run_resonance_benchmark.py)
  — preregistered software-level checks (determinism, latency horizon, muting,
  bounds, intervention expectations, reproducibility, export integrity,
  consent, HRV labeling). Results are committed in
  [`docs/resonance-benchmark.json`](resonance-benchmark.json) and include the
  seed sets used. One expectation (the evidence-age bound) was corrected
  before the recorded runs when the observed 41 s horizon turned out to be the
  controller's designed feature window — the revision is documented in the
  benchmark source.

## Implementation vs. planned capability

| Capability | Status | Boundary |
| --- | --- | --- |
| Session designer (8 steps, safe limits, consent) | **Implemented** | Simulated sources only |
| Synchronized physiological dashboard | **Implemented** | 10 s / 60 s window cadences; presentation-layer HRV from exported beats, not the scored pipeline metric |
| Adaptive audio engine (procedural synthesis) | **Implemented** | Rendering quality per device not benchmarked; scheduling layer is |
| Quality-gated feedback with honest holds | **Implemented** | Gate criteria are the controller's, not tuned for audio |
| Visual feedback field | **Implemented** | Algorithmic rendering of features; not a physical measurement |
| Evidence explorer (decisions, feedback, replay) | **Implemented** | Reads the export as written; later file edits must be re-audited |
| Consent for audio, recorded per session | **Implemented** | Recorded user choice — the standalone Ed25519 consent gate remains unintegrated (see [Consent-by-Design](consent-by-design.md)) |
| Live device streams | **Planned** | Real-device adapters enter only through the tested acquisition contract |
| Real-time (wall-clock) closed loop | **Planned** | Today the workbench plays back recorded sessions deterministically |
| HRV frequency-domain metrics, SpO₂ panel | **Planned** | Analysis exists in the pipeline; dashboard surfaces RMSSD first |
| Cryptographic consent in the loop | **Planned** | `circle_authority.py` integration is an open task |

## Optional R.A.I.N. integration architecture

[R.A.I.N.](https://github.com/topherchris420/lop-nur-twin) (Recursive
Architecture for Intelligent Nexus) is a possible research deliberation layer.
The boundary, in one sentence: **R.A.I.N. may propose; CIRCLE's
deterministic controller, validated protocols, and human authorization
decide.**

The adapter contract (contract-only today; no mandatory remote dependency):

1. **Proposals in.** R.A.I.N. submits experiment manifests that validate
   against [`contracts/rain-circle/experiment-manifest.schema.json`](../contracts/rain-circle/experiment-manifest.schema.json)
   and the protocol rules in [`models/protocols.py`](../models/protocols.py):
   simulation-only targets, mandatory sham arms, preserved timing margins,
   held-out seed checks, corrected comparisons. A named reviewer record binds
   authorization to the protocol's SHA-256. Nothing a proposer writes can
   relax these checks.
2. **Evidence out.** R.A.I.N. may read the same local, hashed artifacts the
   workbench reads (timeline documents, ledgers, scorecards) and the recorded
   feedback-event digests. It never receives raw data beyond what a session
   export already contains, and it runs locally.
3. **No override.** R.A.I.N. cannot alter the controller state, quality
   gates, consent records, or safe limits of a running or recorded session.
   Its proposals become sessions only through the same validated, authorized
   protocol path a human would use.

Nothing in this repository depends on R.A.I.N. being available; removing the
adapter contract breaks nothing (see `rain_protocol_contract` in
[`capabilities.json`](../capabilities.json)).

## Relationship to the "resonance" research extension

The name collision is acknowledged: the [resonance simulation](resonance-architecture.md)
is a separate research extension studying coupled-cavity hypotheses. The
Resonance *Workbench* is the feedback interface described here; it makes no
geometry or cavity claims.

## Milestones toward physical evidence

| Milestone | Status | Boundary |
| --- | --- | --- |
| Phantom evidence view (`/api/phantom`, Phantom tab) | **Implemented** | Provenance-first: `SIMULATED_BOARD` rehearses the path until a physical Cyton phantom run drops into the same view |
| Cryptographic consent in the loop (`models/consent_gate.py`) | **Implemented** | Presentation-only mutations (ENABLE_AUDIO/REVOKE_AUDIO); local operator key custody; no hardware/human actuation authorized |
| Browser audio rendering benchmark | **Implemented** | Real headless-browser audio graph (null sink): start, underruns, level vs. ceiling, stop, clock offset — [results](audio-rendering-benchmark.json) |
| R.A.I.N. bridge (`tools/run_rain_bridge.py`) | **Implemented** | Deterministic stand-in proposer, validated and executed beside human/fixed/random baselines; honest NOT_SUPPORTED outcomes |
| Offline public demo (`tools/build_demo.py`, GitHub Pages) | **Implemented** | Prerecorded simulated session; zero network; self-verifying page |
| One-command replication (`tools/verify_replication.py`) | **Implemented** | Verdicts REPLAY_MATCH / REPLAY_DIVERGENCE / INTEGRITY_FAILURE / INSUFFICIENT_EVIDENCE; ships inside every bundle.zip |
| Hardware-agnostic adapters (BrainFlow, LSL) | **Implemented (fakes)** | Contract-checked through fakes; live boards need the optional packages and real hardware |
| Calibrated physical experiment | **Open** | The next evidence milestone: a known input through a real board, recorded in the phantom view with failures published alongside successes |
