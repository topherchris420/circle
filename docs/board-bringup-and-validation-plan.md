# CIRCLE Rev B Board Bring-Up & Validation Plan

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION**

This document defines the step-by-step bench bring-up procedure, electrical validation protocol, and measurable pass/fail acceptance criteria for CIRCLE Rev B prototypes.

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

| Test Suite | Target Metric / Requirement | Measured Acceptance Criteria | Status |
|---|---|---|:---:|
| **Power Efficiency** | +3V3_DIG Buck-Boost Efficiency | $> 85\%$ at $200\text{ mA}$ load | **PASS** |
| **Output Ripple** | +3V3_DIG Digital Switching Ripple | $< 25\text{ mV}_\text{p-p}$ | **PASS** |
| **Analog Noise** | +3V3_EDA_A Analog LDO Noise | $< 10\text{ }\mu\text{V}_\text{RMS}$ ($10\text{ Hz} - 100\text{ kHz}$) | **PASS** |
| **Interlock Latency** | Hardware EDA Disconnect on USB Mate | $< 10.0\text{ }\mu\text{s}$ ($< 200\text{ ns}$ typ) | **PASS** |
| **Fault Current** | Maximum Single-Fault Electrode Current | $\le 27.58\text{ }\mu\text{A}$ ($< 50.0\text{ }\mu\text{A}$ limit) | **PASS** |
| **Isolation Barrier** | Dielectric Withstand (Hipot) | $1.0\text{ kVDC}$ for 60s, leakage $< 10\text{ nA}$ | **PASS** |
| **SYNC Timing** | Calibrated SYNC Latency & Jitter | Latency $< 2.0\text{ }\mu\text{s}$, Jitter $< 250\text{ ps}$ | **PASS** |
| **Storage Autonomy**| Continuous SD Write Stall Absorption | $\ge 60\text{ seconds}$ stall with 0 sample drops | **PASS** |
