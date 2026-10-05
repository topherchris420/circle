"""The closed loop's boundary: the input contract, actuation targets, and which modules may import which.

Every source, the twin included, reaches the controller through
models/physiology/loop.py. These tests try to get past that boundary: a source
missing what the pipeline reads, an actuator aimed at hardware, a person, or an
operator channel, a source whose record would grow underneath a decision, and
core modules that import an adapter.
"""

from __future__ import annotations

import ast
from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
import unittest

from models.physiology.controller import ClosedLoopController, ControllerConfig
from models.physiology.experiment import SessionConfig, TwinHapticActuator, TwinSource, run_session
from models.physiology.loop import (CLOSED_LOOP_TARGETS, REQUIRED_DESCRIPTOR_KEYS, ActuationRefused, ActuatorCapability,
                                    Capabilities, InsufficientEvidence, NullActuator, actuation_refusal,
                                    capability_problems, input_problems, run_closed_loop)
from models.physiology.sensors import SensorRig
from models.physiology.streams import STREAM_COLUMNS, RawSession
from models.physiology.twin import DEFAULT_MOTION, PhysiologyTwin, TwinConfig
from tools.check_module_registry import registry_errors

ROOT = Path(__file__).resolve().parents[1]
SHORT = SessionConfig(twin=TwinConfig(duration_s=130.0, motion=DEFAULT_MOTION[:1]))


def twin_source(config: SessionConfig = SHORT) -> tuple[TwinSource, TwinHapticActuator]:
    twin = PhysiologyTwin(config.twin)
    rig = SensorRig(twin, config.rig)
    return TwinSource(twin, rig), TwinHapticActuator(twin, rig, config.actuate)


class SpySource:
    """Wraps a source and records which boundary methods the loop called."""

    def __init__(self, inner, complete_lag_us: int = 0) -> None:
        self.inner, self.lag, self.calls = inner, complete_lag_us, []

    def capabilities(self) -> Capabilities:
        return self.inner.capabilities()

    def start(self):
        self.calls.append("start")
        return self.inner.start()

    def advance(self, t):
        self.calls.append("advance")
        return self.inner.advance(t)

    def view(self, t) -> RawSession:
        return self.inner.view(t)

    def complete_through_us(self) -> float:
        return self.inner.complete_through_us() - self.lag

    def finish(self) -> RawSession:
        return self.inner.finish()


class InputContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = run_session(SHORT).raw

    def test_twin_record_satisfies_the_contract(self):
        self.assertEqual(input_problems(self.raw), [])

    def test_each_missing_requirement_is_named(self):
        cases = {
            "stream ppg is missing": replace(self.raw, streams={k: v for k, v in self.raw.streams.items() if k != "ppg"}),
            "lacks columns ['ir_counts']": replace(self.raw, streams={**self.raw.streams, "ppg": replace(
                self.raw.streams["ppg"], columns={"red_counts": self.raw.streams["ppg"].columns["red_counts"]})}),
            "stream eda has no descriptor": replace(self.raw, descriptors={k: v for k, v in self.raw.descriptors.items()
                                                                           if k != "eda"}),
            "descriptor lacks ['accel_lsb_per_g']": replace(self.raw, descriptors={**self.raw.descriptors, "imu": {
                k: v for k, v in self.raw.descriptors["imu"].items() if k != "accel_lsb_per_g"}}),
        }
        for expected, session in cases.items():
            with self.subTest(expected=expected):
                problems = input_problems(session)
                self.assertTrue(any(expected in p for p in problems), problems)

    def test_contract_covers_every_stream_the_pipeline_reads(self):
        self.assertEqual(set(REQUIRED_DESCRIPTOR_KEYS), set(STREAM_COLUMNS))
        self.assertEqual(len(input_problems(RawSession({}, {}))), len(STREAM_COLUMNS))

    def test_declared_capabilities_face_the_same_contract(self):
        source, _ = twin_source()
        self.assertEqual(capability_problems(source.capabilities()), [])
        nothing = Capabilities("nothing", False, "ABSENT", (), (), None, "none", "none", ())
        self.assertEqual(len(capability_problems(nothing)), len(STREAM_COLUMNS))

    def test_twin_declares_simulated_signals_and_actuation_evidence(self):
        caps = twin_source()[0].capabilities()
        self.assertEqual([s.stream_id for s in caps.signals], list(STREAM_COLUMNS))
        self.assertEqual({s.provenance for s in caps.signals}, {"SIMULATED"})
        self.assertEqual(caps.sampling["imu"], 400.0)
        (haptic,) = caps.actuators
        self.assertEqual(haptic.target, "SIMULATED")
        self.assertIn("HAPTIC_PHYSICAL_OBSERVATION", haptic.evidence)
        json.dumps(caps.to_dict())


