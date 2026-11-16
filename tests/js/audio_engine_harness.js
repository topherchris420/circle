/* Node harness for the CIRCLE audio scheduling engine (no browser needed).
 * Prints a JSON result document consumed by tests/test_resonance_assets.py.
 * Usage: node tests/js/audio_engine_harness.js
 */
"use strict";
const engine = require("../../models/workbench_assets/resonance/audio-engine.js");

function assert(condition, message) {
  if (!condition) { throw new Error("assertion failed: " + message); }
}

const events = [
  { time_us: 0, audible: true, gate_reasons: [], parameters: { intensity: 0.2, level: 0.3, brightness: 0.4, tempo: 0.9, spatial: 0.5, breath_period_s: 8 } },
  { time_us: 5e6, audible: false, gate_reasons: ["MOTION_EXCESSIVE"], parameters: { intensity: 0.2, level: 0.3, brightness: 0.4, tempo: 0.9, spatial: 0.5, breath_period_s: 8 } },
  { time_us: 10e6, audible: true, gate_reasons: [], parameters: { intensity: 0.8, level: 0.9, brightness: 0.9, tempo: 1.2, spatial: 0.8, breath_period_s: 7 } },
];

const out = {};

// 1. Schedule summary and bounds.
const schedule = engine.buildSchedule(events, { maxGain: 0.5 });
assert(schedule.summary.events === 3, "three events");
assert(schedule.summary.muted === 1, "one muted event");
assert(schedule.points[1].level === 0, "muted event level is zero");
assert(schedule.points.every((p) => p.level <= 0.5), "level bound holds");
assert(schedule.points.every((p) => p.intensity >= 0 && p.intensity <= 1), "intensity bound holds");
out.summary = schedule.summary;

// 2. Determinism: identical inputs yield identical schedules.
const again = engine.buildSchedule(events, { maxGain: 0.5 });
assert(JSON.stringify(schedule.points) === JSON.stringify(again.points), "schedule is deterministic");
out.deterministic = true;

// 3. Interpolation between events is bounded and continuous.
const atMuted = engine.interpolateAt(schedule, 5);
assert(atMuted.level === 0, "muted boundary has zero level");
const mid = engine.interpolateAt(schedule, 7.5);
assert(mid.level > 0 && mid.level <= 0.5, "recovery ramps back within bounds");
assert(engine.interpolateAt(schedule, 1.25).intensity === 0.2, "hold before boundary");
const late = engine.interpolateAt(schedule, 12);
assert(late.level > 0 && late.level <= 0.5, "late interpolation bounded");
out.interpolated_mid_level = mid.level;
out.interpolated_late_level = late.level;

// 4. Wild inputs are clamped to the safe envelope.
const wild = engine.buildSchedule([
  { time_us: 0, audible: true, gate_reasons: [], parameters: { intensity: 9, level: 5, brightness: 3, tempo: 9, spatial: 9, breath_period_s: 2 } },
], { maxGain: 0.4, breathPeriodMinS: 6, breathPeriodMaxS: 15 });
assert(wild.points[0].level <= 0.4, "level clamped to session ceiling");
assert(wild.points[0].intensity === 1, "intensity clamped to 1");
assert(wild.points[0].breath_period_s >= 6 && wild.points[0].breath_period_s <= 15, "breath period clamped");
out.clamped = wild.points[0];

// 5. Breathing phase is a deterministic function of session time.
const p1 = engine.breathPhase(schedule, 100);
const p2 = engine.breathPhase(schedule, 100);
assert(p1 === p2 && p1 >= 0 && p1 < 1, "breath phase deterministic and in [0,1)");
out.breath_phase = p1;

// 6. Measured inputs ride along with the schedule, never ahead of availability.
const withInputs = engine.buildSchedule([
  { time_us: 2e6, audible: true, gate_reasons: [], parameters: { level: 0.2 }, inputs: { hr_bpm: 70, scl_us: 4.2 } },
  { time_us: 4e6, audible: true, gate_reasons: [], parameters: { level: 0.2 }, inputs: { hr_bpm: 72, scl_us: 4.5 } },
  { time_us: 6e6, audible: true, gate_reasons: [], parameters: { level: 0.2 } },
], { maxGain: 0.5 });
assert(engine.interpolateAt(withInputs, 1).inputs === null, "no inputs before the first measurement");
assert(engine.interpolateAt(withInputs, 2).inputs.scl_us === 4.2, "inputs available at their event time");
assert(engine.interpolateAt(withInputs, 3.9).inputs.scl_us === 4.2, "latest available inputs, not the next ones");
assert(engine.interpolateAt(withInputs, 4).inputs.hr_bpm === 72, "inputs advance at the next event");
assert(engine.interpolateAt(withInputs, 9).inputs === null, "an event without inputs reports none");
assert(engine.interpolateAt(schedule, 7.5).inputs === null, "events without inputs interpolate cleanly");
out.inputs_respect_availability = true;

// 7. Empty schedule degrades gracefully.
assert(engine.interpolateAt({ points: [] }, 5) === null, "empty schedule returns null");
out.empty_ok = true;

console.log(JSON.stringify(out));
