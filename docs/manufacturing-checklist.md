# CIRCLE Rev B Manufacturing & DFM Checklist

> **ENGINEERING REVIEW ONLY — NOT FOR CLINICAL OR HUMAN CONNECTION**

This document specifies the Design for Manufacturing (DFM), Design for Assembly (DFA), PCB fabrication stackup, SMT assembly parameters, panelization rules, and quality control procedures for CIRCLE Rev B.

---

## 1. PCB Fabrication Specifications (JLCPCB / Eurocircuits 4-Layer Standard)

| Parameter | Specification | Tolerance / Constraint |
|---|---|---|
| **Layer Count** | 4 Copper Layers | Standard JLC04161H-7628 / Isola 370HR |
| **Finished Thickness** | $1.60\text{ mm} \pm 10\%$ | Standard FR4 High-TG ($T_g \ge 150^\circ\text{C}$) |
| **Outer Copper Weight** | 1.0 oz ($35\text{ }\mu\text{m}$) finished | Top and Bottom signal layers |
| **Inner Copper Weight** | 0.5 oz ($17.5\text{ }\mu\text{m}$) base | Ground (L2) and Power (L3) planes |
| **Surface Finish** | ENIG (Electroless Nickel Immersion Gold) | Required for fine-pitch QFN/LGA (ICM-42688, MAX30102) |
| **Minimum Trace / Space**| $0.127\text{ mm} / 0.127\text{ mm}$ ($5\text{ mil} / 5\text{ mil}$) | Standard high-yield tooling |
| **Minimum Via Drill / Pad**| $0.30\text{ mm} / 0.60\text{ mm}$ ($12\text{ mil} / 24\text{ mil}$) | Standard mechanical drilling |
| **Solder Mask** | Matte Black or Dark Blue LPI | High contrast for silkscreen readability |
| **Silkscreen** | White Epoxy Legend | Minimum text height $1.0\text{ mm}$, line width $0.15\text{ mm}$ |
| **Impedance Control** | $90\text{ }\Omega \pm 10\%$ Differential (USB D+/D-) | $w = 0.25\text{ mm}, s = 0.15\text{ mm}$ on Layer 1 over L2 GND |
| **Isolation Cutout Slot** | $8.0\text{ mm} \pm 0.1\text{ mm}$ routed air slot | Spanning full board width under ISOW7742 |

---

## 2. Component Placement & Assembly Rules (DFA)

1. **Fiducials**:
   - Three optical fiducials ($1.0\text{ mm}$ round copper pad with $2.0\text{ mm}$ solder mask opening) placed on diagonal board corners on both Top and Bottom SMT sides.
   - Local micro-fiducials ($0.5\text{ mm}$) placed adjacent to fine-pitch LGA sensor U20 (ICM-42688-P) and U101 (MAX30102).
2. **QFN / LGA Thermal Pad Soldering**:
   - BQ24074 (U2) and TPS63070 (U3) center exposed thermal pads require cross-pattern solder paste stencil apertures ($60\%-70\%$ paste coverage) and arrayed thermal vias ($4\times 0.3\text{ mm}$) to prevent component lifting/floating during reflow.
3. **Keepout & Clearance Rules**:
   - ESP32-S3 PCB antenna keepout: $15.0\text{ mm} \times 15.0\text{ mm}$ area free of all copper, traces, planes, battery mounting, or enclosure screws.
   - Isolation barrier keepout: $\ge 8.0\text{ mm}$ physical clearance zone where no copper, silkscreen, or testpoints may enter.
   - Connector clearances: Minimum $3.0\text{ mm}$ clearance around J1 (USB-C), J2 (Battery), J10 (EDA), J30/J31 (BNCs) for mechanical mating access.
4. **Polarity & Pin-1 Identifiers**:
   - All ICs, diodes, polarized capacitors, and connectors feature high-visibility pin-1 silkscreen dots and chamfered footprint outlines.

---

## 3. SMT Stencil & Solder Reflow Profile

- **Stencil Thickness**: $0.120\text{ mm}$ ($4.7\text{ mil}$) laser-cut stainless steel with electropolishing.
- **Solder Paste**: Lead-free SAC305 (Sn96.5 / Ag3.0 / Cu0.5) Type 4 fine-pitch solder paste.
- **Reflow Profile Parameters**:
  - Preheat / Soak: $150^\circ\text{C}$ to $180^\circ\text{C}$ for $60 - 90\text{ seconds}$.
  - Time Above Liquidus ($217^\circ\text{C}$): $45 - 75\text{ seconds}$.
  - Peak Temperature: $240^\circ\text{C} - 245^\circ\text{C}$ ($< 250^\circ\text{C}$ max).
  - Cooling Ramp Rate: $< 3^\circ\text{C/second}$ to prevent thermal shock to ceramic MLCCs.

---

## 4. Post-Assembly Quality & Test Checklist

- [ ] **Automated Optical Inspection (AOI)**: Verify all 0402/0603 passives, IC alignments, and pin-1 orientations.
- [ ] **X-Ray Inspection (AXI)**: Verify voiding $< 15\%$ on BQ24074, TPS63070, and ICM-42688 thermal/ground pads.
- [ ] **Bed-of-Nails / Pogo-Pin Test Fixture**:
  - Check power rail resistances to ground before applying voltage.
  - Apply 3.7V power; measure all testpoints (TP1 through TP16) against nominal tolerances.
  - Trigger automated self-test firmware to verify SPI, I2C, SDMMC, and interlock deassertion times.
- [ ] **Dielectric Withstand (Hipot) Gate**: 100% production test applying 1000 VDC across isolation barrier for 2s (leakage $< 10\text{ nA}$).
- [ ] **Serialization**: Scan and log AT24CS02 factory-programmed 128-bit UID into quality tracking database.