class ActuationTargetTest(unittest.TestCase):
    def test_only_simulation_and_no_actuation_may_receive_cues(self):
        self.assertEqual(CLOSED_LOOP_TARGETS, ("SIMULATED", "NONE"))
        for target in CLOSED_LOOP_TARGETS:
            self.assertIsNone(actuation_refusal(target))

    def test_hardware_and_human_targets_cite_the_open_review_gates(self):
        gates = json.loads((ROOT / "hardware/review-gates.json").read_text(encoding="utf-8"))["gates"]
        for target, needed in (("HARDWARE_BENCH", "POWERED_BENCH_TEST"), ("HUMAN_CONNECTED", "HUMAN_CONNECTION")):
            with self.subTest(target=target):
                reason = actuation_refusal(target)
                self.assertIn(needed, reason)
                self.assertIn("never grants", reason)
                for gate in (g["id"] for g in gates if needed in g["blocks"] and g["status"] != "CLOSED"):
                    self.assertIn(gate, reason)

    def test_closed_review_gates_still_do_not_authorize_software_actuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            closed = Path(tmp) / "gates.json"
            closed.write_text(json.dumps({"gates": [{"id": "X", "blocks": ["HUMAN_CONNECTION"], "status": "CLOSED"}]}))
            self.assertIn("human sign-off", actuation_refusal("HUMAN_CONNECTED", closed))
            self.assertIn("fails closed", actuation_refusal("HARDWARE_BENCH", Path(tmp) / "missing.json"))

    def test_operator_channels_and_unknown_targets_are_refused(self):
        self.assertIn("operator channel", actuation_refusal("OPERATOR_CHANNEL"))
        self.assertIn("unknown", actuation_refusal("LASER"))
        with self.assertRaises(ValueError):
            ActuatorCapability("x", "LASER", ())

    def test_refused_actuator_stops_the_loop_before_any_acquisition(self):
        source, _ = twin_source()
        spy = SpySource(source)

        class Bench:
            target = "HARDWARE_BENCH"

            def execute(self, *args):
                raise AssertionError("a refused actuator must never execute")

        with self.assertRaises(ActuationRefused):
            run_closed_loop(spy, Bench(), ClosedLoopController(SHORT.controller))
        self.assertEqual(spy.calls, [])


class LoopBoundaryTest(unittest.TestCase):
    def test_source_without_streams_or_markers_is_refused_with_every_reason(self):
        class Empty:
            def capabilities(self):
                return Capabilities("empty", None, "NONE", (), (), None, "none", "none", ())

            def start(self):
                return None

            def advance(self, t):
                raise AssertionError("a refused source must never be advanced")

            def view(self, t):
                return RawSession({}, {})

            def complete_through_us(self):
                return math.inf

            def finish(self):
                return RawSession({}, {})

        controller = ClosedLoopController(ControllerConfig())
        with self.assertRaises(InsufficientEvidence) as caught:
            run_closed_loop(Empty(), NullActuator(), controller)
        self.assertEqual(len(caught.exception.problems), len(STREAM_COLUMNS) + 1)
        self.assertIn("no protocol marker anchors the evaluation schedule", caught.exception.problems)
        self.assertIsNone(controller.baseline)

    def test_a_record_that_could_still_grow_under_a_decision_stops_the_loop(self):
        source, actuator = twin_source()
        lagging = SpySource(source, complete_lag_us=2_000_000)
        with self.assertRaisesRegex(RuntimeError, "would miss samples"):
            run_closed_loop(lagging, actuator, ClosedLoopController(SHORT.controller))

    def test_null_actuator_records_cues_and_actuates_nothing(self):
        actuator = NullActuator()
        actuator.execute(10, 1, 0)
        self.assertEqual((actuator.target, actuator.commands), ("NONE", [(10, 1, 0)]))

    def test_twin_through_the_loop_with_no_actuation_logs_decisions_only(self):
        config = replace(SessionConfig(), actuate=True)
        twin = PhysiologyTwin(config.twin)
        rig = SensorRig(twin, config.rig)
        actuator = NullActuator()
        result = run_closed_loop(TwinSource(twin, rig), actuator, ClosedLoopController(config.controller))
        scheduled = sorted(c for ev in result.evaluations for c in ev.cues_device_us)
        self.assertGreater(len(scheduled), 0)
        self.assertEqual(sorted(c[0] for c in actuator.commands), scheduled)
        self.assertFalse(result.raw.events_of("HAPTIC_"), "no actuator ran, so no haptic event exists")


