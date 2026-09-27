# CIRCLE Rev B Board Bring-Up & Validation Plan

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION**

This document defines the step-by-step bench bring-up procedure, electrical validation protocol, and measurable pass/fail acceptance criteria for CIRCLE Rev B prototypes.

> **Status: NOT PERFORMED.** No Rev B board has been fabricated, assembled, or powered. Every criterion below is a planned test, and each numeric limit is a design target or datasheet-derived expectation, not a measurement. Results, when they exist, must be recorded against `BENCH_BRINGUP` in [`hardware/review-gates.json`](../hardware/review-gates.json). Before any body contact, follow the [physical evidence ladder](physical-evidence-ladder.md): electrical and optical phantoms first.

---

## 1. Safety Equipment & Inspection Setup

Before applying power to any fabricated Rev B assembly:
1. **Visual Inspection**: Under stereo microscope ($10\times - 40\times$), inspect all QFN/LGA packages (ESP32-S3, BQ24074, TPS63070, ICM-42688, ADS1220, ISOW7742) for solder bridging, misalignment, insufficient paste, or voiding.
2. **Isolation Barrier Inspection**: Verify the $\ge 8.0\text{ mm}$ no-copper isolation slot across all 4 layers between `BAT_HUMAN_GND` and `LAB_ISO_GND` has zero flux residue, copper whiskers, or contamination.
3. **Impedance / Unpowered Resistance Checks**:
   - Measure resistance from `+3V3_DIG` to `BAT_HUMAN_GND`: **Pass: $> 100\text{ k}\Omega$**.
   - Measure resistance from `+3V3_EDA_A` to `BAT_HUMAN_GND`: **Pass: $> 500\text{ k}\Omega$**.
   - Measure resistance from `V_SYS` to `BAT_HUMAN_GND`: **Pass: $> 200\text{ k}\Omega$**.
   - Measure resistance between `BAT_HUMAN_GND` and `LAB_ISO_GND`: **Pass: $> 100\text{ G}\Omega$** (Open circuit).
   - Measure resistance between EDA electrode terminals (J10): **Pass: $> 10\text{ G}\Omega$** (Relays K1/K2 normally open).

---

## 2. Step-by-Step Bench Bring-Up Protocol

### Step 2.1: Power Supply & Charging Subsystem
- **Procedure**: Connect bench power supply set to $3.70\text{ V}$ with current limit $200\text{ mA}$ to battery connector J2 (Pin 1 `BAT_POS`, Pin 2 `BAT_NEG`, Pin 3 $10\text{ k}\Omega$ NTC simulator to GND).
- **Measurements**:
  1. Measure `V_SYS` on TP1: **Criteria: $3.65\text{ V} - 3.75\text{ V}$**.
  2. Measure `+3V3_DIG` on TP2: **Criteria: $3.30\text{ V} \pm 1.5\%$ ($3.25\text{ V} - 3.35\text{ V}$)**.
  3. Measure voltage ripple on `+3V3_DIG` using 200 MHz oscilloscope ($1\times$ probe, AC coupled): **Criteria: $< 25\text{ mV}_\text{p-p}$**.
  4. Connect USB-C 5.0V source to J1; verify BQ24074 switches system rail to $4.40\text{ V} \pm 50\text{ mV}$ and battery begins charging at $500\text{ mA} \pm 10\%$.

### Step 2.2: ESP32-S3 Programming & Clocking
- **Procedure**: Connect USB-C cable; verify PC enumerates Espressif USB JTAG/Serial device. Flash test firmware (`esptool.py flash`).
- **Measurements**:
  1. Verify UART console output at 115200 baud on GPIO43.
  2. Verify 40 MHz crystal oscillator stability on ESP32-S3 module.
  3. Verify 8MB Octal PSRAM memory test passes ($100\%$ byte read/write verification).

### Step 2.3: Hardware Safety Interlock & Relay De-Energization Test
- **Procedure**: Run firmware requesting EDA activation (`EDA_FW_REQUEST = 1` on GPIO45).
- **Measurements & Interlock Injection Tests**:
  1. In battery-only mode (no USB), verify `EDA_PREPARE` (TP4) goes HIGH ($3.3\text{ V}$); verify TPS7A2033 enables and `+3V3_EDA_A` (TP3) reaches $3.30\text{ V} \pm 1.0\%$.
  2. Verify `EDA_ANALOG_GOOD` asserts after 10 ms; verify `EDA_ACTIVE` (TP5) goes HIGH and relays K1/K2 energize (measure continuity across contacts).
  3. **USB Insertion Test**: With EDA active, hot-plug USB-C cable. Measure time from VBUS edge to `EDA_ACTIVE` low transition on oscilloscope. **Pass Criteria: $t_{disable} < 10.0\text{ }\mu\text{s}$ (Typical $< 200\text{ ns}$)**.
  4. **Debug Header Insertion Test**: Short `DEBUG_ATTACHED` pin on J3 to GND. **Pass Criteria: Relays K1/K2 immediately open**.
  5. **Low Battery Injection Test**: Decrease power supply voltage below $3.15\text{ V}$. **Pass Criteria: `BATTERY_VALID` deasserts and relays open**.

