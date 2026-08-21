# CIRCLE Emergence Research Experiments

> **ENGINEERING REVIEW ONLY** ? Experimental research protocols. Not certified for clinical, medical, or human-connected use.

## Overview

The **CIRCLE Emergence Module** integrates the **ATOM (Analyses, Targets, Operators, Moderators)** framework from the IONS-X Deep Emergence Lab into the CIRCLE platform. It provides a multi-agent dynamical sandbox for investigating how coupled physiological signals (EDA, PPG optical raw, IMU acceleration) and resonance chamber fields develop emergent cross-channel correlations under real-world and synthetic environmental moderation.

---

## Experiment Presets

| Experiment Bundle | Intended Research Application | Key Hyperparameters |
| :--- | :--- | :--- |
| `balanced` | Standard empirical baseline across multimodal sessions. | 300 agents, 128x128 grid, window=50, threshold=0.32 |
| `quick` | Rapid verification runs and automated test harness. | 50 agents, 64x64 grid, 60 frames, 4 samples/frame |
| `arv` | Associative Remote Viewing and delayed-signal detection. | Memory=500, Window=80, Lags=(15,30,60,120), Threshold=0.28 |
| `coherence` | Environmental coherence study with extended persistence. | 400 agents, Threshold=0.26, Decay=0.997 |
| `dense-agents` | High operator density & spatial clustering investigations. | 800 agents, 96x96 grid, 200 frames |

---

## File Structure

- [`protocol.md`](protocol.md): Step-by-step experiment execution procedure.
- [`analysis-plan.md`](analysis-plan.md): Statistical analysis and graph verification methodology.
- [`controls.md`](controls.md): Blinding, null control baselines, and sham specifications.
- [`configurations.example.json`](configurations.example.json): Verified configuration examples.
