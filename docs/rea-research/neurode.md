# Neurode — Evidence report

Neurode is a brain-sensing headband plus companion app from Neurode Pty Ltd (Sydney, Australia; co-founders Nathalie Gouailhardou, neuroscientist, and Damian Sofrevski, engineer) targeting adult ADHD and executive function. The headband combines fNIRS (functional near-infrared spectroscopy) brain monitoring — 152 channels per the current site, with a 600-channel research variant shown at NeurIPS 2026 — with tRNS (transcranial random noise stimulation, 0.55–1.55 mA). Per the project directive, this report focuses on visualization and reporting, not stimulation controls. As of late 2026 the product is sold as an early-access/beta platform ($999 + $29/month membership, US adults only, iPhone 2018+, invitation/beta framing), explicitly not yet FDA/TGA-authorized, with an iOS app (Medical category, 5.0★ from 14 ratings, v2.43.0 as of July 2025) usable only with the headband. Its marketing centers on "seeing your brain in real time" — live brain-activity visualization, session tracking, focus insights, streaks, and Apple Health correlations.

## Sources consulted

| URL | Contribution |
|---|---|
| https://neurodelabs.com | Homepage: how-it-works steps, tech specs (fNIRS 152 channels, tRNS range), app-screenshots carousel (intensity chooser, insights, progress tracking, Apple Health merge), pricing/membership, eligibility, FAQ, testimonials incl. live-brain-view claims, regulatory disclaimer |
| https://neurodelabs.com/about | Company mission, founders' backgrounds, "Neurode Wave" name, roles, values |
| https://apps.apple.com/us/app/neurode/id6449830978 | App Store listing: description (20-min sessions, brain monitoring + stimulation, tracks activity change over time), Medical category, privacy labels, version history |
| https://www.neurode.com.au/ (via search result) | Earlier site copy: "See your brain in real time", "an MRI in your pocket", track progress daily |
| https://techcrunch.com/2024/09/10/neurode-wants-to-treat-and-track-adhd-symptoms-through-a-wearable-headband/ | Founding story, fNIRS origin at Bionics Institute, real-time data feedback via app |
| https://newatlas.com/science/adhd-autism/adhd-device-neurode | Real-time data feedback, PFC change tracking over time, "MRI in your pocket" quote, Rae AI assistant for to-do lists, funding (A$5.3M) |
| https://medium.com/stoic-vc/investment-notes-neurode-db67856ca09a | Investor memo: closed-loop claim (fNIRS diagnostic informs tRNS modulation), app-guided sessions with real-time insights, IRB/class-II framing |
| https://neurips.cc/virtual/2026/loc/sydney/174110 | NeurIPS 2026 demo: 600-channel fNIRS-EEG headband, live visualization of oxy/deoxy-hemoglobin projected onto an anatomical brain map, real-time attention decoding (internal vs. external locus of attention) |
| https://www.itechguides.com/world-first-adhd-headband-treats-symptoms-in-20-minutes-per-day-what-neurode-actually-proves | Independent critical assessment: early-access status, pricing, evidence gaps |
| https://www.youtube.com/watch?v=s8breQwGbls (First Principles interview, via search) | 152-channel fNIRS array description |
| https://apps.apple.com/us/app/neurode/id6449830978 reviews (via search) | User review: daily "bandwidth" monitoring, multiple sessions per day |

## Findings

### Onboarding and session flow

- **OBSERVED** — The marketed usage flow is three steps: (1) put on headband, (2) start a stim session and work as usual, (3) "lock in" with increased focus levels. (Homepage "How do I use It" carousel)
- **DOCUMENTED** — Sessions are 20 minutes, recommended daily (minimum 3×/week to see results); sessions can be done during any activity, ideally cognitively engaging tasks. (Homepage FAQ)
- **DOCUMENTED** — The app is compatible only with the Neurode headband; access is via invitation/early-access purchase flow (Stripe checkout, eligibility checklist: 18+, US resident, iPhone 2018+, no epilepsy/seizure history, no head/neck metal implants, etc.). (App Store listing; homepage order section)
- **OBSERVED** — An app screenshot carousel on the homepage shows a session-intensity chooser ("Choose your stimulation intensity to get the most from your focus session") as part of session setup — shown as a screenshot image, not operated. (Homepage carousel, items 1–5 of 5)
- **DOCUMENTED** — Monthly delivery of clinical-grade stimulation pads is part of membership, implying a pad-replacement ritual in onboarding/ongoing use. (Homepage "What you get")
- **UNVERIFIED** — Exact in-app onboarding sequence (pairing, fit check, calibration) is not publicly documented; no accessible source describes the first-session experience step by step.

