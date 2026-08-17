import re
from collections import defaultdict

with open(r'C:\Users\chris\.gemini\antigravity\scratch\circle\hardware\circle-ppg\circle-ppg.kicad_pcb', 'r') as f:
    pcb = f.read()

# find all pads: (pad "..." smd rect (at X Y) ... (net NUM "NAME"))
pad_re = re.compile(r'\(pad\s+"[^"]+"\s+smd\s+rect\s+\(at\s+([-0-9.]+)\s+([-0-9.]+)(?:\s+[-0-9.]+)?\).*?\(net\s+(\d+)\s+"([^"]+)"\)\)')

# we also need the footprint's (at X Y) to offset the pad
fp_re = re.compile(r'\(footprint\s+"[^"]+"\s+\(layer\s+"F\.Cu"\)\s+\(at\s+([-0-9.]+)\s+([-0-9.]+)(?:\s+[-0-9.]+)?\)')

nets_pads = defaultdict(list)

# Split into footprints
parts = pcb.split('(footprint')
for part in parts[1:]:
    lines = part.split('\n')
    m_fp = fp_re.search('(footprint' + part)
    if m_fp:
        fx, fy = float(m_fp.group(1)), float(m_fp.group(2))
        for m_pad in pad_re.finditer(part):
            px, py, net_num, net_name = float(m_pad.group(1)), float(m_pad.group(2)), int(m_pad.group(3)), m_pad.group(4)
            if net_num > 0:
                nets_pads[net_num].append((fx+px, fy+py))

segments = []
for net_num, pads in nets_pads.items():
    if len(pads) > 1:
        # connect all pads to the first one
        x0, y0 = pads[0]
        for xi, yi in pads[1:]:
            segments.append(f'  (segment (start {x0:.2f} {y0:.2f}) (end {xi:.2f} {yi:.2f}) (width 0.25) (layer "F.Cu") (net {net_num}))')

# insert before last parenthesis
pcb = pcb.rsplit(')', 1)[0] + '\n'.join(segments) + '\n)'

with open(r'C:\Users\chris\.gemini\antigravity\scratch\circle\hardware\circle-ppg\circle-ppg.kicad_pcb', 'w') as f:
    f.write(pcb)
