"""Physiology twin, Rev B sensor models, pipeline, closed loop, evidence export, and audit."""

from dataclasses import replace
import gzip
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from models.physiology.controller import ClosedLoopController, replay
from models.physiology.dsp import (contiguous_runs, filter_zero_phase, fir_bandpass, fir_lowpass, gaussian_lowpass, mask_runs,
                                   parabolic_peak_offset)
from models.physiology.experiment import SessionConfig, run_session
from models.physiology.pipeline import _slope_bumps, eda_conductance_us, fit_clock, moving_average
from models.physiology.sensors import (EDA_BITS, EDA_EXCITATION_V, EDA_PGA_GAIN, EDA_SERIES_LIMIT_OHM, EDA_VREF_V,
                                       RigConfig, descriptors)
from models.physiology.streams import Stream
from models.physiology.twin import PhysiologyTwin, TwinConfig
from models.physiology.validation import score
from models.session_records import load_session, seal_record
from tools.run_physiology_twin import export_run
from models.physiology.audit import audit_run


class DSPTest(unittest.TestCase):
    def test_zero_phase_filter_does_not_shift_a_peak(self):
        x = np.zeros(2001)
        x[1000] = 1.0
        y = filter_zero_phase(x, fir_lowpass(5.0, 100.0, 201))
        self.assertEqual(int(np.argmax(y)), 1000)
        self.assertAlmostEqual(float(y.sum()), 1.0, places=6)

    def test_bandpass_removes_dc_and_keeps_passband(self):
        t = np.arange(0, 60, 0.01)
        taps = fir_bandpass(0.5, 8.0, 100.0, 601)
        dc = filter_zero_phase(np.full(len(t), 5.0), taps)
        tone = filter_zero_phase(np.sin(2 * np.pi * 1.5 * t), taps)
        self.assertLess(np.max(np.abs(dc[700:-700])), 1e-3)
        self.assertAlmostEqual(np.max(np.abs(tone[700:-700])), 1.0, delta=0.02)

    def test_runs_and_peak_interpolation(self):
        self.assertEqual(contiguous_runs(np.array([3, 4, 5, 9, 10])), [(0, 3), (3, 5)])
        self.assertEqual(mask_runs(np.array([0, 1, 1, 0, 1], dtype=bool)), [(1, 3), (4, 5)])
        self.assertAlmostEqual(parabolic_peak_offset(1.0, 2.0, 1.0), 0.0)
        self.assertGreater(parabolic_peak_offset(1.0, 2.0, 1.9), 0.0)


class SensorModelTest(unittest.TestCase):
    def test_eda_front_end_inverts_exactly(self):
        conductance = np.array([0.5, 2.0, 4.0, 12.0, 25.0])
        g = conductance * 1e-6
        v = EDA_EXCITATION_V * EDA_SERIES_LIMIT_OHM * g / (1 + EDA_SERIES_LIMIT_OHM * g)
        codes = np.round(v * EDA_PGA_GAIN / EDA_VREF_V * 2 ** (EDA_BITS - 1))
        recovered = eda_conductance_us(codes, descriptors(RigConfig())["eda"])
        np.testing.assert_allclose(recovered, conductance, rtol=1e-5)

    def test_unobservable_fifo_overflow_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "OVF_COUNTER"):
            RigConfig(ppg_fifo_stall_s=0.6)

    def test_clock_fit_recovers_drift_and_offset(self):
        lab = np.arange(1, 301)
        device = np.floor((7.0 + lab * (1 + 40e-6)) * 1e6).astype(np.int64)
        fit = fit_clock(Stream("sync", np.arange(300), device, {"lab_pulse_index": lab}))
        self.assertAlmostEqual(fit.ppm, 40.0, delta=0.01)
        self.assertLess(abs(fit.offset_us - 7e6), 2.0)

    def test_twin_config_rejects_gaps_in_protocol(self):
        phases = TwinConfig().phases
        with self.assertRaises(ValueError):
            TwinConfig(phases=(phases[0], phases[2], *phases[3:]))


