# CIRCLE Rev B Requirements-to-Evidence Verification Matrix

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION**

This document establishes the bidirectional proof matrix linking every functional, electrical, and safety requirement to physical design artifacts, simulation/calculation proofs, and rule-checker execution outputs.

---

## 1. Requirements Verification Matrix

| Req ID | Requirement Statement | Target Performance Metric | Evidence Artifact / Document Location | Verification Method | Result Status |
|---|---|---|---|---|:---:|
| **REQ-01** | Compute Engine & Memory Capacity | ESP32-S3 (240 MHz, 16MB Flash, 8MB PSRAM) | `hardware/reports/bom/circle-main-revB-sourced.csv` (U1) | Datasheet cross-probe; Memory test firmware | **PASS** |
| **REQ-02** | USB-C 5V UFP Sink & ESD Protection | Dual 5.1k CC pulldowns; 500mA PTC fuse; ESD protection | `hardware/circle-main/legacy/01_compute_usb.sch` (J1, R1, R2, F1, D1) | Schematic netlist inspection; Ohm's law CC verification | **PASS** |
| **REQ-03** | Pre-Charger USB VBUS Detection | $< 10\text{ }\mu\text{s}$ async disconnect upon USB mate | `hardware/circle-main/legacy/01_compute_usb.sch` & `docs/safety-and-fault-analysis.md` | Circuit delay analysis ($t_{pd} < 200\text{ ns}$) | **PASS** |
| **REQ-04** | Battery Charging & DPPM Control | BQ24074 ($I_{CHG} = 500\text{ mA}$, NTC thermistor $0-45^\circ\text{C}$) | `hardware/circle-main/legacy/02_power.sch` (U2, R_SET, R_ILIM) | Resistor formula calculation: $R_{SET} = 890 / 0.50\text{ A} = 1.78\text{ k}\Omega$ | **PASS** |
| **REQ-05** | Primary 3.3V Digital Buck-Boost | TPS63070 ($2.0-16.0\text{ V}$ input, 2.0A output, $> 85\%$ eff) | `hardware/circle-main/legacy/02_power.sch` & `docs/power-budget-analysis.md` | Efficiency derivation; Coilcraft XFL4020 $I_{sat} = 5.4\text{ A}$ margin | **PASS** |
| **REQ-06** | Ultra-Low-Noise Analog Power Supply | TPS7A2033 ($6.5\text{ }\mu\text{V}_\text{RMS}$ noise, 85 dB PSRR) | `hardware/circle-main/legacy/02_power.sch` (U7) | Datasheet noise curve; enable tied to `EDA_PREPARE` | **PASS** |
| **REQ-07** | Electrodermal Activity 24-bit ADC | ADS1220 (Dedicated SPI, DRDY interrupt, low noise) | `hardware/circle-main/legacy/03_eda_safety.sch` (U10, GPIO39-42, GPIO47) | Pin map audit; SPI timing verification | **PASS** |
| **REQ-08** | Precision Voltage Ref & Buffer | REF5020 (2.048V, 3 ppm/°C) + OPA2192 ($V_{OS} < 5\text{ }\mu\text{V}$) | `hardware/circle-main/legacy/03_eda_safety.sch` (U11, U12) | AFE excitation calculation ($0.500\text{ V} \pm 1.0\%$) | **PASS** |
| **REQ-09** | Fail-Open EDA Output Relays | Dual normally-open PhotoMOS (AQY212GS, $V_{OFF} = 60\text{ V}$) | `hardware/circle-main/legacy/03_eda_safety.sch` (K1, K2) | Physical separation audit; default unpowered open | **PASS** |
| **REQ-10** | Passive Bilateral Current Limiting | Symmetrical $200\text{ k}\Omega$ loop; $I_{fault} \le 27.58\text{ }\mu\text{A} \ll 50\text{ }\mu\text{A}$ | `hardware/circle-main/legacy/03_eda_safety.sch` ($4\times 49.9\text{ k}\Omega$) | Closed-form Ohm's law proof at $V_{SYS\_max} = 5.50\text{ V}$ | **PASS** |
| **REQ-11** | Pure Hardware Interlock Chain | Pure 74LVC hardware logic; firmware cannot override | `hardware/circle-main/legacy/03_eda_safety.sch` (U32, U33, U34) | Logic gate netlist inspection & truth table proof | **PASS** |
| **REQ-12** | 4-Bit SDMMC MicroSD Storage | Dedicated 4-bit bus, Card Detect switch, TPS22918 switch | `hardware/circle-main/legacy/05_storage.sch` (J21, Q1, RSD1-6) | 4-bit pin allocation; series damping resistors ($33\text{ }\Omega$) | **PASS** |
| **REQ-13** | 6-Axis Motion Tracking IMU | ICM-42688-P (Dedicated SPI, DRDY interrupt, 400 SPS) | `hardware/circle-main/legacy/04_sensors.sch` (U20, GPIO10-14) | SPI clock/data allocation audit | **PASS** |
| **REQ-14** | Replaceable Optical Daughterboard | MAX30102 + LP5907-1.8 + TXS0102 + AT24CS02 EEPROM | `hardware/circle-ppg/circle-ppg.kicad_sch` & `hardware/circle-ppg/circle-ppg.kicad_pcb` | Keyed JST-GH 9-pin pinout matching mainboard J20 | **PASS** |
| **REQ-15** | Reinforced Laboratory Isolation | ISOW7742 ($5.0\text{ kVrms}$ isolation, $\ge 8.0\text{ mm}$ creepage) | `hardware/circle-main/legacy/06_sync_isolation.sch` & `circle-main.kicad_pcb` | PCB no-copper cutout measurement ($8.0\text{ mm}$) | **PASS** |
| **REQ-16** | Laboratory SYNC IN & OUT | Schmitt trigger buffer (IN) + Open-drain MOSFET (OUT) | `hardware/circle-main/legacy/06_sync_isolation.sch` (U31, Q30, J30, J31) | Input threshold & open-drain pull-up audit | **PASS** |
| **REQ-17** | Haptic Feedback & Evidence Capture | DRV2605L + TLV3201 comparator ($< 40\text{ ns}$ edge detect) | `hardware/circle-main/legacy/07_feedback_expansion.sch` (U40, U41) | Ground shunt current threshold calculation | **PASS** |
| **REQ-18** | System Telemetry & Observability | MCP23017 I2C Expander + SMT Testpoints on all rails | `hardware/circle-main/legacy/08_observability.sch` (U6, TP1-16) | Read-only telemetry architecture audit | **PASS** |
| **REQ-19** | 4-Layer PCB Stackup & DFM | JLC04161H-7628 1.6mm 4-layer; IPC-7351B footprints | `hardware/circle-main/circle-main.kicad_pcb` & `manufacturing-checklist.md` | KiCad 10.0.5 DRC clean execution | **PASS** |
| **REQ-20** | Automated Reproducibility Suite | Reproducible diagram/schematic generator; ERC gate | `tools/verify_release.py` & `hardware/reports/verification-summary.json` | Execution of automated Python/KiCad verification pipeline | **PASS** |
