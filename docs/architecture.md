# CIRCLE Rev B System Architecture

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION.**

CIRCLE Rev B is a precision, battery-powered physiological acquisition and closed-loop feedback instrument designed for experimental research. The system consists of two physical assemblies:
1. **`circle-main`**: Main compute, power management, EDA analog front-end, fail-open safety interlocks, 6-axis IMU, 4-bit SDMMC storage, reinforced-isolated synchronization, haptic actuation, and observability.
2. **`circle-ppg`**: Keyed, replaceable optical contact daughterboard preserving raw red and infrared photoplethysmography data.

---

## 1. Electrical Domain Partitioning & Safety Boundaries

The system strictly partitions circuitry into two isolated electrical domains:
- **`BAT_HUMAN` Domain**: Contains the ESP32-S3 microcontroller, BQ24074 battery charger, LiPo battery, TPS63070 digital power converter, TPS7A2033 low-noise analog LDO, ADS1220 EDA front-end, ICM-42688-P IMU, microSD storage, DRV2605L haptic driver, and `circle-ppg` optical board.
- **`LAB_ISO` Domain**: Contains the external interfaces of SYNC IN and SYNC OUT (BNC connectors J30 and J31), signal conditioning, and open-drain output drivers. This domain is powered and referenced exclusively to `LAB_ISO_GND` and the BNC outer shields.

