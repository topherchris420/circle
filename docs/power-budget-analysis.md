# CIRCLE Rev B Power Budget & Battery Sizing Analysis

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION**

This document provides a comprehensive rail-by-rail power budget analysis, regulator efficiency modeling, battery capacity sizing, and power-path thermal calculations for CIRCLE Rev B.

---

## 1. System Power Architecture Overview

The CIRCLE Rev B power distribution architecture utilizes a two-tier regulation scheme:
1. **Primary Input & Charging**: BQ24074 linear charger with Dynamic Power Path Management (DPPM) supplying the system rail (`V_SYS`) from either USB-C 5V or a protected 1S LiPo cell.
2. **Primary Digital Regulation**: TPS63070 high-efficiency buck-boost converter producing regulated +3.3V (`+3V3_DIG`) across the full LiPo voltage range (3.0V to 4.2V).
3. **Dedicated Clean Analog Regulation**: TPS7A2033 ultra-low-noise, high-PSRR LDO supplying +3.3V (`+3V3_EDA_A`) to the EDA front-end and ADS1220 ADC.
4. **Switched Peripheral Rails**: Individual TPS22918 high-side load switches for MicroSD, PPG LEDs, Haptics, and Isolation primary.

```
                  +-------------------------------------------------------+
                  |                     USB-C 5V (J1)                     |
                  +-------------------------------------------------------+
                                              |
                                              v
+------------------------+        +-----------------------+
|  LiPo 1S 3.7V Batt J2  | <----> |  TI BQ24074 Charger   |
|  (1000 mAh, NTC Therm) |        |  Power-Path Mgt (U2)  |
+------------------------+        +-----------------------+
                                              |
                                              v V_SYS (3.6V - 4.4V)
                       +----------------------+----------------------+
                       |                                             |
                       v                                             v
        +-----------------------------+               +-----------------------------+
        |  TI TPS63070 Buck-Boost     |               |  TI TPS7A2033 Low-Noise LDO |
        |  Primary Digital Reg (U3)   |               |  EDA Analog Rail (U7)       |
        +-----------------------------+               +-----------------------------+
                       |                                             |
                       v +3V3_DIG (3.30V)                            v +3V3_EDA_A (3.30V)
     +-----------------+-----------------+            +--------------+--------------+
     |                 |                 |            |                             |
     v                 v                 v            v                             v
[ESP32-S3 MCU]   [ICM-42688 IMU]   [MCP23017 Exp]  [ADS1220 ADC]            [REF5020 Reference]
     |                 |                 |                                  [OPA2192 Buffers]
     v (Switched)      v (Switched)      v (Switched)
  [SW_SD]           [SW_PPG_LED]      [SW_HAPTIC]     [SW_ISOLATION]
  (MicroSD)         (MAX30102 LEDs)   (DRV2605L)      (ISOW7742 Prim)
```

---

## 2. Detailed Rail-by-Rail Power Budget

