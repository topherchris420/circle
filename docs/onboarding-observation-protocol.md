# CIRCLE: uncoached public onboarding study

**STATUS: NOT YET RUN.** This is an evaluation plan, not an observed outcome.

Recruit at least five volunteers unfamiliar with CIRCLE, with anonymous task
tracking and consent. On mobile and desktop, ask each to:

1. Reach the no-install demo from the landing page and explain whether the
   scenario used real human measurements.
2. Play a session, find a deliberate signal-quality failure and explain why
   feedback was withheld.
3. Distinguish First Light's public real-camera recordings from its live
   phone-camera path (not physically tested by the authors).
4. Find the repository, evidence verifier and setup instructions.
5. Navigate without horizontal overflow, hidden controls or unwanted audio.

Record completion, time, errors, confusion and participants' own explanations,
with no health records. Examine keyboard navigation, reduced-motion support,
screen-reader labels and audio-off defaults. Publish aggregate outcomes and
first-round failures, fix blockers, and repeat with new participants.

One required site-owner step remains: under **Settings → Pages → Build and
deployment**, set **Source = GitHub Actions**, not Deploy from a branch.
The automated deployment checker cannot itself remove the competing Jekyll
publisher. See [Pages deployment incident](github-pages.md).
