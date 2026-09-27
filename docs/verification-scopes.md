# Verification Scopes

> **ENGINEERING REVIEW ONLY — NOT FOR FABRICATION OR HUMAN CONNECTION.**

Verification must name its scope. One green check never implies another. `python tools/verify_release.py` reports each scope separately:

| Scope | What can set it | Current state |
|---|---|---|
| `SOFTWARE_CONTRACTS` | Unit tests, schemas, manifest, review-gate file, capability registry, research contracts | `PASS` in software runs |
| `SIMULATION_BENCHMARK` | Twin session scored against hidden truth, independent audit, scenario suite | `PASS` (simulated data only) |
| `GENERATED_ARTIFACTS` | Diagrams and schematics regenerate deterministically | `PASS` |
| `SCHEMATIC_ERC` | `FRESH_PASS` only from a new run of the pinned KiCad; otherwise `ARCHIVED_REPORT_PASS_NOT_RERUN` | Archived reports from KiCad 10.0.5 pass |
| `PCB_DRC` | As above, always qualified by the open routing allowlist | Zero rule violations; **412 unconnected items across 52 allowlisted nets — the boards are not routed** |
| `BENCH_VALIDATION` | Recorded bench results closing gate `BENCH_BRINGUP` | `NOT_PERFORMED` |
| `ELECTRICAL_SAFETY_REVIEW` | A named independent reviewer closing `INDEPENDENT_ELECTRICAL_SAFETY_REVIEW` | `NOT_REVIEWED` |
| `ISOLATION_WITHSTAND` | Witnessed withstand test closing `ISOLATION_CREEPAGE_CLEARANCE` | `NOT_TESTED` |
| `EMC` | Test report closing `EMC_TESTING` | `NOT_TESTED` |
| `MEASUREMENT_CHAIN` | Phantom validation closing `ELECTRONIC_PHANTOM_VALIDATION` | `NOT_VALIDATED` |
| `FABRICATION` | Every gate that blocks fabrication closed, then human sign-off | `NOT_AUTHORIZED` |
| `HUMAN_USE` | Every human-connection gate closed, including ethics approval | `NOT_AUTHORIZED` |
| `CLINICAL` | Out of scope for this repository | `OUT_OF_SCOPE_NOT_VALIDATED` |

The last eight scopes are read from [`hardware/review-gates.json`](../hardware/review-gates.json). Software can record that evidence is missing; it cannot close a gate that needs physical measurement, accredited testing, independent review, or ethics approval. `tools/check_review_gates.py` rejects a `CLOSED` gate without a named reviewer, date, and existing artifacts.

Status words mean exactly this:

- `REPOSITORY_VERIFIED`: every software scope passed **and** fresh ERC/DRC ran on the pinned KiCad. It says nothing about bench, safety, EMC, measurement, or human use.
- `SOFTWARE_VERIFIED`: explicit `--software-only` run passed; hardware checks were not requested.
- `INCOMPLETE`: software passed but the pinned KiCad was unavailable. Never success.
- `FAILED`: a step failed.

Missing KiCad never produces success. A stale checked-in report never satisfies a failed fresh run. The checked-in [`hardware/reports/verification-summary.json`](../hardware/reports/verification-summary.json) records the most recent full-mode run; an earlier version claimed `"verified": true` while its own first step recorded KiCad as skipped, and has been replaced.

## Capability status

[`capabilities.json`](../capabilities.json) states, for every module, whether an architecture is working code: `IMPLEMENTED`, `SIMULATION_VALIDATED`, `EXPERIMENTAL`, `CONTRACT_ONLY`, `DESIGNED_NOT_BUILT`, `PLANNED`, `NOT_IMPLEMENTED`, or `SPECULATIVE`, plus what each does *not* claim. `tools/check_module_registry.py` verifies paths and evidence exist and that no instrument-core module imports a research extension.

## Where numbers come from

| Class | Example | May be described as |
|---|---|---|
| Datasheet value | ISOW7742 5.0 kVrms; ADS1220 24-bit | "rated", "nominal"; never "the device achieves" |
| Derived calculation | 27.5 µA fault current (5.5 V / 199.6 kΩ) | "calculated", with the review gate that governs it |
| Simulator assumption | +23.7 ppm device clock; 1.5 µs + Exp(1.2 µs) capture latency | "assumed" |
| Simulation benchmark | HR MAE 0.39 bpm on held-out twin seeds | "against the twin" |
| Design target | < 25 mVp-p ripple; 60 s stall absorption | "target" |
| Review threshold | 1 ms PPG timestamp bound; 10 µs edge P99.9 | "specification" |
| Physical measurement | none exist | — |

A 24-bit ADC does not imply 24-bit effective physiological resolution. A microsecond timer does not imply microsecond end-to-end synchronization. A component rating is not assembled-system performance.