| Subsystem / Functional Block | Power Rail | Voltage ($V$) | Typ Current ($I_{typ}$) | Peak Current ($I_{pk}$) | Typ Power ($P_{typ}$) | Peak Power ($P_{pk}$) | Sizing Margin | Power Hook Reference |
|---|---|---|---|---|---|---|---|---|
| **ESP32-S3 Compute & PSRAM** | `+3V3_DIG` | 3.30 V | 95.0 mA | 380.0 mA | 313.5 mW | 1254.0 mW | +150% (2.0A max) | RSH2 / JP2 |
| **ICM-42688-P 6-Axis IMU** | `+3V3_DIG` | 3.30 V | 1.0 mA | 1.5 mA | 3.3 mW | 5.0 mW | $> +1000\%$ | Digital Rail |
| **MCP23017 Telemetry Expander**| `+3V3_DIG` | 3.30 V | 0.8 mA | 2.0 mA | 2.6 mW | 6.6 mW | $> +1000\%$ | Digital Rail |
| **74LVC Safety Interlock Logic**| `+3V3_DIG` | 3.30 V | 0.5 mA | 1.0 mA | 1.7 mW | 3.3 mW | $> +1000\%$ | Digital Rail |
| **ADS1220 24-bit $\Delta\Sigma$ ADC** | `+3V3_EDA_A` | 3.30 V | 0.45 mA | 0.8 mA | 1.5 mW | 2.6 mW | $> +1000\%$ | RSH3 / JP3 |
| **REF5020 & OPA2192 AFE** | `+3V3_EDA_A` | 3.30 V | 2.8 mA | 6.0 mA | 9.2 mW | 19.8 mW | $> +1000\%$ | RSH3 / JP3 |
| **TPS3700 Window Supervisors** | `+3V3_DIG` | 3.30 V | 0.05 mA | 0.1 mA | 0.17 mW | 0.33 mW | $> +1000\%$ | Digital Rail |
| **MAX30102 Optical Logic** | `PPG_1V8` | 1.80 V | 1.2 mA | 2.5 mA | 2.2 mW | 4.5 mW | $+3900\%$ (100mA) | Local Daughterboard |
| **MAX30102 Optical LEDs** | `+3V3_PPG_LED`| 3.30 V | 15.0 mA | 120.0 mA | 49.5 mW | 396.0 mW | $+1500\%$ (2.0A) | RSH4 / JP4 |
| **MicroSD Card (4-bit SDMMC)**| `+3V3_SD` | 3.30 V | 35.0 mA | 180.0 mA | 115.5 mW | 594.0 mW | $+1000\%$ (2.0A) | RSH5 / JP5 |
| **ISOW7742 Isolated SYNC** | `+3V3_ISO_PRIM`| 3.30 V | 22.0 mA | 85.0 mA | 72.6 mW | 280.5 mW | $+2200\%$ (2.0A) | Primary Isolation Hook |
| **DRV2605L Haptic Actuator** | `+3V3_HAPTIC` | 3.30 V | 0.1 mA (idle) | 220.0 mA (pulse) | 0.33 mW | 726.0 mW | $+800\%$ (2.0A) | RSH6 / JP6 |
| **Total System Aggregate** | `V_SYS` | **3.70 V nom** | **173.9 mA** | **1000.9 mA** | **643.4 mW** | **3703.3 mW** | **+50% on 1.5A Limit**| **RSH1 / JP1** |

---

## 3. Regulator Sizing & Efficiency Calculations

### 3.1 Primary Digital Buck-Boost (TPS63070)
- **Input Voltage Range**: $V_{IN} = 3.00\text{ V}$ to $4.20\text{ V}$ (LiPo battery mode) or $4.40\text{ V}$ ($V_{SYS}$ USB power path).
- **Regulated Output**: $V_{OUT} = 3.30\text{ V}$.
- **Typical Efficiency**: $\eta \approx 88\%$ at nominal load ($150\text{ mA} - 400\text{ mA}$).
- **Nominal Input Current Calculation**:
  $$I_{IN\_typ} = \frac{V_{OUT} \times I_{OUT\_typ}}{\eta \times V_{BAT\_nom}} = \frac{3.30\text{ V} \times 170\text{ mA}}{0.88 \times 3.70\text{ V}} \approx 172.2\text{ mA}$$
- **Peak Input Current Calculation (Worst-Case at $V_{BAT} = 3.0\text{ V}$)**:
  $$I_{IN\_max} = \frac{V_{OUT} \times I_{OUT\_pk}}{\eta \times V_{BAT\_min}} = \frac{3.30\text{ V} \times 990\text{ mA}}{0.82 \times 3.00\text{ V}} \approx 1.328\text{ A}$$
- **Inductor Saturation Verification**:
  Selected Coilcraft XFL4020-102ME:
  - $L = 1.0\text{ }\mu\text{H} \pm 20\%$
  - $I_{sat} = 5.4\text{ A} \gg 1.33\text{ A}$ (Margin $> 300\%$)
  - $I_{rms} = 4.5\text{ A} \gg 1.33\text{ A}$
  - $DCR = 11.2\text{ m}\Omega \implies P_{loss\_DCR} = (0.172\text{ A})^2 \times 0.0112\text{ }\Omega \approx 0.33\text{ mW}$ (negligible).

