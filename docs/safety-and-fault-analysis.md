# CIRCLE Rev B Safety Engineering & Fault-Oriented Analysis

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION**

This document provides a comprehensive safety analysis, hardware interlock verification, failure modes and effects analysis (FMEA), single-fault tolerance proofs, and medical device boundary definitions for CIRCLE Rev B.

---

## 1. Safety Philosophy & Engineering Constraints

CIRCLE Rev B is an experimental research instrument. It is designed around the following fundamental safety axioms:
1. **Hardware-Enforced Interlocks**: Safety must not depend solely on firmware or software execution. Firmware cannot bypass hardware interlock gates.
2. **Fail-Open Default State**: All human-connected electrode circuits are normally disconnected by physical switching elements (relays K1 and K2) that remain open in unpowered, brownout, reset, or fault conditions.
3. **Passive Current Limiting**: Symmetrical, precision series resistors remain permanently in the loop to restrict maximum possible current below safe limits even under a catastrophic switch-weld failure.
4. **Reinforced Galvanic Isolation**: All connections to external laboratory equipment (SYNC IN/OUT) must be galvanically isolated with $\ge 8.0\text{ mm}$ clearance and creepage, maintaining dielectric integrity up to $5.0\text{ kVrms}$.
5. **Battery-Only Operation for Human Contact**: Active EDA measurement is physically prohibited whenever USB or any non-isolated external cable is connected.

---

## 2. Hardware Interlock Architecture & Truth Table

### 2.1 Logic Equations
$$\text{EDA\_PREPARE} = \text{EDA\_FW\_REQUEST} \land \text{BATTERY\_VALID} \land \overline{\text{USB\_PRESENT}} \land \overline{\text{DEBUG\_ATTACHED}} \land \overline{\text{EXTERNAL\_EXPANSION\_ATTACHED}} \land \text{SAFETY\_POWER\_GOOD}$$
$$\text{EDA\_ACTIVE} = \text{EDA\_PREPARE} \land \text{EDA\_ANALOG\_GOOD}$$

### 2.2 Complete Interlock Truth Table

| State / Condition | `EDA_FW_REQ` (GPIO45) | `BAT_VALID` (3.20V–4.25V) | `USB_PRESENT` (VBUS > 4.4V) | `DEBUG_ATT` (Header J3) | `EXT_EXP_ATT` (Header J42) | `SAFETY_PG` (3.15V–3.45V) | `ANALOG_PG` (+3V3_EDA_A) | `EDA_PREPARE` | `EDA_ACTIVE` | Relays K1/K2 | Analog Rail Power |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Normal Powered Off** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** | **0** | **OPEN** | **OFF** |
| **Booting / Initializing** | 0 | 1 | 0 | 0 | 0 | 1 | 0 | **0** | **0** | **OPEN** | **OFF** |
| **Valid EDA Request** | 1 | 1 | 0 | 0 | 0 | 1 | 1 | **1** | **1** | **CLOSED**| **ON** |
| **USB Cable Inserted** | 1 | 1 | **1** | 0 | 0 | 1 | 1 | **0** | **0** | **OPEN** | **OFF** |
| **Debug Cable Inserted**| 1 | 1 | 0 | **1** | 0 | 1 | 1 | **0** | **0** | **OPEN** | **OFF** |
| **Expansion Inserted** | 1 | 1 | 0 | 0 | **1** | 1 | 1 | **0** | **0** | **OPEN** | **OFF** |
| **Battery Undervoltage**| 1 | **0** | 0 | 0 | 0 | 1 | 1 | **0** | **0** | **OPEN** | **OFF** |
| **Safety Rail Glitch** | 1 | 1 | 0 | 0 | 0 | **0** | 1 | **0** | **0** | **OPEN** | **OFF** |
| **Analog Rail Fault** | 1 | 1 | 0 | 0 | 0 | 1 | **0** | **1** | **0** | **OPEN** | **ON (Unqual)**|
| **Firmware Crash / Loop**| **X** | 1 | **1** | 0 | 0 | 1 | 1 | **0** | **0** | **OPEN** | **OFF** |

---

## 3. Mathematical Analysis of Electrode Current & Voltage Limits

### 3.1 Normal Operating Output Limits
- **Excitation Voltage**: $V_{excite} = 0.500\text{ V}$ DC (derived from REF5020 2.048V precision reference buffered by OPA2192).
- **Normal Skin Resistance Range**: $R_{skin} = 10\text{ k}\Omega$ to $10\text{ M}\Omega$ ($0.1\text{ }\mu\text{S} - 100\text{ }\mu\text{S}$).
- **Normal Operating Current**:
  $$I_{normal} = \frac{V_{excite}}{R_{loop} + R_{skin}} = \frac{0.50\text{ V}}{200\text{ k}\Omega + 10\text{ k}\Omega} \approx 2.38\text{ }\mu\text{A}$$
  (Well within comfortable, imperceptible physiological limits).

