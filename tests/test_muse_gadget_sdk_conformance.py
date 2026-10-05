"""Conformance with the Muse Gadget SDK's own code. Runs only where the musegadget package is installed.

Elsewhere the adapter is tested against SimulatedGadgetService. Here the same
client and command set run against the SDK itself, with no network, no gadget,
and no Muse:

  * musegadget.service.Service.serve_local, the real local-socket service: CIRCLE's
    LocalSocketClient must read its replies exactly as it reads the simulator's,
    and every fixture transcript must hold.
  * musegadget.link_client.LinkSession, the real control-stream client, over an
    in-memory transport with a real Noise XX handshake against a minimal fake VM
    (the SDK's own test pattern): a gadget built on it must advertise exactly
    CIRCLE's command set and return each result as the SDK's link.result.

To run them: pip install "git+https://github.com/facebookincubator/muse-gadget-sdk@1d2cb5a#subdirectory=linux"
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from models.muse_gadget.client import LocalSocketClient
from models.muse_gadget.commands import COMMAND_SPECS, CircleCommandHandler

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/muse_gadget/local_socket_protocol.json").read_text(encoding="utf-8"))
EXAMPLE_PROTOCOL = (ROOT / "experiments/protocols/paced-breathing-arousal.json").read_text(encoding="utf-8")
HAVE_SDK = importlib.util.find_spec("musegadget") is not None
SKIP = "musegadget (the Muse Gadget Linux SDK) is not installed"


class FakeMuseSession:
    """Stands in for a registered LinkSession inside the SDK's Service (as the SDK's tests do)."""

    registered_at = 1.0

    def __init__(self) -> None:
        self.sent: list[tuple[str, str | None]] = []

    async def send_chat(self, message: str, session_id: str | None = None) -> dict:
        self.sent.append((message, session_id))
        return {"ok": True, "status": 200, "response": None}


async def ask(path: Path, payload: bytes) -> dict:
    reader, writer = await asyncio.open_unix_connection(str(path))
    writer.write(payload)
    await writer.drain()
    reply = json.loads(await reader.readline())
    writer.close()
    return reply


@unittest.skipUnless(HAVE_SDK, SKIP)
class LocalServiceConformanceTest(unittest.TestCase):
    def run_service(self, check) -> None:
        from musegadget.executor import Account, Executor
        from musegadget.identity import Identity
        from musegadget.service import Service

        async def scenario():
            with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
                path = Path(tmp) / "mg.sock"
                service = Service(identity=Identity("02:00:00:00:00:01"), executor=Executor(Account.current()))
                server = await service.serve_local(path)
                try:
                    await check(service, path)
                finally:
                    server.close()
                    await server.wait_closed()

        asyncio.run(scenario())

    def test_the_client_reads_the_real_service_as_it_reads_the_simulator(self):
        async def check(service, path):
            client = LocalSocketClient(path, timeout_s=5)
            self.assertEqual((await asyncio.to_thread(client.probe)).outcome, "SERVICE_RESPONDING")
            self.assertEqual((await asyncio.to_thread(client.send, "hi")).outcome, "NOT_CONNECTED")
            session = FakeMuseSession()
            service._current = session
            sent = await asyncio.to_thread(client.send, "session ended", "circle-sessions")
            self.assertEqual(sent.outcome, "DELIVERED_ACK")
            self.assertEqual(session.sent, [("session ended", "circle-sessions")])
            self.assertEqual((await asyncio.to_thread(client.probe)).outcome, "SERVICE_RESPONDING")
            self.assertEqual(len(session.sent), 1, "a probe must never reach the Muse")

        self.run_service(check)

    def test_the_fixture_transcripts_hold_for_the_real_service(self):
        async def check(service, path):
            for transcript in FIXTURE["transcripts"]:
                with self.subTest(transcript=transcript["name"]):
                    service._current = FakeMuseSession() if transcript["link"] == "connected" else None
                    reply = await ask(path, transcript["request"].encode())
                    if "reply" in transcript:
                        self.assertEqual(reply, transcript["reply"])
                    else:
                        self.assertIs(reply["ok"], transcript["reply_ok"])

        self.run_service(check)


@unittest.skipUnless(HAVE_SDK, SKIP)
class LinkSessionConformanceTest(unittest.TestCase):
    def test_a_gadget_advertises_exactly_circles_commands_and_serves_them(self):
        from musegadget.link_client import DeviceDescription, LinkSession, MessageDecoder, Outcome, encode_message
        from musegadget.noise import (ApplicationResponse, BodyChunk, NoiseFrameDecoder, NoiseXXResponder, ServiceFrame,
                                      encode_noise_frames)
        from musegadget.noise.transport import decode_request_envelope, encode_response_envelope

        class Pipe:
            def __init__(self, inbox: asyncio.Queue, outbox: asyncio.Queue) -> None:
                self.inbox, self.outbox = inbox, outbox

            async def send(self, data) -> None:
                await self.outbox.put(data)

            async def recv(self):
                data = await self.inbox.get()
                if data is None:
                    raise ConnectionError("closed")
                return data

            async def close(self) -> None:
                await self.outbox.put(None)

        class FakeVm:
            def __init__(self, ws: Pipe) -> None:
                self.ws, self.frames, self.messages, self.stream_id = ws, NoiseFrameDecoder(), MessageDecoder(), 0

            async def handshake(self) -> None:
                responder = NoiseXXResponder()
                responder.initialize()
                await self.ws.send(responder.read_message1_and_write_message2(await self.ws.recv()))
                responder.read_message3(await self.ws.recv())
                self.send_cipher, self.recv_cipher = responder.split()

            async def next_frame(self) -> ServiceFrame:
                while True:
                    assembled = self.frames.decode(self.recv_cipher.decrypt_with_ad(b"", await self.ws.recv()))
                    if assembled is not None:
                        return decode_request_envelope(assembled)

            async def next_message(self) -> dict:
                while True:
                    messages = self.messages.feed((await self.next_frame()).value.data)
                    if messages:
                        return messages[0]

            async def send_frame(self, frame: ServiceFrame) -> None:
                for chunk in encode_noise_frames(encode_response_envelope(frame)):
                    await self.ws.send(self.send_cipher.encrypt_with_ad(b"", chunk))

            async def accept_control_stream(self) -> None:
                request = await self.next_frame()
                self.stream_id = request.stream_id
                await self.send_frame(ServiceFrame.response(self.stream_id, ApplicationResponse(status=200, end_body=False)))

            async def send_message(self, message: dict) -> None:
                await self.send_frame(ServiceFrame.body_chunk(self.stream_id, BodyChunk(data=encode_message(message))))

        async def scenario():
            to_device, to_vm = asyncio.Queue(), asyncio.Queue()
            device_ws, vm = Pipe(to_device, to_vm), FakeVm(Pipe(to_vm, to_device))

            async def connect(url, headers):
                return device_ws

            device = DeviceDescription(node_id="homelink-c1c1e0", display_name="circle", version="0.1.0",
                                       commands=COMMAND_SPECS)
            session = LinkSession(noise_host="gw.example", vm_id="vm", vm_auth_token="tok", device=device,
                                  run_command=CircleCommandHandler(), connect=connect)
            task = asyncio.ensure_future(session.run(asyncio.Event()))
            await asyncio.wait_for(vm.handshake(), 10)
            await asyncio.wait_for(vm.accept_control_stream(), 10)
            register = await asyncio.wait_for(vm.next_message(), 10)
            self.assertEqual(register["method"], "link.register")
            self.assertEqual(register["params"]["commands_v2"], COMMAND_SPECS)
            await vm.send_message({"type": "res", "id": register["id"], "ok": True})
            await vm.send_message({"method": "link.invoke", "id": "inv-1", "command": "circle.protocol.validate",
                                   "params": {"protocol_json": EXAMPLE_PROTOCOL}, "timeout_ms": 30000})
            result = await asyncio.wait_for(vm.next_message(), 60)
            self.assertEqual((result["method"], result["id"], result["ok"]), ("link.result", "inv-1", True))
            self.assertEqual(result["payload"]["status"], "VALID_FOR_SIMULATION")
            self.assertFalse(result["payload"]["authorized"])
            await vm.send_message({"method": "link.invoke", "id": "inv-2", "command": "system.run",
                                   "params": {"command": "id"}, "timeout_ms": 5000})
            refused = await asyncio.wait_for(vm.next_message(), 10)
            self.assertEqual(refused, {"method": "link.result", "id": "inv-2", "ok": False,
                                       "error": "unsupported command: system.run"})
            await vm.send_message({"type": "evt", "event": "link.unpaired"})
            self.assertIs(await asyncio.wait_for(task, 10), Outcome.UNPAIRED)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
