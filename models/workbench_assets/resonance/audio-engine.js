/* CIRCLE adaptive audio engine — pure scheduling layer.
 *
 * This file contains no Web Audio API usage: it turns the deterministic
 * feedback parameter-event stream from the server into an interpolation
 * schedule that is a pure function of its inputs. The synthesizer
 * (synth.js) renders the schedule; tests import this file directly so
 * schedule determinism is checked without a browser.
 *
 * Bounds are enforced here as well as in the server: level never exceeds
 * maxGain, and the breathing period stays inside its configured range.
 */
(function (global) {
  "use strict";

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

  /* Build the interpolation schedule from feedback events.
   * events: [{time_us, audible, parameters: {intensity, level, brightness,
   *           tempo, spatial, breath_period_s}, gate_reasons: [...],
   *           inputs: {hr_bpm, scl_us, ...} (optional, the features read)}]
   * opts:   {maxGain, breathPeriodMinS, breathPeriodMaxS} (optional clamps)
   * Returns {points, summary} where points is sorted by time in seconds with
   * clamped parameters and a zero level for muted events. */
  function buildSchedule(events, opts) {
    opts = opts || {};
    var maxGain = typeof opts.maxGain === "number" ? opts.maxGain : 0.5;
    var bMin = typeof opts.breathPeriodMinS === "number" ? opts.breathPeriodMinS : 6.0;
    var bMax = typeof opts.breathPeriodMaxS === "number" ? opts.breathPeriodMaxS : 15.0;
    var points = [];
    var mutedCount = 0, maxLevel = 0, lastAudible = null;
    for (var i = 0; i < events.length; i++) {
      var e = events[i];
      var p = e.parameters || {};
      var audible = !!e.audible;
      var level = audible ? clamp(Number(p.level) || 0, 0, maxGain) : 0;
      var point = {
        time_s: e.time_us / 1e6,
        audible: audible,
        intensity: clamp(Number(p.intensity) || 0, 0, 1),
        level: level,
        brightness: clamp(Number(p.brightness) || 0, 0, 1),
        tempo: clamp(Number(p.tempo) || 1, 0.25, 2),
        spatial: clamp(Number(p.spatial) || 0, 0, 1),
        breath_period_s: clamp(Number(p.breath_period_s) || 10, bMin, bMax),
        gate_reasons: e.gate_reasons || [],
        inputs: e.inputs || null
      };
      if (!audible) mutedCount++;
      if (level > maxLevel) maxLevel = level;
      if (audible) lastAudible = point;
      points.push(point);
    }
    points.sort(function (a, b) { return a.time_s - b.time_s; });
    return {
      points: points,
      summary: {
        events: points.length,
        audible: points.length - mutedCount,
        muted: mutedCount,
        max_level: maxLevel,
        span_s: points.length ? [points[0].time_s, points[points.length - 1].time_s] : null
      }
    };
  }

  /* Linear interpolation of the schedule at session time t (seconds).
   * Before the first point the first point holds; after the last, the last.
   * `inputs` is never interpolated or read ahead: it is the measured feature
   * set of the latest event at or before t, and null before the first event,
   * so a readout never shows a measurement before it was available. */
  function interpolateAt(schedule, t) {
    var pts = schedule.points;
    if (!pts.length) { return null; }
    if (t <= pts[0].time_s) { return clone(pts[0], t, t === pts[0].time_s ? pts[0].inputs : null); }
    var last = pts[pts.length - 1];
    if (t >= last.time_s) { return clone(last, t, last.inputs); }
    var lo = 0, hi = pts.length - 1;
    while (hi - lo > 1) {
      var mid = (lo + hi) >> 1;
      if (pts[mid].time_s <= t) { lo = mid; } else { hi = mid; }
    }
    var a = pts[lo], b = pts[hi];
    var f = (t - a.time_s) / (b.time_s - a.time_s || 1);
    var out = { time_s: t, audible: a.audible || b.audible, gate_reasons: b.gate_reasons, inputs: a.inputs || null };
    var keys = ["intensity", "level", "brightness", "tempo", "spatial", "breath_period_s"];
    for (var k = 0; k < keys.length; k++) {
      var key = keys[k];
      out[key] = a[key] + (b[key] - a[key]) * f;
    }
    return out;
  }

  function clone(p, t, inputs) {
    var out = { time_s: t, audible: p.audible, gate_reasons: p.gate_reasons, inputs: inputs || null };
    var keys = ["intensity", "level", "brightness", "tempo", "spatial", "breath_period_s"];
    for (var i = 0; i < keys.length; i++) { out[keys[i]] = p[keys[i]]; }
    return out;
  }

  /* Breathing-guidance phase, 0..1 (0 = begin inhale, 0.5 = begin exhale).
   * Piecewise-constant period from the schedule: deterministic in session
   * time, independent of wall-clock, so replay reproduces it. */
  function breathPhase(schedule, t) {
    var pts = schedule.points;
    if (!pts.length) { return 0; }
    var period = 10, t0 = pts[0].time_s;
    var integrated = 0;
    for (var i = 0; i < pts.length; i++) {
      var start = pts[i].time_s;
      var end = (i + 1 < pts.length) ? pts[i + 1].time_s : Infinity;
      var p = pts[i].breath_period_s;
      if (t <= start) { break; }
      var segEnd = Math.min(t, end);
      integrated += (segEnd - start) / p;
      if (t <= end) { period = p; return (integrated % 1 + 1) % 1; }
      period = p;
    }
    return (integrated % 1 + 1) % 1;
  }

  var api = { buildSchedule: buildSchedule, interpolateAt: interpolateAt, breathPhase: breathPhase };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; }
  global.CircleAudioEngine = api;
})(typeof window !== "undefined" ? window : globalThis);
