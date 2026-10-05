"""The live ingestion boundary: deliveries in, a lawful RawSession out, every departure explicit.

The twin's own records are delivered chunk by chunk, as a device would deliver
them, over a link that can corrupt, repeat, stall, and drop. The tests demand
that clean delivery changes nothing at all, that every fault is refused or
declared (never repaired or hidden), that a silent link is never mistaken for a
calm subject, and that a session which went through the boundary still exports,
audits as REPLAY_MATCH, and replays from its recording.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import gzip
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from models.acquisition.ingest import LINK_STREAM, Ingestor, LinkMonitor, StreamChunk
from models.acquisition.live import IngestingSource, pump
from models.acquisition.recorded import RecordedSource
from models.acquisition.records import refusal_session, write_refusal
from models.acquisition.simulator import CORRUPTIONS, FaultPlan, SimulatedLink, corrupted
from models.physiology.audit import audit_run
from models.physiology.controller import ClosedLoopController, ControllerConfig
from models.physiology.evidence import dumps
from models.physiology.experiment import SessionConfig, TwinHapticActuator, TwinSource, run_session, session_run
from models.physiology.ledger import passport
from models.physiology.loop import ActuatorCapability, Capabilities, NullActuator, run_closed_loop
from models.physiology.scenarios import SCENARIOS
from models.physiology.sensors import RigConfig, SensorRig
from models.physiology.streams import DeviceEvent, Gap, RawSession
from models.physiology.twin import DEFAULT_MOTION, PhysiologyTwin, TwinConfig
from models.session_records import SessionRecordError, load_session, seal_record, validate_session
from tools.run_physiology_twin import export_run

SHORT = SessionConfig(twin=TwinConfig(duration_s=130.0, motion=DEFAULT_MOTION[:1]))
SHORT_STALL = replace(SHORT, rig=RigConfig(ppg_fifo_stall_at_s=40.0))
ACQUISITION_FLAGS = ("ACQUISITION:LIVE_INGESTION_BOUNDARY", "AVAILABILITY:HOST_RECEIPT")


def chunks(stream, size: int) -> list[StreamChunk]:
    return [StreamChunk.of(stream, a, min(a + size, len(stream))) for a in range(0, len(stream), size)]


def deliver_all(ingestor: Ingestor, raw: RawSession, size: int = 997) -> None:
    for gap in raw.gaps:
        ingestor.deliver_gap(gap, gap.device_time_us)
    for name, stream in raw.streams.items():
        for chunk in chunks(stream, size):
            ingestor.deliver_chunk(chunk, chunk.available_us)
    for event in raw.events:
        ingestor.deliver_event(event, event.device_time_us)


def same_stream(a, b) -> bool:
    return (all(np.array_equal(getattr(a, f), getattr(b, f)) for f in ("sequence", "device_time_us", "available_us"))
            and a.columns.keys() == b.columns.keys() and all(np.array_equal(a.columns[c], b.columns[c]) for c in a.columns))


def live_run(plan: FaultPlan, config: SessionConfig = SessionConfig(), capacity=4_000_000):
    twin = PhysiologyTwin(config.twin)
    rig = SensorRig(twin, config.rig)
    source = IngestingSource(SimulatedLink(TwinSource(twin, rig), plan), capacity=capacity)
    result = run_closed_loop(source, TwinHapticActuator(twin, rig, config.actuate), ClosedLoopController(config.controller))
    return source, result, twin, rig


class IngestorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = run_session(SHORT_STALL).raw
        cls.imu = cls.raw.streams["imu"]

    def ingestor(self, **kwargs) -> Ingestor:
        return Ingestor(self.raw.descriptors, **kwargs)

    def test_chunked_delivery_reproduces_the_record_exactly(self):
        ingestor = self.ingestor()
        deliver_all(ingestor, self.raw)
        view = ingestor.view()
        for name in self.raw.streams:
            self.assertTrue(same_stream(view.streams[name], self.raw.streams[name]), name)
        self.assertEqual(sorted(view.gaps, key=lambda g: g.first_sequence), self.raw.gaps)
        self.assertEqual(view.events, self.raw.events)
        self.assertEqual((ingestor.faults, ingestor.summary()["host_declared_gaps"]), ([], 0))

    def test_a_view_holds_only_what_firmware_held_by_then(self):
        ingestor = self.ingestor()
        deliver_all(ingestor, self.raw)
        for t in (int(self.imu.device_time_us[1000]), int(self.raw.streams["ppg"].available_us[4000])):
            expected, view = self.raw.until(t), ingestor.view(t)
            for name in expected.streams:
                self.assertTrue(same_stream(view.streams[name], expected.streams[name]))
            self.assertEqual(view.events, expected.events)

    def test_malformed_chunks_are_refused_and_kept_as_faults(self):
        real = StreamChunk.of(self.raw.streams["ppg"], 0, 200)
        for kind in CORRUPTIONS:
            with self.subTest(kind=kind):
                ingestor = self.ingestor()
                outcome = ingestor.deliver_chunk(corrupted(real, kind), real.available_us)
                expected = "UNKNOWN_STREAM" if kind == "UNKNOWN_STREAM" else "MALFORMED"
                self.assertEqual(outcome, f"REJECTED:{expected}")
                self.assertEqual([f.kind for f in ingestor.faults], [expected])
                self.assertEqual(ingestor.deliver_chunk(real, real.available_us), "ACCEPTED")
        ingestor = self.ingestor()
        self.assertEqual(ingestor.deliver_chunk(real, real.available_us[:5]), "REJECTED:MALFORMED")
        self.assertEqual(ingestor.deliver_chunk(real.part(0, 0), 0), "EMPTY")

    def test_an_identical_retransmission_is_dropped_and_a_conflicting_one_refused(self):
        ingestor = self.ingestor()
        first, second = StreamChunk.of(self.imu, 0, 100), StreamChunk.of(self.imu, 100, 200)
        for chunk in (first, second):
            self.assertEqual(ingestor.deliver_chunk(chunk, chunk.available_us), "ACCEPTED")
        self.assertEqual(ingestor.deliver_chunk(first, first.available_us), "DUPLICATE")
        overlap = StreamChunk.of(self.imu, 150, 250)
        self.assertEqual(ingestor.deliver_chunk(overlap, overlap.available_us), "TRIMMED")
        self.assertEqual(len(ingestor.view().streams["imu"]), 250)
        forged = replace(first, columns={**first.columns, "ax_lsb": first.columns["ax_lsb"] + 1})
        self.assertEqual(ingestor.deliver_chunk(forged, first.available_us), "REJECTED:CONFLICTING_RETRANSMISSION")
        self.assertEqual(len(ingestor.view().streams["imu"]), 250)

    def test_a_chunk_from_the_past_is_refused(self):
        ingestor = self.ingestor()
        ingestor.deliver_chunk(StreamChunk.of(self.imu, 0, 200), self.imu.available_us[:200])
        late = StreamChunk.of(self.imu, 300, 400)
        shift = int(late.device_time_us[0] - self.imu.device_time_us[100])
        backwards = replace(late, device_time_us=late.device_time_us - shift, available_us=late.available_us - shift)
        self.assertEqual(ingestor.deliver_chunk(backwards, backwards.available_us), "REJECTED:OUT_OF_ORDER")

    def test_an_undeclared_loss_is_declared_by_the_host_with_its_exact_range(self):
        ingestor = self.ingestor()
        for a, b in ((0, 100), (150, 250)):
            chunk = StreamChunk.of(self.imu, a, b)
            ingestor.deliver_chunk(chunk, chunk.available_us)
        inner = StreamChunk.of(self.imu, 250, 370)
        keep = np.r_[0:50, 70:120]
        jumped = StreamChunk("imu", inner.sequence[keep], inner.device_time_us[keep], inner.available_us[keep],
                             {c: v[keep] for c, v in inner.columns.items()})
        ingestor.deliver_chunk(jumped, jumped.available_us)
        gaps = [(g.first_sequence, g.last_sequence) for g in ingestor.gaps]
        self.assertEqual(gaps, [(100, 149), (300, 319)])
        self.assertTrue(all(g.cause.startswith("UNDECLARED_SEQUENCE_DISCONTINUITY") for g in ingestor.gaps))
        self.assertEqual(ingestor.gaps[0].device_time_us, int(self.imu.available_us[150]))

    def test_a_device_declaration_may_arrive_before_the_samples_preceding_the_loss(self):
        (fifo_gap,) = self.raw.gaps
        ingestor = self.ingestor()
        self.assertEqual(ingestor.deliver_gap(fifo_gap, fifo_gap.device_time_us), "ACCEPTED")
        for chunk in chunks(self.raw.streams["ppg"], 300):
            ingestor.deliver_chunk(chunk, chunk.available_us)
        self.assertEqual(ingestor.gaps, [fifo_gap])
        self.assertEqual(ingestor.deliver_gap(fifo_gap, fifo_gap.device_time_us), "DUPLICATE")

    def test_declarations_that_contradict_the_record_are_refused(self):
        ingestor = self.ingestor()
        chunk = StreamChunk.of(self.imu, 0, 100)
        ingestor.deliver_chunk(chunk, chunk.available_us)
        self.assertEqual(ingestor.deliver_gap(Gap("imu", 50, 60, 0, "claimed loss"), 0), "REJECTED:GAP_OVERLAPS_RECORD")
        self.assertEqual(ingestor.deliver_gap(Gap("imu", 200, 210, 0, "declared loss"), 0), "ACCEPTED")
        carrying = StreamChunk.of(self.imu, 180, 220)
        self.assertEqual(ingestor.deliver_chunk(carrying, carrying.available_us), "REJECTED:CONFLICTS_DECLARED_GAP")
        self.assertEqual(ingestor.deliver_gap(Gap("imu", 300, 290, 0, "reversed"), 0), "REJECTED:MALFORMED")
        self.assertEqual(ingestor.deliver_gap(Gap("eeg", 0, 1, 0, "unknown"), 0), "REJECTED:UNKNOWN_STREAM")

    def test_capacity_bounds_memory_and_every_refused_sample_is_declared_lost(self):
        ingestor = self.ingestor(capacity={"eda": 10**6, "ppg": 10**6, "imu": 1000, "sync": 10**6})
        outcomes = {ingestor.deliver_chunk(c, c.available_us) for c in chunks(self.imu, 300)}
        self.assertIn("LOST_TO_CAPACITY", outcomes)
        self.assertEqual(len(ingestor.view().streams["imu"]), 1000)
        (gap,) = ingestor.gaps
        self.assertEqual((gap.first_sequence, gap.last_sequence), (1000, len(self.imu) - 1))
        self.assertTrue(gap.cause.startswith("HOST_BUFFER_FULL"))
        self.assertEqual(ingestor.lost_to_capacity["imu"], len(self.imu) - 1000)

    def test_host_receipt_delays_availability_and_never_moves_sample_time(self):
        ingestor = self.ingestor(stamp_host_availability=True)
        chunk = StreamChunk.of(self.imu, 0, 400)
        ingestor.deliver_chunk(chunk, chunk.available_us + 500_000)
        stored = ingestor.view().streams["imu"]
        self.assertTrue(np.array_equal(stored.device_time_us, chunk.device_time_us))
        self.assertTrue(np.array_equal(stored.available_us, chunk.available_us + 500_000))
        first_receipt = int(chunk.available_us[0]) + 500_000
        self.assertEqual(len(ingestor.view(first_receipt - 1).streams["imu"]), 0)
        self.assertEqual(len(ingestor.view(first_receipt).streams["imu"]), 1)

    def test_without_host_receipt_a_late_delivery_would_rewrite_what_a_past_view_held(self):
        ppg = self.raw.streams["ppg"]
        t = int(ppg.available_us[2000])
        early, late = StreamChunk.of(ppg, 0, 1500), StreamChunk.of(ppg, 1500, 2001)
        for stamp, expect_stable in ((False, False), (True, True)):
            with self.subTest(host_receipt=stamp):
                ingestor = self.ingestor(stamp_host_availability=stamp)
                ingestor.deliver_chunk(early, early.available_us)
                before = len(ingestor.view(t).streams["ppg"])
                ingestor.deliver_chunk(late, t + 1_000_000)  # arrives a second after the view was taken
                after = len(ingestor.view(t).streams["ppg"])
                self.assertEqual(before == after, expect_stable)

    def test_events_are_deduplicated_and_validated(self):
        ingestor = self.ingestor()
        event = DeviceEvent("protocol_events", 0, "PHASE_START:REST_BASELINE", 10)
        self.assertEqual(ingestor.deliver_event(event, 10), "ACCEPTED")
        self.assertEqual(ingestor.deliver_event(event, 11), "DUPLICATE")
        self.assertEqual(ingestor.deliver_event(replace(event, device_time_us=12), 12), "REJECTED:CONFLICTING_RETRANSMISSION")
        self.assertEqual(ingestor.deliver_event(DeviceEvent("x", 0, "K", 1, (("v", float("nan")),)), 1), "REJECTED:MALFORMED")


class LinkMonitorTest(unittest.TestCase):
    def test_transitions_are_stamped_when_their_thresholds_were_crossed(self):
        monitor = LinkMonitor(500_000, 2_000_000)
        self.assertEqual([e.kind for e in monitor.delivered(1_000_000)], ["LINK:LIVE"])
        self.assertEqual(monitor.tick(1_400_000), [])
        crossed = monitor.tick(5_000_000)
        self.assertEqual([(e.kind, e.device_time_us) for e in crossed],
                         [("LINK:STALE", 1_500_000), ("LINK:DISCONNECTED", 3_000_000)])
        (back,) = monitor.delivered(6_000_000)
        self.assertEqual((back.kind, back.attribute("silence_us"), monitor.state), ("LINK:RECONNECTED", 5_000_000, "LIVE"))
        self.assertTrue(all(e.stream_id == LINK_STREAM for e in monitor.events))

    def test_continuous_delivery_never_looks_silent_and_a_gap_inside_a_batch_is_found(self):
        monitor = LinkMonitor(500_000, 2_000_000)
        self.assertEqual([e.kind for e in monitor.delivered_many(np.arange(0, 10_000_000, 2_500))], ["LINK:LIVE"])
        gapped = LinkMonitor(500_000, 2_000_000)
        times = np.concatenate([np.arange(0, 1_000_000, 2_500), np.arange(4_000_000, 5_000_000, 2_500)])
        self.assertEqual([e.kind for e in gapped.delivered_many(times)],
                         ["LINK:LIVE", "LINK:STALE", "LINK:DISCONNECTED", "LINK:RECONNECTED"])
        self.assertEqual(gapped.events[1].device_time_us, 997_500 + 500_000)

    def test_a_transport_error_disconnects_at_once(self):
        monitor = LinkMonitor()
        monitor.delivered(0)
        self.assertEqual([(e.kind, e.device_time_us) for e in monitor.failed(100)], [("LINK:DISCONNECTED", 100)])
        self.assertEqual(monitor.failed(200), [])
        with self.assertRaises(ValueError):
            LinkMonitor(2_000_000, 1_000_000)


class LiveLoopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = run_session(SessionConfig())

    def test_a_clean_link_reproduces_the_direct_run_exactly(self):
        source, result, _, _ = live_run(FaultPlan())
        self.assertEqual([e.comparable() for e in result.evaluations], [e.comparable() for e in self.ref.evaluations])
        for name in self.ref.raw.streams:
            self.assertTrue(same_stream(result.raw.streams[name], self.ref.raw.streams[name]), name)
        self.assertEqual(sorted(result.raw.gaps, key=lambda g: g.device_time_us), self.ref.raw.gaps)
        self.assertEqual([e for e in result.raw.events if e.stream_id != LINK_STREAM], self.ref.raw.events)
        self.assertEqual([e.kind for e in result.raw.events if e.stream_id == LINK_STREAM], ["LINK:LIVE"])
        self.assertEqual(source.report()["faults"], 0)

    def test_corrupted_and_repeated_chunks_change_nothing_but_the_fault_log(self):
        plan = FaultPlan(corrupt=(("ppg", 60.0, "FLOAT_VALUES"), ("imu", 70.0, "REVERSED_TIME"),
                                  ("eda", 80.0, "OUT_OF_RANGE"), ("sync", 90.0, "UNKNOWN_STREAM")),
                         retransmit=(("imu", 100.0), ("ppg", 101.0)))
        source, result, _, _ = live_run(plan)
        self.assertEqual([e.comparable() for e in result.evaluations], [e.comparable() for e in self.ref.evaluations])
        report = source.report()
        self.assertEqual(report["faults_by_kind"], {"MALFORMED": 3, "UNKNOWN_STREAM": 1})
        self.assertEqual(report["outcomes"]["DUPLICATE"], 2)

    def test_an_outage_is_recorded_as_silence_and_loss_never_as_a_calm_subject(self):
        source, result, _, _ = live_run(FaultPlan(outages=((244.0, 258.0),)))
        anchor = result.raw.events_of("PHASE_START:")[0].device_time_us
        self.assertEqual(source.report()["link_states"], ["LINK:LIVE", "LINK:STALE", "LINK:DISCONNECTED", "LINK:RECONNECTED"])
        host_gaps = [g for g in result.raw.gaps if g.cause.startswith("UNDECLARED")]
        self.assertEqual(sorted(g.stream_id for g in host_gaps), ["eda", "imu", "ppg", "sync"])
        blind = [e for e in result.evaluations if 245 <= (e.input_cutoff_us - anchor) / 1e6 <= 258]
        self.assertTrue(blind and all(e.gate_reasons for e in blind), "every evaluation that could not see must hold")
        self.assertIn("DATA_STALE", {r for e in blind for r in e.gate_reasons})
        acted = [e for e in result.evaluations if e.action in ("START_PACED_BREATHING", "STOP_RELEASED")]
        self.assertTrue(all(not e.gate_reasons for e in acted))
        self.assertIn("STOP_QUALITY_LOST", [e.action for e in result.evaluations], "a loop that cannot observe must stop")

    def test_a_starved_stream_never_drives_a_decision(self):
        capacity = {"eda": 10**6, "ppg": 10**6, "imu": 60_000, "sync": 10**6}
        source, result, _, _ = live_run(FaultPlan(), capacity=capacity)
        self.assertEqual([e.action for e in result.evaluations if e.decision_id], [])
        self.assertIn("DATA_STALE", {r for e in result.evaluations for r in e.gate_reasons})
        self.assertEqual(source.report()["lost_to_capacity"]["imu"], len(self.ref.raw.streams["imu"]) - 60_000)


class EvidenceThroughTheBoundaryTest(unittest.TestCase):
    """A session that crossed a damaged link exports, audits REPLAY_MATCH, and replays from its recording."""

    @classmethod
    def setUpClass(cls):
        config = replace(SessionConfig(), acquisition=ACQUISITION_FLAGS)
        plan = FaultPlan(stalls=((248.0, 256.0),), outages=((290.0, 297.0),), corrupt=(("ppg", 100.0, "OUT_OF_RANGE"),))
        cls.source, cls.result, twin, rig = live_run(plan, config)
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "run"
        export_run(session_run(config, cls.result, twin, rig), cls.out, None, with_report=False,
                   extra_documents={"ingestion.json": dumps(cls.source.report())})
        cls.audit = audit_run(cls.out)
        cls.records = load_session(cls.out / "session.ndjson")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_independent_audit_rebuilds_and_replays_the_whole_session(self):
        self.assertEqual(self.audit["replay_status"], "REPLAY_MATCH", json.dumps(self.audit["checks"], indent=1))
        self.assertTrue(self.audit["valid"])

    def test_the_record_names_its_acquisition_path_and_keeps_the_link_history(self):
        header = self.records[0]
        for flag in ACQUISITION_FLAGS:
            self.assertIn(flag, header["status_flags"])
        links = [r for r in self.records if "LINK_STATE" in r["status_flags"]]
        self.assertEqual([next(f for f in r["status_flags"] if f.startswith("EVENT_KIND:")) for r in links],
                         ["EVENT_KIND:LINK:" + s for s in ("LIVE", "STALE", "DISCONNECTED", "RECONNECTED", "STALE",
                                                           "DISCONNECTED", "RECONNECTED")])
        causes = [r["cause"] for r in self.records if r["record_type"] == "GAP"]
        self.assertTrue(any(c.startswith("UNDECLARED_SEQUENCE_DISCONTINUITY") for c in causes))
        ingestion = json.loads((self.out / "ingestion.json").read_text())
        self.assertEqual(ingestion["faults_by_kind"]["MALFORMED"], 1)

    def test_stale_evidence_was_held_and_never_acted_on(self):
        reasons = {r for e in self.result.evaluations for r in e.gate_reasons}
        self.assertIn("DATA_STALE", reasons)
        for e in self.result.evaluations:
            if e.action == "START_PACED_BREATHING":
                self.assertEqual(e.gate_reasons, [])

    def test_the_recording_replays_every_decision_and_command(self):
        recorded = RecordedSource(self.out)
        actuator = NullActuator()
        result = run_closed_loop(recorded, actuator, ClosedLoopController(recorded.controller_config))
        comparison = recorded.compare(result, actuator)
        self.assertTrue(comparison["decisions_match"] and comparison["commands_match"], comparison)
        self.assertEqual(comparison["evaluations_replayed"], len(self.result.evaluations))
        self.assertEqual({s.provenance for s in recorded.capabilities().signals}, {"SIMULATED"})

    def test_a_tampered_recording_is_not_replayed(self):
        copy = self.tmp / "tampered"
        shutil.copytree(self.out, copy)
        path = copy / "raw/eda.csv.gz"
        lines = gzip.decompress(path.read_bytes()).decode("ascii").splitlines()
        fields = lines[100].split(",")
        fields[-1] = str(int(fields[-1]) + 1)
        lines[100] = ",".join(fields)
        path.write_bytes(gzip.compress(("\n".join(lines) + "\n").encode("ascii"), mtime=0))
        with self.assertRaisesRegex(ValueError, "unverified data is not replayed"):
            RecordedSource(copy)

    def test_the_manifest_records_software_revision_and_configuration_hash(self):
        manifest = json.loads((self.out / "manifest.json").read_text())
        self.assertIn("git_commit", manifest["software_revision"])
        self.assertEqual(len(manifest["config_sha256"]), 64)
        self.assertEqual(manifest["config"]["acquisition"], list(ACQUISITION_FLAGS))
        self.assertIn("ingestion.json", manifest["artifacts"])


class PumpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = run_session(SHORT).raw

    def test_a_full_queue_drops_the_newest_and_declares_each_drop_lost(self):
        imu = self.raw.streams["imu"]
        pieces = chunks(imu, 400)
        ingestor = Ingestor(self.raw.descriptors)

        async def link():
            for chunk in pieces:  # a burst: no awaits, so the consumer cannot keep up
                yield chunk.available_us, chunk

        report = asyncio.run(pump(link(), ingestor, max_queue=3))
        self.assertEqual((report.received, report.dropped_chunks), (len(pieces), len(pieces) - 3))
        self.assertEqual(len(ingestor.view().streams["imu"]), 1200)
        covered = sorted((g.first_sequence, g.last_sequence) for g in ingestor.gaps)
        self.assertEqual((covered[0][0], covered[-1][1]), (1200, len(imu) - 1))
        self.assertTrue(all(g.cause.startswith("HOST_QUEUE_FULL") for g in ingestor.gaps))

    def test_a_graceful_stop_ingests_everything_already_received(self):
        ppg = self.raw.streams["ppg"]
        pieces = chunks(ppg, 500)
        ingestor = Ingestor(self.raw.descriptors)
        stop = asyncio.Event()

        async def link():
            for i, chunk in enumerate(pieces):
                if i == 5:
                    stop.set()
                yield chunk.available_us, chunk
                await asyncio.sleep(0)

        report = asyncio.run(pump(link(), ingestor, max_queue=4, stop=stop))
        self.assertEqual((report.dropped_chunks, report.received), (0, 5))
        self.assertEqual(len(ingestor.view().streams["ppg"]), 2500)
        with self.assertRaises(ValueError):
            asyncio.run(pump(link(), ingestor, max_queue=0))


class RefusalSessionTest(unittest.TestCase):
    CAPS = Capabilities("example-gadget", True, "RESPONDING", (), (ActuatorCapability("chat", "OPERATOR_CHANNEL", ("ACK",)),),
                        "1.0", "example host", "none held", ("delivers no streams",))

    def test_a_refusal_is_an_ordinary_contract_valid_session(self):
        problems = ["stream eda is missing", "no protocol marker anchors the evaluation schedule"]
        events = [DeviceEvent("example_link", 0, "LINK_STATE:SERVICE_RESPONDING", 1200, (("round_trip_us", 800.0),))]
        records = refusal_session(self.CAPS, problems, events, ControllerConfig(), "ATTEMPT-1", "RAW_MEASURED")
        validate_session(records)
        card = passport(records, {"TERMINATED": "INSUFFICIENT_EVIDENCE"})
        self.assertEqual((card["MODE"], card["INPUT"], card["HARDWARE"], card["EVALUATIONS"].split()[0]),
                         ("LIVE", "no streams", "example host", "0"))
        self.assertEqual([r["cause"] for r in records if r["record_type"] == "FAULT"], problems)
        self.assertIn("TERMINATED:INSUFFICIENT_EVIDENCE", records[-1]["status_flags"])
        with tempfile.TemporaryDirectory() as tmp:
            manifest = write_refusal(Path(tmp), records, self.CAPS)
            for name, entry in manifest["artifacts"].items():
                data = (Path(tmp) / name).read_bytes()
                self.assertEqual(len(data), entry["bytes"])
            self.assertEqual(len(load_session(Path(tmp) / "session.ndjson")), len(records))

    def test_a_refusal_needs_reasons_and_a_real_or_simulated_provenance(self):
        with self.assertRaises(ValueError):
            refusal_session(self.CAPS, [], [], ControllerConfig(), "X", "SIMULATED")
        with self.assertRaises(ValueError):
            refusal_session(self.CAPS, ["reason"], [], ControllerConfig(), "X", "TEST")


class SessionContractGapTest(unittest.TestCase):
    """Two latent defects found while building the boundary, now fixed and pinned."""

    @staticmethod
    def gap(first: int, last: int, t: int) -> dict:
        return seal_record({"schema_version": "2.2.0", "record_type": "GAP", "provenance": "SIMULATED",
                            "device_time_start_us": t, "device_time_end_us": t, "status_flags": [], "stream_id": "ppg",
                            "dropped_first_sequence": first, "dropped_last_sequence": last, "cause": "test loss"})

    def test_separate_losses_on_a_bundle_stream_are_valid_in_any_declaration_order(self):
        validate_session([self.gap(10, 20, 1), self.gap(50, 60, 2)])
        validate_session([self.gap(50, 60, 1), self.gap(10, 20, 2)])
        with self.assertRaisesRegex(SessionRecordError, "overlaps"):
            validate_session([self.gap(10, 20, 1), self.gap(15, 30, 2)])

    def test_the_sensor_loss_scenario_now_survives_its_own_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = run_session(SCENARIOS["sensor_loss"].configure(7))
            self.assertEqual(len(run.raw.gaps), 2, "FIFO overflow and head detach: two losses on one stream")
            export_run(run, Path(tmp), None, with_report=False)
            self.assertEqual(audit_run(Path(tmp))["replay_status"], "REPLAY_MATCH")


if __name__ == "__main__":
    unittest.main()
