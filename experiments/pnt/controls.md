# Quantum PNT Null Controls & Ablation Specifications

> **NOTICE**: ENGINEERING REVIEW ONLY. Control conditions and ablation baselines for quantum navigation benchmarking.

---

## 1. Control Conditions

1. **Condition A (Classical IMU Baseline)**:
   - Pure dead reckoning without quantum aiding.
   - Measures raw error accumulation from sensor noise and uncompensated biases.

2. **Condition B (Atom Interferometer Aided)**:
   - IMU augmented with periodic Mach-Zehnder acceleration updates.
   - Validates accelerometer bias bounding.

3. **Condition C (Gravity Gradiometer Aided)**:
   - IMU augmented with gravity gradient tensor measurements.
   - Validates terrain anomaly and attitude coupling.

4. **Condition D (Full Quantum Suite + Optical Clock)**:
   - All quantum subsystems active.
   - Evaluates overall system drift reduction.

---

## 2. Sham and Degraded Sensor Controls

- **Zero-Contrast Sham**: Atom interferometer operated with zero fringe contrast ($C=0$) to isolate shot-noise breakdown.
- **Phase-Noise Stress Test**: Laser phase noise scaled by 10x to test filter robustness under degraded optical coherence.
