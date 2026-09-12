# Quantum Positioning and Navigation (PNT) Architecture

> **NOTICE**: ENGINEERING REVIEW ONLY. This document describes the theoretical, mathematical, and algorithmic architecture of the Quantum PNT simulation module integrated into the CIRCLE platform.

---

## 1. Executive Summary

The executable module is a seeded, translation-only benchmark for the implemented 15-state bias-aiding estimator. It evaluates a classical IMU baseline and a reference-aided estimate against the same known simulated trajectory. The reference accelerometer is a Gaussian specific-force model.

| Capability | Implementation status |
| --- | --- |
| IMU propagation and accelerometer bias aiding | Executed by `models/pnt/experiment.py` |
| Baseline comparison and trajectory RMSE | Calculated over all integration steps |
| Outlier rejection and Joseph-form updates | Implemented; covariance symmetry is restored after updates |
| Quantum-state propagation, atom fringes, UKF | Research extensions, not implemented by the benchmark |
| Gradiometer and optical-clock fusion | Research extensions, not evaluated by the benchmark |
| Hardware accuracy and sensor rejection ratios | Not established |

The present state uses Euler angles and a local positive-up vertical axis. The quaternion/NED formulation below describes a target architecture and is not the executed mechanization. The experimental clock helper is not a measurement-fusion implementation and is excluded from the benchmark. See [reproducible experiments](reproducible-experiments.md#pnt-benchmark-with-ground-truth) for commands and metric definitions.

---

## 2. Target Mathematical State Representation

### 2.1 Nominal 15-State Navigation Vector
The nominal state vector $\mathbf{x} \in \mathbb{R}^{16}$ (with unit quaternion attitude):
$$\mathbf{x} = \begin{bmatrix} \mathbf{r}^n \\ \mathbf{v}^n \\ \mathbf{q}_b^n \\ \mathbf{b}_a \\ \mathbf{b}_g \end{bmatrix}$$
where:
- $\mathbf{r}^n = [r_N, r_E, r_D]^T$: Position in local NED frame (m)
- $\mathbf{v}^n = [v_N, v_E, v_D]^T$: Velocity in local NED frame (m/s)
- $\mathbf{q}_b^n = [q_w, q_x, q_y, q_z]^T$: Unit quaternion orientation on $SO(3)$
- $\mathbf{b}_a = [b_{ax}, b_{ay}, b_{az}]^T$: Accelerometer bias error (m/s$^2$)
- $\mathbf{b}_g = [b_{gx}, b_{gy}, b_{gz}]^T$: Gyroscope bias error (rad/s)

### 2.2 Linearized Error-State Dynamics
The error state $\delta\mathbf{x} \in \mathbb{R}^{15}$ is defined as:
$$\delta\mathbf{x} = [\delta\mathbf{r}^n, \delta\mathbf{v}^n, \delta\boldsymbol{\theta}^n, \delta\mathbf{b}_a, \delta\mathbf{b}_g]^T$$

The continuous-time error propagation equation is:
$$\delta\dot{\mathbf{x}}(t) = \mathbf{F}(t) \delta\mathbf{x}(t) + \mathbf{G}(t) \mathbf{w}(t)$$

where the system Jacobian $\mathbf{F}$ is:
$$\mathbf{F} = \begin{bmatrix} \mathbf{0}_{3\times 3} & \mathbf{I}_{3\times 3} & \mathbf{0}_{3\times 3} & \mathbf{0}_{3\times 3} & \mathbf{0}_{3\times 3} \\ \boldsymbol{\Gamma}^n & \mathbf{0}_{3\times 3} & -[\mathbf{f}^n_\times] & \mathbf{R}_b^n & \mathbf{0}_{3\times 3} \\ \mathbf{0}_{3\times 3} & \mathbf{0}_{3\times 3} & -[\boldsymbol{\omega}^n_\times] & \mathbf{0}_{3\times 3} & -\mathbf{R}_b^n \\ \mathbf{0}_{3\times 3} & \mathbf{0}_{3\times 3} & \mathbf{0}_{3\times 3} & -\frac{1}{\tau_a}\mathbf{I}_{3\times 3} & \mathbf{0}_{3\times 3} \\ \mathbf{0}_{3\times 3} & \mathbf{0}_{3\times 3} & \mathbf{0}_{3\times 3} & \mathbf{0}_{3\times 3} & -\frac{1}{\tau_g}\mathbf{I}_{3\times 3} \end{bmatrix}$$

---

## 3. Proposed Cold-Atom Sensing Model

### 3.1 Mach-Zehnder Phase Accumulation
In a symmetric $\pi/2 - \pi - \pi/2$ pulse sequence with pulse separation $T$, the inertial phase shift accumulated between the two interfering atomic wavepackets is:
$$\Delta\Phi = \mathbf{k}_{\text{eff}} \cdot \mathbf{a} T^2$$

The excited state population fraction detected by fluorescence is:
$$P_e = \frac{1}{2} \left(1 - C \cos(\Delta\Phi + \delta\phi)\right)$$

where $C$ is the fringe contrast and $\delta\phi$ incorporates laser and environmental phase noise.

### 3.2 Quantum Projection Noise Limit
The standard quantum limit (SQL) for $N$ uncorrelated atoms is:
$$\sigma_{\Phi,\text{SQL}} = \frac{1}{C \sqrt{N}}$$

Yielding an acceleration measurement uncertainty:
$$\sigma_a = \frac{1}{C \sqrt{N} \, k_{\text{eff}} T^2}$$

---

## 4. Proposed Relativistic Frequency Model

The fractional frequency deviation $y(t) = \frac{\Delta f(t)}{f_0}$ of the quantum clock incorporates general and special relativistic corrections:
$$y(t) = y_{\text{stochastic}}(t) + D t + \frac{g \Delta h(t)}{c^2} - \frac{v^2(t)}{2 c^2}$$

- **Gravitational Redshift**: $+1.09 \times 10^{-16} \text{ m}^{-1}$ near Earth's surface.
- **Kinematic Time Dilation**: $-5.56 \times 10^{-18} (\text{m/s})^{-2}$.

---

## 5. Epistemological and Provenance Guarantees

1. Estimator output records use `MODEL_INFERRED` and the explicit `SIMULATED_INPUT` flag. Referenced streams are the simulated IMU and reference accelerometer actually used.
2. Records are validated against the session schema, including inclusive sequence ranges and a Castagnoli CRC-32C checksum. CRC detects accidental corruption and does not authenticate the record.
3. The exported metrics file retains the configuration, seed, trace, and errors calculated against simulated truth. The session record references its SHA-256.
4. Covariance-derived uncertainty is reported separately from RMSE. A single synthetic benchmark does not establish general performance improvement or physical quantum sensing capability.
