# Resonance Experimental Protocol

> **ENGINEERING REVIEW / BENCH VALIDATION ONLY — NOT CERTIFIED FOR HUMAN CONNECTION.**

## 1. Experimental Sequence

Every experimental run must execute an automated 4-phase sequence to decouple transient switching artifacts and ensure baseline stability:

```text
┌────────────────┐    ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│   Phase 1:     │    │   Phase 2:     │    │   Phase 3:     │    │   Phase 4:     │
│   Baseline     │───►│   Sham Control │───►│   Active Field │───►│   Washout      │
│   (5000 ms)    │    │   (5000 ms)    │    │   (15000 ms)   │    │   (5000 ms)    │
└────────────────┘    └────────────────┘    └────────────────┘    └────────────────┘
```

### Phase Details:
1. **Baseline ($T_0 \to T_1$):** Chamber power supply energized with RF outputs disabled ($0.0\text{ V}$). CIRCLE records ambient background noise, thermal drift, and baseline PPG/EDA/IMU or electronic phantom values.
2. **Sham Control ($T_1 \to T_2$):** Resonator relays switch into a matched dummy load ($50\ \Omega$ non-radiating load). Drive amplifiers active but no field coupled into the resonant chamber. This measures acoustic noise, power supply hum, and switching transients.
3. **Active Intervention ($T_2 \to T_3$):** Resonance Controller drives the 5 subsystems ($R_\text{outer}, R_\text{middle}, R_\text{inner}, R_\text{core\_up}, R_\text{core\_down}$) according to the specified frequency ladder, phase pattern, and modulation.
4. **Washout ($T_3 \to T_4$):** Field de-energized. System monitors decay time, relaxation kinetics, and return to baseline.

## 2. Double-Blind Configuration ID Handling

* All intervention configurations are assigned a cryptographic hash identifier (`BLIND-XXXX`).
* The operator and automated analysis layer evaluate anonymized condition pairs without knowing whether a trial was $\phi$-spaced, equal-spaced, randomized, or sham.
* De-blinding is permitted only after statistical effect sizes, artifact flags, and repeatability metrics are computed and sealed.

## 3. Hardware Synchronization via `LAB_ISO`

1. CIRCLE asserts `SYNC_OUT_DRIVE` (or captures `SYNC_IN_CAPTURE`) via the BNC connector on the `LAB_ISO` domain.
2. The digital isolator (TI ISOW7742) transmits the start/stop edge across the 8.0 mm slot with sub-microsecond jitter.
3. The Resonance Experiment Controller logs the corresponding hardware timestamp in its intervention record.
4. Both records are assembled into CIRCLE's asynchronous microSD log with explicit provenance metadata.
