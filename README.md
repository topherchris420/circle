# CIRCLE Rev A

> **ENGINEERING REVIEW ONLY** — Experimental research hardware. This repository is not approved for fabrication or human connection and does not establish medical-device, electrical-safety, EMC, or measurement-performance claims.

The repository contains the architecture diagrams, safety contracts, validation documents, and KiCad 10 schematics for the CIRCLE Rev A bench validation platform.

## Verify the review package

```powershell
py -3.11 tools/verify_release.py
```

Success means the generated artifacts are reproducible, both KiCad projects parse, and no unexplained ERC error remains. It does not authorize fabrication or human connection. KiCad 10.0.5 validates and exports the legacy review sources; native .kicad_sch conversion remains open because kicad-cli sch upgrade does not import legacy .sch.
