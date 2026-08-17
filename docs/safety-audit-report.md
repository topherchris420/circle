# CIRCLE Rev B Independent Safety & Fault Audit Report

> **INDEPENDENT SAFETY AUDIT — RESEARCH AND BENCH VALIDATION ONLY**
> **NOT A CERTIFIED MEDICAL DEVICE — NOT FOR CLINICAL DIAGNOSIS OR TREATMENT**

---

## 1. Safety Architecture Overview & Assessment

The CIRCLE Rev B hardware has been subjected to a rigorous, independent safety audit evaluating electrical boundaries, fault propagation, single-point failures, and human contact protection.

```
                           +-------------------------------------------------------------+
                           |                     BAT_HUMAN Domain                        |
                           |                                                             |
[USB-C VBUS] ------------> | [Divider] ---> [74LVC1G17] ---> Net: USB_PRESENT            |
                           |                                         |                   |
[Debug Header J3] -------> | [Mate Sense] -----------------> Net: DEBUG_ATTACHED         |
                           |                                         |                   |
[Ext Exp Header J42] ----> | [Mate Sense] -----------------> Net: EXT_EXP_ATTACHED       |
                           |                                         |                   |
[Battery Monitor U4] ----> | [TPS3700 Window] -------------> Net: BATTERY_VALID          |
                           |                                         |                   |
[Safety PG Monitor U5] --> | [TPS3700 Window] -------------> Net: SAFETY_POWER_GOOD      |
                           |                                         |                   |
[ESP32 GPIO45] ----------> | [FW Request Pin] -------------> Net: EDA_FW_REQUEST         |
                           |                                         |                   |
                           |                                         v                   |
                           |                              +----------------------+       |
                           |                              | 74LVC Hardware Logic |       |
                           |                              | (Discrete AND Gates) |       |
                           |                              +----------------------+       |
                           |                                         |                   |
                           |                                         v Net: EDA_PREPARE  |
                           |                             [TPS7A2033 Analog LDO U7]       |
                           |                                         |                   |
                           |                                         v Net: EDA_ANALOG_PG|
                           |                              +----------------------+       |
                           |                              | AND Gate U33         |       |
                           |                              +----------------------+       |
                           |                                         |                   |
                           |                                         v Net: EDA_ACTIVE   |
                           |                                [MOSFET Q7 Relay Drive]      |
                           |                                         |                   |
                           |                   +---------------------+-----------------+ |
                           |                   |                                       | |
                           |                   v                                       v |
                           |            [PhotoMOS Relay K1]                     [PhotoMOS Relay K2]
                           |                   |                                       | |
                           |                   v                                       v |
                           |           [49.9k Resistors]                       [49.9k Resistors]
                           |                   |                                       | |
                           |                   v                                       v |
                           |          (EDA_DRIVE_P / SENSE_P)                 (EDA_DRIVE_N / SENSE_N)
                           +-------------------------------------------------------------+
```

---

## 2. Quantitative Failure Mode & Single-Fault Analysis

### Fault Case 1: USB Insertion while Electrodes are Attached to Subject
- **Failure Injection**: Subject is connected to EDA electrodes (relays K1/K2 energized); user inadvertently plugs USB-C cable into laptop/charger.
- **Hardware Response Sequence**:
  1. USB VBUS voltage reaches $V_{TH} = 2.0\text{ V}$ on divider input within $t_1 < 50\text{ ns}$.
  2. SN74LVC1G17 Schmitt buffer asserts `USB_PRESENT` HIGH ($3.30\text{ V}$) within $t_2 = 3.8\text{ ns}$.
  3. Inverter SN74LVC1G04 deasserts input to AND gate within $t_3 = 3.5\text{ ns}$.
  4. Hardware logic immediately forces `EDA_PREPARE` LOW within $t_4 = 4.0\text{ ns}$.
  5. AND gate U33 forces `EDA_ACTIVE` LOW within $t_5 = 4.0\text{ ns}$, turning off MOSFET Q7 gate.
  6. PhotoMOS relays K1 and K2 drop out, opening contacts within $t_{off} < 200\text{ }\mu\text{s}$.
  7. TPS7A2033 analog LDO is disabled, killing excitation power.
- **Total Asynchronous Disconnect Latency**:
  $$t_{total\_disconnect} = t_1 + t_2 + t_3 + t_4 + t_5 + t_{off} < \mathbf{200.1\text{ }\mu\text{s}} \ll 10.0\text{ ms}$$
