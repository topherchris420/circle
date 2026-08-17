# CIRCLE Rev B Known Issues, Unresolved Risks, & Hazard Register

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION**

This document records the formal hazard log, known limitations, procedural risks, and regulatory boundaries for the CIRCLE Rev B platform.

---

## 1. Known Design Limitations & Review Boundary

| Limitation ID | Subsystem / Area | Limitation Description | Design Impact | Mitigation / Recommended Resolution |
|---|---|---|---|---|
| **LIM-01** | Legacy `.sch` Intermediate Export | KiCad 10 CLI parses, ERC-checks, and exports legacy `.sch` files natively, but `kicad-cli sch upgrade` requires GUI import for native graphical layout conversion. | Legacy review sheets remain the deterministic build intermediate. | Upstream KiCad 10 automation tools parse netlists and ERC without loss of precision. |
| **LIM-02** | Non-Isolated USB-C Port | USB-C VBUS and ground are referenced to `BAT_HUMAN_GND`. Direct PC connection while electrodes are attached is prohibited. | Hardware interlocks asynchronously disconnect electrodes on USB insertion. | Enforced by pure hardware interlock chain; procedural rules forbid modifying USB cable to defeat VBUS detection. |
| **LIM-03** | Secondary Optical Accelerometer | ST LIS2DW12 footprint on `circle-ppg` daughterboard is marked `DNI` (Do Not Install) in Rev B base build. | Optical motion artifact compensation relies on mainboard ICM-42688-P. | Can be populated in Rev C after daughterboard cable motion transfer function characterization. |

---

## 2. Formal Hazard Analysis & Risk Register

| Hazard ID | Hazard Scenario | Potential Consequence | Risk Level (Pre-Mitigation) | Designed Hardware Mitigation | Residual Risk Level | Procedural / Operational Constraint |
|---|---|---|:---:|---|:---:|---|
| **HAZ-01** | Arbitrary grounded oscilloscope probe clipped to `BAT_HUMAN_GND` testpoint while electrodes are on subject | Creates non-isolated path to earth ground through scope mains earth | **HIGH** | Testpoints are physically isolated from electrode circuit by PhotoMOS relays when interlock opens. | **LOW (Procedural)** | **MANDATORY**: Never connect earthed test equipment, logic analyzers, or scopes to `BAT_HUMAN` domain during human testing. Use battery-powered DMMs or isolated differential probes. |
| **HAZ-02** | Battery over-discharge or reverse connection at connector J2 | Battery degradation, swelling, or thermal runaway | **MEDIUM** | Keyed JST-PH 3-pin connector prevents physical reverse mating; BQ24074 incorporates reverse-current blocking; TPS3700 cuts off at 3.20V. | **NEGLIGIBLE** | Use only authenticated LiPo cells with integrated overcurrent/undervoltage protection modules (PCM). |
| **HAZ-03** | Dielectric breakdown across laboratory isolation barrier (> 5 kV surge) | High voltage from laboratory equipment enters subject domain | **HIGH** | TI ISOW7742 provides 5.0 kVrms reinforced dielectric rating; PCB features an 8.0 mm physical no-copper cutout slot. | **NEGLIGIBLE** | Perform 100% production hipot test (1000 VDC for 2s) across barrier prior to laboratory use. |
| **HAZ-04** | MicroSD card write stall causing sensor FIFO overflow | Loss of critical physiological time-series data | **MEDIUM** | 8MB Octal PSRAM absorbs continuous write stalls up to 60 seconds; binary frame format records exact gap sequence numbers. | **NEGLIGIBLE** | Format cards with exFAT/FAT32 using 32KB cluster alignment before recording sessions. |

---

## 3. Regulatory & Certification Status Matrix

| Regulatory Standard / Scope | Evaluation Status | Formal Compliance Claim | Required Steps for Commercial / Medical Transition |
|---|:---:|:---:|---|
| **IEC 60601-1 (Medical Electrical Safety)** | **NON-CERTIFIED** | **NONE** (Research & Bench Prototyping Only) | Formal NRTL laboratory evaluation (UL/TUV), creepage/clearance under pollution degree 2, formal risk management file (ISO 14971). |
| **IEC 60601-1-2 (Medical EMC)** | **NON-CERTIFIED** | **NONE** | Radiated/conducted emissions and immunity testing in certified RF chamber. |
| **FCC Part 15B / ICES-003 (Unintentional Radiators)**| **NON-CERTIFIED** | **NONE** | Class B digital device verification in accredited anechoic chamber. |
| **FCC Part 15C / RED (Intentional Radiators)** | **PRE-CERTIFIED MODULE** | Module FCC ID: 2AC7Z-ESPS3WROOM1 | Full final product co-location RF test and integration certification. |
| **ISO 10993-1 (Biocompatibility)** | **NON-CERTIFIED** | **NONE** | Cytotoxicity, sensitization, and intracutaneous irritation testing on final patient-contact electrode/sensor enclosures. |
