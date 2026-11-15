# NextSense — Evidence report

NextSense Smartbuds are consumer wireless earbuds ("Smartbuds", $349) with six dry-contact in-ear EEG sensors (2× 24-bit channels at 1000 Hz, plus 6-axis IMU) that read brain activity in real time and respond with closed-loop audio: timed pink-noise pulses intended to enhance slow-wave (deep) sleep, plus adaptive Focus and Meditation modes. The company (NextSense Inc.; app seller listed as Lucid Reality Inc on the App Store) traces its technology to Alphabet's X moonshot factory and Emory University research, and raised a $16M Series A led by Ascension Ventures (per Seek & Score). The product debuted at CES 2025 as "Tone by NextSense" and launched commercially in early 2026. As of late 2026 it is actively sold (iOS-only companion app, ~4.7★ with 93 ratings, version 1.0.149 shipping fixes), requires an optional Fit Kit consumable subscription (~$14.99/mo) for electrode tip/wing replacement, and has an active help center and clinical-research program (Emory, Mayo, Northwestern collaborators).

## Sources consulted

| URL | Contribution |
|---|---|
| https://nextsense.io | Homepage: product concept, three modes (Sleep/Meditation/Focus), My Day alertness curve, sensor specs, FAQ on EEG, privacy, slow-wave enhancement |
| https://nextsense.io/products/smartbuds | Full technical specifications (EEG channels, sampling rate, audio, battery, Bluetooth, fit), mode descriptions, sound-technology explainer, Fit Kit requirement |
| https://nextsense.io/pages/clinical | Clinical studies (ClinicalTrials.gov links), peer-reviewed publications, researcher profiles, data-export claim ("time-synced signals and events exportable for analysis") |
| https://apps.apple.com/us/app/nextsense/id6636482744 | App Store description: session types, sleep sync, nap mode, sound library, gentle alarm, Apple Health integration, privacy labels |
| https://nextsensesupport.zendesk.com/ | Help center structure (Getting Started, Common Issues, Your Data, Tips & Tricks) |
| https://nextsensesupport.zendesk.com/hc/en-us/sections/46634168444948-Getting-Started | First-day setup flow article index |
| https://nextsensesupport.zendesk.com/hc/en-us/articles/46634202322068-Your-first-day-with-Smartbuds | Documented onboarding: charge, fit sizing, pairing, first session; fit/signal relationship |
| https://nextsensesupport.zendesk.com/hc/en-us/articles/46634312752404-Smartbuds-Features | Official feature list: slow-wave tracking, Slow Wave Boost, insights, Sleep Sync, Nap Mode, sound library, gentle alarm |
| https://www.forbes.com/sites/forbes-personal-shopper/article/nextsense-smartbuds-review (Forbes Vetted, Mar 2026, via search) | Independent reviewer impressions |
| https://gizmodo.com/sleep-tracking-earbuds-didnt-fix-me-but-they-did-open-my-eyes-2000746925 (via search) | App trends tab (week/month/3-month views), nightly stats, sleep efficiency score |
| https://gizmodo.jp/article/sleep-tracking-earbuds-nextsense-smartbuds-review (via search) | Detailed hands-on: EEG tutorial with signal check at setup, session start flow, real-time EEG readout screen, lock-screen activity display, soundscape categories, soundscape download to device, nightly deep-sleep data, slow-wave boost counts, tips replacement cadence (21 sessions), app recognition failures |
| https://www.apartmenttherapy.com/nextsense-smartbuds-review-37543644 (via search) | Setup prompts, sleep schedule config, morning chart (time in bed, drift-off, wakes, slow-wave count, boosts used), Fit Kit subscription |
| https://www.lifewire.com/nextsense-smartbuds-11902523 (via search) | Fit check confirmation feature, sound library including binaural beats, stats vocabulary |
| https://geardiary.com/2026/04/02/nextsense-smartbuds-review (via search) | Sleep-stage detection accuracy concerns, comfort/cons; algorithm vocabulary (light/deep/REM/wake) |
| https://www.soundguys.com/nextsense-smartbuds-bring-eeg-brain-sensors-to-wireless-earbuds-for-the-first-time-152745/ (via search) | Launch details, CES, beta data claims, Fit Kit terms |
| https://seekandscore.com/nextsense-review (via search) | Soundscape library categories, smart-alarm wake-window behavior, beta-night statistics, Series A |
| https://www.nytimes.com/wirecutter/reviews/brain-wave-tracking-sleep-wearables (via search) | Independent skepticism of staging accuracy |

## Findings

### Onboarding and session flow

