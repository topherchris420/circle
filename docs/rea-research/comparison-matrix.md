# Comparison matrix: commercial references vs. the Resonance Workbench

Compiled from the per-product reports in this directory (see each report's
evidence log for claim-level sources and classifications). "CIRCLE (Resonance
Workbench)" columns describe what this repository implements and preserves,
not aspirations.

## Interaction patterns

| Pattern | NextSense | Sychedelic | Healium | Affectable Sleep | Neurode | BioChord | CIRCLE Resonance Workbench |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Physiological dashboard | Sleep charts, drift-off time, slow-wave count | Live BPM + named state on slider | Aura light in VR; provider dashboard | Gauge with baseline + boost lines | "See your brain" maps | — (SDK) | Synchronized HR, HRV (RMSSD, labeled), respiration, EDA, motion, quality per evaluation |
| Beat-interval handling | Not public | PPG-derived state | HR/HRV from wearable | Not public | Not public | Interval stream in, HRV ≥ 1 Hz | Beat times from exported evidence; windows labeled, withheld when too few good intervals |
| Adaptive audio | Pink-noise slow-wave pulses; Focus/Nap modes | Soundscape adapts; binaural beats first | Ambient only | Slow-wave tones | — | Timbre/density/space mapped from HRV | Original procedural synth: intensity/brightness/tempo/spatial from arousal index and features; bounded, quality-gated |
| Breathing guidance | — | Implicit in soundscape | Guided sessions | — | — | — | Paced-breathing swell at a period clamped to 4–10 breaths/min, from measured respiration when causal |
| Visual feedback field | Charts | State slider | Diegetic Aura that brightens on relaxation | Two-line gauge | Intensity chooser | — | Cymatic-inspired canvas rings driven by explicit parameter mapping; every mapping inspectable |
| Quality/sensor status | EEG + fit check at setup | Conductivity gate (< 10 kΩ), disabled CTA | Not documented publicly | Sensor-contact screens with fit guidance | Not documented publicly | Clean/quality-check stage | Quality gate reasons per evaluation (motion, contact, staleness, saturation); events hold and say why |
| Session designer | Mode presets (Focus/Nap/Sleep) | Onboarding ritual + locked/unlocked Boost | 4-step flow | Nightly flow | Not public | API-level | 8-step guided designer: scenario → arm → modalities → safe limits → consent → run → inspect → export |
| Active vs. sham | Not offered | Not offered | Baseline-relative score | Baseline + boost lines | Not public | Not public (no public trials) | Same-seed active/sham arm by design; matched comparison built in |
| Decision evidence | "Boosts used" counter | Boost locked/unlocked states | Score internals opaque | Boost timeline | Not public | Latency/update budgets stated | Full ledger: input cutoff, features, gate outcomes, why-text, execution chain, replay verdict |
| Consent for feedback | Implicit (mode choice) | Implicit (session start) | Implicit | Implicit | Not public | On-device processing | Explicit audio consent recorded with the session; stop/mute always visible |
| Longitudinal view | Trends (week/month/3-month) | Insights timeline | Provider dashboard | Morning review | Monthly tracking view | — | Session history with scorecards and audit verdicts |
| Data export / local control | Vendor cloud | Roadmap only | Provider exports | Not public | Apple Health correlations | 100% on-device | Everything local by default; full evidence bundle download (zip) with hashes |

## Scientific-AI references

| Theme | Autoscience | Inherent Labs | How CIRCLE uses it |
| --- | --- | --- | --- |
| Autonomous experimentation | Carl (ICLR 2025 workshop review), Mira (Kaggle silver) | Faraday (RL-trained replication) | R.A.I.N. may *propose* experiments through validated protocol manifests; CIRCLE's deterministic checks and a human authorization remain the gate |
| Evaluation | Hard VERIFY stage against the user's own baseline | Auto-generated rubrics validated against human raters | Preregistered software benchmarks ([`resonance-benchmark.json`](../resonance-benchmark.json)) with expected results stated before runs |
| Replication | — | "Training to replicate" curriculum | Same seed → byte-identical timeline, feedback digests, and audit verdict; replay verdicts named |
| Human oversight | Voluntary paper withdrawals; human-edited citations | Human-in-the-loop commitments | Consent and safe limits are user actions recorded with the session; the controller never defers to a proposer |

## What the references rarely provide together

1. **Explainable feedback decisions.** Commercial products show *that* they
   responded (a boost counter, a golden aura, an unlocked state); CIRCLE shows
   *why* — measurements available, input cutoff, gate outcomes, the rule text,
   and whether replay reproduces the decision.
2. **Reproducibility.** None of the studied products publishes a way to replay
   a session from its raw evidence. CIRCLE's export → audit → timeline chain
   is deterministic and byte-comparable.
3. **Honest degradation.** Contact loss in commercial apps is a setup problem;
   in CIRCLE, degraded evidence mutes the feedback, holds the parameters, and
   names the reasons in the record.
4. **Active-versus-sham honesty.** Wellness scoring against a self-chosen
   baseline (Healium's score, Affectable's boost) is susceptible to baseline
   inflation; CIRCLE pairs every active arm with a matched sham.

## Limits of this comparison

- The matrix reflects **publicly observable** behavior only; closed-source
  internals are marked INFERRED or UNVERIFIED in the per-product reports.
- Commercial products run on real hardware with real people; the Resonance
  Workbench currently renders **simulated** evidence. That distinction is
  preserved everywhere in this repository.
- "Not public" means not publicly documented at the time of investigation, not
  nonexistent.