### Visualization of physiological data (primary focus)

- **OBSERVED** — The company repeatedly demonstrates live brain-activity visualization: founder/testimonial posts show "My brain in realtime", "Live view from @ritwikpava's brain", and "crazy to see my frontal lobe switch between focused + relaxed states". (Homepage testimonial wall)
- **DOCUMENTED** — Marketing tagline: "See your brain in real time — We let you view your brain activity and understand how that relates to your ADHD, an MRI in your pocket." (neurode.com.au legacy site; New Atlas quote)
- **OBSERVED** — App-screenshot carousel includes screens titled (per carousel captions) "Choose your stimulation intensity…", "Get personalized insights about your focus", "Track your progress, so you can make informed decisions", and "Merge data from other wearables via apple health and see the correlations". The screenshots themselves are images on the marketing site; their exact chart types were not independently verified. (Homepage "Build a habit" carousel)
- **DOCUMENTED** — Monitoring modality is fNIRS (not EEG), 152 channels, measuring prefrontal blood oxygenation associated with activity. (Homepage tech specs)
- **DOCUMENTED** — A research-grade 600-channel multimodal fNIRS-EEG variant streams continuously to a laptop where data is "processed, visualized, and decoded in real time," with oxy- and deoxy-hemoglobin changes projected onto an anatomical brain map updating continuously; a live decoder classifies moment-to-moment whether attention is directed inward or outward, displayed alongside the brain map. (NeurIPS 2026 demo abstract) This is the clearest public description of the visualization approach, but it describes the research demo, not necessarily the shipping consumer app.
- **INFERRED** — The consumer app's live view most likely shows prefrontal fNIRS activity (possibly a simplified heat/curve view) with focus-state classification, given the "focused + relaxed states" testimonial language; the exact rendering is not confirmed.

### Session creation / audio and adaptive behavior

- **DOCUMENTED** — Neurode's loop is measurement + stimulation rather than audio: fNIRS monitoring informs tRNS stimulation ("closed-loop stimulation — fNIRS informs tRNS to achieve optimal therapeutic benefit", per investor memo). There is no soundscape/audio-response feature; sessions are silent aside from any ambient task audio. (Stoic VC memo; homepage)
- **DOCUMENTED** — Users choose stimulation intensity at session setup (screenshot caption), i.e., the adaptive element is stimulation dose, not audio. (Homepage carousel)
- **INFERRED** — Per the directive, stimulation controls were not studied in depth; noted only where they intersect with session flow and reporting.
- **DOCUMENTED** — An AI assistant, "Rae", is integrated with the companion app to help reduce overwhelm and build personalized to-do lists. (New Atlas; Futuroprossimo)
- **UNVERIFIED** — Whether Rae or any adaptive algorithm changes session parameters based on live fNIRS within a session in the shipping product (vs. between sessions).

### Quality / sensor status feedback

- **DOCUMENTED** — Monthly replacement of clinical-grade stimulation pads "to ensure comfortable wear" is the main published maintenance ritual; the site implies pad state matters for session quality. (Homepage "What you get"; FAQ)
- **INFERRED** — Some device/pad contact feedback likely exists during session setup (typical for fNIRS/tRNS devices, and the intensity chooser implies readiness checks), but no public source documents an explicit signal-quality or contact indicator.
- **UNVERIFIED** — Any in-app device status screen (battery, connection, sensor contact) is not visible in accessible sources.

### Insights, reports, and longitudinal presentation

