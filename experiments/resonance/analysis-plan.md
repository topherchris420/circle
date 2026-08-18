# Statistical Analysis Plan & Interpretation Framework

> **ENGINEERING REVIEW / BENCH VALIDATION ONLY — NOT CERTIFIED FOR HUMAN CONNECTION.**

## 1. Epistemological Interpretation Hierarchy

All data processed in the resonance module is strictly stratified according to a 4-tier hierarchy:

1. **Measured:** Raw physical observations from calibrated sensors (voltage, current, input power, output power, frequency, raw optical photodiode counts, accelerometer axes, chamber temperature, hardware timestamps).
2. **Derived:** Mathematical transformations of measured data with closed-form definitions (spectral power density, Q-factor, bandwidth, phase delay, coherence metrics, pulse rate variability, skin conductance response amplitudes).
3. **Model-Inferred:** Latent state estimates and operational scores produced by algorithms (Resonance Response Index, signal-to-noise ratio, cluster classifications).
4. **Hypothesis / Interpretive Label:** Conceptual models, philosophical metaphors, or speculative theories ("prana", "subtle energetic resonance", "geometric field coherence").

> [!CAUTION]
> **Strict Separation**: A hypothesis label must **never** be stored or reported as a physical measurement. The system never outputs claims like `"Prana detected = True"`.

## 2. Statistical Decision Metrics

### Resonance Response Index (RRI)
The primary operational response score $RRI \in [0.0, 1.0]$ is defined as:

$$\text{RRI} = \left( \frac{|d|}{1.0 + |d|} \right) \cdot (1.0 - \text{Risk}_\text{EM})$$

where:
* $d = \frac{\mu_\text{active} - \mu_\text{baseline}}{\sigma_\text{pooled}}$ is Cohen's $d$ effect size between active intervention and baseline.
* $\text{Risk}_\text{EM} \in [0.0, 1.0]$ is the artifact interference penalty computed from near-field RF probes, phantom responses, and thermal gradients.

### Evidence Status Categorization:
* **`REPEATABLE_DIFFERENCE`:** Effect size $|d| > 0.8$, $95\%\text{ CI}$ excludes zero across $> 5$ blinded trials, and phantom artifact risk $< 0.20$.
* **`EXPLORATORY`:** Measurable contrast detected ($0.2 \le |d| \le 0.8$), clean phantom control, awaiting trial replication.
* **`INCONCLUSIVE`:** No statistically significant contrast from sham or baseline ($|d| < 0.2$).
* **`ARTIFACT_LIKELY`:** Detected response strongly mirrors phantom control pickup or high near-field RF interference ($\text{Risk}_\text{EM} \ge 0.40$).
