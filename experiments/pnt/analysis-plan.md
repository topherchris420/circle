# Quantum PNT Statistical Analysis Plan

> **NOTICE**: ENGINEERING REVIEW ONLY. Formal statistical analysis plan for quantum-augmented inertial navigation.

---

## 1. Primary Estimands

1. **Position Root-Mean-Square Error (RMSE)**:
   $$\text{RMSE}_{\text{pos}} = \sqrt{\frac{1}{N} \sum_{k=1}^N \| \mathbf{r}_k - \hat{\mathbf{r}}_k \|^2}$$

2. **Velocity RMSE**:
   $$\text{RMSE}_{\text{vel}} = \sqrt{\frac{1}{N} \sum_{k=1}^N \| \mathbf{v}_k - \hat{\mathbf{v}}_k \|^2}$$

3. **Drift Rate**:
   $$\text{Drift} = \frac{\| \mathbf{r}_N - \hat{\mathbf{r}}_N \|}{\Delta t_{\text{total}}}$$

4. **Quantum Improvement Ratio (QIR)**:
   $$\text{QIR}_{\text{pos}} = \frac{\text{RMSE}_{\text{pos, classical}}}{\text{RMSE}_{\text{pos, quantum}}}$$

---

## 2. Filter Consistency Diagnostics

- **Normalized Estimation Error Squared (NEES)**:
  $$\epsilon_k = (\mathbf{x}_k - \hat{\mathbf{x}}_k)^T \mathbf{P}_k^{-1} (\mathbf{x}_k - \hat{\mathbf{x}}_k)$$
- **Normalized Innovation Squared (NIS)**:
  $$\epsilon_{z,k} = \boldsymbol{\nu}_k^T \mathbf{S}_k^{-1} \boldsymbol{\nu}_k$$

---

## 3. Clock Stability Estimands

- **Overlapping Allan Deviation**:
  $$\sigma_y^2(\tau) = \frac{1}{2 (N - 2m + 1)} \sum_{k=1}^{N - 2m + 1} (\bar{y}_{k+m} - \bar{y}_k)^2$$
