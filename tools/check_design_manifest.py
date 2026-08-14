import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_CIRCLE_MAIN_SHEETS = [
    "00_root",
    "01_compute_usb",
    "02_power",
    "03_eda_safety",
    "04_sensors",
    "05_storage",
    "06_sync_isolation",
    "07_feedback_expansion",
    "08_observability",
]
EXPECTED_CIRCLE_PPG_SHEETS = ["00_ppg_root"]
EXPECTED_CONNECTORS = [
    {"name": "USB_C", "domain": "BAT_HUMAN", "eda_policy": "forces_disabled", "pins": ["VBUS_5V", "USB_DN", "USB_DP", "USB_CC1", "USB_CC2", "USB_SHIELD"]},
    {"name": "BATTERY", "domain": "BAT_HUMAN", "eda_policy": "internal_only", "pins": ["BAT_POS", "BAT_NEG", "BAT_NTC"]},
    {"name": "EDA_ELECTRODES", "domain": "BAT_HUMAN", "eda_policy": "internal_only", "pins": ["EDA_DRIVE_P", "EDA_DRIVE_N", "EDA_SENSE_P", "EDA_SENSE_N"]},
    {"name": "PPG_HEAD", "domain": "BAT_HUMAN", "eda_policy": "internal_only", "pins": ["PPG_3V3", "PPG_LED_PWR", "PPG_SDA_3V3", "PPG_SCL_3V3", "PPG_INT", "PPG_MOTION_INT", "PPG_BOARD_ID", "PPG_LOGIC_GND", "PPG_LED_GND"]},
    {"name": "SYNC_IN_BNC", "domain": "LAB_ISO", "eda_policy": "isolated", "pins": ["SYNC_IN_LAB", "LAB_ISO_GND"]},
    {"name": "SYNC_OUT_BNC", "domain": "LAB_ISO", "eda_policy": "isolated", "pins": ["SYNC_OUT_LAB", "LAB_ISO_GND"]},
    {"name": "DEBUG", "domain": "BAT_HUMAN", "eda_policy": "forces_disabled", "pins": ["UART_TX", "UART_RX", "DEBUG_ATTACHED", "BAT_HUMAN_GND"]},
    {"name": "INTERNAL_EXPANSION", "domain": "BAT_HUMAN", "eda_policy": "internal_only", "pins": ["I2C_SDA_3V3", "I2C_SCL_3V3", "GPIO_EXP_INT", "BAT_HUMAN_GND"]},
    {"name": "EXTERNAL_EXPANSION", "domain": "BAT_HUMAN", "eda_policy": "forces_disabled", "pins": ["EXP_3V3", "EXP_UART_TX", "EXP_UART_RX", "EXTERNAL_EXPANSION_ATTACHED", "BAT_HUMAN_GND"]},
    {"name": "HAPTIC", "domain": "BAT_HUMAN", "eda_policy": "internal_only", "pins": ["HAPTIC_VDRV", "HAPTIC_CURRENT_EDGE", "BAT_HUMAN_GND"]},
    {"name": "MICROSD", "domain": "BAT_HUMAN", "eda_policy": "internal_only", "pins": ["SD_D0", "SD_D1", "SD_D2", "SD_D3", "SD_CLK", "SD_CMD", "BAT_HUMAN_GND"]},
]


def validate(design, interfaces) -> list[str]:
    errors: list[str] = []
    if not isinstance(design, dict):
        errors.append("design: root must be an object")
        return errors + validate({}, interfaces)
    if not isinstance(interfaces, dict):
        errors.append("interfaces: root must be an object")
        return errors + validate(design, {})

    boards = design.get("boards")
    if not isinstance(boards, dict):
        errors.append("design: missing or invalid boards")
    else:
        main_sheets = boards.get("circle-main", {}).get("sheets")
        ppg_sheets = boards.get("circle-ppg", {}).get("sheets")
        if not isinstance(main_sheets, list):
            errors.append("design: circle-main sheets missing or invalid")
        else:
            main_names = [sheet.get("name") if isinstance(sheet, dict) else None for sheet in main_sheets]
            if main_names != EXPECTED_CIRCLE_MAIN_SHEETS:
                errors.append("design: circle-main sheet sequence mismatch")
        if not isinstance(ppg_sheets, list):
            errors.append("design: circle-ppg sheets missing or invalid")
        else:
            ppg_names = [sheet.get("name") if isinstance(sheet, dict) else None for sheet in ppg_sheets]
            if ppg_names != EXPECTED_CIRCLE_PPG_SHEETS:
                errors.append("design: circle-ppg sheet sequence mismatch")

    parts = design.get("parts")
    if not isinstance(parts, list):
        errors.append("design: missing or invalid parts")
    else:
        refs = [part.get("ref") for part in parts if isinstance(part, dict)]
        if len(refs) != len(set(refs)):
            errors.append("duplicate reference designator")

    connectors = interfaces.get("connectors")
    if not isinstance(connectors, list):
        errors.append("interfaces: missing or invalid connectors")
        return errors
    if connectors != EXPECTED_CONNECTORS:
        errors.append("interfaces: connector contract mismatch")
    for connector in connectors:
        if not isinstance(connector, dict):
            errors.append("interfaces: invalid connector entry")
            continue
        pins = connector.get("pins")
        name = connector.get("name", "<unknown>")
        if not isinstance(pins, list):
            errors.append(f"{name}: invalid pin list")
            continue
        if not pins:
            errors.append(f"{name}: empty pin list")
        if connector.get("domain") == "LAB_ISO" and "BAT_HUMAN_GND" in pins:
            errors.append(f"{name}: LAB_ISO connector exposes BAT_HUMAN_GND")
    return errors


def main() -> int:
    try:
        design = json.loads((ROOT / "hardware/design-manifest.json").read_text(encoding="utf-8"))
        interfaces = json.loads((ROOT / "hardware/interfaces.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("ERROR: failed to read design/interface JSON")
        return 1

    errors = validate(design, interfaces)
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("design manifest: OK")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
