/* CIRCLE Resonance Workbench — application logic.
 * Loads a session's timeline evidence, plays it back deterministically, and
 * renders the dashboard, feedback studio, visual field, and evidence explorer.
 */
"use strict";
(function () {
  const $ = (id) => document.getElementById(id);
  const engine = window.CircleAudioEngine, synthMod = window.CircleSynth, visualMod = window.CircleVisual;

  let config = null, runs = [], selected = null, timeline = null, busy = false, connected = false;
  const statusLabels = { running: "In progress", cancelling: "Stopping", completed: "Completed",
    failed: "Could not finish", cancelled: "Cancelled", interrupted: "Interrupted" };
  const isActive = (run) => ["running", "cancelling"].includes(run.status);
  const scenarioById = (id) => config && config.scenarios.find((s) => s.id === id);
  const node = (tag, text, cls) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (cls) el.className = cls; return el; };
  const fmtTime = (s) => { s = Math.max(0, s || 0); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`; };
  const fmt = (v, d = 1) => (typeof v === "number" && isFinite(v)) ? v.toFixed(d) : "—";

  /* ---------------- API ---------------- */
  async function api(path, data, refreshToken = true) {
    const options = data === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", "X-Circle-Token": config.token }, body: JSON.stringify(data) };
    const response = await fetch(path, { ...options, signal: AbortSignal.timeout(30000) });
    const result = await response.json();
    if (response.status === 403 && data !== undefined && refreshToken) {
      config = await api("/api/config"); return api(path, data, false);
    }
    if (!response.ok) { const e = new Error(result.error || "The workbench could not complete that request."); e.status = response.status; throw e; }
    return result;
  }
  function error(message) { $("error").textContent = message; $("error").hidden = !message; }

  /* ---------------- views ---------------- */
  const views = ["designer", "dashboard", "studio", "visual", "evidence", "phantom", "history"];
  function showView(name) {
    views.forEach((v) => { $("view-" + v).hidden = v !== name; });
    document.querySelectorAll(".view-tab").forEach((b) => b.setAttribute("aria-current", b.dataset.view === name ? "page" : "false"));
    if (location.hash !== "#view-" + name) { history.replaceState(null, "", "#view-" + name); }
    if (name === "visual" && visual) { visual.render(null, 0, true, { force: true }); renderCurrentFrame(true); }
  }
  document.querySelectorAll(".view-tab").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));

  /* ---------------- designer ---------------- */
  function renderScenarios() {
    const list = $("scenario-list");
    list.replaceChildren(...config.scenarios.map((item, index) => {
      const label = node("label", undefined, "scenario-option" + (index === 0 ? " on" : ""));
      const radio = document.createElement("input");
      Object.assign(radio, { type: "radio", name: "scenario", value: item.id, checked: index === 0 });
      radio.addEventListener("change", () => {
        label.classList.add("on");
        list.querySelectorAll(".scenario-option").forEach((el) => el !== label && el.classList.remove("on"));
      });
      const text = node("span");
      text.append(node("span", item.category, "sc-cat"), node("span", item.title, "sc-name"), node("span", item.description, "sc-desc"));
      label.append(radio, text); return label;
    }));
  }
  function designerSettings() {
    const form = new FormData($("designer-form"));
    const modalities = [];
    if ($("mod-visual").checked) modalities.push("visual");
    if ($("mod-audio").checked) modalities.push("audio");
    return {
      scenario: form.get("scenario"), seed: Number($("seed").value), arm: form.get("arm"), compare: $("compare").checked,
      feedback: { modalities, max_gain: Number($("max-gain").value) / 100, breath_bpm: Number($("breath-bpm").value) },
      consent: { audio: $("consent-audio").checked }
    };
  }
  function updateConsentUI() {
    const wantsAudio = $("mod-audio").checked, consented = $("consent-audio").checked;
    const warn = $("consent-warning");
    if (wantsAudio && !consented) {
      warn.hidden = false;
      warn.textContent = "Adaptive audio is selected but not allowed yet. Check the consent box to enable it.";
    } else if (!wantsAudio && consented) {
      warn.hidden = false;
      warn.textContent = "Audio consent is recorded but the audio modality is off. Nothing will play.";
    } else { warn.hidden = true; }
  }
  ["mod-audio", "consent-audio", "mod-visual"].forEach((id) => $(id).addEventListener("change", () => { updateConsentUI(); updateStart(); }));
  $("max-gain").addEventListener("input", () => { $("gain-out").textContent = $("max-gain").value + "%"; });
  $("breath-bpm").addEventListener("input", () => { $("breath-out").textContent = Number($("breath-bpm").value).toFixed(1) + " breaths/min"; });
  function updateStart() { $("start").disabled = busy || !connected || runs.some(isActive); }

  $("designer-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !connected || runs.some(isActive)) return;
    const settings = designerSettings();
    if (settings.feedback.modalities.includes("audio") && !settings.consent.audio) {
      error("Allow audio in the consent step before running an audio session."); return;
    }
    if (!settings.feedback.modalities.length) { error("Choose at least one feedback modality."); return; }
    busy = true; updateStart(); error("");
    try {
      const run = await api("/api/runs", settings);
      selected = run.id;
      await refresh(); await showRun(run.id);
      showView("dashboard");
    } catch (exc) { error(exc.message); }
    finally { busy = false; updateStart(); }
  });

  /* ---------------- runs ---------------- */
  async function refresh() {
    runs = await api("/api/runs");
    connected = true; $("connection").hidden = true;
    if (!selected && runs.length) selected = runs[0].id;
    renderHistory(); updateStart();
  }
  async function showRun(id) {
    selected = id;
    const run = await api(`/api/runs/${id}`);
    renderChips(run);
    if (run.status === "completed" && (!timeline || timeline.session.run_id !== id)) {
      await loadTimeline(id);
    }
    renderHistory();
  }
  async function loadTimeline(id) {
    timeline = await api(`/api/runs/${id}/timeline`);
    buildCharts(); buildEvidence(); playback.reset(); updateStudioFromTimeline();
    $("dash-empty").hidden = false; $("dash-body").hidden = true;
    if (timeline.windows.length) { $("dash-empty").hidden = true; $("dash-body").hidden = false; }
    if (currentView === "visual") { renderCurrentFrame(true); }
  }

  /* ---------------- playback ---------------- */
  const playback = {
    playing: false, speed: 1, t: 0, startWall: 0, duration: 360,
    reset() { this.playing = false; this.t = 0; $("play").textContent = "▶ Play"; $("play").disabled = !timeline; this.updateClock(); },
    toggle() {
      if (!timeline) return;
      this.playing = !this.playing;
      if (this.playing) {
        if (synth.enabled) synth.ensureContext();
        this.startWall = performance.now();
        if (!rafOn) { rafOn = true; requestAnimationFrame(frame); }
      }
      $("play").textContent = this.playing ? "⏸ Pause" : "▶ Play";
      if (!this.playing) synth.stop();
    },
    seek(t) { this.t = Math.max(0, Math.min(this.duration, t)); this.updateClock(); renderCurrentFrame(true); },
    updateClock() {
      $("clock").textContent = `${fmtTime(this.t)} / ${fmtTime(this.duration)}`;
      $("scrub").value = String(Math.round(this.t * 4) / 4);
    }
  };
  let rafOn = false;

  /* ---------------- charts ---------------- */
  const charts = {};
  function makeChart(fig, key) {
    const canvas = document.createElement("canvas");
    canvas.width = 640; canvas.height = 260;
    fig.appendChild(canvas);
    const obj = { canvas, ctx: canvas.getContext("2d"), key, data: null, markers: [], hrv: null };
    canvas.addEventListener("pointerdown", (e) => {
      const rect = canvas.getBoundingClientRect();
      const f = (e.clientX - rect.left) / rect.width;
      playback.seek(f * playback.duration);
    });
    charts[key] = obj; return obj;
  }
  function seriesFromWindows(key) {
    return (timeline.windows || []).map((w) => [w.t_s, w[key]]).filter((p) => typeof p[1] === "number");
  }
  function buildCharts() {
    if (!timeline) return;
    playback.duration = Math.max(...(timeline.windows || []).map((w) => w.t_s), 360);
    document.querySelectorAll(".chart").forEach((fig) => {
      const key = fig.dataset.chart;
      if (!charts[key]) makeChart(fig, key);
    });
    charts.hr.data = seriesFromWindows("hr_bpm");
    charts.resp.data = seriesFromWindows("resp_rate_bpm");
    charts.eda.data = seriesFromWindows("scl_us");
    charts.motion.data = seriesFromWindows("motion_fraction");
    charts.hrv.data = (timeline.hrv.series || []).filter((w) => typeof w.rmssd_ms === "number")
      .map((w) => [(w.window_start_s + w.window_end_s) / 2, w.rmssd_ms]);
    charts.quality.data = timeline.evaluations.map((e) => [e.decision_time_us / 1e6, e.gate.every((g) => g === "PASS") || e.gate.length === 0 ? 1 : 0]);
    charts.feedback.data = timeline.feedback.events.map((e) => [e.time_us / 1e6, e.parameters.level]);
    charts.feedback.alt = timeline.feedback.events.map((e) => [e.time_us / 1e6, e.parameters.intensity]);
    for (const key in charts) {
      const c = charts[key];
      const values = (c.data || []).map((p) => p[1]).concat((c.alt || []).map((p) => p[1]));
      c.min = values.length ? Math.min(...values) : 0;
      c.max = values.length ? Math.max(...values) : 1;
      if (c.max - c.min < 1e-9) { c.max = c.min + 1; }
      const span = c.max - c.min;
      c.min -= span * 0.08; c.max += span * 0.08;
      c.__label = `${figLabel(key)}: ${values.length} points, range ${fmt(c.min, 2)} to ${fmt(c.max, 2)}. Time runs left to right across ${fmtTime(playback.duration)}.`;
      c.canvas.setAttribute("aria-label", c.__label);
      c.canvas.setAttribute("role", "img");
    }
    drawAll();
  }
  function figLabel(key) {
    return { hr: "Heart rate (bpm)", hrv: "RMSSD (ms)", resp: "Respiratory rate (breaths per minute)",
      eda: "Skin conductance level (microsiemens)", motion: "Motion fraction",
      quality: "Quality-gate pass fraction", feedback: "Feedback level and intensity" }[key];
  }
  function drawChart(c) {
    const g = c.ctx, w = c.canvas.width, h = c.canvas.height;
    g.clearRect(0, 0, w, h);
    g.fillStyle = "#0d1417"; g.fillRect(0, 0, w, h);
    // gridlines
    g.strokeStyle = "rgba(43,59,66,0.7)"; g.lineWidth = 1;
    for (let i = 1; i < 4; i++) {
      const y = (h * i) / 4;
      g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke();
    }
    const toXY = (t, v) => [t / playback.duration * w, h - 8 - (v - c.min) / (c.max - c.min) * (h - 24)];
    // motion episodes
    if (c === charts.motion && timeline) {
      g.fillStyle = "rgba(217,164,65,0.16)";
      (timeline.motion_episodes || []).forEach(([a, b]) => {
        const x0 = a / playback.duration * w, x1 = b / playback.duration * w;
        g.fillRect(x0, 0, Math.max(1, x1 - x0), h);
      });
    }
    // muted shading on feedback chart
    if (c === charts.feedback && timeline) {
      g.fillStyle = "rgba(217,164,65,0.10)";
      let mutedStart = null;
      timeline.feedback.events.forEach((e) => {
        const t = e.time_us / 1e6;
        if (!e.audible && mutedStart === null) mutedStart = t;
        if (e.audible && mutedStart !== null) {
          g.fillRect(mutedStart / playback.duration * w, 0, (t - mutedStart) / playback.duration * w, h); mutedStart = null;
        }
      });
      if (mutedStart !== null) g.fillRect(mutedStart / playback.duration * w, 0, w, h);
    }
    // series
    const drawLine = (data, color, width) => {
      if (!data || !data.length) return;
      g.strokeStyle = color; g.lineWidth = width; g.beginPath();
      data.forEach((p, i) => { const [x, y] = toXY(p[0], p[1]); i ? g.lineTo(x, y) : g.moveTo(x, y); });
      g.stroke();
    };
    if (c === charts.quality) {
      (c.data || []).forEach((p) => {
        const [x, y] = toXY(p[0], p[1]);
        g.fillStyle = p[1] > 0.5 ? "rgba(127,191,122,0.9)" : "rgba(217,115,110,0.85)";
        g.fillRect(x - 1.5, y, 3, h - y - 8);
      });
    } else {
      drawLine(c.data, "#67c6c3", 1.8);
      drawLine(c.alt, "rgba(217,164,65,0.85)", 1.2);
    }
    // decision markers
    if (timeline) {
      (timeline.decisions || []).forEach((d) => {
        const x = d.decision_time_us / 1e6 / playback.duration * w;
        g.strokeStyle = "rgba(232,238,240,0.35)"; g.setLineDash([2, 4]);
        g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke(); g.setLineDash([]);
      });
      (timeline.cues || []).forEach((cue) => {
        const x = (cue.command_time_us || 0) / 1e6 / playback.duration * w;
        g.fillStyle = "rgba(127,191,122,0.9)";
        g.fillRect(x - 1, h - 10, 2, 10);
      });
    }
    // playhead
    const px = playback.t / playback.duration * w;
    g.strokeStyle = "#e8eef0"; g.lineWidth = 1;
    g.beginPath(); g.moveTo(px, 0); g.lineTo(px, h); g.stroke();
  }
  function drawAll() { for (const key in charts) drawChart(charts[key]); }

  /* ---------------- synth & studio ---------------- */
  const synth = new synthMod.AdaptiveSynth(engine);
  let schedule = null;
  function updateStudioFromTimeline() {
    if (!timeline) return;
    schedule = engine.buildSchedule(timeline.feedback.events, {
      maxGain: timeline.feedback.config.max_gain,
      breathPeriodMinS: timeline.feedback.config.breath_period_bounds_s[0],
      breathPeriodMaxS: timeline.feedback.config.breath_period_bounds_s[1]
    });
    synth.ceiling = timeline.feedback.config.max_gain;
    const fc = timeline.session.feedback_consent || { audio: false, state: "NONE" };
    const audioAllowed = fc.audio && timeline.feedback.config.modalities.includes("audio");
    $("audio-enable").checked = synth.enabled && audioAllowed;
    $("audio-enable").disabled = !audioAllowed;
    $("level").value = String(Math.round(synth.userLevel * 100));
    $("level-out").textContent = Math.round(synth.userLevel * 100) + "%";
    const stateText = {
      PENDING_SIGNATURE: "Audio consent is pending — the proposal is registered and waiting for your signature.",
      EXECUTED: "Audio consent is executed and recorded in the consent log.",
      REVOKED: "Audio consent was revoked for this session. Playback continues muted.",
      REJECTED: "Audio consent was rejected or interrupted; this session stays silent.",
      NONE: "This session proposed no audio feedback."
    };
    $("consent-state").textContent = fc.state ? (stateText[fc.state] || fc.state) : "";
    $("allow-audio").hidden = fc.state !== "PENDING_SIGNATURE";
    $("revoke-audio").hidden = fc.state !== "EXECUTED";
  }
  $("allow-audio").addEventListener("click", async () => {
    if (!selected) return;
    try { await api(`/api/runs/${selected}/consent`, {}); await loadTimeline(selected); }
    catch (exc) { error(exc.message); }
  });
  $("revoke-audio").addEventListener("click", async () => {
    if (!selected) return;
    try { await api(`/api/runs/${selected}/revoke`, {}); synth.enabled = false; $("audio-enable").checked = false; synth.stop(); await loadTimeline(selected); }
    catch (exc) { error(exc.message); }
  });
  $("audio-enable").addEventListener("change", () => {
    synth.enabled = $("audio-enable").checked;
    if (synth.enabled) { synth.ensureContext(); if (synth.ctx && synth.ctx.state === "suspended") synth.ctx.resume(); }
    else synth.stop();
    updateEngineState();
  });
  $("level").addEventListener("input", () => {
    synth.userLevel = Number($("level").value) / 100;
    $("level-out").textContent = $("level").value + "%";
  });
  $("breath-guide").addEventListener("change", () => { synth.breath = $("breath-guide").checked; });
  $("mute").addEventListener("click", () => {
    synth.enabled = false; $("audio-enable").checked = false; synth.stop(); updateEngineState();
  });
  function updateEngineState() {
    const st = synth.state();
    $("engine-state").textContent = !timeline ? "Idle" :
      st.enabled ? (st.muted_reasons.length ? "Holding (quality gate)" : "Sounding") : "Muted";
    $("engine-detail").textContent = st.muted_reasons.length ? "reasons: " + st.muted_reasons.join(", ") : "";
  }

  /* ---------------- visual ---------------- */
  const visual = new visualMod.VisualField($("field-canvas"));
  const reducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------- render loop ---------------- */
  function renderCurrentFrame(force) {
    if (!timeline || !schedule) return;
    const point = engine.interpolateAt(schedule, playback.t);
    const phase = engine.breathPhase(schedule, playback.t);
    const qualityOk = point ? point.audible : false;
    synth.update(point, playback.t, synth.ctx ? synth.ctx.currentTime : 0);
    updateEngineState();
    if (typeof currentView === "string" && currentView === "visual") {
      visual.render(point, phase, qualityOk, { reducedMotion: reducedMotion, wallTime: playback.t, force });
      renderVisualReadout(point, phase);
    }
    renderNow(point);
    drawAll();
  }
  function frame(now) {
    if (playback.playing) {
      // A frame timestamp can precede the wall time captured on Play; never step backwards.
      playback.t = Math.max(0, playback.t + (Math.max(0, now - playback.startWall) / 1000) * playback.speed);
      playback.startWall = now;
      if (playback.t >= playback.duration) { playback.t = playback.duration; playback.playing = false; synth.stop(); $("play").textContent = "▶ Play"; }
      playback.updateClock();
    }
    renderCurrentFrame(false);
    if (playback.playing) { requestAnimationFrame(frame); rafOn = true; }
    else { rafOn = false; }
  }
  let currentView = "designer";
  const origShowView = showView;
  showView = function (name) { currentView = name; origShowView(name); };
  document.querySelectorAll(".view-tab").forEach((b) => b.addEventListener("click", () => { currentView = b.dataset.view; }));
  $("play").addEventListener("click", () => playback.toggle());
  $("scrub").addEventListener("input", () => playback.seek(Number($("scrub").value)));
  document.querySelectorAll(".speed button").forEach((b) => b.addEventListener("click", () => {
    playback.speed = Number(b.dataset.speed);
    document.querySelectorAll(".speed button").forEach((x) => { x.classList.remove("on"); x.setAttribute("aria-pressed", "false"); });
    b.classList.add("on"); b.setAttribute("aria-pressed", "true");
  }));
  document.addEventListener("keydown", (e) => {
    if (["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(document.activeElement?.tagName)) return;
    if (e.key === "k") { playback.toggle(); }
    if (e.key === "m") { $("mute").click(); }
  });

  function renderNow(point) {
    const ev = latestEvaluationAt(playback.t);
    const rows = [];
    if (point) {
      rows.push(["time", fmtTime(playback.t)], ["state", ev ? ev.state_after : "—"],
        ["HR", ev && ev.features.hr_bpm != null ? fmt(ev.features.hr_bpm, 1) + " bpm" : "—"],
        ["SCL", ev && ev.features.scl_us != null ? fmt(ev.features.scl_us, 2) + " µS" : "—"],
        ["arousal idx", ev && ev.arousal_index != null ? fmt(ev.arousal_index, 2) : "—"],
        ["feedback", point.audible ? "active" : "held"],
        ["quality gate", ev ? (ev.gate.length && ev.gate[0] !== "PASS" ? ev.gate.join(", ") : "pass") : "—"]);
    }
    $("now-readout").replaceChildren(...rows.flatMap(([k, v]) => [node("dt", k), node("dd", String(v))]));
    renderEventFeed();
    renderMapReadout(point);
  }
  function latestEvaluationAt(t) {
    if (!timeline) return null;
    let best = null;
    for (const ev of timeline.evaluations) { if (ev.decision_time_us / 1e6 <= t) best = ev; else break; }
    return best;
  }
  let feedKey = "";
  function renderEventFeed() {
    if (!timeline) return;
    const t = playback.t;
    const items = [];
    for (const d of timeline.decisions) {
      const ts = d.decision_time_us / 1e6;
      if (ts <= t) items.push({ t: ts, cls: d.action === "HOLD_QUALITY" ? "hold" : "", text: `${d.action} — ${d.why ? d.why.split(";")[0] : ""}` });
    }
    for (const cue of timeline.cues) {
      const ts = (cue.command_time_us || 0) / 1e6;
      if (ts <= t) items.push({ t: ts, cls: "cue", text: `cue ${cue.cue_index} · ${cue.stage}` });
    }
    items.sort((a, b) => a.t - b.t);
    const key = JSON.stringify(items.slice(-8));
    if (key === feedKey) return;
    feedKey = key;
    $("event-feed").replaceChildren(...items.slice(-8).map((item) => {
      const li = node("li", undefined, item.cls);
      li.append(node("span", fmtTime(item.t), "t"), node("span", item.text));
      return li;
    }));
  }
  function renderMapReadout(point) {
    const rows = point ? [
      ["intensity", fmt(point.intensity, 3)], ["level (cap " + (timeline.feedback.config.max_gain).toFixed(2) + ")", fmt(point.level, 3)],
      ["brightness", fmt(point.brightness, 3)], ["tempo", fmt(point.tempo, 3)],
      ["spatial", fmt(point.spatial, 3)], ["breath period", fmt(point.breath_period_s, 1) + " s"],
      ["inputs: HR", point.inputs && point.inputs.hr_bpm != null ? fmt(point.inputs.hr_bpm, 1) + " bpm" : "—"],
      ["inputs: SCL", point.inputs && point.inputs.scl_us != null ? fmt(point.inputs.scl_us, 2) + " µS" : "—"],
      ["gate", point.gate_reasons.length ? point.gate_reasons.join(", ") : "pass"]
    ] : [["engine", "idle"]];
    const mapEl = $("map-readout") || $("visual-readout");
    $("map-readout").replaceChildren(...rows.flatMap(([k, v]) => [node("dt", k), node("dd", String(v))]));
  }
  function renderVisualReadout(point, phase) {
    const rows = [
      ["session time", fmtTime(playback.t)],
      ["intensity", point ? fmt(point.intensity, 3) : "—"],
      ["breath phase", fmt(phase, 2)],
      ["quality", point ? (point.audible ? "ok" : "held") : "—"]
    ];
    $("visual-readout").replaceChildren(...rows.flatMap(([k, v]) => [node("dt", k), node("dd", String(v))]));
  }

  /* ---------------- evidence explorer ---------------- */
  function buildEvidence() {
    if (!timeline) return;
    const list = $("evidence-list");
    const entries = [];
    timeline.decisions.forEach((d) => entries.push({ kind: d.action, t: d.decision_time_us / 1e6, decision: d }));
    timeline.evaluations.forEach((e) => entries.push({ kind: "eval · " + e.state_after, t: e.decision_time_us / 1e6, evaluation: e }));
    entries.sort((a, b) => a.t - b.t);
    list.replaceChildren(...entries.map((entry) => {
      const li = node("li");
      const btn = node("button");
      btn.append(node("span", entry.kind, "ev-kind"), node("span", fmtTime(entry.t), "ev-t"));
      btn.addEventListener("click", () => {
        list.querySelectorAll("button").forEach((b) => b.setAttribute("aria-current", "false"));
        btn.setAttribute("aria-current", "true");
        renderEvidenceDetail(entry);
      });
      li.appendChild(btn); return li;
    }));
    $("evidence-detail").replaceChildren(node("p", "Choose an event on the left.", "quiet"));
  }
  function renderEvidenceDetail(entry) {
    const el = $("evidence-detail");
    el.replaceChildren();
    if (entry.decision) {
      const d = entry.decision;
      el.append(node("p", undefined, "why"), ...[]);
      const why = node("p", d.why || "", "why");
      el.append(why);
      el.append(dl([["decision", d.decision_id || "—"], ["action", d.action],
        ["decision time", fmtTime(d.decision_time_us / 1e6)],
        ["input cutoff", fmtTime(d.input_cutoff_us / 1e6)],
        ["commands", String(d.commands)], ["execution", d.execution || "—"]]));
      if (d.execution_chain) {
        el.append(node("h3", "Execution evidence"));
        el.append(dl(d.execution_chain.map((link) => [`cue ${link.cue_index}`, `${link.stage}${link.onset ? " · onset Δ " + fmt((link.electrical_onset.device_time_us - link.command.device_time_us) / 1e6, 3) + " s" : ""}`])));
      }
    } else {
      const e = entry.evaluation;
      const ev = timeline.feedback.events.find((f) => f.time_us === e.decision_time_us);
      el.append(dl([
        ["evaluation", e.id], ["state", e.state_after], ["action", e.action || "hold"],
        ["decision time", fmtTime(e.decision_time_us / 1e6)], ["input cutoff", fmtTime(e.input_cutoff_us / 1e6)],
        ["quality gate", e.gate.join(", ") || "pass"],
        ["arousal index", e.arousal_index != null ? fmt(e.arousal_index, 3) : "—"]
      ]));
      el.append(node("h3", "Measurements available"));
      el.append(dl(Object.entries(e.features).slice(0, 14).map(([k, v]) => [k, fmt(Number(v), 3)])));
      if (ev) {
        el.append(node("h3", "Feedback requested"));
        el.append(dl([
          ["audible", ev.audible ? "yes" : "no (held)"],
          ...(Object.entries(ev.parameters).map(([k, v]) => [k, fmt(Number(v), 3)])),
          ["muted because", ev.gate_reasons.join(", ") || "—"]
        ]));
      }
    }
    el.append(node("h3", "Replay"));
    el.append(dl([
      ["audit", timeline.session.audit ? (timeline.session.audit.valid ? "REPLAY_MATCH" : timeline.session.audit.replay_status) : "not recorded"],
      ["decision replay (export)", timeline.provenance.decision_replay.status],
      ["feedback digest", timeline.feedback.digest]
    ]));
  }
  function dl(rows) {
    const list = node("dl", undefined, "readout mono");
    rows.forEach(([k, v]) => { list.append(node("dt", String(k), "k"), node("dd", String(v), "v")); });
    return list;
  }

  /* ---------------- history & chips ---------------- */
  function renderChips(run) {
    const chips = [
      chip(run.settings.scenario, ""), chip(run.settings.arm, run.settings.arm === "active" ? "good" : "warn"),
      chip("seed " + run.settings.seed, ""), chip(statusLabels[run.status] || run.status, run.status === "completed" ? "good" : "")
    ];
    if (run.summary && run.summary.audit_valid !== undefined) {
      chips.push(chip(run.summary.audit_valid ? "audit passed" : "audit needs review", run.summary.audit_valid ? "good" : "bad"));
    }
    const targets = ["dash-chips", "studio-chips", "visual-chips", "evidence-chips"];
    targets.forEach((id) => $(id).replaceChildren(...chips.map((c) => c.cloneNode(true))));
  }
  function chip(text, cls) { const el = node("span", text, "chip" + (cls ? " " + cls : "")); return el; }
  function renderHistory() {
    const list = $("history-list");
    if (!runs.length) {
      list.replaceChildren(node("li", undefined, "empty-state"));
      list.firstChild.append(node("h2", "No sessions yet."), node("p", "Run one from the Design view."));
      return;
    }
    list.replaceChildren(...runs.map((run) => {
      const li = node("li");
      const btn = node("button");
      const left = node("span");
      left.append(node("span", scenarioById(run.settings.scenario)?.title || run.settings.scenario, "h-title"),
        node("span", `${new Date(run.created_at).toLocaleString()} · ${run.settings.arm} · seed ${run.settings.seed} · ${run.id.slice(0, 8)}`, "h-meta"));
      btn.append(left, node("span", run.summary ? `${run.summary.scorecard.passed}/${run.summary.scorecard.total} checks · ${run.summary.audit_valid ? "audit ok" : "audit review"}` : (statusLabels[run.status] || run.status), "h-outcome"));
      btn.addEventListener("click", async () => {
        try { await showRun(run.id); showView("dashboard"); }
        catch (exc) { error(exc.message); }
      });
      li.appendChild(btn); return li;
    }));
    $("storage").textContent = config ? `Saved on this computer: ${config.output}` : "";
  }

  /* ---------------- boot ---------------- */
  async function poll() {
    try {
      if (!config) {
        config = await api("/api/config");
        renderScenarios(); updateConsentUI();
      }
      await refresh();
      if (selected && (!timeline || timeline.session.run_id !== selected)) {
        const run = runs.find((r) => r.id === selected);
        if (run && run.status === "completed") { await loadTimeline(selected); renderChips(run); }
      }
    } catch (exc) {
      connected = false; updateStart();
      $("connection").textContent = "Connection interrupted. Saved sessions remain on disk; this page will reconnect automatically.";
      $("connection").hidden = false;
    } finally { setTimeout(poll, document.hidden ? 6000 : 2500); }
  }
  const hashView = location.hash.match(/^#view-(\w+)$/);
  if (hashView && views.includes(hashView[1])) showView(hashView[1]);
  poll();
})();
