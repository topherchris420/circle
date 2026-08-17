# CIRCLE Rev B Open Risks, Assumptions, & Certification Boundaries

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION**

This document records the operational assumptions, residual risks, and non-certified boundaries for CIRCLE Rev B.

---

## 1. Operating Assumptions

1. **Research & Bench Validation Context**:
   - The device is intended solely for laboratory, benchtop, and controlled research environments by qualified engineering and scientific personnel.
   - The device is powered exclusively by a single-cell LiPo battery with internal protection circuitry (PCM) or through the on-board BQ24074 charger when not connected to human subjects.
2. **Skin Contact & Electrode Interfaces**:
   - EDA measurements use standard non-invasive, pre-gelled Ag/AgCl surface electrodes or dry conductive polymer electrodes on intact skin.
   - PPG optical sensing uses non-invasive reflective optical contact on intact skin (finger, wrist, or forehead).
3. **Environmental Conditions**:
   - Operating temperature: $15^\circ\text{C}$ to $35^\circ\text{C}$.
   - Relative humidity: $20\%$ to $80\%$ non-condensing.
   - Atmospheric pressure: $86\text{ kPa}$ to $106\text{ kPa}$ (standard sea-level to 1500m altitude).

---

## 2. Open Risks & Mitigation Analysis

| Risk ID | Hazard / Risk Description | Severity | Likelihood | Designed Hardware Mitigation | Residual Protocol / Procedural Requirement |
|---|---|:---:|:---:|---|---|
| **RSK-01** | Arbitrary Grounded Oscilloscope Probe attached to Battery Ground during EDA operation | Critical | Medium | Hardware cannot sense a grounded probe clipped directly to a testpoint or ground tab. | **Mandatory Protocol Warning**: Never attach non-isolated test equipment, ground leads, or logic analyzer clips to `BAT_HUMAN` domain while electrodes are attached to a person. |
| **RSK-02** | Defective / Counterfeit LiPo Cell without Internal Protection Module | High | Low | BQ24074 charger regulates charge voltage ($4.20\text{ V}$) and monitors NTC thermistor ($0^\circ\text{C}-45^\circ\text{C}$); TPS3700 cuts off at $3.20\text{ V}$. | Sourcing Requirement: Procure only authenticated battery cells with integrated overcurrent/undervoltage PCM modules (e.g. PKCELL, Adafruit). |
| **RSK-03** | Inadvertent Use of Non-Locking / Damaged Optical Daughterboard Cable | Moderate | Medium | Keyed JST-GH locking connector ensures correct pin polarity; $33\text{ }\Omega$ series resistors protect I2C drivers from cable capacitive loading. | Inspect cable latching before testing. |
| **RSK-04** | MicroSD Card Wear / Corruption after Extended High-Throughput Logging | Minor | Medium | Circular PSRAM buffer absorbs stalls; CRC-32C frame checks identify corrupted blocks without losing session continuity. | Use high-endurance Class 10 / V30 cards (e.g. SanDisk Extreme, Kingston Canvas). |

---

## 3. Formal Certification Boundaries

> [!WARNING]
> **Formal Regulatory Non-Compliance Notice**:
> CIRCLE Rev B has **not** undergone formal third-party laboratory certification for the following standards:
> 1. **Medical Electrical Equipment Safety (IEC 60601-1 / EN 60601-1)**: While Rev B implements patient leakage current limiting ($< 27.5\text{ }\mu\text{A}$), fail-open relays, and $5\text{ kVrms}$ galvanic isolation, it is not certified as a Type BF or Type CF medical device.
> 2. **Electromagnetic Compatibility (FCC Part 15B / CISPR 32 / EN 55032)**: Radiated and conducted emissions tests have not been executed in an anechoic chamber.
> 3. **Radio Equipment Directive (RED / FCC Part 15C)**: Wi-Fi and Bluetooth wireless features utilize the pre-certified Espressif ESP32-S3 module (FCC ID: 2AC7Z-ESPS3WROOM1), but full end-product intentional radiator testing is not certified.
> 4. **Biocompatibility (ISO 10993-1)**: Electrode contacts and optical sensor window materials must be independently evaluated if custom skin-contact enclosures are fabricated.
