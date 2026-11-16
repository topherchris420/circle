/* CIRCLE First Light — the measurement, gates, controller, feedback, and evidence bundle.
 *
 * One implementation of docs/first-light.md, used unchanged by the live camera page,
 * the recorded-session replay, and the Node build of the committed evidence. The
 * independent second implementation is tools/verify_first_light.py (Python, standard
 * library only); it shares no code with this file and must reproduce every decision.
 *
 * Determinism: raw frames are integers (time in microseconds; channel means in
 * milli-units). Analysis uses only IEEE-754 +, -, *, / and sqrt, in the order the
 * specification writes them, so both implementations compute the same doubles.
 */
(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) { module.exports = factory(); }
  else { root.FirstLight = factory(); }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const CORE_VERSION = "first-light-core/1.0.0";

  // The published algorithm. Must equal ALGORITHM in tools/verify_first_light.py, key for key.
  const ALGORITHM = Object.freeze({
    id: "first-light-algorithm/1",
    grid_hz: 50,
    window_us: 8000000,
    step_us: 1000000,
    first_eval_us: 9000000,
    highpass_len: 75,
    lowpass_len: 7,
    lag_min: 15,
    lag_max: 75,
    harmonic_ratio: 0.7,
    min_frames: 120,
    max_gap_us: 250000,
    contact_red_min: 100000,
    contact_red_permille: 550,
    green_min: 5000,
    green_max: 250000,
    step_max: 0.05,
    periodicity_min: 0.65,
    rate_min_bpm: 50.0,
    rate_max_bpm: 180.0,
  });

  const FEEDBACK = Object.freeze({
    id: "first-light-feedback/1",
    max_level: 0.3,
    fade_steps: 3,
    tempo_slew_bpm: 6.0,
    brightness_low_bpm: 50.0,
    brightness_span_bpm: 70.0,
  });

  const CRITERIA_ID = "first-light-criteria/2";
  const GATES = ["FRAMES", "CONTACT", "EXPOSURE", "STEADY", "PERIODIC", "RATE"];

  const REASON_TEXT = {
    TOO_FEW_FRAMES: "too few camera frames in the last 8 s",
    FRAME_GAP: "the camera stalled for more than 250 ms",
    NO_CONTACT: "a frame was not a lit fingertip: dark or not red-dominant",
    UNDEREXPOSED: "the image is too dark to read",
    SATURATED: "the image is saturated",
    UNSTEADY: "the light level jumped: pressure, movement, or a light change",
    NOT_PERIODIC: "no steady pulse rhythm",
    IMPLAUSIBLE_RATE: "the rhythm is outside 50–180 bpm",
    AWAITING_CLEAN_WINDOW: "waiting for a full 8 s window that starts after the last failure",
  };

  // ------------------------------------------------------------------ analysis
  function contact(r, g, b) {
    return r >= ALGORITHM.contact_red_min && 1000 * r >= ALGORITHM.contact_red_permille * (r + g + b);
  }

  function movingAverage(values, length) {
    const half = Math.floor(length / 2);
    const n = values.length;
    const prefix = new Array(n + 1);
    prefix[0] = 0.0;
    for (let i = 0; i < n; i++) { prefix[i + 1] = prefix[i] + values[i]; }
    const out = new Array(n);
    for (let j = 0; j < n; j++) {
      const a = j - half > 0 ? j - half : 0;
      const b = j + half < n - 1 ? j + half : n - 1;
      out[j] = (prefix[b + 1] - prefix[a]) / (b - a + 1);
    }
    return out;
  }

  /** Waveform used for rate: detrended, smoothed, inverted green (systole up). */
  function pulseWaveform(grid) {
    const trend = movingAverage(grid, ALGORITHM.highpass_len);
    const detrended = new Array(grid.length);
    for (let j = 0; j < grid.length; j++) { detrended[j] = grid[j] - trend[j]; }
    const smooth = movingAverage(detrended, ALGORITHM.lowpass_len);
    const half = Math.floor(ALGORITHM.highpass_len / 2);
    const z = [];
    for (let j = half; j < smooth.length - half; j++) { z.push(-smooth[j]); }
    return z;
  }

  function pulseRate(grid) {
    const cfg = ALGORITHM;
    const z = pulseWaveform(grid);
    const n = z.length;
    const r = {};
    for (let lag = cfg.lag_min - 1; lag <= cfg.lag_max + 1; lag++) {
      let sab = 0.0, saa = 0.0, sbb = 0.0;
      for (let i = 0; i < n - lag; i++) {
        const a = z[i];
        const b = z[i + lag];
        sab += a * b;
        saa += a * a;
        sbb += b * b;
      }
      const den = Math.sqrt(saa * sbb);
      r[lag] = den > 0 ? sab / den : 0.0;
    }
    const candidates = [];
    for (let lag = cfg.lag_min; lag <= cfg.lag_max; lag++) {
      if (r[lag] > r[lag - 1] && r[lag] >= r[lag + 1]) { candidates.push(lag); }
    }
    if (!candidates.length) { return { rate: null, periodicity: null }; }
    let best = -Infinity;
    for (const lag of candidates) { if (r[lag] > best) { best = r[lag]; } }
    if (best <= 0) { return { rate: null, periodicity: best }; }
    const bar = cfg.harmonic_ratio * best;
    let lag = null;
    for (const c of candidates) { if (r[c] >= bar) { lag = c; break; } }
    const den = r[lag - 1] - 2 * r[lag] + r[lag + 1];
    const delta = den < 0 ? 0.5 * (r[lag - 1] - r[lag + 1]) / den : 0.0;
    return { rate: 60 * cfg.grid_hz / (lag + delta), periodicity: r[lag] };
  }

  /** Evaluate the window ending at cutoff; frames[0..end) are the frames at or before it.
   *  frames is an array of [t_us, r, g, b] integer tuples. */
  function evaluate(frames, end, cutoff) {
    const cfg = ALGORITHM;
    const start = cutoff - cfg.window_us;
    let lo = end;
    while (lo > 0 && frames[lo - 1][0] >= start) { lo--; }
    const count = end - lo;
    const gates = {};
    for (const name of GATES) { gates[name] = null; }
    const features = { frames: count, max_gap_us: null, out_of_contact: null, red_permille_min: null,
      green_block_min: null, green_block_max: null, step: null, periodicity: null, rate_bpm: null };
    const reasons = [];
    if (count > 0) {
      let gap = Math.max(frames[lo][0] - start, cutoff - frames[end - 1][0]);
      for (let i = lo; i < end - 1; i++) { const d = frames[i + 1][0] - frames[i][0]; if (d > gap) { gap = d; } }
      features.max_gap_us = gap;
    }
    const framesOk = count >= cfg.min_frames && features.max_gap_us !== null && features.max_gap_us <= cfg.max_gap_us;
    gates.FRAMES = framesOk ? "pass" : "fail";
    if (!framesOk) {
      reasons.push(count > 0 && count >= cfg.min_frames ? "FRAME_GAP" : "TOO_FEW_FRAMES");
      return { gates: gates, features: features, reasons: reasons };
    }

    let out = 0;
    let permille = Infinity;
    for (let i = lo; i < end; i++) {
      const f = frames[i];
      if (!contact(f[1], f[2], f[3])) { out++; }
      const total = f[1] + f[2] + f[3];
      const p = total ? Math.floor((1000 * f[1]) / total) : 0;
      if (p < permille) { permille = p; }
    }
    features.out_of_contact = out;
    features.red_permille_min = permille;
    gates.CONTACT = out === 0 ? "pass" : "fail";
    if (out) { reasons.push("NO_CONTACT"); }

    const sums = [0, 0, 0, 0, 0, 0, 0, 0];
    const counts = [0, 0, 0, 0, 0, 0, 0, 0];
    for (let i = lo; i < end; i++) {
      let block = Math.floor((frames[i][0] - start) / 1000000);
      if (block > 7) { block = 7; }
      sums[block] += frames[i][2];
      counts[block] += 1;
    }
    const means = sums.map(function (s, k) { return s / counts[k]; });
    features.green_block_min = Math.min.apply(null, means);
    features.green_block_max = Math.max.apply(null, means);
    let under = false, over = false;
    for (let k = 0; k < 8; k++) {
      if (sums[k] < cfg.green_min * counts[k]) { under = true; }
      if (sums[k] > cfg.green_max * counts[k]) { over = true; }
    }
    gates.EXPOSURE = under || over ? "fail" : "pass";
    if (under) { reasons.push("UNDEREXPOSED"); }
    if (over) { reasons.push("SATURATED"); }

    let total = 0, n = 0;
    for (let k = 0; k < 8; k++) { total += sums[k]; n += counts[k]; }
    const mean = total / n;
    let jump = 0;
    for (let k = 0; k < 7; k++) { const d = Math.abs(means[k + 1] - means[k]); if (d > jump) { jump = d; } }
    const step = mean > 0 ? jump / mean : Infinity;
    features.step = Number.isFinite(step) ? step : null;
    gates.STEADY = step <= cfg.step_max ? "pass" : "fail";
    if (gates.STEADY === "fail") { reasons.push("UNSTEADY"); }

    const grid = resample(frames, lo, end, cutoff);
    const pr = pulseRate(grid);
    features.periodicity = pr.periodicity;
    features.rate_bpm = pr.rate;
    gates.PERIODIC = pr.periodicity !== null && pr.periodicity >= cfg.periodicity_min ? "pass" : "fail";
    if (gates.PERIODIC === "fail") { reasons.push("NOT_PERIODIC"); }
    gates.RATE = pr.rate !== null && cfg.rate_min_bpm <= pr.rate && pr.rate <= cfg.rate_max_bpm ? "pass" : "fail";
    if (gates.RATE === "fail") { reasons.push("IMPLAUSIBLE_RATE"); }
    return { gates: gates, features: features, reasons: reasons };
  }

  function resample(frames, lo, end, cutoff) {
    const period = Math.floor(1000000 / ALGORITHM.grid_hz);
    const m = Math.floor(ALGORITHM.window_us / period);
    const grid = new Array(m);
    let a = lo > 0 ? lo - 1 : 0;
    for (let j = 0; j < m; j++) {
      const when = cutoff - (m - 1 - j) * period;
      while (a + 1 < end && frames[a + 1][0] <= when) { a++; }
      const ta = frames[a][0], va = frames[a][2];
      if (a + 1 < end && ta < when) {
        const tb = frames[a + 1][0], vb = frames[a + 1][2];
        grid[j] = va + (vb - va) * ((when - ta) / (tb - ta));
      } else {
        grid[j] = va;
      }
    }
    return grid;
  }

  // ------------------------------------------------------------------ controller and feedback
  function fmt(x, digits) { return x === null || x === undefined ? "—" : Number(x).toFixed(digits); }

  function why(decision, result) {
    const f = result.features;
    if (decision.decision === "ACT") {
      return "Acted: every gate passed on the last 8 s (periodicity " + fmt(f.periodicity, 2) + " ≥ " +
        ALGORITHM.periodicity_min + ", step " + fmt(f.step, 3) + " ≤ " + ALGORITHM.step_max +
        ", " + f.frames + " frames in contact). Pulse " + fmt(f.rate_bpm, 1) + " bpm drives the sound.";
    }
    const text = decision.reasons.map(function (code) { return REASON_TEXT[code] || code; });
    return "Refused: " + text.join("; ") + ". The sound is silent and no pulse is reported.";
  }

  /** Incremental session: feed frames as they arrive; evaluations happen on schedule. */
  function Session(options) {
    this.frames = [];
    this.decisions = [];
    this.feedback = [];
    this.state = "ACQUIRING";
    this.lastFail = null;
    this.tempo = null;
    this.level = 0.0;
    this.k = 0;
    this.onDecision = (options && options.onDecision) || null;
  }

  Session.prototype.addFrame = function (t, r, g, b) {
    const frames = this.frames;
    if (frames.length && t <= frames[frames.length - 1][0]) { return false; }
    frames.push([t, r, g, b]);
    const t0 = frames[0][0];
    for (;;) {
      const nominal = t0 + ALGORITHM.first_eval_us + this.k * ALGORITHM.step_us;
      if (t < nominal) { break; }
      // All frames at or before `nominal` have arrived; the cutoff is the last of them.
      const end = t === nominal ? frames.length : frames.length - 1;
      this._evaluate(nominal, end);
    }
    return true;
  };

  Session.prototype._evaluate = function (nominal, end) {
    const frames = this.frames;
    const cutoff = frames[end - 1][0];
    const result = evaluate(frames, end, cutoff);
    const passed = GATES.every(function (name) { return result.gates[name] === "pass"; });
    const fresh = this.lastFail === null || cutoff - ALGORITHM.window_us >= this.lastFail;
    const reasons = result.reasons.slice();
    let decision, rate;
    if (passed && fresh) {
      decision = "ACT";
      this.state = "ADAPTING";
      rate = result.features.rate_bpm;
    } else {
      if (!passed) { this.lastFail = cutoff; } else { reasons.push("AWAITING_CLEAN_WINDOW"); }
      decision = "REFUSE";
      this.state = this.state === "ACQUIRING" ? "ACQUIRING" : "REFUSING";
      rate = null;
    }
    const record = { k: this.k, nominal_us: nominal, cutoff_us: cutoff, decision: decision, state: this.state,
      gates: result.gates, reasons: reasons, features: result.features, rate_bpm: rate };
    record.why = why(record, result);
    const fb = FEEDBACK;
    let command;
    if (decision === "ACT") {
      if (this.tempo === null) { this.tempo = rate; }
      else {
        const change = rate - this.tempo;
        const limit = fb.tempo_slew_bpm;
        this.tempo = this.tempo + (change > limit ? limit : change < -limit ? -limit : change);
      }
      this.level = Math.min(fb.max_level, this.level + fb.max_level / fb.fade_steps);
      let brightness = (this.tempo - fb.brightness_low_bpm) / fb.brightness_span_bpm;
      brightness = brightness < 0 ? 0.0 : brightness > 1 ? 1.0 : brightness;
      command = { k: this.k, t_us: cutoff, audible: true, level: this.level, tempo_bpm: this.tempo, brightness: brightness };
    } else {
      this.tempo = null;
      this.level = 0.0;
      command = { k: this.k, t_us: cutoff, audible: false, level: 0.0, tempo_bpm: null, brightness: null };
    }
    this.decisions.push(record);
    this.feedback.push(command);
    this.k += 1;
    if (this.onDecision) { this.onDecision(record, command, result); }
  };

  /** The live pulse waveform over the most recent window, for display only (not evidence). */
  Session.prototype.waveform = function () {
    const frames = this.frames;
    if (frames.length < 2) { return null; }
    const cutoff = frames[frames.length - 1][0];
    if (cutoff - frames[0][0] < ALGORITHM.window_us) { return null; }
    let lo = frames.length;
    while (lo > 0 && frames[lo - 1][0] >= cutoff - ALGORITHM.window_us) { lo--; }
    return pulseWaveform(resample(frames, lo, frames.length, cutoff));
  };

  function runFrames(frames) {
    const session = new Session();
    for (const f of frames) { session.addFrame(f[0], f[1], f[2], f[3]); }
    return session;
  }

  // ------------------------------------------------------------------ evidence encoding
  function framesCsv(frames) {
    const lines = ["t_us,r,g,b"];
    for (const f of frames) { lines.push(f[0] + "," + f[1] + "," + f[2] + "," + f[3]); }
    return lines.join("\n") + "\n";
  }

  function parseFramesCsv(text) {
    const lines = text.split("\n");
    if (lines[0] !== "t_us,r,g,b") { throw new Error("frames.csv must start with t_us,r,g,b"); }
    const out = [];
    for (let i = 1; i < lines.length; i++) {
      if (!lines[i]) { continue; }
      const p = lines[i].split(",");
      out.push([parseInt(p[0], 10), parseInt(p[1], 10), parseInt(p[2], 10), parseInt(p[3], 10)]);
    }
    return out;
  }

  function utf8(text) { return new TextEncoder().encode(text); }

  const K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);

  /** SHA-256 of a Uint8Array, as lowercase hex (synchronous; works on file:// and in Node). */
  function sha256(bytes) {
    const h = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
    const length = bytes.length;
    const padded = new Uint8Array(((length + 9 + 63) >> 6) << 6);
    padded.set(bytes);
    padded[length] = 0x80;
    const bits = length * 8;
    const view = new DataView(padded.buffer);
    view.setUint32(padded.length - 8, Math.floor(bits / 0x100000000));
    view.setUint32(padded.length - 4, bits >>> 0);
    const w = new Uint32Array(64);
    for (let offset = 0; offset < padded.length; offset += 64) {
      for (let i = 0; i < 16; i++) { w[i] = view.getUint32(offset + i * 4); }
      for (let i = 16; i < 64; i++) {
        const x = w[i - 15], y = w[i - 2];
        const s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3);
        const s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
      }
      let a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], k = h[7];
      for (let i = 0; i < 64; i++) {
        const S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        const ch = (e & f) ^ (~e & g);
        const t1 = (k + S1 + ch + K[i] + w[i]) >>> 0;
        const S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        const maj = (a & b) ^ (a & c) ^ (b & c);
        const t2 = (S0 + maj) >>> 0;
        k = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      h[0] = (h[0] + a) >>> 0; h[1] = (h[1] + b) >>> 0; h[2] = (h[2] + c) >>> 0; h[3] = (h[3] + d) >>> 0;
      h[4] = (h[4] + e) >>> 0; h[5] = (h[5] + f) >>> 0; h[6] = (h[6] + g) >>> 0; h[7] = (h[7] + k) >>> 0;
    }
    let hex = "";
    for (let i = 0; i < 8; i++) { hex += ("00000000" + h[i].toString(16)).slice(-8); }
    return hex;
  }

  let CRC_TABLE = null;
  function crc32(bytes) {
    if (!CRC_TABLE) {
      CRC_TABLE = new Uint32Array(256);
      for (let n = 0; n < 256; n++) {
        let c = n;
        for (let k = 0; k < 8; k++) { c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; }
        CRC_TABLE[n] = c >>> 0;
      }
    }
    let crc = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) { crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8); }
    return (crc ^ 0xffffffff) >>> 0;
  }

  /** A deterministic, uncompressed (STORE) zip: fixed 1980-01-01 timestamps, entries in the given order. */
  function zip(entries) {
    const parts = [];
    const central = [];
    let offset = 0;
    for (const entry of entries) {
      const name = utf8(entry.name);
      const data = entry.data;
      const crc = crc32(data);
      const local = new DataView(new ArrayBuffer(30));
      local.setUint32(0, 0x04034b50, true); local.setUint16(4, 20, true); local.setUint16(6, 0x0800, true);
      local.setUint16(8, 0, true); local.setUint16(10, 0, true); local.setUint16(12, 0x0021, true);
      local.setUint32(14, crc, true); local.setUint32(18, data.length, true); local.setUint32(22, data.length, true);
      local.setUint16(26, name.length, true); local.setUint16(28, 0, true);
      parts.push(new Uint8Array(local.buffer), name, data);
      const dir = new DataView(new ArrayBuffer(46));
      dir.setUint32(0, 0x02014b50, true); dir.setUint16(4, 20, true); dir.setUint16(6, 20, true);
      dir.setUint16(8, 0x0800, true); dir.setUint16(10, 0, true); dir.setUint16(12, 0, true);
      dir.setUint16(14, 0x0021, true); dir.setUint32(16, crc, true); dir.setUint32(20, data.length, true);
      dir.setUint32(24, data.length, true); dir.setUint16(28, name.length, true);
      dir.setUint32(42, offset, true);
      central.push(new Uint8Array(dir.buffer), name);
      offset += 30 + name.length + data.length;
    }
    let size = 0;
    for (const c of central) { size += c.length; }
    const eocd = new DataView(new ArrayBuffer(22));
    eocd.setUint32(0, 0x06054b50, true); eocd.setUint16(8, entries.length, true); eocd.setUint16(10, entries.length, true);
    eocd.setUint32(12, size, true); eocd.setUint32(16, offset, true);
    const all = parts.concat(central, [new Uint8Array(eocd.buffer)]);
    let total = 0;
    for (const p of all) { total += p.length; }
    const out = new Uint8Array(total);
    let at = 0;
    for (const p of all) { out.set(p, at); at += p.length; }
    return out;
  }

  /** Read entries from a STORE or uncompressed zip produced by zip() (enough to inspect a bundle in the page). */
  function unzip(bytes) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let end = bytes.length - 22;
    while (end >= 0 && view.getUint32(end, true) !== 0x06054b50) { end--; }
    if (end < 0) { throw new Error("not a zip file"); }
    const count = view.getUint16(end + 10, true);
    let at = view.getUint32(end + 16, true);
    const files = {};
    for (let i = 0; i < count; i++) {
      const method = view.getUint16(at + 10, true);
      const size = view.getUint32(at + 20, true);
      const nameLength = view.getUint16(at + 28, true);
      const extra = view.getUint16(at + 30, true);
      const comment = view.getUint16(at + 32, true);
      const local = view.getUint32(at + 42, true);
      const name = new TextDecoder().decode(bytes.subarray(at + 46, at + 46 + nameLength));
      if (method !== 0) { throw new Error(name + ": compressed entries are not supported in the page; use the Python verifier"); }
      const dataAt = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true);
      files[name] = bytes.subarray(dataAt, dataAt + size);
      at += 46 + nameLength + extra + comment;
    }
    return files;
  }

  /** Build the evidence bundle. options: {mode, reference, device, created, core_sha256}. */
  function bundle(session, options) {
    const protocol = { schema: "circle-first-light-protocol/1", mode: options.mode,
      algorithm: ALGORITHM, feedback: FEEDBACK, criteria: CRITERIA_ID };
    const files = [
      ["protocol.json", JSON.stringify(protocol, null, 1) + "\n"],
      ["raw/frames.csv", framesCsv(session.frames)],
      ["decisions.json", JSON.stringify(session.decisions) + "\n"],
      ["feedback.json", JSON.stringify(session.feedback) + "\n"],
    ];
    if (options.reference) { files.push(["reference.json", JSON.stringify(options.reference) + "\n"]); }
    if (options.device) { files.push(["device.json", JSON.stringify(options.device, null, 1) + "\n"]); }
    if (options.marks) { files.push(["raw/marks.csv", "t_us,step\n" + options.marks.map(function (m) { return m[0] + "," + m[1]; }).join("\n") + "\n"]); }
    const encoded = files.map(function (f) { return { name: f[0], data: utf8(f[1]) }; });
    const listed = {};
    for (const e of encoded) { listed[e.name] = { sha256: sha256(e.data), bytes: e.data.length }; }
    const manifest = { schema: "circle-first-light-bundle/1", created: options.created || null,
      software: { core: CORE_VERSION, core_sha256: options.core_sha256 || null }, files: listed,
      note: "Hashes detect change; they do not authenticate where the frames came from. " +
        "Verify independently with tools/verify_first_light.py." };
    const manifestBytes = utf8(JSON.stringify(manifest, null, 1) + "\n");
    const entries = [{ name: "manifest.json", data: manifestBytes }].concat(encoded);
    return { zip: zip(entries), manifest: manifest, manifest_sha256: sha256(manifestBytes) };
  }

  // ------------------------------------------------------------------ self-check (same code; not independent)
  /** Re-run the bundle's raw frames through this implementation and compare. The page labels this a
   *  self-check: it proves the record is internally consistent, not that a second implementation agrees. */
  function selfCheck(files) {
    const problems = [];
    const manifest = JSON.parse(new TextDecoder().decode(files["manifest.json"]));
    for (const name of Object.keys(manifest.files)) {
      if (!files[name]) { problems.push(name + " is missing"); continue; }
      if (sha256(files[name]) !== manifest.files[name].sha256) { problems.push(name + " does not match its SHA-256"); }
    }
    if (problems.length) { return { integrity: "INTEGRITY_FAILURE", problems: problems }; }
    const frames = parseFramesCsv(new TextDecoder().decode(files["raw/frames.csv"]));
    const replay = runFrames(frames);
    const recorded = JSON.parse(new TextDecoder().decode(files["decisions.json"]));
    if (recorded.length !== replay.decisions.length) { problems.push("evaluation count differs"); }
    for (let i = 0; i < Math.min(recorded.length, replay.decisions.length); i++) {
      if (recorded[i].decision !== replay.decisions[i].decision ||
          JSON.stringify(recorded[i].reasons) !== JSON.stringify(replay.decisions[i].reasons)) {
        problems.push("evaluation " + i + " differs");
        if (problems.length > 5) { break; }
      }
    }
    return { integrity: "INTEGRITY_OK", replay: problems.length ? "REPLAY_DIVERGENCE" : "REPLAY_MATCH",
      problems: problems, evaluations: replay.decisions.length };
  }

  return {
    CORE_VERSION: CORE_VERSION, ALGORITHM: ALGORITHM, FEEDBACK: FEEDBACK, CRITERIA_ID: CRITERIA_ID, GATES: GATES,
    REASON_TEXT: REASON_TEXT, contact: contact, evaluate: evaluate, pulseRate: pulseRate, Session: Session,
    runFrames: runFrames, framesCsv: framesCsv, parseFramesCsv: parseFramesCsv, sha256: sha256, crc32: crc32,
    zip: zip, unzip: unzip, bundle: bundle, selfCheck: selfCheck, utf8: utf8,
  };
});
