# Quantum Positioning and Navigation (PNT) Experiment Specification

> **NOTICE**: ENGINEERING REVIEW ONLY. This document describes the cold-atom quantum positioning, atom interferometry, gravity gradiometry, and relativistic quantum clock experimentation architecture integrated into the CIRCLE platform.

---

## 1. Overview

The runnable benchmark evaluates the implemented estimator with simulated IMU and reference accelerometer streams. It compares aided and unaided navigation against known truth, with deterministic noise, actual trajectory errors, and checksummed records bound to a metrics artifact.

```bash
python tools/run_pnt_experiment.py --duration 10 --dt 0.01 --seed 42 \
  --output-session-record outputs/pnt-record.json
python tools/check_session.py outputs/pnt-record.json
```

The [reproducibility guide](../../docs/reproducible-experiments.md) defines the executed workload and its limits. The protocol, analysis plan, controls, and configuration examples in this directory describe the broader proposed research program. Their quantum-state, gradiometer, clock, UKF, NEES, and Allan-deviation studies are not implemented by this benchmark.

---

## 2. Directory Structure

- `protocol.md`: Step-by-step standardized simulation and benchmarking procedure.
- `analysis-plan.md`: Estimands, statistical consistency tests (NEES, NIS), and Allan deviation analysis.
- `controls.md`: Null controls, classical IMU baselines, and sham observation specifications.
- `configurations.example.json`: Machine-readable configuration examples conforming to `contracts/quantum-pnt.schema.json`.
