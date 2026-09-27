# CIRCLE Rev B Requirements-to-Evidence Verification Matrix

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION**

This matrix links each requirement to the design artifact where it is expressed and the kind of evidence that currently exists. It previously marked every row **PASS**; that overstated the evidence. No row has been verified on hardware.

Evidence classes used below:

| Class | Meaning |
|---|---|
| `DESIGN_INTENT` | The schematic or manifest expresses the requirement. Nothing has been built. |
| `DATASHEET_VALUE` | The number is a component rating, not an assembled-system measurement. |
| `CALCULATION` | A closed-form calculation exists; it has not been independently reviewed. |
| `AUTOMATED_CHECK` | A repository check passes (ERC, DRC with allowlist, schema, generation). |
| `SIMULATION` | Exercised by the physiology twin against assumed hardware behavior. |
| `NOT_TESTED` | Requires firmware, hardware, or measurement that does not exist. |

---

## 1. Requirements Verification Matrix

| Req ID | Requirement Statement | Target Performance Metric | Evidence Artifact / Document Location | Evidence that exists | Evidence class |
|---|---|---|---|---|:---:|
| **REQ-01** | Compute Engine & Memory Capacity | ESP32-S3 (240 MHz, 16MB Flash, 8MB PSRAM) | `hardware/reports/bom/circle-main-revB-sourced.csv` (U1) | Datasheet cross-probe; memory test planned | `DATASHEET_VALUE`; memory test `NOT_TESTED` (no firmware) |
| **REQ-02** | USB-C 5V UFP Sink & ESD Protection | Dual 5.1k CC pulldowns; 500mA PTC fuse; ESD protection | `hardware/circle-main/legacy/01_compute_usb.sch` (J1, R1, R2, F1, D1) | Schematic netlist inspection; Ohm's law CC verification | `DESIGN_INTENT` + `CALCULATION` |
| **REQ-03** | Pre-Charger USB VBUS Detection | $< 10\text{ }\mu\text{s}$ async disconnect upon USB mate | `hardware/circle-main/legacy/01_compute_usb.sch` & `docs/safety-and-fault-analysis.md` | Circuit delay analysis ($t_{pd} < 200\text{ ns}$) | `CALCULATION`; `NOT_TESTED` |
| **REQ-04** | Battery Charging & DPPM Control | BQ24074 ($I_{CHG} = 500\text{ mA}$, NTC thermistor $0-45^\circ\text{C}$) | `hardware/circle-main/legacy/02_power.sch` (U2, R_SET, R_ILIM) | Resistor formula calculation: $R_{SET} = 890 / 0.50\text{ A} = 1.78\text{ k}\Omega$ | `CALCULATION` |
| **REQ-05** | Primary 3.3V Digital Buck-Boost | TPS63070 ($2.0-16.0\text{ V}$ input, 2.0A output, $> 85\%$ eff) | `hardware/circle-main/legacy/02_power.sch` & `docs/power-budget-analysis.md` | Efficiency derivation; Coilcraft XFL4020 $I_{sat} = 5.4\text{ A}$ margin | `DATASHEET_VALUE` + `CALCULATION` |
| **REQ-06** | Ultra-Low-Noise Analog Power Supply | TPS7A2033 ($6.5\text{ }\mu\text{V}_\text{RMS}$ noise, 85 dB PSRR) | `hardware/circle-main/legacy/02_power.sch` (U7) | Datasheet noise curve; enable tied to `EDA_PREPARE` | `DATASHEET_VALUE` |
| **REQ-07** | Electrodermal Activity 24-bit ADC | ADS1220 (Dedicated SPI, DRDY interrupt, low noise) | `hardware/circle-main/legacy/03_eda_safety.sch` (U10, GPIO39-42, GPIO47) | Pin map audit; SPI timing verification | `DESIGN_INTENT`; timing modeled in `SIMULATION` |
| **REQ-08** | Precision Voltage Ref & Buffer | REF5020 (2.048V, 3 ppm/°C) + OPA2192 ($V_{OS} < 5\text{ }\mu\text{V}$) | `hardware/circle-main/legacy/03_eda_safety.sch` (U11, U12) | AFE excitation calculation ($0.500\text{ V} \pm 1.0\%$) | `DATASHEET_VALUE` + `CALCULATION` |
| **REQ-09** | Fail-Open EDA Output Relays | Dual normally-open PhotoMOS (AQY212GS, $V_{OFF} = 60\text{ V}$) | `hardware/circle-main/legacy/03_eda_safety.sch` (K1, K2) | Physical separation audit; default unpowered open | `DESIGN_INTENT` + `DATASHEET_VALUE` |
| **REQ-10** | Passive Bilateral Current Limiting | Symmetrical $200\text{ k}\Omega$ loop; $I_{fault} \le 27.58\text{ }\mu\text{A} \ll 50\text{ }\mu\text{A}$ | `hardware/circle-main/legacy/03_eda_safety.sch` ($4\times 49.9\text{ k}\Omega$) | Closed-form Ohm's law proof at $V_{SYS\_max} = 5.50\text{ V}$ | `CALCULATION` (gate EDA_LIMIT_NETWORK open) |
| **REQ-11** | Pure Hardware Interlock Chain | Pure 74LVC hardware logic; firmware cannot override | `hardware/circle-main/legacy/03_eda_safety.sch` (U32, U33, U34) | Logic gate netlist inspection & truth table proof | `DESIGN_INTENT` |
| **REQ-12** | 4-Bit SDMMC MicroSD Storage | Dedicated 4-bit bus, Card Detect switch, TPS22918 switch | `hardware/circle-main/legacy/05_storage.sch` (J21, Q1, RSD1-6) | 4-bit pin allocation; series damping resistors ($33\text{ }\Omega$) | `DESIGN_INTENT` |
| **REQ-13** | 6-Axis Motion Tracking IMU | ICM-42688-P (Dedicated SPI, DRDY interrupt, 400 SPS) | `hardware/circle-main/legacy/04_sensors.sch` (U20, GPIO10-14) | SPI clock/data allocation audit | `DESIGN_INTENT`; modeled in `SIMULATION` |
| **REQ-14** | Replaceable Optical Daughterboard | MAX30102 + LP5907-1.8 + TXS0102 + AT24CS02 EEPROM | `hardware/circle-ppg/circle-ppg.kicad_sch` & `hardware/circle-ppg/circle-ppg.kicad_pcb` | Keyed JST-GH 9-pin pinout matching mainboard J20 | `DESIGN_INTENT` |
| **REQ-15** | Reinforced Laboratory Isolation | ISOW7742 ($5.0\text{ kVrms}$ isolation, $\ge 8.0\text{ mm}$ creepage) | `hardware/circle-main/legacy/06_sync_isolation.sch` & `circle-main.kicad_pcb` | PCB no-copper cutout measurement ($8.0\text{ mm}$) | `DATASHEET_VALUE` (component rating) + `DESIGN_INTENT` (slot); barrier `NOT_TESTED` |
| **REQ-16** | Laboratory SYNC IN & OUT | Schmitt trigger buffer (IN) + Open-drain MOSFET (OUT) | `hardware/circle-main/legacy/06_sync_isolation.sch` (U31, Q30, J30, J31) | Input threshold & open-drain pull-up audit | `DESIGN_INTENT` |
| **REQ-17** | Haptic Feedback & Evidence Capture | DRV2605L + TLV3201 comparator ($< 40\text{ ns}$ edge detect) | `hardware/circle-main/legacy/07_feedback_expansion.sch` (U40, U41) | Ground shunt current threshold calculation | `DESIGN_INTENT`; IMU observation of actuation shown in `SIMULATION` only |
| **REQ-18** | System Telemetry & Observability | MCP23017 I2C Expander + SMT Testpoints on all rails | `hardware/circle-main/legacy/08_observability.sch` (U6, TP1-16) | Read-only telemetry architecture audit | `DESIGN_INTENT` |
| **REQ-19** | 4-Layer PCB Stackup & DFM | JLC04161H-7628 1.6mm 4-layer; IPC-7351B footprints | `hardware/circle-main/circle-main.kicad_pcb` & `manufacturing-checklist.md` | KiCad 10.0.5 DRC: zero rule violations; unrouted nets allowlisted | `AUTOMATED_CHECK` with open routing allowlist (412 unconnected items; boards not routed) |
| **REQ-20** | Automated Reproducibility Suite | Reproducible diagram/schematic generator; ERC gate | `tools/verify_release.py` (scoped summary) | Execution of automated Python/KiCad verification pipeline | `AUTOMATED_CHECK` (software scopes; fresh ERC/DRC requires pinned KiCad) |
