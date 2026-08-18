# Experimental Controls and Artifact Discrimination

> **ENGINEERING REVIEW / BENCH VALIDATION ONLY — NOT CERTIFIED FOR HUMAN CONNECTION.**

## 1. Geometric Control Matrix

To scientifically test whether specific proportions (e.g. golden ratio $\phi \approx 1.6180339887$) or particular polyhedral core geometries (dual-interpenetrating tetrahedron / Merkaba) possess unique physical properties, the system must evaluate them against balanced control conditions:

| Condition Class | Nested Sphere Diameters | Central Core Geometry | Purpose / Contrast |
| :--- | :--- | :--- | :--- |
| **Nominal Test** | Golden Ratio ($D, D/\phi, D/\phi^2$) | Dual Tetrahedron (Merkaba) | Primary hypothesis condition |
| **Spacing Control** | Equal spacing ($D, 2D/3, D/3$) | Dual Tetrahedron (Merkaba) | Isolates ratio vs diameter effect |
| **Random Spacing** | Uniform random $(D, D \cdot r_1, D \cdot r_2)$ | Dual Tetrahedron (Merkaba) | Tests non-harmonic baseline |
| **Core Control 1** | Golden Ratio ($D, D/\phi, D/\phi^2$) | Spherical Core | Tests spherical vs tetrahedral symmetry |
| **Core Control 2** | Golden Ratio ($D, D/\phi, D/\phi^2$) | Cubic Core | Tests cubic vs tetrahedral symmetry |
| **No-Core Control** | Golden Ratio ($D, D/\phi, D/\phi^2$) | None (Empty cavity) | Isolates contribution of core structure |
| **Sham / Off** | $0.0\text{ mm}$ (Drive disabled) | Sham / Off | Measures baseline noise & environmental drift |

## 2. Matched Orthogonal Factorial Execution

To decouple geometry from core effects and evaluate potential synergistic interactions, the closed-loop scheduler generates matched factorial blocks evaluated at identical drive frequencies and voltage amplitudes:

1. $(\phi \text{ Spacing} \times \text{Merkaba Core})$
2. $(\phi \text{ Spacing} \times \text{Spherical Core})$
3. $(\phi \text{ Spacing} \times \text{No Core})$
4. $(\text{Equal Spacing} \times \text{Merkaba Core})$
5. $(\text{Equal Spacing} \times \text{Spherical Core})$
6. $(\text{Random Spacing} \times \text{Merkaba Core})$
7. $(\text{Sham / Off} \times \text{Sham / Off})$

The resulting multi-trial data is analyzed via the `FactorialInteractionAnalyzer` regression model to estimate $\beta_G$, $\beta_C$, and the interaction coefficient $\beta_{GC}$.

## 3. Electronic Phantoms and Bench Artifact Controls

Electromagnetic and acoustic fields can induce false signals in high-impedance biosignal amplifiers (such as ADS1220 24-bit ADC for EDA or MAX30102 PPG front-end) through:
1. **Direct Capacitive/Inductive Coupling:** High $dV/dt$ or $dI/dt$ picked up on PCB traces.
2. **RF Rectification:** Nonlinear ESD diode junctions rectifying continuous-wave RF into a DC offset that mimics slow skin conductance response (EDA).
3. **Thermal Drift:** Resistive cavity dissipation warming nearby optical diodes and shifting forward voltages.

### Mandatory Bench Phantom Tests:
* **Passive Resistor Phantom:** A precision $100\text{ k}\Omega$ metal-film resistor connected across bench testpoints in place of biological tissue. Any dynamic delta $\Delta_\text{phantom} = \mu_\text{active} - \mu_\text{baseline}$ exceeding threshold is classified as direct EM artifact.
* **Optical Solid-State Phantom:** A neutral density silicone optical block placed on the PPG sensor. Any AC modulation matching the drive frequency is logged as optical/electrical feedthrough.
* **Unpowered Chamber Baseline:** Operating the drive electronics into a shielded $50\ \Omega$ termination with identical cable geometry.
