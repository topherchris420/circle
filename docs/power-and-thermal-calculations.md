# CIRCLE Rev B Power, Thermal, & Analog Calculations

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION**

This document provides the closed-form mathematical derivations and numerical proofs for the CIRCLE Rev B electrical systems, covering:
1. Complete worst-case power budget and battery discharge curves.
2. Primary buck-boost efficiency modeling and inductor saturation margins.
3. Charger thermal dissipation and junction temperature rise.
4. Electrode output current, voltage, and delivered charge limits under normal and single-fault conditions.
5. Analog front-end (AFE) noise, CMRR, bandwidth, and dynamic range headroom.

---

## 1. System Power Budget & Battery Autonomy Calculations

### 1.1 Rail-by-Rail Subsystem Currents

$$\begin{aligned}
I_{\text{ESP32\_typ}} &= 95.0\text{ mA}, \quad &I_{\text{ESP32\_pk}} &= 380.0\text{ mA} \quad (\text{RF TX Burst}) \\
I_{\text{IMU\_typ}} &= 1.0\text{ mA}, \quad &I_{\text{IMU\_pk}} &= 1.5\text{ mA} \\
I_{\text{MCP\_typ}} &= 0.8\text{ mA}, \quad &I_{\text{MCP\_pk}} &= 2.0\text{ mA} \\
I_{\text{AFE\_typ}} &= 3.25\text{ mA}, \quad &I_{\text{AFE\_pk}} &= 6.8\text{ mA} \\
I_{\text{PPG\_1V8}} &= 1.2\text{ mA}, \quad &I_{\text{PPG\_1V8\_pk}} &= 2.5\text{ mA} \\
I_{\text{PPG\_LED}} &= 15.0\text{ mA}, \quad &I_{\text{PPG\_LED\_pk}} &= 120.0\text{ mA} \quad (\text{Pulsed}) \\
I_{\text{SD\_typ}} &= 35.0\text{ mA}, \quad &I_{\text{SD\_pk}} &= 180.0\text{ mA} \quad (\text{Write Burst}) \\
I_{\text{ISO\_typ}} &= 22.0\text{ mA}, \quad &I_{\text{ISO\_pk}} &= 85.0\text{ mA} \\
I_{\text{HAPTIC\_typ}} &= 0.1\text{ mA}, \quad &I_{\text{HAPTIC\_pk}} &= 220.0\text{ mA} \quad (\text{Actuation Pulse})
\end{aligned}$$

### 1.2 Total Current & Power Consumption at Nominal $V_{BAT} = 3.70\text{ V}$

- **Total 3.3V Output Current ($I_{3V3}$)**:
  $$I_{3V3\_typ} = \sum I_{typ} = 95.0 + 1.0 + 0.8 + 3.25 + 1.2 + 15.0 + 35.0 + 22.0 + 0.1 = \mathbf{173.35\text{ mA}}$$
  $$I_{3V3\_pk} = \sum I_{pk} = 380.0 + 1.5 + 2.0 + 6.8 + 2.5 + 120.0 + 180.0 + 85.0 + 220.0 = \mathbf{997.80\text{ mA}}$$

- **Total Power Delivered to System**:
  $$P_{OUT\_typ} = 3.30\text{ V} \times 173.35\text{ mA} = \mathbf{572.06\text{ mW}}$$
  $$P_{OUT\_pk} = 3.30\text{ V} \times 997.80\text{ mA} = \mathbf{3292.74\text{ mW}} \approx \mathbf{3.29\text{ W}}$$

---

## 2. TPS63070 Buck-Boost Sizing & Inductor Saturation

### 2.1 Worst-Case Input Current at Battery Cutoff ($V_{BAT\_min} = 3.00\text{ V}$)
Assuming buck-boost conversion efficiency $\eta = 84\%$ under heavy peak load at $3.00\text{ V}$ input:
$$I_{IN\_max} = \frac{P_{OUT\_pk}}{\eta \times V_{IN\_min}} = \frac{3.293\text{ W}}{0.84 \times 3.00\text{ V}} = \mathbf{1.307\text{ A}}$$

