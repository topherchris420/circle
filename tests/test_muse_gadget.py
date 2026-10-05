"""The Muse Gadget SDK adapter: exactly what the SDK supports, inside CIRCLE's boundaries.

The SDK delivers no physiological signal, so these tests demand that nothing in
the adapter ever offers one; that the closed loop refuses the gadget as a
source and keeps the refusal as a session; that the only output, a chat
message, stays an operator notification that can never carry a cue; and that
the only input, an invocation from the Muse, can at most produce a validated
proposal that a named human must still authorize. No gadget, SDK, token, or
network is needed: SimulatedGadgetService speaks the SDK's local protocol on a
real Unix socket.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest import mock

from models.acquisition.records import refusal_session
from models.muse_gadget import sdk
from models.muse_gadget.capabilities import discover
from models.muse_gadget.client import LocalSocketClient
from models.muse_gadget.commands import COMMAND_SPECS, CircleCommandHandler
from models.muse_gadget.mapping import CLASSES, MAPPING_VERSION, REQUIRED_INPUTS, SDK_SURFACE, document
from models.muse_gadget.notifier import FIELDS, OperatorNotifier, notification_values
from models.muse_gadget.simulator import SimulatedGadgetService
from models.muse_gadget.source import LINK_STREAM, MuseGadgetSource
from models.physiology.controller import ClosedLoopController, ControllerConfig
from models.physiology.experiment import SessionConfig, run_session
from models.physiology.ledger import passport
from models.physiology.loop import ActuationRefused, InsufficientEvidence, NullActuator, run_closed_loop
from models.physiology.twin import DEFAULT_MOTION, TwinConfig
from models.protocols import validate
from models.session_records import load_session, validate_session
from tools import muse_gadget as tool
from tools.run_physiology_twin import export_run

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/muse_gadget/local_socket_protocol.json").read_text(encoding="utf-8"))
EXAMPLE_PROTOCOL = json.loads((ROOT / "experiments/protocols/paced-breathing-arousal.json").read_text(encoding="utf-8"))


def raw_exchange(path: Path, line: bytes) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(str(path))
        sock.sendall(line)
        return json.loads(sock.makefile("rb").readline())


class SocketCase(unittest.TestCase):
    """A short temporary directory for AF_UNIX paths."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir="/tmp"))
        self.sock = self.tmp / "mg.sock"
        self.client = LocalSocketClient(self.sock, timeout_s=0.5)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class SdkFactsTest(unittest.TestCase):
    def test_socket_path_follows_the_sdk_override(self):
        with mock.patch.dict(os.environ, {sdk.SOCKET_ENV: "/tmp/elsewhere.sock"}):
            self.assertEqual(sdk.socket_path(), Path("/tmp/elsewhere.sock"))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(sdk.socket_path(), sdk.DEFAULT_SOCKET)
        self.assertEqual(str(sdk.DEFAULT_SOCKET), FIXTURE["socket"]["default_path"])
        self.assertEqual(sdk.MAX_LOCAL_REQUEST, FIXTURE["socket"]["max_request_bytes"])

    def test_installed_version_is_a_version_or_none(self):
        version = sdk.installed_version()
        self.assertTrue(version is None or version[0].isdigit())

    def test_the_inspected_revision_is_pinned(self):
        self.assertEqual(sdk.SDK_COMMIT, FIXTURE["source"]["commit"])
        self.assertEqual(len(sdk.SDK_COMMIT), 40)


class MappingTest(unittest.TestCase):
    def test_no_closed_loop_input_is_supplied_and_nothing_stands_in(self):
        self.assertTrue(all(e.circle_class == "UNSUPPORTED" and e.supplies == "nothing" for e in REQUIRED_INPUTS))
        classes = {e.name.split(":", 1)[0] for e in REQUIRED_INPUTS}
        self.assertEqual(classes, {"measured", "derived", "estimated", "simulated"})

    def test_every_entry_has_a_defined_class_and_a_reason(self):
        for entry in REQUIRED_INPUTS + SDK_SURFACE:
            with self.subTest(entry=entry.name):
                self.assertIn(entry.circle_class, CLASSES)
                self.assertGreater(len(entry.reason), 40)

    def test_every_command_the_sdk_defines_is_classified(self):
        names = " ".join(e.name for e in SDK_SURFACE)
        for command in sdk.LINUX_COMMANDS + sdk.ESP32_COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, names)

    def test_shell_and_file_access_is_forbidden_on_a_circle_host(self):
        forbidden = [e for e in SDK_SURFACE if e.circle_class == "FORBIDDEN_ON_CIRCLE_HOST"]
        self.assertEqual(len(forbidden), 1)
        for command in ("system.run", "file.read", "file.write"):
            self.assertIn(command, forbidden[0].name)

    def test_the_mapping_is_versioned_and_serializable(self):
        doc = json.loads(json.dumps(document()))
        self.assertEqual((doc["mapping_version"], doc["sdk_commit"]), (MAPPING_VERSION, sdk.SDK_COMMIT))
        self.assertRegex(MAPPING_VERSION, r"^muse-gadget-mapping/\d+\.\d+\.\d+$")


