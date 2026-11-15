# Affectable Sleep — Evidence report

Affectable Sleep is a consumer sleep-neurotechnology product from Affectable Labs Inc. (Sydney, Australia; co-founder/CEO Pete Field). It is a thin, soft EEG headband that monitors brain activity during sleep and delivers closed-loop phase-targeted auditory stimulation ("UltraSleep™") through a built-in bone-conduction speaker — millisecond-scale sound pulses, timed to detected slow-wave activity, intended to boost the amplitude of slow-wave (deep) sleep rather than extend sleep duration. An iOS companion app (designed by Anastasia Kashkinova as sole experience designer, Aug 2025–Aug 2026) presents results next morning. As of late 2026 the company is in pre-order phase (headband + UltraSleep subscription bundle, shipping Q4 2026, USA/Australia only), with the first app beta cohort planned alongside the first headband wave to early testers.

## Sources consulted

- https://affectablesleep.com — homepage: product framing ("personalized, precisely timed micro-auditory neurostimulation"), comfort claims, benefit pillars.
- https://affectablesleep.com/how-it-works — the richest technical-UX source: 7-step closed-loop description, FAQ on stimulation sound/behavior, "view your stimulation response and health sleep data in the app", research library of 50+ papers.
- https://affectablesleep.com/about — company stage (prototype 1 → prototype 2 → beta testing → production), team, design philosophy ("we don't just track your sleep, we Affect it").
- https://anastasia-kas.com/work/affectable-sleep/ — design case study (primary UX source): full companion-app design process, onboarding, gauge visualization, sensor-contact states, data breakdown screen, two rounds of user research (Dec 2025, Jan 2026), final light/dark designs.
- https://affectablesleep.com/product-purchase-subscription (via websearch) — pre-order details: iOS/iPhone requirement, subscription bundle, 30-day guarantee, Q4 2026 shipping.
- https://blog.affectablesleep.com/p/most-sleep-tech-doesnt-improve-your (via websearch) — company blog: Sydney-based startup, pre-orders opened Aug 2025.
- https://news.ycombinator.com/item?id=45878893 (via websearch) — founder Show HN (Nov 2025): real-EEG demo video, within-night stim/sham protocol, headband design goals vs Dreem/Philips.
- https://news.ycombinator.com/item?id=40806227 (via websearch) — earlier founder HN thread: PTAS terminology, positioning vs "fall asleep faster" devices.
- https://www.reddit.com/r/affectablesleep/comments/1morb7q/... (via websearch) — company status post (Aug 2025): independent 3rd-party researchers validating devices since Feb 2025, pre-orders launched.
- https://www.nssn.org.au/news/2025/2/14/transforming-sleep-eeg-headband-innovation-features-at-nssn-sensing-industry-connect (via websearch) — CEO interview explaining slow-wave mechanism and stimulation logic.
- https://www.nytimes.com/wirecutter/reviews/brain-wave-tracking-sleep-wearables/ (via websearch) — market context (Muse, Elemind, NextSense); does not cover Affectable directly.

## Findings

### Onboarding / documented onboarding flow

- **DOCUMENTED** (case study, "Key Screens" + onboarding flow image): "Onboarding walks users through device pairing and fitting." The onboarding flow mockup shows a multi-step sequence for connecting and fitting the headband.
- **OBSERVED** (case study images): an onboarding-flow screen sequence exists as designed artifacts (pairing + fitting steps); individual screen contents were readable only as images in the case study.
- **DOCUMENTED** (about page): headband design requirement — "put on easily while going to bed, without fuss," work with different hair styles, head sizes, and anthropometric factors.
- **INFERRED**: pairing is a Bluetooth-style flow to an iPhone (pre-order page states "Affectable requires an iPhone running iOS"), but the exact pairing UX (scanning, codes, retry) is not described.

### Sensor-contact states

- **DOCUMENTED** (case study, Key Screens): "Sensor connection screens handle the moments when electrodes aren't making proper contact, with guidance to resolve fit." A dedicated screen-set exists for poor electrode contact with fit-resolution guidance.
- **OBSERVED** (case study image "AffectableSleep-Device-States"): a designed screen family for device/sensor states showing contact problems and remediation.
- **DOCUMENTED** (about page): sensor placement and methods were an explicit prototype-2 design problem (different hairstyles, head sizes).
- **INFERRED**: contact-state handling likely distinguishes which sensor/electrode lost contact, since the headband uses multiple "soft flexible sensors"; not confirmed in text.

