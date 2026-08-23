# Quantum PNT Experiment Protocol

> **NOTICE**: ENGINEERING REVIEW ONLY. Standardized protocol for quantum-augmented inertial navigation simulation and validation.

---

## 1. Pre-Experiment Setup

1. **Configuration Initialization**:
   - Select baseline trajectory profile (`static`, `linear`, `circle`, `eight_figure`, `helical`).
   - Define IMU error budget (noise density, bias instability, random walk, scale factor error, cross-axis misalignment).
   - Set cold-atom interferometer parameters ($k_{\text{eff}}$, interrogation time $T$, atom count $N$, contrast $C$).

2. **RNG Seeding**:
   - Explicitly supply integer seed for deterministic noise realizations.

---

## 2. Execution Pipeline

1. **Kinematic Reference Generation**:
   - Generate true position $r(t)$, velocity $v(t)$, attitude quaternion $q(t)$, specific force $f_b(t)$, and angular rates $\omega_{ib}^b(t)$.
2. **Sensor Stream Generation**:
   - Generate classical IMU measurements ($f_m, \omega_m$).
   - Generate periodic atom interferometer acceleration observations at specified sampling intervals.
   - Generate gravity gradiometer differential acceleration $\Delta a = \Gamma L$.
   - Advance quantum clock state $y(t)$ including gravitational redshift and time dilation.
3. **Filter Execution**:
   - Propagate nominal state through high-order strapdown mechanization.
   - Perform measurement updates using Joseph-stabilized Kalman equations with Mahalanobis gating.
4. **Artifact Emission**:
   - Emit validated session records to CIRCLE with Castagnoli CRC-32C checksums.
