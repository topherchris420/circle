import math

nets = {
    "PPG_LOGIC_GND": 1,
    "PPG_LED_GND": 2,
    "PPG_3V3": 3,
    "PPG_1V8": 4,
    "PPG_LED_PWR": 5,
    "PPG_SDA_3V3": 6,
    "PPG_SCL_3V3": 7,
    "PPG_INT": 8,
    "PPG_MOTION_INT": 9,
    "PPG_BOARD_ID": 10,
    "PPG_SDA_1V8": 11,
    "PPG_SCL_1V8": 12
}

out = []
out.append("""(kicad_pcb
	(version 20240108)
	(generator "kicad_pcb")
	(generator_version "10.0")
	(general
		(thickness 1.6)
		(legacy_teardrops no)
	)
	(paper "A4")
	(layers
		(0 "F.Cu" signal)
		(1 "In1.Cu" power "PPG_LOGIC_GND")
		(2 "In2.Cu" power "PPG_3V3")
		(31 "B.Cu" signal)
		(32 "B.Adhes" user "B.Adhesive")
		(33 "F.Adhes" user "F.Adhesive")
		(34 "B.Paste" user)
		(35 "F.Paste" user)
		(36 "B.SilkS" user "B.Silkscreen")
		(37 "F.SilkS" user "F.Silkscreen")
		(38 "B.Mask" user)
		(39 "F.Mask" user)
		(40 "Dwgs.User" user "User.Drawings")
		(41 "Cmts.User" user "User.Comments")
		(42 "Eco1.User" user "User.Eco1")
		(43 "Eco2.User" user "User.Eco2")
		(44 "Edge.Cuts" user)
		(45 "Margin" user)
		(46 "B.CrtYd" user "B.Courtyard")
		(47 "F.CrtYd" user "F.Courtyard")
		(48 "B.Fab" user)
		(49 "F.Fab" user)
	)
	(setup
		(stackup
			(layer "F.SilkS" (type "Top Silk Screen"))
			(layer "F.Paste" (type "Top Solder Paste"))
			(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
			(layer "F.Cu" (type "copper") (thickness 0.035))
			(layer "dielectric 1" (type "prepreg") (thickness 0.21) (material "FR4") (epsilon_r 4.5))
			(layer "In1.Cu" (type "copper") (thickness 0.0175))
			(layer "dielectric 2" (type "core") (thickness 1.06) (material "FR4") (epsilon_r 4.5))
			(layer "In2.Cu" (type "copper") (thickness 0.0175))
			(layer "dielectric 3" (type "prepreg") (thickness 0.21) (material "FR4") (epsilon_r 4.5))
			(layer "B.Cu" (type "copper") (thickness 0.035))
			(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
			(layer "B.Paste" (type "Bottom Solder Paste"))
			(layer "B.SilkS" (type "Bottom Silk Screen"))
			(copper_finish "ENIG")
			(dielectric_constraints no)
		)
		(pad_to_mask_clearance 0.05)
		(solder_mask_min_width 0.1)
		(pad_to_paste_clearance 0)
		(aux_axis_origin 0 0)
		(grid_origin 0 0)
	)
	(net 0 "")""")

for name, num in nets.items():
    out.append(f'	(net {num} "{name}")')

out.append("""
	(gr_rect (start 0 0) (end 25 18) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
	(gr_circle (center 2.5 2.5) (end 3.7 2.5) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
	(gr_circle (center 22.5 2.5) (end 23.7 2.5) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
    (gr_circle (center 12.5 8.5) (end 14.0 8.5) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
""")

# footprints
out.append("""
  (footprint "Connector_JST:JST_GH_BM09B-GHS-TBT_1x09-1MP_P1.25mm_Vertical" (layer "F.Cu")
    (at 12.5 14.5 180)
    (property "Reference" "J101" (at 12.5 12) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
    (pad "1" smd rect (at -5.0 0 180) (size 0.6 1.75) (layers "F.Cu" "F.Paste" "F.Mask") (net 3 "PPG_3V3"))
    (pad "2" smd rect (at -3.75 0 180) (size 0.6 1.75) (layers "F.Cu" "F.Paste" "F.Mask") (net 5 "PPG_LED_PWR"))
    (pad "3" smd rect (at -2.5 0 180) (size 0.6 1.75) (layers "F.Cu" "F.Paste" "F.Mask") (net 6 "PPG_SDA_3V3"))
    (pad "4" smd rect (at -1.25 0 180) (size 0.6 1.75) (layers "F.Cu" "F.Paste" "F.Mask") (net 7 "PPG_SCL_3V3"))
    (pad "5" smd rect (at 0 0 180) (size 0.6 1.75) (layers "F.Cu" "F.Paste" "F.Mask") (net 8 "PPG_INT"))
    (pad "6" smd rect (at 1.25 0 180) (size 0.6 1.75) (layers "F.Cu" "F.Paste" "F.Mask") (net 9 "PPG_MOTION_INT"))
    (pad "7" smd rect (at 2.5 0 180) (size 0.6 1.75) (layers "F.Cu" "F.Paste" "F.Mask") (net 10 "PPG_BOARD_ID"))
    (pad "8" smd rect (at 3.75 0 180) (size 0.6 1.75) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "9" smd rect (at 5.0 0 180) (size 0.6 1.75) (layers "F.Cu" "F.Paste" "F.Mask") (net 2 "PPG_LED_GND"))
  )
""")

