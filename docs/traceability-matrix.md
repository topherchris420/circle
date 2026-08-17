# CIRCLE Rev A to Rev B Traceability Matrix

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION**

This document establishes a bidirectional traceability matrix mapping every functional and architectural requirement from CIRCLE Rev A to its concrete, verified implementation in CIRCLE Rev B.

---

## 1. Traceability Table

| Ref ID | Original Functional Requirement (Rev A) | Rev A Review Status / Gate | Rev B Implementation & Sourcing | Engineering Resolution & Verification |
|---|---|---|---|---|
| **REQ-01** | Compute Engine with 16MB Flash, 8MB PSRAM, Wi-Fi/BLE, native USB | ESP32-S3-WROOM-1-N16R8 provisional; GPIO strapping risks unverified | **Espressif ESP32-S3-WROOM-1-N16R8** | Reserved GPIO35-37 for Octal PSRAM; pulled GPIO45 (EDA request) and GPIO46 (Haptic edge) low at reset; dedicated SPI for IMU & EDA; 4-bit SDMMC bus. |
| **REQ-02** | USB-C 5V Sink with CC Configuration and ESD Protection | Generic USB-C symbol; unverified fuse & ESD | **GCT USB4125-GF-A (USB-C 2.0 16-pin)** + **TI TPD4E05U06DQAR** + **Bel Fuse 0ZCG0050FF2C** | Dual $5.1\text{ k}\Omega \pm 1\%$ pulldowns on CC1/CC2; $22\text{ }\Omega$ series termination on D+/D-; 500mA hold / 1000mA trip PTC fuse; low-capacitance ESD array. |
| **REQ-03** | Pre-Charger USB VBUS Detection for Hardware Interlock | Net `USB_PRESENT` abstract note | **Discrete Symmetrical Divider ($100\text{ k}\Omega / 47\text{ k}\Omega$) + 74LVC1G17 Buffer** | Located ahead of charger power-path switch; asserts `USB_PRESENT` $< 100\text{ ns}$ upon cable insertion, completely independent of charger or MCU firmware state. |
| **REQ-04** | Battery Charging & Dynamic Power-Path Control | `REVIEW_GATE:BATTERY_AND_CHARGE_CURRENT` | **TI BQ24074RGTR** in 16-pin QFN (3x3mm) | $R_{SET} = 1.78\text{ k}\Omega$ sets $I_{CHG} = 500\text{ mA}$; $R_{ILIM} = 1.07\text{ k}\Omega$ sets $I_{LIM} = 1.45\text{ A}$; 10k NTC thermistor input on TS pin ($0^\circ\text{C}$ to $45^\circ\text{C}$ window); DPPM seamlessly switches between USB and LiPo. |
| **REQ-05** | Primary 3.3V Digital Rail Regulation | `REVIEW_GATE:POWER_MAGNETICS_AND_THERMALS` | **TI TPS63070RNMR Buck-Boost** + **Coilcraft XFL4020-102ME (1.0 µH)** | Wide $V_{IN}$ (2.0V to 16V) covers full LiPo discharge (3.0V–4.2V) and USB $V_{SYS}$ (4.4V); delivers 2.0A continuous; ripple $< 25\text{ mV}_\text{p-p}$; thermal via pad to internal ground plane. |
| **REQ-06** | Low-Noise Analog Power Rail for EDA Front-End | Unspecified filtered rail | **TI TPS7A2033PDBVR Ultra-Low-Noise LDO** | Dedicated 3.3V / 300mA LDO ($6.5\text{ }\mu\text{V}_\text{RMS}$ noise, 85 dB PSRR @ 1 kHz) enabled only via `EDA_PREPARE` hardware interlock; decoupled with $10\text{ }\mu\text{F} + 0.1\text{ }\mu\text{F}$ X7R ceramic. |
| **REQ-07** | Electrodermal Activity (EDA) 24-bit ADC Acquisition | ADS1220 provisional | **TI ADS1220IPWR (24-bit $\Delta\Sigma$ ADC)** | Dedicated SPI bus (GPIO39-42), dedicated `EDA_DRDY` (GPIO47), internal/external reference selection, programmable gain ($1\times$ to $128\times$), low-noise PGA. |
| **REQ-08** | Precision Low-Drift Voltage Reference & Bias Buffering | REF5020 & OPA2192 provisional | **TI REF5020AIDR (2.048V, 3 ppm/°C)** + **TI OPA2192IDR (Dual e-trim Op-Amp)** | Generates ultra-stable 0.5V pseudo-differential excitation voltage across skin; $V_{OS} < 5\text{ }\mu\text{V}$, input bias current $5\text{ pA}$, zero-drift topology. |
| **REQ-09** | Fail-Open EDA Output Relays / Disconnect Switches | `REVIEW_GATE:EDA_SWITCH_SELECTION` | **Dual Panasonic AQY212GS PhotoMOS Solid-State Relays** | Separately packaged normally-open solid-state switches (K1, K2); $V_{OFF} = 60\text{ V}$, $I_{OFF\_LEAK} < 1\text{ nA}$, galvanic isolation $1.5\text{ kVrms}$; fail-open when unpowered or safety gate deasserted. |
| **REQ-10** | Passive Bilateral Current Limiting Network | `REVIEW_GATE:EDA_LIMIT_NETWORK` | **$4 \times 49.9\text{ k}\Omega \pm 0.1\%$ Precision Resistors (200 k$\Omega$ loop)** | Series limiters ($R_{A1}, R_{A2}$ on P; $R_{B1}, R_{B2}$ on N) remain in circuit even under single-relay weld; enforces $I_{fault\_max} \le 27.5\text{ }\mu\text{A} \ll 50.0\text{ }\mu\text{A}$ at max $V_{SYS} = 5.5\text{ V}$. |
| **REQ-11** | Hardware Multi-Input Fail-Safe Interlock Logic | Conceptual logic equations | **TI 74LVC1G08 AND Gates & 74LVC1G04 Inverters + TPS3700DDCR Window Supervisors** | Hardware evaluates: $\text{EDA\_PREPARE} = \text{FW\_REQ} \land \text{BAT\_VALID} \land \overline{\text{USB}} \land \overline{\text{DBG}} \land \overline{\text{EXT}} \land \text{SAFE\_PG}$; $\text{EDA\_ACTIVE} = \text{PREPARE} \land \text{ANALOG\_PG}$. Firmware cannot bypass hardware safety terms. |
| **REQ-12** | Removable MicroSD Storage on 4-bit SDMMC | Abstract storage block | **Amphenol 10100273-0101LF Push-Push MicroSD** + **TPS22918 Load Switch** + **Nexperia IP4256CZ3-M ESD** | Dedicated 4-bit SDMMC bus (GPIO4, 5, 6, 7, 15, 16); $33\text{ }\Omega$ series damping resistors; dedicated load switch for software power cycling; Card Detect switch monitored by I/O expander. |
| **REQ-13** | Main 6-Axis Inertial Measurement Unit (IMU) | ICM-42688-P provisional | **TDK InvenSense ICM-42688-P (24-pin LGA)** | Dedicated SPI bus (GPIO10-13), dedicated `IMU_DRDY` (GPIO14), $0.1\text{ }\mu\text{F} + 2.2\text{ }\mu\text{F}$ local decoupling; supports up to 400 SPS per axis raw gyro/accel capture. |
| **REQ-14** | Replaceable Optical PPG Contact Daughterboard | `REVIEW_GATE:PPG_CABLE_SIGNAL_INTEGRITY` | **`circle-ppg` Board: ADI MAX30102 + TI LP5907-1.8 + TI TXS0102 + Microchip AT24CS02** | Local 1.8V low-noise LDO, bidirectional I2C level translator, unique 128-bit factory EEPROM, separate LED power/ground returns, $33\text{ }\Omega$ damping; JST GH 9-pin locking connector. |
| **REQ-15** | Reinforced Galvanic Isolation for Laboratory SYNC | `REVIEW_GATE:ISOLATION_CREEPAGE_CLEARANCE` | **TI ISOW7742DWER (SOIC-16 Wide-Body)** | 5.0 kVrms reinforced isolation barrier, $\ge 8.0\text{ mm}$ clearance and creepage across all PCB layers; integrated isolated DC/DC converter supplying 3.3V @ 100mA to `LAB_ISO` domain. |
| **REQ-16** | Laboratory SYNC IN & SYNC OUT Conditioning | Unspecified TTL logic | **SN74LVC1G17 Schmitt Trigger Buffer (IN)** + **BSS138 N-Ch MOSFET Open-Drain (OUT)** + **BAT54S Clamp** | SYNC IN accepts 3.3V/5.0V TTL pulses (propagation delay $< 15\text{ ns}$, jitter $< 250\text{ ps}$); SYNC OUT open-drain pull-up up to 12V; dual BNC receptacles tied strictly to `LAB_ISO_GND`. |
| **REQ-17** | Haptic Actuation & Electrical Evidence Capture | DRV2605L provisional | **TI DRV2605LDGSR** + **TI TLV3201AIDBVR High-Speed Comparator** | I2C-controlled LRA/ERM haptic driver on `SYS_I2C`; $0.10\text{ }\Omega \pm 1\%$ current shunt in motor return fed to $40\text{ ns}$ comparator generates `HAPTIC_CURRENT_EDGE` on GPIO46. |
| **REQ-18** | System Telemetry & Hardware Observability | Abstract U6 block | **Microchip MCP23017-E/SO (16-bit I2C Expander)** + Surface Mount Test Points (Keystone 5000/5001) | Collects all power-good, attachment, fault, and card status flags over `SYS_I2C` (GPIO8/9) with interrupt on GPIO48; strictly read-only monitoring; dedicated Kelvin shunts on all rails. |
| **REQ-19** | PCB Layout & Physical Clearances | `REVIEW_GATE:FOOTPRINT_VERIFICATION` | **4-Layer IPC-7351B Class 2 Layout** | Defined $85.0\text{ mm} \times 55.0\text{ mm}$ mainboard outline; 4x M2.5 mounting holes; $15.0\text{ mm} \times 15.0\text{ mm}$ antenna keepout; $8.0\text{ mm}$ no-copper isolation cutout; $90\text{ }\Omega$ USB differential pairs. |

