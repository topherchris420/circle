"""OpenBCI Cyton bridge: an 8- or 16-channel ADS1299 board, through CIRCLE's ingestion boundary.

  self-test   protocol vectors, then simulated sessions through the same bridge,
              boundary, and exporter: a damaged phantom that must pass, a
              phantom with a firmware fault that must fail, an ECG recording
              scored against known beats, and a Daisy session. No board, no
              dongle, no pyserial.
  simulate    write a simulated phantom or recording to inspect
  ports       list serial ports; the dongle is an FTDI FT231X (needs pyserial)
  probe       identify a board: dongle link, banner, firmware, registers
  phantom     the board as its own electronic phantom: every channel on the
              ADS1299's internal test signals or shorted inputs, accelerometer
              off, judged against the datasheet; no person needed
  record      stream electrodes into a contract-valid session (needs
              --wearer-consents and --battery-powered)

What the board sends and how it is read is pinned in
models/openbci_cyton/protocol.py (OpenBCI_Cyton_Library 24e1c42, v3.1.5;
OpenBCI_Radios 389a831; TI ADS1299 datasheet SBAS499C). Every piece goes
through models.acquisition.live.pump() into an Ingestor with host-receipt
availability; every loss is an exact GAP from the 8-bit sample counter, or one
marked discontinuity whose size is stated to be unknown. Sample times come
from a minimum-delay clock line fitted to the receipts (models/acquisition/
clock.py), because the ADS1299's internal oscillator is only within +-0.5 %
(+-2.5 % over temperature) of 250 SPS; exact intervals come from the ADC's own
sample index, kept in every row.

The Cyton cannot drive CIRCLE's closed loop (no EDA, PPG counts, gyroscope, or
sync stream in the input contract's form); each session records why.

Safety. Attach electrodes to a person only with the Cyton on its battery and
reaching the computer only through the radio dongle. This is not a medical
device, and nothing here makes it one.

  python tools/openbci_cyton.py self-test
  python tools/openbci_cyton.py simulate --mode phantom --output outputs/cyton-phantom-simulated
  pip install pyserial
  python tools/openbci_cyton.py ports
  python tools/openbci_cyton.py probe --port /dev/ttyUSB0
  python tools/openbci_cyton.py phantom --port /dev/ttyUSB0 --output outputs/cyton-phantom
  python tools/openbci_cyton.py record --port /dev/ttyUSB0 --wearer-consents --battery-powered --seconds 300 --ecg-channel 2
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.openbci_cyton import analysis as an  # noqa: E402
from models.openbci_cyton import bridge as b  # noqa: E402
from models.openbci_cyton import protocol as p  # noqa: E402
from models.openbci_cyton.framing import Framer, decode_packet, encode_packet  # noqa: E402
from models.openbci_cyton.simulator import Scenario, SimulatedCyton, SimulatedPort, VirtualClock  # noqa: E402
from models.openbci_cyton.streams import DAISY_STREAM, EXG_STREAM  # noqa: E402
from models.session_records import load_session  # noqa: E402

FT231X_VID_PID = (0x0403, 0x6015)

# A packet written out by hand from the firmware's layout (sendChannelDataSerial) and the dongle's framing
# (bufferStreamFlush), independent of encode_packet: counter 5; channels +full scale, -full scale, -1, 0, 1,
# 0x123456, -0x123456, 42; accelerometer words 16, -16, 8000 (1 g at 2 mg / 16 per count); stop byte 0xC0.
VECTOR_PACKET = "a0057fffff800000ffffff000000000001123456edcbaa00002a0010fff01f40c0"
VECTOR_CHANNELS = (8388607, -8388608, -1, 0, 1, 0x123456, -0x123456, 42)
BANNER = ("OpenBCI V3 8-16 channel\nOn Board ADS1299 Device ID: 0x3E\nOn Daisy ADS1299 Device ID: 0x3E\n"
          "LIS3DH Device ID: 0x33\nFirmware: v3.1.2\n$$$")


def check_protocol() -> list[str]:
    """Bytes and grammar against the pinned firmware."""
    problems = []
    packet = decode_packet(bytes.fromhex(VECTOR_PACKET))
    if (packet.counter, packet.channels, packet.accel(), packet.type_name) != (5, VECTOR_CHANNELS, (16, -16, 8000),
                                                                               "ACCEL"):
        problems.append(f"hand-written packet decoded as {packet}")
    if encode_packet(5, VECTOR_CHANNELS, bytes.fromhex("0010fff01f40")).hex() != VECTOR_PACKET:
        problems.append("encode_packet disagrees with the hand-written packet")
    if decode_packet(encode_packet(9, [0] * 8)).accel() is not None:
        problems.append("an all-zero accelerometer triple must read as 'no new reading'")
    for got, want in ((p.channel_settings(1), b"x1060110X"), (p.channel_settings(9, gain=12, input_type="SHORTED"),
                                                             b"xQ051110X"),
                      (p.lead_off(1, True, False), b"z110Z"), (p.board_mode("marker"), b"/4"),
                      (p.sample_rate(250), b"~6"), (p.marker(ord("A")), b"`A")):
        if got != want:
            problems.append(f"command {got!r} should be {want!r}")
    for refused in (b"A", b"j", b"{", b"/5", b"/1", b"~0", b"\xf0\x01", b"x10601"):
        if p.command_refusal(refused) is None:
            problems.append(f"{refused!r} should be refused")
    for allowed in (b"b", b"s", b"v", b"V", b"?", b"d", b"-", b"]", b"0", b"/4", b"~~", b"`A", p.DONGLE_SYS_UP,
                    p.channel_settings(16, power_down=True)):
        if p.command_refusal(allowed) is not None:
            problems.append(f"{allowed!r} should be allowed: {p.command_refusal(allowed)}")
    if abs(p.microvolts_per_count(24) - 0.0223517444553) > 1e-12:
        problems.append(f"gain-24 scale is {p.microvolts_per_count(24)} uV per count")
    if p.TEST_SIGNAL_PERIOD_SAMPLES != {"SLOW": 256, "FAST": 128}:
        problems.append(f"test-signal periods {p.TEST_SIGNAL_PERIOD_SAMPLES}")
    banner = p.parse_banner(BANNER)
    if banner is None or (banner.ads_id, banner.daisy, banner.lis3dh_id, banner.banner_firmware) != (0x3E, True, 0x33,
                                                                                                     "v3.1.2"):
        problems.append(f"banner parsed as {banner}")
    dump = "\nBoard ADS Registers\n" + p.register_dump_lines({"ADS_ID": 0x3E, "CONFIG1": 0x96, "CONFIG2": 0xD1,
                                                             "CH1SET": 0x68, "CH2SET": 0x55}) + "$$$"
    regs = p.parse_register_dump(dump).get("board")
    if regs is None or regs.data_rate_hz != 250 or regs.test_signal != {"internal": True, "amplitude_k": 1,
                                                                        "frequency": "FAST"} \
            or regs.channels()[0] != p.ChannelRegister(False, 24, "NORMAL", True) \
            or regs.channels()[1] != p.ChannelRegister(False, 12, "TESTSIG", False):
        problems.append(f"register dump parsed as {regs}")
    framer = Framer()
    stream = b"junk\x07" + encode_packet(1, [1] * 8) + encode_packet(2, [2] * 8)[:20] + encode_packet(3, [3] * 8) \
        + b"Success: done$$$" + encode_packet(4, [4] * 8)
    items = [framer.feed(stream[i:i + 5]) for i in range(0, len(stream), 5)]
    counters = [x.counter for group in items for x in group if hasattr(x, "counter")]
    if counters != [1, 3, 4]:
        problems.append(f"framer recovered counters {counters}, expected [1, 3, 4]")
    return problems


async def simulated(scenario: Scenario, plan: b.Plan, output: Path, session_id: str
                    ) -> tuple[b.Session, Any, dict[str, Any], dict[str, Any], SimulatedCyton]:
    clock = VirtualClock()
    board = SimulatedCyton(scenario)
    session, raw, report = await b.run(SimulatedPort(board, clock), clock, plan)
    results = b.analyze(raw, session.core, session)
    info = b.SessionInfo(session_id, "SIMULATED", False, "simulated Cyton" + (" + Daisy" if scenario.daisy else "")
                         + " (models/openbci_cyton/simulator.py)", session.now(),
                         details={"scenario": {k: v for k, v in vars(scenario).items()}})
    manifest = b.write_session(output, raw, session.core, session, info, results, report)
    return session, raw, results, manifest, board


# Host seconds from power-on; the phantom's segments start near 2.5, 11.2, 20.0, 28.7, 35.5, and 42.2 s.
DAMAGED_PHANTOM = Scenario(seed=11, drift_ppm=2400.0, radio_loss=0.002,
                           dropouts_s=((22.0, 23.6), (44.4, 45.6)),        # mid-segment (> one wrap), and a tail
                           corrupt_packets=(1500,), stray_bytes=((14.2, b"\x00\xff\xa0\x13\x80"),),
                           usb_stalls_s=((25.0, 25.3),))
ECG_SCENARIO = Scenario(seed=3, drift_ppm=-3200.0, radio_loss=0.002, railed_channel=5)


def truth_rmssd(beats_s: np.ndarray, t0_s: float, t1_s: float) -> float:
    inside = beats_s[(beats_s >= t0_s) & (beats_s <= t1_s)]
    rr = np.diff(inside) * 1e3
    return float(np.sqrt(np.mean(np.diff(rr) ** 2)))


async def self_test(output: Path) -> tuple[list[str], dict[str, Any]]:
    problems = [f"protocol: {x}" for x in check_protocol()]
    summary: dict[str, Any] = {}

    # 1. A damaged phantom: losses, a 1.6 s dropout (more than one counter wrap), a corrupted packet, stray bytes,
    #    and a USB stall. Every check must pass, and every loss must be declared exactly.
    session, raw, results, manifest, board = await simulated(DAMAGED_PHANTOM, b.phantom_plan(), output / "phantom",
                                                             "CYTON-SELF-TEST-PHANTOM")
    card = results["phantom"]
    summary["phantom"] = {"verdict": card["verdict"], "lost_declared": session.core.streams.lost_packets,
                          "lost_in_air": len(board.truth.lost_in_air), "gaps": len(raw.gaps)}
    if card["verdict"] != "PASS":
        problems.append(f"damaged phantom: {[c['id'] for c in card['checks'] if c['status'] == 'FAIL']} failed")
    corrupted = len(DAMAGED_PHANTOM.corrupt_packets)
    exg = raw.streams[EXG_STREAM]
    last_seen = {int(e): int(exg.columns["sample_index"][exg.columns["epoch"] == e].max())
                 for e in np.unique(exg.columns["epoch"])}
    revealed = [(seg, k) for seg, k in board.truth.lost_in_air if k < last_seen.get(seg, -1)]
    tails = {seg for seg, k in board.truth.lost_in_air if k > last_seen.get(seg, -1)}
    marked_tails = sum(1 for g in raw.gaps if g.stream_id == EXG_STREAM and g.cause.startswith("SEGMENT_TAIL_LOST"))
    summary["phantom"].update(revealed=len(revealed), tail_segments=len(tails), tails_marked=marked_tails)
    if session.core.streams.epochs != len(session.segments):
        problems.append(f"{session.core.streams.epochs} epochs for {len(session.segments)} segments: a loss went ambiguous")
    if session.core.streams.lost_packets != len(revealed) + corrupted:
        problems.append(f"declared {session.core.streams.lost_packets} lost packets exactly; the simulated air lost "
                        f"{len(revealed)} that a later packet revealed, and {corrupted} arrived corrupted")
    if marked_tails != len(tails) or not tails:
        problems.append(f"{len(tails)} segment(s) lost their tail; {marked_tails} marked")
    if not any("wrap(s) resolved by the sample clock" in g.cause for g in raw.gaps):
        problems.append("the dropout longer than a counter wrap was not resolved by the sample clock")
    if any(g.cause.startswith(("UNDECLARED", "HOST_", "COUNTER_AMBIGUOUS")) for g in raw.gaps):
        problems.append("a loss reached the boundary undeclared, or was left ambiguous")
    if not manifest["framing"]["bytes_discarded"]:
        problems.append("stray and corrupted bytes were not counted as discarded")
    records = load_session(output / "phantom" / "session.ndjson")
    if not any("CLOSED_LOOP_NOT_ELIGIBLE" in r["status_flags"] for r in records):
        problems.append("the closed-loop refusal is not recorded")
    if not any(r["record_type"] == "CLOCK_MAPPING" and "PROBE_BOUNDED" in r["status_flags"] for r in records):
        problems.append("no probe-bounded clock mapping was recorded")
    header = next(r for r in records if r["record_type"] == "SESSION_HEADER")
    if "BY_CONSTRUCTION:INTERNAL_TEST_CONDITIONS_ONLY" not in header["status_flags"]:
        problems.append("the phantom session does not state it holds no signal from a body")

    # 2. The same phantom with one packet the counter counts but the ADC never took: it must fail, and only there.
    faulty = Scenario(seed=12, phantom_packets=(3200,))
    _, _, results, _, _ = await simulated(faulty, b.phantom_plan(), output / "phantom-negative-control",
                                          "CYTON-SELF-TEST-NEGATIVE-CONTROL")
    failed = [c["id"] for c in results["phantom"]["checks"] if c["status"] == "FAIL"]
    summary["negative_control"] = {"verdict": results["phantom"]["verdict"], "failed": failed}
    if results["phantom"]["verdict"] != "FAIL" or not failed or \
            not all(f.startswith("TEST_SIGNAL_PERIOD_EXACT:") for f in failed):
        problems.append(f"negative control: expected only a period check to fail, got {failed}")

    # 3. An ECG on channel 2 through a lossy link, scored against the simulator's beats.
    session, raw, results, manifest, board = await simulated(
        ECG_SCENARIO, b.Plan("RECORD", (("electrodes", 75.0),), "default", ecg_channel="ch2"), output / "ecg",
        "CYTON-SELF-TEST-ECG")
    beats_us = np.array(results["_beats_us"]) + session.t0
    score = an.score_beats(beats_us, np.array(board.truth.beats_s))
    window = results["hrv"][0]["payload"] if results["hrv"] else None
    first, last = beats_us.min() / 1e6, beats_us.max() / 1e6
    reference = truth_rmssd(np.array(board.truth.beats_s), first, min(first + 60, last))
    clock = max(results["clock"], key=lambda c: c["duration_s"])
    summary["ecg"] = {**{k: round(v, 4) for k, v in score.items()}, "beats": results["ecg"]["beats"],
                      "rmssd_ms": window and round(window["rmssd_ms"], 2), "truth_rmssd_ms": round(reference, 2),
                      "clock_ppm": round(clock["ppm"], 1), "truth_ppm": ECG_SCENARIO.drift_ppm}
    if score["sensitivity"] < 0.9 or score["ppv"] < 0.98 or score["timing_rms_ms"] > 4:
        problems.append(f"ECG beats scored {score}")
    if window is None or abs(window["rmssd_ms"] - reference) > 0.15 * reference:
        problems.append(f"RMSSD {window and window['rmssd_ms']:.1f} ms against {reference:.1f} ms in the simulated beats")
    if abs(clock["ppm"] - ECG_SCENARIO.drift_ppm) > 25:
        problems.append(f"sample clock measured {clock['ppm']:.0f} ppm; the simulated oscillator runs "
                        f"{ECG_SCENARIO.drift_ppm:.0f} ppm")
    railed = [q["channel"] for q in results["quality"] if q["railed_fraction"] > 0.5]
    if railed != ["ch5"]:
        problems.append(f"railed channels {railed}, expected ch5")
    accel = raw.streams["cyton_accel"]
    rate = (len(accel) - 1) / ((accel.device_time_us[-1] - accel.device_time_us[0]) / 1e6) if len(accel) > 1 else 0
    if not 24 < rate < 26.5:
        problems.append(f"accelerometer readings arrive at {rate:.1f} Hz; the LIS3DH runs at about 25")
    for name, stream in raw.streams.items():
        if len(stream) and (np.any(stream.available_us < stream.device_time_us) or np.any(np.diff(stream.device_time_us) <= 0)):
            problems.append(f"{name}: timing invariant broken")

    # 4. The Daisy: alternating halves, both at 125 Hz, and the stale average after the ADC starts flagged.
    session, raw, results, manifest, board = await simulated(
        Scenario(seed=4, daisy=True, ecg_channel=None), b.Plan("RECORD", (("electrodes", 6.0),), "marker",
                                                                probe_interval_s=0.5), output / "daisy",
        "CYTON-SELF-TEST-DAISY")
    rows = {n: len(raw.streams[n]) for n in (EXG_STREAM, DAISY_STREAM)}
    summary["daisy"] = {**rows, "faults": manifest["ingestion"]["faults_by_kind"]}
    if abs(rows[EXG_STREAM] - rows[DAISY_STREAM]) > 1 or not 700 < rows[EXG_STREAM] < 760:
        problems.append(f"Daisy halves {rows}")
    if manifest["ingestion"]["faults_by_kind"].get("STALE_AVERAGE_AT_ADC_START") != 1:
        problems.append("the first daisy half after the ADC started was not flagged")
    if results["probes_paired"] < 8:
        problems.append(f"only {results['probes_paired']} marker probes came back")
    return problems, summary


# ------------------------------------------------------------------ hardware
def require_serial() -> bool:
    try:
        import serial  # noqa: F401
    except ImportError:
        print("this command needs pyserial: pip install pyserial", file=sys.stderr)
        return False
    return True


def list_ports() -> int:
    from serial.tools import list_ports as lp

    ports = list(lp.comports())
    for port in ports:
        dongle = (port.vid, port.pid) == FT231X_VID_PID
        print(f"{port.device:<20} {port.description}{'   <- FTDI FT231X, as on the OpenBCI dongle' if dongle else ''}")
    print(f"{len(ports)} serial port(s)" if ports else "no serial ports (is the dongle plugged in?)")
    return 0


def run_hardware(args: argparse.Namespace, plan: b.Plan, human: bool) -> int:
    port = b.SerialPort(args.port)
    latency = b.usb_latency_timer_ms(args.port)
    if latency is not None and latency > 1:
        print(f"note: the FTDI latency timer is {latency} ms; OpenBCI recommends 1 ms. Receipts stay honest bounds, but "
              f"timing is coarser (echo 1 | sudo tee /sys/bus/usb-serial/devices/{Path(args.port).name}/latency_timer)")

    async def go() -> tuple[b.Session, Any, Any]:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        import signal
        try:
            loop.add_signal_handler(signal.SIGINT, stop.set)
        except NotImplementedError:
            signal.signal(signal.SIGINT, lambda *_: loop.call_soon_threadsafe(stop.set))
        return await b.run(port, b.monotonic_us, plan, blocking_reads=True, stop=stop, status=print)

    print(f"CIRCLE <- OpenBCI Cyton on {args.port} ({p.PROTOCOL_REFERENCE})")
    try:
        session, raw, report = asyncio.run(go())
    except b.CytonError as exc:
        print(f"no session recorded: {exc}", file=sys.stderr)
        return 2
    finally:
        port.close()
    results = b.analyze(raw, session.core, session)
    banner = session.setup.banner
    hardware = "OpenBCI Cyton" + (" + Daisy" if banner and banner.daisy else "") + \
        f", firmware {session.setup.version or 'unknown'}"
    info = b.SessionInfo(args.session_id, "RAW_MEASURED", human, hardware, session.now(),
                         details={"host_clock": {"timebase": "HOST_MONOTONIC_FROM_ATTEMPT_START",
                                                 "utc_at_t0": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                            time.gmtime(time.time() - session.now() / 1e6))},
                                  "usb_latency_timer_ms": latency,
                                  **({"wearer_consent": "attested by the operator with --wearer-consents",
                                      "power": "attested by the operator with --battery-powered"} if human else {})})
    manifest = b.write_session(args.output, raw, session.core, session, info, results, report)
    print((args.output / "passport.txt").read_text(encoding="utf-8"), end="")
    if "phantom" in results:
        for item in results["phantom"]["checks"]:
            print(f"  {item['status']:<13} {item['id']}")
    print(f"ingestion: {manifest['ingestion']['samples']} samples, {manifest['ingestion']['gaps']} gaps, "
          f"{manifest['ingestion']['faults']} faults; terminated {session.terminated}")
    print(f"session written to {args.output}" + (" (owner-only; it holds the wearer's data)" if human else ""))
    return 0 if session.terminated in ("COMPLETED", "OPERATOR_STOP") else 1


def probe(args: argparse.Namespace) -> int:
    port = b.SerialPort(args.port)
    session = b.Session(port, b.monotonic_us, b.Plan("RECORD", (("electrodes", 1.0),)), blocking_reads=True)
    try:
        session.configure_board()
        session.configure_segment("electrodes")
        session.restore()
    except b.CytonError as exc:
        print(f"probe failed: {exc}", file=sys.stderr)
        return 2
    finally:
        port.close()
    s = session.setup
    print(f"dongle:   {s.dongle}")
    print(f"ADS1299:  0x{s.banner.ads_id:02X}" + (f", Daisy 0x{s.banner.daisy_ads_id:02X}" if s.banner.daisy else ""))
    print(f"LIS3DH:   0x{(s.banner.lis3dh_id or 0):02X}")
    print(f"firmware: {s.version} ('V'); banner says {s.banner.banner_firmware}"
          + ("" if s.version == f"v{p.LIBRARY_VERSION}" else f"  (CIRCLE is pinned to v{p.LIBRARY_VERSION})"))
    for config in s.configuration:
        for ch in config["channels"]:
            print(f"  ch{ch['channel']:<2} gain {ch['gain']:<2} input {ch['input_type']:<9} "
                  f"{'off' if ch['power_down'] else 'on'}  SRB2 {'closed' if ch['srb2'] else 'open'}")
    for problem in s.register_problems:
        print(f"  MISMATCH {problem}")
    return 0


# ----------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    test = sub.add_parser("self-test", help="vectors and simulated sessions; no board, no pyserial")
    test.add_argument("--output", type=Path, help="keep the simulated sessions here (default: a temporary directory)")
    sim = sub.add_parser("simulate", help="write a simulated session to inspect")
    sim.add_argument("--mode", choices=("phantom", "record"), default="phantom")
    sim.add_argument("--seconds", type=float, default=60.0, help="record mode duration (default 60)")
    sim.add_argument("--daisy", action="store_true")
    sim.add_argument("--output", type=Path, default=Path("outputs/cyton-simulated"))
    sub.add_parser("ports", help="list serial ports (needs pyserial)")
    for name in ("probe", "phantom", "record"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--port", required=True, help="the dongle's serial port, e.g. /dev/ttyUSB0 or COM3")
        if name == "probe":
            continue
        cmd.add_argument("--output", type=Path, default=Path(f"outputs/cyton-{name}"))
        cmd.add_argument("--session-id", default=f"CYTON-{name.upper()}")
        if name == "phantom":
            cmd.add_argument("--scale", type=float, default=1.0, help="multiply every segment's duration (default 1)")
        else:
            cmd.add_argument("--wearer-consents", action="store_true",
                             help="required: the person wearing the electrodes knows this records their "
                                  "biopotentials and motion to this computer, and agrees")
            cmd.add_argument("--battery-powered", action="store_true",
                             help="required: the Cyton runs on its battery and reaches this computer only through "
                                  "the radio dongle")
            cmd.add_argument("--seconds", type=float, default=300.0)
            cmd.add_argument("--board-mode", choices=("default", "analog", "digital", "marker"), default="default",
                             help="default streams the accelerometer; marker adds clock probes instead")
            cmd.add_argument("--gain", type=int, choices=p.GAINS, default=24)
            cmd.add_argument("--ecg-channel", type=int, help="detect R peaks and RMSSD on this channel (1-16)")
            cmd.add_argument("--probe-interval-s", type=float, default=0.5, help="marker mode only")
    args = parser.parse_args(argv)

    if args.command == "self-test":
        with tempfile.TemporaryDirectory() as tmp:
            out = args.output or Path(tmp)
            problems, summary = asyncio.run(self_test(out))
            print(f"OpenBCI Cyton bridge self-test (simulated board through pump() -> Ingestor -> {out})")
            for name, values in summary.items():
                print(f"  {name}: {values}")
        print("  self-test passed" if not problems else "  FAILED:\n    " + "\n    ".join(problems))
        return 0 if not problems else 1
    if args.command == "simulate":
        if args.mode == "phantom":
            plan, scenario = b.phantom_plan(), DAMAGED_PHANTOM
        else:
            plan = b.Plan("RECORD", (("electrodes", args.seconds),), "default", ecg_channel="ch2")
            scenario = Scenario(seed=3, daisy=args.daisy, radio_loss=0.002)
        _, _, results, manifest, _ = asyncio.run(simulated(scenario, plan, args.output, f"CYTON-SIMULATED-{args.mode.upper()}"))
        print((args.output / "passport.txt").read_text(encoding="utf-8"), end="")
        print(f"simulated session written to {args.output}")
        return 0
    if args.command == "record":
        if not (args.wearer_consents and args.battery_powered):
            print("record stores the wearer's biopotentials on this computer, and electrodes may touch a person only "
                  "with the board on battery and linked by radio. Confirm both: --wearer-consents --battery-powered.",
                  file=sys.stderr)
            return 2
        if args.ecg_channel is not None and not 1 <= args.ecg_channel <= 16:
            print("--ecg-channel is 1 to 16", file=sys.stderr)
            return 2
    if not require_serial():
        return 2
    if args.command == "ports":
        return list_ports()
    if args.command == "probe":
        return probe(args)
    if args.command == "phantom":
        return run_hardware(args, b.phantom_plan(args.scale), human=False)
    plan = b.Plan("RECORD", (("electrodes", args.seconds),), args.board_mode, gains=(args.gain,) * 16,
                  probe_interval_s=args.probe_interval_s if args.board_mode == "marker" else None,
                  ecg_channel=f"ch{args.ecg_channel}" if args.ecg_channel else None)
    return run_hardware(args, plan, human=True)


if __name__ == "__main__":
    raise SystemExit(main())
