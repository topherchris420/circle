# Healium — Evidence report

**Product:** Healium (Healium Wellness / Healium Clinical)
**Vendor:** StoryUP, Inc. dba Healium (CEO Sarah Hill; Chief Science Officer Dr. Jeff Tarrant; Chief Medical Officer Dr. Murdoc Khaleghi)
**Research date:** November 15, 2026. All URLs were publicly accessible at research time; no logins, paywalls, or proprietary assets were bypassed.

Healium is an immersive biofeedback and neurofeedback training platform that combines 360-degree virtual-reality "meditation stories" with real-time physiological input from consumer wearables (smartwatches, EEG headbands, a finger sensor). Built by StoryUP, Inc. of Columbia, Missouri, and marketed primarily to clinicians, VA hospitals, schools, and wellness organizations, it turns heart rate, HRV, skin conductance, and EEG signals into responsive visual elements — most prominently the "Aura," a light that brightens and turns golden as the user relaxes. As of late 2026 the product is actively maintained (iOS companion app v5.1.1 released October 2026), FDA-registered as a Class II 510(k)-exempt biofeedback platform under the name "Healium Clinical" (announced May 2026), deployed in a 700+ kit in-home VR program for Veterans, and backed by a marketing-claimed base of nine peer-reviewed studies including a Mayo Clinic Proceedings randomized controlled trial on preoperative anxiety. It is a commercial, closed-source product; nothing about its internal algorithms is published.

## Sources consulted

| URL | What it contributed |
|---|---|
| https://tryhealium.com | Product overview, positioning ("immersive biofeedback training for anxiety, stress & pain"), four-step session flow, wearable + dashboard framing, FAQ (hardware, pricing, privacy, research use), company footer (StoryUp Inc. dba Healium, 2026) |
| https://tryhealium.com/how-it-works | Detailed patient experience flow, Healium Score definition, clinician dashboard data list, session lengths (4–20 min), wearable-optional statement, clinical FAQ |
| https://tryhealium.com/science-behind-healium | List of claimed peer-reviewed studies (Mayo Clinic Proceedings RCT, Frontiers in Psychology, NeuroRegulation, etc.), research collaborators, leadership team bios |
| https://www.tryhealium.com/compatible-devices | Full compatible hardware matrix: VR headsets, wearables, sensor modalities per device; gear FAQ |
| https://tryhealium.com/experiences | Full experience library (50+ titles, durations 4–22 min), "Aura Awakening" onboarding experience description, per-experience descriptors of what biofeedback changes |
| https://tryhealium.com/knowledge-base/how-is-my-healium-score-calculated | Exact Healium Score calculation rule and per-sensor baseline definitions |
| https://apps.apple.com/us/app/healium-biofeedback-meditation/id1403144098 | iOS companion app listing: description, v5.1.1 (Oct 2026), 4.1★/68 ratings, privacy nutrition labels, seller, Heal-U curriculum, membership model |
| https://www.meta.com/experiences/healium-biofeedback-meditation/3688700857882832 | Meta Quest store listing: 3.4★/23 ratings, user review text (visuals, audio, customizability) |
| https://tryhealium.com/blog/healium-announces-fda-registration-of-healium-clinical-as-a-class-ii-510k-exempt-biofeedback-medical-device (via search) | FDA Class II 510(k)-exempt registration details; split into Healium Wellness vs. Healium Clinical platforms; VA deployment claims |
| https://tryhealium.com/blog/what-is-healium-and-how-does-it-work (via search) | Restated mechanism: signals → "vibrant biodata" users visualize and interact with |
| https://tryhealium.com/blog/press-release-in-home-vr-initiative (via search) | VA / SoldierPoint / VA Immersive 700+ in-home VR kit program (April 2026) |
| https://tryhealium.com/blog/mosaic-medical-center-healium-immersive-vr-partnership (via search) | Hospital deployment example (Mosaic Maryville, June 2026) |
| https://dashboard.tryhealium.com (login page, not signed in) | Existence of a separate web provider dashboard; contents not accessible without an account |

## Findings

### Visual / interactive feedback environments