class ClientTest(SocketCase):
    def test_a_probe_finds_a_responding_service_and_forwards_nothing(self):
        with SimulatedGadgetService(self.sock) as service:
            self.assertEqual(self.client.probe().outcome, "SERVICE_RESPONDING")
            self.assertEqual(service.accepted, [])

    def test_every_scripted_behavior_has_its_outcome(self):
        script = ["ack", "not_connected", "error", "drop", "malformed", "stall"]
        expected = ["DELIVERED_ACK", "NOT_CONNECTED", "REJECTED", "CONNECTION_DROPPED", "MALFORMED_REPLY", "TIMEOUT"]
        with SimulatedGadgetService(self.sock, script) as service:
            outcomes = [self.client.send("status", "circle-sessions").outcome for _ in script]
            self.assertEqual(outcomes, expected)
            self.assertEqual(service.accepted, [{"message": "status", "session_id": "circle-sessions"}])

    def test_invalid_requests_are_never_sent(self):
        with SimulatedGadgetService(self.sock) as service:
            for message, side_chat in (("", None), ("   ", None), (None, None), ("ok", "../etc"), ("ok", "x" * 65),
                                       ("x" * 70_000, None)):
                with self.subTest(message=str(message)[:10], side_chat=side_chat):
                    self.assertEqual(self.client.send(message, side_chat).outcome, "INVALID_REQUEST")
            self.assertEqual(service.connections, 0)

    def test_absent_misplaced_and_stale_sockets_are_told_apart(self):
        self.assertEqual(self.client.probe().outcome, "SERVICE_ABSENT")
        self.sock.write_text("not a socket")
        self.assertEqual(self.client.send("hi").outcome, "NOT_A_SOCKET")
        self.sock.unlink()
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(self.sock))
        stale.close()
        self.assertEqual(self.client.probe().outcome, "CONNECTION_REFUSED")

    def test_a_socket_this_account_may_not_open_is_classified(self):
        def forbidden(path, timeout):
            raise PermissionError(13, "Permission denied", path)

        with SimulatedGadgetService(self.sock):
            client = LocalSocketClient(self.sock, timeout_s=0.5, opener=forbidden)
            self.assertEqual(client.send("hi").outcome, "PERMISSION_DENIED")

    def test_exchanges_are_timed_on_the_host_clock(self):
        ticks = iter(range(1000, 100_000, 250))
        with SimulatedGadgetService(self.sock):
            exchange = LocalSocketClient(self.sock, clock=lambda: next(ticks)).send("hi")
        self.assertEqual((exchange.started_us, exchange.round_trip_us), (1000, 250))

    def test_the_sdk_transcripts_hold_for_the_simulator(self):
        for transcript in FIXTURE["transcripts"]:
            behavior = "ack" if transcript["link"] == "connected" else "not_connected"
            with self.subTest(transcript=transcript["name"]), SimulatedGadgetService(self.sock, default=behavior):
                reply = raw_exchange(self.sock, transcript["request"].encode())
                if "reply" in transcript:
                    self.assertEqual(reply, transcript["reply"])
                else:
                    self.assertIs(reply["ok"], transcript["reply_ok"])
                if "probe_outcome" in transcript:
                    self.assertEqual(self.client.probe().outcome, transcript["probe_outcome"])
                if "send_outcome" in transcript:
                    request = json.loads(transcript["request"])
                    self.assertEqual(self.client.send(request["message"], request.get("session_id")).outcome,
                                     transcript["send_outcome"])


