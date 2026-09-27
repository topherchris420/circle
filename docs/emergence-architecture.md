# Emergence Architecture

> **ENGINEERING REVIEW ONLY** — Experimental research architecture. Not certified for clinical, medical, or human-connected use.

## Overview

The **CIRCLE Emergence Research Module** integrates the **ATOM (Analyses, Targets, Operators, Moderators)** dynamical field simulation and causal discovery engine (originating from IONS-X Deep Emergence Lab) into the CIRCLE biosignal research ecosystem.

It provides a repeatable, deterministic sandbox for exploring how physiological signals (photoplethysmography optical absorption, electrodermal activity, 6-axis inertial motion) and resonance cavity drive excitations form pairwise cross-channel correlations across spatial fields under environmental moderation.

---

The implemented analysis computes Pearson correlations on normalized spatial model fields. It does not establish causal direction, nonlocal effects, or direct measurements of consciousness. See [reproducible experiments](reproducible-experiments.md) for input selection, simulated controls, and record validation.

## 1. The ATOM Architecture

The module formalizes field-theoretic discovery into four interacting layers:

```text
┌───────────────────────────────────────────────────────────────┐
│                      MODERATORS (M)                           │
│  Geomagnetic (Kp), Lunar Phase, Sidereal Time, Coherence      │
└───────────────────────────────────────────────────────────────┘
               │ Modulates Dynamics             │ Scales Threshold & Decay
               ▼                                ▼
┌───────────────────────────────┐      ┌────────────────────────┐
│         TARGETS (T)           │      │     OPERATORS (O)      │
│  Coupled 4-Channel 2D Field   │ ◄──► │  Autonomous Agents     │
│  (EM/RF, Opt/IR, REG, Ctrl)   │      │  (Sample & Remember)   │
└───────────────────────────────┘      └────────────────────────┘
                                                   │
                                                   ▼ Correlate & Detect
                                       ┌────────────────────────┐
                                       │     ANALYSES (A)       │
                                       │  Emergent Relationship │
                                       │  Graph & Confidence    │
                                       └────────────────────────┘
```

### 1.1 Targets (T)
A coupled 4-channel spatial-temporal field $F(x, y, t) \in \mathbb{R}^{4 	imes N 	imes N}$ integrated using 2D Fourier spectral diffusion:

$$\mathcal{F}[F_c](k_x, k_y, t + \Delta t) = \mathcal{F}[F_c](k_x, k_y, t) \cdot \exp\left(-
u_c (k_x^2 + k_y^2) \Delta t \cdot M(t)
ight)$$

followed by non-linear saturation $F \leftarrow (1 - \lambda) F + \lambda 	anh(4 F)$ and cross-channel coupling.

### 1.2 Operators (O)
An ensemble of autonomous sampling agents roving the 2D grid via bounded random walks. Each agent maintains a sliding memory buffer ($W = 50$) and computes pairwise Pearson correlation coefficients:

$$r_{ij} = rac{\sum (x_i - ar{x}_i)(x_j - ar{x}_j)}{\sqrt{\sum (x_i - ar{x}_i)^2 \sum (x_j - ar{x}_j)^2}}$$

Agents are partitioned into specialized functional archetypes:
- **Perceivers:** High spatial agility, local instantaneous cross-correlation.
- **Forecasters:** Temporal lag evaluation ($5, 15, 30, 60$ frames) for causal lead-lag discovery.
- **Integrators:** Broad memory accumulation and low-frequency coherence tracking.

### 1.3 Moderators (M)
Global environmental variables modulate both field spectral diffusion and agent discovery parameters:
- **Geomagnetic Activity ($K_p$):** Geomagnetic storm pressure.
- **Lunar Phase:** Synodic cycle alignment.
- **Local Sidereal Time (LST):** Celestial coordinate orientation.
- **Solar X-Ray Flux:** Flare pressure scaling.
- **Coherence Windows:** Discrete events scaling discovery sensitivity and extending confidence decay halflives.

### 1.4 Analyses (A)
Dynamic weighted directed graph $G = (V, E, W)$ tracking discovered channel relationships. Inactive edges decay exponentially ($w_{t+1} = \gamma w_t$ with $\gamma = 0.995$) and are pruned below threshold.

---

## 2. CIRCLE Biosignal & Resonance Channel Mapping

The `CircleTelemetryBridge` maps physical CIRCLE data streams to the standard ATOM 4-channel schema:

| ATOM Channel | CIRCLE Data Stream | Physical Modality | Description |
| :--- | :--- | :--- | :--- |
| **Channel 0: EM/RF / Motion** | `imu_accel`, `imu_gyro`, `rf_noise` | ICM-42688 6-axis IMU / RF Pickup | Inertial motion artifacts and radiated EMI field monitoring. |
| **Channel 1: Optical / PPG** | `ppg_red`, `ppg_ir` | MAX30102 Optical Sensor | Raw red (660 nm) and infrared (880 nm) optical absorption. |
| **Channel 2: `eda_or_entropy`** | `eda_conductance`, `reg_variance` | ADS1220 EDA or an entropy/RNG variance | Whatever scalar is supplied. Formerly named `consciousness_proxy`; renamed for its observables. Nothing here measures consciousness. |
| **Channel 3: Control Baseline** | `control_baseline`, `sham_control` | Synthesized null noise / sham load | False-positive gauge. In **synthetic** mode the generator deliberately mixes ch2 into ch3 during coherence windows (a known injected coupling), so ch3 is not a clean null there. |

---

## 3. Null-Model Backbone

An agent "discovering" a correlation is not evidence until it is compared with what the identical procedure finds by chance. Operators sample smooth, autocorrelated fields with overlapping windows, so raw counts are large even between unrelated channels.

`models/emergence/null_model.py` re-runs the exact discovery rule on **circular-shift surrogates** of every agent's observation series (autocorrelation preserved, cross-channel alignment destroyed) and reports:

- total discoveries against the surrogate distribution (Monte Carlo p-value, never zero);
- each channel pair against the surrogate maximum over pairs (family-wise error control);
- in synthetic mode, a **known-truth score**: the generator injects ch0 ← ch1 and ch3 ← ch2 couplings, so the engine should find those pairs and only those.

A 300-frame synthetic run (`python tools/run_emergence_lab.py --quick --headless --frames 300`) produced 26,545 discoveries against a null mean of about 2,020. The two injected pairs were distinguishable from chance (FWER p = 0.01); the four independent pairs, roughly 2,000 discoveries between them, were not (FWER p ≥ 0.21). Runs shorter than 2 × window + 1 frames report `INSUFFICIENT_LENGTH` instead of a p-value. Exported records are flagged `EXPLORATORY_NOT_CONFIRMATORY` and carry the null summary.

## 4. Data Provenance & Invariants

All discoveries emitted by the Emergence Research Module strictly adhere to the CIRCLE session schema:
- **Provenance Category:** `MODEL_INFERRED` (or `SIMULATED` in synthetic mode).
- **Record Type:** `MODEL_RESULT`.
- **Integrity Evidence:** Every emitted record includes source stream sequence ranges and a calculated CRC-32C checksum over canonical JSON serialization.
- **Zero Medical Claim:** Discovery of cross-channel correlation does not assert clinical or diagnostic meaning.