- **OBSERVED** — Healium offers a library of 50+ named 360-degree VR experiences (Inner Cathedral, Celestial Sea, Aurora Borealis, Magic Snow Globe, etc.), 4–22 minutes long, with preview videos publicly hosted on the experiences page. The previews are pre-rendered video and do not themselves demonstrate biofeedback reactivity.
- **DOCUMENTED** — "Each one responding in real time to your own heart rate, HRV, or EEG brainwaves" (homepage and experiences page). Examples of the responsive mechanic from experience descriptions: use your feelings to "make the flurries fly" (Magic Snow Globe), "part the clouds, stop the rain, and illuminate the rainbow" (Embrace the Storm), "watch as your brain patterns react to different hues" (Colors of Healing), "use your feelings to float up the side of a beautiful waterfall" (Waterfall to the Clouds), butterflies summoned "at the end" (Tranquil Garden).
- **DOCUMENTED** — The "Aura" is Healium's central biofeedback visual: a light attached to the user's hands that "grows brighter and more golden" as the user relaxes. The "Aura Awakening" experience is an explicit training-onboarding piece that teaches users to see their own regulation before using other experiences.
- **INFERRED** — The actual biofeedback-to-visual mapping appears to be a coarse "calmness" scalar driving brightness/color/plot progress of pre-authored scenes, rather than raw-signal visualization (the site speaks of "vibrant biodata," but no page shows waveform-level rendering inside the VR scenes). The exact transfer function is unpublished.
- **UNVERIFIED** — Smoothness, latency, and frame behavior of the real-time coupling; no public demonstration of a live session with visible sensor-driven change was reviewable from text sources.

### Audio mapping and signal chain

- **DOCUMENTED** — Experiences include ambient sound, music, and narration (App Store description; Meta Quest user review praises "excellent ambient sound and music"). Audio is part of the storytelling, not the primary biofeedback channel — Healium's feedback modality is visual.
- **UNVERIFIED** — Whether audio parameters (e.g., music intensity, filter, tempo) are modulated by physiological state. Nothing public states audio is biofeedback-driven; treat as unknown.

### Wearable sensor integration

- **DOCUMENTED** — Compatible sensors and modalities (compatible-devices page):
  - Apple Watch Series 4+ — heart rate (iPhone, Apple Vision Pro, Meta Quest)
  - Samsung Galaxy Watch 4+ — heart rate (Android, Meta Quest, Pico)
  - Muse 2 EEG headband — EEG neurofeedback (Quest, Pico, iPhone)
  - Brainlink Lite EEG headband — EEG (iPhone, Android, Quest, Pico)
  - eVu-TPS finger sensor (Thought Technology) — HRV, blood pulse volume, skin conductance, skin temperature (Meta Quest)
- **DOCUMENTED** — VR platforms: Meta Quest 2/3/3s, Apple Vision Pro; Pico G3/G2 4K/Neo 3/4 for select enterprise customers. Mobile companion apps exist for iPhone and Android; the web dashboard exists for clinicians.
- **DOCUMENTED** — Wearables are optional: sessions run standalone without a sensor, but pairing "unlocks" the Aura and real-time transformation of the experience.
- **INFERRED** — The Apple/Samsung watch links are phone-mediated (watch → phone → headset), while the eVu-TPS and Muse pair more directly to Quest hardware; the exact BLE topology is not documented.

### Session flow and feedback

- **DOCUMENTED** — Canonical four-step flow (homepage, how-it-works, app listing): (1) pair a wearable, (2) select an experience by goal (focus, positivity, sleep, calm), (3) run a 4–20 minute guided session in which the Aura gives live feedback, (4) receive a "Healium Score" and review it in the dashboard.
- **DOCUMENTED** — Healium Score = "the percentage of time that you were more relaxed than when you started the session." Baseline is set at session start: high-beta EEG power for EEG headbands, heart rate for smartwatches. Score is capped at 100 (knowledge-base article).
- **DOCUMENTED** — Provider dashboard tracks: individual and group aggregate Healium Scores; session duration, frequency, experience type, and device used; per-session brainwave and heart-rate activity; long-term high-beta and heart-rate trends; export of outcome summaries "for clinical documentation or research."
- **OBSERVED** — Dashboard screenshots are published on the how-it-works page (score panel, panel-level trend charts), confirming the dashboard exists and its general layout; interactive behavior was not testable without an account.
- **INFERRED** — Because the score is a percentage-of-time-below-baseline measure, it is sensitive to baseline inflation (an anxious start yields high scores); no public page discusses baseline validation, making this a plausible weakness rather than a demonstrated one.

