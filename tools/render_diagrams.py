"""Render review diagrams deterministically with the Python standard library."""

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

RESONANCE_ARCH_NODES = [
    ("CIRCLE BAT_HUMAN Sensors", 40, 180, "sensor"),
    ("ESP32-S3 Compute & Log", 250, 180, "device"),
    ("ISOW7742 (5 kVrms)", 460, 180, "barrier"),
    ("Isolated SYNC (BNC)", 660, 180, "lab"),
    ("Resonance Controller", 870, 180, "model"),
    ("5-Channel DDS Drive", 870, 330, "gate"),
    ("Power & Energy Monitor", 660, 330, "evidence"),
    ("Resonant Chamber (Phi)", 870, 480, "device"),
    ("Subject / Phantom", 40, 480, "human"),
    ("Closed-Loop Optimization", 460, 480, "software"),
]
RESONANCE_ARCH_EDGES = [
    (0, 1, "samples"), (1, 2, "hardware timestamp"), (2, 3, "isolated pulse"),
    (3, 4, "trigger sync"), (4, 5, "target freqs"), (5, 6, "P_in measurement"),
    (5, 7, "multi-ch drive"), (7, 8, "radiated field"), (8, 0, "sense response"),
    (1, 9, "provenance log"), (9, 4, "next adaptive cfg"),
]

RESONANCE_SAFETY_NODES = [
    ("EDA Electrodes (Human)", 50, 180, "eda"),
    ("PPG Optical Head (Human)", 50, 280, "sensor"),
    ("circle-main BAT_HUMAN", 50, 400, "device"),
    ("8.0mm NO-COPPER CUTOUT", 370, 290, "unsafe"),
    ("ISOW7742 (5.0 kVrms)", 370, 400, "barrier"),
    ("BNC Isolated SYNC", 650, 400, "lab"),
    ("Resonance Controller", 880, 250, "model"),
    ("5-Channel Amplifiers", 880, 380, "gate"),
    ("External Resonator Cavity", 880, 510, "device"),
]
RESONANCE_SAFETY_EDGES = [
    (0, 2, "direct connection"), (1, 2, "direct connection"),
    (2, 3, "PHYSICALLY SEPARATED"), (2, 4, "ISOW7742 only"),
    (4, 5, "isolated sync"), (5, 6, "coax sync"),
    (6, 7, "drive signals"), (7, 8, "high power"),
]

RESONANCE_GEOM_NODES = [
    ("Outer Sphere: D = 300 mm [R_outer]", 100, 180, "device"),
    ("Middle Sphere: D/phi = 185.4 mm [R_middle]", 100, 300, "software"),
    ("Inner Sphere: D/phi^2 = 114.6 mm [R_inner]", 100, 420, "sensor"),
    ("Dual Tetrahedron (Merkaba) [R_core]", 600, 240, "model"),
    ("Upward Pointing Tetrahedron [R_core_up]", 600, 380, "gate"),
    ("Downward Pointing Tetrahedron [R_core_down]", 600, 500, "eda"),
    ("Power Accounting: P_out <= P_in", 350, 600, "evidence"),
]
RESONANCE_GEOM_EDGES = [
    (0, 1, "phi = 1.618034"), (1, 2, "phi = 1.618034"),
    (2, 3, "central enclosure"), (3, 4, "upper element"),
    (3, 5, "inverted element"), (0, 6, "conservation verified"),
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
        width = 160 if len(label) < 26 else 280
        height = 62
        centers.append((x + width / 2, y + height / 2))
    for source, target, label in edges:
        x1, y1 = centers[source]; x2, y2 = centers[target]
        ET.SubElement(root, svg_tag("line"), {"x1": str(x1), "y1": str(y1), "x2": str(x2), "y2": str(y2), "stroke": "#30343b", "stroke-width": "2", "marker-end": "url(#arrow)"})
        edge_text = ET.SubElement(root, svg_tag("text"), {"x": str((x1 + x2) / 2), "y": str((y1 + y2) / 2 - 6), "text-anchor": "middle", "font-family": "Arial, sans-serif", "font-size": "11", "fill": "#39424c"})
        edge_text.text = label
    for label, x, y, style in nodes:
        width = 160 if len(label) < 26 else 280
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
    render(
        OUT / "resonance-architecture.svg", "CIRCLE Resonance Closed-Loop System Architecture",
        RESONANCE_ARCH_NODES, RESONANCE_ARCH_EDGES,
        domains=(("CIRCLE_MEASUREMENT", 25, 120, 600, 540, "#dcebdc"), ("RESONANCE_EXPERIMENT", 640, 120, 530, 540, "#dde5f5")),
        footer="Resonance chamber driven strictly through isolated LAB_ISO sync interface.",
    )
    render(
        OUT / "resonance-safety-boundary.svg", "CIRCLE Resonance Electrical Safety & Isolation Boundary",
        RESONANCE_SAFETY_NODES, RESONANCE_SAFETY_EDGES,
        domains=(("BAT_HUMAN (SENSING ONLY)", 25, 120, 310, 540, "#dcebdc"), ("ISOLATION GAP (8mm)", 345, 120, 270, 540, "#fbe4e2"), ("LAB_ISO & RESONANCE CHAMBER", 625, 120, 550, 540, "#dde5f5")),
        footer="Zero conductive connection permitted between resonance drive and BAT_HUMAN domain.",
    )
    render(
        OUT / "resonance-geometry.svg", "CIRCLE Resonance Parametric Nested Phi-Cavity Geometry",
        RESONANCE_GEOM_NODES, RESONANCE_GEOM_EDGES,
        domains=(("NESTED SPHERICAL CAVITIES", 40, 120, 480, 540, "#dcebdc"), ("POLYHEDRAL CENTRAL CORE", 540, 120, 620, 540, "#dde5f5")),
        footer="Parametric nested golden-ratio spheres (Phi = 1.618034) with central dual-tetrahedral core.",
    )
    print("rendered 5 diagrams")


if __name__ == "__main__":
    main()
