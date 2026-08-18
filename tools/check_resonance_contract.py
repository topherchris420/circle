"""Semantic and contract validator for CIRCLE Resonance research module."""

from __future__ import annotations

import json
import math
import pathlib
import sys
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts/resonance-intervention.schema.json"
CONFIGS_PATH = ROOT / "experiments/resonance/configurations.example.json"
MANIFEST_PATH = ROOT / "hardware/design-manifest.json"

PHI = (1.0 + math.sqrt(5.0)) / 2.0


def check_schema_structure() -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Missing schema: {SCHEMA_PATH}")

    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    required = data.get("required", [])
    for field in [
        "schema_version",
        "experiment_id",
        "configuration_id",
        "geometry",
        "drive_channels",
        "power_and_energy",
        "timing",
        "provenance",
        "interpretation_level",
        "status_flags",
    ]:
        if field not in required:
            raise ValueError(f"Schema missing required field: {field}")

    defs = data.get("$defs", {})
    for def_key in ["geometry", "channelDrive", "driveChannels", "powerAndEnergy", "provenance", "interpretationLevel"]:
        if def_key not in defs:
            raise ValueError(f"Schema missing definition: $defs/{def_key}")

    print("resonance schema structure: OK")


def check_example_configurations() -> None:
    if not CONFIGS_PATH.exists():
        raise FileNotFoundError(f"Missing example configs: {CONFIGS_PATH}")

    data = json.loads(CONFIGS_PATH.read_text(encoding="utf-8"))
    configs = data.get("configurations", [])
    if len(configs) < 2:
        raise ValueError("configurations.example.json must contain at least 2 configurations.")

    for cfg in configs:
        geom = cfg["geometry"]
        pwr = cfg["power_and_energy"]

        # Energy conservation check
        if pwr["measured_output_power_w"] > pwr["input_power_w"]:
            raise ValueError(f"Energy conservation violation in {cfg['configuration_id']}: P_out > P_in")

        # Golden ratio check if nominal
        if geom["geometry_type"] == "GOLDEN_RATIO_SPHERES":
            outer = geom["outer_diameter_mm"]
            middle = geom["middle_diameter_mm"]
            inner = geom["inner_diameter_mm"]
            if abs(middle - (outer / PHI)) > 0.1:
                raise ValueError(f"Middle diameter {middle} does not match outer / phi ({outer / PHI})")
            if abs(inner - (outer / (PHI ** 2))) > 0.1:
                raise ValueError(f"Inner diameter {inner} does not match outer / phi^2 ({outer / (PHI ** 2)})")

        # Provenance check: Simulated data must not be tagged RAW_MEASURED
        if "sim" in cfg["experiment_id"] and cfg["provenance"] == "RAW_MEASURED":
            raise ValueError("Simulated experiment cannot have provenance RAW_MEASURED")

    print(f"example configurations ({len(configs)} configs verified): OK")


def check_safety_isolation_contract() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    # Verify that no human domain net or connector has resonance drives
    human_nets = set(manifest.get("required_nets", []))
    forbidden = ["RESONANCE_DRIVE", "R_OUTER_V", "R_CORE_RF", "CHAMBER_HV"]
    for net in human_nets:
        for f in forbidden:
            if f in net:
                raise ValueError(f"Safety violation: forbidden resonance net found in BAT_HUMAN manifest: {net}")

    print("resonance safety isolation contract: OK")


def main() -> None:
    check_schema_structure()
    check_example_configurations()
    check_safety_isolation_contract()
    print("all resonance contracts: OK")


if __name__ == "__main__":
    main()