class CapabilitiesTest(SocketCase):
    def test_no_signal_is_ever_offered_and_the_only_output_is_an_operator_channel(self):
        absent = discover(self.client)
        self.assertEqual((absent.signals, absent.actuators, absent.connected), ((), (), False))
        self.assertEqual(absent.connection_state, "LOCAL_SERVICE_ABSENT")
        with SimulatedGadgetService(self.sock):
            present = discover(self.client)
        self.assertEqual((present.signals, present.connected, present.sampling), ((), True, {}))
        (chat,) = present.actuators
        self.assertEqual((chat.target, chat.closed_loop), ("OPERATOR_CHANNEL", False))

    def test_discovery_reads_no_credentials(self):
        marker = "marker-value-that-is-not-a-token"
        with mock.patch.dict(os.environ, {"MUSEGADGET_SDK_TOKEN": marker}), SimulatedGadgetService(self.sock):
            self.assertNotIn(marker, json.dumps(discover(self.client).to_dict()))

    def test_limitations_state_what_the_sdk_cannot_do(self):
        limitations = " ".join(discover(self.client).limitations)
        for phrase in ("no physiological sensing", "No device clock", "not that a person read it", "Meta's Muse service"):
            self.assertIn(phrase, limitations)


class SourceTest(SocketCase):
    def test_the_closed_loop_refuses_the_gadget_and_the_refusal_is_a_session(self):
        with SimulatedGadgetService(self.sock):
            source = MuseGadgetSource(self.client)
            with self.assertRaises(InsufficientEvidence) as caught:
                run_closed_loop(source, NullActuator(), ClosedLoopController(ControllerConfig()))
            capabilities = source.capabilities()
        problems = caught.exception.problems
        self.assertEqual(len(problems), 5)
        self.assertTrue(all(name in " ".join(problems) for name in ("eda", "ppg", "imu", "sync", "protocol marker")))
        records = refusal_session(capabilities, problems, source.link_events, ControllerConfig(), "MUSE-1", "SIMULATED")
        validate_session(records)
        card = passport(records)
        self.assertEqual((card["MODE"], card["INPUT"], card["HUMAN DATA"]), ("SIMULATED", "no streams", "NONE"))
        self.assertEqual([e.kind for e in source.link_events], ["LINK_STATE:SERVICE_RESPONDING"])

    def test_a_service_that_disappears_and_returns_is_recorded_as_link_states(self):
        source = MuseGadgetSource(self.client)
        service = SimulatedGadgetService(self.sock)
        service.start()
        source.observe()
        service.stop()
        source.observe()
        service.start()
        source.observe()
        service.stop()
        self.assertEqual([e.kind for e in source.link_events],
                         ["LINK_STATE:SERVICE_RESPONDING", "LINK_STATE:SERVICE_ABSENT", "LINK_STATE:SERVICE_RESPONDING"])
        self.assertTrue(all(e.stream_id == LINK_STREAM for e in source.link_events))
        times = [e.device_time_us for e in source.link_events]
        self.assertEqual(times, sorted(times))

    def test_its_view_never_contains_a_stream(self):
        source = MuseGadgetSource(self.client)
        source.observe()
        self.assertEqual((source.view(10**12).streams, source.finish().streams), ({}, {}))
        self.assertFalse(source.advance(10**6))