### 3.2 EDA Analog LDO (TPS7A2033)
- **Input Voltage**: $V_{SYS} = 3.70\text{ V}$ nominal.
- **Output Voltage**: $V_{OUT} = 3.30\text{ V}$.
- **Dropout Voltage**: $V_{DO} = 65\text{ mV}$ at $50\text{ mA}$ load.
- **Minimum Operating Input**: $V_{IN\_min} = 3.30\text{ V} + 0.065\text{ V} = 3.365\text{ V}$.
  - Note: Below $3.365\text{ V}$ battery level, `BATTERY_VALID` supervisor trips at $3.20\text{ V}$, ensuring analog acquisition is only active while the LDO maintains $> 80\text{ dB}$ PSRR.
- **Power Dissipation**:
  $$P_{D\_LDO} = (V_{IN} - V_{OUT}) \times I_{typ} = (3.70\text{ V} - 3.30\text{ V}) \times 3.25\text{ mA} = 1.30\text{ mW}$$
  (SOT-23 thermal rise $< 0.3^\circ\text{C}$).

---

## 4. Battery Autonomy & Operating Profiles

### Profile 1: Full Continuous Research Mode
- **Operating Parameters**: ESP32-S3 active (240 MHz, BLE advertising 10 Hz), ADS1220 EDA @ 64 SPS, MAX30102 PPG @ 200 SPS (red + IR), ICM-42688 IMU @ 400 SPS, continuous 4-bit SDMMC logging, ISOW7742 active, haptic pulse every 60s.
- **Average Current Draw**: $I_{avg} \approx 173.9\text{ mA}$ at $3.7\text{ V}$.
- **Battery Capacity**: $1000\text{ mAh}$ 1S LiPo (PKCELL LP803048).
- **Estimated Runtime**:
  $$\text{Runtime} = \frac{1000\text{ mAh} \times 0.90\text{ (usable capacity)}}{173.9\text{ mA}} \approx \mathbf{5.17\text{ hours}}$$

### Profile 2: Balanced Physiological Logging Mode
- **Operating Parameters**: ESP32-S3 low-power tickless idle between sensor FIFO interrupts, ADS1220 EDA @ 32 SPS, MAX30102 @ 100 SPS (LED duty cycle reduced), ICM-42688 @ 200 SPS, chunked SDMMC burst writes every 10s, haptic off.
- **Average Current Draw**: $I_{avg} \approx 62.5\text{ mA}$ at $3.7\text{ V}$.
- **Estimated Runtime**:
  $$\text{Runtime} = \frac{900\text{ mAh}}{62.5\text{ mA}} \approx \mathbf{14.4\text{ hours}}$$

### Profile 3: Ultra-Low-Power Standby / Sleep Mode
- **Operating Parameters**: ESP32-S3 in Deep Sleep, all load switches opened (`SW_SD`, `SW_PPG_LED`, `SW_HAPTIC`, `SW_ISOLATION` off), TPS7A2033 disabled, ICM-42688 in low-power wake-on-motion mode ($10\text{ }\mu\text{A}$).
- **Average Current Draw**: $I_{sleep} \approx 45\text{ }\mu\text{A}$.
- **Estimated Standby Life**: $> 18,000\text{ hours}$ ($> 2\text{ years}$).

---

## 5. Charger Thermals & Protection

- **Charger IC**: TI BQ24074RGTR (QFN-16 with exposed thermal pad).
- **Fast Charge Current**: $I_{CHG} = 500\text{ mA}$.
- **Worst-Case Charger Power Dissipation**:
  $$P_{D\_CHG} = (V_{USB\_max} - V_{BAT\_min}) \times I_{CHG} = (5.25\text{ V} - 3.20\text{ V}) \times 0.50\text{ A} = 1.025\text{ W}$$
- **Thermal Sizing**:
  - $R_{\theta JA} = 45^\circ\text{C/W}$ with $4\times$ ground plane thermal vias.
  - Temperature Rise: $\Delta T = 1.025\text{ W} \times 45^\circ\text{C/W} = 46.1^\circ\text{C}$.
  - Maximum Die Temperature ($25^\circ\text{C}$ ambient): $T_J = 25^\circ\text{C} + 46.1^\circ\text{C} = 71.1^\circ\text{C} \ll 125^\circ\text{C}$ maximum thermal limit.
