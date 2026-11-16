/* CIRCLE research site.
 * - Hero: four physiological traces (PPG, EDA, respiration, IMU) drawn as fine thread bundles,
 *   with a single pulse travelling each one. Illustrative shapes, labelled as such in the legend.
 * - Session: a figure drawn entirely from window.CIRCLE_DEMO, the recorded simulated session
 *   the workbench replays. Nothing on that figure is typed by hand.
 */
(function () {
  "use strict";
  document.documentElement.classList.add("js");
  const SVG = "http://www.w3.org/2000/svg";
  const still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (id) => document.getElementById(id);
  const el = (name, attrs, parent) => {
    const node = document.createElementNS(SVG, name);
    for (const key in attrs) { node.setAttribute(key, attrs[key]); }
    if (parent) { parent.appendChild(node); }
    return node;
  };
  const ready = (fn) => (document.readyState !== "loading" ? fn() : document.addEventListener("DOMContentLoaded", fn));

  /* ---------------- hero signals ---------------- */
  function seeded(seed) {
    let s = seed >>> 0;
    return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  }
  const ease = (u) => { const v = Math.pow(u, 1.7); return v * v * (3 - 2 * v); };
  const gauss = (p, c, w) => Math.exp(-Math.pow((p - c) / w, 2));
  const noise = (() => {
    const rnd = seeded(42);
    const values = Array.from({ length: 900 }, () => rnd() * 2 - 1);
    return (x) => {
      const i = Math.max(0, Math.min(values.length - 2, Math.floor((x + 100) / 1.6)));
      return values[i];
    };
  })();
  const SIGNALS = [
    { id: "ppg", y0: 742, y1: 250, amp: 26, wave: (x, k) => {
      const p = (((x + k * 2.5) / 62) % 1 + 1) % 1;
      return -(gauss(p, 0.2, 0.055) + 0.38 * gauss(p, 0.46, 0.08));
    } },
    { id: "eda", y0: 772, y1: 352, amp: 46, wave: (x, k) => {
      let v = 0;
      for (const c of [260 + k * 6, 700 + k * 4, 960 + k * 5]) {
        if (x > c) { v -= (1 - Math.exp(-(x - c) / 18)) * Math.exp(-(x - c) / 170); }
      }
      return v - x / 4000;
    } },
    { id: "resp", y0: 800, y1: 446, amp: 16, wave: (x, k) => Math.sin((x + k * 14) / 236 * Math.PI * 2) },
    { id: "imu", y0: 826, y1: 536, amp: 3, wave: (x, k) => {
      const burst = gauss(x, 520 + k * 3, 46) * 5.5;
      return noise(x + k * 7) * (0.5 + burst);
    } },
  ];

  function drawHero() {
    const svg = $("hero-signals");
    if (!svg) { return; }
    const defs = el("defs", {}, svg);
    const fade = el("linearGradient", { id: "trace-fade", gradientUnits: "userSpaceOnUse", x1: "0", y1: "0", x2: "1200", y2: "0" }, defs);
    [["0", 0], ["0.18", 1], ["0.82", 1], ["1", 0]].forEach(([o, a]) =>
      el("stop", { offset: o, "stop-color": "#f5f5f7", "stop-opacity": String(a) }, fade));
    const glow = el("radialGradient", { id: "pulse-glow" }, defs);
    [["0", "#ffffff", 1], ["0.35", "#67c6c3", 1], ["1", "#67c6c3", 0]].forEach(([o, c, a]) =>
      el("stop", { offset: o, "stop-color": c, "stop-opacity": String(a) }, glow));

    const group = el("g", {}, svg);
    const strands = 5;
    const paths = [];
    SIGNALS.forEach((signal, si) => {
      for (let k = 0; k < strands; k += 1) {
        const spread = (k - (strands - 1) / 2) * 3.2;
        let d = "";
        for (let x = -40; x <= 1240; x += 2.5) {
          const u = ease(Math.max(0, Math.min(1, (x + 40) / 1280)));
          const base = signal.y0 + (signal.y1 - signal.y0) * u + spread * (1 + u * 1.6);
          const y = base + signal.amp * (1 - k * 0.07) * signal.wave(x, k);
          d += (d ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
        }
        const primary = k === Math.floor(strands / 2);
        const path = el("path", {
          d, id: "trace-" + signal.id + "-" + k, class: "trace", stroke: "url(#trace-fade)",
          "stroke-width": primary ? "1.3" : String(0.9 - Math.abs(k - 2) * 0.18),
          "stroke-opacity": primary ? "0.72" : String(0.34 - Math.abs(k - 2) * 0.1),
        }, group);
        paths.push(path);
        if (primary && !still) {
          const dot = el("circle", { r: si === 0 ? "3" : "2.4", fill: "url(#pulse-glow)", class: "pulse" }, group);
          const motion = el("animateMotion", { dur: (8 + si * 1.7).toFixed(1) + "s", repeatCount: "indefinite",
            begin: (si * 0.9).toFixed(1) + "s", rotate: "auto" }, dot);
          el("mpath", { href: "#" + path.id }, motion);
        }
      }
    });
    if (still) { return; }
    // Draw the threads in once, left to right.
    paths.forEach((path, i) => {
      const length = path.getTotalLength();
      path.style.strokeDasharray = length + " " + length;
      path.style.strokeDashoffset = String(length);
      path.style.transition = "stroke-dashoffset 2.6s cubic-bezier(0.22, 1, 0.36, 1) " + (0.15 + (i % strands) * 0.07 + Math.floor(i / strands) * 0.12) + "s";
    });
    requestAnimationFrame(() => requestAnimationFrame(() => paths.forEach((p) => { p.style.strokeDashoffset = "0"; })));
  }

  /* ---------------- nav ---------------- */
  function wireNav() {
    const nav = $("nav");
    const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 8);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    const toggle = nav.querySelector(".nav-toggle");
    const sheet = $("nav-sheet");
    const set = (open) => { toggle.setAttribute("aria-expanded", String(open)); sheet.hidden = !open; nav.classList.toggle("scrolled", open || window.scrollY > 8); };
    toggle.addEventListener("click", () => set(sheet.hidden));
    sheet.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => set(false)));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !sheet.hidden) { set(false); toggle.focus(); } });
  }

  /* ---------------- reveal ---------------- */
  function wireReveal() {
    const items = document.querySelectorAll(".reveal");
    if (still || !("IntersectionObserver" in window)) { items.forEach((i) => i.classList.add("in")); return; }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => { if (entry.isIntersecting) { entry.target.classList.add("in"); io.unobserve(entry.target); } });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    items.forEach((i) => io.observe(i));
  }

  /* ---------------- copy buttons ---------------- */
  function wireCopy() {
    document.querySelectorAll("[data-copy]").forEach((button) => {
      button.addEventListener("click", () => {
        const text = $(button.dataset.copy).innerText.trim();
        const done = (label) => { button.textContent = label; setTimeout(() => { button.textContent = "Copy"; }, 1600); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(() => done("Copied"), () => done("Select to copy"));
        } else { done("Select to copy"); }
      });
    });
  }

  /* ---------------- recorded session ---------------- */
  const fmtTime = (t) => { const s = Math.max(0, Math.round(t)); return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); };
  const codeList = (codes) => codes.map((c) => "<code>" + c + "</code>").join(", ");
  const escapeHtml = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function sessionModel(data) {
    const tl = data.timeline;
    const evals = tl.evaluations.map((e) => ({ t: e.decision_time_us / 1e6, ai: e.arousal_index, gate: e.gate,
      pass: e.gate.length === 1 && e.gate[0] === "PASS", state: e.state_after, action: e.action, id: e.id }));
    const windows = tl.windows.map((w) => ({ t: w.t_s, hr: w.hr_bpm, scl: w.scl_us, motion: w.motion_fraction }));
    const decisions = tl.decisions.map((d) => ({ t: d.decision_time_us / 1e6, action: d.action, id: d.decision_id,
      why: d.why, execution: d.execution, commands: d.commands }));
    const start = decisions.find((d) => d.action.indexOf("START") === 0);
    const stop = decisions.find((d) => d.action.indexOf("STOP") === 0);
    const num = (re, s) => { const m = s && s.match(re); return m ? parseFloat(m[1]) : null; };
    const trigger = num(/trigger ([\d.]+)/, start && start.why);
    const release = num(/release ([\d.]+)/, stop && stop.why);
    const holds = [];
    evals.forEach((e) => {
      if (e.pass) { return; }
      const last = holds[holds.length - 1];
      if (last && last.evals[last.evals.length - 1] === evals[evals.indexOf(e) - 1]) { last.evals.push(e); }
      else { holds.push({ evals: [e] }); }
    });
    holds.forEach((h) => {
      h.t0 = h.evals[0].t; h.t1 = h.evals[h.evals.length - 1].t;
      h.reasons = Array.from(new Set([].concat.apply([], h.evals.map((e) => e.gate))));
      h.state = h.evals[0].state;
      h.motion = tl.motion_episodes.find((m) => m[0] <= h.t1 && m[1] >= h.t0 - 30) || null;
    });
    const end = Math.max(360, evals[evals.length - 1].t);
    return { tl, evals, windows, decisions, start, stop, trigger, release, holds, end,
      motion: tl.motion_episodes, session: tl.session, provenance: tl.provenance };
  }

  function drawSession(model, full) {
    const host = $("specimen-plot");
    host.textContent = "";
    const W = Math.max(300, host.clientWidth);
    const compact = W < 560;
    const padL = 0, padR = compact ? 6 : 10;
    const lanes = [
      { key: "hr", label: "Heart rate", unit: "bpm · 10 s windows", h: compact ? 70 : 96 },
      { key: "scl", label: "Skin conductance level", unit: "µS · 10 s windows", h: compact ? 70 : 96 },
      { key: "ai", label: "Arousal index", unit: "per 5 s evaluation", h: compact ? 92 : 128 },
      { key: "gate", label: "Quality gates", unit: "per evaluation", h: 14 },
    ];
    const labelH = 26, gap = compact ? 18 : 24, axisH = 26;
    let y = 0;
    lanes.forEach((lane) => { lane.top = y + labelH; y = lane.top + lane.h + gap; });
    const H = y - gap + axisH;
    const x = (t) => padL + (t / model.end) * (W - padL - padR);
    const tAt = (px) => Math.max(0, Math.min(model.end, ((px - padL) / (W - padL - padR)) * model.end));

    const svg = el("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", tabindex: "0",
      "aria-label": "Recorded simulated session: heart rate, skin conductance level, arousal index with trigger and release thresholds, and quality-gate results across " + Math.round(model.end) + " seconds. Use the left and right arrow keys to step through evaluations." }, host);
    const defs = el("defs", {}, svg);
    const clip = el("clipPath", { id: "session-clip", class: "reveal-clip" }, defs);
    const clipRect = el("rect", { x: 0, y: -20, width: still || full ? W : 0, height: H + 40 }, clip);

    // context bands: motion episodes and the guidance interval
    const bands = el("g", {}, svg);
    if (model.start && model.stop) {
      el("rect", { class: "guidance", x: x(model.start.t), y: lanes[0].top - 6, width: x(model.stop.t) - x(model.start.t),
        height: lanes[3].top + lanes[3].h - lanes[0].top + 12 }, bands);
    }
    model.motion.forEach((m) => {
      el("rect", { class: "motion", x: x(m[0]), y: lanes[0].top - 6, width: Math.max(2, x(m[1]) - x(m[0])),
        height: lanes[3].top + lanes[3].h - lanes[0].top + 12 }, bands);
    });

    // time grid
    const grid = el("g", {}, svg);
    for (let t = 0; t <= model.end; t += 60) {
      el("line", { class: "grid", x1: x(t), x2: x(t), y1: lanes[0].top - 6, y2: lanes[3].top + lanes[3].h + 6 }, grid);
      const tick = el("text", { class: "tick", x: x(t), y: H - 6, "text-anchor": t === 0 ? "start" : (t >= model.end - 1 ? "end" : "middle") }, grid);
      tick.textContent = t === 0 ? "0 s" : (t / 60) + " min";
    }

    const plotted = el("g", { "clip-path": "url(#session-clip)" }, svg);
    const scales = {};
    function lane(laneDef, points, opts) {
      const values = points.map((p) => p.v);
      let lo = opts.lo != null ? opts.lo : Math.min.apply(null, values);
      let hi = opts.hi != null ? opts.hi : Math.max.apply(null, values);
      const pad = (hi - lo) * 0.12 || 1; lo -= pad; hi += pad;
      const yv = (v) => laneDef.top + laneDef.h - ((v - lo) / (hi - lo)) * laneDef.h;
      scales[laneDef.key] = yv;
      const lbl = el("text", { class: "lane-label", x: padL, y: laneDef.top - 12 }, svg);
      lbl.textContent = laneDef.label;
      if (!compact || laneDef.key !== "gate") {
        const unit = el("text", { class: "lane-unit", x: W - padR, y: laneDef.top - 12, "text-anchor": "end" }, svg);
        unit.textContent = laneDef.unit;
      }
      (opts.thresholds || []).forEach((th) => {
        if (th.v == null) { return; }
        el("line", { class: "threshold", x1: padL, x2: W - padR, y1: yv(th.v), y2: yv(th.v) }, plotted);
        const tl = el("text", { class: "threshold-label", x: W - padR, y: yv(th.v) + (th.below ? 12 : -5), "text-anchor": "end" }, plotted);
        tl.textContent = th.label + " " + th.v.toFixed(2);
      });
      const d = points.map((p, i) => (i ? "L" : "M") + x(p.t).toFixed(1) + " " + yv(p.v).toFixed(1)).join("");
      if (opts.area) {
        el("path", { class: "area", d: d + "L" + x(points[points.length - 1].t).toFixed(1) + " " + yv(Math.max(lo, 0)).toFixed(1) +
          "L" + x(points[0].t).toFixed(1) + " " + yv(Math.max(lo, 0)).toFixed(1) + "Z" }, plotted);
      }
      el("path", { class: "series" + (opts.signal ? " signal" : ""), d }, plotted);
      // range labels
      const range = el("text", { class: "tick", x: padL, y: laneDef.top + laneDef.h + 13 }, svg);
      range.textContent = opts.rangeLabel ? opts.rangeLabel(Math.min.apply(null, values), Math.max.apply(null, values)) : "";
    }
    lane(lanes[0], model.windows.map((w) => ({ t: w.t, v: w.hr })), { rangeLabel: (a, b) => a.toFixed(0) + "–" + b.toFixed(0) + " bpm" });
    lane(lanes[1], model.windows.map((w) => ({ t: w.t, v: w.scl })), { rangeLabel: (a, b) => a.toFixed(2) + "–" + b.toFixed(2) + " µS" });
    lane(lanes[2], model.evals.map((e) => ({ t: e.t, v: e.ai })), { signal: true, area: true, lo: Math.min(0, Math.min.apply(null, model.evals.map((e) => e.ai))),
      thresholds: [{ v: model.trigger, label: "trigger" }, { v: model.release, label: "release", below: true }] });

    // gate strip
    const gate = lanes[3];
    const lblG = el("text", { class: "lane-label", x: padL, y: gate.top - 12 }, svg);
    lblG.textContent = lanes[3].label;
    const unitG = el("text", { class: "lane-unit", x: W - padR, y: gate.top - 12, "text-anchor": "end" }, svg);
    unitG.textContent = compact ? "pass · fail" : "white pass · amber fail";
    const step = (W - padL - padR) / (model.end / 5);
    model.evals.forEach((e) => {
      el("rect", { class: e.pass ? "gate-pass" : "gate-fail", x: x(e.t) - Math.max(1.5, step * 0.32), y: gate.top + (e.pass ? 4 : 0),
        width: Math.max(3, step * 0.64), height: e.pass ? gate.h - 8 : gate.h, rx: 1.5 }, plotted);
    });

    // decisions
    model.decisions.forEach((d, i) => {
      el("line", { class: "decision", x1: x(d.t), x2: x(d.t), y1: lanes[0].top - 10, y2: gate.top + gate.h + 4 }, plotted);
      const right = x(d.t) > W * 0.7;
      const label = el("text", { class: "decision-label", x: x(d.t) + (right ? -6 : 6), y: lanes[2].top + 12 + i * 14,
        "text-anchor": right ? "end" : "start" }, plotted);
      label.textContent = compact ? d.action.split("_")[0] : d.action;
    });

    // cursor
    const cursor = el("g", { opacity: "0" }, svg);
    const cLine = el("line", { class: "cursor", y1: lanes[0].top - 10, y2: gate.top + gate.h + 4 }, cursor);
    const dots = { hr: el("circle", { class: "cursor-dot", r: 3.5 }, cursor), scl: el("circle", { class: "cursor-dot", r: 3.5 }, cursor),
      ai: el("circle", { class: "cursor-dot signal", r: 3.5 }, cursor) };
    const hit = el("rect", { class: "hit", x: 0, y: 0, width: W, height: H }, svg);

    const nearestWindow = (t) => model.windows.reduce((a, b) => (Math.abs(b.t - t) < Math.abs(a.t - t) ? b : a));
    const evalAtOrBefore = (t) => { let found = null; model.evals.forEach((e) => { if (e.t <= t + 2.5) { found = e; } }); return found || model.evals[0]; };
    let current = model.start ? model.evals.findIndex((e) => Math.abs(e.t - model.start.t) < 0.01) : 0;

    function show(t, snapEval) {
      const w = nearestWindow(t);
      const e = snapEval || evalAtOrBefore(t);
      const tx = snapEval ? e.t : t;
      cursor.setAttribute("opacity", "1");
      cLine.setAttribute("x1", x(tx)); cLine.setAttribute("x2", x(tx));
      dots.hr.setAttribute("cx", x(w.t)); dots.hr.setAttribute("cy", scales.hr(w.hr));
      dots.scl.setAttribute("cx", x(w.t)); dots.scl.setAttribute("cy", scales.scl(w.scl));
      dots.ai.setAttribute("cx", x(e.t)); dots.ai.setAttribute("cy", scales.ai(e.ai));
      const gateText = e.pass ? "PASS" : e.gate.join(" · ");
      $("specimen-readout").innerHTML =
        "<div><dt>Time</dt><dd>" + fmtTime(tx) + " · " + escapeHtml(e.id) + "</dd></div>" +
        "<div><dt>Heart rate</dt><dd>" + w.hr.toFixed(1) + " bpm</dd></div>" +
        "<div><dt>Skin conductance</dt><dd>" + w.scl.toFixed(2) + " µS</dd></div>" +
        "<div><dt>Arousal index</dt><dd>" + e.ai.toFixed(2) + "</dd></div>" +
        "<div><dt>Gate · state</dt><dd class=\"" + (e.pass ? (e.action ? "act" : "") : "hold") + "\">" + escapeHtml(gateText) +
          " · " + escapeHtml(e.action || e.state) + "</dd></div>";
    }
    const fromEvent = (ev) => { const r = svg.getBoundingClientRect(); return tAt((ev.clientX - r.left) * (W / r.width)); };
    hit.addEventListener("pointermove", (ev) => show(fromEvent(ev)));
    hit.addEventListener("pointerdown", (ev) => show(fromEvent(ev)));
    svg.addEventListener("keydown", (ev) => {
      if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight" && ev.key !== "Home" && ev.key !== "End") { return; }
      ev.preventDefault();
      if (ev.key === "Home") { current = 0; } else if (ev.key === "End") { current = model.evals.length - 1; }
      else { current = Math.max(0, Math.min(model.evals.length - 1, current + (ev.key === "ArrowRight" ? 1 : -1))); }
      show(model.evals[current].t, model.evals[current]);
    });
    show(model.evals[Math.max(0, current)].t, model.evals[Math.max(0, current)]);

    return { reveal: () => { clipRect.style.transition = "width 2.4s cubic-bezier(0.22, 1, 0.36, 1)"; clipRect.setAttribute("width", W); } };
  }

  function renderMoments(model) {
    const list = $("moments");
    const items = [];
    model.holds.forEach((h) => {
      const n = h.evals.length;
      items.push({ t: h.t0, cls: "hold", time: fmtTime(h.t0) + "–" + fmtTime(h.t1), title: "HOLD · gates failed",
        body: n + " consecutive evaluation" + (n === 1 ? "" : "s") + " failed quality gates (" + codeList(h.reasons) + ")" +
          (h.motion ? ", around a motion episode at " + h.motion[0].toFixed(0) + "–" + h.motion[1].toFixed(0) + " s" : "") +
          ". Controller state: <code>" + escapeHtml(h.state) + "</code>." });
    });
    model.decisions.forEach((d) => {
      const isStart = d.action.indexOf("START") === 0;
      items.push({ t: d.t, cls: "act", time: fmtTime(d.t) + " · " + escapeHtml(d.id), title: escapeHtml(d.action),
        body: isStart ? d.commands + " cue commands; execution <code>" + escapeHtml(d.execution || "") + "</code> (simulated observation)." :
          "Guidance released by the controller.",
        why: d.why });
    });
    items.sort((a, b) => a.t - b.t);
    list.innerHTML = items.map((m) => "<li class=\"moment reveal " + m.cls + "\"><time>" + m.time + "</time><h3>" + m.title + "</h3><p>" + m.body + "</p>" +
      (m.why ? "<p class=\"why\">“" + escapeHtml(m.why) + "”</p>" : "") + "</li>").join("");
  }

  function renderCaption(model) {
    const s = model.session, p = model.provenance;
    const parts = ["Simulation only. No person was measured.",
      "scenario " + s.scenario + " · seed " + s.seed + " · " + s.arm + " arm",
      "controller " + p.controller_version + " · pipeline " + p.pipeline_version];
    if (p.decision_replay) { parts.push("decision replay " + p.decision_replay.status + " across " + p.decision_replay.evaluations + " evaluations"); }
    if (p.scorecard) { parts.push("scorecard " + p.scorecard.passed + "/" + p.scorecard.total + " against simulated truth"); }
    if (p.ledger_sha256) { parts.push("ledger " + p.ledger_sha256.slice(0, 19) + "…"); }
    $("specimen-caption").textContent = parts.join("  ·  ");
  }

  function wireSession() {
    const data = window.CIRCLE_DEMO;
    if (!data || !data.timeline || !$("specimen-plot")) { return; }
    const model = sessionModel(data);
    renderMoments(model);
    renderCaption(model);
    let handle = drawSession(model);
    let revealed = still;
    const figure = $("specimen");
    if (!revealed && "IntersectionObserver" in window) {
      const io = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) { revealed = true; setTimeout(() => handle.reveal(), 250); io.disconnect(); }
      }, { threshold: 0.25 });
      io.observe(figure);
    } else { revealed = true; handle.reveal(); }
    let width = $("specimen-plot").clientWidth;
    window.addEventListener("resize", () => {
      const now = $("specimen-plot").clientWidth;
      if (Math.abs(now - width) < 2) { return; }
      width = now;
      handle = drawSession(model, revealed);
    });
  }

  ready(() => {
    drawHero();
    wireNav();
    wireSession();
    wireReveal();
    wireCopy();
    requestAnimationFrame(() => document.querySelectorAll(".hero .reveal").forEach((n) => n.classList.add("in")));
  });
})();