class NotifierTest(SocketCase):
    VALUES = notification_values({"SESSION": "TWIN-CLEAN-S7-ACTIVE", "MODE": "SIMULATED", "ARM": "ACTIVE",
                                  "CONTROLLER": "1.2.0", "EVALUATIONS": "59", "INTERVENTIONS": "1 program(s)",
                                  "HUMAN DATA": "NONE", "SEED": "7", "HARDWARE": "Rev B forward model"},
                                 REPLAY="independent audit REPLAY_MATCH")

    def test_messages_come_only_from_whitelisted_fields(self):
        self.assertEqual(set(self.VALUES), {"SESSION", "MODE", "ARM", "CONTROLLER", "EVALUATIONS", "INTERVENTIONS",
                                            "HUMAN_DATA", "REPLAY"})
        self.assertTrue(set(self.VALUES) <= set(FIELDS))
        with self.assertRaisesRegex(ValueError, "whitelist"):
            OperatorNotifier.compose("SESSION_COMPLETE", {**self.VALUES, "HR": "88 bpm"})
        with self.assertRaisesRegex(ValueError, "needs"):
            OperatorNotifier.compose("SESSION_COMPLETE", {k: v for k, v in self.VALUES.items() if k != "REPLAY"})
        with self.assertRaisesRegex(ValueError, "unknown template"):
            OperatorNotifier.compose("BREATHE_SLOWLY", self.VALUES)

    def test_values_cannot_smuggle_lines_or_length(self):
        message = OperatorNotifier.compose("SESSION_COMPLETE", {**self.VALUES, "SESSION": "A\nB\tC " + "x" * 500})
        self.assertNotIn("\n", message)
        self.assertNotIn("\t", message)
        self.assertLess(len(message), 600)

    def test_every_attempt_is_recorded_outside_the_loop(self):
        with SimulatedGadgetService(self.sock, ["ack", "not_connected"]) as service:
            notifier = OperatorNotifier(self.client, provenance="SIMULATED")
            outcomes = [notifier.notify("SESSION_COMPLETE", self.VALUES).outcome for _ in range(2)]
            self.assertEqual(service.accepted[0]["message"], OperatorNotifier.compose("SESSION_COMPLETE", self.VALUES))
            self.assertEqual(service.accepted[0]["session_id"], "circle-sessions")
        self.assertEqual(outcomes, ["DELIVERED_ACK", "NOT_CONNECTED"])
        validate_session(notifier.records)
        for record, outcome in zip(notifier.records, outcomes):
            for flag in ("NOT_AN_INTERVENTION", "OUTSIDE_CLOSED_LOOP", f"DELIVERY:{outcome}"):
                self.assertIn(flag, record["status_flags"])
            self.assertNotEqual(record["record_type"], "INTERVENTION")

    def test_the_notifier_can_never_deliver_a_cue(self):
        notifier = OperatorNotifier(self.client, provenance="SIMULATED")
        with self.assertRaises(ActuationRefused):
            notifier.execute(0, 1, 0)

        class Untouchable:
            def start(self):
                raise AssertionError("the loop must refuse before acquiring")

        with self.assertRaisesRegex(ActuationRefused, "operator channel"):
            run_closed_loop(Untouchable(), notifier, ClosedLoopController(ControllerConfig()))
        with self.assertRaises(ValueError):
            OperatorNotifier(self.client, provenance="TEST")


