# CIRCLE Rev B Design Decision Log

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION**

This document records the architectural and electrical design decisions, component selections, trade-off analyses, and rejected alternatives for CIRCLE Rev B.

---

## 1. Decision Log Index

| Decision ID | Topic / Subsystem | Chosen Solution | Key Rationale | Rejected Alternatives Considered |
|---|---|---|---|---|
| **DEC-01** | Compute Engine | **ESP32-S3-WROOM-1-N16R8** | Integrated 240 MHz dual-core, native USB 2.0, 16MB Flash, 8MB Octal PSRAM for 60s SD write stall absorption, Wi-Fi/BLE. | *STM32H7*: Higher cost, external BLE module needed; *nRF5340*: Limited RAM for raw burst buffering. |
| **DEC-02** | Battery Charger & Power-Path | **TI BQ24074RGTR** | Integrated Dynamic Power-Path Management (DPPM), programmable $500\text{ mA}$ charge current, 10k NTC thermistor monitoring, autonomous power switching. | *TP4056*: No power-path mgt (battery discharges while connected); *BQ25606*: I2C complexity not needed for robust hardware safety. |
| **DEC-03** | Primary Digital Voltage Regulator | **TI TPS63070RNMR Buck-Boost** | Wide input range (2.0V to 16V) seamlessly supports full LiPo curve (3.0V–4.2V) and 4.4V $V_{SYS}$; 2.0A output capacity; high efficiency ($> 88\%$). | *Buck-only (TPS62088)*: Drops out below 3.4V, wasting $> 15\%$ battery capacity; *Boost-then-LDO*: Excessive power dissipation. |
| **DEC-04** | EDA Analog Power Supply | **TI TPS7A2033 Low-Noise LDO** | $6.5\text{ }\mu\text{V}_\text{RMS}$ ultra-low noise, $85\text{ dB}$ PSRR @ 1 kHz, dedicated enable pin tied to hardware `EDA_PREPARE` net. | *Direct digital rail*: Digital switching noise couples into 24-bit ADC; *LC filter only*: Insufficient low-frequency ripple rejection. |
| **DEC-05** | EDA Output Disconnect Switches | **Dual Panasonic AQY212GS PhotoMOS Relays** | True galvanic solid-state disconnection, $> 10^{10}\text{ }\Omega$ off-isolation resistance, $60\text{ V}$ breakdown, $< 1\text{ nA}$ leakage, zero contact bounce. | *Mechanical reed relays*: Susceptible to magnetic interference and vibration; *Analog MUX (ADG704)*: Poor off-isolation ($< 1\text{ M}\Omega$ under fault). |
| **DEC-06** | EDA Passive Current Limiting | **$4 \times 49.9\text{ k}\Omega \pm 0.1\%$ (200 k$\Omega$ Loop)** | Restricts worst-case fault current to $27.5\text{ }\mu\text{A}$ ($< 50.0\text{ }\mu\text{A}$ limit) even under single-relay weld; symmetrical topology suppresses common-mode noise. | *Active current limiter (BJT/JFET)*: Subject to single-point component short failures; *Single resistor*: Lacks bilateral symmetry. |
| **DEC-07** | Laboratory SYNC Isolation | **TI ISOW7742DWER Reinforced Isolator** | 5.0 kVrms reinforced isolation, integrated low-emission DC/DC converter supplying isolated power, $\ge 8.0\text{ mm}$ wide-body SOIC creepage. | *Optocouplers (6N137)*: Aging degradation, high LED drive current, requires separate isolated DC-DC converter brick. |
| **DEC-08** | Removable Storage Interface | **Amphenol Push-Push MicroSD + 4-bit SDMMC** | Native 4-bit SDMMC bus achieves $> 10\text{ MB/s}$ throughput, Card Detect hardware switch, dedicated TPS22918 load switch for power cycling. | *SPI mode MicroSD*: Limited to $< 2\text{ MB/s}$, causes buffer overflow during burst logging; *eMMC*: Not user-removable. |
| **DEC-09** | PPG Optical Architecture | **Modular `circle-ppg` Daughterboard (MAX30102)** | Modular JST-GH 9-pin cable allows optical head replacement without redesigning compute board; local 1.8V LDO and I2C level translation. | *Monolithic on-board sensor*: Rigid placement prevents ergonomic finger/wrist skin contact; *Discrete LEDs/PD*: Complex calibration. |
| **DEC-10** | Hardware Interlock Strategy | **Discrete 74LVC Hardware Logic + TPS3700 Window Supervisors** | Pure hardware evaluation of all safety terms; firmware cannot energize relays if any unsafe condition (USB, debug, low battery) is present. | *Firmware-only check*: Single CPU crash or hung interrupt could leave electrodes energized while USB is plugged in. |

---

## 2. Component Selection Details & Lifecycle Status

All selected components have been verified for active lifecycle status, active manufacturing, and broad availability across major authorized distributors (Digi-Key, Mouser, Newark):

1. **ESP32-S3-WROOM-1-N16R8**: Espressif Systems (Active, 10-year longevity commitment).
2. **BQ24074RGTR**: Texas Instruments (Active, high-volume production).
3. **TPS63070RNMR**: Texas Instruments (Active, high-volume production).
4. **ADS1220IPWR**: Texas Instruments (Active, high-precision industrial standard).
5. **REF5020AIDR**: Texas Instruments (Active, high-precision voltage reference).
6. **OPA2192IDR**: Texas Instruments (Active, e-trim operational amplifier).
7. **AQY212GS**: Panasonic Electric Works (Active, solid-state PhotoMOS).
8. **ISOW7742DWER**: Texas Instruments (Active, reinforced digital isolation).
9. **ICM-42688-P**: TDK InvenSense (Active, ultra-low noise 6-axis IMU).
10. **MAX30102EFD+T**: Analog Devices / Maxim Integrated (Active, optical biosensor).
11. **DRV2605LDGSR**: Texas Instruments (Active, haptic driver).
12. **MCP23017-E/SO**: Microchip Technology (Active, standard I2C I/O expander).
