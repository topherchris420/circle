/* CIRCLE film — the composition.
 *
 * One rule: a frame is a pure function of film time. Nothing here uses CSS
 * transitions, timers, or wall-clock animation, so the renderer can ask for
 * any timestamp and get the same picture, and the preview can scrub freely.
 *
 * The product shots are the real Resonance Workbench (workbench.html), driven
 * through its own tabs, scrubber, checkbox, and evidence list — the same
 * controls a visitor would use. Every number, label, and trace outside that
 * page comes from ad-data.js, which tools/build_ad.py generates from a real
 * simulated session, its verifier verdict, and the recorded R.A.I.N. run.
 */
(function () {
  "use strict";

  const AD = window.CIRCLE_AD;
  const TL = AD.workbench.timeline;
  const W = 1920, H = 1080, CHROME = 46;
  const params = new URLSearchParams(location.search);
  const RENDER = params.has("render");

  /* Edit decision lists: [master start, master end] segments, in film order.
   * The 90-second film is the master; the 30-second cut is the workbench-only
   * sequence (signals, audio + field, gate failure, evidence, end card). */
  const CUTS = {
    "90": [[0, 90]],
    "30": [[12.5, 17.5], [22.5, 27.5], [35, 47.5], [80, 87.5]],
  };
  const CUT = CUTS[params.get("cut")] ? params.get("cut") : "90";
  const EDL = CUTS[CUT];
  const DURATION = EDL.reduce((sum, [a, b]) => sum + (b - a), 0);
  function masterTime(tau) {
    let acc = 0;
    for (const [a, b] of EDL) {
      if (tau < acc + (b - a)) return a + (tau - acc);
      acc += b - a;
    }
    return EDL[EDL.length - 1][1];
  }

  const $ = (id) => document.getElementById(id);
  const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
  const prog = (t, a, b) => clamp01((t - a) / (b - a));
  const lerp = (a, b, f) => a + (b - a) * f;
  const ease = {
    linear: (x) => x,
    inCubic: (x) => x * x * x,
    outCubic: (x) => 1 - Math.pow(1 - x, 3),
    inOut: (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
    outExpo: (x) => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x)),
    outBack: (x) => 1 + 2.4 * Math.pow(x - 1, 3) + 1.4 * Math.pow(x - 1, 2),
  };
  /* Piecewise keyframes: [[t, v0, v1, ...], ...], eased between neighbours. */
  function key(frames, t, fn) {
    if (t <= frames[0][0]) return frames[0].slice(1);
    const last = frames[frames.length - 1];
    if (t >= last[0]) return last.slice(1);
    let i = 0;
    while (frames[i + 1][0] <= t) i++;
    const a = frames[i], b = frames[i + 1];
    const f = (fn || ease.inOut)((t - a[0]) / (b[0] - a[0] || 1));
    return a.slice(1).map((v, k) => lerp(v, b[k + 1], f));
  }
  const fmt = (v, d) => Number(v).toFixed(d);

  /* ------------------------------------------------------------------ data */
  const events = TL.feedback.events;
  const evaluations = TL.evaluations;
  const sToUs = 1e6;
  const feedbackAt = (s) => { let out = events[0]; for (const e of events) { if (e.time_us / sToUs <= s) out = e; else break; } return out; };
  const staleEval = evaluations.find((e) => e.gate.includes("DATA_STALE"));
  const stopDecision = TL.decisions.find((d) => d.action === "STOP_QUALITY_LOST");
  const mmss = (us) => { const s = us / sToUs; return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(Math.floor(s % 60)).padStart(2, "0"); };
  const STALE_T = staleEval.decision_time_us / sToUs;        // device seconds at the DATA_STALE evaluation
  const GAP = AD.raw.ppg_gap_s;

  /* ------------------------------------------------- generated DOM content */
  const tickSvg = '<svg viewBox="0 0 18 18"><path d="M3.5 9.6 L7.4 13.2 L14.5 5" fill="none" stroke="#7fbf7a" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  (function buildRain() {
    const live = AD.rain.rain_live;
    const first = (k) => (live.attempts[k] && live.attempts[k][0]) || {};
    const model = first("scenario").model || "";
    $("rain-meta").textContent = "Live runtime · model " + model + " · three bounded choices, each with its own confidence.";
    const rows = [
      ["scenario", "scenario", String(live.answers.scenario)],
      ["cue_period_s", "cue period", live.answers.cue_period_s + " s"],
      ["min_beat_coverage", "min. beat coverage", fmt(live.answers.min_beat_coverage, 2)],
    ];
    $("rain-rows").innerHTML = rows.map(([k, label, value], i) => {
      const conf = first(k).confidence;
      const hash = (live.reasoning[k] || {}).envelope_hash || "";
      return '<div class="row" data-in="' + (52.9 + i * 0.4) + '" data-out="57.0">' +
        '<span class="k">' + label + '</span><span class="v">' + value + "</span>" +
        '<span class="c"><span class="bar"><i data-grow="' + (53.2 + i * 0.4) + '" data-to="' + conf + '"></i></span>' +
        "confidence <b>" + fmt(conf, 2) + "</b><span>· envelope " + hash.slice(0, 12) + "…</span></span></div>";
    }).join("");

    const seeds = AD.rain.seeds;
    const checks = [
      "Simulation-only target",
      "Matched sham arm",
      "Held-out seeds " + seeds[0] + "–" + seeds[seeds.length - 1],
      "Quality gates: tighten only",
      "Human sign-off, bound to the protocol hash",
    ];
    $("rain-checks").innerHTML = checks.map((text, i) =>
      '<li data-in="' + (54.35 + i * 0.36) + '" data-out="57.0"><span class="tick" data-tick="' + (54.6 + i * 0.36) + '">' + tickSvg + "</span>" + text + "</li>").join("");

    const plan = AD.rain_analysis_plan || {};
    $("compare-meta").textContent = "Seeds " + seeds.join(", ") + " · mean difference, active − sham · " +
      String(plan.test || "").toLowerCase().replace(/_/g, " ") + " · α = " + plan.alpha;
    const names = { HUMAN_DESIGNED: "Human-designed", FIXED_DEFAULT: "Fixed default", RANDOM_BASELINE: "Random baseline" };
    const bars = [{ name: "R.A.I.N. proposal", sub: model + " · " + live.answers.scenario, d: live.result.mean_difference_active_minus_sham,
      p: live.result.p_adjusted, c: live.result.conclusion, rain: true }]
      .concat(AD.rain.executed.map((e) => ({ name: names[e.label] || e.label, sub: e.protocol_id + " · " + e.scenario,
        d: e.primary.mean_difference_active_minus_sham, p: e.primary.p_adjusted, c: e.primary.conclusion })));
    const scale = Math.max(...bars.map((b) => Math.abs(b.d))) * 1.18;
    $("compare-bars").innerHTML = bars.map((b, i) =>
      '<div class="bar-row' + (b.rain ? " rain" : "") + '" data-in="' + (57.85 + i * 0.2) + '" data-out="62.0">' +
      '<span class="name">' + b.name + "<small>" + b.sub + "</small></span>" +
      '<span class="track"><i data-grow="' + (58.2 + i * 0.2) + '" data-to="' + Math.abs(b.d) / scale + '"></i></span>' +
      '<span class="d">' + fmt(b.d, 3).replace("-", "−") + '</span><span class="p">p<sub>adj</sub> ' + b.p + "</span>" +
      '<span class="verdict" data-in="' + (60.0 + i * 0.16) + '" data-out="62.0" data-style="stamp">' + b.c + "</span></div>").join("");
    $("rain-path").textContent = AD.rain_source;
  })();

  (function buildVerify() {
    $("dl-name").textContent = AD.bundle.name;
    $("dl-meta").textContent = AD.bundle.artifacts.length + " artifacts · " + fmt(AD.bundle.artifact_bytes / 1e6, 1) + " MB · SHA-256 each";
    const detail = {
      artifact_hashes: (d) => d.artifacts + " files", session_contract: (d) => d.records + " records",
      analysis_rederived: (d) => d.beats + " beats", decisions_replayed: (d) => d.evaluations + " evaluations",
      temporal_lawfulness: (d) => d.decisions_checked + " decisions", session_rederived: (d) => d.rebuilt + " rebuilt",
    };
    const names = Object.keys(AD.verdict.checks);
    $("verify-checks").innerHTML = names.map((name, i) => {
      const check = AD.verdict.checks[name];
      const extra = detail[name] && check.detail ? detail[name](check.detail) : "";
      return '<li data-in="' + (71.9 + i * 0.26) + '" data-out="77.0"><span class="tick" data-tick="' + (72.15 + i * 0.26) + '">' + tickSvg + "</span>" +
        name + (extra ? "<em>" + extra + "</em>" : "") + "</li>";
    }).join("");
    $("quote-ver").textContent = "controller " + TL.provenance.controller_version;
    $("legal").textContent = "Open source · Simulation-based · Not a medical device. Every signal shown is simulated; no person was measured " +
      "and no effect in people is claimed. Session " + AD.workbench.runs[0].id.slice(0, 8) + " · seed " + AD.session.seed +
      " · pipeline " + TL.provenance.pipeline_version + " · controller " + TL.provenance.controller_version + ". R.A.I.N. result from the recorded run of 2026-11-15.";
  })();

  /* ---------------------------------------------- auto in/out (text beats) */
  const autos = Array.from(document.querySelectorAll("[data-in]")).map((el) => ({
    el, tin: Number(el.dataset.in), tout: Number(el.dataset.out), style: el.dataset.style || (el.classList.contains("cap") ? "cap" : "rise"),
    cap: el.classList.contains("cap") || el.classList.contains("cap-data"), on: false,
  }));
  const grows = Array.from(document.querySelectorAll("[data-grow]")).map((el) => ({ el, t: Number(el.dataset.grow), to: Number(el.dataset.to) }));
  const ticks = Array.from(document.querySelectorAll("[data-tick]")).map((el) => ({ el, t: Number(el.dataset.tick), svg: el.firstChild }));

  function applyAutos(t) {
    let capOpacity = 0;
    for (const a of autos) {
      const dIn = a.style === "stamp" ? 0.42 : a.style === "cap" ? 0.7 : 0.95;
      const dOut = a.style === "stamp" ? 0.3 : 0.45;
      const pin = prog(t, a.tin, a.tin + dIn), pout = prog(t, a.tout, a.tout + dOut);
      if (pin <= 0 || pout >= 1) {
        if (a.on) { a.el.style.visibility = "hidden"; a.on = false; }
        continue;
      }
      const ei = ease.outExpo(pin), eo = ease.inCubic(pout);
      let opacity, transform, blur = 0;
      if (a.style === "stamp") {
        opacity = Math.min(1, pin * 5) * (1 - eo);
        transform = "scale(" + lerp(1.28, 1, ease.outBack(pin)).toFixed(4) + ")";
      } else {
        const rise = a.style === "cap" ? 26 : 44;
        opacity = ei * (1 - eo);
        transform = "translateY(" + ((1 - ei) * rise - eo * 18).toFixed(2) + "px)";
        blur = (1 - ei) * 14 + eo * 8;
      }
      a.el.style.visibility = "visible";
      a.el.style.opacity = opacity.toFixed(4);
      a.el.style.transform = transform;
      a.el.style.filter = blur > 0.08 ? "blur(" + blur.toFixed(2) + "px)" : "none";
      a.on = true;
      if (a.cap && opacity > capOpacity) capOpacity = opacity;
    }
    for (const g of grows) {
      g.el.style.transform = "scaleX(" + (g.to * ease.outCubic(prog(t, g.t, g.t + 0.9))).toFixed(4) + ")";
    }
    for (const k of ticks) {
      const p = prog(t, k.t, k.t + 0.3);
      k.svg.style.opacity = p > 0 ? "1" : "0";
      k.svg.style.transform = "scale(" + (p > 0 ? lerp(0.3, 1, ease.outBack(p)) : 0).toFixed(3) + ")";
      k.el.style.borderColor = p > 0 ? "#7fbf7a" : "";
    }
    return capOpacity;
  }

  /* ----------------------------------------------------- the product window */
  const shell = $("wb-shell"), frameEl = $("wb");
  let doc = null, win = null;
  const wb = {
    view: null, audio: null, selected: undefined, lastSeek: null,
    setView(name) {
      if (this.view === name) return;
      doc.querySelector('.view-tab[data-view="' + name + '"]').click();
      this.view = name; this.lastSeek = null;
    },
    setAudio(on) {
      if (this.audio === on) return;
      const box = doc.getElementById("audio-enable");
      if (box.checked !== on) { box.checked = on; box.dispatchEvent(new Event("change")); }
      this.audio = on;
    },
    seek(s) {
      const scrub = doc.getElementById("scrub");
      scrub.value = String(s);
      scrub.dispatchEvent(new Event("input"));
      this.lastSeek = s;
    },
    entry(kind, time) {
      const buttons = doc.querySelectorAll("#evidence-list button");
      for (const b of buttons) {
        if (b.querySelector(".ev-kind").textContent === kind && b.querySelector(".ev-t").textContent === time) return b;
      }
      return null;
    },
    select(target) {
      const id = target ? target.kind + "@" + target.time : null;
      if (this.selected === id) return;
      doc.querySelectorAll("#evidence-list button").forEach((b) => b.setAttribute("aria-current", "false"));
      if (target) {
        const b = this.entry(target.kind, target.time);
        if (b) b.click();
      } else {
        const detail = doc.getElementById("evidence-detail");
        detail.innerHTML = '<p class="quiet">Choose an event on the left.</p>';
      }
      this.selected = id;
    },
  };

  const STALE_ENTRY = { kind: "eval · " + staleEval.state_after, time: mmss(staleEval.decision_time_us) };
  const STOP_ENTRY = { kind: stopDecision.action, time: mmss(stopDecision.decision_time_us) };

  /* Camera: [t, focus x, focus y (window px, chrome included), scale]. */
  const CAM = [
    [12.5, 720, 523, 0.80], [13.4, 720, 523, 0.86], [14.3, 720, 523, 0.86],
    [17.4, 560, 336, 1.42], [19.3, 584, 356, 1.46], [20.5, 604, 716, 1.46], [22.499, 620, 724, 1.50],
    [22.5, 700, 500, 1.18], [24.999, 540, 456, 1.50],
    [25.0, 720, 500, 1.28], [29.999, 720, 500, 1.46],
    [30.0, 1010, 412, 1.42], [32.6, 1040, 396, 1.60],
    [39.8, 720, 590, 1.30], [42.499, 720, 600, 1.42],
    [42.5, 720, 520, 0.98], [43.4, 760, 500, 1.04], [44.3, 958, 392, 1.5], [45.45, 958, 560, 1.5], [46.35, 958, 742, 1.5],
    [46.4, 770, 580, 1.10], [46.95, 780, 570, 1.12], [47.45, 900, 430, 1.34], [50.0, 930, 410, 1.42],
  ];
  /* Page scroll inside the workbench window: [t, scrollY]. */
  const SCROLL = [
    [14.3, 0], [16.4, 215], [22.499, 215], [22.5, 0], [24.999, 0], [25.0, 150], [29.999, 150], [30.0, 215], [33, 215],
    [39.8, 150], [42.499, 150], [42.5, 0], [44.3, 0], [45.45, 180], [46.35, 363], [46.4, 0], [50, 0],
  ];
  /* Session playhead (seconds into the recorded session): [t, s]. */
  const SESSION = [
    [12.9, 0], [21.6, 236], [22.5, 236.5], [25.0, 239.5], [30.0, 249.6], [32.6, 252.4],
    [39.8, 258.4], [42.5, 263.4], [50, 263.4],
  ];
  const viewAt = (t) => (t < 22.5 ? "dashboard" : t < 25 ? "studio" : t < 30 ? "visual" : t < 39 ? "dashboard" : t < 42.5 ? "visual" : "evidence");
  const AUDIO_ON_T = 23.75;
  const SELECT_STALE_T = 43.15, SELECT_STOP_T = 46.9;

  let cam = { x: 0, y: 0, s: 1 };
  function applyWorkbench(t) {
    const visible = (t >= 12.5 && t < 32.75) || (t >= 39.8 && t < 50.0);
    if (!visible || !doc) { shell.style.visibility = "hidden"; return false; }
    const [fx, fy, s] = key(CAM, t);
    let opacity = 1, lift = 0;
    if (t < 13.4) { const p = ease.outExpo(prog(t, 12.5, 13.4)); opacity = p; lift = (1 - p) * 90; }
    if (t > 32.3 && t < 33) opacity = 1 - ease.inOut(prog(t, 32.3, 32.75));
    if (t >= 39.8 && t < 40.4) opacity = ease.outCubic(prog(t, 39.8, 40.4));
    if (t > 49.5) opacity = 1 - ease.inOut(prog(t, 49.5, 49.95));
    cam = { x: W / 2 - fx * s, y: H / 2 - fy * s + lift, s };
    shell.style.visibility = "visible";
    shell.style.opacity = opacity.toFixed(4);
    shell.style.transform = "translate(" + cam.x.toFixed(2) + "px," + cam.y.toFixed(2) + "px) scale(" + s.toFixed(5) + ")";

    wb.setView(viewAt(t));
    wb.setAudio(t >= AUDIO_ON_T);
    if (wb.view === "evidence") {
      wb.select(t >= SELECT_STOP_T ? STOP_ENTRY : t >= SELECT_STALE_T ? STALE_ENTRY : null);
      const list = doc.getElementById("evidence-list");
      const target = wb.entry(STALE_ENTRY.kind, STALE_ENTRY.time);
      if (list && target) {
        const want = Math.max(0, target.offsetTop - list.offsetTop - 250);
        list.scrollTop = want * ease.inOut(prog(t, 42.5, 43.0));
      }
    }
    if (wb.view === "visual") wb.seek(key(SESSION, t - 1 / 60, ease.linear)[0]);
    wb.seek(key(SESSION, t, ease.linear)[0]);
    win.scrollTo(0, key(SCROLL, t)[0]);
    return true;
  }
  /* A point or box inside the workbench page, in stage coordinates. */
  function stageRect(el) {
    const r = el.getBoundingClientRect();
    return { x: cam.x + r.left * cam.s, y: cam.y + (r.top + CHROME) * cam.s, w: r.width * cam.s, h: r.height * cam.s };
  }
  function stageCenter(el, dx, dy) {
    const r = stageRect(el);
    return [r.x + (dx === undefined ? r.w / 2 : dx * cam.s), r.y + (dy === undefined ? r.h / 2 : dy * cam.s)];
  }

  /* Highlights over real rows in the evidence detail panel. */
  const hlLayer = $("hl-layer");
  const HL = [
    { label: "quality gate", a: 44.15, b: 46.35, cls: "amber" },
    { label: "ppg_age_s", a: 44.95, b: 46.35, cls: "" },
    { label: "muted because", a: 45.8, b: 46.35, cls: "amber" },
  ].map((h) => { const el = document.createElement("div"); el.className = "hl " + h.cls; hlLayer.appendChild(el); return Object.assign(h, { el }); });
  function applyHighlights(t) {
    for (const h of HL) {
      const p = prog(t, h.a, h.a + 0.35), q = prog(t, h.b - 0.2, h.b);
      if (!doc || wb.view !== "evidence" || p <= 0 || q >= 1) { h.el.style.visibility = "hidden"; continue; }
      const dt = Array.from(doc.querySelectorAll("#evidence-detail dt")).find((n) => n.textContent === h.label);
      if (!dt || !dt.nextElementSibling) { h.el.style.visibility = "hidden"; continue; }
      const a = stageRect(dt), b = stageRect(dt.nextElementSibling);
      const pad = 9 * cam.s;
      const x = a.x - pad, y = Math.min(a.y, b.y) - pad * 0.5, w = b.x + b.w - a.x + pad * 2, hgt = Math.max(a.h, b.h) + pad;
      h.el.style.visibility = "visible";
      h.el.style.opacity = (ease.outCubic(p) * (1 - q)).toFixed(3);
      h.el.style.left = x.toFixed(1) + "px"; h.el.style.top = y.toFixed(1) + "px";
      h.el.style.width = w.toFixed(1) + "px"; h.el.style.height = hgt.toFixed(1) + "px";
    }
  }

  /* The pointer: travels to real controls and presses them. */
  const cursor = $("cursor"), click = $("click");
  const MOVES = [
    { a: 22.7, b: 23.58, press: 23.7, hide: 24.6, from: [1420, 880], to: () => stageCenter(doc.getElementById("audio-enable")) },
    { a: 42.55, b: 43.04, press: 43.12, hide: 43.9, from: [1250, 820], to: () => { const b = wb.entry(STALE_ENTRY.kind, STALE_ENTRY.time); return b ? stageCenter(b, 120) : [0, 0]; } },
    { a: 46.4, b: 46.8, press: 46.88, hide: 47.45, from: [1180, 760], to: () => { const b = wb.entry(STOP_ENTRY.kind, STOP_ENTRY.time); return b ? stageCenter(b, 120) : [0, 0]; } },
  ];
  function applyCursor(t) {
    let shown = false, pressed = false;
    for (const m of MOVES) {
      if (t < m.a - 0.25 || t > m.hide || !doc) continue;
      const to = m.to();
      const f = ease.inOut(prog(t, m.a, m.b));
      const x = lerp(m.from[0], to[0], f), y = lerp(m.from[1], to[1], f);
      const alpha = Math.min(prog(t, m.a - 0.25, m.a), 1 - prog(t, m.hide - 0.3, m.hide));
      const dip = 1 - 0.14 * Math.sin(Math.PI * prog(t, m.press - 0.07, m.press + 0.13));
      cursor.style.visibility = "visible";
      cursor.style.opacity = alpha.toFixed(3);
      cursor.style.transform = "translate(" + (x - 5).toFixed(1) + "px," + (y - 3).toFixed(1) + "px) scale(" + (1.5 * dip).toFixed(3) + ")";
      shown = true;
      const r = prog(t, m.press, m.press + 0.5);
      if (r > 0 && r < 1) {
        click.style.visibility = "visible";
        click.style.opacity = (1 - r).toFixed(3);
        click.style.transform = "translate(" + to[0].toFixed(1) + "px," + to[1].toFixed(1) + "px) scale(" + lerp(0.3, 1.5, ease.outCubic(r)).toFixed(3) + ")";
        pressed = true;
      }
    }
    if (!shown) cursor.style.visibility = "hidden";
    if (!pressed) click.style.visibility = "hidden";
  }

  /* ------------------------------------------------------------ raw traces */
  const canvas = $("traces"), g = canvas.getContext("2d");
  function segments(stream, gapS) {
    const out = []; let cur = null;
    for (let i = 0; i < stream.t_s.length; i++) {
      if (!cur || stream.t_s[i] - cur.t[cur.t.length - 1] > gapS) { cur = { t: [], v: [] }; out.push(cur); }
      cur.t.push(stream.t_s[i]); cur.v.push(stream.v[i]);
    }
    return out;
  }
  function movingMean(v, half) {
    const out = new Array(v.length); let sum = 0, lo = 0, hi = -1;
    for (let i = 0; i < v.length; i++) {
      const a = Math.max(0, i - half), b = Math.min(v.length - 1, i + half);
      while (hi < b) sum += v[++hi];
      while (lo < a) sum -= v[lo++];
      out[i] = sum / (hi - lo + 1);
    }
    return out;
  }
  function percentile(values, q) { const s = values.slice().sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(q * s.length))]; }
  /* Pulse wave: the AC component of the infrared counts, inverted so systole points up. */
  function prepPulse(stream) {
    const segs = segments(stream, 0.2);
    let all = [];
    for (const s of segs) { const base = movingMean(s.v, 30); s.y = s.v.map((v, i) => -(v - base[i])); all = all.concat(s.y.map(Math.abs)); }
    const amp = percentile(all, 0.97) || 1;
    for (const s of segs) s.y = s.y.map((y) => Math.max(-1.4, Math.min(1.4, y / amp)));
    return segs;
  }
  function prepSlow(stream) {
    const segs = segments(stream, 0.2);
    const all = stream.v, lo = percentile(all, 0.02), hi = percentile(all, 0.98), mid = (lo + hi) / 2, span = (hi - lo) / 2 || 1;
    for (const s of segs) s.y = movingMean(s.v, 4).map((v) => Math.max(-1.3, Math.min(1.3, (v - mid) / span)));
    return segs;
  }
  function prepMotion(stream) {
    const segs = segments(stream, 0.2);
    const med = percentile(stream.v, 0.5);
    const dev = Math.max(120, percentile(stream.v.map((v) => Math.abs(v - med)), 0.995));
    for (const s of segs) s.y = s.v.map((v) => Math.max(-1.3, Math.min(1.3, (v - med) / dev)));
    return segs;
  }
  const RAW = {};
  for (const name of ["opening", "dropout"]) {
    RAW[name] = { ppg: prepPulse(AD.raw[name].ppg_ir), eda: prepSlow(AD.raw[name].eda), imu: prepMotion(AD.raw[name].imu_ax), w: AD.raw[name].window_s };
  }

  function strokeTrace(segs, xOf, yc, amp, tMax, color, width, glow) {
    g.lineJoin = "round"; g.lineCap = "round"; g.strokeStyle = color; g.lineWidth = width;
    g.shadowColor = color; g.shadowBlur = glow;
    let head = null;
    for (const s of segs) {
      if (s.t[0] > tMax) break;
      g.beginPath();
      let started = false;
      for (let i = 0; i < s.t.length; i++) {
        let t = s.t[i], y = s.y[i];
        if (t > tMax) {
          if (i > 0) { const f = (tMax - s.t[i - 1]) / (t - s.t[i - 1]); y = lerp(s.y[i - 1], y, f); t = tMax; } else break;
        }
        const x = xOf(t), py = yc - y * amp;
        if (x < -40) continue;
        if (!started) { g.moveTo(x, py); started = true; } else g.lineTo(x, py);
        head = [x, py];
        if (t >= tMax) break;
      }
      g.stroke();
    }
    g.shadowBlur = 0;
    return head;
  }
  function headDot(head, color, r) {
    if (!head) return;
    g.fillStyle = "#ffffff"; g.shadowColor = color; g.shadowBlur = 26;
    g.beginPath(); g.arc(head[0], head[1], r, 0, Math.PI * 2); g.fill();
    g.shadowBlur = 0;
  }

  const TEAL = "#67c6c3", AMBER = "#d9a441";
  function drawOpening(t) {
    const raw = RAW.opening, w0 = raw.w[0], w1 = raw.w[1];
    const collapse = ease.inCubic(prog(t, 6.45, 7.55));
    const alpha = (1 - prog(t, 6.9, 7.55)) * prog(t, 0.5, 0.9);
    if (alpha <= 0) return;
    const rows = [
      { segs: raw.ppg, yc: 272, amp: 38, a: 0.7, b: 3.1, color: TEAL, width: 3, glow: 20 },
      { segs: raw.eda, yc: 410, amp: 26, a: 2.2, b: 4.1, color: "#8fd6d3", width: 2.4, glow: 14 },
      { segs: raw.imu, yc: 520, amp: 16, a: 2.6, b: 4.5, color: "#b6e3e1", width: 2, glow: 10 },
    ];
    for (const row of rows) {
      const p = ease.outCubic(prog(t, row.a, row.b));
      if (p <= 0) continue;
      const yc = lerp(row.yc, 540, collapse), sx = 1 - collapse * 0.985;
      g.save();
      g.globalAlpha = alpha;
      g.translate(960, 0); g.scale(sx, 1); g.translate(-960, 0);
      const xOf = (ts) => 150 + ((ts - w0) / (w1 - w0)) * 1620;
      const head = strokeTrace(row.segs, xOf, yc, row.amp * (1 - collapse * 0.6), lerp(w0, w1, p), row.color, row.width / Math.max(sx, 0.25), row.glow);
      if (p < 1) headDot(head, row.color, 5);
      g.restore();
    }
  }

  /* The dropout: a monitor that scrolls through the declared PPG gap. Device time
   * is paced so the DATA_STALE evaluation lands exactly on the downbeat at 37.5 s. */
  const GATE_T = 37.5;
  const dataTime = (t) => (t <= GATE_T ? STALE_T - (GATE_T - t) * 3.0 : STALE_T + (t - GATE_T) * 1.2);
  const LOSS_AT = GATE_T - (STALE_T - GAP.start) / 3.0;      // film time when the last pulse sample arrives
  function drawDropout(t) {
    const alpha = prog(t, 34.55, 35.0) * (1 - prog(t, 39.4, 39.85));
    if (alpha <= 0) return;
    const raw = RAW.dropout, now = dataTime(t), xNow = 1330, pps = 150;
    const xOf = (ts) => xNow - (now - ts) * pps;
    g.save();
    g.globalAlpha = alpha;
    // now-line
    g.strokeStyle = "rgba(255,255,255,0.16)"; g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(xNow, 250); g.lineTo(xNow, 850); g.stroke();
    const lost = now > GAP.start + 0.05;
    const head = strokeTrace(raw.ppg.filter((s) => s.t[0] < GAP.end - 1), xOf, 470, 92, now, TEAL, 3.4, 24);
    if (lost) {
      const x0 = Math.max(110, xOf(GAP.start));
      g.strokeStyle = "rgba(217,164,65,0.75)"; g.lineWidth = 2.5; g.setLineDash([3, 13]); g.lineCap = "round";
      g.beginPath(); g.moveTo(x0, 470); g.lineTo(xNow, 470); g.stroke(); g.setLineDash([]);
      g.fillStyle = AMBER; g.shadowColor = AMBER; g.shadowBlur = 22;
      g.beginPath(); g.arc(xNow, 470, 6, 0, Math.PI * 2); g.fill(); g.shadowBlur = 0;
    } else {
      headDot(head, TEAL, 6);
    }
    headDot(strokeTrace(raw.eda, xOf, 730, 24, now, "rgba(143,214,211,0.62)", 2.2, 8), "#8fd6d3", 3.5);
    headDot(strokeTrace(raw.imu, xOf, 838, 15, now, "rgba(182,227,225,0.5)", 1.8, 6), "#b6e3e1", 3);
    // soft left edge
    const fade = g.createLinearGradient(0, 0, 420, 0);
    fade.addColorStop(0, "rgba(5,8,10,1)"); fade.addColorStop(0.3, "rgba(5,8,10,0.92)"); fade.addColorStop(1, "rgba(5,8,10,0)");
    g.globalAlpha = 1; g.fillStyle = fade; g.fillRect(0, 230, 420, 660);
    g.restore();

    const state = $("drop-state");
    state.textContent = lost ? "no samples" : "optical pulse";
    state.className = lost ? "lost" : "";
    const age = $("drop-age");
    const running = Math.max(0, now - 1.0 - GAP.start);
    const frozen = t >= GATE_T;
    age.innerHTML = "ppg_age_s<b>" + fmt(frozen ? staleEval.features.ppg_age_s : running, 3) + "</b>" + (frozen ? " · " + staleEval.id : "");
    age.style.left = (xNow + 26) + "px"; age.style.top = "452px";
  }

  /* -------------------------------------------------------- ring + chapter */
  const ring = $("ring");
  const arc = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  arc.setAttribute("class", "ring-arc"); arc.setAttribute("r", "110"); arc.setAttribute("transform", "rotate(-90)");
  $("ring-arcs").appendChild(arc);
  const CIRC = 2 * Math.PI * 110;
  const CHAPTERS = [
    { n: "01", name: "SENSING", a: 10, b: 22.5 }, { n: "02", name: "ADAPTATION", a: 22.5, b: 32.5 },
    { n: "03", name: "UNCERTAINTY", a: 32.5, b: 50 }, { n: "04", name: "REASONING", a: 50, b: 67.5 },
    { n: "05", name: "VERIFICATION", a: 67.5, b: 80 },
  ];
  const HUD_POS = [1374, 1023, 0.155], END_POS = [960, 306, 0.74];
  let titlePos = [690, 495, 0.62];
  function measureTitle() {
    const gap = document.querySelector(".lockup-gap").getBoundingClientRect(), st = $("stage").getBoundingClientRect();
    const k = st.width / W;
    titlePos = [(gap.left - st.left + gap.width / 2) / k - 14, (gap.top - st.top + gap.height / 2) / k, 0.62];
  }
  function applyRing(t) {
    if (t < 7.5 || t >= 89.6) { ring.style.visibility = "hidden"; }
    else {
      let pos, frac, base = 1;
      if (t < 10.1) {
        const move = ease.inOut(prog(t, 9.35, 10.1));
        pos = titlePos.map((v, i) => lerp(v, HUD_POS[i], move));
        frac = ease.outCubic(prog(t, 7.5, 8.6)) * (1 - ease.inOut(prog(t, 9.35, 10.0)));
        base = prog(t, 9.4, 10.0);
      } else if (t < 80) {
        pos = HUD_POS;
        let done = 0;
        CHAPTERS.forEach((c, i) => { if (t >= c.a) done = i + prog(t, c.a, c.b); });
        frac = done / CHAPTERS.length;
      } else {
        const move = ease.inOut(prog(t, 80.0, 81.3));
        pos = HUD_POS.map((v, i) => lerp(v, END_POS[i], move));
        frac = 1;
      }
      ring.style.visibility = "visible";
      ring.style.transform = "translate(" + (pos[0] - 150 * pos[2]).toFixed(2) + "px," + (pos[1] - 150 * pos[2]).toFixed(2) + "px) scale(" + pos[2].toFixed(5) + ")";
      arc.setAttribute("stroke-dasharray", (CIRC * frac).toFixed(2) + " " + CIRC.toFixed(2));
      arc.style.opacity = frac > 0.001 ? "1" : "0";
      ring.querySelector(".ring-base").style.opacity = base.toFixed(3);
    }
    const chapter = $("chapter"), badge = $("sim-badge");
    const current = CHAPTERS.find((c) => t >= c.a && t < c.b);
    if (current) {
      const o = Math.min(prog(t, current.a + 0.1, current.a + 0.55), 1 - prog(t, current.b - 0.3, current.b));
      $("chapter-n").textContent = current.n; $("chapter-name").textContent = current.name;
      chapter.style.visibility = "visible"; chapter.style.opacity = (0.92 * o).toFixed(3);
    } else chapter.style.visibility = "hidden";
    const bo = Math.min(prog(t, 0.9, 1.6), 1 - prog(t, 79.7, 80.3));
    badge.style.visibility = bo > 0 ? "visible" : "hidden"; badge.style.opacity = (0.9 * bo).toFixed(3);
  }

  /* ----------------------------------------------------- terminal + extras */
  const term = $("term");
  const COMMAND = "python tools/verify_replication.py " + AD.bundle.name.replace(".zip", "/") + " --json verdict.json";
  function applyTerminal(t) {
    if (t < 70.3 || t > 77.8) return;
    const typed = Math.floor(prog(t, 70.6, 71.8) * COMMAND.length);
    let html = '<span class="pr">$ </span>' + COMMAND.slice(0, typed);
    const out = t >= 75.0;
    if (!out) html += (t < 71.8 || Math.floor(t * 2.2) % 2 === 0) ? '<span class="caret"></span>' : "";
    else {
      html += '\n<span class="ok">VERDICT: ' + AD.verdict.verdict + "</span>";
      if (t >= 75.15) html += "\n  replay status: " + AD.verdict.replay_status;
      if (t >= 75.3) html += '\n<span class="dimline">A matching replay shows the package reproduces from its inputs — not that it measured the world.</span>';
    }
    term.innerHTML = html;
  }
  function applyAdaptData(t) {
    if (t < 25.7 || t > 30.4 || wb.lastSeek === null) return;
    const e = feedbackAt(wb.lastSeek);
    $("adapt-data").textContent = "level " + fmt(e.parameters.level, 3) + " of a " + fmt(TL.feedback.config.max_gain, 2) + " ceiling · breath " +
      fmt(e.parameters.breath_period_s, 1) + " s · gate " + (e.gate_reasons.length ? e.gate_reasons.join(", ") : "pass") + " · state " + e.state;
  }

  /* -------------------------------------------------------- atmosphere */
  const glow = $("glow"), dim = $("wb-dim"), fade = $("fade");
  function mix(a, b, f) { return a.map((v, i) => Math.round(lerp(v, b[i], f))); }
  const C_TEAL = [103, 198, 195], C_AMBER = [217, 164, 65], C_GREEN = [127, 191, 122];
  function applyAtmosphere(t, capOpacity, wbVisible) {
    let color = C_TEAL, strength = 0.0;
    strength = Math.max(strength, 0.10 * prog(t, 0.6, 3) * (1 - prog(t, 6.5, 7.5)));
    strength = Math.max(strength, 0.20 * prog(t, 7.5, 8.6));
    const amber = prog(t, 37.4, 37.9) * (1 - prog(t, 49.0, 50.0));
    const amber2 = prog(t, 62.5, 63.2) * (1 - prog(t, 66.6, 67.4));
    const green = prog(t, 74.95, 75.35) * (1 - prog(t, 77.0, 77.6));
    color = mix(color, C_AMBER, Math.max(amber, amber2));
    color = mix(color, C_GREEN, green);
    if (wbVisible) strength = Math.max(strength, 0.16);
    if (t >= 80) strength = Math.max(strength, 0.24 * prog(t, 80, 82));
    glow.style.opacity = "1";
    glow.style.background = "radial-gradient(52% 48% at 50% 46%, rgba(" + color.join(",") + "," + strength.toFixed(3) + ") 0%, rgba(" + color.join(",") + ",0) 72%)";

    const quote = prog(t, 47.45, 47.95) * (1 - prog(t, 49.5, 49.95));
    if (quote > 0) { dim.className = "full"; dim.style.opacity = quote.toFixed(3); }
    else { dim.className = ""; dim.style.opacity = wbVisible ? shell.style.opacity : "0"; }
  }
  function applyFade(tau, t) {
    let black = 0;
    if (CUT === "90") black = Math.max(1 - prog(t, 0.0, 0.7), prog(t, 88.9, 89.9));
    else black = Math.max(1 - prog(tau, 0.0, 0.35), prog(tau, DURATION - 0.7, DURATION - 0.05));
    fade.style.opacity = black.toFixed(4);
  }

  /* ------------------------------------------------------------------ dither */
  (function grain() {
    const el = $("grain"), c = el.getContext("2d"), image = c.createImageData(el.width, el.height), px = image.data;
    let state = 0x2f6e2b1;
    for (let i = 0; i < px.length; i += 4) {
      state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
      const v = state >>> 30;                       // 0..3 code values
      px[i] = v; px[i + 1] = v; px[i + 2] = v; px[i + 3] = 255;
    }
    c.putImageData(image, 0, 0);
  })();

  /* ------------------------------------------------------------- the frame */
  function render(tau) {
    const t = masterTime(Math.max(0, Math.min(DURATION, tau)));
    const capOpacity = applyAutos(t);
    const wbVisible = applyWorkbench(t);
    g.clearRect(0, 0, W, H);
    drawOpening(t);
    drawDropout(t);
    applyHighlights(t);
    applyCursor(t);
    applyRing(t);
    applyTerminal(t);
    applyAdaptData(t);
    applyAtmosphere(t, capOpacity, wbVisible);
    applyFade(tau, t);
    return t;
  }

  /* --------------------------------------------------------------- startup */
  function fitStage() {
    const stage = $("stage");
    if (RENDER) { stage.style.transform = "none"; return; }
    const pad = 46;
    const k = Math.min(window.innerWidth / W, (window.innerHeight - pad) / H);
    stage.style.transform = "translateY(" + (-pad / 2) + "px) scale(" + k.toFixed(5) + ")";
  }
  function workbenchReady() {
    return new Promise((resolve, reject) => {
      const started = performance.now();
      (function poll() {
        try {
          const d = frameEl.contentDocument, play = d && d.getElementById("play");
          if (play && !play.disabled && d.querySelectorAll("#evidence-list button").length) {
            doc = d; win = frameEl.contentWindow;
            const style = d.createElement("style");
            // Footage hygiene only: no scrollbars, no focus rings. The page is otherwise untouched.
            style.textContent = "html,.evidence-list,.event-feed{scrollbar-width:none}*::-webkit-scrollbar{display:none}";
            d.head.appendChild(style);
            d.getElementById("scrub").step = "any";
            return resolve();
          }
        } catch (error) { return reject(error); }
        if (performance.now() - started > 30000) return reject(new Error("the workbench page never loaded its session"));
        setTimeout(poll, 60);
      })();
    });
  }

  /* The product's own sound. Renders CIRCLE's adaptive audio engine — the synth.js and
   * audio-engine.js loaded by the workbench page — against the recorded feedback
   * schedule, following the same session playhead the picture shows. Master timeline. */
  const audioSession = (t) => (t < 34.55 ? key(SESSION, t, ease.linear)[0] : dataTime(t));
  window.__engineLayer = async function (sampleRate) {
    const cw = frameEl.contentWindow, engine = cw.CircleAudioEngine;
    const from = 23.0, to = 42.0, rate = 60;
    const schedule = engine.buildSchedule(events, { maxGain: TL.feedback.config.max_gain,
      breathPeriodMinS: TL.feedback.config.breath_period_bounds_s[0], breathPeriodMaxS: TL.feedback.config.breath_period_bounds_s[1] });
    const ctx = new cw.OfflineAudioContext(2, Math.ceil((to - from) * sampleRate), sampleRate);
    const synth = new cw.CircleSynth.AdaptiveSynth(engine);
    synth.ctx = ctx; synth._build(); synth.ceiling = TL.feedback.config.max_gain;
    for (let i = 0; i <= (to - from) * rate; i++) {
      const t = from + i / rate, s = audioSession(t);
      synth.enabled = t >= AUDIO_ON_T;
      synth.update(engine.interpolateAt(schedule, s), s, i / rate);
    }
    const buffer = await ctx.startRendering();
    const left = buffer.getChannelData(0), right = buffer.getChannelData(1);
    const pcm = new Int16Array(left.length * 2);
    let peak = 0;
    for (let i = 0; i < left.length; i++) {
      peak = Math.max(peak, Math.abs(left[i]), Math.abs(right[i]));
      pcm[2 * i] = Math.max(-1, Math.min(1, left[i])) * 32767;
      pcm[2 * i + 1] = Math.max(-1, Math.min(1, right[i])) * 32767;
    }
    const bytes = new Uint8Array(pcm.buffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return { from, to, sampleRate, peak, base64: btoa(binary) };
  };

  window.__film = { duration: DURATION, cut: CUT, fps: 30, edl: EDL };
  window.__ready = Promise.all([workbenchReady(), document.fonts.ready]).then(() => {
    fitStage(); measureTitle(); render(0);
    return window.__film;
  });
  window.__seek = function (tau) { return render(tau); };

  if (!RENDER) {
    const transport = $("transport"), scrub = $("tp-scrub"), clock = $("tp-clock"), playBtn = $("tp-play"), snd = $("snd");
    transport.hidden = false;
    scrub.max = String(DURATION);
    let playing = false, t0 = 0, base = 0, tau = Number(params.get("t")) || 0;
    snd.src = "out/circle-film-" + CUT + "s.m4a";
    let hasSound = false;
    snd.addEventListener("canplay", () => { hasSound = true; });
    function show() { render(tau); scrub.value = String(tau); clock.textContent = tau.toFixed(1) + " / " + DURATION.toFixed(1) + (hasSound ? "" : " · silent preview"); }
    function loop(now) {
      if (!playing) return;
      tau = hasSound ? snd.currentTime : base + (now - t0) / 1000;
      if (tau >= DURATION) { tau = DURATION; playing = false; playBtn.textContent = "Play"; snd.pause(); }
      show();
      if (playing) requestAnimationFrame(loop);
    }
    playBtn.addEventListener("click", () => {
      playing = !playing; playBtn.textContent = playing ? "Pause" : "Play";
      if (playing) {
        if (tau >= DURATION) tau = 0;
        base = tau; t0 = performance.now();
        if (hasSound) { snd.currentTime = tau; snd.play().catch(() => { hasSound = false; }); }
        requestAnimationFrame(loop);
      } else snd.pause();
    });
    scrub.addEventListener("input", () => { tau = Number(scrub.value); base = tau; t0 = performance.now(); if (hasSound) snd.currentTime = tau; show(); });
    window.addEventListener("resize", () => { fitStage(); measureTitle(); show(); });
    window.__ready.then(show);
  }
})();
