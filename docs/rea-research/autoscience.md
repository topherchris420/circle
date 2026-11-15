# Autoscience (Autoscience Institute) — Evidence report

Autoscience (autoscience.ai, doing business as Autoscience Institute, San Mateo, CA) is a venture-backed startup whose stated mission is to "accelerate discovery by automating AI research," i.e., automating the research and development of machine learning itself. The company first gained public attention in March 2025 when its AI system **Carl** produced papers that passed peer review at ICLR 2025 workshops — billed as the first AI system to produce academically peer-reviewed research — and later demonstrated an autonomously generated *full-length* workshop paper. In January 2026 it announced **Mira**, an "ML Research Agent" product that autonomously improves customers' machine learning models against a user-specified evaluation metric, and in March 2026 it announced a $14M seed round led by General Catalyst (with Perplexity Fund, Toyota Ventures, S32, and MaC Ventures) to scale what it calls an "Automated AI Research Lab." As of late 2026 Autoscience is an active, funded commercial company offering Mira (ML research agent) and Carl (research synthesis), positioning AI agents as the primary researcher inside a human-organized research organization. Its work is frequently discussed alongside Sakana AI's "The AI Scientist" (which achieved a peer-reviewed workshop paper via a different system, later published in Nature as "Towards end-to-end automation of AI research"), though Autoscience maintains its Carl milestones came first; the priority claim is contested in press coverage.

## Sources consulted

- `https://www.autoscience.ai/blog/meet-carl` — Carl announcement: hypothesis generation, experiment design and execution, paper writing, ICLR 2025 workshop acceptances, verification and validation practices, withdrawal of papers.
  - Note: direct fetches of autoscience.ai pages repeatedly returned no content to this agent's fetcher; page content was instead obtained via search-engine-rendered text of the same public URLs. Treat quoted wording as coming from those rendered pages.
- `https://www.autoscience.ai/blog/carl-full-paper` — first full-length peer-reviewed Carl paper; scope of human edits; full-length track acceptance.
- `https://www.autoscience.ai/blog/introducing-mira` — Mira product announcement; Kaggle Santa 2025 silver medal; system powered by Carl.
- `https://www.autoscience.ai/blog/autoscience-autonomous-ai-lab` — $14M seed round (March 2026); Automated AI Research Lab framing; parallel-agent methodology; motivation (2,000+ ML papers/week).
- `https://www.autoscience.ai/mira` and `https://www.autoscience.ai/carl` — product pages: Mira's experiment/verify loop, "you name the metric" optimization, isolated training runs; Carl positioned as research synthesis.
- `https://www.autoscience.ai/blog` — blog index confirming post dates and product/research split.
- `https://www.rdworldonline.com/startup-autoscience-says-its-ai-agent-carl-just-wrote-the-first-academically-peer-reviewed-paper/` — independent press: CEO Tom Cowan quotes; paper title "Investigating Alignment Signals in Initial Token Representations."
- `https://www.rdworldonline.com/autoscience-raises-14m-seed-round-to-scale-its-autonomous-ai-research-lab/` — independent press on funding, Kaggle result, parallel-agent approach.
- `https://www.siliconangle.com/2026/03/19/autoscience-builds-automated-research-lab-machine-learning-models-14m/` — launch coverage (date/market context).
- `https://www.scientificamerican.com/article/ai-wrote-a-scientific-paper-that-passed-peer-review/` — context on Sakana's AI Scientist and the disputed "first" claim regarding Autoscience.
- `https://www.nature.com/articles/s41586-026-10265-5` and `https://arxiv.org/abs/2408.06292` — related (non-Autoscience) AI Scientist work used only as comparative context.

## Findings

### Autonomous experimentation

- **OBSERVED** — Carl "successfully ideated novel scientific hypotheses, designed and performed experiments, and wrote multiple academic papers that passed peer review at workshops in the International Conference on Learning Representations (ICLR)" (Meet Carl blog post).
- **OBSERVED** — Mira autonomously improves ML models: "spins up isolated training runs, tracks loss curves, compares against your baseline," and "Only variants that beat your baseline on your verifier ship" (Mira product page).
- **OBSERVED** — Mira "works without human intervention beyond an initial setup"; it was entered into a live $50k Kaggle competition (Santa 2025, Christmas Tree Packing Challenge) and won a Silver Medal against 3,300 teams, which the company describes as the first fully autonomous system to place in a featured Kaggle competition (Introducing Mira blog; press coverage).
- **DOCUMENTED** — Autoscience's stated methodology is "running autonomous research agents in parallel against the same problem, then selecting the best results" (CEO comments reported by R&D World).
- **DOCUMENTED** — The company frames a "research organization where the researcher is driven by AI systems," aiming to "compress years of machine learning research into months" (funding announcement, March 2026).
- **INFERRED** — Carl is described as an "Automated Academic Researcher" that powers Mira; the internal architecture (agent harness, model backbone, how ablations are chosen) is not publicly detailed beyond a referenced "Carl Technical Report," whose full contents were not retrieved here.

