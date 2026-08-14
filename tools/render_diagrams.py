"""Render the two review diagrams deterministically with the Python standard library."""

from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "diagrams"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)

SYSTEM_NODES = [
    ("Human", 40, 110, "human"), ("CIRCLE", 210, 110, "device"),
    ("VitalSync", 380, 110, "software"), ("DRR", 550, 110, "software"),
    ("AdaptiveDecision", 720, 110, "model"), ("Feedback", 930, 110, "feedback"),
    ("Sensors", 40, 330, "sensor"), ("Capture", 210, 330, "device"),
    ("SRAM", 380, 330, "storage"), ("PSRAM", 550, 330, "storage"),
    ("microSD", 720, 330, "storage"), ("Record Assembly", 380, 470, "device"),
    ("Telemetry", 720, 470, "software"),
    ("Authoritative Device Monotonic Clock", 40, 590, "clock"),
    ("Raw + Timing + Sequence + Quality + Provenance Evidence", 600, 590, "evidence"),
]
SYSTEM_EDGES = [
    (0, 1, "sense"), (1, 2, "synchronize"), (2, 3, "model"),
    (3, 4, "decide"), (4, 5, "command"), (5, 0, "intervene"),
    (0, 1, "measure"), (6, 7, "samples"), (7, 8, "DMA"),
    (8, 9, "spill"), (9, 10, "async write"), (7, 11, "records"),
    (11, 12, "lower priority"), (13, 7, "timestamps"),
    (13, 5, "action time"), (13, 11, "metadata"), (11, 14, "preserve"),
]
SAFETY_NODES = [
    ("USB_PRESENT", 70, 210, "unsafe"), ("DEBUG_ATTACHED", 70, 310, "unsafe"),
    ("EXTERNAL_EXPANSION_ATTACHED", 70, 410, "unsafe"),
    ("BATTERY_VALID + SAFETY_POWER_GOOD", 70, 510, "good"),
    ("Hardware fail-off EDA gate", 380, 310, "gate"),
    ("EDA front end + normally-open switches", 590, 210, "eda"),
    ("Compute", 590, 360, "device"), ("Storage", 590, 480, "storage"),
    ("Haptic", 380, 530, "feedback"), ("ISOW7742", 790, 340, "barrier"),
    ("BNC SYNC IN conditioning", 940, 230, "lab"),
    ("BNC SYNC OUT open-drain", 940, 450, "lab"),
]
SAFETY_EDGES = [
    (0, 4, "disable"), (1, 4, "disable"), (2, 4, "disable"),
    (3, 4, "qualify"), (4, 5, "EDA_ACTIVE"), (10, 9, "isolated in"),
    (9, 6, "capture"), (6, 9, "drive"), (9, 11, "isolated out"),
]
COLORS = {
    "human": "#f3e8d1", "device": "#b9d8f2", "software": "#c9e6cf",
    "model": "#d7c6f2", "feedback": "#f2c2b8", "sensor": "#cfe8e8",
    "storage": "#d9dde3", "clock": "#ffe29a", "evidence": "#fff1bf",
    "unsafe": "#f3b0aa", "good": "#b9deb5", "gate": "#f4b860",
    "eda": "#e6c5d8", "barrier": "#f4b860", "lab": "#c9d7f0",
}


def svg_tag(name):
    return f"{{{NS}}}{name}"


def render(path, title, nodes, edges, domains=(), footer=None):
    root = ET.Element(svg_tag("svg"), {"viewBox": "0 0 1200 720", "role": "img", "aria-label": title})
    defs = ET.SubElement(root, svg_tag("defs"))
    marker = ET.SubElement(defs, svg_tag("marker"), {"id": "arrow", "viewBox": "0 0 10 10", "refX": "9", "refY": "5", "markerWidth": "7", "markerHeight": "7", "orient": "auto-start-reverse"})
    ET.SubElement(marker, svg_tag("path"), {"d": "M 0 0 L 10 5 L 0 10 z", "fill": "#30343b"})
    ET.SubElement(root, svg_tag("rect"), {"width": "1200", "height": "720", "fill": "#fbfaf6"})
    warning = ET.SubElement(root, svg_tag("text"), {"x": "600", "y": "34", "text-anchor": "middle", "font-family": "Arial, sans-serif", "font-size": "18", "font-weight": "bold", "fill": "#a32622"})
    warning.text = "ENGINEERING REVIEW ONLY — NOT FOR HUMAN CONNECTION"
    heading = ET.SubElement(root, svg_tag("text"), {"x": "600", "y": "70", "text-anchor": "middle", "font-family": "Arial, sans-serif", "font-size": "24", "font-weight": "bold", "fill": "#161b22"})
    heading.text = title
    for label, x, y, w, h, fill in domains:
        ET.SubElement(root, svg_tag("rect"), {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "rx": "18", "fill": fill, "fill-opacity": "0.25", "stroke": "#59636e", "stroke-width": "2"})
        text = ET.SubElement(root, svg_tag("text"), {"x": str(x + 18), "y": str(y + 28), "font-family": "Arial, sans-serif", "font-size": "17", "font-weight": "bold", "fill": "#252b31"})
        text.text = label
    centers = []
    for label, x, y, style in nodes:
        width = 150 if len(label) < 24 else 245
        height = 62
        centers.append((x + width / 2, y + height / 2))
    for source, target, label in edges:
        x1, y1 = centers[source]; x2, y2 = centers[target]
        ET.SubElement(root, svg_tag("line"), {"x1": str(x1), "y1": str(y1), "x2": str(x2), "y2": str(y2), "stroke": "#30343b", "stroke-width": "2", "marker-end": "url(#arrow)"})
        edge_text = ET.SubElement(root, svg_tag("text"), {"x": str((x1 + x2) / 2), "y": str((y1 + y2) / 2 - 6), "text-anchor": "middle", "font-family": "Arial, sans-serif", "font-size": "11", "fill": "#39424c"})
        edge_text.text = label
    for label, x, y, style in nodes:
        width = 150 if len(label) < 24 else 245
        ET.SubElement(root, svg_tag("rect"), {"x": str(x), "y": str(y), "width": str(width), "height": "62", "rx": "10", "fill": COLORS[style], "stroke": "#30343b", "stroke-width": "2"})
        text = ET.SubElement(root, svg_tag("text"), {"x": str(x + width / 2), "y": str(y + 36), "text-anchor": "middle", "font-family": "Arial, sans-serif", "font-size": "13", "font-weight": "bold", "fill": "#161b22"})
        text.text = label
    if footer:
        note = ET.SubElement(root, svg_tag("text"), {"x": "600", "y": "695", "text-anchor": "middle", "font-family": "Arial, sans-serif", "font-size": "13", "fill": "#7a231f"})
        note.text = footer
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True, short_empty_elements=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    render(OUT / "system-architecture.svg", "CIRCLE Rev A Closed-Loop Architecture", SYSTEM_NODES, SYSTEM_EDGES)
    render(
        OUT / "safety-boundaries.svg", "CIRCLE Rev A Human / Laboratory Safety Boundary",
        SAFETY_NODES, SAFETY_EDGES,
        domains=(("BAT_HUMAN", 35, 135, 720, 520, "#dcebdc"), ("LAB_ISO", 900, 135, 270, 520, "#dde5f5")),
        footer="Arbitrary grounded probes are a procedural hazard outside intended attachment detection.",
    )
    print("rendered 2 diagrams")


if __name__ == "__main__":
    main()