- **DOCUMENTED** — The app "provides access to insights on your brain data, [lets you] monitor executive function improvements and track your own productivity streaks." (Homepage FAQ #04)
- **DOCUMENTED** — "We'll track your progress using our brain monitoring technology, showing you how your brain activity evolves with each session"; a team of neuroscientists/psychologists/engineers is available by message to explain results. (Homepage FAQ #02)
- **DOCUMENTED** — "It also measures how active your brain is and tracks how that activity changes over time, so that you know if your symptoms are improving." (App Store description)
- **OBSERVED** — A marketing screenshot is captioned "IOS - Complete Tracking - 1 Month", indicating a month-scale progress view exists in the app UI. (Homepage carousel image filename/caption)
- **DOCUMENTED** — Apple Health integration merges other-wearable data "and see the correlations". (Homepage carousel caption)
- **DOCUMENTED** — Company-claimed outcome framing: 45% of users feel improvement in week 1; most see results in 3–8 weeks; benefits claimed to persist up to two weeks after breaks. Vendor claims, not independently verified. (Homepage FAQ #08; iTechGuides skeptical counterpoint)
- **OBSERVED** — A user review describes monitoring daily "bandwidth usage" and managing multiple sessions per day, suggesting per-session summaries plus a daily aggregate concept. (App Store review, via search)
- **UNVERIFIED** — Whether raw fNIRS signals or channel-level data are ever exposed to consumers in the app; public descriptions are of derived focus/activity metrics.

### Interaction patterns

- **DOCUMENTED** — Habit-forming framing: streaks, 20-minute session ritual, "like a workout or meditation" mental model; sessions run in the background of normal work. (Homepage FAQ)
- **DOCUMENTED** — Intensity selection at session start; passive monitoring during the session (user works as usual). (Homepage carousel + usage steps)
- **INFERRED** — Post-session summary screen(s) exist ("Finished Session" image filenames on the marketing site suggest session-complete report screens), but their contents are not documented in accessible text.
- **DOCUMENTED** — Human-in-the-loop support: experts reachable by message to interpret results — a concierge pattern unusual for consumer wearables. (Homepage FAQ #02)

### Loading / error states

- **UNVERIFIED** — No accessible source shows loading, empty, or error states of the app (e.g., headband disconnect, poor contact, failed session). Not visible in marketing screenshots text.

## Evidence log

| Claim | Classification | Source URL |
|---|---|---|
| Headband uses fNIRS (not EEG), 152 channels | DOCUMENTED | https://neurodelabs.com |
| Live brain-activity view in the app ("my brain in realtime", "live view") | OBSERVED | https://neurodelabs.com |
| "See your brain in real time… an MRI in your pocket" | DOCUMENTED | https://www.neurode.com.au/ (via search) |
| 3-step usage: put on headband, start session, work as usual | OBSERVED | https://neurodelabs.com |
| 20-minute daily sessions; ≥3×/week for results | DOCUMENTED | https://neurodelabs.com |
| Intensity chooser at session start (app screenshot) | OBSERVED | https://neurodelabs.com |
| App tracks brain-activity change over time / symptom improvement | DOCUMENTED | https://apps.apple.com/us/app/neurode/id6449830978 |
| Personalized focus insights + progress tracking (app screenshots) | OBSERVED | https://neurodelabs.com |
| 1-month complete-tracking view ("Complete Tracking - 1 Month" screenshot) | OBSERVED | https://neurodelabs.com |
| Apple Health merge with correlations | DOCUMENTED | https://neurodelabs.com |
| Productivity streaks and executive-function monitoring in app | DOCUMENTED | https://neurodelabs.com |
| Experts on message to explain results | DOCUMENTED | https://neurodelabs.com |
| Closed-loop: fNIRS informs tRNS | DOCUMENTED | https://medium.com/stoic-vc/investment-notes-neurode-db67856ca09a |
| Rae AI assistant for to-do lists / overwhelm | DOCUMENTED | https://newatlas.com/science/adhd-autism/adhd-device-neurode |
| 600-channel fNIRS-EEG research headband; live anatomical-map visualization; real-time internal/external attention decoding | DOCUMENTED | https://neurips.cc/virtual/2026/loc/sydney/174110 |
| Early access, not FDA/TGA authorized | DOCUMENTED | https://neurodelabs.com |
| Pricing $999 + $29/mo; 60-day guarantee; US adults; iPhone 2018+ | DOCUMENTED | https://neurodelabs.com |
| Monthly stimulation pad delivery | DOCUMENTED | https://neurodelabs.com |
| Consumer app exposes raw fNIRS signals | UNVERIFIED | (absence in accessible sources) |
| In-app sensor/contact quality feedback | INFERRED | (from pad-replacement emphasis + typical practice) |
| In-app device status screen | UNVERIFIED | (absence in accessible sources) |

## Missing evidence and inaccessible functionality

- The app requires the Neurode headband (invitation/early-access purchase) and an iPhone 2018+/iOS 18; no public demo of the actual app screens in operable form exists — all UI knowledge comes from marketing screenshots and third-party descriptions.
- The exact visual design of the live brain view (anatomical map vs. curves vs. heat strip), the metric vocabulary shown, and any configurable thresholds are not publicly documented. The NeurIPS 2026 demo describes a research variant's visualization (anatomical projection + attention decoder), which may exceed what ships to consumers.
- No public documentation of session summaries' contents, streak mechanics, error/empty states, or data export for consumers.
- The status of the double-blind placebo-controlled RCT on 120 adults with ADHD (referenced on the site as "publishing soon") was not verifiable from accessible pages; iTechGuides likewise notes incomplete public clinical evidence.
- Founded in Australia; the older neurode.com.au domain still carries earlier copy; current sales appear US-focused.

## Relevance to CIRCLE

- **Physiological dashboard**: Neurode's strongest pattern for CIRCLE is the live "see your brain in real time" experience — showing the active physiological signal during a session, not only after it. CIRCLE's simulated PPG/EDA/IMU streams can replicate this transparency better: live traces plus visible quality gates, versus Neurode's derived focus scores whose computation is closed.
- **Session designer**: Neurode's session model is deliberately minimal (put on device → start 20-min session → work as usual) with intensity as the only pre-session parameter. CIRCLE's session designer can adopt this low-friction "background session" pattern while adding explicit protocol parameters, gates, and active-vs-sham arms that Neurode does not expose.
- **Adaptive audio engine**: Neurode has no audio adaptation — it is a measurement/stimulation product. The gap is instructive: CIRCLE's adaptive audio engine with quality gates covers a design space Neurode leaves empty, and CIRCLE's closed loop (signal gates → audio parameters) can be shown explicitly where Neurode's fNIRS→tRNS loop is only asserted in an investor memo.
- **Evidence explorer**: Neurode's longitudinal story (per-session evolution, month-scale tracking, streaks, Apple Health correlations) is a good template for CIRCLE's longitudinal measurement presentation. But Neurode's "insights" are opaque derived claims with vendor-stated effect statistics; CIRCLE's evidence export + independent replay audit + active-vs-sham comparison is precisely the rigor layer Neurode's marketing lacks — reviewers (iTechGuides) already note the evidence gap.
- **Sensor status**: Neurode's consumable-pad ritual and (inferred) contact checks parallel CIRCLE's simulated sensor-quality gates; CIRCLE can make the gate state a first-class, always-visible UI element rather than an implied prerequisite.
- **Human interpretation layer**: Neurode's "message a neuroscientist to explain your results" concierge is an interesting pattern; CIRCLE's equivalent could be reproducible evidence bundles that a human or independent auditor can replay without vendor mediation.
- **Consent gate**: Neurode's eligibility checklist (medical contraindications) and invitation gating resemble CIRCLE's consent gate concept; CIRCLE can model consent as an explicit, logged, replayable step.

## Suggested original implementation ideas for CIRCLE

1. **Live dual-view dashboard**: split-screen during a session — raw simulated signal traces (PPG/EDA/IMU) with quality-gate indicators on one side, derived state (e.g., "focus/calm" classification) on the other, with a visible link showing how the derived state is computed from the raw signal. This directly out-transparents Neurode's opaque focus scores.
2. **Session evolution strip**: a Neurode-style "how your activity evolves with each session" longitudinal chart, but where every historical point links to its full evidence bundle and one-click independent replay audit.
3. **Minimal-friction session start**: adopt the three-step "put on → start → work as usual" flow, with CIRCLE's consent gate and pre-session sensor check inserted as explicit, logged steps in the same flow.
4. **Active-vs-sham insight framing**: where Neurode publishes vendor percentages ("45% feel improvement in week 1"), CIRCLE can compute and display within-subject active-vs-sham contrasts with confidence intervals from its own session data, making claims auditable by construction.
5. **Correlation crosswalk**: like Neurode's Apple Health merge, allow correlating CIRCLE sessions with imported daily metadata (sleep, exercise), but show the underlying paired data points rather than only a correlation coefficient.
6. **Streak with substance**: keep habit streaks, but annotate each streak day with signal-quality summary and gate outcomes, so a streak means "valid measured sessions," not just "days the app was opened."
7. **Anatomical/state map experiment**: inspired by Neurode's live brain-map demo, add an optional playful "body map" for CIRCLE's simulated streams (cardiac, electrodermal, motion) that highlights modality health per region/time — interactive visualization without claiming neural source localization.