### Experiment evaluation and verification

- **OBSERVED** — Mira's workflow ends in an explicit VERIFY stage driven by the customer's own eval: "You name the metric. Mira optimizes for it," including quality, inference speed, and cost/resource-efficiency axes (Mira product page).
- **OBSERVED** — External benchmark framing: Kaggle Santa 2025 placement is used as a third-party-verifiable performance signal rather than only self-reported metrics (Introducing Mira blog).
- **OBSERVED** — Before submitting Carl's papers, the team "rigorously reviewed Carl's research," and the papers "passed two plagiarism checkers and a citation checker to reduce the likelihood of accidental academic violations" (Meet Carl blog).
- **DOCUMENTED** — Carl's full-length paper passed ICLR 2025 workshop peer review with "every review for the paper exceeded the acceptance threshold"; human edits were "limited to citations and formatting" (Carl full paper blog; R&D World coverage).
- **INFERRED** — Peer review serves as Autoscience's principal external evaluation mechanism for research claims, with Kaggle leaderboards and customer evals serving as the principal evaluation mechanisms for Mira; no published standardized autonomous-science benchmark authored by Autoscience was found.

### Human oversight of AI-generated research

- **OBSERVED** — Autoscience voluntarily withdrew its accepted papers from the ICLR workshops after acceptance, stating that organizers "may not have sufficient time to thoughtfully establish and implement new standards and procedures appropriately geared toward autonomous AI scientists" (Meet Carl blog).
- **OBSERVED** — Human pre-submission review, plagiarism checks, and citation checks were applied before any peer-review submission (Meet Carl blog).
- **DOCUMENTED** — Press coverage (Scientific American) notes Autoscience stated its papers were accepted at ICLR workshops before Sakana's AI Scientist, a priority claim that other coverage contextualizes; this is a disputed provenance question, not a settled fact.
- **INFERRED** — The operating philosophy appears to be "full autonomy in generation, human gating in publication": humans intervene at verification and submission boundaries rather than inside the experiment loop. Autoscience has not published a formal oversight policy document, so the degree of oversight beyond these examples is unknown.
- **UNVERIFIED** — Any claims about internal safety controls, run isolation guarantees for customer models, or audit logging in Mira/Carl; product pages show a "verify" stage but no published audit-trail specification.

### Evidence-based workflow structure

- **OBSERVED** — The Mira loop is structured as numbered stages (experiment → track metrics → compare against baseline → verify against the user's eval), making baseline comparison and the user-chosen verifier explicit gates (Mira product page).
- **OBSERVED** — Motivation is explicitly evidence-overload-driven: "more than 2,000 machine learning papers published every week, no human research team can effectively evaluate and implement every new breakthrough" (funding announcement).
- **INFERRED** — Carl's "research synthesis" product positioning (automated literature absorption feeding Mira's model improvements) suggests a pipeline of claim extraction → hypothesis → experiment → verified improvement, but intermediate artifacts (e.g., structured evidence records) are not published.

## Evidence log

| Claim | Classification | Source URL |
|---|---|---|
| Carl ideated hypotheses, designed/ran experiments, wrote papers passing ICLR 2025 workshop peer review | OBSERVED | https://www.autoscience.ai/blog/meet-carl |
| First full-length Carl paper accepted at ICLR 2025 workshop; only human edits were citations/formatting | OBSERVED | https://www.autoscience.ai/blog/carl-full-paper |
| Papers passed two plagiarism checkers and a citation checker pre-submission | OBSERVED | https://www.autoscience.ai/blog/meet-carl |
| Autoscience withdrew accepted papers pending community standards for AI scientists | OBSERVED | https://www.autoscience.ai/blog/meet-carl |
| Mira won Silver Medal in Kaggle Santa 2025 vs 3,300 teams; first autonomous placement in a featured Kaggle competition | OBSERVED | https://www.autoscience.ai/blog/introducing-mira |
| Mira runs isolated training runs, tracks loss curves, ships only variants that beat baseline on user's verifier | OBSERVED | https://www.autoscience.ai/mira |
| Methodology of parallel autonomous agents with best-result selection | DOCUMENTED | https://www.rdworldonline.com/autoscience-raises-14m-seed-round-to-scale-its-autonomous-ai-research-lab/ |
| $14M seed led by General Catalyst, March 2026 | OBSERVED | https://www.autoscience.ai/blog/autoscience-autonomous-ai-lab |
| Paper title "Investigating Alignment Signals in Initial Token Representations"; CEO Tom Cowan quotes | DOCUMENTED | https://www.rdworldonline.com/startup-autoscience-says-its-ai-agent-carl-just-wrote-the-first-academically-peer-reviewed-paper/ |
| Priority of Autoscience's peer-review milestone relative to Sakana's AI Scientist is contested | DOCUMENTED | https://www.scientificamerican.com/article/ai-wrote-a-scientific-paper-that-passed-peer-review/ |
| Internal Carl architecture details; "Carl Technical Report" contents | UNVERIFIED | https://www.autoscience.ai/blog/meet-carl (report referenced, not retrieved) |
| Degree of routine human oversight inside Mira/Carl loops | UNVERIFIED | (no published policy found) |

