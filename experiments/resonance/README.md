# CIRCLE Resonance Experimental Framework

> **ENGINEERING REVIEW / BENCH VALIDATION ONLY — NOT CERTIFIED FOR CLINICAL OR HUMAN-CONNECTED USE.**

## Purpose & Scope

The CIRCLE Resonance research module provides an empirical, evidence-before-inference experimental framework to investigate:
1. Whether externally driven resonant electromagnetic/acoustic fields, geometric cavity proportions, and multi-frequency relationships produce measurable, reproducible changes in CIRCLE's synchronized sensor streams.
2. How to rigorously isolate true physiological or environmental changes from electromagnetic interference (EMI), capacitive pickup, RF rectification, or thermal drift on CIRCLE's analog front-ends.

## Core Architectural Invariants

1. **Absolute Electrical Isolation**: The resonance chamber, amplifiers, signal generators, and antenna structures are strictly decoupled from CIRCLE's `BAT_HUMAN` domain. All communications occur via the isolated laboratory synchronization barrier (`LAB_ISO` domain, ISOW7742 5 kVrms).
2. **Conservation of Energy**: All power measurements enforce $P_\text{out} \le P_\text{in}$. Nonlinear spectral products (harmonics, intermodulation, sum/difference frequencies, mode splitting) are analyzed as ordinary physical conversions with measured thermal and radiative dissipation.
3. **Epistemological Integrity**: Metaphysical or speculative labels ("prana", "subtle energy", "vital force") are categorized strictly as `HYPOTHESIS_LABEL` elements within the data model. Internal analysis relies on objective operational metrics, such as the `Resonance Response Index (RRI)` and Cohen's $d$ effect sizes.

## Repository Contents

* [`protocol.md`](protocol.md): Standard experimental trial sequence (Baseline $\to$ Sham $\to$ Active $\to$ Washout) and blinding methodology.
* [`controls.md`](controls.md): Specification of geometric controls ($\phi$ vs equal vs random vs sham; dual tetrahedron vs sphere vs cube vs none) and electronic phantom loads.
* [`analysis-plan.md`](analysis-plan.md): Pre-registered statistical analysis plan, artifact discrimination criteria, and uncertainty quantification.
* [`configurations.example.json`](configurations.example.json): Machine-readable configuration matrix for reproducible bench test runs.