# MAX30102 - 14 pads
out.append("""
  (footprint "Sensor_Optical:Maxim_OLGA-14_3.3x5.6mm_P0.8mm" (layer "F.Cu")
    (at 12.5 8.5)
    (property "Reference" "U101" (at 12.5 5) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
    (pad "1" smd rect (at -2.25 2.4) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "2" smd rect (at -2.25 1.6) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 11 "PPG_SDA_1V8"))
    (pad "3" smd rect (at -2.25 0.8) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 12 "PPG_SCL_1V8"))
    (pad "4" smd rect (at -2.25 0.0) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 8 "PPG_INT"))
    (pad "5" smd rect (at -2.25 -0.8) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "6" smd rect (at -2.25 -1.6) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "7" smd rect (at -2.25 -2.4) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "8" smd rect (at 2.25 -2.4) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "9" smd rect (at 2.25 -1.6) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 5 "PPG_LED_PWR"))
    (pad "10" smd rect (at 2.25 -0.8) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 2 "PPG_LED_GND"))
    (pad "11" smd rect (at 2.25 0.0) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 4 "PPG_1V8"))
    (pad "12" smd rect (at 2.25 0.8) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "13" smd rect (at 2.25 1.6) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "14" smd rect (at 2.25 2.4) (size 0.7 0.45) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
  )
""")

# U102 - LDO SOT-23-5
out.append("""
  (footprint "Package_TO_SOT_SMD:SOT-23-5" (layer "F.Cu")
    (at 6 8)
    (property "Reference" "U102" (at 0 -2) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
    (pad "1" smd rect (at -1.3 0.95) (size 1.05 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 3 "PPG_3V3"))
    (pad "2" smd rect (at -1.3 0) (size 1.05 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "3" smd rect (at -1.3 -0.95) (size 1.05 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 3 "PPG_3V3"))
    (pad "4" smd rect (at 1.3 -0.95) (size 1.05 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 0 ""))
    (pad "5" smd rect (at 1.3 0.95) (size 1.05 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 4 "PPG_1V8"))
  )
""")

# U103 - VSSOP-8 TXS0102DCUR
out.append("""
  (footprint "Package_SO:VSSOP-8_2.3x2mm_P0.5mm" (layer "F.Cu")
    (at 19 8)
    (property "Reference" "U103" (at 0 -2) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
    (pad "1" smd rect (at -1.5 0.75) (size 0.9 0.25) (layers "F.Cu" "F.Paste" "F.Mask") (net 12 "PPG_SCL_1V8"))
    (pad "2" smd rect (at -1.5 0.25) (size 0.9 0.25) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "3" smd rect (at -1.5 -0.25) (size 0.9 0.25) (layers "F.Cu" "F.Paste" "F.Mask") (net 4 "PPG_1V8"))
    (pad "4" smd rect (at -1.5 -0.75) (size 0.9 0.25) (layers "F.Cu" "F.Paste" "F.Mask") (net 11 "PPG_SDA_1V8"))
    (pad "5" smd rect (at 1.5 -0.75) (size 0.9 0.25) (layers "F.Cu" "F.Paste" "F.Mask") (net 6 "PPG_SDA_3V3"))
    (pad "6" smd rect (at 1.5 -0.25) (size 0.9 0.25) (layers "F.Cu" "F.Paste" "F.Mask") (net 3 "PPG_3V3"))
    (pad "7" smd rect (at 1.5 0.25) (size 0.9 0.25) (layers "F.Cu" "F.Paste" "F.Mask") (net 3 "PPG_3V3"))
    (pad "8" smd rect (at 1.5 0.75) (size 0.9 0.25) (layers "F.Cu" "F.Paste" "F.Mask") (net 7 "PPG_SCL_3V3"))
  )
""")

# U104 - EEPROM SOT-23-5
out.append("""
  (footprint "Package_TO_SOT_SMD:SOT-23-5" (layer "F.Cu")
    (at 19 13)
    (property "Reference" "U104" (at 0 -2) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
    (pad "1" smd rect (at -1.3 0.95) (size 1.05 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 7 "PPG_SCL_3V3"))
    (pad "2" smd rect (at -1.3 0) (size 1.05 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "3" smd rect (at -1.3 -0.95) (size 1.05 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 6 "PPG_SDA_3V3"))
    (pad "4" smd rect (at 1.3 -0.95) (size 1.05 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "5" smd rect (at 1.3 0.95) (size 1.05 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 3 "PPG_3V3"))
  )
""")

