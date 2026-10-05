"""Optional checks against a real, paired Muse gadget on this host.

Skipped unless CIRCLE_MUSE_GADGET_HARDWARE=1. They talk to the real musegadget
service's local socket ($MUSEGADGET_SOCKET or the SDK default) and never need
or read a token. With CIRCLE_MUSE_GADGET_SEND=1 one test also posts a single
message to the side chat named by CIRCLE_MUSE_GADGET_SIDE_CHAT (default
circle-hardware-test); that message leaves the host for Meta's Muse service.

    CIRCLE_MUSE_GADGET_HARDWARE=1 python -m unittest tests.test_muse_gadget_hardware
"""

from __future__ import annotations

import os
import unittest

from models.muse_gadget.capabilities import discover
from models.muse_gadget.client import LocalSocketClient
from models.muse_gadget.source import MuseGadgetSource
from models.physiology.controller import ClosedLoopController, ControllerConfig
from models.physiology.loop import InsufficientEvidence, NullActuator, run_closed_loop

ENABLED = os.environ.get("CIRCLE_MUSE_GADGET_HARDWARE") == "1"
SEND = os.environ.get("CIRCLE_MUSE_GADGET_SEND") == "1"


@unittest.skipUnless(ENABLED, "set CIRCLE_MUSE_GADGET_HARDWARE=1 on a host running a paired Muse gadget")
class MuseGadgetHardwareTest(unittest.TestCase):
    def test_the_local_service_responds(self):
        probe = LocalSocketClient(timeout_s=10).probe()
        self.assertEqual(probe.outcome, "SERVICE_RESPONDING", probe.detail)

    def test_a_real_gadget_offers_no_signal(self):
        capabilities = discover(LocalSocketClient(timeout_s=10))
        self.assertTrue(capabilities.connected, capabilities.connection_state)
        self.assertEqual(capabilities.signals, ())

    def test_the_closed_loop_refuses_the_real_gadget(self):
        with self.assertRaises(InsufficientEvidence):
            run_closed_loop(MuseGadgetSource(LocalSocketClient(timeout_s=10)), NullActuator(),
                            ClosedLoopController(ControllerConfig()))

    @unittest.skipUnless(SEND, "set CIRCLE_MUSE_GADGET_SEND=1 to post one test message to the Muse")
    def test_one_message_reaches_the_muse_service(self):
        side_chat = os.environ.get("CIRCLE_MUSE_GADGET_SIDE_CHAT", "circle-hardware-test")
        exchange = LocalSocketClient(timeout_s=90).send("CIRCLE hardware check: link test, nothing to do.", side_chat)
        self.assertEqual(exchange.outcome, "DELIVERED_ACK", exchange.detail)


if __name__ == "__main__":
    unittest.main()