### Simplified physiological displays (the gauge)

- **OBSERVED** (case study, final designs and selected-direction images): the central dashboard is a gauge-style visualization with two overlaid lines — nightly sleep restoration and the UltraSleep boost on top of it.
- **DOCUMENTED** (case study): verbal label system of Baseline / Medium / High for the combined value; deliberately no "Low" label "to not let it affect how the users felt." Evaluative scores, filled circles/rings, and colour-coded ratings were explicitly rejected as conventions.
- **DOCUMENTED** (case study, research round 2): the gauge was initially multi-coloured across Low/Medium/High sections and was flagged as too complex by biohackers; simplified to a single-colour treatment before beta.
- **DOCUMENTED** (case study): a "+xx%" boost figure — never negative — was added after users in both research rounds asked for "a concrete number to hold onto."
- **DOCUMENTED** (case study, research round 1): a timeline under the main gauge shows when UltraSleep boosts happened during the night; an HRV area was present and initially confusing between peak and nightly comparison, later improved.
- **INFERRED**: the design goal is "restoration and improvement, not judgement" — avoiding the nocebo effect of bad scores; this is a stated design rationale, and its effect on users is not independently validated.

### Layered data exploration

- **DOCUMENTED** (case study, Key Screens): "A data breakdown screen sits behind the main view for users — primarily biohackers — who want granular access to sleep stages, time, and UltraSleep session detail; intentionally separated so it doesn't dominate the experience for those who don't need it."
- **OBSERVED** (case study image "AffectableSleep-DataBreakdown"): a dedicated granular breakdown screen exists as a designed artifact.
- **DOCUMENTED** (case study): info drawers were added throughout the app after research showed users wanted in-context explanations without leaving their current view; tooltips and contextual copy were requested by biohackers.
- **DOCUMENTED** (case study): a device-status screen surfaces battery level and hardware state at a glance; a personalised streak + insights area was added in the final iteration.
- **INFERRED**: the layering (glanceable gauge → drawer explanations → full breakdown screen) is a three-tier information architecture; exact contents of the breakdown (which metrics beyond sleep stages and UltraSleep detail) are not enumerated in text.

### Presenting complex measurements without overwhelming users

- **DOCUMENTED** (case study, core design challenge): the explicit brief was to "invent a new visual language for sleep" that avoids score-anxiety; sleep apps' rings/scores were treated as a liability because "a 'bad' score on a night the headband was actively helping would undermine trust in the device."
- **DOCUMENTED** (case study, user research): two cohorts shaped this — young parents/premenopausal women (hours-slept as headline metric "actively harmful" for them) and biohackers (wanted numbers, HRV, sleep-stage terminology). Both struggled with purely verbal labels and wanted some quantification — hence +xx%.
- **DOCUMENTED** (website FAQ): the company's own framing that "trackers ask you to chase better scores. We focus on making your sleep better, then show you how we did it."
- **INFERRED**: the persona split (feeling-focused majority vs number-hungry biohackers) is the organizing principle of the whole information architecture; the app serves both via layering rather than modes.

### Device connection, stimulation behavior, and feedback

- **DOCUMENTED** (how-it-works): closed loop is: monitor EEG → detect slow-wave patterns → emit micro-pulse of sound via bone-conduction speaker, "precisely adapted to your brain activity at that moment" → brain responds → headband measures response in real time confirming changes in brain activity and autonomic signals. Each detection-to-response cycle is "under a second," occurring "thousands of times per night."
- **DOCUMENTED** (FAQ): pulses last less than one-tenth of a second, not delivered in rhythm/beat, volume-matched in real time to brain activity — "loud enough for your brain to respond, not loud enough to wake you." Users are unlikely to hear or feel anything.
- **DOCUMENTED** (founder, HN): stimulation runs in a within-night stim/sham protocol in their own testing; observed effects "match or exceed" 50+ published studies (self-assessed).
- **DOCUMENTED** (pre-order page): app shows "stimulation response and health sleep data" the next morning — feedback is retrospective (morning review), not live during sleep.
- **INFERRED**: unlike daytime closed-loop products, there is no in-the-moment user-facing feedback; the "feedback transition" that matters is night→morning, from unconscious intervention to explained outcome.

### Loading/error states and status

- **OBSERVED** (case study image "AffectableSleep-DeviceStatus"): a device-status screen with battery level and hardware state exists as a designed artifact.
- **DOCUMENTED** (case study): sensor-contact screens with fit guidance (see above) are the primary error-state handling.
- **UNVERIFIED**: specific loading states, connection-loss handling during the night, or sync-failure UX — not described in accessible text.

