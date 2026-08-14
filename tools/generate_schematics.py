"""Generate deterministic review-only CIRCLE KiCad legacy schematics."""
from argparse import ArgumentParser
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.kicad_legacy import Component, LegacySheet, Pin, ProjectSymbol
EXPECTED_PPG_PINS = ["PPG_3V3", "PPG_LED_PWR", "PPG_SDA_3V3", "PPG_SCL_3V3", "PPG_INT", "PPG_MOTION_INT", "PPG_BOARD_ID", "PPG_LOGIC_GND", "PPG_LED_GND"]
SHEET_NETS = {
"00_root": ["BAT_HUMAN", "LAB_ISO", "BAT_HUMAN_GND", "LAB_ISO_GND", "NO COPPER OR WIRE JOINS THE TWO GROUND DOMAINS"],
"01_compute_usb": ["USB_PRESENT PRE-CHARGER SENSE", "USB_D_MINUS", "USB_D_PLUS", "DEBUG_ATTACHED", "GPIO45 RESET-LOW EDA_FW_REQUEST", "GPIO46 RESET-LOW HAPTIC_CURRENT_EDGE", "GPIO35-37 UNAVAILABLE OCTAL PSRAM", "U6 OBSERVABILITY ONLY - NOT EDA PERMISSION"],
"02_power": ["VBUS_5V", "USB_PRESENT", "VBAT", "BATTERY_VALID", "SAFETY_POWER_GOOD", "SW_SD", "SW_PPG_LED", "SW_HAPTIC", "SW_ISOLATION", "SW_EXPANSION"],
"03_eda_safety": ["EDA_PREPARE", "EDA_ACTIVE", "EDA_ANALOG_GOOD", "USB_PRESENT", "DEBUG_ATTACHED", "EXTERNAL_EXPANSION_ATTACHED", "EDA_FW_REQUEST", "REVIEW_GATE:EDA_LIMIT_NETWORK", "REVIEW_GATE:EDA_SWITCH_SELECTION", "PASSIVE LIMITS REMAIN SERIES UNDER ONE WELDED SWITCH"],
"04_sensors": ["IMU_SCLK", "IMU_MOSI", "IMU_MISO", "IMU_CS_N", "IMU_DRDY", "PPG_SDA_3V3", "PPG_SCL_3V3", "PPG_INT", "PPG_MOTION_INT", "PPG_BOARD_ID"],
"05_storage": ["SD_D0", "SD_D1", "SD_D2", "SD_D3", "SD_CLK", "SD_CMD", "SD_CARD_DETECT", "SAFE_EJECT", "ASYNCHRONOUS STORAGE NEVER BLOCKS CAPTURE"],
"06_sync_isolation": ["BAT_HUMAN_GND", "LAB_ISO_GND", "ISOW7742 REINFORCED BARRIER", "SYNC_IN_LAB 3V3/5V TTL COMPARATOR", "SYNC_IN_CAPTURE", "SYNC_OUT_DRIVE", "SYNC_OUT_LAB OPEN-DRAIN", "ISO_HEALTH_CHALLENGE", "ISO_HEALTH_STATUS"],
"07_feedback_expansion": ["DRV2605L", "HAPTIC_CURRENT_EDGE", "HAPTIC_FAULT", "INTERNAL_EXPANSION", "EXTERNAL_EXPANSION_ATTACHED", "ACTUATION COMMAND START COMPLETE FAULT EVIDENCE"],
"08_observability": ["TP_ALL_RAILS", "TP_USB_PRESENT", "TP_BATTERY_VALID", "TP_SAFETY_POWER_GOOD", "TP_EDA_ANALOG_GOOD", "TP_SYNC_BOTH_SIDES", "TP_SD_ACTIVITY", "FAULT_INJECTION", "NO LAB GROUND ON BAT_HUMAN TEST POINT"],
"00_ppg_root": ["MAX30102 RAW RED/IR ONLY", "PPG_3V3", "PPG_LED_PWR", "PPG_LOGIC_GND", "PPG_LED_GND", "PPG_SDA_3V3", "PPG_SCL_3V3", "PPG_INT", "AT24CS02 BOARD ID", "LIS2DW12 DNI", "OPTICAL KEEP-OUT AND AMBIENT-LIGHT EXCLUSION"],
}

