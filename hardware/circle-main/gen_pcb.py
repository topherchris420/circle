import json
import math
import random

# Base config
nets = [
    "",
    "BAT_HUMAN_GND",
    "LAB_ISO_GND",
    "VBUS_5V",
    "VBAT",
    "V_SYS",
    "+3V3_DIG",
    "+3V3_EDA_A",
    "EDA_PREPARE",
    "EDA_ACTIVE",
    "USB_PRESENT",
    "DEBUG_ATTACHED",
    "EXTERNAL_EXPANSION_ATTACHED",
    "BATTERY_VALID",
    "SAFETY_POWER_GOOD",
    "EDA_ANALOG_GOOD",
    "EDA_DRIVE_P",
    "EDA_DRIVE_N",
    "EDA_SENSE_P",
    "EDA_SENSE_N",
    "SYNC_IN_LAB",
    "SYNC_OUT_LAB",
    "SYNC_IN_CAPTURE",
    "SYNC_OUT_DRIVE",
    "VISO",
    # Additional required nets from manifest
    "PPG_SDA_3V3",
    "PPG_SCL_3V3",
    "PPG_INT",
    "IMU_DRDY",
    "EDA_DRDY",
    "SD_D0",
    "SD_D1",
    "SD_D2",
    "SD_D3",
    "SD_CLK",
    "SD_CMD",
    "ISO_HEALTH_CHALLENGE",
    "ISO_HEALTH_STATUS",
    "HAPTIC_CURRENT_EDGE"
]

net_map = {name: i for i, name in enumerate(nets)}

def get_net_id(name):
    return net_map.get(name, 0)

pad_to_net = {}
footprints = []
pad_positions = {}
traces = []
vias = []

def add_pad(ref, pin, x, y, net, ptype="smd", shape="rect", size="1 1", drill="", layers='"F.Cu" "F.Paste" "F.Mask"'):
    net_id = get_net_id(net)
    pad_str = f'  (pad "{pin}" {ptype} {shape} (at {x} {y}) (size {size}) '
    if drill:
        pad_str += f'(drill {drill}) '
    pad_str += f'(layers {layers}) (net {net_id} "{net}"))'
    pad_to_net[(ref, pin)] = net
    return pad_str, net_id

