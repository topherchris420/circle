"""What the Muse Gadget SDK exposes, as inspected at a pinned revision.

Source: https://github.com/facebookincubator/muse-gadget-sdk (Apache-2.0; a few
third-party files keep their upstream licenses), commit 1d2cb5a (2026-10-05),
Linux package `musegadget` 0.1.0, ESP32 firmware built as version 999.0.0.

The SDK connects a device someone builds, an ESP32 board or a Linux computer,
to their Muse: Meta's AI assistant, running in a per-user cloud VM and paired
through the Muse phone app. Control flows from the Muse to the device. The
device advertises commands in `link.register` over a Noise-encrypted WebSocket
to the VM and answers each `link.invoke`; the Muse decides when to invoke them.

  Linux device SDK   commands the Muse may invoke: system.run (any shell command
                     as the install account), file.read, file.write, device.health.
                     Local programs may only post text into the Muse chat, through
                     the service's Unix socket (`musegadget send-user-msg`).
  ESP32 device SDK   status light, button, screens (display.draw_url,
                     display.show_animation), push-to-talk voice to the Muse
                     (replies are text), voice.configure, device.discover,
                     device.ota, plus sensors.read on the Seeed SenseCAP Indicator
                     (CO2, tVOC index, temperature, relative humidity, each with an
                     integer age in seconds) and camera.capture on the SenseCAP
                     Watcher. Only the Muse VM invokes these.

Neither SDK carries a physiological signal, a sample clock, timestamps, or
sequence numbers. Pairing needs an SDK token from gadgets.muse.ai and the Muse
app's Developer mode; community pairing has no manufacturer verification and
cannot prevent an active man-in-the-middle (the SDK says so).

The constants below mirror the Linux SDK's local-socket protocol
(linux/src/musegadget/config.py, service.py, cli.py). CIRCLE never reads the
SDK token or the pairing tokens: a local program needs neither.
"""

from __future__ import annotations

import os
from pathlib import Path
import re

SDK_REPOSITORY = "https://github.com/facebookincubator/muse-gadget-sdk"
SDK_COMMIT = "1d2cb5af1cc3c412eedf8b08b49d3876a1eba956"
SDK_LINUX_PACKAGE = "musegadget"
SDK_LINUX_VERSION_INSPECTED = "0.1.0"

SOCKET_ENV = "MUSEGADGET_SOCKET"                                # config.py
DEFAULT_SOCKET = Path("/run/musegadget/musegadget.sock")         # config.py
MAX_LOCAL_REQUEST = 64 * 1024                                    # service.py: start_unix_server(limit=...)
SESSION_ID_RE = re.compile(r"[A-Za-z0-9-]{1,64}")                 # service.py: side-chat ids
LOCAL_REPLY_TIMEOUT_S = 90                                       # cli.py: send-user-msg waits this long

# Replies the service writes (service.py, Service._local_request).
REPLY_EXPECTED_MESSAGE = 'expected {"message": "..."}'
REPLY_BAD_SESSION_ID = "session_id must be letters, digits and dashes"
REPLY_NOT_CONNECTED = "not connected to the Muse"

LINUX_COMMANDS = ("system.run", "file.read", "file.write", "device.health")
ESP32_COMMANDS = ("device.health", "device.discover", "display.draw_url", "display.show_animation", "voice.configure",
                  "sensors.read", "camera.capture", "device.ota")


def socket_path() -> Path:
    """Where the musegadget service accepts messages from local programs."""
    return Path(os.environ.get(SOCKET_ENV) or DEFAULT_SOCKET)


def installed_version() -> str | None:
    """The musegadget version importable from this interpreter, or None.

    An installed gadget usually lives in its own environment (/opt/musegadget/venv),
    so None here does not mean no gadget is running; the socket probe says that.
    """
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version(SDK_LINUX_PACKAGE)
    except PackageNotFoundError:
        return None
