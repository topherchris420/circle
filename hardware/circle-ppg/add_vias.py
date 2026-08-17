import re

with open(r'C:\Users\chris\.gemini\antigravity\scratch\circle\hardware\circle-ppg\circle-ppg.kicad_pcb', 'r') as f:
    pcb = f.read()

pad_re = re.compile(r'\(pad\s+"[^"]+"\s+smd\s+rect\s+\(at\s+([-0-9.]+)\s+([-0-9.]+)(?:\s+[-0-9.]+)?\).*?\(net\s+1\s+"PPG_LOGIC_GND"\)\)')
fp_re = re.compile(r'\(footprint\s+"[^"]+"\s+\(layer\s+"F\.Cu"\)\s+\(at\s+([-0-9.]+)\s+([-0-9.]+)(?:\s+[-0-9.]+)?\)')

vias = []
parts = pcb.split('(footprint')
for part in parts[1:]:
    m_fp = fp_re.search('(footprint' + part)
    if m_fp:
        fx, fy = float(m_fp.group(1)), float(m_fp.group(2))
        for m_pad in pad_re.finditer(part):
            px, py = float(m_pad.group(1)), float(m_pad.group(2))
            vias.append(f'  (via (at {fx+px:.2f} {fy+py:.2f}) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 1))')

pcb = pcb.rsplit(')', 1)[0] + '\n' + '\n'.join(vias) + '\n)'
with open(r'C:\Users\chris\.gemini\antigravity\scratch\circle\hardware\circle-ppg\circle-ppg.kicad_pcb', 'w') as f:
    f.write(pcb)
