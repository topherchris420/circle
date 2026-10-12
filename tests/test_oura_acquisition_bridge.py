"""The Oura BLE bridge: open_oura's decoders, exact declared losses, and a session that keeps CIRCLE's rules.

No ring and no bleak are needed. The live path runs against a fake bleak whose
ring answers the real protocol (AES challenge, feature modes, time-boxed ACM),
streams frames, drops the link once, and remembers the state it is left in.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest

import numpy as np

from models.acquisition.ingest import StreamChunk
from models.session_records import load_session
from models.physiology.streams import Gap
from tools import oura_acquisition_bridge as bridge
from tools.oura_acquisition_bridge import (ACM_SLOTS, ACM_STREAM, IBI_STREAM, BridgeCore, RingStreams, acm_frame,
                                           beat_frame, check_vectors, rmssd_ms)

KEY = bytes.fromhex("4431967d8bacc2659743142b68391d9a")
FIRMWARE_REPLY = bytes.fromhex("091202000003040301000105000cffeeddccbbaa")   # carries a MAC: aa:bb:cc:dd:ee:ff


def chunks(pieces):
    return [p for p in pieces if isinstance(p, StreamChunk)]


def gaps(pieces):
    return [p for p in pieces if isinstance(p, Gap)]


class DecoderTest(unittest.TestCase):
    def test_open_oura_vectors_and_request_bytes(self):
        self.assertEqual(check_vectors(), [])

    def test_beat_keeps_invalid_beats_with_their_validity(self):
        beat = bridge.decode_live_beat(beat_frame(1100, validity=0, time_since=7))
        self.assertEqual((beat.ibi_ms, beat.validity, beat.time_since_raw, beat.bpm), (1100, 0, 7, None))
        self.assertIsNone(bridge.decode_live_beat(beat_frame(800)[:8]))

    def test_rmssd_matches_open_oura(self):
        self.assertAlmostEqual(rmssd_ms(np.array([800, 820, 810, 830])), 17.3205, places=3)


class RingStreamsTest(unittest.TestCase):
    def acm(self, streams, counter, at, samples=2):
        return streams.notification(acm_frame(counter, [(1, 2, 3), (4, 5, 6)][:samples]), at)

    def test_counter_wraps_without_a_gap(self):
        s = RingStreams(hr=False)
        pieces = [p for i, c in enumerate((254, 255, 0, 1)) for p in self.acm(s, c, 1_000_000 + 40_000 * i)]
        self.assertEqual(gaps(pieces), [])
        self.assertEqual(np.concatenate([c.sequence for c in chunks(pieces)]).tolist(), list(range(8)))

    def test_lost_frames_are_exactly_their_slots(self):
        s = RingStreams(hr=False)
        self.acm(s, 10, 1_000_000)
        pieces = self.acm(s, 14, 1_160_000)
        (gap,) = gaps(pieces)
        self.assertEqual((gap.first_sequence, gap.last_sequence), (ACM_SLOTS, 4 * ACM_SLOTS - 1))
        self.assertTrue(gap.cause.startswith("RING_FRAME_COUNTER_DISCONTINUITY"))
        self.assertEqual(chunks(pieces)[0].sequence.tolist(), [8, 9])

    def test_late_old_frame_is_refused_not_read_as_a_wrap(self):
        s = RingStreams(hr=False)
        self.acm(s, 10, 1_000_000)
        self.acm(s, 11, 1_040_000)
        self.assertEqual(self.acm(s, 10, 1_040_100, samples=1), [])
        self.assertEqual(s.faults[-1][1], "STALE_FRAME")
        self.assertEqual(gaps(self.acm(s, 12, 1_080_000)), [])

    def test_a_wrong_stated_rate_cannot_stall_the_stream(self):
        s = RingStreams(hr=False)
        self.acm(s, 0, 1_000_000)
        refused = [self.acm(s, 100 + i, 1_100_000 + 10_000 * i) for i in range(bridge.MAX_STALE_RUN)]
        self.assertEqual(refused, [[]] * bridge.MAX_STALE_RUN)
        (gap,) = gaps(self.acm(s, 110, 1_200_000))
        self.assertTrue(gap.cause.startswith("RATE_INCONSISTENT"))
        self.assertEqual(gaps(self.acm(s, 111, 1_240_000)), [])

    def test_identical_retransmission_is_dropped_and_a_conflicting_one_refused(self):
        s = RingStreams(hr=False)
        self.acm(s, 5, 1_000_000)
        self.assertEqual(self.acm(s, 5, 1_000_100), [])
        self.assertEqual(s.duplicate_frames, 1)
        self.assertEqual(self.acm(s, 5, 1_000_200, samples=1), [])
        self.assertEqual(s.faults[-1][1], "CONFLICTING_RETRANSMISSION")

    def test_silence_beyond_the_counter_is_marked_not_guessed(self):
        s = RingStreams(hr=False)
        self.acm(s, 10, 1_000_000)
        (gap,) = gaps(self.acm(s, 12, 13_000_000))
        self.assertTrue(gap.cause.startswith("COUNTER_AMBIGUOUS"))
        self.assertEqual(gap.last_sequence - gap.first_sequence + 1, ACM_SLOTS)

    def test_rearm_keeps_continuity_or_marks_a_restart(self):
        s = RingStreams(hr=False)
        self.acm(s, 100, 1_000_000)
        s.acm_rearmed()
        self.assertEqual(gaps(self.acm(s, 101, 1_040_000)), [])
        s.acm_rearmed()
        (gap,) = gaps(self.acm(s, 0, 1_080_000))
        self.assertTrue(gap.cause.startswith("ACM_REARMED"))

    def test_link_loss_marks_each_delivering_stream_once(self):
        s = RingStreams()
        s.notification(beat_frame(900), 1_000_000)
        self.acm(s, 1, 1_010_000)
        first = s.link_lost(2_000_000, "test")
        self.assertEqual(sorted(g.stream_id for g in first), [ACM_STREAM, IBI_STREAM])
        self.assertEqual(s.link_lost(3_000_000, "again"), [])
        self.assertEqual(chunks(s.notification(beat_frame(900), 4_000_000))[0].sequence.tolist(), [2])

    def test_sample_times_increase_and_never_precede_availability(self):
        s = RingStreams(hr=False)
        burst = [p for c in range(1, 6) for p in self.acm(s, c, 2_000_000 + c)]   # five frames in one radio event
        times = np.concatenate([c.device_time_us for c in chunks(burst)])
        avail = np.concatenate([c.available_us for c in chunks(burst)])
        self.assertTrue(np.all(np.diff(times) > 0))
        self.assertTrue(np.all(avail >= times))

    def test_other_notifications_are_counted_and_discarded(self):
        s = RingStreams()
        self.assertEqual(s.notification(FIRMWARE_REPLY, 1_000), [])
        self.assertEqual(s.notification(beat_frame(900, feature=0x03), 2_000), [])
        self.assertEqual(dict(s.ignored), {"0x09": 1, "0x2f/0x28": 1})


class SelfTestSessionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "session"
        cls.problems, cls.manifest = asyncio.run(bridge.self_test(cls.out))
        cls.records = load_session(cls.out / "session.ndjson")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_self_test_passes(self):
        self.assertEqual(self.problems, [])

    def test_raw_bundle_is_bound_by_its_descriptor(self):
        for record in (r for r in self.records if r["record_type"] == "STREAM_DESCRIPTOR"):
            flags = dict(f.split(":", 1) for f in record["status_flags"] if ":" in f)
            content = gzip.decompress((self.out / flags["RAW_ARTIFACT"]).read_bytes())
            self.assertEqual(hashlib.sha256(content).hexdigest(), flags["CONTENT_SHA256"])

    def test_hrv_windows_recompute_from_their_cited_beats(self):
        lines = gzip.decompress((self.out / "raw/oura_ibi.csv.gz").read_bytes()).decode().splitlines()
        rows = {int(r[0]): int(r[3]) for r in (line.split(",") for line in lines[1:])}
        windows = [r for r in self.records if "HRV_WINDOW" in r["status_flags"]]
        self.assertTrue(windows)
        for window in windows:
            diffs = []
            for span in window["source_sequence_ranges"]:
                beats = [rows[s] for s in range(span["first_sequence"], span["last_sequence"] + 1)]
                self.assertTrue(all(300 <= b <= 2000 for b in beats))
                diffs += np.diff(beats).tolist()
            self.assertEqual(len(diffs), window["payload"]["successive_pairs"])
            self.assertAlmostEqual(float(np.sqrt(np.mean(np.square(diffs)))), window["payload"]["rmssd_ms"], places=9)
            self.assertLessEqual(window["input_cutoff_us"], window["decision_time_us"])

    def test_closed_loop_refusal_is_recorded(self):
        refused = [r["cause"] for r in self.records if "CLOSED_LOOP_NOT_ELIGIBLE" in r["status_flags"]
                   and r["record_type"] == "FAULT"]
        self.assertEqual(len(refused), 4)


# --------------------------------------------------------------- fake bleak
class FakeRing:
    """A ring that speaks the protocol the bridge uses, and remembers what was left switched on."""

    def __init__(self, key: bytes, drop_after_frames: int) -> None:
        self.key, self.drop_after_frames = key, drop_after_frames
        self.hr_mode, self.acm_on, self.counter, self.nonce = 1, False, 0, bytes(range(1, 16))
        self.authenticated = False
        self.writes: list[bytes] = []

    def handle(self, data: bytes) -> list[bytes]:
        self.writes.append(data)
        if data == bridge.REQUEST_FIRMWARE:
            return [FIRMWARE_REPLY]
        if data == bridge.REQUEST_HARDWARE_ID:
            return [bytes.fromhex("191100424c425f303300000000000000000000")]
        if data == bytes.fromhex("2f012b"):
            return [bytes.fromhex("2f102c") + self.nonce]
        if data[:3] == bytes.fromhex("2f112d"):
            self.authenticated = data[3:] == bridge.encrypt_nonce(self.key, self.nonce)
            return [bytes([0x2F, 0x02, 0x2E, 0 if self.authenticated else 1])]
        if not self.authenticated:
            return [bytes.fromhex("2f022f01")]
        if data == bytes.fromhex("2f022002"):
            return [bytes([0x2F, 0x06, 0x21, 0x02, self.hr_mode, 0, 0, 0])]
        if data[:4] == bytes.fromhex("2f032202"):
            self.hr_mode = data[4]
            return [bytes.fromhex("2f03230200")]
        if data[:2] == bytes.fromhex("0607"):
            self.acm_on = True
            return [bytes.fromhex("070100")]
        if data == bytes.fromhex("060400000000"):
            self.acm_on = False
            return [bytes.fromhex("070100")]
        return []


class FakeBleakError(Exception):
    pass


def fake_bleak(ring: FakeRing, fail_on_reconnect: Exception | None = None) -> dict[str, types.ModuleType]:
    device = types.SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="Oura Ring Gen3")
    adv = types.SimpleNamespace(service_uuids=[bridge.OURA_SERVICE], rssi=-50, local_name="Oura Ring Gen3")
    characteristic = types.SimpleNamespace(uuid=bridge.OURA_NOTIFY, properties=["notify"])

    class Scanner:
        @staticmethod
        async def discover(timeout, return_adv):
            return {device.address: (device, adv)}

        @staticmethod
        async def find_device_by_address(address, timeout):
            return device

    class Client:
        connections = 0

        def __init__(self, target, disconnected_callback=None, timeout=None):
            self.callback, self.notify, self.dropped = disconnected_callback, None, False
            self.services = types.SimpleNamespace(
                get_service=lambda uuid: types.SimpleNamespace(characteristics=[characteristic]))

        async def __aenter__(self):
            Client.connections += 1
            ring.authenticated = False
            if Client.connections > 1:
                ring.counter = 0                       # a re-armed ring restarts its frame counter
            self.task = asyncio.ensure_future(self.stream())
            return self

        async def __aexit__(self, *exc):
            self.task.cancel()
            if not self.dropped:
                self.callback(self)                    # bleak reports every disconnect, intended or not

        async def start_notify(self, char, callback):
            if fail_on_reconnect is not None and Client.connections > 1:
                raise fail_on_reconnect
            self.notify = callback

        async def write_gatt_char(self, uuid, data, response=True):
            if self.dropped:
                raise FakeBleakError("not connected")
            for frame in ring.handle(bytes(data)):
                asyncio.get_running_loop().call_soon(self.notify, char_for(uuid), bytearray(frame))

        async def pair(self):
            return True

        async def stream(self):
            sent = 0
            while True:
                await asyncio.sleep(0.01)
                if ring.acm_on and self.notify:
                    ring.counter = (ring.counter + 1) % 256
                    self.notify(characteristic, bytearray(acm_frame(ring.counter, [(1, 2, 16384), (3, 4, 16380)])))
                    sent += 1
                if ring.hr_mode == 3 and self.notify and sent % 10 == 0:
                    self.notify(characteristic, bytearray(beat_frame(880 + (sent % 7) * 10)))
                if Client.connections == 1 and sent >= ring.drop_after_frames:
                    self.dropped = True
                    self.callback(self)
                    return

    def char_for(uuid):
        return characteristic

    package = types.ModuleType("bleak")
    package.BleakScanner, package.BleakClient = Scanner, Client
    exc = types.ModuleType("bleak.exc")
    exc.BleakError = FakeBleakError
    package.exc = exc
    return {"bleak": package, "bleak.exc": exc}


def run_fake_session(root: Path, ring: FakeRing, fail_on_reconnect: Exception | None = None) -> int:
    key_file = root / "ring.key"
    key_file.write_text(KEY.hex() + "\n", encoding="ascii")
    os.chmod(key_file, 0o600)
    args = argparse.Namespace(key_file=key_file, wearer_consents=True, seconds=1.2, output=root / "session",
                              session_id="OURA-FAKE", no_hr=False, no_acm=False, pair=False, connect_timeout=5.0,
                              max_reconnects=3, reconnect_delay_s=0.05, queue=256, stale_after_s=None,
                              disconnected_after_s=None, address=None, name="Oura", scan_timeout=0.1)
    saved = {name: sys.modules.get(name) for name in ("bleak", "bleak.exc")}
    sys.modules.update(fake_bleak(ring, fail_on_reconnect))
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return asyncio.run(bridge.record(args))
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class LiveBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "session"
        cls.ring = FakeRing(KEY, drop_after_frames=40)
        cls.code = run_fake_session(Path(cls.tmp.name), cls.ring)
        cls.records = load_session(cls.out / "session.ndjson")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def kinds(self):
        return [f.split(":", 1)[1] for r in self.records if r["record_type"] == "EVENT"
                for f in r["status_flags"] if f.startswith("EVENT_KIND:")]

    def test_session_is_written_and_valid(self):
        self.assertEqual(self.code, 0)
        header = self.records[0]
        self.assertIn("HUMAN_DATA", header["status_flags"])
        self.assertIn("WEARER_CONSENT:ATTESTED_BY_OPERATOR", header["status_flags"])
        self.assertIn("SOURCE_HARDWARE:Oura ring BLB_03, firmware 3.4.3", header["status_flags"])
        self.assertEqual(header["provenance"], "RAW_MEASURED")

    def test_ring_is_authenticated_streamed_and_restored(self):
        kinds = self.kinds()
        for kind in ("RING_AUTHENTICATION", "LIVE_HR_ON", "ACM_ON", "RING_DISCONNECTED", "RING_RESTORED",
                     "LINK:DISCONNECTED", "LINK:RECONNECTED"):
            self.assertIn(kind, kinds)
        self.assertEqual(kinds.count("RING_CONNECTED"), 2)
        self.assertEqual((self.ring.hr_mode, self.ring.acm_on), (1, False))

    def test_dropped_link_is_an_exact_marked_gap_on_both_streams(self):
        lost = [r for r in self.records if r["record_type"] == "GAP" and r["cause"].startswith("LINK_LOST")]
        self.assertEqual(sorted(r["stream_id"] for r in lost), [ACM_STREAM, IBI_STREAM])
        undeclared = [r for r in self.records if r["record_type"] == "GAP" and r["cause"].startswith("UNDECLARED")]
        self.assertEqual(undeclared, [])

    def test_no_identifier_or_key_leaves_the_ring(self):
        for path in self.out.rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                data = gzip.decompress(data) if path.suffix == ".gz" else data
                for secret in (KEY.hex(), "aabbccddeeff", "ffeeddccbbaa", "aa:bb:cc:dd:ee:ff"):
                    self.assertNotIn(secret.encode(), data.lower(), path.name)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)

    def test_both_streams_reached_the_boundary(self):
        manifest = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        self.assertGreater(manifest["ingestion"]["samples"][ACM_STREAM], 40)
        self.assertGreater(manifest["ingestion"]["samples"][IBI_STREAM], 2)
        self.assertEqual(manifest["provenance"], "RAW_MEASURED")


class BackendFailureTest(unittest.TestCase):
    def test_an_unexpected_backend_error_still_exports_what_was_acquired(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = run_fake_session(Path(tmp), FakeRing(KEY, drop_after_frames=40), EOFError("dbus went away"))
            records = load_session(Path(tmp) / "session" / "session.ndjson")
        self.assertEqual(code, 0)
        self.assertIn("TERMINATED:BRIDGE_ERROR:EOFError", records[-1]["status_flags"])
        self.assertGreater(records[-1]["payload"]["samples_oura_acm"], 0)


class CommandLineTest(unittest.TestCase):
    def test_record_needs_the_wearers_consent(self):
        with tempfile.NamedTemporaryFile() as key, contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(bridge.main(["record", "--key-file", key.name]), 2)
        self.assertIn("--wearer-consents", err.getvalue())

    def test_core_requires_a_stream(self):
        with self.assertRaises(ValueError):
            BridgeCore(False, False, 1.0, 4.0)


if __name__ == "__main__":
    unittest.main()
