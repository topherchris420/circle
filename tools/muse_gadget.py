"""Inspect and use a Muse gadget from CIRCLE, within what the Muse Gadget SDK actually supports.

  capabilities   discover what the gadget environment on this host supports (JSON)
  mapping        the versioned mapping from the SDK's surface to CIRCLE (JSON)
  check          offer the gadget to the closed loop as a source; the input contract
                 refuses it (the SDK delivers no physiological stream) and the refusal
                 is written as a session (session.ndjson, passport.txt, manifest.json)
  notify         compose the end-of-session message for an exported, audited run and
                 print it; only with --send is it posted to the Muse chat
  commands       print the command set a CIRCLE gadget would serve, or run one locally

--simulate uses a deterministic stand-in for the musegadget service, so every
subcommand works with no gadget, no SDK token, and no network. Without it,
commands talk to the local musegadget socket ($MUSEGADGET_SOCKET or
/run/musegadget/musegadget.sock). Nothing here reads Muse credentials.
"""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.acquisition.records import refusal_session, write_refusal
from models.muse_gadget.capabilities import discover
from models.muse_gadget.client import LocalSocketClient
from models.muse_gadget.commands import COMMAND_SPECS, CircleCommandHandler
from models.muse_gadget.mapping import MAPPING_VERSION, document
from models.muse_gadget.notifier import DEFAULT_SIDE_CHAT, OperatorNotifier, notification_values
from models.muse_gadget.sdk import SDK_COMMIT
from models.muse_gadget.simulator import SimulatedGadgetService
from models.muse_gadget.source import MuseGadgetSource
from models.physiology.controller import ClosedLoopController, ControllerConfig
from models.physiology.loop import InsufficientEvidence, NullActuator, run_closed_loop


@contextlib.contextmanager
def gadget(args: argparse.Namespace) -> Iterator[tuple[LocalSocketClient, str]]:
    """A client for the real local socket, or for a simulated service; and the provenance its observations carry."""
    if getattr(args, "simulate", False):
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp, SimulatedGadgetService(Path(tmp) / "mg.sock"):
            yield LocalSocketClient(Path(tmp) / "mg.sock", timeout_s=args.timeout), "SIMULATED"
    else:
        yield LocalSocketClient(args.socket, timeout_s=args.timeout), "RAW_MEASURED"


def attempt(client: LocalSocketClient, provenance: str, output: Path, session_id: str) -> dict:
    """Offer the gadget to the closed loop; record what happens (always a refusal: it has no streams)."""
    source = MuseGadgetSource(client)
    try:
        run_closed_loop(source, NullActuator(), ClosedLoopController(ControllerConfig()))
    except InsufficientEvidence as exc:
        capabilities = source.capabilities()
        records = refusal_session(capabilities, exc.problems, source.link_events, ControllerConfig(), session_id,
                                  provenance, (f"MAPPING_VERSION:{MAPPING_VERSION}", f"SDK_INSPECTED_AT:{SDK_COMMIT[:12]}"))
        return write_refusal(output, records, capabilities, {"mapping_version": MAPPING_VERSION, "sdk_commit": SDK_COMMIT})
    raise RuntimeError("the closed loop accepted a source with no physiological streams; the input contract is broken")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def connected(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--socket", type=Path, help="musegadget socket (default: $MUSEGADGET_SOCKET or the SDK default)")
        p.add_argument("--simulate", action="store_true", help="use a deterministic simulated musegadget service")
        p.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for the service (default 10)")
        return p

    connected(sub.add_parser("capabilities", help="discover what the gadget environment supports"))
    sub.add_parser("mapping", help="print the SDK-to-CIRCLE mapping")
    check = connected(sub.add_parser("check", help="offer the gadget to the closed loop and record the outcome"))
    check.add_argument("--output", type=Path, default=Path("outputs/muse-gadget-attempt"))
    check.add_argument("--session-id", default="MUSE-GADGET-ATTEMPT")
    notify = connected(sub.add_parser("notify", help="report an exported run's outcome to the Muse chat"))
    notify.add_argument("run", type=Path, help="exported run directory (tools/run_physiology_twin.py --output)")
    notify.add_argument("--side-chat", default=DEFAULT_SIDE_CHAT, help=f"Muse side chat id (default {DEFAULT_SIDE_CHAT})")
    notify.add_argument("--send", action="store_true", help="actually post the message (default: print it only)")
    notify.add_argument("--record", type=Path, help="where to write the notification record (default: beside the run)")
    commands = sub.add_parser("commands", help="the command set a CIRCLE gadget would serve")
    commands.add_argument("--invoke", help="run one command locally, as a Muse invocation would")
    commands.add_argument("--params", default="{}", help="JSON parameters for --invoke")
    args = parser.parse_args(argv)

    if args.command == "mapping":
        print(json.dumps(document(), indent=2))
        return 0
    if args.command == "commands":
        if not args.invoke:
            print(json.dumps(COMMAND_SPECS, indent=2))
            return 0
        result = CircleCommandHandler()(args.invoke, json.loads(args.params), None)
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    with gadget(args) as (client, provenance):
        if args.command == "capabilities":
            print(json.dumps(discover(client).to_dict(), indent=2))
            return 0
        if args.command == "check":
            manifest = attempt(client, provenance, args.output, args.session_id)
            print((args.output / "passport.txt").read_text(encoding="utf-8"), end="")
            print("Refused by the input contract (expected: the Muse Gadget SDK delivers no physiological stream):")
            for reason in manifest["refusal"]:
                print(f"  - {reason}")
            print(f"Session written to {args.output}")
            return 0
        return notify_run(args, client, provenance)


def notify_run(args: argparse.Namespace, client: LocalSocketClient, provenance: str) -> int:
    from models.physiology.audit import audit_run

    manifest = json.loads((args.run / "manifest.json").read_text(encoding="utf-8"))
    status = audit_run(args.run)["replay_status"]
    values = notification_values(manifest["passport"], REPLAY=f"independent audit {status}")
    notifier = OperatorNotifier(client, args.side_chat, provenance)
    message = notifier.compose("SESSION_COMPLETE", values)
    print(f"Message for Muse side chat {args.side_chat!r} ({len(message.encode())} bytes, leaves this host for Meta's "
          f"Muse service):\n  {message}")
    if not args.send:
        print("Not sent (dry run). Add --send to post it.")
        return 0
    exchange = notifier.notify("SESSION_COMPLETE", values)
    record = args.record or args.run.parent / f"{args.run.name}.operator-notifications.ndjson"
    record.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in notifier.records),
                      encoding="utf-8")
    print(f"Delivery: {exchange.outcome} ({exchange.detail}); record written to {record}")
    return 0 if exchange.outcome == "DELIVERED_ACK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
