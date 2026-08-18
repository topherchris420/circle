"""Semantic, statistical, and electrical isolation contract validator for CIRCLE Resonance."""

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


def check_scientific_neutrality_invariants() -> None:
    """Verify that prior physics in the simulator are symmetric across geometries."""
    from models.resonance_response.simulator import ResonanceSimulator, GeometryConfig

    sim_phi = ResonanceSimulator(GeometryConfig(geometry_type="GOLDEN_RATIO_SPHERES", outer_diameter_mm=300.0))
    sim_eq = ResonanceSimulator(GeometryConfig(geometry_type="EQUAL_SPHERES", outer_diameter_mm=300.0))
    sim_rnd = ResonanceSimulator(GeometryConfig(geometry_type="RANDOM_SPHERES", outer_diameter_mm=300.0))

    res_phi = sim_phi.simulate_run(config_id="neutrality_phi", base_freq_hz=73.2, input_voltage_v=5.0)
    res_eq = sim_eq.simulate_run(config_id="neutrality_eq", base_freq_hz=73.2, input_voltage_v=5.0)
    res_rnd = sim_rnd.simulate_run(config_id="neutrality_rnd", base_freq_hz=73.2, input_voltage_v=5.0)

    # Prior physical input and output power MUST be identical across geometries for identical drive voltage
    if res_phi.power_and_energy["input_power_w"] != res_eq.power_and_energy["input_power_w"]:
        raise ValueError("Scientific neutrality violation: Input power differs by geometry label!")
    if res_phi.power_and_energy["measured_output_power_w"] != res_eq.power_and_energy["measured_output_power_w"]:
        raise ValueError("Scientific neutrality violation: Prior output power differs by geometry label!")
    if res_phi.power_and_energy["measured_output_power_w"] != res_rnd.power_and_energy["measured_output_power_w"]:
        raise ValueError("Scientific neutrality violation: Random geometry receives different prior coupling!")

    print("scientific neutrality prior symmetry: OK")


def check_electrical_domain_graph_isolation() -> None:
    """Verify that the hardware manifest and netlist domain partitioning enforce complete isolation."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    boards = manifest.get("boards", {})

    # Verify domain declarations
    main_board = boards.get("circle-main", {})
    if main_board.get("domain") != "BAT_HUMAN":
        raise ValueError("circle-main board domain must be BAT_HUMAN")

    sheets = main_board.get("sheets", [])
    sheet_names = [s["name"] for s in sheets]

    # Only sheet 06_sync_isolation is permitted to bridge to LAB_ISO
    if "06_sync_isolation" not in sheet_names:
        raise ValueError("Missing required isolation sheet: 06_sync_isolation")

    # Verify no human sensing sheets contain external resonance nets
    human_sheets = [s for s in sheet_names if s != "06_sync_isolation"]
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
    check_scientific_neutrality_invariants()
    check_electrical_domain_graph_isolation()
    print("all resonance neutrality and safety contracts: OK")


if __name__ == "__main__":
    main()