### 2.2 Inductor Ripple & Peak Switch Current
For switching frequency $f_{SW} = 2.4\text{ MHz}$ and inductance $L = 1.0\text{ }\mu\text{H}$:
$$\Delta I_L = \frac{V_{IN\_min} \times (V_{OUT} - V_{IN\_min})}{f_{SW} \times L \times V_{OUT}} = \frac{3.00\text{ V} \times (3.30\text{ V} - 3.00\text{ V})}{2.4 \times 10^6 \times 1.0 \times 10^{-6} \times 3.30\text{ V}} = \frac{0.90}{7.92} \approx 0.114\text{ A}$$
$$I_{L\_peak} = I_{IN\_max} + \frac{\Delta I_L}{2} = 1.307\text{ A} + 0.057\text{ A} = \mathbf{1.364\text{ A}}$$

- **Inductor Selected**: Coilcraft `XFL4020-102ME` ($L = 1.0\text{ }\mu\text{H} \pm 20\%$, $I_{sat} = 5.40\text{ A}$, $DCR = 11.2\text{ m}\Omega$).
- **Saturation Margin Verification**:
  $$\text{Margin} = \frac{I_{sat} - I_{L\_peak}}{I_{L\_peak}} = \frac{5.40\text{ A} - 1.364\text{ A}}{1.364\text{ A}} = \mathbf{+295.9\%}$$
  (The inductor will never saturate under any credible operating transient).

---

## 3. BQ24074 Charger Power Dissipation & Thermals

### 3.1 Linear Charger Power Dissipation
- **Fast Charge Current**: $I_{CHG} = 500\text{ mA}$.
- **USB Input Voltage**: $V_{USB\_max} = 5.25\text{ V}$ (USB 5V $+5\%$ tolerance).
- **Minimum Battery Voltage during Constant Current Phase**: $V_{BAT\_min} = 3.20\text{ V}$.
- **Maximum Power Dissipated in Charger IC**:
  $$P_{D\_charger} = (V_{USB\_max} - V_{BAT\_min}) \times I_{CHG} = (5.25\text{ V} - 3.20\text{ V}) \times 0.500\text{ A} = \mathbf{1.025\text{ W}}$$

### 3.2 Junction Temperature Calculation
- **Package**: QFN-16 ($3.0\text{ mm} \times 3.0\text{ mm}$) with exposed thermal pad soldered to 4x thermal vias ($0.3\text{ mm}$ drill) connecting to Layer 2 ground plane.
- **Thermal Resistance**: $R_{\theta JA} = 45.0^\circ\text{C/W}$.
- **Temperature Rise ($\Delta T$)**:
  $$\Delta T = P_{D\_charger} \times R_{\theta JA} = 1.025\text{ W} \times 45.0^\circ\text{C/W} = \mathbf{46.13^\circ\text{C}}$$
- **Junction Temperature ($T_J$) at Ambient $T_A = 25.0^\circ\text{C}$**:
  $$T_J = T_A + \Delta T = 25.0^\circ\text{C} + 46.13^\circ\text{C} = \mathbf{71.13^\circ\text{C}}$$
- **Thermal Margin**:
  $$T_{margin} = T_{J\_max} - T_J = 125.0^\circ\text{C} - 71.13^\circ\text{C} = \mathbf{+53.87^\circ\text{C}}$$
  (Compliant with conservative thermal derating standards).

---

## 4. Electrode Output Safety Limits & Single-Fault Current Proof

### 4.1 Series Limiting Resistor Tolerances
The loop contains four precision metal film resistors (Panasonic ERA-3AEB4992V, $49.9\text{ k}\Omega \pm 0.1\%, 25\text{ ppm/}^\circ\text{C}$):
$$R_{A1} = R_{A2} = R_{B1} = R_{B2} = 49.9\text{ k}\Omega \pm 0.1\%$$
$$R_{min\_single} = 49.9\text{ k}\Omega \times (1 - 0.001) = 49.8501\text{ k}\Omega$$
$$R_{loop\_min} = 4 \times 49.8501\text{ k}\Omega = \mathbf{199.4004\text{ k}\Omega}$$

