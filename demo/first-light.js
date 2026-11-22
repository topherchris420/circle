/* CIRCLE First Light — page controller.
 * Sources (a real recording, the camera, the phantom) feed integer frames into
 * FirstLight.Session (first-light-core.js). This file only draws, plays the bounded sound,
 * guides the live protocol, and packages the evidence. It makes no decision of its own.
 * Nothing is uploaded: there is no network call except loading this page's own files.
 */
(function () {
  "use strict";
  const FL = window.FirstLight;
  const $ = function (id) { return document.getElementById(id); };
  const CONDITIONS = { "0": "at rest", "1": "pressing harder on the lens", "2": "moving the finger on the lens",
    "3": "walking", "4": "coughing", "5": "laughing", "6": "changing the light", "7": "talking" };
  const GATE_TEXT = {
    FRAMES: function (f) { return f.frames + " frames" + (f.max_gap_us === null ? "" : ", longest gap " + Math.round(f.max_gap_us / 1000) + " ms") + " (need 120, 250 ms)"; },
    CONTACT: function (f) { return f.out_of_contact === null ? "not checked" : f.out_of_contact + " frames out of contact (need 0)"; },
    EXPOSURE: function (f) { return f.green_block_min === null ? "not checked" : "green " + (f.green_block_min / 1000).toFixed(0) + "–" + (f.green_block_max / 1000).toFixed(0) + " of 255 (need 5–250)"; },
    STEADY: function (f) { return f.step === null ? "not checked" : "largest jump " + (f.step * 100).toFixed(1) + "% (limit 5%)"; },
    PERIODIC: function (f) { return f.periodicity === null ? "not checked" : "periodicity " + f.periodicity.toFixed(2) + " (need 0.65)"; },
    RATE: function (f) { return f.rate_bpm === null ? "not checked" : f.rate_bpm.toFixed(1) + " bpm (need 50–180)"; },
  };

  const app = { mode: "recorded", running: false, session: null, source: null, marks: [], reference: null,
    last: null, command: null, lit: {}, step: null, coreSha: null, recordingName: null, rows: [], sawAct: false };

  // ------------------------------------------------------------------ small helpers
  function notice(text) { const n = $("notice"); n.hidden = !text; n.textContent = text || ""; }
  function light(step) {
    if (app.lit[step]) { return; }
    app.lit[step] = true;
    const li = document.querySelector('#chain [data-step="' + step + '"]');
    if (li) { li.classList.add("lit"); }
  }
  function seconds(us) { return (us / 1e6).toFixed(1) + " s"; }
  function ecgRate(qrs, start, end) {
    // Display only: the verdict against ECG is computed by tools/verify_first_light.py.
    const beats = qrs.filter(function (t) { return t >= start && t <= end; });
    if (beats.length < 5) { return null; }
    const gaps = [];
    for (let i = 0; i + 1 < beats.length; i++) { gaps.push(beats[i + 1] - beats[i]); }
    gaps.sort(function (a, b) { return a - b; });
    const n = gaps.length;
    const median = n % 2 ? gaps[(n - 1) / 2] : (gaps[n / 2 - 1] + gaps[n / 2]) / 2;
    return 60000000 / median;
  }
  function segmentAt(t) {
    if (!app.reference || !app.reference.segments) { return null; }
    for (const s of app.reference.segments) { if (t >= s.start_us && t <= s.end_us) { return s; } }
    return null;
  }

  // ------------------------------------------------------------------ sound (bounded, opt-in)
  const sound = { ctx: null, master: null, on: false, next: 0 };
  function soundToggle() {
    sound.on = !sound.on;
    if (sound.on && !sound.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) { sound.on = false; notice("This browser has no Web Audio; the visual ring still follows the pulse."); }
      else { sound.ctx = new AC(); sound.master = sound.ctx.createGain(); sound.master.gain.value = 0; sound.master.connect(sound.ctx.destination); }
    }
    if (sound.ctx) { sound.ctx.resume(); if (!sound.on) { sound.master.gain.setTargetAtTime(0, sound.ctx.currentTime, 0.02); } }
    $("sound").setAttribute("aria-pressed", String(sound.on));
    $("sound").textContent = sound.on ? "Sound on" : "Sound off";
  }
  function soundApply(command) {
    if (!sound.ctx) { return; }
    const now = sound.ctx.currentTime;
    const audible = sound.on && command && command.audible && realTime();
    // A refusal silences within tens of milliseconds, including any note still ringing.
    sound.master.gain.cancelScheduledValues(now);
    sound.master.gain.setTargetAtTime(audible ? 1 : 0, now, 0.02);
    if (audible && sound.next < now) { sound.next = now + 0.05; }
  }
  function soundTick() {
    const c = app.command;
    if (!sound.ctx || !sound.on || !c || !c.audible || !realTime()) { return; }
    const period = 60 / c.tempo_bpm;
    while (sound.next < sound.ctx.currentTime + 0.2) {
      const t = Math.max(sound.next, sound.ctx.currentTime + 0.01);
      const osc = sound.ctx.createOscillator();
      const env = sound.ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = 180 + 240 * c.brightness;
      env.gain.setValueAtTime(0.0001, t);
      env.gain.exponentialRampToValueAtTime(Math.min(FL.FEEDBACK.max_level, c.level), t + 0.02);
      env.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
      osc.connect(env); env.connect(sound.master);
      osc.start(t); osc.stop(t + 0.25);
      sound.next += period;
    }
  }
  function realTime() { return app.mode !== "recorded" || $("speed").value === "1"; }

  // ------------------------------------------------------------------ drawing
  function drawRing(ts) {
    const ring = $("ring");
    const c = app.command;
    const still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let scale = 1;
    if (c && c.audible && !still) {
      const phase = ((ts / 1000) * c.tempo_bpm / 60) % 1;
      scale = 1 + 0.07 * (c.level / FL.FEEDBACK.max_level) * Math.exp(-6 * phase);
    }
    ring.style.transform = "scale(" + scale.toFixed(4) + ")";
  }
  function drawWave() {
    const canvas = $("wave");
    const g = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    g.clearRect(0, 0, w, h);
    g.strokeStyle = "rgba(255,255,255,0.08)"; g.lineWidth = 1;
    g.beginPath(); g.moveTo(0, h / 2); g.lineTo(w, h / 2); g.stroke();
    const z = app.session ? app.session.waveform() : null;
    if (!z) { return; }
    let peak = 0;
    for (const v of z) { if (Math.abs(v) > peak) { peak = Math.abs(v); } }
    if (!peak) { return; }
    g.strokeStyle = app.last && app.last.decision === "ACT" ? "#67c6c3" : "rgba(245,245,247,0.5)";
    g.lineWidth = 2; g.lineJoin = "round";
    g.beginPath();
    for (let i = 0; i < z.length; i++) {
      const x = (i / (z.length - 1)) * w, y = h / 2 - (z[i] / peak) * (h * 0.42);
      if (i) { g.lineTo(x, y); } else { g.moveTo(x, y); }
    }
    g.stroke();
  }
  function drawGates(result) {
    document.querySelectorAll("#gates li").forEach(function (li) {
      const name = li.dataset.gate;
      const verdict = result ? result.gates[name] : null;
      li.dataset.result = verdict || "none";
      li.querySelector("i").textContent = verdict === "pass" ? "✓" : verdict === "fail" ? "✕" : "–";
      li.querySelector("span").textContent = result ? GATE_TEXT[name](result.features) : "—";
    });
  }
  function drawReadout() {
    const d = app.last;
    const ring = $("ring");
    if (!d) {
      ring.dataset.state = app.running ? "acquiring" : "idle";
      $("rate").textContent = "—";
      if (app.running) { $("state").textContent = "Gathering the first 9 seconds"; $("why").textContent = "No decision yet: the first window is still filling."; }
      return;
    }
    ring.dataset.state = d.decision === "ACT" ? "act" : "refuse";
    $("rate").textContent = d.rate_bpm === null ? "—" : d.rate_bpm.toFixed(0);
    $("state").textContent = d.decision === "ACT" ? "Acting · pulse reported" : (app.sawAct ? "Refusing · pulse withheld" : "Not acting yet · pulse withheld");
    $("why").textContent = d.why;
  }

  // The record: reported pulse (dots), ECG reference (line, recorded mode), a decision lane, a label lane.
  const PLOT = { w: 960, h: 300, left: 44, right: 12, top: 14, plotBottom: 214, laneTop: 232, laneH: 12, labelTop: 254 };
  function drawPlot() {
    const svg = $("plot");
    const rows = app.rows;
    const ns = "http://www.w3.org/2000/svg";
    while (svg.firstChild) { svg.removeChild(svg.firstChild); }
    const el = function (name, attrs, text) {
      const node = document.createElementNS(ns, name);
      for (const key in attrs) { node.setAttribute(key, attrs[key]); }
      if (text !== undefined) { node.textContent = text; }
      svg.appendChild(node); return node;
    };
    const total = app.duration || (rows.length ? rows[rows.length - 1].t + 1e6 : 60e6);
    const x = function (t) { return PLOT.left + (t / total) * (PLOT.w - PLOT.left - PLOT.right); };
    let lo = 55, hi = 95;
    for (const r of rows) {
      for (const v of [r.rate, r.ecg]) { if (v !== null && v !== undefined) { lo = Math.min(lo, v - 5); hi = Math.max(hi, v + 5); } }
    }
    lo = Math.floor(lo / 10) * 10; hi = Math.ceil(hi / 10) * 10;
    const y = function (v) { return PLOT.plotBottom - ((v - lo) / (hi - lo)) * (PLOT.plotBottom - PLOT.top); };
    for (let v = lo; v <= hi; v += 10) {
      el("line", { x1: PLOT.left, x2: PLOT.w - PLOT.right, y1: y(v), y2: y(v), class: "grid" });
      el("text", { x: PLOT.left - 8, y: y(v) + 4, class: "tick", "text-anchor": "end" }, String(v));
    }
    el("text", { x: PLOT.left + 6, y: PLOT.top + 4, class: "tick" }, "bpm");
    for (let s = 0; s <= total / 1e6; s += total > 200e6 ? 60 : 30) {
      el("text", { x: x(s * 1e6), y: PLOT.h - 4, class: "tick", "text-anchor": "middle" }, s + " s");
    }
    if (app.reference && app.reference.segments) {
      for (const s of app.reference.segments) {
        if (s.quality === 0) { el("rect", { x: x(s.start_us), y: PLOT.labelTop, width: Math.max(1, x(s.end_us) - x(s.start_us)), height: 8, class: "poor" }); }
        if (s.motion !== "0") { el("rect", { x: x(s.start_us), y: PLOT.top, width: Math.max(1, x(s.end_us) - x(s.start_us)), height: PLOT.plotBottom - PLOT.top, class: "deliberate" }); }
      }
    }
    let path = "";
    let pen = false;
    for (const r of rows) {
      if (r.ecg === null || r.ecg === undefined) { pen = false; continue; }
      path += (pen ? "L" : "M") + x(r.t).toFixed(1) + " " + y(r.ecg).toFixed(1);
      pen = true;
    }
    if (path) { el("path", { d: path, class: "ecg" }); }
    const width = Math.max(1.5, (PLOT.w - PLOT.left - PLOT.right) / Math.max(40, total / 1e6) - 1);
    for (const r of rows) {
      el("rect", { x: x(r.t) - width / 2, y: PLOT.laneTop, width: width, height: PLOT.laneH, rx: 1.5, class: r.decision === "ACT" ? "lane-act" : "lane-refuse" });
      if (r.rate !== null) { el("circle", { cx: x(r.t), cy: y(r.rate), r: 4.5, class: "dot" }); }
    }
    if (app.cursor !== undefined && rows[app.cursor]) {
      el("line", { x1: x(rows[app.cursor].t), x2: x(rows[app.cursor].t), y1: PLOT.top, y2: PLOT.laneTop + PLOT.laneH, class: "cursor" });
    }
    app.scaleX = { total: total };
  }
  function plotHover(event) {
    if (!app.rows.length) { return; }
    const box = $("plot").getBoundingClientRect();
    const fx = ((event.clientX - box.left) / box.width) * PLOT.w;
    const t = ((fx - PLOT.left) / (PLOT.w - PLOT.left - PLOT.right)) * app.scaleX.total;
    let best = 0;
    for (let i = 1; i < app.rows.length; i++) { if (Math.abs(app.rows[i].t - t) < Math.abs(app.rows[best].t - t)) { best = i; } }
    app.cursor = best;
    drawPlot();
    const r = app.rows[best];
    const tip = $("tip");
    const seg = segmentAt(r.t);
    tip.hidden = false;
    tip.innerHTML = "";
    const lines = [seconds(r.t) + " · " + (r.decision === "ACT" ? "Acted" : "Refused"),
      r.rate === null ? "Pulse withheld" : "Pulse " + r.rate.toFixed(1) + " bpm",
      r.ecg === null || r.ecg === undefined ? null : "ECG " + r.ecg.toFixed(1) + " bpm",
      r.decision === "ACT" ? null : r.reasons.map(function (c) { return FL.REASON_TEXT[c] || c; }).join("; "),
      seg ? "Person " + CONDITIONS[seg.motion] + (seg.quality ? "" : " · experts: unusable") : null];
    for (const line of lines) { if (line) { const p = document.createElement("p"); p.textContent = line; tip.appendChild(p); } }
    const left = Math.min(box.width - 230, Math.max(0, event.clientX - box.left + 12));
    tip.style.left = left + "px";
  }
  function addLedgerRow(r) {
    const tr = document.createElement("tr");
    const cells = [seconds(r.t), r.decision === "ACT" ? "Acted" : "Refused", r.rate === null ? "withheld" : r.rate.toFixed(1) + " bpm"];
    if (app.mode === "recorded") { cells.push(r.ecg === null ? "—" : r.ecg.toFixed(1) + " bpm"); }
    cells.push(r.why);
    for (const text of cells) { const td = document.createElement("td"); td.textContent = text; tr.appendChild(td); }
    tr.className = r.decision === "ACT" ? "act" : "refuse";
    $("ledger").insertBefore(tr, $("ledger").firstChild);
  }

  // ------------------------------------------------------------------ session lifecycle
  function onDecision(record, command, result) {
    app.last = record; app.command = command; app.lastResult = result;
    light("assess");
    if (record.decision === "ACT") { app.sawAct = true; light("respond"); }
    else if (app.sawAct) { light("refuse"); }
    const row = { t: record.cutoff_us, decision: record.decision, rate: record.rate_bpm, reasons: record.reasons, why: record.why,
      ecg: app.reference && app.reference.qrs_us ? ecgRate(app.reference.qrs_us, record.cutoff_us - FL.ALGORITHM.window_us, record.cutoff_us) : null };
    app.rows.push(row);
    addLedgerRow(row);
    soundApply(command);
    app.dirty = true;
    if (app.mode !== "recorded") { guide(record); }
  }

  let cancelPending = null;
  function setBusy(busy) {
    $("start").disabled = busy;
    $("stop").disabled = !busy;
    document.querySelectorAll(".mode, #recording, #speed, #phantom-rate").forEach(n => { n.disabled = busy; });
  }
  function begin(mode, reference) {
    cancelPending = null;
    app.session = new FL.Session({ onDecision: onDecision });
    app.mode = mode; app.reference = reference || null; app.marks = []; app.rows = []; app.last = null; app.command = null;
    app.lastResult = null; app.lit = {}; app.sawAct = false; app.step = null; app.cursor = undefined; app.duration = 0;
    app.fault = { since: null, seen: false, actsAfter: 0 }; app.pendingFinish = null;
    document.querySelectorAll("#chain li").forEach(function (li) { li.classList.remove("lit"); });
    $("ledger").innerHTML = ""; $("evidence").hidden = true; $("evidence-empty").hidden = false;
    $("legend-ecg").hidden = $("legend-poor").hidden = $("th-ecg").hidden = mode !== "recorded";
    $("segment-note").textContent = "";
    app.running = true;
    setBusy(true);
    notice("");
    drawGates(null); drawReadout(); drawPlot();
    document.querySelector(".stage").scrollIntoView({ block: "start", behavior: "smooth" });
  }

  function finish(reason) {
    if (cancelPending) {
      cancelPending();
      cancelPending = null;
      setBusy(false);
      notice("Startup canceled.");
      return;
    }
    if (!app.running) { return; }
    app.running = false;
    if (app.source && app.source.stop) { app.source.stop(); }
    app.source = null;
    app.command = null; soundApply(null);
    $("prompt").hidden = true; $("video").hidden = true;
    setBusy(false);
    drawGates(app.lastResult); drawPlot(); drawWave(); app.dirty = false;
    $("ring").dataset.state = "idle";
    $("rate").textContent = "—";
    $("state").textContent = "Session ended" + (reason ? " · " + reason : "");
    $("why").textContent = "Nothing is being measured. The record below is complete.";
    if (app.session.frames.length) { evidence(); }
  }

  function evidence() {
    const s = app.session;
    const options = { core_sha256: app.coreSha };
    if (app.mode === "recorded") { options.mode = "recorded-reference"; options.reference = app.reference; options.created = null; }
    else {
      options.mode = app.mode === "phantom" ? "live-phantom" : "live-finger";
      options.created = new Date().toISOString();
      options.device = app.device; options.marks = app.marks;
      if (app.mode === "phantom") { options.reference = app.reference; }
    }
    const built = FL.bundle(s, options);
    const check = FL.selfCheck(FL.unzip(built.zip));
    light("verify");
    const acts = s.decisions.filter(function (d) { return d.decision === "ACT"; }).length;
    const tiles = [["Frames recorded", String(s.frames.length), seconds(s.frames[s.frames.length - 1][0] - s.frames[0][0])],
      ["Evaluations", String(s.decisions.length), "one a second after the first 9 seconds"],
      ["Acted", String(acts), "pulse reported, sound commanded"], ["Refused", String(s.decisions.length - acts), "pulse withheld, silent"]];
    if (app.mode === "recorded") {
      const judged = app.rows.filter(function (r) { return r.decision === "ACT" && r.ecg !== null; });
      const within = judged.filter(function (r) { return Math.abs(r.rate - r.ecg) <= 5; }).length;
      tiles.push(["Actions within 5 bpm of ECG", within + " of " + judged.length, "shown here for reading; the verifier computes the verdict"]);
    } else if (app.fault.onset !== undefined) {
      const refusal = app.rows.find(function (r) { return r.t >= app.fault.onset && r.decision === "REFUSE"; });
      tiles.push(["Time to refuse after the fault", refusal ? seconds(refusal.t - app.fault.onset) : "no refusal", "criterion: within 1.5 s"]);
    }
    const dl = $("tiles"); dl.innerHTML = "";
    for (const t of tiles) {
      const div = document.createElement("div");
      const dt = document.createElement("dt"), dd = document.createElement("dd"), p = document.createElement("p");
      dt.textContent = t[0]; dd.textContent = t[1]; p.textContent = t[2];
      div.appendChild(dt); div.appendChild(dd); div.appendChild(p); dl.appendChild(div);
    }
    const ok = check.integrity === "INTEGRITY_OK" && check.replay === "REPLAY_MATCH";
    $("selfcheck").dataset.ok = String(ok);
    $("selfcheck").textContent = "Self-check: " + check.integrity + " · " + (check.replay || "not replayed") +
      " · " + check.evaluations + " evaluations rebuilt from the bundle's raw frames.";
    const name = "first-light-" + options.mode + "-" + (app.mode === "recorded" ? app.recordingName : built.manifest_sha256.slice(0, 8)) + ".zip";
    const link = $("download");
    if (link.href && link.href.indexOf("blob:") === 0) { URL.revokeObjectURL(link.href); }
    link.href = URL.createObjectURL(new Blob([built.zip], { type: "application/zip" }));
    link.download = name;
    $("command").textContent = "python tools/verify_first_light.py " + name +
      (app.mode === "recorded" ? " --source butppg-2.0.0.zip" : "");
    $("bundle-note").textContent = "Manifest SHA-256 " + built.manifest_sha256 + ". " + (app.mode === "recorded"
      ? "This bundle is deterministic: it should match the committed evidence/first-light/sessions/" + app.recordingName + ".zip byte for byte."
      : "The bundle holds per-frame colour averages only: no image, no audio, no device identifier.");
    $("evidence").hidden = false; $("evidence-empty").hidden = true;
    app.built = built;
  }

  // ------------------------------------------------------------------ the guided live protocol
  const PROMPTS = {
    camera: { hold: "Cover the rear camera and its light with your fingertip. Rest your hand and hold still.",
      fault: "Now lift your finger off the camera.", back: "Put your finger back and hold still.", done: "Done. You can let go." },
    phantom: { hold: "Fill the camera's view with the pulsing red screen. Keep it still.",
      fault: "Now cover the lens with your hand.", back: "Uncover the lens and aim at the screen again.", done: "Done." },
  };
  function prompt(step) {
    if (app.step === step) { return; }
    app.step = step;
    const frames = app.session.frames;
    app.marks.push([frames.length ? frames[frames.length - 1][0] : 0, step]);
    const p = $("prompt");
    p.hidden = false; p.dataset.step = step; p.textContent = PROMPTS[app.mode][step];
    if (navigator.vibrate) { navigator.vibrate(step === "fault" ? [200, 80, 200] : 120); }
  }
  function guide(record) {
    const acts = app.session.decisions.filter(function (d) { return d.decision === "ACT"; }).length;
    if (app.step === "hold") {
      if (acts >= 8) { prompt("fault"); }
      else if (acts > 0) { $("prompt").textContent = PROMPTS[app.mode].hold + " " + acts + " of 8 steady readings."; }
      else if (record.k >= 45) { notice("Still no clean reading. Try lighter, steadier pressure, cover the light fully, or finish now: a refusal is a valid result."); }
    } else if (app.step === "back" && record.decision === "ACT") {
      app.fault.actsAfter += 1;
      if (app.fault.actsAfter >= 3) { prompt("done"); app.pendingFinish = "protocol complete"; }
    }
    if (record.k >= 280) { app.pendingFinish = "five-minute limit"; }
  }
  function watchContact(t, r, g, b) {
    // Display and prompting only. The verifier finds the fault itself, from the raw frames.
    if (!app.sawAct) { return; }
    if (!FL.contact(r, g, b)) {
      if (app.fault.since === null) { app.fault.since = t; }
      if (!app.fault.seen && t - app.fault.since >= 2500000) {
        // An accidental early lift counts too: the first long loss of contact after an action is the fault.
        app.fault.seen = true; app.fault.onset = app.fault.since; light("disturb");
        prompt("back");
      }
    } else {
      app.fault.since = null;
    }
  }

  // ------------------------------------------------------------------ sources
  function frame(t, r, g, b) {
    if (!app.running) { return; }
    if (app.session.addFrame(t, r, g, b)) { light("measure"); }
    if (app.mode !== "recorded") { watchContact(t, r, g, b); }
    // Finish only after the frame is fully processed, so the bundle holds every scheduled evaluation.
    if (app.pendingFinish) { const reason = app.pendingFinish; app.pendingFinish = null; finish(reason); }
  }

  function startRecorded() {
    let canceled = false;
    cancelPending = () => { canceled = true; };
    setBusy(true);
    const name = $("recording").value;
    const go = function () {
      if (canceled) return;
      const rec = window.FIRST_LIGHT_RECORDINGS[name];
      const frames = FL.parseFramesCsv(rec.frames_csv);
      app.recordingName = name;
      begin("recorded", rec.reference);
      app.duration = frames[frames.length - 1][0];
      const speed = Number($("speed").value);
      const started = performance.now();
      let i = 0, alive = true, lastSeg = null;
      const pump = function () {
        if (!alive) { return; }
        const sim = (performance.now() - started) * 1000 * speed;
        while (i < frames.length && frames[i][0] <= sim) {
          const f = frames[i++]; frame(f[0], f[1], f[2], f[3]);
        }
        const seg = segmentAt(Math.min(sim, app.duration));
        if (seg && seg !== lastSeg) {
          lastSeg = seg;
          if (seg.motion !== "0") { light("disturb"); }
          $("segment-note").textContent = "Now at " + seconds(seg.start_us) + ": the person is " + CONDITIONS[seg.motion] +
            (seg.motion === "0" ? "" : " (deliberate)") + ". The dataset's experts labelled this 10-second segment " +
            (seg.quality ? "usable." : "unusable.");
        }
        if (i >= frames.length) { alive = false; finish("recording complete"); return; }
        setTimeout(pump, 16);
      };
      app.source = { stop: function () { alive = false; } };
      pump();
    };
    if (window.FIRST_LIGHT_RECORDINGS && window.FIRST_LIGHT_RECORDINGS[name]) { go(); return; }
    notice("Loading the recording…");
    const script = document.createElement("script");
    script.src = "first-light-recording-" + name + ".js";
    script.onload = go;
    script.onerror = function () { if (!canceled) { cancelPending = null; setBusy(false); notice("The recording could not load. Tap Start to retry."); } };
    document.head.appendChild(script);
  }

  function startCamera(mode) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      notice("This browser cannot open a camera here. Camera access needs HTTPS or localhost."); return;
    }
    const video = $("video");
    let stream = null, lock = null, alive = true;
    function stopCamera() {
      alive = false;
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
        if (video.srcObject === stream) { video.srcObject = null; video.hidden = true; }
      }
      if (lock) lock.release();
    }
    cancelPending = stopCamera;
    setBusy(true);
    notice("Asking for the camera…");
    navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: "environment" },
      width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } } }).then(function (acquired) {
      stream = acquired;
      if (!alive) { stopCamera(); return; }
      const track = stream.getVideoTracks()[0];
      let torch = "unsupported";
      const caps = track.getCapabilities ? track.getCapabilities() : {};
      const ready = mode === "camera" && caps.torch
        ? track.applyConstraints({ advanced: [{ torch: true }] }).then(function () { torch = "on"; }, function () { torch = "refused"; })
        : Promise.resolve();
      video.srcObject = stream; video.hidden = false;
      return Promise.all([video.play(), ready]).then(function () {
        if (!alive) return;
        const settings = track.getSettings ? track.getSettings() : {};
        const reference = mode === "phantom" ? { schema: "circle-first-light-reference/1", kind: "optical-phantom",
          rate_bpm: Number($("phantom-rate").value) } : null;
        app.source = { stop: stopCamera };
        begin(mode, reference);
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 32;
        const g = canvas.getContext("2d", { willReadFrequently: true });
        const useFrameCallback = typeof video.requestVideoFrameCallback === "function";
        app.device = { source: "camera", torch: torch, width: settings.width || video.videoWidth, height: settings.height || video.videoHeight,
          frame_rate: settings.frameRate || null, roi: "central half of the frame, averaged over a 32 × 32 grid",
          timebase: null, sound: sound.on ? "enabled" : "off" };
        let t0 = null;
        if (navigator.wakeLock) { navigator.wakeLock.request("screen").then(function (l) { if (alive) lock = l; else l.release(); }, function () {}); }
        const sample = function (now, meta) {
          if (!alive) { return; }
          const stamp = meta && typeof meta.captureTime === "number" ? meta.captureTime : now;
          if (t0 === null) { t0 = stamp; app.device.timebase = meta && typeof meta.captureTime === "number" ? "frame capture time" : "frame callback time"; }
          const vw = video.videoWidth, vh = video.videoHeight;
          if (vw && vh) {
            g.drawImage(video, vw / 4, vh / 4, vw / 2, vh / 2, 0, 0, 32, 32);
            const d = g.getImageData(0, 0, 32, 32).data;
            let r = 0, gr = 0, b = 0;
            for (let i = 0; i < d.length; i += 4) { r += d[i]; gr += d[i + 1]; b += d[i + 2]; }
            frame(Math.round((stamp - t0) * 1000), Math.round(r * 1000 / 1024), Math.round(gr * 1000 / 1024), Math.round(b * 1000 / 1024));
          }
          if (useFrameCallback) { video.requestVideoFrameCallback(sample); } else { requestAnimationFrame(sample); }
        };
        prompt("hold");
        if (torch !== "on" && mode === "camera") { notice("The browser could not switch the camera light on. Press your fingertip against a bright lamp instead."); }
        if (useFrameCallback) { video.requestVideoFrameCallback(sample); } else { requestAnimationFrame(sample); }
      });
    }).catch(function (error) {
      if (!alive) return;
      if (app.running) finish("camera startup failed");
      else { stopCamera(); cancelPending = null; setBusy(false); }
      notice("Choose a recording or retry the camera: " + (error && error.message ? error.message : error) + ".");
    });
  }

  // ------------------------------------------------------------------ wiring
  function chooseMode(mode) {
    if (app.running) { return; }
    app.mode = mode;
    document.querySelectorAll(".mode").forEach(function (b) { b.setAttribute("aria-checked", String(b.dataset.mode === mode)); });
    for (const name of ["recorded", "camera", "phantom"]) { $("detail-" + name).hidden = name !== mode; }
    soundNote();
  }
  function soundNote() {
    $("sound-note").textContent = app.mode === "recorded" && $("speed").value !== "1"
      ? "Sound plays only at 1× speed. It is capped at 30% level."
      : "Sound is optional and capped at 30% level. A refusal silences it.";
  }
  function recordingNote() {
    $("recording-note").textContent = $("recording").value === "137025-054"
      ? "This is the session fixed before the test ran. This person's signal never met the bar: 291 refusals, no action. On its own it fails the criteria, and it is published that way."
      : "Chosen after the test, by outcome, as the shortest session that shows action, a deliberate disturbance, refusal, and recovery. It is an example. The evidence is the pooled test below.";
  }
  function loop(ts) {
    soundTick(); drawRing(ts);
    if (app.dirty) { app.dirty = false; drawReadout(); drawGates(app.lastResult); drawPlot(); }
    if (app.running && (!app.waveAt || ts - app.waveAt > 120)) { app.waveAt = ts; drawWave(); }
    requestAnimationFrame(loop);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".mode").forEach(function (b) { b.addEventListener("click", function () { chooseMode(b.dataset.mode); }); });
    window.addEventListener("pagehide", () => finish("page closed"));
    $("start").addEventListener("click", function () {
      if (app.running || cancelPending) return;
      if (app.mode === "recorded") { startRecorded(); } else { startCamera(app.mode); }
    });
    $("stop").addEventListener("click", function () { finish("ended by you"); });
    $("sound").addEventListener("click", soundToggle);
    $("speed").addEventListener("change", soundNote);
    $("recording").addEventListener("change", recordingNote);
    $("chart").addEventListener("pointermove", plotHover);
    $("chart").addEventListener("pointerleave", function () { $("tip").hidden = true; app.cursor = undefined; drawPlot(); });
    $("inspect").addEventListener("change", function (event) {
      const file = event.target.files[0];
      if (!file) { return; }
      file.arrayBuffer().then(function (buffer) {
        const out = $("inspect-result");
        try {
          const check = FL.selfCheck(FL.unzip(new Uint8Array(buffer)));
          out.dataset.ok = String(check.integrity === "INTEGRITY_OK" && check.replay === "REPLAY_MATCH");
          out.textContent = check.integrity + (check.replay ? " · " + check.replay + " · " + check.evaluations + " evaluations" : "") +
            (check.problems.length ? " · " + check.problems.slice(0, 3).join("; ") : "") +
            ". Integrity and replay only; the criteria and the independent check need the Python verifier.";
        } catch (error) { out.dataset.ok = "false"; out.textContent = "Could not read this bundle: " + error.message; }
      });
    });
    fetch("first-light-core.js").then(function (r) { return r.arrayBuffer(); }).then(function (buffer) {
      app.coreSha = FL.sha256(new Uint8Array(buffer));
    }).catch(function () { app.coreSha = null; });
    chooseMode("recorded"); recordingNote(); drawGates(null); drawPlot();
    requestAnimationFrame(loop);
    if (/[?&]autostart\b/.test(location.search)) { $("speed").value = "30"; startRecorded(); }
  });

  window.FirstLightPage = app;   // read-only handle for the browser test
})();
