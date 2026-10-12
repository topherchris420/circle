"""The OpenBCI Cyton bridge: pinned protocol, exact declared losses, the phantom's verdicts, and lawful sessions.

No board, dongle, or pyserial is needed. Sessions run against the simulated
Cyton (models/openbci_cyton/simulator.py) on a virtual clock, which follows the
pinned firmware's commands, packets, and quirks and keeps the truth it rendered.
"""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

import numpy as np

from models.openbci_cyton import analysis as an
from models.openbci_cyton import bridge as b
from models.openbci_cyton import protocol as p
from models.openbci_cyton.framing import Discarded, Framer, Packet, Text, channel_matrix, decode_packet, encode_packet
from models.openbci_cyton.simulator import Scenario, SimulatedCyton, SimulatedPort, VirtualClock
from models.openbci_cyton.streams import (ACCEL_STREAM, DAISY_STREAM, EXG_STREAM, MARKER_STREAM, CytonStreams,
                                          StreamLayout)
from models.acquisition.ingest import StreamChunk
from models.physiology.streams import DeviceEvent, Gap, RawSession
from models.session_records import load_session
from tools import openbci_cyton as tool


def packet(counter: int, value: int = 0, accel: tuple[int, int, int] = (0, 0, 0), packet_type: int = p.PACKET_ACCEL,
           aux: bytes | None = None) -> Packet:
    words = aux if aux is not None else b"".join(int(v).to_bytes(2, "big", signed=True) for v in accel)
    return decode_packet(encode_packet(counter, [value + i for i in range(8)], words, packet_type))


def chunks(pieces, stream=None):
    return [x for x in pieces if isinstance(x, StreamChunk) and (stream is None or x.stream_id == stream)]


def gaps(pieces, stream=None):
    return [x for x in pieces if isinstance(x, Gap) and (stream is None or x.stream_id == stream)]


def run(coro):
    return asyncio.run(coro)


class ProtocolTest(unittest.TestCase):
    def test_vectors_and_grammar_match_the_pinned_firmware(self):
        self.assertEqual(tool.check_protocol(), [])

    def test_refusals_name_their_reason(self):
        self.assertIn("SD-card", p.command_refusal(b"A"))
        self.assertIn("9600", p.command_refusal(b"/5"))
        self.assertIn("250 SPS", p.command_refusal(b"~3"))
        self.assertIsNone(p.command_refusal(p.marker(0x41)))
        with self.assertRaises(ValueError):
            p.marker(0)                                         # indistinguishable from "no marker"
        with self.assertRaises(ValueError):
            p.channel_settings(3, gain=3)

    def test_register_values_round_trip(self):
        for gain in p.GAINS:
            for kind in p.INPUT_TYPES:
                value = p.channel_register_value(False, gain, kind, True)
                self.assertEqual(p.ChannelRegister.decode(value), p.ChannelRegister(False, gain, kind, True))


class FramerTest(unittest.TestCase):
    def test_any_split_of_the_byte_stream_gives_the_same_result(self):
        stream = b"OpenBCI V3 8-16 channel\n$$$" + b"".join(encode_packet(i, [i] * 8) for i in range(20)) \
            + b"\x01\x02" + encode_packet(20, [7] * 8)
        whole = Framer()
        reference = whole.feed(stream) + whole.flush()
        for size in (1, 3, 33, 64):
            framer = Framer()
            items = [x for i in range(0, len(stream), size) for x in framer.feed(stream[i:i + size])] + framer.flush()
            self.assertEqual([x.counter for x in items if isinstance(x, Packet)],
                             [x.counter for x in reference if isinstance(x, Packet)])
            self.assertEqual(sum(x.count for x in items if isinstance(x, Discarded)), 2)
            self.assertEqual([x.text for x in items if isinstance(x, Text)], ["OpenBCI V3 8-16 channel\n$$$"])

    def test_a_fake_frame_inside_channel_data_is_not_accepted_after_a_resync(self):
        # Channel bytes that spell 0xA0 ... and, 32 bytes later, a 0xCX byte: a frame only by accident.
        fake = encode_packet(9, [0xA00000, 0, 0, 0, 0, 0, 0, 0xC5])
        stream = b"\x01" + fake[:5] + encode_packet(10, [1] * 8) + encode_packet(11, [2] * 8)
        framer = Framer()
        counters = [x.counter for x in framer.feed(stream) + framer.flush() if isinstance(x, Packet)]
        self.assertEqual(counters, [10, 11])

    def test_channel_matrix_agrees_with_the_per_packet_decoder(self):
        rng = np.random.default_rng(0)
        packets = [decode_packet(encode_packet(i, rng.integers(-2 ** 23, 2 ** 23, 8).tolist())) for i in range(50)]
        self.assertEqual(channel_matrix(packets).tolist(), [list(pk.channels) for pk in packets])