### 4.2 Absolute Worst-Case Fault Current ($I_{fault\_max}$)
- **Worst-Case Fault Scenario**:
  1. Relay K1 contact suffers catastrophic weld/short.
  2. Excitation buffer op-amp fails with output shorted directly to highest internal power rail ($V_{SYS\_max} = 5.50\text{ V}$).
  3. Patient skin impedance is $R_{skin} = 0.0\text{ }\Omega$ (direct short).
- **Fault Current Derivation**:
  $$I_{fault\_max} = \frac{V_{SYS\_max}}{R_{loop\_min}} = \frac{5.50\text{ V}}{199.4004\text{ k}\Omega} = \mathbf{27.5827\text{ }\mu\text{A}}$$

### 4.3 Safety Standard Comparison
- **IEC 60601-1 / ANSI AAMI ES60601-1 Limit for Patient Auxiliary DC Current (Single Fault)**:
  $$I_{limit\_standard} = \mathbf{50.00\text{ }\mu\text{A}}$$
- **Safety Margin Percentage**:
  $$\text{Safety Margin} = \frac{50.00\text{ }\mu\text{A} - 27.58\text{ }\mu\text{A}}{50.00\text{ }\mu\text{A}} \times 100\% = \mathbf{44.83\%}$$

---

## 5. Analog Front-End (AFE) Signal & Noise Analysis

### 5.1 Excitation Voltage & Dynamic Range
- **Precision Reference**: REF5020 ($V_{REF} = 2.048\text{ V} \pm 0.05\%$).
- **Excitation Divider**: Symmetrical divider buffered by OPA2192 generates $V_{excite} = 0.500\text{ V} \pm 1.0\%$.
- **Usable Skin Conductance Dynamic Range**:
  - Minimum measurable conductance: $G_{min} = 0.05\text{ }\mu\text{S}$ ($R_{skin} = 20\text{ M}\Omega$).
  - Maximum measurable conductance: $G_{max} = 100.0\text{ }\mu\text{S}$ ($R_{skin} = 10\text{ k}\Omega$).
  - ADC Input Voltage Range:
    $$V_{in\_min} = V_{excite} \times \frac{10\text{ k}\Omega}{10\text{ k}\Omega + 200\text{ k}\Omega} \approx 23.8\text{ mV}$$
    $$V_{in\_max} = V_{excite} \times \frac{20\text{ M}\Omega}{20\text{ M}\Omega + 200\text{ k}\Omega} \approx 495.0\text{ mV}$$

### 5.2 Noise Spectral Density & Effective Number of Bits (ENOB)
- **Thermal Johnson-Nyquist Noise of $200\text{ k}\Omega$ loop at $T = 300\text{ K}$**:
  $$v_n = \sqrt{4 k_B T R \Delta f} = \sqrt{4 \times (1.38 \times 10^{-23}) \times 300 \times 200000 \times 64} \approx 460.5\text{ nV}_\text{RMS}$$
- **ADS1220 Input Noise at Gain=1, 64 SPS**:
  $$v_{n\_ADC} = 0.45\text{ }\mu\text{V}_\text{RMS}$$
- **Total Input-Referred Noise**:
  $$v_{n\_total} = \sqrt{v_n^2 + v_{n\_ADC}^2} = \sqrt{(0.460)^2 + (0.450)^2} = \mathbf{0.644\text{ }\mu\text{V}_\text{RMS}}$$
- **Effective Resolution (ENOB)**:
  $$\text{ENOB} = \frac{\ln\left(\frac{V_{FSR}}{v_{n\_total} \times 2\sqrt{2}}\right)}{\ln(2)} = \frac{\ln\left(\frac{2.048\text{ V}}{0.644 \times 10^{-6} \times 2.828}\right)}{0.69315} = \mathbf{20.08\text{ Bits}}$$
  (Achieves $> 20\text{-bit}$ effective dynamic range, completely resolving tonic and phasic electrodermal fluctuations).