### Quality / error states

- **DOCUMENTED** — A quality-check step exists in the sense that the baseline is measured at session start and the score depends on it; the knowledge base describes constant measurement "compared to your starting baseline." What happens on signal drop, poor contact, or motion artifacts is not described anywhere public.
- **UNVERIFIED** — Sensor-loss handling, artifact rejection, minimum-data thresholds for a valid score, and behavior when a wearable disconnects mid-session. The published clinical studies likely describe some of this, but the study manuscripts were not individually fetched for this report.
- **OBSERVED** (indirect) — Meta Quest reviews (3.4★, 23 ratings) include complaints (26% one-star), and one detailed reviewer explicitly did not use the biofeedback features — hinting the wearable integration may be the fragile part, but this is anecdotal, not evidence of specific failure modes. **UNVERIFIED** as a product property.

### Regulatory and privacy posture

- **DOCUMENTED** — FDA registration as Class II 510(k)-exempt biofeedback medical platform "Healium Clinical" (May 2026 blog announcement); registration is explicitly noted as not constituting FDA clearance or pre-market review. Two platforms: Healium Wellness (privacy wall between users and organizational admins) and Healium Clinical (providers may access patient data for care workflows).
- **DOCUMENTED** — Data handled on an "ISO Certified, HIPAA-ready, and NIST-aligned" system (homepage FAQ). Apple privacy labels: Health & Fitness and Contact Info linked to identity; Identifiers and Diagnostics not linked.
- **DOCUMENTED** — Positioned as not a diagnostic/medical treatment in consumer materials, while the Clinical platform is intended for use under supervision of a qualified healthcare professional.

## Evidence log

| Claim | Classification | Source URL |
|---|---|---|
| 50+ immersive VR experiences, 4–22 min | OBSERVED (listing with previews) | https://tryhealium.com/experiences |
| Experiences respond in real time to HR, HRV, or EEG | DOCUMENTED | https://tryhealium.com/ ; https://tryhealium.com/experiences |
| Aura light brightens/gilds with relaxation; "Aura Awakening" teaches this | DOCUMENTED | https://tryhealium.com/experiences |
| Healium Score = % of session time calmer than start baseline (high-beta for EEG, HR for watch) | DOCUMENTED | https://tryhealium.com/knowledge-base/how-is-my-healium-score-calculated |
| Compatible sensors: Apple Watch, Galaxy Watch, Muse 2, Brainlink Lite, eVu-TPS (HRV/BPV/SC/ST) | DOCUMENTED | https://www.tryhealium.com/compatible-devices |
| Platforms: Quest 2/3/3s, Vision Pro, Pico (enterprise), iOS/Android companion, web dashboard | DOCUMENTED | https://www.tryhealium.com/compatible-devices |
| Sessions usable without a wearable (degraded, no Aura) | DOCUMENTED | https://tryhealium.com/how-it-works |
| Provider dashboard: per-session and longitudinal biometrics, exports | OBSERVED (screenshots) / DOCUMENTED | https://tryhealium.com/how-it-works |
| FDA Class II 510(k)-exempt registration as "Healium Clinical" (May 2026) | DOCUMENTED | https://tryhealium.com/blog/healium-announces-fda-registration-of-healium-clinical-as-a-class-ii-510k-exempt-biofeedback-medical-device |
| Mayo Clinic Proceedings RCT on preoperative anxiety | DOCUMENTED (vendor-cited) | https://tryhealium.com/science-behind-healium |
| 700+ VA in-home VR kits (Apr 2026) | DOCUMENTED (vendor press release) | https://tryhealium.com/blog/press-release-in-home-vr-initiative |
| iOS app v5.1.1 (Oct 2026), 4.1★/68 ratings; Quest 3.4★/23 ratings | OBSERVED (store listings) | https://apps.apple.com/us/app/healium-biofeedback-meditation/id1403144098 ; meta.com experiences listing |
| Biofeedback→visual mapping is a coarse calmness scalar, not raw waveform rendering | INFERRED | (multiple pages, absence of contrary evidence) |
| Audio is modulated by physiology | UNVERIFIED | — |
| Sensor-drop/artifact handling behavior | UNVERIFIED | — |
| ISO/HIPAA-ready/NIST-aligned data handling | DOCUMENTED (vendor claim) | https://tryhealium.com |

