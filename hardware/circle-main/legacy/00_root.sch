EESchema Schematic File Version 4
LIBS:circle-cache
EELAYER 29 0
EELAYER END
$Descr A4 11693 8268
encoding utf-8
Sheet 1 1
Title "Hierarchy and safety domains"
Comment1 "ENGINEERING REVIEW ONLY - NOT FOR HUMAN CONNECTION"
$EndDescr
$Sheet
S 900 1100 1300 700
U 10000001
F0 "01_compute_usb" 50
F1 "01_compute_usb.sch" 50
$EndSheet
$Sheet
S 5700 1100 1300 700
U 10000002
F0 "02_power" 50
F1 "02_power.sch" 50
$EndSheet
$Sheet
S 900 2400 1300 700
U 10000003
F0 "03_eda_safety" 50
F1 "03_eda_safety.sch" 50
$EndSheet
$Sheet
S 5700 2400 1300 700
U 10000004
F0 "04_sensors" 50
F1 "04_sensors.sch" 50
$EndSheet
$Sheet
S 900 3700 1300 700
U 10000005
F0 "05_storage" 50
F1 "05_storage.sch" 50
$EndSheet
$Sheet
S 5700 3700 1300 700
U 10000006
F0 "06_sync_isolation" 50
F1 "06_sync_isolation.sch" 50
$EndSheet
$Sheet
S 900 5000 1300 700
U 10000007
F0 "07_feedback_expansion" 50
F1 "07_feedback_expansion.sch" 50
$EndSheet
$Sheet
S 5700 5000 1300 700
U 10000008
F0 "08_observability" 50
F1 "08_observability.sch" 50
$EndSheet
Text Label 700 5600 0    50   ~ 0
BAT_HUMAN
Text Label 700 5840 0    50   ~ 0
LAB_ISO
Text Label 700 6080 0    50   ~ 0
BAT_HUMAN_GND
Text Label 700 6320 0    50   ~ 0
LAB_ISO_GND
Text Notes 600 400 0    50   ~ 0
ENGINEERING REVIEW ONLY - NOT FOR HUMAN CONNECTION
Text Notes 700 6560 0    50   ~ 0
NO COPPER OR WIRE JOINS THE TWO GROUND DOMAINS
$EndSCHEMATC
