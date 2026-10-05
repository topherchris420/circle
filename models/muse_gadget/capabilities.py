"""Capability discovery for the Muse gadget environment on this host.

discover() reports what is actually there, from a protocol probe of the local
musegadget socket and the importable package version, in the same Capabilities
record every CIRCLE source uses. It never contacts the Muse, never reads a
token, and never lists a signal the SDK does not deliver: `signals` is empty by
construction, because the SDK delivers none.
"""

from __future__ import annotations

from models.physiology.loop import ActuatorCapability, Capabilities

from .client import Exchange, LocalSocketClient
from .mapping import MAPPING_VERSION
from .sdk import SDK_COMMIT, installed_version

LIMITATIONS = (
    "The Muse Gadget SDK provides no physiological sensing: no EEG, EDA, PPG, or inertial stream reaches local programs.",
    "Control flows from the Muse (an AI assistant in a cloud VM) to the gadget; a local program can only post text "
    "into the Muse chat.",
    "No device clock, sample timestamps, or sequence numbers: nothing from the SDK can satisfy CIRCLE's timing contract.",
    "An acknowledgement means the Muse service accepted a chat turn, not that a person read it; replies are AI-written.",
    "Messages leave this host for Meta's Muse service: never send participant identifiers or physiological data.",
    "Whether the service holds a live session with the Muse is visible only by sending a message.",
    f"Mapping {MAPPING_VERSION} reflects the SDK at commit {SDK_COMMIT[:7]}; re-inspect after SDK updates.",
)

AUTHENTICATION = ("CIRCLE holds no Muse credentials. The local socket admits root and the gadget's run-as group; the "
                  "SDK token and pairing tokens stay inside the musegadget service.")


def discover(client: LocalSocketClient | None = None, probe: Exchange | None = None) -> Capabilities:
    """What the Muse gadget environment supports right now (probing the socket unless `probe` is given)."""
    client = client or LocalSocketClient()
    probe = probe or client.probe()
    responding = probe.outcome == "SERVICE_RESPONDING"
    version = installed_version()
    actuators = (ActuatorCapability(
        "muse_chat", "OPERATOR_CHANNEL", ("DELIVERY_ACK",),
        "Text into the Muse chat through the musegadget service; the Muse, an AI assistant, may answer in the app"),
    ) if responding else ()
    return Capabilities(
        source="muse-gadget", connected=responding, connection_state=f"LOCAL_{probe.outcome}",
        signals=(), actuators=actuators,
        sdk_version=f"{version}" if version else None,
        hardware=(f"musegadget service at {client.path}" if responding else f"none reachable at {client.path}"),
        authentication=AUTHENTICATION, limitations=LIMITATIONS)