### Research grounding and status

- **DOCUMENTED** (how-it-works research library): 50+ peer-reviewed studies in slow-wave enhancement listed with DOIs (Parkinson's RCT 2026, Alzheimer's at-home 2024, chronic insomnia pilot 2024, memory/amyloid in older adults, MEG neurophysiology of CLAS, home-based phase-locked pilot).
- **DOCUMENTED** (Reddit/Show HN): independent 3rd-party researchers have used Affectable Ultrasleep in their own trials since Feb 2025 (company claim); headband validated by them (company claim).
- **DOCUMENTED** (pre-order page): headband sold only bundled with UltraSleep subscription; ships Q4 2026; USA and Australia only; requires iPhone.
- **UNVERIFIED**: independent published results specifically of the Affectable device (as opposed to the underlying PTAS literature); no third-party hands-on review of the shipped product was found.

## Evidence log

| Claim | Classification | Source URL |
|---|---|---|
| iOS companion app designed ground-up Aug 2025–Aug 2026, beta late 2026 | DOCUMENTED | https://anastasia-kas.com/work/affectable-sleep/ |
| Onboarding walks through device pairing and fitting | DOCUMENTED | https://anastasia-kas.com/work/affectable-sleep/ |
| Central gauge: two overlaid lines (restoration + UltraSleep boost) | OBSERVED (design images) | https://anastasia-kas.com/work/affectable-sleep/ |
| Verbal labels Baseline/Medium/High; "Low" deliberately omitted | DOCUMENTED | https://anastasia-kas.com/work/affectable-sleep/ |
| "+xx%" never-negative boost figure added per user request | DOCUMENTED | https://anastasia-kas.com/work/affectable-sleep/ |
| Gauge simplified from multi-colour to single colour after biohuzzer feedback | DOCUMENTED | https://anastasia-kas.com/work/affectable-sleep/ |
| Data breakdown screen behind main view: sleep stages, time, UltraSleep session detail | DOCUMENTED | https://anastasia-kas.com/work/affectable-sleep/ |
| Sensor-contact screens with fit-resolution guidance for poor electrode contact | DOCUMENTED | https://anastasia-kas.com/work/affectable-sleep/ |
| Device status screen: battery level and hardware state at a glance | OBSERVED (design images) | https://anastasia-kas.com/work/affectable-sleep/ |
| Info drawers/tooltips added for in-context explanations after both research rounds | DOCUMENTED | https://anastasia-kas.com/work/affectable-sleep/ |
| Nightly timeline of when boosts occurred, under main gauge | DOCUMENTED | https://anastasia-kas.com/work/affectable-sleep/ |
| HRV area initially confusing (peak vs nightly comparison), later improved | DOCUMENTED | https://anastasia-kas.com/work/affectable-sleep/ |
| Closed loop: EEG → pattern detection → <100 ms bone-conduction pulse → real-time response measurement; thousands/night | DOCUMENTED | https://affectablesleep.com/how-it-works |
| Pulses <0.1 s, not rhythmic, real-time volume-matching; unlikely heard/felt | DOCUMENTED | https://affectablesleep.com/how-it-works |
| Morning app shows "stimulation response and health sleep data" | DOCUMENTED | https://affectablesleep.com/how-it-works |
| Company stage: beta testing; pre-orders; Q4 2026 shipping; USA/Australia; iPhone required | DOCUMENTED | https://affectablesleep.com/about , product-purchase page |
| Two prototypes: lab prototype → headband with EEG sensor placement work | DOCUMENTED | https://affectablesleep.com/about |
| 50+ peer-reviewed slow-wave-enhancement studies cited with DOIs | DOCUMENTED | https://affectablesleep.com/how-it-works |
| Within-night stim/sham testing with real EEG demo video (founder) | DOCUMENTED (self-claimed) | https://news.ycombinator.com/item?id=45878893 |
| Independent 3rd-party researchers validating/using devices since Feb 2025 | DOCUMENTED (company claim) | https://www.reddit.com/r/affectablesleep/comments/1morb7q/ |
| Onboarding pairing UX details (scanning, retry, night-time disconnect handling) | UNVERIFIED | — |
| Independent published results for the Affectable device itself | UNVERIFIED | — |

## Missing evidence and inaccessible functionality

