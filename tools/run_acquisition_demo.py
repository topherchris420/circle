"""End-to-end demonstration: one closed-loop experiment through CIRCLE's acquisition boundary.

Runs deterministically, with no hardware, token, or network:

  1. Capabilities  discovery for every source: the twin, the twin behind a
                   simulated link, the recording this run produces, and the Muse
                   gadget environment
  2. Live loop     the twin's device records delivered over a damaged link (a
                   corrupted chunk, a retransmission, a stall, an outage) through
                   the ingestion boundary into the closed loop: ingestion, features,
                   state estimate, bounded controller, quality gates, simulated haptic
                   intervention, IMU-observed actuation, later evaluations, export,
                   and an independent audit that must report REPLAY_MATCH
  3. Recorded      the exported bundle replayed through the same loop as a
                   RecordedSource; decisions and commands must match the record
  4. Muse gadget   the gadget offered as a source; the input contract refuses it
                   (it delivers no physiological stream) and the refusal is a session
  5. Operator      the run's outcome posted to a Muse chat as an operator
                   notification, outside the loop, and recorded
  6. Provenance    for the first decision: what produced the observations, what
                   interpreted them, what decided, what was actuated, what followed

--muse-socket PATH uses a real musegadget service for steps 1, 4, and 5; step 5
then posts only with --send. Everything else is SIMULATED, and nothing here
involves a person.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.acquisition.live import IngestingSource
from models.acquisition.recorded import RecordedSource
from models.acquisition.simulator import FaultPlan, SimulatedLink
from models.muse_gadget.capabilities import discover
from models.muse_gadget.notifier import DEFAULT_SIDE_CHAT, OperatorNotifier, notification_values
from models.physiology.audit import audit_run
from models.physiology.controller import ClosedLoopController
from models.physiology.evidence import dumps
from models.physiology.experiment import TwinHapticActuator, TwinSource, run_session, session_run
from models.physiology.loop import NullActuator, run_closed_loop
from models.physiology.scenarios import SCENARIOS
from models.physiology.sensors import SensorRig
from models.physiology.twin import PhysiologyTwin
from tools.muse_gadget import attempt, gadget
from tools.run_physiology_twin import export_run

DEFAULT_FAULTS = FaultPlan(corrupt=(("ppg", 100.0, "FLOAT_VALUES"),), retransmit=(("imu", 150.0),),
                           stalls=((196.0, 204.0),), outages=((330.0, 336.0),))
ACQUISITION_FLAGS = ("ACQUISITION:LIVE_INGESTION_BOUNDARY", "AVAILABILITY:HOST_RECEIPT")


def provenance_of_first_decision(out: Path, live_caps: dict) -> dict:
    ledger = json.loads((out / "live/closed_loop_ledger.json").read_text(encoding="utf-8"))
    manifest = json.loads((out / "live/manifest.json").read_text(encoding="utf-8"))
    decisions = ledger["decisions"]
    if not decisions:
        return {"decision": None, "note": "the controller made no decision in this run"}
    first = decisions[0]
    stages = Counter(link["stage"] for link in first.get("execution_chain", []))
    after = next((d for d in decisions[1:] if d["decision_id"].startswith(first["decision_id"])), None)
    revision = manifest["software_revision"]
    return {
        "decision": f"{first['decision_id']} {first['action']} at device time {first['decision_time_us']} us",
        "observations": (f"{len(live_caps['signals'])} streams ({', '.join(s['stream_id'] for s in live_caps['signals'])}), "
                         f"{', '.join(sorted({s['provenance'] for s in live_caps['signals']}))}, from "
                         f"{live_caps['source']}; {live_caps['hardware']}; availability stamped at host receipt"),
        "interpretation": (f"pipeline {manifest['pipeline_version']}, analysis code {manifest['pipeline_source']}, "
                           f"repository {revision['git_commit'][:12]} (tracked files clean: {revision['worktree_clean']})"),
        "decided_by": f"controller {manifest['controller_version']}: {first['why']}",
        "intervention": (f"{sum(stages.values())} cue(s): " + ", ".join(f"{n} {stage}" for stage, n in sorted(stages.items()))
                         if stages else first.get("execution", "none")),
        "afterward": (f"{after['decision_id']} {after['action']}: {after['why']}" if after else "no later decision") +
                     "; an effect on physiology is not asserted without a matched control",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=Path("outputs/acquisition-demo"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--no-faults", action="store_true", help="deliver over a clean link")
    parser.add_argument("--no-report", action="store_true", help="skip report.html for the live run")
    parser.add_argument("--muse-socket", type=Path, help="use this real musegadget socket instead of the simulator")
    parser.add_argument("--send", action="store_true", help="with --muse-socket: actually post the notification")
    args = parser.parse_args(argv)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    plan = FaultPlan() if args.no_faults else DEFAULT_FAULTS

    # 2. Live loop: the twin's records over a damaged link, through the ingestion boundary.
    config = replace(SCENARIOS["clean"].configure(args.seed), acquisition=ACQUISITION_FLAGS)
    twin = PhysiologyTwin(config.twin)
    rig = SensorRig(twin, config.rig)
    link = SimulatedLink(TwinSource(twin, rig), plan)
    live = IngestingSource(link)
    result = run_closed_loop(live, TwinHapticActuator(twin, rig, config.actuate), ClosedLoopController(config.controller))
    run = session_run(config, result, twin, rig)
    report = live.report()
    export_run(run, out / "live", None, with_report=not args.no_report, extra_documents={"ingestion.json": dumps(report)})
    audit = audit_run(out / "live")
    direct = run_session(replace(config, acquisition=()))
    decisions = [(e.decision_time_us, e.action, e.decision_id) for e in result.evaluations if e.decision_id]
    direct_decisions = [(e.decision_time_us, e.action, e.decision_id) for e in direct.evaluations if e.decision_id]
    differing = sum(a.comparable() != b.comparable() for a, b in zip(result.evaluations, direct.evaluations))

    # 3. Recorded: the exported bundle through the same loop.
    recorded = RecordedSource(out / "live")
    replay_actuator = NullActuator()
    replayed = run_closed_loop(recorded, replay_actuator, ClosedLoopController(recorded.controller_config))
    comparison = recorded.compare(replayed, replay_actuator)

    # 1, 4, 5. The Muse gadget environment: discovery, the refused attempt, an operator notification.
    simulate = args.muse_socket is None
    with gadget(SimpleNamespace(simulate=simulate, socket=args.muse_socket, timeout=10.0)) as (client, provenance):
        muse_caps = discover(client)
        refusal = attempt(client, provenance, out / "muse-attempt", "MUSE-GADGET-ATTEMPT")
        notifier = OperatorNotifier(client, DEFAULT_SIDE_CHAT, provenance)
        values = notification_values(run_manifest_passport(out), REPLAY=f"independent audit {audit['replay_status']}")
        if simulate or args.send:
            delivery = notifier.notify("SESSION_COMPLETE", values).outcome
            (out / "operator-notifications.ndjson").write_text(
                "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in notifier.records), encoding="utf-8")
        else:
            delivery = "NOT_SENT_DRY_RUN"
    live_caps = live.capabilities().to_dict()
    capabilities = {"twin": TwinSource(twin, rig).capabilities().to_dict(), "twin_over_simulated_link": live_caps,
                    "recording": recorded.capabilities().to_dict(), "muse_gadget": muse_caps.to_dict()}
    (out / "capabilities.json").write_bytes(dumps(capabilities))

    # 6. Provenance of the first decision.
    provenance_answer = provenance_of_first_decision(out, live_caps)
    checks = {"audit_replay_match": audit["replay_status"] == "REPLAY_MATCH",
              "recorded_replay_matches": comparison["decisions_match"] and comparison["commands_match"],
              "muse_refused_by_input_contract": refusal["terminated"] == "INSUFFICIENT_EVIDENCE",
              "muse_offered_no_signals": not muse_caps.signals,
              "notification_outside_loop": delivery in ("DELIVERED_ACK", "NOT_SENT_DRY_RUN") if simulate else True}
    summary = {"provenance": "SIMULATED" if simulate else "SIMULATED_LOOP_REAL_GADGET_LINK", "seed": args.seed,
               "fault_plan": {k: v for k, v in plan.__dict__.items()},
               "live": {"decisions": decisions, "decisions_identical_to_direct_run": decisions == direct_decisions,
                        "evaluations_whose_evidence_differed_from_direct_run": differing,
                        "gate_failures": dict(sorted(Counter(r for e in result.evaluations for r in e.gate_reasons).items())),
                        "ingestion": {k: v for k, v in report.items() if k != "faults_detail"},
                        "audit": audit["replay_status"]},
               "recorded": comparison, "muse_gadget": {"capabilities": muse_caps.to_dict(), "refusal": refusal["refusal"],
                                                       "notification": delivery},
               "first_decision": provenance_answer, "checks": checks}
    (out / "summary.json").write_bytes(dumps(summary))

    print(f"CIRCLE acquisition demonstration (seed {args.seed}) -> {out}")
    print(f"  live loop      decisions {[(d[2], d[1]) for d in decisions]}; identical to the direct run: "
          f"{decisions == direct_decisions}; evaluations with impaired evidence: {differing}")
    print(f"                 link {report['link_states']}; faults {report['faults_by_kind']}; "
          f"host-declared gaps {report['host_declared_gaps']}")
    print(f"                 independent audit: {audit['replay_status']}")
    print(f"  recorded       decisions match: {comparison['decisions_match']}; commands match: {comparison['commands_match']}")
    print(f"  muse gadget    {muse_caps.connection_state}; signals offered: {len(muse_caps.signals)}; "
          f"closed loop: refused ({len(refusal['refusal'])} reasons, session in {out / 'muse-attempt'})")
    print(f"  operator       notification: {delivery} (outside the loop; never an intervention)")
    print("  provenance of the first decision:")
    for key, value in provenance_answer.items():
        print(f"    {key:<14} {value}")
    failed = [name for name, passed in checks.items() if not passed]
    print("  all checks passed" if not failed else f"  FAILED: {failed}")
    return 0 if not failed else 1


def run_manifest_passport(out: Path) -> dict[str, str]:
    return json.loads((out / "live/manifest.json").read_text(encoding="utf-8"))["passport"]


if __name__ == "__main__":
    raise SystemExit(main())