### Step 2.4: EDA Front-End Current Limiting & Noise Test
- **Procedure**: With EDA active, connect $100\text{ k}\Omega \pm 0.1\%$ precision test resistor across electrode terminals J10 (`EDA_DRIVE_P` to `EDA_DRIVE_N`).
- **Measurements**:
  1. Measure excitation voltage across test resistor: **Criteria: $0.500\text{ V} \pm 1.0\%$**.
  2. Read ADS1220 24-bit ADC samples at 64 SPS over 60 seconds: **Criteria: Noise $< 0.05\text{ }\mu\text{S}_\text{RMS}$**.
  3. **Short-Circuit Fault Test**: Place a digital ammeter directly across J10 terminals; inject 5.5V rail into AFE excitation buffer. **Pass Criteria: Measured short-circuit current $\le 27.58\text{ }\mu\text{A}$**.

### Step 2.5: Galvanic Isolation & High-Voltage Hipot Test
- **Procedure**: Using an automated dielectric withstand tester (Hipot):
  1. Apply $1000\text{ VDC}$ between `BAT_HUMAN_GND` and `LAB_ISO_GND` for 60 seconds. **Pass Criteria: Leakage current $< 10\text{ nA}$, insulation resistance $> 100\text{ G}\Omega$**.
  2. Measure SYNC IN capture latency using pulse generator (5V square pulse, $10\text{ }\mu\text{s}$ width) connected to J30. Measure delay to GPIO1 interrupt. **Pass Criteria: Latency $< 2.0\text{ }\mu\text{s}$, peak-to-peak jitter $< 250\text{ ps}$**.
  3. Measure SYNC OUT pulse generation at J31. **Pass Criteria: Fall time $< 20\text{ ns}$ with $1\text{ k}\Omega$ pullup**.

### Step 2.6: MicroSD 4-Bit SDMMC Storage & Stall Recovery Test
- **Procedure**: Insert SanDisk Extreme 32GB Class 10 MicroSD card; run continuous raw data capture benchmark.
- **Measurements**:
  1. Verify 4-bit SDMMC bus clock runs at 40 MHz with clean rise times ($< 5\text{ ns}$).
  2. Inject simulated 45-second SD write stall; verify PSRAM ring buffer absorbs all samples without dropping a single frame.
  3. Hot-remove card during active recording; verify firmware catches Card Detect edge, flushes pending data to Flash/PSRAM, and cleanly resumes upon re-insertion.

### Step 2.7: PPG Optical Daughterboard (`circle-ppg`) Test
- **Procedure**: Connect `circle-ppg` via 150mm JST-GH cable to J20.
- **Measurements**:
  1. Read AT24CS02 EEPROM unique 128-bit serial number over I2C (address `0x50`).
  2. Measure local 1.8V LDO output on daughterboard: **Criteria: $1.80\text{ V} \pm 1.5\%$**.
  3. Configure MAX30102 for red + IR acquisition @ 200 SPS; place index finger on optical window.
  4. Verify clean raw photoplethysmogram waveforms with AC pulsatile amplitude $> 10,000\text{ counts}$ and zero digital clock noise coupling into red/IR channels.

---

## 3. Summary Validation Matrix

Each row is a hardware design decision stated as a proposition that the bench must earn. None has been tested.

| Proposition under test | Acceptance criterion (target) | Basis of the target | Status |
|---|---|---|:---:|
| The buck-boost is efficient enough for the battery budget | > 85 % at 200 mA | Datasheet curve | **NOT PERFORMED** |
| Digital switching ripple stays below analog needs | < 25 mVp-p on `+3V3_DIG` | Design target | **NOT PERFORMED** |
| The analog LDO is quiet enough for 24-bit EDA use | < 10 µVrms (10 Hz–100 kHz) | Datasheet (6.5 µVrms typical) | **NOT PERFORMED** |
| The interlock removes electrode drive on USB mate | < 10 µs (logic propagation typically < 200 ns) | Gate-delay calculation | **NOT PERFORMED** |
| The limit network bounds single-fault electrode current | ≤ 27.58 µA | Calculation (5.5 V / 199.6 kΩ); requires independent review | **NOT PERFORMED** |
| The assembled isolation barrier withstands test voltage | 1.0 kVDC for 60 s, leakage < 10 nA | Planned production test; component is rated 5.0 kVrms | **NOT PERFORMED** |
| SYNC capture meets timing needs | latency < 2 µs, jitter < 250 ps | Datasheet delay; design target | **NOT PERFORMED** |
| PSRAM buffering survives SD write stalls | ≥ 60 s stall with 0 sample drops | Calculation from stream rates (see note) | **NOT PERFORMED** |
| The wrist IMU observes haptic actuation | onset within ±5 ms of TLV3201 edge | Twin result (simulation only) | **NOT PERFORMED** |
| The PPG head gives usable pulse signal | AC amplitude > 10,000 counts | Design target | **NOT PERFORMED** |

Note on buffering: the modeled streams (EDA 64 SPS × 3 B, PPG 100 SPS × 6 B, IMU 400 SPS × 12 B, plus framing) are on the order of 6–10 kB/s, so 8 MB of PSRAM could in principle hold several minutes. The 60 s target leaves margin for firmware use of PSRAM; it is a calculation, not a measured stall test.

Passing any row closes nothing by itself: gates in [`hardware/review-gates.json`](../hardware/review-gates.json) also require independent review where stated.
