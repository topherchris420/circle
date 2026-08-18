# Statistical Analysis Plan & Interpretation Framework

> **ENGINEERING REVIEW / BENCH VALIDATION ONLY — NOT CERTIFIED FOR HUMAN CONNECTION.**

## 1. Epistemological Interpretation Hierarchy

All data processed in the resonance module is strictly stratified according to a 4-tier hierarchy:

1. **Measured:** Raw physical observations from calibrated sensors (voltage, current, input power, output power, frequency, raw optical photodiode counts, accelerometer axes, chamber temperature, hardware timestamps).
2. **Derived:** Mathematical transformations of measured data with closed-form definitions (spectral power density, Q-factor, bandwidth, phase delay, coherence metrics, pulse rate variability, skin conductance response amplitudes).
3. **Model-Inferred:** Latent state estimates and operational scores produced by algorithms (Resonance Response Index, posterior surrogate distributions, signal-to-noise ratio, cluster classifications).
4. **Hypothesis / Interpretive Label:** Conceptual models, philosophical metaphors, or speculative theories ("geometric coupling", "sacred geometry analogy").

> [!CAUTION]
> **Strict Separation**: A hypothesis label must **never** be stored or reported as a physical measurement. The system never outputs claims like `"Prana detected = True"`.

## 2. Statistical Decision Metrics

### A. Double-Difference Sham Subtraction
To eliminate ambient drifts, temperature fluctuations, and switching noise, all biological intervention contrasts compute the net double-difference:

$$\Delta_\text{net} = (\mu_\text{active} - \mu_\text{active\_base}) - (\mu_\text{sham} - \mu_\text{sham\_base})$$

$$\text{Cohen's } d = \frac{\Delta_\text{net}}{\sigma_\text{pooled}}$$

### B. Circular Block Permutation Testing (Autocorrelation-Aware)
Physiological time series (EDA, PPG, HRV) exhibit strong temporal autocorrelation ($\text{Cov}(x_t, x_{t+k}) > 0$). Naive sample-level permutation artificially deflates variance and produces spuriously tiny $p$-values.

CIRCLE implements **Circular Block Permutation** with block length $L_\text{block} \ge 5\text{ samples}$ (preserving the short-range autocorrelation structure within contiguous blocks). Condition assignments are shuffled across blocks to evaluate the null hypothesis:

$$H_0: \Delta_\text{active} = \Delta_\text{sham}$$

yielding an exact empirical $p_\text{perm}$.

### C. Aligned Block Bootstrap Confidence Intervals for RRI
The **Resonance Response Index ($RRI \in [0.0, 1.0]$)** is penalized by electromagnetic and thermal artifact risk:

$$\text{RRI} = \left( \frac{|d|}{1.0 + |d|} \right) \cdot (1.0 - \text{Risk}_\text{EM})$$

Uncertainty is quantified using 1,000 empirical block bootstrap resamples across active baseline, active intervention, sham baseline, and sham intervention simultaneously, deriving the aligned $95\%\text{ CI} = [RRI_{2.5}, RRI_{97.5}]$.

### D. Phantom Baseline-Subtracted Delta Evaluation
To prevent harmless DC offsets on dummy loads from generating false-positive interference alarms, phantom controls evaluate the dynamic change:

$$\Delta_\text{phantom} = \mu_\text{phantom\_active} - \mu_\text{phantom\_baseline}$$

If $|\Delta_\text{phantom}| > 0.40 \cdot |\Delta_\text{bio}|$ and $|\Delta_\text{phantom}| > 0.10$, the trial is flagged with `DIRECT_EM_INSTRUMENTATION_PICKUP` and penalized.

### E. Evidence Status Categorization:
* **`REPEATABLE_DIFFERENCE`:** Permutation $p_\text{perm} < 0.01$, bootstrap $CI_\text{low} > 0.20$, repeatability $> 0.75$, $|d| > 0.80$, and artifact risk $< 0.20$.
* **`EXPLORATORY`:** Measurable contrast detected ($p_\text{perm} < 0.05$, $|d| \ge 0.20$), clean phantom control, awaiting trial replication.
* **`INCONCLUSIVE`:** No statistically significant contrast from sham or baseline ($p_\text{perm} \ge 0.05$ or $|d| < 0.20$).
* **`ARTIFACT_LIKELY`:** Detected response mirrors electronic phantom delta or high near-field RF interference ($\text{Risk}_\text{EM} \ge 0.35$).
