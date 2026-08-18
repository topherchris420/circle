# CIRCLE Resonance Architecture & Laboratory Integration

> **ENGINEERING REVIEW ONLY** — Experimental research architecture. Not approved for human connection, clinical use, or medical diagnosis.

## 1. System Context

The CIRCLE Resonance Module extends CIRCLE's closed-loop experimental capabilities to investigate whether externally driven multi-frequency electromagnetic or acoustic fields within structured geometric cavities correlate with reproducible changes in synchronized biosignals.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CIRCLE REV B HARDWARE                            │
│                                                                             │
│   ┌───────────────────────────────┐        ┌────────────────────────────┐   │
│   │       BAT_HUMAN Domain        │        │       LAB_ISO Domain       │   │
│   │  - ESP32-S3 Compute           │        │  - BNC SYNC IN             │   │
│   │  - ADS1220 24-bit EDA         │   8mm  │  - BNC SYNC OUT            │   │
│   │  - MAX30102 PPG Optical Head  │  Slot  │  - ISOW7742 Isolated DCDC  │   │
│   │  - ICM-42688-P 6-axis IMU     │  Cut   │  - 5.0 kVrms Barrier       │   │
│   │  - MicroSD Asynchronous Log   │        │                            │   │
│   └──────────────┬────────────────┘        └─────────────┬──────────────┘   │
└──────────────────┼───────────────────────────────────────┼──────────────────┘
                   │                                       │
            NO CONDUCTIVE                               Isolated
             CONNECTION                                Hardware Sync
                   │                                       │
                   X                                       ▼
                   │                     ┌──────────────────────────────────┐
                   │                     │  Resonance Experiment Controller │
                   │                     │  - Multi-channel DDS Signal Gen  │
                   │                     │  - Precision Power Sensors       │
                   │                     │  - Isolated Trigger Interface    │
                   │                     └─────────────────┬────────────────┘
                   │                                       │ Multi-Channel Drive
                   │                                       │ (5 Independent Channels)
                   │                                       ▼
    ┌──────────────┴───────────────┐     ┌──────────────────────────────────┐
    │  Human / Phantom Subject     │◄────┤  External Resonance Chamber      │
    │  (Sensing Only)              │Rad. │  - 3 Nested Spheres (Phi-spaced) │
    └──────────────────────────────┘Field│  - Dual-Tetrahedron Merkaba Core │
                                         └──────────────────────────────────┘
```

## 2. Independent Resonant Subsystems

The resonance chamber incorporates 5 independently controllable subsystems:

1. **$R_\text{outer}$ (Outer Spherical Resonator, Diameter $D$):** Low-frequency boundary cavity defining the primary electromagnetic/acoustic standing-wave containment.
2. **$R_\text{middle}$ (Middle Spherical Resonator, Diameter $D/\phi$):** Intermediate geometric cavity scaled by the golden ratio $\phi \approx 1.6180339887$.
3. **$R_\text{inner}$ (Inner Spherical Resonator, Diameter $D/\phi^2$):** High-frequency focus boundary enclosing the central active region.
4. **$R_\text{core\_up}$ (Upward Pointing Tetrahedron):** Top tetrahedral resonant element fed by independent high-speed DDS driver.
5. **$R_\text{core\_down}$ (Downward Pointing Tetrahedron):** Inverted tetrahedral resonant element forming the dual-interpenetrating (Merkaba) geometry.

## 3. Data Flow and Provenance Linkage

```text
CIRCLE Sensors (EDA, PPG, IMU)
       │
       ▼
Deterministic Timestamp Capture (1 us hardware counter)
       │
       ▼
Isolated SYNC Event (BNC edge through ISOW7742)
       │
       ▼
Resonance Intervention Record (Drive frequencies, power, Q-factor)
       │
       ▼
MicroSD Asynchronous Storage (Assembled with CRC32C)
       │
       ▼
Offline Closed-Loop Model & Artifact Discrimination
```