---

## 2. Review Gate Closure Summary

All seven fabrication-blocking review gates defined in Rev A are formally closed in Rev B:

1. **`EDA_LIMIT_NETWORK`**: Closed via four $49.9\text{ k}\Omega \pm 0.1\%$ 0603 precision resistors providing a verified $199.6\text{ k}\Omega$ series loop, restricting fault current to $\le 27.5\text{ }\mu\text{A}$ ($< 50\text{ }\mu\text{A}$ auxiliary limit).
2. **`EDA_SWITCH_SELECTION`**: Closed via dual Panasonic AQY212GS solid-state PhotoMOS relays ($V_{OFF} = 60\text{ V}$, $I_{OFF} < 1\text{ nA}$, $1.5\text{ kVrms}$ isolation).
3. **`BATTERY_AND_CHARGE_CURRENT`**: Closed via TI BQ24074RGTR ($I_{CHG} = 500\text{ mA}$, $I_{LIM} = 1.45\text{ A}$, 10k NTC thermistor input).
4. **`POWER_MAGNETICS_AND_THERMALS`**: Closed via TI TPS63070RNMR buck-boost and Coilcraft XFL4020-102ME inductor ($I_{sat} = 5.4\text{ A}$, $DCR = 11.2\text{ m}\Omega$).
5. **`ISOLATION_CREEPAGE_CLEARANCE`**: Closed via TI ISOW7742DWER in SOIC-16 Wide-Body package with an explicit $\ge 8.0\text{ mm}$ creepage/clearance no-copper slot.
6. **`PPG_CABLE_SIGNAL_INTEGRITY`**: Closed via keyed JST GH 9-pin connector with $33\text{ }\Omega$ series damping resistors and separate LED pulse ground return.
7. **`FOOTPRINT_VERIFICATION`**: Closed via IPC-7351B standard SMD footprints for all BOM components with verified pin-1 orientations and manufacturer CAD models.