class StreamsTest(unittest.TestCase):
    def feed(self, streams, counters, start_us=1_000_000, period=4000, **kw):
        out = []
        for i, c in enumerate(counters):
            out += streams.packets([packet(c, **kw)], start_us + i * period + 2000)
        return out

    def test_counter_wraps_without_a_gap_and_times_are_lawful(self):
        s = CytonStreams(StreamLayout())
        s.start_segment(990_000)
        pieces = self.feed(s, [i % 256 for i in range(600)])
        self.assertEqual(gaps(pieces), [])
        exg = chunks(pieces, EXG_STREAM)
        seq = np.concatenate([c.sequence for c in exg])
        self.assertEqual(seq.tolist(), list(range(600)))
        t = np.concatenate([c.device_time_us for c in exg])
        avail = np.concatenate([c.available_us for c in exg])
        self.assertTrue(np.all(np.diff(t) > 0) and np.all(avail >= t))
        self.assertEqual(np.concatenate([c.columns["sample_index"] for c in exg]).tolist(), list(range(600)))

    def test_lost_packets_are_exactly_their_rows_and_the_segment_start_is_counted(self):
        s = CytonStreams(StreamLayout())
        s.start_segment(990_000)
        pieces = s.packets([packet(3)], 1_020_000)                       # counters 0..2 never arrived
        (start,) = gaps(pieces, EXG_STREAM)
        self.assertEqual((start.first_sequence, start.last_sequence), (0, 2))
        self.assertTrue(start.cause.startswith("CYTON_SEGMENT_START_LOST"))
        pieces = s.packets([packet(4)], 1_024_000) + s.packets([packet(9)], 1_044_000)
        (gap,) = gaps(pieces, EXG_STREAM)
        self.assertEqual((gap.first_sequence, gap.last_sequence), (5, 8))
        self.assertTrue(gap.cause.startswith("CYTON_COUNTER_DISCONTINUITY"))
        self.assertEqual(s.lost_packets, 7)

    def test_a_silence_longer_than_a_wrap_is_resolved_by_the_sample_clock(self):
        s = CytonStreams(StreamLayout())
        s.start_segment(990_000)
        self.feed(s, list(range(250)))                                   # one second establishes the clock
        lost = 600                                                       # 2.4 s of radio silence, over two wraps
        index = 250 + lost
        pieces = s.packets([packet(index % 256)], 1_000_000 + index * 4000 + 2000)
        (gap,) = gaps(pieces, EXG_STREAM)
        self.assertEqual((gap.first_sequence, gap.last_sequence), (250, 250 + lost - 1))
        self.assertIn("2 full counter wrap(s) resolved by the sample clock", gap.cause)

    def test_a_silence_the_clock_cannot_resolve_is_one_marked_discontinuity(self):
        s = CytonStreams(StreamLayout())
        s.start_segment(990_000)
        self.feed(s, list(range(250)))
        pieces = s.packets([packet(17)], 1_000_000 + 60_000_000)        # a minute: +-2.5 % spans many wraps
        (gap,) = gaps(pieces, EXG_STREAM)
        self.assertEqual(gap.first_sequence, gap.last_sequence)
        self.assertTrue(gap.cause.startswith("COUNTER_AMBIGUOUS"))
        self.assertEqual(s.epochs, 2)
        self.assertEqual(chunks(pieces, EXG_STREAM)[0].sequence.tolist(), [251])

    def test_a_loss_of_exactly_one_wrap_is_counted_not_refused(self):
        s = CytonStreams(StreamLayout())
        s.start_segment(990_000)
        self.feed(s, list(range(250)))
        index = 249 + 256                                                # counter repeats: 249 % 256 == 505 % 256
        pieces = s.packets([packet(index % 256, value=5)], 1_000_000 + index * 4000 + 2000)
        (gap,) = gaps(pieces, EXG_STREAM)
        self.assertEqual((gap.first_sequence, gap.last_sequence), (250, 504))
        self.assertEqual(s.faults, [])

    def test_a_first_packet_with_counter_255_starts_at_index_255(self):
        s = CytonStreams(StreamLayout())
        s.start_segment(990_000)
        pieces = s.packets([packet(255)], 990_000 + 256 * 4000 + 20_000)
        (gap,) = gaps(pieces, EXG_STREAM)
        self.assertEqual((gap.first_sequence, gap.last_sequence), (0, 254))
        self.assertEqual(chunks(pieces, EXG_STREAM)[0].columns["sample_index"].tolist(), [255])

    def test_duplicates_are_ignored_and_conflicts_refused(self):
        s = CytonStreams(StreamLayout())
        s.start_segment(990_000)
        self.feed(s, [0, 1])
        self.assertEqual(s.packets([packet(1)], 1_010_000), [])
        self.assertEqual(s.duplicates, 1)
        self.assertEqual(s.packets([packet(1, value=99)], 1_011_000), [])
        self.assertEqual(s.faults[-1][1], "CONFLICTING_RETRANSMISSION")

    def test_accelerometer_zero_fill_and_uncountable_loss(self):
        s = CytonStreams(StreamLayout())
        s.start_segment(990_000)
        pieces = []
        for i in range(30):
            pieces += s.packets([packet(i, accel=(16, -16, 8000) if i % 10 == 3 else (0, 0, 0))], 1_000_000 + i * 4000)
        accel = chunks(pieces, ACCEL_STREAM)
        self.assertEqual(sum(len(c) for c in accel), 3)
        self.assertEqual(accel[0].columns["az_lsb"].tolist(), [8000])
        pieces = s.packets([packet(35)], 1_000_000 + 35 * 4000)
        (mark,) = gaps(pieces, ACCEL_STREAM)
        self.assertEqual(mark.first_sequence, mark.last_sequence)
        self.assertTrue(mark.cause.startswith("ACCEL_LOSS_UNKNOWN"))

    def test_daisy_halves_alternate_and_keep_their_own_contiguous_sequences(self):
        s = CytonStreams(StreamLayout(daisy=True))
        s.start_segment(990_000)
        pieces = self.feed(s, list(range(12)))
        board, daisy = chunks(pieces, EXG_STREAM), chunks(pieces, DAISY_STREAM)
        self.assertEqual(np.concatenate([c.sequence for c in board]).tolist(), list(range(6)))
        self.assertEqual(np.concatenate([c.sequence for c in daisy]).tolist(), list(range(6)))
        self.assertEqual(np.concatenate([c.columns["sample_index"] for c in board]).tolist(), [1, 3, 5, 7, 9, 11])
        self.assertIn("STALE_AVERAGE_AT_ADC_START", [f[1] for f in s.faults])
        pieces = s.packets([packet(15)], 1_000_000 + 15 * 4000)          # 12, 13, 14 lost: two daisy rows, one board
        self.assertEqual([(g.stream_id, g.first_sequence, g.last_sequence) for g in gaps(pieces)],
                         [(EXG_STREAM, 6, 6), (DAISY_STREAM, 6, 7)])

    def test_markers_in_the_data_become_events(self):
        s = CytonStreams(StreamLayout(board_mode="marker"))
        s.start_segment(990_000)
        pieces = s.packets([packet(0, packet_type=p.PACKET_RAW_AUX, aux=b"\x00\x41" + bytes(4))], 1_002_000)
        (event,) = [x for x in pieces if isinstance(x, DeviceEvent)]
        self.assertEqual((event.stream_id, event.kind, event.attribute("code")), (MARKER_STREAM, "MARKER_IN_DATA", 65.0))

    def test_a_silent_tail_is_marked_when_the_segment_stops(self):
        s = CytonStreams(StreamLayout())
        s.start_segment(990_000)
        self.feed(s, list(range(10)))
        self.assertEqual(s.end_segment(1_100_000, 250_000, 1_350_000), [])
        s.start_segment(1_200_000)
        s.packets([packet(0)], 1_220_000)
        (mark,) = s.end_segment(2_000_000, 250_000, 2_250_000)
        self.assertTrue(mark.cause.startswith("SEGMENT_TAIL_LOST"))

    def test_a_segment_with_no_packet_marks_every_stream(self):
        s = CytonStreams(StreamLayout())
        s.start_segment(990_000)
        marks = s.end_segment(5_000_000, 250_000, 5_250_000)
        self.assertEqual({m.stream_id for m in marks}, {EXG_STREAM, ACCEL_STREAM})
        self.assertTrue(all(m.cause.startswith("SEGMENT_NOTHING_ARRIVED") for m in marks))


