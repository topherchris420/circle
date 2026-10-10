# CIRCLE

**A loop that can answer for itself.**

A signal becomes a decision. A decision changes a system. CIRCLE preserves the evidence connecting them.

CIRCLE is an open research instrument for studying the relationships among physiological signals, adaptive feedback, and human authority. Its working software turns simulated sensor records into bounded decisions, follows interventions through their observable consequences, and lets another researcher reconstruct the session from the raw data.

The ambition is a closed-loop human-state platform whose actions remain inspectable, reproducible, and subject to meaningful consent. Today, that ambition has a runnable digital test bench, an independent evidence auditor, a cryptographic consent module, and a hardware design awaiting physical validation.

[Run an experiment](#run-your-first-experiment) · [Follow the evidence](#follow-one-decision) · [Explore human consent](#human-authority-in-the-loop) · [See the results](#results-you-can-inspect) · [Find your way around](#find-your-way-around)

> **ENGINEERING REVIEW ONLY** — Experimental research hardware. This repository is not approved for fabrication or human connection and does not establish medical-device, electrical-safety, EMC, or measurement-performance claims. All physiological results shown here come from simulation.

![CIRCLE recovers physiological signals from simulated sensor codes and compares them with hidden ground truth](diagrams/physiology-polygraph.png)

*One simulated session, several physiological pathways, a shared timeline. Ground truth is available to the evaluator; the controller must work from the device records it actually receives.*

## Run your first experiment

**Python 3.11 or later. No device required.**

```bash
git clone https://github.com/topherchris420/circle.git
cd circle
python -m pip install -r requirements.txt
python tools/run_physiology_twin.py --output outputs/physiology --audit
```

This runs a six-minute simulated protocol: rest, breath hold, a stressor, and recovery with adaptive haptic guidance. It exports the evidence, scores estimates against hidden truth, and independently audits the session.

Open `outputs/physiology/report.html` in your browser. Start with a decision in the ledger and follow it back to the samples that justified it. Then follow its cue forward to the simulated electrical onset and IMU-observed vibration.

| Ask the report | Inspect |
|---|---|
| What did the controller know? | Input cutoff, features, quality gates, and exact sample ranges |
| Why did it act or hold? | Controller state, formula components, and recorded gate outcomes |
| Did the cue happen? | Command, electrical onset, and independently detected vibration in the twin |
| Can someone reproduce the decision? | Replay verdict and evidence audit |

The [committed example report](diagrams/circle-physiology-session.html) is also available to open locally after cloning. The [pipeline methods](docs/physiology-pipeline.md) explain how each channel is reconstructed.

**Try the counterfactual.** Run the same seed with cues withheld, or expose the controller to adversarial conditions:

```bash
# Same simulated seed, sham arm: decisions recorded, cues not actuated
python tools/run_physiology_twin.py --sham --output outputs/sham --audit

# Motion, poor contact, missing data, timing faults, and other challenges
python tools/run_physiology_twin.py --scenarios

# Reconstruct and audit an exported session independently
python tools/audit_physiology_run.py outputs/physiology
```

The twin assumes a physiological response to paced breathing. Comparing active and sham arms tests behavior under that assumption; it does not establish an effect in people.

## Follow one decision

The central question is simple: **what gives this system grounds to act?**

Consider a simulated increase in heart rate alongside a change in skin conductance. CIRCLE preserves five distinct parts of the story:

1. **Observation.** Raw EDA, PPG, IMU, and synchronization records carry device timestamps, sequence numbers, availability times, and declared gaps.
2. **Interpretation.** The pipeline derives estimates with lineage back to the exact source samples. Physiological pathways must provide sufficient agreement before guidance can begin.
3. **Decision.** The controller evaluates only evidence available at that moment and before its input cutoff. Motion, stale data, poor contact, or inadequate evidence can produce a recorded hold.
4. **Execution.** A scheduled cue is followed through command, electrical onset, and independently observed vibration. Each stage needs its own evidence.
5. **Reconstruction.** The auditor re-derives the controller decisions and derived session records from the raw bundle, then checks them against the export.

**Decision ≠ command ≠ actuation ≠ effect ≠ interpretation.** Keeping those distinctions intact is the instrument's central discipline.

A missing signal stays missing. After an impairment, the controller requires a full clean 40-second evidence window before it can treat an elevated state as sustained. A cue gains `PHYSICALLY_OBSERVED` status only from its observation record—in the current test bench, that observation is simulated too.

Replay produces an explicit verdict such as `REPLAY_MATCH`, `REPLAY_DIVERGENCE`, `TIMING_VIOLATION`, or `INSUFFICIENT_EVIDENCE`. Rewriting checksums cannot conceal a derived record that disagrees with independent reconstruction.

Read the [closed-loop evidence contract](docs/closed-loop-evidence.md), [record schema](contracts/session-record.schema.json), and [auditor](models/physiology/audit.py).

## Human authority in the loop

An adaptive system needs a clear boundary between proposing an action and having permission to perform it. CIRCLE now provides two complementary mechanisms, with separate integration boundaries.

### Consent-by-Design

[`circle_authority.py`](circle_authority.py) implements a standalone, deterministic consent gate. A restricted action becomes an immutable envelope containing its mutation, proposal timestamp, state-history hash, unique UUID, and an initially empty signature slot.

The action waits in `pending_registry` while normal telemetry continues. Only a matching `HumanConsentEvent`, pulled from the incoming queue and verified against the registered Ed25519 human master public key, can release it for execution.

| Action state | Meaning |
|---|---|
| `PENDING_SIGNATURE` | The proposal is registered; the loop continues without executing it. |
| `EXECUTED` | A valid consent event arrived and the mutation completed; the signature and exact execution frame are recorded. |
| `REJECTED` | The proposal, consent, or execution failed its checks; the action will not be retried automatically. |

Run the six-frame example:

```bash
python tools/run_authority_demo.py
```

Telemetry begins at frame 0. A proposal arrives at frame 1, waits through frames 2 and 3, and executes when signed consent arrives at frame 4. Telemetry continues at frame 5. Repeating the demo produces identical replay records.

**Integration boundary:** the gate is currently demonstrated in a standalone simulation; the physiological controller and protocol runner do not yet route through it. Signatures cover the UUID's 16 binary bytes; the host must durably bind that UUID to one envelope and prevent reuse across sessions. The separate authority replay stream records signatures and execution frames as canonical, hash-linked JSON. Immutable storage and crash recovery remain host responsibilities.

The [integration contract](docs/consent-by-design.md) covers signing, event ordering, replay, failure behavior, and the test-only credentials used by the example.

### Bound the experiment before it runs

The [experiment-protocol runner](models/protocols.py) validates proposed experiments against deterministic rules: simulation targets, mandatory sham arms, preserved timing margins, held-out seeds, and corrected statistical comparisons. A named reviewer authorizes the protocol's SHA-256 before simulated execution. This existing authorization record is separate from the Ed25519 consent gate above.

```bash
python tools/run_protocol.py validate experiments/protocols/paced-breathing-arousal.json
python tools/run_protocol.py authorize experiments/protocols/paced-breathing-arousal.json --reviewer "Your Name" --output outputs/auth.json
python tools/run_protocol.py run experiments/protocols/paced-breathing-arousal.json --authorization outputs/auth.json --output outputs/protocol-result.json
```

AI can help formulate and examine a proposal. The deterministic checks and human authorization define what may proceed.

## Results you can inspect

The checked-in benchmarks score the software against known **simulated** truth. They preserve the evaluation conditions and failures alongside the results.

| Measurement | Recorded result | Evaluation context |
|---|---|---|
| Heartbeat detection | Mean F1 **0.9999** | Motion-free PPG, ±50 ms tolerance |
| Heart rate | Mean MAE **0.39 bpm** | Recovered from raw sensor codes |
| HRV, RMSSD | Mean MAE **1.5 ms** | 60-second windows |
| Respiratory rate | Mean MAE **0.36 breaths/min** | Recovered respiratory modulation |
| Skin conductance response detection | Mean sensitivity **0.98**, PPV **1.00** | Motion-free responses ≥0.05 µS |
| PPG FIFO timing | Worst error **39.18 µs** | Reconstructed sample timestamps |
| Haptic onset detection | Worst error **2.97 ms** | IMU observation compared with the twin's onset |

Source: [physiology benchmark](docs/physiology-benchmark.json), 50 seeds, 100–149. **999 of 1,000 checks passed.** Seed 147 failed the skin-conductance response sensitivity threshold; the [methods document](docs/physiology-pipeline.md) retains and explains that result.

The [adversarial benchmark](docs/scenario-benchmark.json) records **240/240 passing runs** across eight scenarios and fresh seeds 600–629 for controller 1.2.0. An earlier round exposed a controller that could start guidance from an elevated state already resolved during a motion-obscured interval. That failure led to the clean-window precondition and a new confirmatory seed set. The [evidence history](docs/closed-loop-evidence.md) preserves the sequence.

These are reproducible software results under the twin's model. Physical sensor accuracy, hardware performance, and human outcomes require their own evidence.

## One controller, explicit boundaries

Simulation, recorded evidence, and a live acquisition interface meet at the same [`RawSession` boundary](models/physiology/loop.py). The pipeline and controller consume device records; they do not import the twin's hidden truth.

![CIRCLE acquisition boundary connecting sources to the controller, actuation gate, and evidence pipeline](diagrams/acquisition-boundary.svg)

The acquisition layer exercises corrupted, duplicated, stalled, and dropped packets. Losses become exact `GAP` records. Availability is recorded at receipt so replay can reconstruct what the controller could see. Sources that lack required streams are refused with reasons; accepted closed-loop actuator targets are currently `SIMULATED` and `NONE`.

The [Muse Gadget adapter](docs/hardware-sources.md) offers capability discovery, recorded refusals, protocol validation, and an optional operator-notification channel outside the loop. Its mapping supplies no physiological streams, so it cannot serve as a biosignal source. It is removable and has never been validated against a paired gadget.

```bash
python tools/run_acquisition_demo.py
python tools/muse_gadget.py capabilities --simulate
python tools/muse_gadget.py check --simulate
```

The gadget simulator uses local Unix-domain sockets. See [hardware sources](docs/hardware-sources.md) for setup, adapter scope, and privacy boundaries.

## From simulation to an instrument

| Layer | Where it stands |
|---|---|
| Signal reconstruction, deterministic controller, evidence export, audit, replay | Implemented and exercised against the physiology twin |
| Cryptographic consent | Implemented as a standalone event reducer with a deterministic example and tests |
| Acquisition | Simulated-link and recorded-bundle paths exercised; no live biosignal device connected |
| Rev B hardware | Designed, not built; main and optical boards remain unrouted |
| Firmware | Not implemented; the twin models timing requirements firmware must eventually meet |
| Bench, phantom, electrical-safety, EMC, or human validation | None performed |

The [capability registry](capabilities.json) records each module's status, evidence, and limits.

**Rev B is designed to make timing and intervention evidence observable.** The 85 × 55 mm main board combines an ESP32-S3, ADS1220 EDA front end, ICM-42688-P IMU, SDMMC storage, and DRV2605L haptics with current-edge detection. The 25 × 18 mm optical board carries a MAX30102 red/IR sensor. Isolated laboratory and human-connected domains, interlocks, and current limiting are design provisions awaiting physical review and measurement.

![CIRCLE Rev B visualization of intended hardware geometry](diagrams/circle-3d-animation.gif)

*Intended geometry only. This animation contains no measured telemetry and does not demonstrate a functioning device.*

[Architecture](docs/architecture.md) · [Main schematic](hardware/reports/pdf/circle-main.pdf) · [Optical schematic](hardware/reports/pdf/circle-ppg.pdf) · [Safety analysis](docs/safety-analysis.md) · [Bring-up plan](docs/board-bringup-and-validation-plan.md) · [3D viewer](diagrams/circle-3d-viewer.html)

The next physical evidence comes from electronic and optical phantoms, bench measurements, isolated system tests, and hardware loopback. The [physical evidence ladder](docs/physical-evidence-ladder.md) defines the progression and prerequisites for any eventual human-connected work.

## Research with room for uncertainty

CIRCLE also hosts bounded research extensions. Each has explicit contracts and provenance; the [module registry check](tools/check_module_registry.py) enforces the declared separation between core code and removable research packages.

| Extension | What you can examine | Current scope |
|---|---|---|
| [Resonance](docs/resonance-architecture.md) | Coupled-cavity simulations, blinded comparisons, autocorrelation-aware permutation tests, and [falsifiable hypotheses](docs/resonance-hypotheses.md) | Experimental simulation; no chamber or measured geometry effect |
| [Emergence](docs/emergence-architecture.md) | ATOM correlation search evaluated against circular-shift surrogate nulls and family-wise correction | Exploratory associations; no causal or consciousness claim |
| [PNT](docs/quantum-pnt-architecture.md) | Translation-only 15-state estimator versus an unaided baseline on shared simulated IMU data | Simulation benchmark; quantum sensing remains speculative |
| [R.A.I.N. protocol](docs/rain-circle-experiment-protocol.md) | Versioned experiment manifests, results, and analysis contracts | Contracts here; executor elsewhere |
| [Mathematics intake](docs/MATH_RESEARCH.md) | A proposed packet-loss and clock-drift experiment with a negative control | Research design; not implemented or tested |

The [shared R.A.I.N. mathematics scout](https://github.com/topherchris420/lop-nur-twin/blob/main/docs/MATH_PORTFOLIO.md) surfaces candidate references for review. A reference match does not validate an implementation.

The stranger the hypothesis, the more ordinary the measurement discipline: predefined comparisons, blinding, preserved null results, and correction for every configuration searched.

## Verify the claim you care about

```bash
# Unit and property tests, including the consent gate
python -m unittest discover -s tests

# Software, simulation, and generated-artifact verification
python tools/verify_release.py --software-only

# Full verification, including fresh ERC/DRC with the pinned KiCad toolchain
python tools/verify_release.py

# Current review gates and authorization boundaries
python tools/check_review_gates.py
```

The [checked-in verification summary](hardware/reports/verification-summary.json) records passing software scopes and an **incomplete full verification** because fresh hardware checks were not run. Archived KiCad 10.0.5 schematic reports pass; PCB checks retain an open allowlist of **52 unrouted nets**. The [18 open review gates](hardware/review-gates.json) do not authorize fabrication or human use.

Use [GitHub Actions](https://github.com/topherchris420/circle/actions) for current CI results and [`toolchain.json`](toolchain.json) for the pinned toolchain. The [verification scopes](docs/verification-scopes.md) explain exactly what each result establishes.

## Find your way around

| Start here | Purpose |
|---|---|
| [`models/physiology/`](models/physiology) | Twin, sensor models, pipeline, controller, evidence export, ledger, and independent audit |
| [`circle_authority.py`](circle_authority.py) | Human-consent state machine and replay payloads |
| [`models/acquisition/`](models/acquisition) | Ingestion, simulated link faults, and recorded replay |
| [`models/protocols.py`](models/protocols.py) | Experiment validation, reviewer authorization, and simulation execution |
| [`models/session_records.py`](models/session_records.py) · [`contracts/`](contracts) | Record validation, provenance, lineage, and experiment schemas |
| [`tools/`](tools) · [`tests/`](tests) | Runnable experiments, auditors, verification tools, and regression tests |
| [`experiments/`](experiments) | Protocols and research configurations |
| [`hardware/`](hardware) | KiCad sources, interfaces, design manifest, review gates, and reports |
| [`docs/`](docs) · [`diagrams/`](diagrams) | Methods, evidence boundaries, architecture, and visual explanations |

## Help close the next evidence gap

Useful contributions start with a question the instrument can answer:

- **Signal processing:** propose an estimator, compare it on fresh seeds, and retain the cases where it fails.
- **Consent and replay:** connect the standalone authority gate to a bounded application path, with durable UUID bindings and crash-recovery evidence.
- **Acquisition:** implement a source that satisfies the stream and timing contracts, then exercise loss, delay, and replay.
- **Hardware and firmware:** work through the documented review gates, timestamping requirements, and phantom-validation plans.
- **Research methods:** make a hypothesis falsifiable, preregister the comparison, and preserve the null result.

Open an [issue](https://github.com/topherchris420/circle/issues) with the question, proposed change, evidence it would produce, and a condition that would count as failure.

## The premise

A human state is rarely one signal. The body offers many imperfect observations; understanding begins in the relationships among them. CIRCLE treats those observations with care: an arousal index is an engineering trigger, and physiological measurements alone cannot establish a person's emotion, intent, diagnosis, or consciousness.

An adaptive instrument should be able to explain what it observed, account for what it changed, and preserve the person's authority over what happens next. That is the circle this project is working to close.

**A Vers3Dynamics research project by Christopher Woodyard.** Built by one researcher. Held in common. Free to explore.