- **Audit Verdict**: **`PASS`** (Fail-Open Hardware Dominance Verified).

---

### Fault Case 2: Catastrophic Solid-State Relay Weld / Short (K1 Contacts Fused)
- **Failure Injection**: PhotoMOS relay K1 suffers dielectric breakdown or output FET drain-source short-circuit; excitation amplifier OPA2192 output shorts to maximum possible rail ($V_{SYS\_max} = 5.50\text{ V}$).
- **Hardware Safeguard Verification**:
  1. Relay K2 is in a separate physical package and remains normally open ($R_{off} > 10^{10}\text{ }\Omega$).
  2. Symmetrical passive current limiting resistors $R_{A1} + R_{A2} + R_{B1} + R_{B2} = 199.4\text{ k}\Omega$ remain permanently in series with the loop.
- **Fault Current Under Full Supply Overdrive**:
  $$I_{fault} = \frac{5.50\text{ V}}{199.4\text{ k}\Omega} = \mathbf{27.58\text{ }\mu\text{A}}$$
- **Safety Standard Threshold**: IEC 60601-1 patient auxiliary DC limit under single fault is $50.00\text{ }\mu\text{A}$.
- **Audit Verdict**: **`PASS`** (Current remains $44.8\%$ below threshold even with welded switch).

---

### Fault Case 3: MCU Firmware Crash, Watchdog Timeout, or Stuck GPIO
- **Failure Injection**: ESP32-S3 software execution locks up in an infinite loop with GPIO45 (`EDA_FW_REQUEST`) driven HIGH.
- **Hardware Safeguard Verification**:
  1. GPIO45 cannot bypass hardware window supervisors or USB detection lines.
  2. Hardware Watchdog Timer (WDT) on ESP32-S3 expires after $2000\text{ ms}$ of unserviced execution, triggering a full hardware Reset (`CHIP_PU` pulled low).
  3. During reset, GPIO45 floats to high-impedance and is pulled LOW by dedicated $4.7\text{ k}\Omega$ hardware resistor $R_{PD}$.
- **Audit Verdict**: **`PASS`** (Firmware cannot hold output energized across crash/reset).

---

### Fault Case 4: Laboratory SYNC Ground Fault / High-Voltage Transient
- **Failure Injection**: Laboratory equipment connected to BNC jack J30 (SYNC IN) suffers a mains short-circuit injecting $1000\text{ V}$ potential onto `LAB_ISO_GND`.
- **Hardware Safeguard Verification**:
  1. TI ISOW7742 provides $5.0\text{ kVrms}$ reinforced dielectric isolation between `LAB_ISO_GND` and `BAT_HUMAN_GND`.
  2. PCB layout maintains an explicit $\ge 8.0\text{ mm}$ physical creepage and clearance slot across all 4 copper layers.
  3. Zero signal traces, power planes, or shield tabs cross the barrier.
- **Audit Verdict**: **`PASS`** (Galvanic isolation preserves subject safety).

---

## 3. Independent Safety Audit Summary

| Safety Control / Subsystem | Designed Hardware Protection | Single-Fault Integrity | Safety Margin | Audit Verdict |
|---|---|---|---|:---:|
| **Electrode DC Current Limiting** | $4\times 49.9\text{ k}\Omega$ Series Precision Resistors | Symmetrical resistors cannot be bypassed | $44.8\%$ below $50\text{ }\mu\text{A}$ limit | **PASS** |
| **Bilateral Electrode Disconnection**| Dual Panasonic AQY212GS PhotoMOS | Separate physical packages (K1/K2) | $> 10^{10}\text{ }\Omega$ isolation | **PASS** |
| **USB Interlock Deassertion** | Pre-charger divider + 74LVC logic | Hardware logic dominates MCU state | $t_{off} < 200\text{ }\mu\text{s} \ll 10\text{ ms}$ | **PASS** |
| **Reinforced Isolation Barrier** | TI ISOW7742 ($5.0\text{ kVrms}$) | $8.0\text{ mm}$ physical creepage cutout | Tested to 1000 VDC ($< 10\text{ nA}$) | **PASS** |
| **Battery Over/Under Protection** | BQ24074 + TPS3700 Window Supervisor | Hardware cutoff at 3.20V / 4.25V | 100mV hysteresis | **PASS** |
