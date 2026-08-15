# Preliminary Power Budget

> **ENGINEERING REVIEW ONLY ? NOT FOR FABRICATION OR HUMAN CONNECTION.**

| Rail/load | Nominal | Peak | Source | Confidence | Margin | Measurement hook |
|---|---:|---:|---|---|---:|---|
| VBAT/system | 350 mA | 1200 mA | preliminary aggregate | Low | 35% | RSH1/JP1 |
| 3V3 digital/radio | 180 mA | 700 mA | module estimate | Low | 40% | RSH2/JP2 |
| EDA analog | 12 mA | 25 mA | part estimates | Low | 50% | RSH3/JP3 |
| PPG 1V8 logic | 8 mA | 20 mA | sensor estimate | Low | 50% | logic hook |
| PPG LED | 20 mA | 150 mA | pulsed estimate | Low | 50% | RSH4/JP4 |
| SD | 40 mA | 300 mA | card envelope | Medium | 50% | RSH5/JP5 |
| Haptic | 80 mA | 350 mA | actuator estimate | Low | 50% | RSH6/JP6 |
| Isolated SYNC | 35 mA | 120 mA | isolator estimate | Low | 40% | isolation hook |

Charger current, battery capacity, magnetics, thermal copper, and regulator closure remain release gates; these are estimates, not measurements.
