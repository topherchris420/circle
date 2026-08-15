# CIRCLE Rev A

> **ENGINEERING REVIEW ONLY** — Experimental research hardware. This repository is not approved for fabrication or human connection and does not establish medical-device, electrical-safety, EMC, or measurement-performance claims.

The repository contains the architecture diagrams, safety contracts, validation documents, and KiCad 10 schematics for the CIRCLE Rev A bench validation platform.

## Overview

CIRCLE is a two-board, battery-domain research instrument for reviewing a synchronized sensing and feedback architecture:

- **`circle-main`** combines ESP32-S3 compute, battery and power management, protected electrodermal-activity (EDA) acquisition, IMU capture, microSD storage, isolated synchronization, haptic feedback, and observability.
- **`circle-ppg`** is a keyed, replaceable optical contact board that preserves raw red and infrared measurements.

The design separates the human-connected `BAT_HUMAN` domain from the laboratory `LAB_ISO` domain. USB, debug, and external-expansion attachment force the hardware EDA path off; isolated SYNC is the intended boundary between the two domains. See the [architecture](docs/architecture.md) and [safety analysis](docs/safety-analysis.md) before reviewing the schematics.

![CIRCLE Rev A safety boundaries](diagrams/safety-boundaries.svg)

## Review status and limitations

This package is intended to make the Rev A design reviewable and reproducible—not buildable or deployable.

- The safety, power, isolation, signal-integrity, and footprint items in the [review gates](docs/review-gates.md) remain fabrication blockers.
- Component values marked `REVIEW_GATE` require independent calculation, CAD review, and bench evidence.
- KiCad 10.0.5 can parse, ERC-check, and export the generated legacy `.sch` review sources. Native `.kicad_sch` conversion is still open because `kicad-cli sch upgrade` does not import legacy `.sch` files.
- ERC validates parser-visible structure. Architecture-level `NET:` annotations are not fabrication-ready electrical connectivity.
- No fabrication, powered-electrode, human-subject, EMC, regulatory, or measurement-performance validation has been completed.

Passing the repository checks does **not** close a review gate or authorize fabrication or human connection.

## Repository guide

| Path | Contents |
| --- | --- |
| [`contracts/`](contracts/) | JSON Schema for session records, provenance, timing, sequence ranges, status, and checksums |
| [`diagrams/`](diagrams/) | System-architecture and safety-boundary diagrams in Mermaid and rendered SVG forms |
| [`docs/`](docs/) | Architecture, safety analysis, pin allocation, timing/data model, power budget, validation plan, and review gates |
| [`hardware/design-manifest.json`](hardware/design-manifest.json) | Board hierarchy, required nets, parts, GPIO allocation, and unresolved review gates |
| [`hardware/interfaces.json`](hardware/interfaces.json) | Connector pin ordering, electrical domains, and EDA attachment policy |
| [`hardware/circle-main/`](hardware/circle-main/) | Main-board KiCad project and generated legacy schematic sheets |
| [`hardware/circle-ppg/`](hardware/circle-ppg/) | Optical-board KiCad project and generated legacy schematic sheet |
| [`hardware/reports/`](hardware/reports/) | ERC inputs/allowlist, toolchain record, and latest verification summary |
| [`tools/`](tools/) | Deterministic generators and contract, schema, ERC, and release checks |
| [`tests/`](tests/) | Standard-library unit tests for repository and generated-artifact contracts |

## Prerequisites

The pinned toolchain is recorded in [`toolchain.json`](toolchain.json):

- Python 3.11 or newer
- KiCad CLI 10.0.5 for the complete release verification
- UTF-8 text and LF line endings

The Python checks use only the standard library; no package installation is required.

## Verify the review package

### Fast, platform-independent checks

Run the unit tests and contract validators without KiCad:

```bash
python -m unittest discover -s tests
python tools/check_design_manifest.py
python tools/check_record_schema.py
```

### Complete release verification

`verify_release.py` runs the tests and validators, regenerates diagrams and schematics, invokes KiCad ERC for both boards, checks the ERC allowlist, and writes `hardware/reports/verification-summary.json`.

On Windows, its default KiCad location is `%USERPROFILE%\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe`:

```powershell
py -3.11 tools/verify_release.py
```

If KiCad is installed elsewhere, set `KICAD_CLI` explicitly. For example, on POSIX systems:

```bash
KICAD_CLI=/usr/bin/kicad-cli python tools/verify_release.py
```

A successful run ends with:

```text
CIRCLE Rev A review package: VERIFIED
```

Because the full command rewrites generated artifacts and reports, run it from a clean worktree and inspect `git diff` afterward. Reproducible output should not introduce an unexplained diff.

## Regenerate individual artifacts

Use the source-controlled generators rather than hand-editing generated output:

```bash
# Render both SVG architecture diagrams
python tools/render_diagrams.py

# Generate the main-board legacy schematic package
python tools/generate_schematics.py

# Generate the optical-board legacy schematic package
python tools/generate_schematics.py --board circle-ppg
```

After regeneration, run at least the fast checks above. Changes intended for a complete review package should also pass `tools/verify_release.py` with the pinned KiCad version.

## Suggested review order

1. Read the [architecture](docs/architecture.md) and inspect the [system diagram](diagrams/system-architecture.svg).
2. Review the [safety analysis](docs/safety-analysis.md) and [safety-boundary diagram](diagrams/safety-boundaries.svg).
3. Confirm every unresolved item in the [review gates](docs/review-gates.md).
4. Check the [pin allocation](docs/pin-allocation.md), [power budget](docs/preliminary-power-budget.md), and [timing/data model](docs/timing-and-data-model.md) against the manifests and schematics.
5. Evaluate the evidence required by the [validation plan](docs/validation-plan.md).
6. Run the complete release verification and inspect the resulting [verification summary](hardware/reports/verification-summary.json).

## Data contract

[`contracts/session-record.schema.json`](contracts/session-record.schema.json) is the machine-readable contract for captured and derived records. It requires explicit record type, provenance, monotonic device-time bounds, status flags, and CRC-32C evidence; stream-oriented records also retain source identities and sequence ranges. Validate it with:

```bash
python tools/check_record_schema.py
```
