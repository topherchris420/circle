# Quantum Positioning and Navigation (PNT) Experiment Specification

> **NOTICE**: ENGINEERING REVIEW ONLY. This document describes the cold-atom quantum positioning, atom interferometry, gravity gradiometry, and relativistic quantum clock experimentation architecture integrated into the CIRCLE platform.

---

## 1. Overview

The Quantum PNT module simulates and benchmarks multi-sensor fusion combining:
1. 6-DOF Tactical/Navigation Grade Inertial Measurement Units (IMU)
2. Cold-Atom Light-Pulse Mach-Zehnder Atom Interferometers
3. Differential Cold-Atom Gravity Gradiometers
4. Optical Lattice / Cold-Atom Quantum Clocks

All filtering is executed via a 15-state Error-State Extended Kalman Filter (ES-EKF) or Manifold Unscented Kalman Filter (UKF) with Joseph-form covariance updates and strict positive-semidefinite (PSD) eigenvalue protection.

---

## 2. Directory Structure

- `protocol.md`: Step-by-step standardized simulation and benchmarking procedure.
- `analysis-plan.md`: Estimands, statistical consistency tests (NEES, NIS), and Allan deviation analysis.
- `controls.md`: Null controls, classical IMU baselines, and sham observation specifications.
- `configurations.example.json`: Machine-readable configuration examples conforming to `contracts/quantum-pnt.schema.json`.