```
+-----------------------------------------------------------------------------------------+
|                                    BAT_HUMAN DOMAIN                                     |
|                                                                                         |
|  [USB-C 5V] ---> [VBUS Detect] ---> Hardware Disable Net (USB_PRESENT)                 |
|       |                                     |                                           |
|       v                                     v                                           |
|  [BQ24074] <--> [LiPo 1S + NTC]     +--------------------+                              |
|       |                             | Hardware Safety    |                              |
|       v                             | Interlock Chain    |                              |
|  [TPS63070] ---> +3V3_DIG           +--------------------+                              |
|       |                                     |                                           |
|       +--------> [TPS7A2033]                v                                           |
|                     |               [Relays K1 & K2]                                    |
|                     v                       |                                           |
|             +3V3_EDA_A (Analog)             v                                           |
|                     |              [Passive Limiters]                                   |
|                     v                       |                                           |
|             [ADS1220 AFE] <------> [EDA Electrodes]                                     |
|                                                                                         |
|  [ESP32-S3] <---> [ICM-42688-P IMU]                                                     |
|      |                                                                                  |
|      +----------> [MicroSD 4-bit SDMMC]                                                 |
|      |                                                                                  |
|      +----------> [DRV2605L Haptic] ---> [TLV3201 Edge Detect]                          |
|      |                                                                                  |
|      +----------> [JST-GH Connector] <---> [circle-ppg Daughterboard]                   |
|      |                                                                                  |
+------+----------------------------------------------------------------------------------+
       |
       |  === 5.0 kVrms Reinforced Galvanic Isolation Barrier (>= 8.0 mm Creepage) ===
       |  [TI ISOW7742 Quad Digital Isolator + Integrated Isolated DC-DC Converter]
       v
+-----------------------------------------------------------------------------------------+
|                                     LAB_ISO DOMAIN                                      |
|                                                                                         |
|  [ISOW7742 Isolated VISO] ---> [74LVC1G17 Schmitt Buffer] <--- [SYNC_IN_BNC (J30)]      |
|                                [BSS138 Open-Drain Driver] ---> [SYNC_OUT_BNC (J31)]     |
|                                [Health Loopback Logic]                                  |
|                                                                                         |
|  Referenced strictly to LAB_ISO_GND (No connection to BAT_HUMAN_GND)                    |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Hardware Fail-Open Safety Chain

The electrodermal activity (EDA) output path uses a multi-tier hardware interlock preventing any human-connected stimulation or measurement whenever non-isolated external equipment is attached.

### 2.1 Hardware Logic Equations
$$\text{EDA\_PREPARE} = \text{EDA\_FW\_REQUEST} \land \text{BATTERY\_VALID} \land \overline{\text{USB\_PRESENT}} \land \overline{\text{DEBUG\_ATTACHED}} \land \overline{\text{EXTERNAL\_EXPANSION\_ATTACHED}} \land \text{SAFETY\_POWER\_GOOD}$$
$$\text{EDA\_ACTIVE} = \text{EDA\_PREPARE} \land \text{EDA\_ANALOG\_GOOD}$$

### 2.2 Functional Behavior
1. **Asynchronous Deassertion**: If USB VBUS, a debug header, or an external expansion cable is mated, the corresponding detection line deasserts $\text{EDA\_PREPARE}$; gate-delay calculation gives $< 100\text{ ns}$ (the validation plan requires $< 10\ \mu\text{s}$ measured).
2. **Bilateral Disconnect**: Two separate Panasonic AQY212GS PhotoMOS relays (K1 and K2) physically disconnect both the Drive and Sense electrode conductors.
3. **Power Removal**: The TPS7A2033 analog LDO is disabled, de-energizing the excitation voltage reference and ADC front-end.
4. **Passive Series Limiting**: Four $49.9\text{ k}\Omega \pm 0.1\%$ precision resistors ($199.6\text{ k}\Omega$ total loop resistance) are permanently placed in series with the electrode leads. By calculation, even with a welded relay contact the fault current under a 5.5 V rail is $I \le 5.5\text{ V} / 199.6\text{ k}\Omega \approx 27.5\text{ }\mu\text{A}$, below the $50.0\text{ }\mu\text{A}$ design limit. This is an unreviewed design calculation (gate `EDA_LIMIT_NETWORK`), not a measurement.

---

## 3. Subsystem Functional Blocks

### 3.1 Power Management
- **TI BQ24074RGTR**: Linear charger with Dynamic Power Path Management (DPPM). Automatically routes USB 5V power to the system rail (`V_SYS`) while charging the single-cell LiPo at $500\text{ mA}$. Monitors battery temperature via 10k NTC thermistor.
- **TI TPS63070RNMR**: High-efficiency buck-boost converter producing regulated +3.3V (`+3V3_DIG`) from any battery/system voltage between 2.0V and 16.0V.
- **TI TPS22918DBVR**: Individual high-side load switches controlling power distribution to MicroSD, PPG LEDs, Haptics, Isolation primary, and Expansion headers for aggressive sleep power savings.

### 3.2 Compute & Storage
- **ESP32-S3-WROOM-1-N16R8**: Dual-core 240 MHz MCU with 16MB Flash and 8MB Octal PSRAM. Runs deterministic acquisition tasks on dedicated cores.
- **MicroSD 4-bit SDMMC**: Dedicated high-speed storage interface with DMA buffering:
  $$\text{Sensors} \longrightarrow \text{Internal SRAM DMA} \longrightarrow \text{PSRAM Ring Buffer} \longrightarrow \text{Asynchronous SDMMC}$$
  Sized by calculation to absorb roughly 60 seconds of SD write stalls (design target; no firmware or hardware test exists).

### 3.3 Sensor Interfaces
- **TDK InvenSense ICM-42688-P**: High-precision 6-axis IMU on dedicated SPI bus (GPIO10-13) with hardware timestamping via `IMU_DRDY` (GPIO14).
- **TI ADS1220IPWR**: 24-bit delta-sigma ADC with programmable gain amplifier and dedicated `EDA_DRDY` interrupt (GPIO47).
- **`circle-ppg` Daughterboard**: Keyed JST-GH 9-pin interface carrying I2C, interrupts, board identification EEPROM (AT24CS02), and isolated LED pulse power returns.

### 3.4 Isolated Synchronization
- **TI ISOW7742DWER**: Digital isolator rated 5.0 kVrms reinforced (datasheet rating; the assembled barrier is untested) with integrated DC/DC converter.
- **SYNC IN**: Symmetrical resistor divider and SN74LVC1G17 Schmitt buffer capturing external triggers (datasheet: $< 15\text{ ns}$ delay; system timing untested).
- **SYNC OUT**: BSS138 open-drain MOSFET output allowing external pull-up voltages up to 12V.

---

## 4. Closed-Loop Evidence Model

CIRCLE is organized in three layers. Only the first two define the instrument.

| Layer | Contents | Status |
|---|---|---|
| **1. Sensing and evidence** | Rev B acquisition design, device clock, availability-aware raw streams, session record contract, provenance | Hardware designed, not built; software implemented and simulation-validated |
| **2. Closed-loop experimentation** | Signal pipeline, temporally lawful controller, execution evidence, audit and replay, adversarial scenarios, protocol validation | Implemented; validated only against the physiology twin |
| **3. Research extensions** | Resonance, emergence, PNT, R.A.I.N. protocol contracts | Bounded modules attached through contracts; removable without breaking layers 1–2 (checked by `tools/check_module_registry.py`) |

The loop, and the evidence each step leaves behind:

```
sense      raw codes, sample time, availability time           RAW_MEASURED (SIMULATED in the twin)
preserve   hashed raw bundle, declared GAPs, device events     STREAM_DESCRIPTOR, GAP, EVENT
infer      windows and controller features with lineage        DERIVED, MODEL_INFERRED (+ input cutoff)
decide     evaluation with gate results and decision time      MODEL_RESULT (decision_id)
intervene  firmware command                                    EVENT: HAPTIC_COMMAND
observe    electrical onset; independent IMU observation       EVENT (TLV3201 edge); EVENT, DERIVED from IMU
verify     every derived record rebuilt from raw, decisions     audit replay status
           replayed, temporal check, execution chain
```

A decision, a command, a physical actuation, an observed effect, and an interpretation are different things and are recorded as different things. A command is not evidence that a motor moved; an electrical edge is not evidence the vibration reached the body; nothing in a session asserts that physiology changed. Effect claims require matched controls. See [closed-loop evidence](closed-loop-evidence.md).

External analysis systems (DRR, R.A.I.N., typed-judgment critics) attach above the record: they may read sessions and propose protocols, and they never write evidence. Every recorded event retains its 64-bit device-monotonic timestamp (µs resolution), provenance class, and CRC-32C checksum.