class CommandsTest(unittest.TestCase):
    def setUp(self):
        self.handler = CircleCommandHandler()

    def validate(self, protocol) -> dict:
        text = protocol if isinstance(protocol, str) else json.dumps(protocol)
        return self.handler("circle.protocol.validate", {"protocol_json": text}, 30_000)

    def test_specs_follow_the_sdk_command_format_and_stay_small(self):
        for name, spec in COMMAND_SPECS.items():
            with self.subTest(command=name):
                self.assertTrue(name.startswith("circle."))
                self.assertIsInstance(spec["description"], str)
                for param in {**spec["required"], **spec["optional"]}.values():
                    self.assertIn(param["type"], ("string", "integer", "boolean"))
                    self.assertTrue(param["description"])
        self.assertLess(len(json.dumps(COMMAND_SPECS)), 4096)

    def test_capabilities_are_read_only_and_state_their_limits(self):
        result = self.handler("circle.capabilities", {}, None)
        self.assertTrue(result["ok"])
        payload = result["payload"]
        self.assertIn("cannot authorize", payload["authority"])
        self.assertIn("simulated", payload["human_data"])
        self.assertIn("muse_gadget_adapter", {m["id"] for m in payload["modules"]})

    def test_a_valid_protocol_is_validated_and_nothing_is_authorized(self):
        result = self.validate(EXAMPLE_PROTOCOL)
        payload = result["payload"]
        self.assertEqual(payload["status"], "VALID_FOR_SIMULATION")
        self.assertEqual(payload["protocol_sha256"], validate(EXAMPLE_PROTOCOL)["protocol_sha256"])
        self.assertEqual((payload["authorized"], payload["executed"]), (False, False))
        self.assertIn("named human", payload["next_step"])

    def test_a_rejected_protocol_reports_its_problems(self):
        payload = self.validate({**EXAMPLE_PROTOCOL, "target": "HUMAN_PARTICIPANT"})["payload"]
        self.assertEqual(payload["status"], "REJECTED")
        self.assertTrue(any("not executable" in p for p in payload["problems"]))

    def test_an_ai_proposal_cannot_present_itself_as_human(self):
        result = self.validate({**EXAMPLE_PROTOCOL, "proposed_by": {"kind": "HUMAN", "name": "anyone"}})
        self.assertFalse(result["ok"])
        self.assertIn("AI_MODEL", result["error"])

    def test_malformed_inputs_are_refused_without_raising(self):
        for params in ({}, {"protocol_json": 7}, {"protocol_json": "  "}, {"protocol_json": "{"},
                       {"protocol_json": '{"a": 1, "a": 2}'}, {"protocol_json": '{"a": NaN}'},
                       {"protocol_json": "[1, 2]"}, {"protocol_json": "x" * 70_000}):
            with self.subTest(params=str(params)[:40]):
                self.assertFalse(self.handler("circle.protocol.validate", params, None)["ok"])
        self.assertFalse(self.handler("circle.protocol.validate", None, None)["ok"])

    def test_no_command_can_authorize_execute_or_reach_the_shell(self):
        for name in ("circle.protocol.authorize", "circle.protocol.run", "system.run", "file.read", "file.write",
                     "device.ota", "circle.capabilities.write"):
            with self.subTest(command=name):
                result = self.handler(name, {"command": "id"}, None)
                self.assertEqual(result, {"ok": False, "error": f"unsupported command: {name}"})

    def test_a_failing_validator_becomes_an_error_result(self):
        def broken(protocol):
            raise RuntimeError("validator unavailable")

        result = CircleCommandHandler(validator=broken)("circle.protocol.validate",
                                                         {"protocol_json": json.dumps(EXAMPLE_PROTOCOL)}, None)
        self.assertEqual(result, {"ok": False, "error": "RuntimeError: validator unavailable"})

    def test_every_invocation_is_logged_with_the_protocol_hash(self):
        self.handler("circle.capabilities", {}, None)
        self.validate(EXAMPLE_PROTOCOL)
        self.handler("system.run", {}, None)
        log = self.handler.log
        self.assertEqual([entry["command"] for entry in log], ["circle.capabilities", "circle.protocol.validate", "system.run"])
        self.assertEqual(log[1]["protocol_sha256"], validate(EXAMPLE_PROTOCOL)["protocol_sha256"])
        self.assertFalse(log[2]["ok"])


class ToolTest(unittest.TestCase):
    def run_tool(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = tool.main(list(argv))
        return code, out.getvalue()

    def test_check_records_the_refusal_with_the_simulator(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, text = self.run_tool("check", "--simulate", "--output", tmp)
            self.assertEqual(code, 0)
            self.assertIn("Refused by the input contract", text)
            records = load_session(Path(tmp) / "session.ndjson")
            self.assertIn("SIMULATED_DATA", records[0]["status_flags"])
            manifest = json.loads((Path(tmp) / "manifest.json").read_text())
            self.assertEqual(manifest["terminated"], "INSUFFICIENT_EVIDENCE")

    def test_notify_only_sends_when_asked(self):
        config = SessionConfig(twin=TwinConfig(duration_s=130.0, motion=DEFAULT_MOTION[:1]))
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            export_run(run_session(config), run_dir, None, with_report=False)
            code, text = self.run_tool("notify", str(run_dir), "--simulate")
            self.assertEqual(code, 0)
            self.assertIn("Not sent (dry run)", text)
            self.assertFalse(list(Path(tmp).glob("*.ndjson")))
            record = Path(tmp) / "sent.ndjson"
            code, text = self.run_tool("notify", str(run_dir), "--simulate", "--send", "--record", str(record))
            self.assertEqual(code, 0)
            (sent,) = load_session(record)
            self.assertIn("DELIVERY:DELIVERED_ACK", sent["status_flags"])

    def test_commands_can_be_listed_and_invoked(self):
        code, text = self.run_tool("commands")
        self.assertEqual((code, set(json.loads(text))), (0, set(COMMAND_SPECS)))
        self.assertEqual(self.run_tool("commands", "--invoke", "system.run")[0], 1)
        code, text = self.run_tool("mapping")
        self.assertEqual(json.loads(text)["mapping_version"], MAPPING_VERSION)


if __name__ == "__main__":
    unittest.main()
