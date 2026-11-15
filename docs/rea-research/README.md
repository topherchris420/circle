# REA research: methodology and evidence log

This directory records a lawful, publicly observable investigation of seven
products and two research organizations, conducted with the
[REA reverse-engineering framework](https://github.com/morluto/rea) as the
methodology guide. Its purpose was **not** to copy commercial software, but to
learn which interaction patterns earn their place in CIRCLE's Resonance
Workbench, and which limitations CIRCLE can answer with transparency,
extensibility, and reproducibility.

## How the investigation was run

- **Host and tools.** Windows 11 (ARM64). REA `rea-agents` 6.8.0 was
  installed and registered for the OpenCode coding agent (`rea setup --client
  opencode`; unrelated agent configurations were preserved). REA's `doctor`
  check reports that native Ghidra decompilation is unavailable on
  Windows/ARM64, so the investigation used REA-supported **website and
  documentation observation** (public pages, app-store listings, published
  case studies, press, and independent reviews) rather than binary analysis.
- **Lawful observation only.** No authentication, DRM, paywalls, or security
  controls were bypassed; no proprietary assets, credentials, or private data
  were extracted. No commercial application was executed locally. Where an
  app requires hardware or an account, that limitation is recorded.
- **Classification.** Every finding is marked:
  - **OBSERVED** — directly demonstrated on a publicly accessible page.
  - **DOCUMENTED** — described in official documentation or listings.
  - **INFERRED** — a plausible technical explanation, not independently confirmed.
  - **UNVERIFIED** — insufficient evidence.

## Reports

| Product / lab | Report | What it is |
| --- | --- | --- |
| NextSense | [`nextsense.md`](nextsense.md) | Ear-EEG buds with brain-responsive audio (Alphabet X lineage) |
| Sychedelic | [`sychedelic.md`](sychedelic.md) | tDCS + PPG + adaptive-audio headphones (India, pre-order) |
| Healium | [`healium.md`](healium.md) | Immersive VR biofeedback with responsive environments |
| Affectable Sleep | [`affectable-sleep.md`](affectable-sleep.md) | Closed-loop slow-wave auditory stimulation EEG headband companion |
| Neurode | [`neurode.md`](neurode.md) | fNIRS + tRNS headband with brain-state visualization |
| BioChord | [`biochord.md`](biochord.md) | Heartbeat-to-audio SDK (interval stream in, adaptive audio out) |
| Autoscience | [`autoscience.md`](autoscience.md) | Autonomous research agents (Carl, Mira) |
| Inherent Labs | [`inherent.md`](inherent.md) | AI scientists trained to replicate research (Replica, Faraday) |

A cross-product view is in [`comparison-matrix.md`](comparison-matrix.md).

## What this investigation is not

- It is not a security audit, a competitive teardown, or a claim about product
  quality. Products are cited only for their publicly observable behavior.
- It is not a claim that CIRCLE replicates any product. Every implemented
  behavior is an original workbench feature; the reports name the patterns that
  motivated them.
- Findings marked INFERRED or UNVERIFIED are hypotheses about closed-source
  behavior, not facts.

## Aggregate evidence log

The per-report evidence logs use this shape:

| Claim | Classification | Source |
| --- | --- | --- |
| (one row per claim) | OBSERVED / DOCUMENTED / INFERRED / UNVERIFIED | URL |

Across the seven product reports: the strongest publicly documented evidence
bases were NextSense (live help center, spec pages, clinical-research page,
multiple independent hands-on reviews) and Healium (published session model,
provider dashboard, RCT citation). The weakest were Neurode (marketing
screenshots and press; no operable public app demo) and BioChord (young
company, documented signal-chain architecture, no public demo). Affectable
Sleep's richest source was a designer's public case study, which documents the
companion app as design artifacts rather than shipped software.