class SCRDetectorTest(unittest.TestCase):
    @staticmethod
    def bateman(t, onset, amplitude, tau1=0.7, tau2=2.8):
        peak = math.log(tau2 / tau1) * tau1 * tau2 / (tau2 - tau1)
        norm = math.exp(-peak / tau2) - math.exp(-peak / tau1)
        tau = np.clip(t - onset, 0, None)
        return np.where(t >= onset, amplitude * (np.exp(-tau / tau2) - np.exp(-tau / tau1)) / norm, 0.0)

    def detect(self, signal, fs=64.0):
        smooth = filter_zero_phase(signal, gaussian_lowpass(1.2, fs))
        slope = moving_average(np.gradient(smooth) * fs, int(fs * 0.25))
        return _slope_bumps(slope, fs)

    def test_isolated_response_amplitude_and_onset(self):
        fs = 64.0
        t = np.arange(0, 40, 1 / fs)
        found = self.detect(4.0 + self.bateman(t, 12.0, 0.30), fs)
        self.assertEqual(len(found), 1)
        onset, _, amplitude = found[0]
        self.assertAlmostEqual(t[onset], 12.0, delta=0.25)
        self.assertAlmostEqual(amplitude, 0.30, delta=0.03)

    def test_response_riding_on_a_decay_is_detected(self):
        fs = 64.0
        t = np.arange(0, 45, 1 / fs)
        # The second response never turns the conductance upward: only the
        # slope's transient excess over the recovering baseline reveals it.
        signal = 4.0 + self.bateman(t, 10.0, 1.2) + self.bateman(t, 15.0, 0.06)
        self.assertTrue(np.all(np.gradient(signal)[int(15.0 * fs):int(17.5 * fs)] < 0))
        found = self.detect(signal, fs)
        self.assertEqual(len(found), 2, found)
        self.assertAlmostEqual(t[found[0][0]], 10.0, delta=0.1)
        self.assertAlmostEqual(found[0][2], 1.2, delta=0.02)
        self.assertAlmostEqual(t[found[1][0]], 15.0, delta=0.1)

    def test_smoothing_does_not_ring_into_false_responses(self):
        fs = 64.0
        t = np.arange(0, 40, 1 / fs)
        found = self.detect(4.0 + self.bateman(t, 12.0, 2.0), fs)
        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0][2], 2.0, delta=0.02)


class TwinCausalityTest(unittest.TestCase):
    def test_arms_share_noise_until_the_first_cue(self):
        active = run_session(SessionConfig(twin=TwinConfig(seed=3)))
        sham = run_session(SessionConfig(twin=TwinConfig(seed=3), actuate=False))
        first = min(o.truth["physical_onset_true_s"] for o in active.haptic if "physical_onset_true_s" in o.truth)
        a, s = active.twin.truth(), sham.twin.truth()
        before = np.array(a["t_s"]) < first
        for key in ("hr_bpm", "arousal", "spo2_pct", "scl_tonic_us", "resp_rate_bpm"):
            np.testing.assert_array_equal(np.array(a[key])[before], np.array(s[key])[before])
        self.assertFalse(np.array_equal(np.array(a["arousal"]), np.array(s["arousal"])))
        self.assertEqual([e.decision_id for e in sham.evaluations if e.action == "START_PACED_BREATHING"], ["PBR-1"])
        self.assertFalse(any(e.kind == "HAPTIC_ELECTRICAL_ONSET" for e in sham.raw.events))

    def test_twin_refuses_cues_into_generated_physiology(self):
        twin = PhysiologyTwin(TwinConfig())
        twin.advance_to(30.0)
        from models.physiology.twin import HapticCue
        with self.assertRaises(ValueError):
            twin.add_cues([HapticCue(1, 0, 10.0, 10.0, True)])


