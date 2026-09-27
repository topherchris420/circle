# CIRCLE Resonance Safety Boundary Analysis

> **ENGINEERING REVIEW ONLY** — Experimental research hardware. This document formalizes the isolation and safety boundaries of the resonance research framework.

## 1. Absolute Isolation Invariant

The core electrical rule governing the CIRCLE Resonance architecture is:

> **The external resonance chamber and its drive electronics MUST NEVER establish a conductive connection with CIRCLE's `BAT_HUMAN` domain.**

### Forbidden Connections:
* Direct contact between drive amplifiers and EDA electrodes (`EDA_DRIVE_P`, `EDA_DRIVE_N`, `EDA_SENSE_P`, `EDA_SENSE_N`).
* Direct connection to PPG contact board (`circle-ppg`) or JST-GH connector.
* Direct galvanic link to `BAT_HUMAN_GND`.
* Interfacing via USB-C (`VBUS_5V`, `USB_DP`, `USB_DN`), debug UART, or internal/external expansion headers.

## 2. Permitted Laboratory Interface: `LAB_ISO`

The only allowable interface between CIRCLE and the Resonance Experiment Controller is through the reinforced `LAB_ISO` isolated synchronization channels:

```text
CIRCLE BAT_HUMAN Domain                    CIRCLE LAB_ISO Domain
┌──────────────────────────┐   8.0 mm slot   ┌──────────────────────────┐
│ ESP32-S3 GPIO            │ ═══════════════ │ ISOW7742 Isolated Side   │
│ - SYNC_IN_CAPTURE (GPIO8)│  TI ISOW7742    │ - BNC SYNC IN (J6)       │
│ - SYNC_OUT_DRIVE (GPIO9) │ 5.0 kVrms Dielectric│ - BNC SYNC OUT (J7)  │
│ - Internal Isolated GND  │                 │ - LAB_ISO_GND            │
└──────────────────────────┘                 └─────────────┬────────────┘
                                                           │
                                                  50-ohm Coaxial Cable
                                                           │
                                                           ▼
                                             Resonance Experiment Controller
```

## 3. Physical Spacing & High-Voltage Isolation

1. **8.0 mm Cutout Slot:** The PCB design includes a slot intended to increase creepage between `BAT_HUMAN` and `LAB_ISO`. The 5.0 kVrms figure is the isolator's component rating; the assembled barrier has not been reviewed or tested (gate `ISOLATION_CREEPAGE_CLEARANCE`).
2. **Fail-Off Interlocks:** Any attachment of USB or debug instrumentation automatically opens hardware optocoupler / solid-state switches on the EDA analog front-end.
3. **Power Budgeting & Thermal Limiting:** Any future drive must measure and clamp input power so chamber heating cannot masquerade as a response. No chamber or drive exists.
