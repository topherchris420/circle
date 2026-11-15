/* CIRCLE adaptive audio synthesizer — renders the schedule from audio-engine.js.
 *
 * Original procedural synthesis: a soft detuned pad through a low-pass whose
 * cutoff follows brightness, a filtered noise bed whose gain follows intensity,
 * and an optional breathing-guidance swell. Everything routes through a master
 * gain that is hard-capped by the session's consented ceiling and a limiter.
 *
 * The engine is silent until a person enables it (consent), stops without
 * clicks when data goes missing, and never claims a physiological effect.
 */
(function (global) {
  "use strict";

  function AdaptiveSynth(engine) {
    this.engine = engine;           // CircleAudioEngine
    this.ctx = null;
    this.enabled = false;           // consent + user switch
    this.ceiling = 0.5;           // session max_gain; level never exceeds it
    this.userLevel = 1.0;         // multiplier 0..1 from the level slider
    this.breath = true;            // breathing guidance on by default
    this.schedule = null;
    this._nodes = null;
    this._lastPoint = null;
    this._log = [];                // parameter-change log for replay inspection
  }

  AdaptiveSynth.prototype.ensureContext = function () {
    if (this.ctx) { return this.ctx; }
    var AC = global.AudioContext || global.webkitAudioContext;
    if (!AC) { return null; }
    this.ctx = new AC();
    return this.ctx;
  };

  AdaptiveSynth.prototype._build = function () {
    var ctx = this.ctx;
    var master = ctx.createGain();
    master.gain.value = 0;
    var limiter = ctx.createDynamicsCompressor();
    limiter.threshold.value = -10; limiter.knee.value = 2; limiter.ratio.value = 12;
    limiter.attack.value = 0.005; limiter.release.value = 0.25;
    master.connect(limiter).connect(ctx.destination);

    // Pad: two detuned triangle oscillators through a low-pass.
    var padGain = ctx.createGain(); padGain.gain.value = 0;
    var filter = ctx.createBiquadFilter(); filter.type = "lowpass";
    filter.frequency.value = 440; filter.Q.value = 0.4;
    var o1 = ctx.createOscillator(); o1.type = "triangle"; o1.frequency.value = 174.6;
    var o2 = ctx.createOscillator(); o2.type = "triangle"; o2.frequency.value = 175.9;
    var panner = ctx.createStereoPanner ? ctx.createStereoPanner() : null;
    o1.connect(filter); o2.connect(filter);
    if (panner) { filter.connect(panner).connect(padGain).connect(master); }
    else { filter.connect(padGain).connect(master); }
    o1.start(); o2.start();

    // Noise bed: looped buffer through a band-pass, gain follows intensity.
    var noiseGain = ctx.createGain(); noiseGain.gain.value = 0;
    var band = ctx.createBiquadFilter(); band.type = "bandpass"; band.frequency.value = 520; band.Q.value = 0.8;
    var noise = ctx.createBufferSource();
    var buffer = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
    var data = buffer.getChannelData(0);
    var state = 1234567; // seeded LCG: the bed is reproducible per engine build
    for (var i = 0; i < data.length; i++) {
      state = (state * 1103515245 + 12345) & 0x7fffffff;
      data[i] = (state / 0x3fffffff - 1) * 0.5;
    }
    noise.buffer = buffer; noise.loop = true;
    noise.connect(band).connect(noiseGain).connect(master);
    noise.start();

    // Breathing guidance: a slow sine swell on its own gain.
    var breathGain = ctx.createGain(); breathGain.gain.value = 0;
    var bo = ctx.createOscillator(); bo.type = "sine"; bo.frequency.value = 261.6;
    var bo2 = ctx.createOscillator(); bo2.type = "sine"; bo2.frequency.value = 523.3;
    var boGain = ctx.createOscillator(); boGain.type = "sine"; boGain.frequency.value = 1 / 10;
    var boDepth = ctx.createGain(); boDepth.gain.value = 0;
    bo.connect(breathGain); bo2.connect(breathGain);
    boGain.connect(boDepth.gain);
    boDepth.connect(breathGain.gain);
    breathGain.connect(master);
    bo.start(); bo2.start(); boGain.start();

    this._nodes = { master: master, padGain: padGain, filter: filter, panner: panner,
                    noiseGain: noiseGain, breathGain: breathGain, boGain: boGain, boDepth: boDepth };
    return this._nodes;
  };

  /* Apply the interpolated parameters for session time t.
   * gainTime is the AudioContext time to ramp toward. */
  AdaptiveSynth.prototype.update = function (point, sessionTimeS, gainTime) {
    if (!this.ctx || !this._nodes) { return; }
    var nodes = this._nodes;
    var target = this.enabled ? (point ? point.level : 0) * this.userLevel : 0;
    var ramp = 0.6;
    nodes.master.gain.setTargetAtTime(Math.min(target, this.ceiling), gainTime, ramp);
    if (!point) { this._lastPoint = null; return; }
    var changed = !this._lastPoint || this._lastPoint.time_s !== point.time_s;
    nodes.filter.frequency.setTargetAtTime(220 + 2000 * point.brightness, gainTime, ramp);
    nodes.padGain.gain.setTargetAtTime(0.55, gainTime, ramp);
    nodes.noiseGain.gain.setTargetAtTime(0.12 * point.intensity, gainTime, ramp);
    if (nodes.panner) {
      nodes.panner.pan.setTargetAtTime((point.spatial - 0.5) * 1.2, gainTime, 1.2);
    }
    // Breathing guidance: sine swell whose frequency follows the guided period.
    var breathOn = this.enabled && this.breath && point.audible;
    var hz = 1 / Math.max(4, Math.min(20, point.breath_period_s));
    nodes.boGain.frequency.setTargetAtTime(hz, gainTime, ramp);
    nodes.boDepth.gain.setTargetAtTime(breathOn ? 0.16 : 0, gainTime, ramp);
    nodes.breathGain.gain.setTargetAtTime(breathOn ? 0.5 : 0, gainTime, ramp);
    if (changed) {
      this._log.push({ session_time_s: Number(sessionTimeS.toFixed(3)),
        audible: point.audible, level: Number(point.level.toFixed(4)),
        brightness: Number(point.brightness.toFixed(4)), tempo: Number(point.tempo.toFixed(4)),
        spatial: Number(point.spatial.toFixed(4)), breath_period_s: Number(point.breath_period_s.toFixed(3)),
        gate_reasons: point.gate_reasons });
      if (this._log.length > 5000) { this._log.shift(); }
      this._lastPoint = point;
    }
  };

  AdaptiveSynth.prototype.stop = function () {
    if (this._nodes && this.ctx) {
      this._nodes.master.gain.setTargetAtTime(0, this.ctx.currentTime, 0.25);
    }
  };

  AdaptiveSynth.prototype.state = function () {
    var point = this._lastPoint;
    return {
      enabled: this.enabled,
      muted_reasons: point ? point.gate_reasons : [],
      level: point ? point.level : 0
    };
  };

  global.CircleSynth = { AdaptiveSynth: AdaptiveSynth };
})(typeof window !== "undefined" ? window : globalThis);
