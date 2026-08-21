# Emergence Controls and Blinding Strategy

> **ENGINEERING REVIEW ONLY** ? Experimental controls specification. Not certified for clinical or medical application.

## 1. Control Architectures

To ensure that discovered graph edges represent genuine cross-channel coupling rather than mathematical or sampling artifacts, CIRCLE implements four distinct control tiers:

1. **Internal Channel 3 Null Baseline:** Every target field embeds an uncorrelated Gaussian noise channel ($N(0, 1)$). Operator discoveries involving Channel 3 establish the empirical false-positive rate under identical spatial random-walk sampling.
2. **Phase-Scrambled Surrogate Controls:** Fourier transform of empirical biosignals with randomized phase spectra preserves power spectral density while destroying temporal cross-channel coherence.
3. **Time-Shifted Asynchronous Baselines:** Signals shifted by $T_{	ext{offset}} > 5 	imes W$ break causal synchrony while maintaining channel variance and autocorrelation characteristics.
4. **Hardware Phantom & Sham Dummy Loads:** Matched $50\ \Omega$ load controls isolate radiated RF/EMI pickup from physiological responses.

---

## 2. Double-Blind Tokenization

All empirical emergence evaluations employ cryptographically sealed trial manifests with opaque trial tokens (`TRIAL-XXXXXXXX`). Condition codes are revealed only after analysis routines finalize discovery graphs and commit SHA-256 result digests.
