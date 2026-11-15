/* CIRCLE audio rendering benchmark — measures the real Web Audio engine.
 *
 * Runs in any browser (or headless with --autoplay-policy=no-user-gesture-required).
 * It exercises the same AdaptiveSynth used by the workbench against a fixed,
 * deterministic schedule and measures: context start latency, output-timestamp
 * progression (underrun detection), rendered output level against the session
 * ceiling, stop ramp-down, and audio-clock to wall-clock offset (sound/visual
 * synchronization bound).
 *
 * Headless modes render through a null audio sink: these measurements describe
 * the browser's audio graph behavior, not audible quality on physical
 * speakers. The result JSON lands in #bench-result and document.title.
 */
(function () {
  "use strict";
  const engine = window.CircleAudioEngine;
  const synthMod = window.CircleSynth;

  const EVENTS = [
    { time_us: 0, audible: true, gate_reasons: [],
      parameters: { intensity: 0.25, level: 0.4, brightness: 0.4, tempo: 0.9, spatial: 0.5, breath_period_s: 10 } },
    { time_us: 4e6, audible: true, gate_reasons: [],
      parameters: { intensity: 0.75, level: 0.5, brightness: 0.9, tempo: 1.2, spatial: 0.8, breath_period_s: 7 } },
    { time_us: 8e6, audible: false, gate_reasons: ["MOTION_EXCESSIVE"],
      parameters: { intensity: 0.75, level: 0.5, brightness: 0.9, tempo: 1.2, spatial: 0.8, breath_period_s: 7 } },
  ];
  const CEILING = 0.5;

  function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

  async function run() {
    const result = { schema: "circle-audio-rendering-benchmark/1", environment: {} };
    console.log("[bench] starting");
    const synth = new synthMod.AdaptiveSynth(engine);
    synth.ceiling = CEILING;
    synth.userLevel = 1.0;
    const schedule = engine.buildSchedule(EVENTS, { maxGain: CEILING });
    result.schedule = schedule.summary;

    // 1. Context start latency: creation + resume to running.
    const t0 = performance.now();
    synth.ensureContext();
    if (synth.ctx && synth.ctx.state === "suspended") {
      // A headless or device-less host may never resolve resume(); race it so
      // the benchmark always reports rather than hanging.
      await Promise.race([synth.ctx.resume(), sleep(1500)]);
    }
    let running = false;
    while (performance.now() - t0 < 3000) {
      if (synth.ctx && synth.ctx.state === "running") { running = true; break; }
      await sleep(25);
    }
    result.start_latency_ms = Math.round(performance.now() - t0);
    result.context_running = running;
    console.log("[bench] context running:", running, result.start_latency_ms + "ms");
    if (!running) { return finish(result); }
    result.environment = { sample_rate: synth.ctx.sampleRate, base_latency_s: synth.ctx.baseLatency || null,
                          state: synth.ctx.state };

    // 2. Render for ~5 s: underruns via output-timestamp progression, and the
    //    real output level via an analyser on the master chain.
    const analyser = synth.ctx.createAnalyser();
    analyser.fftSize = 2048;
    synth._nodes.master.connect(analyser);
    synth.enabled = true;
    const tStart = synth.ctx.currentTime;
    let lastAudioTime = tStart, lastWall = performance.now(), underruns = 0, peakRms = 0;
    const buffer = new Float32Array(analyser.fftSize);
    const renderMs = 5000;
    const renderStart = performance.now();
    let iterations = 0;
    while (performance.now() - renderStart < renderMs) {
      await sleep(50);
      iterations += 1;
      const now = performance.now();
      const out = synth.ctx.getOutputTimestamp();
      const audioNow = out.contextTime != null ? out.contextTime : synth.ctx.currentTime;
      const advanced = audioNow - lastAudioTime;
      const wall = (now - lastWall) / 1000;
      // A stall: the audio clock advanced far less than wall time did.
      if (advanced < wall * 0.5) { underruns += 1; }
      lastAudioTime = audioNow; lastWall = now;
      analyser.getFloatTimeDomainData(buffer);
      let sum = 0;
      for (let i = 0; i < buffer.length; i++) { sum += buffer[i] * buffer[i]; }
      const rms = Math.sqrt(sum / buffer.length);
      if (rms > peakRms) { peakRms = rms; }
      // Drive the synth through the schedule in session time.
      const sessionT = ((performance.now() - t0 - 3000) / 1000) * 1.0;
      const point = engine.interpolateAt(schedule, Math.max(0, sessionT));
      synth.update(point, sessionT, synth.ctx.currentTime);
    }
    result.underruns = underruns;
    result.peak_output_rms = Number(peakRms.toFixed(5));
    result.within_ceiling = peakRms <= CEILING * 1.05 + 1e-6;
    result.audible_output = peakRms > 1e-4;

    // 3. Audio-clock to wall-clock offset: the bound on sound/visual sync.
    const out = synth.ctx.getOutputTimestamp();
    if (out.contextTime != null && out.performanceTime != null) {
      const now = performance.now();
      result.audio_visual_sync_offset_ms = Math.round(now - out.performanceTime);
    } else {
      result.audio_visual_sync_offset_ms = null;
    }

    // 4. Stop ramp-down: after stop(), the master gain must fall to silence.
    synth.stop();
    const stopStart = performance.now();
    let settled = false, settleMs = null;
    while (performance.now() - stopStart < 2500) {
      await sleep(100);
      if (synth._nodes.master.gain.value < 0.01) { settled = true; settleMs = Math.round(performance.now() - stopStart); break; }
    }
    result.stop_settled = settled;
    result.stop_settle_ms = settleMs;
    synth.enabled = false;
    return finish(result);
  }

  function finish(result) {
    result.completed_at = new Date().toISOString();
    const text = JSON.stringify(result);
    const pre = document.getElementById("bench-result");
    if (pre) { pre.textContent = text; }
    const status = document.getElementById("bench-status");
    if (status) { status.textContent = "Done."; }
    // The benchmark harness (or a person) can read the result from the page
    // title without DevTools tooling: real-time render, real audio clock.
    document.title = "BENCH-DONE " + text;
    return result;
  }

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", run); }
  else { run(); }
})();
