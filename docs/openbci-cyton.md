# OpenBCI Cyton: a real biosignal board at CIRCLE's boundary

> **ENGINEERING REVIEW ONLY** — The bridge has not been run against a physical Cyton in this repository. It was built from the pinned firmware and datasheet sources below and exercised against protocol vectors and a simulated board that follows that firmware. Nothing here establishes anything about a person, and the Cyton is not a medical device.

The [OpenBCI Cyton](https://github.com/OpenBCI/OpenBCI_Cyton_Library) is an open 8-channel biopotential board (16 with the Daisy module) built around the Texas Instruments ADS1299, a 24-bit ADC designed for EEG, ECG, and EMG. It streams over a radio dongle at 250 samples per second, carries a LIS3DH accelerometer, and can read three analog or five digital pins.

CIRCLE's bridge brings it through the same ingestion boundary as the twin, the Oura ring, and recorded bundles. It also does something none of them can: **it turns the board into its own electronic phantom.** The ADS1299 can connect every channel to an internal square wave or short its inputs. With known truth from the datasheet and firmware, real bytes can be judged as they cross the radio, the dongle, USB, and CIRCLE's framing, before anyone wears an electrode.

```bash
python tools/openbci_cyton.py self-test                  # no board, no pyserial: vectors and simulated sessions
python tools/openbci_cyton.py simulate --mode phantom --output outputs/cyton-phantom-simulated
pip install pyserial
python tools/openbci_cyton.py ports
python tools/openbci_cyton.py probe --port /dev/ttyUSB0
python tools/openbci_cyton.py phantom --port /dev/ttyUSB0 --output outputs/cyton-phantom
python tools/openbci_cyton.py record --port /dev/ttyUSB0 --wearer-consents --battery-powered --seconds 300 --ecg-channel 2
```

---

## What the board sends

Every fact the bridge depends on is pinned in [`models/openbci_cyton/protocol.py`](../models/openbci_cyton/protocol.py), with the source function or definition it mirrors:

| Source | Revision |
|---|---|
| [OpenBCI_Cyton_Library](https://github.com/OpenBCI/OpenBCI_Cyton_Library) (firmware, MIT) | commit `24e1c42`, library 3.1.5 |
| [OpenBCI_Radios](https://github.com/OpenBCI/OpenBCI_Radios) (board and dongle radios, MIT) | commit `389a831` |
| TI ADS1299 datasheet | SBAS499C, revised January 2017 |

| Element | What the sources say |
|---|---|
| Packet | 33 bytes: `0xA0`, an 8-bit sample counter, eight 24-bit big-endian two's-complement codes, six aux bytes, and `0xC0` OR the packet type. The board sends `'A'` (0x41); the dongle writes `0xA0` (`bufferStreamFlush`). |
| Loss | The board radio forwards only complete 33-byte packets. A packet lost on the UART or in the air is absent, and the counter is the only record of it. |
| Counter | It restarts at 0 whenever the ADC starts: on `b`, and on every setting changed while streaming, because the firmware stops and restarts the ADC to apply it. |
| Scale | `4.5 V / gain / (2^23 − 1)` per count; at gain 24, 0.02235 µV. |
| Accelerometer | LIS3DH at ±4 g, high resolution, 25 Hz. After each accelerometer packet the words are zeroed, so a reading appears only in the packet after the LIS3DH has a new one. An all-zero triple means no new reading. |
| Board modes | `default` (accelerometer), `analog` (A5, A6, A7 as 10-bit reads), `digital` (D11, D12, D13, D17, D18), `marker` (a host-sent character in AUX1, once). |
| Daisy | Odd counters carry channels 1–8 and even counters carry channels 9–16. Each is the average of two consecutive ADC samples, so each half is a 125 Hz stream. |
| Text | Replies and dongle messages end in `$$$`. Most replies are suppressed while streaming. |
| Oscillator | Internal, 2.048 MHz, ±0.5 % at 25 °C and ±2.5 % over −40 to 85 °C. "250 SPS" can be 1.25 SPS off. |

Two firmware quirks are recorded rather than hidden: the soft-reset banner prints `Firmware: v3.1.2` while `V` answers `v3.1.5`; and marker mode stores the character's code (`` `5 `` gives 53), not the digit the changelog describes.

The first Daisy half after every ADC start averages a value left from before the start (`updateDaisyData` runs after `firstDataPacket` is cleared). The bridge keeps it as sent and records a `STALE_AVERAGE_AT_ADC_START` fault.

---

## How a session keeps CIRCLE's evidence rules

**Configured, then verified.** Setup stops any stream left running, asks the dongle whether the board answers (`0xF0 0x07`), soft-resets and parses the banner (ADS1299 and LIS3DH identities, the Daisy), reads the firmware version, turns time stamps off, and sets the board mode. It then configures the channels and **reads the ADC's registers back** over `?`. Every stream descriptor's gain is the gain read back, not the one requested. A board that acknowledges a command without applying it is caught here and recorded as `BOARD_CONFIGURATION_MISMATCH`.

**Only commands whose effect is recorded.** [`command_refusal`](../models/openbci_cyton/protocol.py) refuses SD-card logging (data CIRCLE would not hold or hash), the WiFi shield, debug and BLE board modes, sample rates above 250 SPS, and dongle radio settings. Every command sent is listed in the session header.

**Through the boundary.** Every read goes through the framer and `CytonStreams`, then every piece goes through `pump()` into an `Ingestor` with host-receipt availability, with a `LinkMonitor` recording `LINK:*` transitions.

### Losses are exact, or marked as unknown

| Cause | What is declared |
|---|---|
| `CYTON_COUNTER_DISCONTINUITY` | The exact samples that never arrived, by unwrapped sample index |
| `CYTON_SEGMENT_START_LOST` | The counter restarts at 0 on `b`; the first packets never arrived |
| …`full counter wrap(s) resolved by the sample clock` | A silence longer than 256 samples, counted exactly (below) |
| `COUNTER_AMBIGUOUS` | One marked discontinuity: more than one count, or none, fits the receipt time |
| `SEGMENT_TAIL_LOST` | The link was silent before the stop; samples taken then were never delivered |
| `LINK_LOST` | The serial port failed |
| `ACCEL_LOSS_UNKNOWN` | Packets were lost; the accelerometer readings they may have carried cannot be counted |

An 8-bit counter cannot tell a loss of 3 samples from a loss of 259. The sample clock can. The ADC's oscillator is within ±2.5 % of nominal, so the next packet's receipt time, compared with the epoch's clock line, admits exactly one count of lost samples. That holds as long as no packet waits more than 0.5 s between its data-ready and the host's read. When more than one count fits, or none does, the bridge does not choose. It marks one discontinuity of unknown size and starts a new epoch.

Bytes that are neither a checked packet nor text are counted and recorded as `BYTES_DISCARDED`. After a discard, a candidate packet is accepted only when the next byte starts another packet or its counter continues the last accepted packet's. A stray `0xA0` followed 32 bytes later by a `0xCX` byte is otherwise one chance in sixteen.

### Timing: the device's clock, mapped honestly

The Cyton has a real sample clock, which neither the Oura ring nor the Muse gadget has. It is only as accurate as its internal oscillator, though, and the radio and the USB serial converter add variable delay. CIRCLE keeps both facts:

- **Exact intervals come from the ADC.** Every row carries `epoch`, `sample_index` (unwrapped), and the raw `counter`. Beat-to-beat intervals, test-signal periods, and loss counts are computed in ADC samples.
- **Sample times are on the host's monotonic clock.** They come from a minimum-delay clock line, [`models/acquisition/clock.py`](../models/acquisition/clock.py): the line under every receipt that minimizes total delay (Moon, Skelly and Towsley, IEEE INFOCOM 1999). It never places a sample after it was received, and its slope measures the oscillator against the host. A `CLOCK_MAPPING` record per epoch gives the rate in ppm and the bounds.
- **Receipts bound only one side.** A constant transport latency is invisible to receipts. In `marker` board mode the host sends a marker every half-second and records when. A marker cannot be in a sample taken before it was sent, less one sample of slack for the firmware's loop. These probes bound the mapping from below; receipts bound it from above. Without probes, the record says `UPPER_BOUND_ONLY_LATENCY_FLOOR_UNKNOWN`.

Scored against simulated truth (offsets from −5,000 to +25,000 ppm, a 16 ms USB latency timer, radio jitter, 1 % loss), the online line recovers the rate to within 20 ppm. The probe bounds always contain the true mapping and were 7–9 ms wide in those runs. The bridge never assumes a latency distribution.

On Linux, the bridge reads the FTDI latency timer (`/sys/bus/usb-serial/devices/ttyUSB*/latency_timer`) and notes when it exceeds the 1 ms OpenBCI recommends. Receipts remain honest upper bounds either way.

---

## The board as its own phantom

```bash
python tools/openbci_cyton.py phantom --port /dev/ttyUSB0
```

The phantom runs six segments in `marker` mode. Its accelerometer is off. Every channel is on the shorted inputs, the 1× and 2× slow and fast square waves, or the DC test level. **Nothing from a body can reach a channel in these conditions**, so the session is `NOT_HUMAN_DATA` by construction, and no person is needed.

| Check | Judged against | Status |
|---|---|---|
| `TEST_SIGNAL_PERIOD_EXACT` | The square wave and the ADC share fCLK, so its period is exactly 256 (slow) or 128 (fast) ADC samples *whatever the oscillator's error*. Every period, on every channel, is judged to 0.05 sample, across declared losses. | judged |
| `TEST_SIGNAL_TWO_LEVELS` | Away from edges, the spread on each level is under 1 % of the step | judged |
| `TEST_SIGNAL_CHANNEL_AGREEMENT` | One signal feeds every channel: each step is within the datasheet's 2 % test-signal accuracy of the median | judged |
| `TEST_SIGNAL_2X_OVER_1X` | The 2× setting is twice the 1×, to within 4 % | judged |
| `TEST_SIGNAL_AMPLITUDE`, `TEST_SIGNAL_DC` | The datasheet states the amplitude two incompatible ways: `k·VREF/2400` (1.875 mV at 4.5 V) in its register table, ±1 and ±2 mV in its electrical table | **reported, not judged** |
| `SHORTED_INPUT_NOISE` | Under 5× the datasheet's 0.14 µVrms (gain 24, 250 SPS). The factor of five is CIRCLE's margin, not TI's. | judged |
| `SAMPLE_CLOCK_RATE` | Within ±2.5 % of 250 SPS against the host clock; whether it is within ±0.5 % is noted | judged |
| `CLOCK_PROBES_CONSISTENT` | One line satisfies every receipt and every marker probe | judged |
| `REGISTERS_READ_BACK` | The ADC holds the configuration the scaling assumes | judged |
| `FRAMING_ALL_LOSSES_DECLARED` | Every missing sample was declared by the bridge with its cause | judged |

The verdict is `FAIL` if any check fails, `INCOMPLETE` if one could not be evaluated, and `PASS` only when every check that can be judged was judged and passed.

The period check tests the whole chain at once: ADC, PIC32, both radios, dongle, USB, framing, sign extension, and loss accounting. A packet the counter counts but the ADC never took shifts every later edge by one sample, so the check fails. The self-test includes that negative control.

One measurement the bridge cannot make for you: whether the test signal swings ±A or 0 to A. The first phantom run on real hardware settles it, and the session records the measured step.

---

## Recording people

```bash
python tools/openbci_cyton.py record --port /dev/ttyUSB0 --wearer-consents --battery-powered --seconds 300 --ecg-channel 2
```

- **Consent and power are attested, or nothing runs.** `--wearer-consents`: the person wearing the electrodes knows this records their biopotentials and motion, and agrees. `--battery-powered`: the Cyton runs on its battery and reaches the computer only through the radio dongle. Electrodes on a person and a wired connection to a mains-powered computer must never coexist.
- **Human data stays here.** Sessions are flagged `HUMAN_DATA`, written owner-only (0700/0600), and contain no board serial number or MAC address. The radio link itself is unauthenticated and unencrypted; anyone in range on the same channel could listen.
- **What is derived.** Per-channel quality (railed fraction, 1–40 Hz RMS, line-noise share) is computed over the longest contiguous run. With `--ecg-channel`, a Pan-Tompkins-style detector finds R peaks. Intervals come from the ADC's sample index, times come from the clock line, and RMSSD windows are `MODEL_INFERRED` with exact source ranges. A peak within 50 ms of a lost sample is dropped, and an interval never spans a hole longer than 40 ms. Against the simulator's known beats, sensitivity is above 0.9, positive predictivity above 0.98, and RMSSD within 15 % of the truth. That says nothing about real electrodes or people, and RMSSD here is not a clinical HRV measurement.
- **The closed loop does not run on it.** The ADS1299 measures biopotentials. CIRCLE's controller needs skin conductance, MAX30102 red/IR counts, a gyroscope, and a lab sync stream in its input contract's form. The session records the refusal as `FAULT` records (`CLOSED_LOOP_NOT_ELIGIBLE`). Nothing is imputed, and nothing is actuated.

`analog` mode records whatever is attached to A5–A7 (a pulse sensor or a skin-conductance module, for example) as raw 10-bit codes. CIRCLE does not know what those sensors are and claims nothing about them. `digital` mode can capture a laboratory TTL on D17.

---

## The simulated Cyton

[`models/openbci_cyton/simulator.py`](../models/openbci_cyton/simulator.py) is the bridge's test bench. It follows the pinned firmware's command processor, reply texts, multi-character commands, stream-safe restarts, packet types, accelerometer zero fill, board modes, Daisy averaging, and the stale first Daisy half. It runs the ADC, the test signal, and the LIS3DH on separate clocks, and models radio latency, loss, and dropouts, 62-byte USB transfers with a latency timer, stalls, corrupted and stray bytes, and boards that are off or ignore commands. Every rendered value comes from a stated truth: an EEG-like background, an ECG with known R peaks, a pulse sensor with a 210 ms transit time, and a 1 Hz TTL. That truth is used only for scoring.

`python tools/openbci_cyton.py self-test` runs four sessions through the real bridge:

1. **A damaged phantom that must pass.** It includes 0.2 % radio loss, a 1.6 s mid-segment dropout spanning more than one counter wrap, a dropout at a segment's tail, a corrupted packet, stray bytes, and a USB stall. Every loss a later packet reveals must be declared exactly, and the tail must be marked.
2. **A phantom with an invented packet that must fail**, and only on the period check.
3. **An ECG through a lossy link**, scored against known beats, with the sample clock measured to within 25 ppm of the simulated oscillator.
4. **A Daisy session.** Its halves must alternate, and the stale first average must be flagged.

---

## What this does not show

- No physical Cyton, dongle, or electrode has been connected in this repository. Real radios, USB stacks, and boards fail in ways the simulator does not model.
- A phantom PASS validates the Cyton's own signal chain and CIRCLE's ingestion of it. It is not evidence about CIRCLE Rev B, which has its own phantoms on the [physical evidence ladder](physical-evidence-ladder.md).
- Clock bounds assume the stated latency bound and one sample of firmware slack for markers. Sample times are estimates; intervals in ADC samples are exact only up to the oscillator's rate, which the mapping measures.
- Nothing here changes what CIRCLE claims about physiology. The Cyton cannot drive the closed loop, and no intervention effect is asserted.