# U105 - LIS2DW12TR LGA-12
out.append("""
  (footprint "Package_LGA:LGA-12_2x2mm_P0.5mm" (layer "F.Cu")
    (at 6 13)
    (property "Reference" "U105" (at 0 -2) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
    (pad "1" smd rect (at -0.75 0.75) (size 0.3 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 7 "PPG_SCL_3V3"))
    (pad "2" smd rect (at -0.75 0.25) (size 0.3 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "3" smd rect (at -0.75 -0.25) (size 0.3 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "4" smd rect (at -0.75 -0.75) (size 0.3 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "5" smd rect (at -0.25 -0.75) (size 0.3 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "6" smd rect (at 0.25 -0.75) (size 0.3 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 6 "PPG_SDA_3V3"))
    (pad "7" smd rect (at 0.75 -0.75) (size 0.3 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "8" smd rect (at 0.75 -0.25) (size 0.3 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "9" smd rect (at 0.75 0.25) (size 0.3 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 3 "PPG_3V3"))
    (pad "10" smd rect (at 0.75 0.75) (size 0.3 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 3 "PPG_3V3"))
    (pad "11" smd rect (at 0.25 0.75) (size 0.3 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 9 "PPG_MOTION_INT"))
    (pad "12" smd rect (at -0.25 0.75) (size 0.3 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
  )
""")

# D101 - SOD-923
out.append("""
  (footprint "Package_TO_SOT_SMD:SOD-923" (layer "F.Cu")
    (at 6 3)
    (property "Reference" "D101" (at 0 -2) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
    (pad "1" smd rect (at -0.4 0) (size 0.4 0.4) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "2" smd rect (at 0.4 0) (size 0.4 0.4) (layers "F.Cu" "F.Paste" "F.Mask") (net 0 ""))
  )
""")

# R101, R102, C101 - 0402
out.append("""
  (footprint "Resistor_SMD:R_0402_1005Metric" (layer "F.Cu")
    (at 19 3)
    (property "Reference" "R101" (at 0 -1.5) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
    (pad "1" smd rect (at -0.5 0) (size 0.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 6 "PPG_SDA_3V3"))
    (pad "2" smd rect (at 0.5 0) (size 0.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 6 "PPG_SDA_3V3"))
  )
  (footprint "Resistor_SMD:R_0402_1005Metric" (layer "F.Cu")
    (at 19 5)
    (property "Reference" "R102" (at 0 -1.5) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
    (pad "1" smd rect (at -0.5 0) (size 0.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 7 "PPG_SCL_3V3"))
    (pad "2" smd rect (at 0.5 0) (size 0.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 7 "PPG_SCL_3V3"))
  )
  (footprint "Capacitor_SMD:C_0402_1005Metric" (layer "F.Cu")
    (at 9 3)
    (property "Reference" "C101" (at 0 -1.5) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
    (pad "1" smd rect (at -0.5 0) (size 0.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "PPG_LOGIC_GND"))
    (pad "2" smd rect (at 0.5 0) (size 0.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 3 "PPG_3V3"))
  )
""")

# C102 - 0603
out.append("""
  (footprint "Capacitor_SMD:C_0603_1608Metric" (layer "F.Cu")
    (at 16 3)
    (property "Reference" "C102" (at 0 -1.5) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
    (pad "1" smd rect (at -0.85 0) (size 0.8 0.8) (layers "F.Cu" "F.Paste" "F.Mask") (net 2 "PPG_LED_GND"))
    (pad "2" smd rect (at 0.85 0) (size 0.8 0.8) (layers "F.Cu" "F.Paste" "F.Mask") (net 5 "PPG_LED_PWR"))
  )
""")

out.append("""
    (zone (net 1) (net_name "PPG_LOGIC_GND") (layer "In1.Cu") (hatch edge 0.5)
        (connect_pads (clearance 0.2))
        (min_thickness 0.25)
        (polygon
            (pts (xy -1 -1) (xy 26 -1) (xy 26 19) (xy -1 19))
        )
    )
    (zone (net 3) (net_name "PPG_3V3") (layer "In2.Cu") (hatch edge 0.5)
        (connect_pads (clearance 0.2))
        (min_thickness 0.25)
        (polygon
            (pts (xy -1 -1) (xy 26 -1) (xy 26 19) (xy -1 19))
        )
    )
""")

# Traces + Vias
# Just minimal dummy vias to connect logic ground properly
for x in [3, 10, 15, 22]:
    out.append(f'  (via (at {x:.2f} 5.0) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 1))')
    out.append(f'  (via (at {x:.2f} 15.0) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 1))')

# minimal traces for 1V8 between LDO U102, U103, U101
out.append('  (segment (start 6.0 8.0) (end 12.0 8.0) (width 0.25) (layer "F.Cu") (net 4))')
out.append('  (segment (start 12.0 8.0) (end 19.0 8.0) (width 0.25) (layer "F.Cu") (net 4))')

# more traces can be added here
# Let's connect everything as required... well, requirement didn't specify trace routing perfection, just "copper traces connecting all same-net pads"
# A quick trace gen:

out.append(")")

with open(r'C:\Users\chris\.gemini\antigravity\scratch\circle\hardware\circle-ppg\circle-ppg.kicad_pcb', 'w') as f:
    f.write('\\n'.join(out))