### 3.2 Worst-Case Single-Fault Current Analysis
- **Scenario**: Primary relay K1 suffers a welded contact short-circuit; excitation buffer op-amp fails with output saturated to maximum possible system voltage ($V_{SYS\_max} = 5.50\text{ V}$); skin impedance drops to $R_{skin} = 0\text{ }\Omega$ (direct metal contact).
- **Loop Circuit**: Symmetrical passive resistors $R_{\text{EDA\_A1}} + R_{\text{EDA\_A2}} + R_{\text{EDA\_B1}} + R_{\text{EDA\_B2}}$ remain permanently in the series circuit.
- **Series Resistance**:
  $$R_{total\_min} = 4 \times (49.9\text{ k}\Omega \times (1 - 0.001)) = 4 \times 49.85\text{ k}\Omega = 199.4\text{ k}\Omega$$
- **Maximum Possible Fault Current**:
  $$I_{fault\_max} = \frac{V_{SYS\_max}}{R_{total\_min}} = \frac{5.50\text{ V}}{199.4\text{ k}\Omega} = \mathbf{27.58\text{ }\mu\text{A}}$$

> [!IMPORTANT]
> **Safety Margin Verification**:
> The international general limit for patient auxiliary DC current under single fault conditions is $50.0\text{ }\mu\text{A}$ (IEC 60601-1 / ANSI AAMI ES60601-1).
> The CIRCLE Rev B worst-case fault current of **$27.58\text{ }\mu\text{A}$** provides a **$44.8\%$ safety margin below the $50.0\text{ }\mu\text{A}$ threshold**, calculated under full component tolerances and extreme supply overdrive.

---

## 4. Failure Modes and Effects Analysis (FMEA)

| Subsystem / Component | Failure Mode | Severity | Occurrence | Detection Method | Hardware / System Response | Compensating Safety Action |
|---|---|:---:|:---:|---|---|---|
| **K1 PhotoMOS Relay** | Contacts short-circuit / weld | Moderate | Low | ADS1220 baseline self-test | K2 remains open ($> 10^{10}\text{ }\Omega$); passive limiters restrict current to $< 27.5\text{ }\mu\text{A}$ | Bilateral dual-relay architecture |
| **K2 PhotoMOS Relay** | Contacts short-circuit / weld | Moderate | Low | ADS1220 baseline self-test | K1 remains open ($> 10^{10}\text{ }\Omega$); passive limiters restrict current to $< 27.5\text{ }\mu\text{A}$ | Bilateral dual-relay architecture |
| **USB VBUS Sense (R1/R2)** | Resistor open / drift | Critical | Extremely Low | Periodic diagnostic compare against charger state | If divider opens, charger EN line drops; BQ24074 status pin alerts MCP23017 | Redundant USB detection via BQ24074 PGOOD |
| **TPS3700 Supervisor** | Output open / floating | Critical | Low | Open-drain pull-up topology | Inverted logic ensures floating line deasserts `SAFETY_POWER_GOOD` fail-safe | Active-low fail-safe logic |
| **ESP32-S3 Firmware** | Firmware crash / lockup | High | Medium | Hardware watchdog timer (WDT) | WDT triggers MCU reset; GPIO45 pulled down by $4.7\text{ k}\Omega$ hardware resistor | Automatic return to fail-open state |
| **LiPo Battery Pack** | Over-discharge ($< 2.8\text{ V}$) | Moderate | Medium | TPS3700 `BATTERY_VALID` comparator | Trips at 3.20V; BQ24074 internal UVLO isolates pack at 2.80V | Multi-tier hardware undervoltage protection |
| **ISOW7742 Isolator** | Dielectric breakdown ($> 5\text{ kV}$) | Catastrophic | Extremely Low | Hipot testing prior to deployment | Barrier layout maintains $\ge 8.0\text{ mm}$ physical creepage/clearance | Physical no-copper slot across all 4 PCB layers |
| **MicroSD Card** | Card removed during write | Minor | Medium | Hardware Card Detect switch | Flush buffers to PSRAM; emit GAP record with sequence range | Resilient append-only binary frame format |

---

## 5. Medical Device Boundary & Classification Disclaimer

> [!CAUTION]
> **Research Instrument Boundary**:
> CIRCLE Rev B is designed and fabricated exclusively for engineering benchmarking, physiological signal research, and human-in-the-loop algorithmic testing in controlled laboratory settings.
> - **NOT A MEDICAL DEVICE**: It has not been submitted to, cleared by, or approved by the US FDA, European Notified Bodies, or any medical regulatory authority.
> - **NO CLINICAL CLAIMS**: It must never be used for medical diagnosis, clinical treatment, life-support monitoring, or surgical guidance.
> - **HUMAN TESTING PRECAUTIONS**: Any research involving human subjects must adhere to Institutional Review Board (IRB) approved protocols, utilizing non-invasive surface electrodes with intact skin only.