- **OBSERVED** — Setup begins with charging (case LEDs as battery indicator), a fit-sizing tutorial video, choosing tip/wing sizes (S/M/L), and pairing via the charging-case button followed by in-app on-screen instructions. (Zendesk "Your first day with Smartbuds")
- **OBSERVED** — First use includes an EEG tutorial with a sensor "signal check" that verifies the electrodes are making good contact before sleep sessions; starting a session afterwards is a one-tap action from the app. (Gizmodo Japan hands-on)
- **OBSERVED** — The app asks the user to configure a sleep routine (target bedtime/wake window), which customizes reminders (e.g., charge buds before bed) but does not hard-gate session start. (Website FAQ + Apartment Therapy)
- **DOCUMENTED** — Session types: Sleep, Nap (timer + soundscape; drift-off naps are added to the day's sleep total), Focus (open-ended, Pomodoro, or "Smart"), and Meditation (guided, brain-responsive soundscape, or user-supplied audio). (App Store listing; product page)
- **DOCUMENTED** — Audio can be pre-downloaded from the in-app library to the buds so sessions run without continuous Bluetooth streaming, saving battery. (Gizmodo Japan)
- **INFERRED** — "Smart" Focus sessions presumably use the same real-time EEG loop as Sleep (detect drift, adapt audio), but the exact control rule is not published.

### Visualization of physiological data

- **OBSERVED** — During a session the app switches to a real-time screen showing monitored EEG values alongside the playing soundscape. (Gizmodo Japan)
- **OBSERVED** — The morning report is a chart of total time in bed, drift-off time, total wakes, and slow-wave count plus the number of "slow boosts" (audio enhancement events) used during the night. (Apartment Therapy)
- **OBSERVED** — A "trends" tab aggregates data in 1-week, 1-month, and 3-month intervals alongside granular nightly breakdowns; metrics include total sleep time, wake-ups, sleep efficiency (reviewer saw 96–97% scores). (Gizmodo US + Japan)
- **DOCUMENTED** — Focus sessions end with a readout showing "when your attention held and when it wandered"; the "My Day" alertness curve maps focus capacity across the day and recommends when to schedule deep work. (Website homepage; App Store listing)
- **DOCUMENTED** — Apple Health integration reads DOB, sex, heart rate, HRV, respiratory rate, VO2max, sleep, weight, steps, exercise time, and daylight time to personalize insights. (App Store listing)
- **UNVERIFIED** — Whether raw EEG waveforms are ever exposed to the user in the app (vs. only derived metrics). The clinical page suggests time-synced signal export exists for researchers, but the consumer app's display is described in terms of derived values (slow-wave counts, efficiency).

### Audio behavior (closed-loop adaptive audio)

- **DOCUMENTED** — The core mechanism is EEG-guided auditory stimulation: when slow-wave (deep) sleep is detected, the buds play gentle pink-noise pulses timed to the brain's slow-wave rhythm, deepening and extending slow waves without waking the user. (Product page "Brain Responsive Sleep Technology"; FAQ)
- **DOCUMENTED** — Sleep Sync pauses audio automatically when sensors detect the user has fallen asleep (e.g., audiobook position preserved). (App Store; Zendesk feature list)
- **DOCUMENTED** — Meditation mode senses when the user is "still wound up" and adjusts sound in real time; Focus mode adapts audio when sensors detect drift vs. locked-in attention. (Website homepage)
- **OBSERVED** — Reviewers describe the sleep-enhancement audio as low-frequency, quieter than typical white noise; the default sleep soundscape is rain. (Gizmodo Japan)
- **DOCUMENTED** — The soundscape library is organized into categories (weather and water, ambient, binaural beats, "noises of all colors" — white/pink/brown/blue) plus an enhanced sound-masking mode targeting snoring/room noise. (Seek & Score; Lifewire)
- **DOCUMENTED** — Gentle alarm wakes the user during lighter sleep within a chosen window with sounds that build slowly. (App Store; Seek & Score)
- **INFERRED** — The closed loop runs on-device or bud-side given "on-device audio" and millisecond "detection latency" claims, but the exact split between phone and bud processing is not documented.

### Quality / sensor status feedback

- **OBSERVED** — A signal check is part of first-time setup, verifying sensor contact quality. (Gizmodo Japan)
- **OBSERVED** — The app provides an in-app "fit check" confirming tip/wing fit. (Lifewire)
- **DOCUMENTED** — Sensor quality degrades as skin oils wear the conductive Tecticoat coating; tips/wings must be replaced roughly every 21 sessions (~$49 kit or ~$14.99/mo subscription) to maintain "clinical-grade EEG signal quality." (Gizmodo Japan; SoundGuys; Apartment Therapy)
- **OBSERVED** — Failure states: reviewers report occasional failure of the app to recognize the earbuds, requiring re-pairing; iOS lock-screen shows session activity (useful for confirming buds are active); battery can run out before morning (a dedicated help article exists). (Gizmodo Japan; Zendesk)
- **INFERRED** — Continuous on-screen contact/impedance feedback during a session is plausible given the real-time EEG readout, but no source explicitly confirms an impedance meter.

### Insights and reports

- **DOCUMENTED** — Personalized insights cover daily and long-term trends: total sleep time, wake-ups, sleep efficiency, slow-wave metrics; beta users reportedly saw measurable deep-sleep increases in the first week (company data over 106 controlled beta nights; treat as vendor-claimed). (App Store; SoundGuys)
- **DOCUMENTED** — Focus recommendations ("schedule deep work in your strongest hours") derive from the My Day alertness curve. (Homepage)
- **OBSERVED** — Reviewers found the app "more inviting and easier to digest than expected," while at least one found per-night staging occasionally at odds with lived experience (e.g., deep sleep marked before an early waking, or "asleep" detected while the reviewer was clearly awake and reading their phone). (Gizmodo US; Gear Diary; Wirecutter)
- **UNVERIFIED** — Any clinician-facing or research-facing export UI in the consumer app; the clinical page advertises "time-synced signals and events exportable for analysis" for research workflows but details are not public.

### Interaction patterns

- **OBSERVED** — One-tap session start; iOS lock-screen integration for session visibility; timer-based Nap mode with soundscape picker; soundscape library browsing with pre-download. (Gizmodo Japan; App Store)
- **DOCUMENTED** — Mode-first navigation (Sleep / Meditation / Focus / Nap), each with its own session chrome and post-session readout. (Website; App Store)
- **OBSERVED** — Nocturnal data is presented as a morning-after chart rather than requiring the user to watch the screen overnight. (Apartment Therapy)

### Loading / error states

- **OBSERVED** — App/bud recognition failures with re-pairing as the workaround (reviewer-reported); audio download issues were fixed in app version 1.0.149 ("What's New" on App Store, 2 days before this research); battery-before-morning is a documented support topic. (Gizmodo Japan; App Store; Zendesk)
- **UNVERIFIED** — In-session sensor-loss handling UX (e.g., what the user sees if an electrode loses contact mid-sleep) is not described in any accessible source.

## Evidence log

| Claim | Classification | Source URL |
|---|---|---|
| Six dry-contact EEG electrodes, 2× 24-bit channels @ 1000 Hz, 6-axis IMU | DOCUMENTED | https://nextsense.io/products/smartbuds |
| Closed-loop pink-noise slow-wave enhancement | DOCUMENTED | https://nextsense.io/products/smartbuds |
| Real-time EEG readout screen during session | OBSERVED | https://gizmodo.jp/article/sleep-tracking-earbuds-nextsense-smartbuds-review |
| Setup signal check for sensor contact | OBSERVED | https://gizmodo.jp/article/sleep-tracking-earbuds-nextsense-smartbuds-review |
| Morning chart: time in bed, drift-off, wakes, slow-wave count, boosts used | OBSERVED | https://www.apartmenttherapy.com/nextsense-smartbuds-review-37543644 |
| Trends tab with week/month/3-month aggregations | OBSERVED | https://gizmodo.com/sleep-tracking-earbuds-didnt-fix-me-but-they-did-open-my-eyes-2000746925 |
| Sleep Sync pauses audio on sleep onset | DOCUMENTED | https://apps.apple.com/us/app/nextsense/id6636482744 |
| Nap Mode with timer + soundscape; naps added to daily total | DOCUMENTED | https://nextsensesupport.zendesk.com/hc/en-us/articles/46634312752404-Smartbuds-Features |
| Focus session types (open-ended, Pomodoro, Smart) | DOCUMENTED | https://nextsense.io/products/smartbuds |
| My Day alertness curve and deep-work scheduling recommendations | DOCUMENTED | https://nextsense.io |
| Soundscape library categories and sound-masking mode | DOCUMENTED | https://seekandscore.com/nextsense-review |
| Gentle alarm within wake window | DOCUMENTED | https://seekandscore.com/nextsense-review |
| Apple Health reads HRV, HR, sleep, etc. for personalization | DOCUMENTED | https://apps.apple.com/us/app/nextsense/id6636482744 |
| Fit Kit replacement every ~21 sessions; signal quality rationale | OBSERVED | https://gizmodo.jp/article/sleep-tracking-earbuds-nextsense-smartbuds-review |
| Fit check feature in app | OBSERVED | https://www.lifewire.com/nextsense-smartbuds-11902523 |
| Occasional app fails to recognize buds; re-pair needed | OBSERVED | https://gizmodo.jp/article/sleep-tracking-earbuds-nextsense-smartbuds-review |
| Sleep-stage detection sometimes disagrees with lived experience | OBSERVED | https://geardiary.com/2026/04/02/nextsense-smartbuds-review |
| Audio pre-downloaded to buds for battery saving | OBSERVED | https://gizmodo.jp/article/sleep-tracking-earbuds-nextsense-smartbuds-review |
| iOS lock-screen shows active session | OBSERVED | https://gizmodo.jp/article/sleep-tracking-earbuds-nextsense-smartbuds-review |
| Research workflows: time-synced signal/event export | DOCUMENTED | https://nextsense.io/pages/clinical |
| Raw EEG waveform exposure in consumer app | UNVERIFIED | (absence in accessible sources) |
| Company data: slow-wave increases across 106 beta nights | DOCUMENTED (vendor-claimed) | https://www.soundguys.com/nextsense-smartbuds-bring-eeg-brain-sensors-to-wireless-earbuds-for-the-first-time-152745/ |

## Missing evidence and inaccessible functionality

- The app requires NextSense Smartbuds hardware and an iPhone (iOS 17.6+); all in-app screens (session control, live EEG readout, trends charts, My Day curve) were observed only via third-party reviews and official descriptions, not directly operated.
- No public documentation of the closed-loop control algorithm (detection thresholds, pulse timing rules, adaptation cadence), so its behavior cannot be independently audited from public sources.
- Whether/how users can export their own raw EEG data from the consumer app is unclear; the clinical page's export claim appears aimed at researchers.
- Android app does not exist as of late 2026 (iOS only; per website and reviews).
- Sensor-loss mid-session UX, data-deletion flow (claimed to exist in-app), and meditation session readout details were not visible in accessible sources.

## Relevance to CIRCLE

- **Adaptive audio engine**: NextSense's core pattern — physiological gate (sleep stage / attention state) driving audio parameters in real time — is exactly CIRCLE's closed-loop controller with signal-quality gates. Their division into named session modes (Sleep/Nap/Focus/Meditation) with per-mode readouts is a clean pattern for CIRCLE's session designer. The "boosts used" counter (making closed-loop interventions countable and visible) is directly worth adopting.
- **Physiological dashboard**: Their trend hierarchy (nightly detail → week/month/3-month aggregates; daily alertness curve) maps onto CIRCLE's longitudinal measurement presentation. Their metric vocabulary (drift-off time, total wakes, slow-wave count, efficiency) shows how to translate raw signals into explainable derived metrics.
- **Session designer**: Nap Mode (timer + soundscape + auto-detect of drift-off, folded into daily totals) and Focus's three session shapes (open-ended/Pomodoro/Smart) are useful templates for CIRCLE's session presets.
- **Evidence explorer**: NextSense exposes derived scores but (publicly) not raw signals or algorithm transparency; reviewers explicitly distrusted staging when it contradicted experience. CIRCLE can do better: expose signal-quality timelines, gate decisions, and event annotations alongside summary scores, and make every session independently replayable — turning the "trust gap" reviewers noted into CIRCLE's differentiator.
- **Sensor status**: The fit check + first-session signal check + consumable-degradation warnings are a good model for CIRCLE's simulated PPG/EDA/IMU quality gates (e.g., explicit "signal check" step before a session counts as valid evidence).
- **Transparency/reproducibility**: NextSense cites peer-reviewed validation and clinical trials but keeps the consumer loop opaque. CIRCLE's evidence export and independent replay audit directly address what NextSense leaves closed.

## Suggested original implementation ideas for CIRCLE

1. **Boost ledger**: like NextSense's "slow boosts used," log every closed-loop intervention (gate state, parameter change, timestamps) in a per-session ledger viewable in the evidence explorer, so users can see not just outcomes but controller actions.
2. **Disagreement flag**: reviewers distrust staging that contradicts experience; let users annotate a session ("I was awake at 3:17") and store the annotation alongside the signal-quality record, making human ground truth part of the replayable evidence.
3. **Signal-check gate before evidence accrual**: require an explicit pre-session sensor-signal check (as NextSense does for EEG contact) before a session is admitted to longitudinal statistics; failed checks are shown, not hidden.
4. **Mode-shaped sessions with post-session readouts**: implement Sleep/Nap/Focus/Meditation-style presets in the session designer, each with its own summary card (e.g., "attention held vs. wandered" timeline for focus sessions).
5. **Trend ladder**: nightly detail → 7/30/90-day aggregate views, plus a "My Day"-style daily capacity curve derived from simulated streams — with the difference that each point is clickable through to the underlying evidence bundle and replay audit.
6. **Raw-plus-derived dashboard**: show the simulated waveform traces (PPG/EDA/IMU) beside derived metrics, something NextSense does not clearly offer consumers — making CIRCLE's dashboard more transparent by construction.
7. **Consent-gated data export**: mirror NextSense's opt-in data-sharing posture, but make export a first-class, reproducible artifact (consent record + data + controller log) rather than a buried setting.
