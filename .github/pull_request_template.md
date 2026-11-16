## What this changes

<!-- One question or change per pull request. What does a user, researcher, or reviewer see differently? -->

## Evidence

<!-- What evidence does this produce or affect? Name the seeds, scenarios, verdicts, or benchmarks.
     For a fix, describe the check that would have caught the bug. -->

## Checks

- [ ] `python -m unittest discover -s tests` passes
- [ ] `python tools/verify_release.py --software-only` passes, or the reason it was not run is stated
- [ ] Regenerated artifacts (diagrams, schematic packages, reports) are committed if a generator changed
- [ ] If the workbench UI changed: checked in a browser, and `python tools/build_demo.py` still builds the offline demo
- [ ] No new claim goes beyond the evidence; simulated results stay labeled as simulated