def simulate(scenario: Scenario, plan: b.Plan, output: Path, human: bool = False):
    async def go():
        clock = VirtualClock()
        board = SimulatedCyton(scenario)
        session, raw, report = await b.run(SimulatedPort(board, clock), clock, plan)
        results = b.analyze(raw, session.core, session)
        info = b.SessionInfo("TEST", "SIMULATED", human, "simulated Cyton", session.now())
        manifest = b.write_session(output, raw, session.core, session, info, results, report)
        return session, raw, results, manifest, board
    return run(go())


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_damaged_phantom_passes_and_its_session_is_lawful_and_self_describing(self):
        scenario = Scenario(seed=21, radio_loss=0.003, corrupt_packets=(900,))
        session, raw, results, manifest, board = simulate(scenario, b.phantom_plan(0.8), self.out / "phantom")
        card = results["phantom"]
        self.assertEqual(card["verdict"], "PASS", [c for c in card["checks"] if c["status"] == "FAIL"])
        judged = {c["id"].split(":")[0] for c in card["checks"] if c["status"] in ("PASS", "FAIL")}
        self.assertTrue({"TEST_SIGNAL_PERIOD_EXACT", "TEST_SIGNAL_TWO_LEVELS", "TEST_SIGNAL_CHANNEL_AGREEMENT",
                         "TEST_SIGNAL_2X_OVER_1X", "SHORTED_INPUT_NOISE", "SAMPLE_CLOCK_RATE", "CLOCK_PROBES_CONSISTENT",
                         "REGISTERS_READ_BACK", "FRAMING_ALL_LOSSES_DECLARED"} <= judged)
        self.assertTrue(any(c["status"] == "REPORTED" and c["id"].startswith("TEST_SIGNAL_AMPLITUDE")
                            for c in card["checks"]))
        records = load_session(self.out / "phantom" / "session.ndjson")
        header = records[0]
        self.assertIn("NOT_HUMAN_DATA", header["status_flags"])
        self.assertIn("BY_CONSTRUCTION:INTERNAL_TEST_CONDITIONS_ONLY", header["status_flags"])
        self.assertTrue(any(r["record_type"] == "FAULT" and "CLOSED_LOOP_NOT_ELIGIBLE" in r["status_flags"]
                            for r in records))
        self.assertTrue(any(r["record_type"] == "CONFIG_CHANGE" and "READ_BACK_FROM_ADS_REGISTERS" in r["status_flags"]
                            for r in records))
        self.assertNotIn(ACCEL_STREAM, raw.streams)                      # marker mode: accelerometer off
        # The raw bundle is bound by the hashes the descriptors and manifest state.
        for record in (r for r in records if r["record_type"] == "STREAM_DESCRIPTOR"):
            path = self.out / "phantom" / f"raw/{record['stream_id']}.csv.gz"
            content = gzip.decompress(path.read_bytes())
            self.assertIn(f"CONTENT_SHA256:{hashlib.sha256(content).hexdigest()}", record["status_flags"])
        for name, entry in manifest["artifacts"].items():
            self.assertEqual(hashlib.sha256((self.out / "phantom" / name).read_bytes()).hexdigest(), entry["sha256"])
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(os.stat(self.out / "phantom" / "session.ndjson").st_mode), 0o600)
        # The board is left as a next program expects it.
        self.assertEqual(session.setup.commands[-2:], ["d", "/0"])
        self.assertEqual(board.board_mode, "default")
        self.assertTrue(all(s["input_type"] == "NORMAL" for s in board.settings))

    def test_a_packet_the_adc_never_took_fails_the_period_check(self):
        _, _, results, _, _ = simulate(Scenario(seed=22, phantom_packets=(2100,)), b.phantom_plan(0.6),
                                       self.out / "negative")
        failed = [c["id"] for c in results["phantom"]["checks"] if c["status"] == "FAIL"]
        self.assertEqual(results["phantom"]["verdict"], "FAIL")
        self.assertTrue(failed and all(f.startswith("TEST_SIGNAL_PERIOD_EXACT:") for f in failed), failed)

    def test_a_board_that_ignores_channel_settings_is_caught_by_read_back(self):
        plan = b.Plan("RECORD", (("electrodes", 3.0),), "default", gains=(12,) * 16)
        session, raw, _, _, _ = simulate(Scenario(seed=23, ignore_channel_commands=True), plan, self.out / "mismatch")
        self.assertEqual(len(session.setup.register_problems), 8)
        self.assertEqual(raw.descriptors[EXG_STREAM]["ch1_gain"], 24.0)  # scaling follows the ADC, not the request
        records = load_session(self.out / "mismatch" / "session.ndjson")
        self.assertEqual(sum("BOARD_CONFIGURATION_MISMATCH" in r["status_flags"] for r in records), 8)

    def test_an_incomplete_register_dump_verifies_nothing_it_lacks(self):
        _, raw, results, _, _ = simulate(Scenario(seed=26, drop_register_lines=("CH3SET",)), b.phantom_plan(0.3),
                                         self.out / "partial")
        read_back = next(c for c in results["phantom"]["checks"] if c["id"] == "REGISTERS_READ_BACK")
        self.assertEqual(read_back["status"], "FAIL")
        records = load_session(self.out / "partial" / "session.ndjson")
        self.assertTrue(any("PARTLY_READ_BACK_REST_ASSUMED" in r["status_flags"] for r in records))
        self.assertTrue(any("CH3SET" in r.get("cause", "") for r in records if r["record_type"] == "FAULT"))
        exg = next(r for r in records if r["record_type"] == "STREAM_DESCRIPTOR")
        self.assertIn("SCALE:GAIN_NOT_FULLY_READ_BACK", exg["status_flags"])

    def test_a_missing_daisy_section_is_a_mismatch(self):
        plan = b.Plan("RECORD", (("electrodes", 2.0),), "default")
        session, _, _, _, _ = simulate(Scenario(seed=27, daisy=True, drop_register_lines=("DAISY_SECTION",)), plan,
                                       self.out / "no-daisy-dump")
        self.assertTrue(any("daisy ADS1299's registers are missing" in x for x in session.setup.register_problems))

    def test_an_ecg_channel_the_board_lacks_is_refused_before_acquisition(self):
        clock = VirtualClock()
        board = SimulatedCyton(Scenario(seed=28))
        plan = b.Plan("RECORD", (("electrodes", 5.0),), "default", ecg_channel="ch12")
        with self.assertRaises(b.CytonError) as caught:
            run(b.run(SimulatedPort(board, clock), clock, plan))
        self.assertIn("8 channels", str(caught.exception))
        self.assertEqual(board.truth.segments, [])                       # nothing was streamed
        empty = an.ecg_beats(RawSession({}, {}), "ch12", [])
        self.assertEqual((empty["beats"], empty["unavailable"]), ([], "the board has no such channel"))

    def test_a_segment_that_delivers_nothing_is_marked_and_not_completed(self):
        plan = b.Plan("RECORD", (("electrodes", 3.0),), "default")
        session, raw, _, _, _ = simulate(Scenario(seed=29, dropouts_s=((0.0, 1e4),)), plan, self.out / "silent")
        self.assertEqual(session.terminated, "SEGMENT_DELIVERED_NOTHING")
        self.assertEqual(len(raw.streams[EXG_STREAM]), 0)
        marks = [g for g in raw.gaps if g.cause.startswith("SEGMENT_NOTHING_ARRIVED")]
        self.assertEqual({g.stream_id for g in marks}, {EXG_STREAM, ACCEL_STREAM})
        load_session(self.out / "silent" / "session.ndjson")

    def test_packets_held_in_usb_past_the_stop_are_drained_not_declared_lost(self):
        plan = b.Plan("RECORD", (("electrodes", 4.0),), "default")
        session, _, _, _, _ = simulate(Scenario(seed=30), plan, self.out / "dry-run")
        stop_world_s = (session.t0 + session.segments[0]["started_us"]) / 1e6 + 4.0
        stall = ((stop_world_s - 0.35, stop_world_s + 0.05),)
        session, raw, _, _, _ = simulate(Scenario(seed=30, usb_stalls_s=stall), plan, self.out / "stalled")
        self.assertEqual(raw.gaps, [])
        self.assertEqual(session.core.streams.epochs, 1)
        self.assertEqual(session.terminated, "COMPLETED")

    def test_an_ecg_recording_is_human_data_with_lawful_hrv_windows(self):
        plan = b.Plan("RECORD", (("electrodes", 65.0),), "default", ecg_channel="ch2")
        session, raw, results, _, board = simulate(Scenario(seed=24, radio_loss=0.001), plan, self.out / "ecg",
                                                   human=True)
        score = an.score_beats(np.array(results["_beats_us"]) + session.t0, np.array(board.truth.beats_s))
        self.assertGreater(score["sensitivity"], 0.9)
        self.assertGreater(score["ppv"], 0.98)
        records = load_session(self.out / "ecg" / "session.ndjson")
        self.assertIn("HUMAN_DATA", records[0]["status_flags"])
        windows = [r for r in records if "HRV_WINDOW" in r["status_flags"]]
        self.assertTrue(windows)
        for window in windows:
            self.assertEqual(window["provenance"], "MODEL_INFERRED")
            self.assertLessEqual(window["input_cutoff_us"], window["decision_time_us"])
            self.assertGreater(window["payload"]["mean_hr_bpm"], 55)
        self.assertTrue(any(r["record_type"] == "CLOCK_MAPPING" and "UPPER_BOUND_ONLY_LATENCY_FLOOR_UNKNOWN"
                            in r["status_flags"] for r in records))
        analysis = json.loads((self.out / "ecg" / "analysis.json").read_text())
        self.assertNotIn("_beats_us", analysis)

    def test_an_unreachable_board_records_nothing(self):
        clock = VirtualClock()
        with self.assertRaises(b.CytonError) as caught:
            run(b.run(SimulatedPort(SimulatedCyton(Scenario(power_off_s=0.0)), clock), clock, b.phantom_plan()))
        self.assertIn("unreachable", str(caught.exception))

    def test_a_failing_port_ends_the_session_with_a_marked_loss_and_an_export(self):
        class Failing(SimulatedPort):
            def read(self, timeout_s):
                if self.clock() > 8_000_000:
                    raise OSError("device unplugged")
                return super().read(timeout_s)

        async def go():
            clock = VirtualClock()
            plan = b.Plan("RECORD", (("electrodes", 20.0),), "default")
            session, raw, report = await b.run(Failing(SimulatedCyton(Scenario(seed=25)), clock), clock, plan)
            return session, raw
        session, raw = run(go())
        self.assertEqual(session.terminated, "LINK_LOST")
        self.assertTrue(any(g.cause.startswith("LINK_LOST") for g in raw.gaps))
        self.assertIn("LINK:DISCONNECTED", [e.kind for e in raw.events])

    def test_the_bridge_never_sends_a_refused_command(self):
        session = b.Session(SimulatedPort(SimulatedCyton(), VirtualClock()), VirtualClock(), b.phantom_plan(),
                            blocking_reads=False)
        with self.assertRaises(ValueError):
            session.send(b"A")                                           # SD-card logging

    def test_phantom_plans_cannot_include_electrodes_or_the_accelerometer(self):
        with self.assertRaises(ValueError):
            b.Plan("PHANTOM", (("electrodes", 1.0),), "marker")
        with self.assertRaises(ValueError):
            b.Plan("PHANTOM", (("shorted", 1.0),), "default")


class ProbePairingTest(unittest.TestCase):
    def test_a_marker_pairs_with_its_own_send_not_an_earlier_lost_one(self):
        def seen(at_us, index):
            return DeviceEvent(MARKER_STREAM, index, "MARKER_IN_DATA", at_us,
                               (("code", 65.0), ("epoch", 0.0), ("sample_index", float(index))))
        sent = [(65, 1_000_000), (66, 1_500_000), (65, 27_000_000), (65, 53_000_000)]
        probes = b.pair_probes([seen(27_010_000, 6_500), seen(53_012_000, 13_000)], sent)
        self.assertEqual(probes, [(0, 6_500, 27_000_000), (0, 13_000, 53_000_000)])


class CommandLineTest(unittest.TestCase):
    def test_record_refuses_without_consent_and_power_attestation(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(tool.main(["record", "--port", "/dev/null", "--wearer-consents"]), 2)
        self.assertIn("--battery-powered", err.getvalue())

    def test_simulate_writes_a_session(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(tool.main(["simulate", "--mode", "record", "--seconds", "4", "--output", tmp]), 0)
            load_session(Path(tmp) / "session.ndjson")
        self.assertIn("simulated session written", out.getvalue())


if __name__ == "__main__":
    unittest.main()