class ClosedLoopSessionTest(unittest.TestCase):
    """One full 6-minute closed-loop session, exported and independently audited."""

    @classmethod
    def setUpClass(cls):
        cls.session = run_session(SessionConfig())
        cls.truth = cls.session.truth()
        cls.card = score(cls.session, cls.truth)
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "run"
        export_run(cls.session, cls.out, counterfactual=None, with_report=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_truth_check_passes(self):
        failed = [c for c in self.card["checks"] if not c["passed"]]
        self.assertEqual(failed, [])
        self.assertGreaterEqual(len(self.card["checks"]), 19)

    def test_closed_loop_starts_and_releases_guidance(self):
        actions = [(e.action, e.decision_id) for e in self.session.evaluations if e.decision_id]
        self.assertEqual(actions, [("START_PACED_BREATHING", "PBR-1"), ("STOP_RELEASED", "PBR-1-STOP")])
        start = next(e for e in self.session.evaluations if e.decision_id == "PBR-1")
        armed = next(e.device_time_us for e in self.session.raw.events if e.kind == "PHASE_START:RECOVERY")
        self.assertGreater(start.device_time_us, armed)

    def test_decisions_replay_bit_for_bit(self):
        replayed = replay(self.session.raw, self.session.config.controller, self.session.evaluation_end_us)
        self.assertEqual([e.comparable() for e in replayed], [e.comparable() for e in self.session.evaluations])

    def test_future_samples_cannot_change_a_decision(self):
        config = self.session.config.controller
        decision = next(e for e in self.session.evaluations if e.decision_id == "PBR-1")
        cutoff = decision.device_time_us - int(config.decision_margin_s * 1e6)
        raw = self.session.raw.until(decision.device_time_us)
        tampered_streams = {}
        for name, stream in raw.streams.items():
            late = stream.device_time_us > cutoff
            columns = {k: np.where(late, v * 0 + 12345, v) for k, v in stream.columns.items()}
            tampered_streams[name] = Stream(name, stream.sequence, stream.device_time_us, columns)
        tampered = replace(raw, streams=tampered_streams)
        controller = ClosedLoopController(config)
        # Warm the controller state exactly as the online loop did.
        for ev in self.session.evaluations:
            if ev.device_time_us >= decision.device_time_us:
                break
            controller.evaluate(self.session.raw.until(ev.device_time_us), ev.device_time_us)
        again = controller.evaluate(tampered, decision.device_time_us)
        self.assertEqual(again.comparable(), decision.comparable())

    def test_session_passes_the_existing_contract_auditor(self):
        records = load_session(self.out / "session.ndjson")
        types = {r["record_type"] for r in records}
        self.assertTrue({"SESSION_HEADER", "STREAM_DESCRIPTOR", "CLOCK_MAPPING", "GAP", "MODEL_RESULT",
                         "INTERVENTION", "SESSION_TRAILER"} <= types)
        self.assertNotIn("RAW_MEASURED", {r["provenance"] for r in records})
        gap = next(r for r in records if r["record_type"] == "GAP")
        lost = self.truth["timing"]["ppg_lost_sequences"][0]
        self.assertEqual([gap["dropped_first_sequence"], gap["dropped_last_sequence"]], lost)
        self.assertIn("OVF_COUNTER", gap["cause"])

    def test_independent_audit_passes(self):
        result = audit_run(self.out)
        self.assertTrue(result["valid"], json.dumps(result["checks"], indent=1))
        self.assertFalse(result["authentication_verified"])

    def test_audit_detects_a_changed_raw_sample(self):
        copy = self.tmp / "tampered-raw"
        shutil.copytree(self.out, copy)
        path = copy / "raw" / "eda.csv.gz"
        lines = gzip.decompress(path.read_bytes()).decode().splitlines()
        seq, t, code = lines[5000].split(",")
        lines[5000] = f"{seq},{t},{int(code) + 40000}"
        path.write_bytes(gzip.compress(("\n".join(lines) + "\n").encode(), mtime=0))
        result = audit_run(copy)
        self.assertFalse(result["valid"])
        self.assertFalse(result["checks"]["artifact_hashes"]["passed"])
        self.assertFalse(result["checks"]["raw_content_bound"]["passed"])

    def test_audit_detects_a_rewritten_decision_even_with_a_valid_crc(self):
        copy = self.tmp / "tampered-decision"
        shutil.copytree(self.out, copy)
        path = copy / "session.ndjson"
        records = [json.loads(line) for line in path.read_text().splitlines()]
        for i, record in enumerate(records):
            if record.get("decision_id") == "PBR-1" and record["record_type"] == "MODEL_RESULT":
                record["payload"]["arousal_index"] = 1.5  # below trigger: decision no longer justified
                records[i] = seal_record(record)
        path.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in records))
        result = audit_run(copy)
        self.assertTrue(result["checks"]["session_contract"]["passed"])
        self.assertFalse(result["checks"]["decisions_replayed"]["passed"])

    def test_export_is_byte_deterministic(self):
        again = self.tmp / "again"
        export_run(run_session(SessionConfig()), again, counterfactual=None, with_report=True)
        for name in ("session.ndjson", "analysis.json", "scorecard.json", "report.html", "manifest.json",
                     "raw/ppg.csv.gz", "raw/imu.csv.gz"):
            self.assertEqual((self.out / name).read_bytes(), (again / name).read_bytes(), name)

    def test_report_is_self_contained(self):
        html = (self.out / "report.html").read_text(encoding="utf-8")
        self.assertIn("<title>CIRCLE Closed-Loop Session</title>", html)
        self.assertIn('id="session-data"', html)
        self.assertNotIn("<script src=", html)


if __name__ == "__main__":
    unittest.main()