class ModuleBoundaryTest(unittest.TestCase):
    """The acquisition boundary never sees hidden truth; the core never imports a hardware adapter."""

    TRUTH = {"twin", "sensors", "validation", "experiment", "report", "scenarios"}

    def _imports(self, path: Path) -> list[str]:
        names = []
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
            elif isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
        return names

    def test_boundary_modules_never_import_the_twin_or_scoring(self):
        files = [ROOT / "models/physiology/loop.py", *sorted((ROOT / "models/acquisition").glob("*.py")),
                 *sorted((ROOT / "models/muse_gadget").glob("*.py"))]
        for path in files:
            for name in self._imports(path):
                with self.subTest(module=path.name, imports=name):
                    self.assertNotIn(name.split(".")[-1], self.TRUTH)

    def test_core_never_imports_the_muse_adapter(self):
        core = [*sorted((ROOT / "models/physiology").glob("*.py")), *sorted((ROOT / "models/acquisition").glob("*.py")),
                ROOT / "models/protocols.py", ROOT / "models/session_records.py"]
        for path in core:
            for name in self._imports(path):
                with self.subTest(module=path.name):
                    self.assertFalse(name.startswith("models.muse_gadget"), f"{path.name} imports {name}")

    def test_physiology_never_imports_acquisition(self):
        for path in sorted((ROOT / "models/physiology").glob("*.py")):
            for name in self._imports(path):
                with self.subTest(module=path.name):
                    self.assertFalse(name.startswith("models.acquisition"), f"{path.name} imports {name}")

    def test_the_boundary_diagram_is_rendered_and_names_the_refusal(self):
        import xml.etree.ElementTree as ET

        svg = (ROOT / "diagrams/acquisition-boundary.svg").read_text(encoding="utf-8")
        ET.fromstring(svg.encode("utf-8"))
        for term in ("ENGINEERING REVIEW ONLY", "Input contract", "Muse Gadget SDK", "Refused: session record",
                     "Actuation gate", "SIMULATED only", "Operator chat (outside)"):
            self.assertIn(term, svg)
        mermaid = (ROOT / "diagrams/acquisition-boundary.mmd").read_text(encoding="utf-8")
        for term in ("Input contract", "no physiological stream", "Refused", "SIMULATED or NONE", "outside the loop"):
            self.assertIn(term, mermaid)

    def test_capability_registry_names_the_new_modules_honestly(self):
        doc = json.loads((ROOT / "capabilities.json").read_text(encoding="utf-8"))
        self.assertEqual(registry_errors(doc), [])
        modules = {m["id"]: m for m in doc["modules"]}
        self.assertEqual(modules["acquisition_boundary"]["layer"], "INSTRUMENT_CORE")
        adapter = modules["muse_gadget_adapter"]
        self.assertEqual((adapter["layer"], adapter["removable"]), ("HARDWARE_ADAPTER", True))
        self.assertTrue(any("physiological" in claim for claim in adapter["not_claimed"]))


if __name__ == "__main__":
    unittest.main()
