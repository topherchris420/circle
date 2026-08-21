# Emergence Statistical Analysis Plan

> **ENGINEERING REVIEW ONLY** ? Experimental analysis plan. Not certified for clinical or medical application.

## 1. Primary Estimand

The primary estimand is the normalized discovery density difference ($\Delta D$) between active physiological/resonance channel pairs and the matched null control channel:

$$\Delta D = D_{	ext{active}} - D_{	ext{control}}$$

where $D = rac{1}{T} \sum_{t=1}^T \mathbf{1}_{\{|r(t)| > 	heta_{	ext{calibrated}}\}}$.

---

## 2. Statistical Testing & Significance Thresholds

- **Null Hypothesis ($H_0$):** Active channel pair correlation rates do not exceed null control expectations ($E[\Delta D] \le 0$).
- **Alternative Hypothesis ($H_1$):** Active channel pair correlation rates exceed null control expectations ($E[\Delta D] > 0$).
- **Family-Wise Error Rate:** Bounded at $lpha = 0.05$ using Holm-Bonferroni correction over all $inom{4}{2} = 6$ pairwise comparisons.
- **Autocorrelation Adjustment:** Correlation windows account for effective sample size $N_{	ext{eff}} = N / (2	au + 1)$ where $	au$ is the estimated lag-1 autocorrelation time.

---

## 3. Environmental Moderation Analysis

- Regress cumulative discovery count against active environmental moderators ($K_p$ geomagnetic index, lunar phase alignment, local sidereal time, solar X-ray flux, and discrete coherence windows).
- Compute variance inflation factors (VIF) to detect collinearity between solar and geomagnetic covariates.
