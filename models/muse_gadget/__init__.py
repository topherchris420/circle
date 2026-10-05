"""Muse Gadget SDK adapter: what Meta's SDK can honestly contribute to CIRCLE.

The Muse Gadget SDK (github.com/facebookincubator/muse-gadget-sdk) connects
devices someone builds, ESP32 boards and Linux computers, to their Muse: Meta's
AI assistant, in a per-user cloud VM. Control flows from the Muse to the device.
The SDK carries no physiological signal, no sample clock, no timestamps, and no
sequence numbers (see sdk.py for the inspected surface).

So the Muse gadget is not a biosignal source, and this adapter never pretends
otherwise. It contributes exactly what the SDK supports, inside CIRCLE's
boundaries:

  capabilities  live discovery of the gadget environment; no signals, ever
  mapping       the versioned statement of what maps to CIRCLE (no measurement)
  source        the gadget offered to the closed loop, refused by the input
                contract with the reasons recorded as a session
  notifier      templated session outcomes posted to the Muse chat: an operator
                channel outside the loop, refused as a cue actuator
  commands      the command set a CIRCLE gadget would serve: read capabilities
                and validate AI-proposed protocols, never authorize or execute
  client        the musegadget local-socket protocol, every outcome classified
  simulator     a deterministic stand-in for the musegadget service

Everything here uses the standard library. Nothing requires the SDK, a gadget,
a token, or a network; the core never imports this package.
"""
