"""The explicit, versioned mapping from the Muse Gadget SDK to CIRCLE's representation.

Two tables. REQUIRED_INPUTS walks everything CIRCLE's closed loop is built on,
named by evidence class (measured, derived, estimated, simulated), and states
what the Muse Gadget SDK can supply for each. SDK_SURFACE walks everything the
SDK exposes and states what CIRCLE may do with it.

Nothing maps to a physiological measurement, because the SDK measures none.
That limitation is the main entry here, not a footnote: CIRCLE never fills an
unsupported input with an estimate, an interpolation, or a simulation.

The mapping is data, versioned with the SDK revision it was checked against
(sdk.SDK_COMMIT). Re-inspect the SDK before changing it; tests pin every entry.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sdk import SDK_COMMIT

MAPPING_VERSION = "muse-gadget-mapping/1.0.0"

CLASSES = {
    "UNSUPPORTED": "CIRCLE needs it; the SDK cannot supply it, so nothing stands in for it.",
    "OPERATOR_NOTIFICATION": "Text from CIRCLE to the Muse chat. Outside the closed loop; never an intervention.",
    "AI_PROPOSAL": "A request from the Muse to CIRCLE. At most a proposal a named human must authorize.",
    "LINK_STATE": "An observation of the gadget link itself, never of a person.",
    "NOT_REACHABLE": "Exists in the SDK, but only the Muse VM can invoke it; local programs cannot read it.",
    "FORBIDDEN_ON_CIRCLE_HOST": "Would let the Muse bypass validation, authorization, and evidence integrity.",
    "NOT_IN_THIS_SDK": "Often assumed of products named Muse; absent from this SDK.",
}


@dataclass(frozen=True)
class Entry:
    name: str
    circle_class: str
    supplies: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "class": self.circle_class, "supplies": self.supplies, "reason": self.reason}


_NO_SENSOR = "no SDK board or Linux gadget exposes such a sensor to local programs"

# Everything the closed loop is built on, by evidence class.
REQUIRED_INPUTS = (
    Entry("measured:rev_b.eda.code", "UNSUPPORTED", "nothing",
          f"Electrodermal activity needs electrodes and an ADC; {_NO_SENSOR}."),
    Entry("measured:rev_b.ppg.red_counts,ir_counts", "UNSUPPORTED", "nothing",
          f"Photoplethysmography needs an optical front end at the skin; {_NO_SENSOR}."),
    Entry("measured:rev_b.imu.accel_gyro", "UNSUPPORTED", "nothing",
          f"Motion gating needs a body-worn inertial stream; {_NO_SENSOR}."),
    Entry("measured:lab.sync.pulse_index", "UNSUPPORTED", "nothing",
          "Clock mapping needs device timestamps against a laboratory reference; the SDK carries no sample clock, "
          "timestamps, or sequence numbers."),
    Entry("derived:physiology.hr_bpm,scl_us,scr_rate_per_min,resp_rate_bpm", "UNSUPPORTED", "nothing",
          "Derived only from the measured streams above, none of which exist here."),
    Entry("estimated:controller.arousal_index", "UNSUPPORTED", "nothing",
          "Estimated from heart rate and skin conductance with two-system agreement; with neither, there is no "
          "estimate, and none is substituted."),
    Entry("simulated:twin.*", "UNSUPPORTED", "nothing",
          "Simulation comes only from the twin and is labeled SIMULATED; a hardware adapter never simulates."),
)

# Everything the SDK exposes, and what CIRCLE may do with it.
SDK_SURFACE = (
    Entry("linux:local_socket send-user-msg", "OPERATOR_NOTIFICATION", "delivery acknowledgement",
          "The only SDK capability a local program can use. CIRCLE posts templated session outcomes to a side chat; "
          "an acknowledgement means the Muse service accepted a chat turn, not that a person read it."),
    Entry("linux:link.invoke", "AI_PROPOSAL", "requests from the Muse",
          "A gadget built on musegadget.link_client.LinkSession can advertise CIRCLE's command set "
          "(models/muse_gadget/commands.py): read capabilities, validate a protocol. Never authorize or execute."),
    Entry("linux:system.run,file.read,file.write", "FORBIDDEN_ON_CIRCLE_HOST", "nothing",
          "Shell and file access as the install account would let the Muse authorize protocols, rewrite evidence, or "
          "change review gates. Never run the stock command set as an account that can reach CIRCLE."),
    Entry("linux:device.health", "NOT_REACHABLE", "nothing",
          "Uptime, load, memory, disk, and board temperature of the gadget host, reported to the Muse VM. Not "
          "evidence about any person."),
    Entry("linux:service link state", "LINK_STATE", "local service reachability",
          "A probe shows whether a service is listening; whether it holds a live Muse session is visible only by "
          "sending a message."),
    Entry("esp32:sensors.read (SenseCAP Indicator CO2, tVOC index, temperature, humidity)", "NOT_REACHABLE", "nothing",
          "Environmental, not physiological; invoked only by the Muse VM; integer-second ages and no sample clock."),
    Entry("esp32:camera.capture, push-to-talk audio", "NOT_REACHABLE", "nothing",
          "Invoked by the Muse VM or the person at the device and sent to the Muse; never captured by CIRCLE."),
    Entry("esp32:display.draw_url, display.show_animation, voice.configure", "NOT_REACHABLE", "nothing",
          "Outputs the Muse VM drives. Not a timed, physically observed cue path, so never a CIRCLE intervention."),
    Entry("esp32:device.health, device.discover, device.ota", "NOT_REACHABLE", "nothing",
          "Board battery and power state, local network discovery, and firmware updates, invoked by the Muse VM. "
          "Not evidence about any person."),
    Entry("muse.eeg.* (EEG headbands sold under the Muse name)", "NOT_IN_THIS_SDK", "nothing",
          "Headband EEG belongs to a different product and SDK. Even with it, CIRCLE's controller needs "
          "electrodermal and cardiovascular agreement, which EEG does not provide."),
)


def required_input_support() -> dict[str, str]:
    """Each closed-loop input and what the Muse Gadget SDK supplies for it."""
    return {e.name: e.supplies for e in REQUIRED_INPUTS}


def document() -> dict[str, object]:
    return {"mapping_version": MAPPING_VERSION, "sdk_commit": SDK_COMMIT, "classes": CLASSES,
            "required_inputs": [e.to_dict() for e in REQUIRED_INPUTS],
            "sdk_surface": [e.to_dict() for e in SDK_SURFACE]}