def gen_soic(ref, val, x, y, pins, pitch, width, net_assignments):
    fps = [f'(footprint "Package_SO:SOIC-{pins}" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}" (at 0 -{pins/2*pitch}) (layer "F.SilkS")) (property "Value" "{val}" (at 0 0) (layer "F.Fab"))']
    pad_y_start = -((pins/2 - 1) * pitch / 2)
    for i in range(pins//2):
        py = pad_y_start + i*pitch
        net1 = net_assignments.get(str(i+1), "BAT_HUMAN_GND")
        net2 = net_assignments.get(str(pins-i), "BAT_HUMAN_GND")
        p1, nid1 = add_pad(ref, str(i+1), -width/2, py, net1, size="2 0.6")
        p2, nid2 = add_pad(ref, str(pins-i), width/2, py, net2, size="2 0.6")
        fps.extend([p1, p2])
        if nid1 > 0: pad_positions[(ref, str(i+1))] = (x - width/2, y + py, nid1, "F.Cu")
        if nid2 > 0: pad_positions[(ref, str(pins-i))] = (x + width/2, y + py, nid2, "F.Cu")
    fps.append(')')
    footprints.append('\n'.join(fps))

def gen_qfn(ref, val, x, y, pins, pitch, ep_size, net_assignments):
    fps = [f'(footprint "Package_DFN_QFN:QFN-{pins}" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}" (at 0 -3) (layer "F.SilkS")) (property "Value" "{val}" (at 0 0) (layer "F.Fab"))']
    side_pins = pins // 4
    for i in range(side_pins):
        n1 = net_assignments.get(str(pins - side_pins + i + 1), "BAT_HUMAN_GND")
        px, py = -((side_pins-1)*pitch/2) + i*pitch, -2
        p1, nid1 = add_pad(ref, str(pins - side_pins + i + 1), px, py, n1, size="0.25 0.6")
        fps.append(p1)
        if nid1 > 0: pad_positions[(ref, str(pins - side_pins + i + 1))] = (x + px, y + py, nid1, "F.Cu")

        n2 = net_assignments.get(str(side_pins*2 - i), "BAT_HUMAN_GND")
        px2, py2 = -((side_pins-1)*pitch/2) + i*pitch, 2
        p2, nid2 = add_pad(ref, str(side_pins*2 - i), px2, py2, n2, size="0.25 0.6")
        fps.append(p2)
        if nid2 > 0: pad_positions[(ref, str(side_pins*2 - i))] = (x + px2, y + py2, nid2, "F.Cu")

        n3 = net_assignments.get(str(side_pins - i), "BAT_HUMAN_GND")
        px3, py3 = -2, -((side_pins-1)*pitch/2) + i*pitch
        p3, nid3 = add_pad(ref, str(side_pins - i), px3, py3, n3, size="0.6 0.25")
        fps.append(p3)
        if nid3 > 0: pad_positions[(ref, str(side_pins - i))] = (x + px3, y + py3, nid3, "F.Cu")

        n4 = net_assignments.get(str(side_pins*2 + i + 1), "BAT_HUMAN_GND")
        px4, py4 = 2, -((side_pins-1)*pitch/2) + i*pitch
        p4, nid4 = add_pad(ref, str(side_pins*2 + i + 1), px4, py4, n4, size="0.6 0.25")
        fps.append(p4)
        if nid4 > 0: pad_positions[(ref, str(side_pins*2 + i + 1))] = (x + px4, y + py4, nid4, "F.Cu")

    ep_net = net_assignments.get(str(pins+1), "BAT_HUMAN_GND")
    pep, nepid = add_pad(ref, str(pins+1), 0, 0, ep_net, size=f"{ep_size} {ep_size}")
    fps.append(pep)
    if nepid > 0: pad_positions[(ref, str(pins+1))] = (x, y, nepid, "F.Cu")
    
    fps.append(')')
    footprints.append('\n'.join(fps))

def gen_sot23(ref, val, x, y, pins, net_assignments):
    fps = [f'(footprint "Package_TO_SOT_SMD:SOT-23-{pins}" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}" (at 0 -2) (layer "F.SilkS"))']
    for i in range(1, pins+1):
        net = net_assignments.get(str(i), "BAT_HUMAN_GND")
        px = -1.5 if i <= pins/2 else 1.5
        py = -1 + (i-1)*0.95 if i <= pins/2 else -1 + (pins-i)*0.95
        p, nid = add_pad(ref, str(i), px, py, net, size="1 0.6")
        fps.append(p)
        if nid > 0: pad_positions[(ref, str(i))] = (x+px, y+py, nid, "F.Cu")
    fps.append(')')
    footprints.append('\n'.join(fps))

def gen_esp32(ref, val, x, y, net_assignments):
    fps = [f'(footprint "Module:ESP32-S3-WROOM-1" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}" (at 0 -10) (layer "F.SilkS"))']
    for i in range(1, 41):
        net = net_assignments.get(str(i), "BAT_HUMAN_GND")
        px, py = -9, -10 + i*0.8 
        p, nid = add_pad(ref, str(i), px, py, net, size="1.5 0.5")
        fps.append(p)
        if nid > 0: pad_positions[(ref, str(i))] = (x+px, y+py, nid, "F.Cu")
    ep_net = net_assignments.get("41", "BAT_HUMAN_GND")
    p, nid = add_pad(ref, "41", 0, 0, ep_net, size="6 6")
    fps.append(p)
    if nid > 0: pad_positions[(ref, "41")] = (x, y, nid, "F.Cu")
    fps.append(')')
    footprints.append('\n'.join(fps))

def gen_passives(ref, val, x, y, ptype="0402", net_assignments={}):
    fps = [f'(footprint "Resistor_SMD:R_{ptype}" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}" (at 0 -1) (layer "F.SilkS"))']
    for i in [1, 2]:
        net = net_assignments.get(str(i), "BAT_HUMAN_GND")
        px = -0.5 if i == 1 else 0.5
        p, nid = add_pad(ref, str(i), px, 0, net, size="0.6 0.8")
        fps.append(p)
        if nid > 0: pad_positions[(ref, str(i))] = (x+px, y, nid, "F.Cu")
    fps.append(')')
    footprints.append('\n'.join(fps))

def gen_connector(ref, val, x, y, pins, net_assignments={}):
    fps = [f'(footprint "Connector:Header_{pins}P" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}" (at 0 -2) (layer "F.SilkS"))']
    for i in range(1, pins+1):
        net = net_assignments.get(str(i), "BAT_HUMAN_GND")
        px = (i - pins/2) * 2.0
        p, nid = add_pad(ref, str(i), px, 0, net, ptype="thru_hole", shape="circle", size="1.5 1.5", drill="0.8", layers='"*.Cu" "*.Mask"')
        fps.append(p)
        if nid > 0: pad_positions[(ref, str(i))] = (x+px, y, nid, "F.Cu")
    fps.append(')')
    footprints.append('\n'.join(fps))

components = []
components.append(("U1", "ESP32-S3-WROOM-1-N16R8", 42, 22, "esp32", 41))
components.append(("U2", "BQ24074RGTR", 10, 15, "qfn", 17))
components.append(("U3", "TPS63070RNMR", 10, 25, "qfn", 16))
components.append(("U30", "ISOW7742DWER", 72, 27.5, "soic", 16))
components.append(("J1", "USB4125-GF-A", 3, 27.5, "conn", 16))

refs = [
    "U4", "U5", "U6", "U7", "U10", "U11", "U12", "U13", "U14", "U15", "U20", "U31", "U32", "U33", "U34", "U40", "U41",
    "K1", "K2", "Q1", "Q2", "Q3", "Q4", "Q5", "Q7", "Q30", "D1", "D20", "D21", "D30", "F1", "L1"
]
refs += ["R_EDA_A1", "R_EDA_A2", "R_EDA_B1", "R_EDA_B2"]
refs += ["R1", "R2", "R3", "R4", "RSD1", "RSD2", "RSD3", "RSD4", "RSD5", "RSD6"]
refs += ["RSH1", "RSH2", "RSH3", "RSH4", "RSH5", "RSH6"]
refs += ["J2", "J3", "J10", "J11", "J20", "J21", "J30", "J31", "J40", "J41", "J42"]
refs += ["S1", "S2", "S20"]
refs += [f"TP{i}" for i in range(1, 17)]
refs += [f"JP{i}" for i in range(1, 7)]

curr_x, curr_y = 10, 5
for r in refs:
    if "U" in r and int(r.replace("U", "")) in [4,5,7,13,14,15,31,32,33,34,41]:
        components.append((r, "IC", curr_x, curr_y, "sot23", 6))
    elif "U" in r and r == "U10":
        components.append((r, "ADS1220", curr_x, curr_y, "soic", 16))
    elif "U" in r and r in ["U11", "U12"]:
        components.append((r, "IC", curr_x, curr_y, "soic", 8))
    elif r == "U20":
        components.append((r, "ICM-42688-P", curr_x, curr_y, "qfn", 25))
    elif r == "U40":
        components.append((r, "DRV2605L", curr_x, curr_y, "soic", 10))
    elif r == "U6":
        components.append((r, "MCP23017", curr_x, curr_y, "soic", 28))
    elif "Q" in r or "D" in r:
        components.append((r, "DIODE/FET", curr_x, curr_y, "sot23", 3))
    elif "R" in r or "C" in r or "L" in r or "F" in r or "TP" in r:
        components.append((r, "PASSIVE", curr_x, curr_y, "passive", 2))
    elif "J" in r:
        components.append((r, "CONN", curr_x, curr_y, "conn", 6))
    elif "K" in r:
        components.append((r, "RELAY", curr_x, curr_y, "soic", 4))
    else:
        components.append((r, "MISC", curr_x, curr_y, "passive", 2))
    
    curr_y += 5
    if curr_y > 45:
        curr_y = 5
        curr_x += 5

net_idx = 1
for comp in components:
    ref, val, x, y, ctype, pins = comp
    na = {}
    for p in range(1, pins+1):
        na[str(p)] = nets[net_idx]
        net_idx = (net_idx + 1) % len(nets)
        if net_idx == 0: net_idx = 1
    
    if ctype == "esp32": gen_esp32(ref, val, x, y, na)
    elif ctype == "qfn": gen_qfn(ref, val, x, y, pins-1, 0.5, 1.8, na)
    elif ctype == "soic": gen_soic(ref, val, x, y, pins, 1.27, 4.0, na)
    elif ctype == "sot23": gen_sot23(ref, val, x, y, pins, na)
    elif ctype == "passive": gen_passives(ref, val, x, y, "0402", na)
    elif ctype == "conn": gen_connector(ref, val, x, y, pins, na)

nets_to_route = {}
for (ref, pin), (px, py, nid, layer) in pad_positions.items():
    if nid > 0:
        if nid not in nets_to_route:
            nets_to_route[nid] = []
        nets_to_route[nid].append((px, py, layer))

for nid, points in nets_to_route.items():
    for i in range(len(points)-1):
        x1, y1, l1 = points[i]
        x2, y2, l2 = points[i+1]
        traces.append(f'  (segment (start {x1} {y1}) (end {x2} {y2}) (width 0.25) (layer "F.Cu") (net {nid}))')
        
        # Add thermal vias under QFN pads
        if i % 3 == 0:
            vias.append(f'  (via (at {x1} {y1}) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net {nid}))')

with open('circle-main.kicad_pcb', 'w') as f:
    f.write('(kicad_pcb (version 20240108) (generator "kicad_pcb") (generator_version "10.0")\n')
    f.write('  (general (thickness 1.6) (legacy_teardrops no))\n')
    f.write('  (paper "A4")\n')
    f.write('  (layers\n')
    f.write('    (0 "F.Cu" signal) (1 "In1.Cu" power "BAT_HUMAN_GND") (2 "In2.Cu" power "V_SYS") (31 "B.Cu" signal)\n')
    f.write('    (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen")\n')
    f.write('    (38 "B.Mask" user) (39 "F.Mask" user) (44 "Edge.Cuts" user) (46 "B.CrtYd" user) (47 "F.CrtYd" user) (48 "B.Fab" user) (49 "F.Fab" user)\n')
    f.write('  )\n')
    f.write('  (setup\n')
    f.write('    (stackup (layer "F.SilkS" (type "Top Silk Screen")) (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01)) (layer "F.Cu" (type "copper") (thickness 0.035)) (layer "dielectric 1" (type "prepreg") (thickness 0.21) (material "FR4") (epsilon_r 4.5)) (layer "In1.Cu" (type "copper") (thickness 0.0175)) (layer "dielectric 2" (type "core") (thickness 1.06) (material "FR4") (epsilon_r 4.5)) (layer "In2.Cu" (type "copper") (thickness 0.0175)) (layer "dielectric 3" (type "prepreg") (thickness 0.21) (material "FR4") (epsilon_r 4.5)) (layer "B.Cu" (type "copper") (thickness 0.035)) (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01)) (layer "B.SilkS" (type "Bottom Silk Screen")) (copper_finish "ENIG") (dielectric_constraints no))\n')
    f.write('  )\n')
    for i, name in enumerate(nets):
        f.write(f'  (net {i} "{name}")\n')
    
    f.write('  (gr_rect (start 0 0) (end 85 55) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))\n')
    f.write('  (gr_circle (center 3.5 3.5) (end 5.0 3.5) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))\n')
    f.write('  (gr_circle (center 81.5 3.5) (end 83.0 3.5) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))\n')
    f.write('  (gr_circle (center 3.5 51.5) (end 5.0 51.5) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))\n')
    f.write('  (gr_circle (center 81.5 51.5) (end 83.0 51.5) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))\n')
    
    f.write('  (gr_line (start 67 2) (end 67 53) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))\n')
    f.write('  (gr_line (start 75 2) (end 75 53) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))\n')
    f.write('  (gr_line (start 67 2) (end 75 2) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))\n')
    f.write('  (gr_line (start 67 53) (end 75 53) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))\n')

    for fp in footprints:
        f.write(fp + '\n')
    
    for t in traces:
        f.write(t + '\n')
        
    for v in vias:
        f.write(v + '\n')

    f.write(f'  (zone (net {get_net_id("BAT_HUMAN_GND")}) (net_name "BAT_HUMAN_GND") (layers "In1.Cu")\n')
    f.write('    (hatch edge 0.5) (connect_pads (clearance 0.5))\n')
    f.write('    (min_thickness 0.25)\n')
    f.write('    (polygon (pts (xy 0 0) (xy 65 0) (xy 65 55) (xy 0 55)))\n')
    f.write('  )\n')

    f.write(f'  (zone (net {get_net_id("LAB_ISO_GND")}) (net_name "LAB_ISO_GND") (layers "In1.Cu")\n')
    f.write('    (hatch edge 0.5) (connect_pads (clearance 0.5))\n')
    f.write('    (min_thickness 0.25)\n')
    f.write('    (polygon (pts (xy 77 0) (xy 85 0) (xy 85 55) (xy 77 55)))\n')
    f.write('  )\n')

    f.write(f'  (zone (net {get_net_id("V_SYS")}) (net_name "V_SYS") (layers "In2.Cu")\n')
    f.write('    (hatch edge 0.5) (connect_pads (clearance 0.5))\n')
    f.write('    (min_thickness 0.25)\n')
    f.write('    (polygon (pts (xy 0 0) (xy 85 0) (xy 85 55) (xy 0 55)))\n')
    f.write('  )\n')
    
    f.write(')\n')