## Missing evidence and inaccessible functionality

- The **Carl Technical Report** is referenced but its full text was not retrieved; Carl's internal architecture, agent design, and evaluation rubrics remain UNVERIFIED.
- Direct fetching of autoscience.ai pages failed from this environment; page content was confirmed only through search-engine-rendered text. Interactive product functionality (Mira onboarding, `/get-started` flow, Carl research-synthesis UI) was not exercised.
- No published documentation found on: consent/ethics policies for autonomously conducted research, data provenance rules, audit trails, or reproducibility artifacts for Carl-generated papers (beyond links to accepted PDFs on Google Drive).
- No standardized public benchmark authored by Autoscience was found; evaluation evidence relies on peer review, Kaggle, and customer evals.

## Relevance to CIRCLE

- **Proposal vs. control separation.** Autoscience's split between autonomous hypothesis/experiment generation (Carl/Mira agents) and externally imposed verification gates (peer review, Kaggle leaderboard, the customer's baseline eval) maps directly onto CIRCLE's planned R.A.I.N. adapter: an external agent may *propose* experiments and improvements, but only changes that beat the baseline on the operator's own verifier are allowed to ship. CIRCLE's deterministic controller should play the role of Mira's "VERIFY" stage — a hard, non-negotiable gate the proposing agent cannot rewrite.
- **Parallel proposal with selection.** Autoscience runs many autonomous agents against the same problem and selects the best result. A CIRCLE R.A.I.N. adapter could generate multiple candidate experiment proposals, with selection done by CIRCLE's deterministic validation rules (preregistered protocol conformance, safety envelope, consent checks), never by the proposing model itself.
- **Pre-submission verification battery.** Carl's workflow (internal review + plagiarism/citation checks before submission) suggests CIRCLE should attach machine-checkable validation artifacts to every experiment registration: originality/consistency checks, provenance-verified citations, and schema validation before an experiment becomes runnable.
- **External, third-party-verifiable evaluation.** Autoscience leans on externally adjudicated signals (peer review, Kaggle). CIRCLE's evidence export should similarly produce artifacts that a third party can audit independently (replay audit), rather than trusting the workbench's self-report.
- **Consent and withdrawal as governance.** Autoscience's voluntary withdrawal of accepted papers shows evaluation status is a lifecycle property, not a terminal state; CIRCLE's experiment registry should likewise support withdrawing/superseding a registered experiment while preserving the full audit trail.
- **Caution for CIRCLE:** Autoscience's philosophy is "automating AI research" with humans at publication boundaries; CIRCLE's consent-gated, human-in-the-loop physiological domain requires stricter boundaries — the R.A.I.N. adapter must remain advisory, and its proposals must pass the consent gate and safety checks exactly like human-authored ones.

## Suggested original implementation ideas for CIRCLE

1. **Proposal/verification split in the experiment schema**: model a R.A.I.N. (or any AI) proposal as a first-class registry object with `proposed_by`, `hypothesis`, `predicted_effect`, and `verification_plan` fields, where `verification_plan` is authored/owned by CIRCLE's deterministic layer and cannot be edited by the proposer.
2. **Baseline-gated auto-improvement for controller parameters**: mirroring Mira's "only variants that beat your baseline ship," allow (opt-in) automated sweeps of *controller parameters only* where a candidate change is promoted only if it beats the preregistered baseline outcome on replayed historical sessions — never live sessions.
3. **Pre-registration verification battery**: an automated checklist run at registration time (schema conformance, citation/provenance checks analogous to Carl's plagiarism/citation checkers, consent-scope compatibility, safety-envelope arithmetic) whose results are stored as evidence attached to the experiment record.
4. **Multi-proposal tournament with deterministic selection**: when an external agent proposes N experiments, run them as *simulated* trials in the stream simulator and rank by preregistered success criteria, surfacing the ranking in the evidence explorer with per-proposal provenance.
5. **Withdrawal/supersession lifecycle**: registry states for registered → running → completed → withdrawn/superseded, where withdrawal (à la Autoscience's ICLR withdrawal) preserves all artifacts and records the reason, keeping the audit trail intact.
6. **External-evidence export format**: a signed export bundle (protocol, raw streams, controller decisions, outcome evaluation) designed so an independent auditor could "peer review" a CIRCLE experiment without access to the workbench — the CIRCLE analogue of submitting to an external venue.
7. **Evidence-overload triage view**: motivated by Autoscience's 2,000-papers-per-week framing, add an evidence-explorer view that ranks and clusters registered experiments/outcomes so a human curator can triage large volumes of AI-proposed experiment results.
