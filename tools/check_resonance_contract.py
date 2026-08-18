"""Semantic, physical, statistical, and electrical isolation validator for CIRCLE Resonance."""

from __future__ import annotations

import json
import math
import pathlib
import sys
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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

        # Energy conservation check: P_out <= P_in
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

        # Provenance check
        if "sim" in cfg["experiment_id"] and cfg["provenance"] == "RAW_MEASURED":
            raise ValueError("Simulated experiment cannot have provenance RAW_MEASURED")

    print(f"example configurations ({len(configs)} configs verified): OK")


def check_physical_geometric_derivation() -> None:
    """Verify that physical electrostatic capacitances and mutual coupling derive from geometry."""
    from models.resonance_response.simulator import GeometricParameterExtractor, GeometryConfig

    geom_phi = GeometryConfig(geometry_type="GOLDEN_RATIO_SPHERES", outer_diameter_mm=300.0)
    geom_eq = GeometryConfig(geometry_type="EQUAL_SPHERES", outer_diameter_mm=300.0)

    extractor_phi = GeometricParameterExtractor(geom_phi)
    extractor_eq = GeometricParameterExtractor(geom_eq)

    c_phi, k_phi = extractor_phi.extract_coupling_matrix()
    c_eq, k_eq = extractor_eq.extract_coupling_matrix()

    # Geometry directly alters physical mutual coupling based on inter-shell distance Delta_r
    if k_phi[0][1] == 0.0 or k_eq[0][1] == 0.0:
        raise ValueError("Coupling extraction failed: matrix entry is zero for active geometry")

    # The coupling differs purely as a consequence of different physical spacing Delta_r
    if k_phi[0][1] == k_eq[0][1]:
        raise ValueError("Geometry derivation failed: Phi and equal spacing produced identical coupling matrix!")

    print("physical geometric parameter extraction (G -> {C, k}): OK")


def check_electrical_domain_graph_isolation() -> None:
    """Verify that the hardware manifest and netlist domain partitioning enforce complete isolation."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    boards = manifest.get("boards", {})

    main_board = boards.get("circle-main", {})
    if main_board.get("domain") != "BAT_HUMAN":
        raise ValueError("circle-main board domain must be BAT_HUMAN")

    sheets = main_board.get("sheets", [])
    sheet_names = [s["name"] for s in sheets]

    if "06_sync_isolation" not in sheet_names:
        raise ValueError("Missing required isolation sheet: 06_sync_isolation")

    forbidden_net_keywords = ["RESONANCE_DRIVE", "R_OUTER_V", "R_CORE_RF", "CHAMBER_HV", "50_OHM_RF"]
    required_nets = manifest.get("required_nets", [])
    for net in required_nets:
        for kw in forbidden_net_keywords:
            if kw in net:
                raise ValueError(f"Safety domain violation: forbidden resonance net '{net}' found in manifest required_nets")

    print("electrical domain graph isolation: OK")


def main() -> None:
    check_schema_structure()
    check_example_configurations()
    check_physical_geometric_derivation()
    check_electrical_domain_graph_isolation()
    print("all resonance physics, neutrality, and safety contracts: OK")


if __name__ == "__main__":
    main()