def safe_symbol(value):
    return re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_") or "REVIEW_ITEM"

def load_contracts():
    design = json.loads((ROOT / "hardware/design-manifest.json").read_text(encoding="utf-8"))
    interfaces = json.loads((ROOT / "hardware/interfaces.json").read_text(encoding="utf-8"))
    if design.get("release_class") != "ENGINEERING_REVIEW_ONLY": raise SystemExit("refusing non-review release class")
    return design, interfaces

def cache_text(parts):
    names = sorted({safe_symbol(part["value"]) for part in parts})
    symbols = [ProjectSymbol(name, (Pin("A", "1", "P"), Pin("B", "2", "P"))).emit() for name in names]
    return "EESchema-LIBRARY Version 2.4\n#encoding utf-8\n" + "".join(symbols) + "#End Library\n"

def make_sheet(name, title, parts, child_names=()):
    sheet = LegacySheet(title)
    sheet.note("ENGINEERING REVIEW ONLY - NOT FOR HUMAN CONNECTION", 600, 400)
    for index, part in enumerate(parts):
        x = 1300 + (index % 4) * 2100; y = 1200 + (index // 4) * 800
        sheet.add(Component(part["ref"], safe_symbol(part["value"]), x, y, part["value"]))
    for index, child in enumerate(child_names):
        sheet.child_sheet(child, child + ".sch", 900 + (index % 2) * 4800, 1100 + (index // 2) * 1300)
    for index, net in enumerate(SHEET_NETS[name]):
        y = 5600 + (index % 8) * 240; x = 700 if index < 8 else 6000
        if re.fullmatch(r"[A-Z0-9_]+", net): sheet.label(net, x, y)
        else: sheet.note(net, x, y)
    return sheet

def generate(board, selected=None):
    design, interfaces = load_contracts(); board_info = design["boards"][board]
    names = [item["name"] for item in board_info["sheets"]]
    if selected:
        unknown = set(selected) - set(names)
        if unknown: raise SystemExit("unknown sheets: " + ", ".join(sorted(unknown)))
        names = selected
    if board == "circle-ppg":
        pins = next(item["pins"] for item in interfaces["connectors"] if item["name"] == "PPG_HEAD")
        if pins != EXPECTED_PPG_PINS: raise SystemExit("PPG cable pin order mismatch")
    out = ROOT / "hardware" / board / "legacy"; out.mkdir(parents=True, exist_ok=True)
    parts = [part for part in design["parts"] if part.get("board", "circle-main") == board]
    cache_name = "circle-ppg-cache.lib" if board == "circle-ppg" else "circle-cache.lib"
    (out / cache_name).write_text(cache_text(parts), encoding="utf-8", newline="\n")
    title_by_name = {item["name"]: item["title"] for item in board_info["sheets"]}
    for name in names:
        sheet_parts = [part for part in parts if part["sheet"] == name]
        children = [item["name"] for item in board_info["sheets"] if item["name"] != "00_root"] if name == "00_root" else ()
        (out / f"{name}.sch").write_text(make_sheet(name, title_by_name[name], sheet_parts, children).emit(), encoding="utf-8", newline="\n")
    if board == "circle-main": print(f"generated {len(names)} mainboard sheets" + (" and 1 symbol library" if len(names) == 3 else ""))
    else: print(f"generated {len(names)} PPG sheet and 1 symbol library")

def main():
    parser = ArgumentParser(); parser.add_argument("--board", default="circle-main", choices=("circle-main", "circle-ppg")); parser.add_argument("--sheets")
    args = parser.parse_args(); generate(args.board, args.sheets.split(",") if args.sheets else None)
if __name__ == "__main__": main()