## Missing evidence and inaccessible functionality

- **Account/hardware-gated:** the live product (VR sessions, Aura behavior, provider dashboard at dashboard.tryhealium.com, Heal-U curriculum, mobile app runtime) requires membership and hardware. None of it was executed; all runtime claims above are DOCUMENTED, not OBSERVED.
- **Proprietary/unpublished:** the biofeedback transfer function (how HR/HRV/EEG map to scene brightness/plot progress), the exact "calmness" estimator, any artifact rejection or baseline logic, group-aggregation statistics in the dashboard, and pricing (quote-only).
- **Studies not independently verified:** the nine peer-reviewed publications are cited on the vendor's science page; original manuscripts (other than the Mayo abstract link) were not fetched, so effect sizes and protocols remain vendor-summarized.
- **Inaccessible pages:** none failed to load; the dashboard login page was reachable but its contents require an account.

## Relevance to CIRCLE

Patterns worth adopting:

- **Responsive visual environment** — Healium's strongest idea is the *narrative-embedded* biofeedback cue: not a gauge or graph, but a diegetic light (Aura) inside a story whose brightness/color/plot progress encode state. CIRCLE's browser workbench could adopt "signal as scene element" rather than always plotting signals: e.g., a simulated PPG stream driving an ambient visual whose luminance tracks a quality-gated calmness metric.
- **Session designer** — Healium's "prescribe sessions" model (clinician picks goal — focus/calm/sleep/positivity — and duration 4–20 min; platform guides the session automatically) is a direct analog of a CIRCLE session designer: protocol templates with target modality, duration, and feedback mapping, runnable without the operator present.
- **Evidence explorer** — the provider dashboard (session score, per-session biometrics, long-term trends, export for documentation/research) is the commercial analog of CIRCLE's evidence export. Healium demonstrates that clinicians value per-session and longitudinal summaries plus export.
- **Baseline-relative scoring** — a simple, explainable session outcome metric ("% time calmer than baseline") is compelling for closed-loop controller evaluation; CIRCLE's active-vs-sham comparisons could use an analogous, but better-validated, session score.

What CIRCLE could do better:

- **Transparency and reproducibility** — Healium's score formula is only marketing-level public; its mapping and artifact handling are closed. CIRCLE can publish exact formulas, versioned algorithms, and full raw-signal evidence bundles so any session is independently replayable and auditable — Healium's published score cannot be recomputed by a third party.
- **Signal-quality gates as first-class states** — Healium barely documents error/quality behavior. CIRCLE's quality gates (explicit bad-signal states, drop handling, minimum-valid-data rules for scores) directly address this gap.
- **Independent replay audit** — Healium's dashboard shows summaries; it does not (publicly) allow re-analysis of the underlying session data. CIRCLE's replay-audit capability is a clear differentiator.
- **Consent and privacy** — Healium sells organizational deployments with a "privacy wall" for wellness vs. clinician access for clinical; CIRCLE's consent gate can make data release an explicit, per-session, auditable user decision rather than a platform tier.

## Suggested original implementation ideas for CIRCLE

1. **Diegetic feedback layer for the browser workbench:** a small "aura" widget — an ambient WebGL/canvas light whose brightness and hue track a quality-gated calmness index derived from the simulated PPG/EDA streams, with the raw traces available in a collapsible "instrument" panel. Diegetic by default, instrument-grade on demand.
2. **Baseline-relative session score with a validity certificate:** implement "% time below session-start baseline" like Healium, but export it with the baseline window, artifact-rejection log, and signal-quality timeline, so the score is independently recomputable during replay audit — and flag sessions whose baseline fails a stability gate rather than letting a noisy baseline inflate the score.
3. **Session designer with protocol cards:** goal (calm/focus), duration, target modality, feedback mapping (visual gain, thresholds), and active-vs-sham arm assignment, saved as versioned JSON protocol files that replay deterministically.
4. **Sensor-loss rehearsal mode:** since CIRCLE simulates streams, deliberately scripted dropouts and motion artifacts in the simulated PPG/EDA/IMU feeds to exercise quality gates and error UI — something no Healium page documents but every real deployment needs.
5. **Group evidence explorer:** panel-level aggregate trend views (like Healium's clinic dashboard) built on top of exported evidence bundles, with active-vs-sham comparison as the default lens and per-session drill-down into replayable raw data.
