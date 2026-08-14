"""Small deterministic KiCad legacy schematic emitter for review artifacts."""
from dataclasses import dataclass, field
import re

MAX_X, MAX_Y = 11693, 8268


def _coord(*values):
    if any(not 0 <= value <= limit for value, limit in zip(values, (MAX_X, MAX_Y) * (len(values) // 2))):
        raise ValueError("coordinate outside A4 sheet")


@dataclass(frozen=True)
class Pin:
    name: str
    number: str
    electrical_type: str
    def __post_init__(self):
        if not self.number:
            raise ValueError("pin number is required")


@dataclass(frozen=True)
class ProjectSymbol:
    name: str
    pins: tuple[Pin, ...] | list[Pin]
    def emit(self):
        lines = [f"# {self.name}", f"DEF {self.name} U 0 40 Y Y 1 F N", 'F0 "U" 0 350 50 H V C CNN', f'F1 "{self.name}" 0 -350 50 H V C CNN', "DRAW", "S -350 300 350 -300 0 1 10 f"]
        for index, pin in enumerate(self.pins):
            y = 200 - index * 100
            lines.append(f"X {pin.name} {pin.number} -550 {y} 200 R 40 40 1 1 {pin.electrical_type}")
        return "\n".join(lines + ["ENDDRAW", "ENDDEF", ""]) 


@dataclass
class Component:
    ref: str
    symbol: str
    x: int
    y: int
    value: str
    def __post_init__(self):
        _coord(self.x, self.y)
        if not self.value:
            raise ValueError("component value is required")


@dataclass
class LegacySheet:
    title: str
    components: list[Component] = field(default_factory=list)
    wires: list[tuple[int, int, int, int]] = field(default_factory=list)
    labels: list[tuple[str, int, int]] = field(default_factory=list)
    notes: list[tuple[str, int, int]] = field(default_factory=list)
    children: list[tuple[str, str, int, int]] = field(default_factory=list)
    def add(self, component):
        if any(existing.ref == component.ref for existing in self.components):
            raise ValueError(f"duplicate reference: {component.ref}")
        self.components.append(component); return self
    def wire(self, x1, y1, x2, y2):
        _coord(x1, y1, x2, y2); self.wires.append((x1, y1, x2, y2)); return self
    def label(self, name, x, y):
        _coord(x, y)
        if re.search(r"\s", name): raise ValueError("labels cannot contain whitespace")
        self.labels.append((name, x, y)); return self
    def note(self, text, x, y):
        _coord(x, y); self.notes.append((text, x, y)); return self
    def child_sheet(self, title, filename, x, y):
        _coord(x, y); self.children.append((title, filename, x, y)); return self
    def emit(self):
        lines = ["EESchema Schematic File Version 4", "LIBS:circle-cache", "EELAYER 29 0", "EELAYER END", "$Descr A4 11693 8268", "encoding utf-8", "Sheet 1 1", f'Title "{self.title}"', 'Comment1 "ENGINEERING REVIEW ONLY - NOT FOR HUMAN CONNECTION"', "$EndDescr"]
        for index, component in enumerate(self.components, 1):
            lines += ["$Comp", f"L {component.symbol} {component.ref}", f"U 1 1 {index:08X}", f"P {component.x} {component.y}", f'F 0 "{component.ref}" H {component.x + 100} {component.y + 100} 50  0000 C CNN', f'F 1 "{component.value}" H {component.x + 100} {component.y - 100} 50  0000 C CNN', "\t1    0    0    -1", "$EndComp"]
        for index, (title, filename, x, y) in enumerate(self.children, 1):
            lines += ["$Sheet", f"S {x} {y} 1300 700", f"U {0x10000000 + index:08X}", f'F0 "{title}" 50', f'F1 "{filename}" 50', "$EndSheet"]
        for x1, y1, x2, y2 in self.wires: lines += ["Wire Wire Line", f"\t{x1} {y1} {x2} {y2}"]
        for name, x, y in self.labels: lines.append(f"Text Label {x} {y} 0    50   ~ 0\n{name}")
        for text, x, y in self.notes: lines.append(f"Text Notes {x} {y} 0    50   ~ 0\n{text}")
        return "\n".join(lines + ["$EndSCHEMATC", ""])