- The app exists only as designed artifacts (Figma→SwiftUI prototypes) and is not publicly released; the case-study images are the only view of screens. No live app, no App Store listing found.
- Full functionality requires the Affectable headband (pre-order, not yet broadly shipped as of this research) plus an iPhone and an UltraSleep subscription.
- Screen-image details (exact wording, drawer contents, breakdown metrics list) are only partially legible in case-study images; some specifics remain INFERRED.
- No public documentation of the stimulation algorithm parameters (detection thresholds, volume-matching rule, safety cutoffs) beyond qualitative descriptions.
- No independent hands-on review of the headband or app was found; Wirecutter's July 2026 round-up covers competitors (Muse, Elemind, NextSense) but not Affectable.
- Founder's claims about effect sizes matching published literature are self-assessed; third-party trial results are not yet published.

## Relevance to CIRCLE

- **Physiological dashboard**: the gauge-with-two-lines (baseline + intervention boost) is a directly transferable pattern for CIRCLE's active-vs-sham comparisons — showing what the physiology did on its own versus what the closed-loop controller added. CIRCLE can adopt the "never-negative-only boost framing" cautiously, but should go further by letting researchers toggle between the simplified gauge view and raw signals (transparency over reassurance).
- **Simplified physiological displays**: the deliberate rejection of scores/rings/judgement labels (Baseline/Medium/High, no "Low") is a strong anti-nocebo pattern for CIRCLE's participant-facing views — especially relevant since CIRCLE's consent gate and participant experience should not induce score anxiety. CIRCLE's researcher-facing views can stay dense while participant views adopt the label discipline.
- **Layered data exploration**: the three-tier layering (glanceable gauge → in-context info drawers → granular breakdown screen "behind" the main view) is an excellent model for CIRCLE's evidence explorer: default simplicity with a deliberate path to depth, rather than two separate expert/novice modes.
- **Session designer**: Affectable's design shows the value of explaining *what the device did for you* (boost timeline, +xx%). CIRCLE's session designer can adopt per-intervention "what happened and why" summaries — with the improvement that CIRCLE exports the exact gate decisions and stimulation parameters for replay audit, which Affectable does not publicly offer.
- **Sensor-contact states**: dedicated contact-failure screens with fit-resolution guidance map directly onto CIRCLE's signal-quality gates for simulated PPG/EDA/IMU streams; CIRCLE should show *which* stream failed and the remediation, and log it in the evidence export.
- **Adaptive audio engine**: Affectable's real-time volume-matched, phase-locked micro-pulses are the sleep-side analog of CIRCLE's closed-loop controller; CIRCLE could simulate a phase-locked auditory actuator driven by simulated EEG-like slow waves, with the volume-matching rule exposed and editable.
- **What CIRCLE can do better**: reproducibility and transparency. Affectable's UI explains outcomes but the algorithm is proprietary and unpublished; CIRCLE can ship every session as a replayable evidence bundle (raw streams + controller decisions + parameter versions), and make active-vs-sham a first-class, user-visible toggle rather than an internal protocol detail.

## Suggested original implementation ideas for CIRCLE

1. **Two-line intervention gauge**: a dashboard component plotting baseline physiology and controller-added boost as overlaid curves with a derived "+xx%" delta — plus a toggle that reveals the raw streams and gate events behind each point.
2. **Non-judgemental label sets**: configurable qualitative labels for state zones that exclude negative evaluative terms by default (Baseline/Medium/High pattern), with an option for researchers to override — preserving honesty without nocebo framing in participant views.
3. **Contact-state screen family**: for each simulated sensor, a dedicated "not making proper contact" state with physical remediation guidance (mirroring Affectable's sensor-connection screens), recorded as quality-gate events in the session log.
4. **Info-drawer layering in the evidence explorer**: every metric on the main dashboard opens an in-context drawer (definition, current gate thresholds, recent values) without navigation; a separate "breakdown" view holds full per-phase and per-stream detail for power users.
5. **Night-intervention timeline strip**: a compact timeline under the main visualization showing when each closed-loop intervention fired and the physiological response that followed — the auditable version of Affectable's boost timeline.
6. **Morning-review style session recap**: after each CIRCLE session, an auto-generated recap card: what the controller did, when, what changed, and what would have happened under sham (counterfactual line from the same session's replay) — directly supporting active-vs-sham comparisons.
7. **Persona-adaptive density**: a user-preference that adjusts dashboard density between "feeling-focused" (labels, deltas) and "biohacker" (HRV/stage terminology, raw numbers) modes, informed by Affectable's documented finding that both cohorts wanted quantification but different amounts of context.
