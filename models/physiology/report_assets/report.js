(() => {
  "use strict";
  const DATA = JSON.parse(document.getElementById("session-data").textContent);
  const S = DATA.series;
  const P = DATA.points;
  const DURATION = DATA.duration;
  const MIN_SPAN = 1.5;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const trace = document.getElementById("trace");
  const tctx = trace.getContext("2d");
  const overview = document.getElementById("overview");
  const octx = overview.getContext("2d");
  const micro = document.getElementById("micro");
  const caption = document.getElementById("chapter-caption");

  const FONT_LABEL = "600 11px 'Saira Semi Condensed', 'Arial Narrow', sans-serif";
  const FONT_VALUE = "600 11px 'JetBrains Mono', ui-monospace, monospace";
  const FONT_TICK = "10px 'JetBrains Mono', ui-monospace, monospace";
  const AXIS_H = 26;
  const PAD_L = 10;
  const PAD_R = 54;
  const STRIP_GAP = 5;

  let view = [0, DURATION];
  let cursor = null;
  let drag = null;
  let animation = null;
  let C = {};
  let cssWidth = 0;
  let cssHeight = 0;

  function readColors() {
    const style = getComputedStyle(document.documentElement);
    for (const name of ["page", "surface", "ink", "ink-2", "muted", "grid", "rule", "band", "cardiac", "resp", "spo2",
      "eda", "motion", "ctrl", "cue", "truth", "ghost", "motion-wash", "loop-wash", "gap-wash"]) {
      C[name] = style.getPropertyValue("--" + name).trim();
    }
  }

  // ------------------------------------------------------------ data access
  function valueAt(segs, t) {
    if (!segs) return null;
    for (const s of segs) {
      const i = (t - s.t0) / s.dt;
      if (i >= 0 && i <= s.v.length - 1) {
        const i0 = Math.floor(i);
        const i1 = Math.min(i0 + 1, s.v.length - 1);
        return s.v[i0] + (s.v[i1] - s.v[i0]) * (i - i0);
      }
    }
    return null;
  }

  function visible(segs, t0, t1, out) {
    if (!segs) return out;
    for (const s of segs) {
      const i0 = Math.max(0, Math.floor((t0 - s.t0) / s.dt));
      const i1 = Math.min(s.v.length - 1, Math.ceil((t1 - s.t0) / s.dt));
      for (let i = i0; i <= i1; i++) out.push(s.v[i]);
    }
    return out;
  }

  function extent(values, pad, minSpan) {
    let lo = Infinity;
    let hi = -Infinity;
    for (const v of values) {
      if (v === null || !isFinite(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    if (!isFinite(lo)) return [0, 1];
    let span = hi - lo;
    if (span < minSpan) {
      const mid = (hi + lo) / 2;
      lo = mid - minSpan / 2;
      hi = mid + minSpan / 2;
      span = minSpan;
    }
    return [lo - span * pad, hi + span * pad];
  }

  function quantileExtent(values, q, pad) {
    const sorted = values.filter((v) => v !== null && isFinite(v)).sort((a, b) => a - b);
    if (!sorted.length) return [-1, 1];
    const lo = sorted[Math.floor((sorted.length - 1) * q)];
    const hi = sorted[Math.ceil((sorted.length - 1) * (1 - q))];
    const span = Math.max(hi - lo, 1e-6);
    return [lo - span * pad, hi + span * pad];
  }

  function nearest(sortedTimes, t) {
    let lo = 0;
    let hi = sortedTimes.length - 1;
    if (hi < 0) return -1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (sortedTimes[mid] < t) lo = mid; else hi = mid;
    }
    return Math.abs(sortedTimes[lo] - t) <= Math.abs(sortedTimes[hi] - t) ? lo : hi;
  }

  // ---------------------------------------------------------------- drawing
  function niceStep(span, target) {
    const raw = span / Math.max(1, target);
    const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 20, 30, 60, 120];
    for (const s of steps) if (s >= raw) return s;
    return 120;
  }

  function lineSegs(ctx, segs, X, Y, color, width, alpha) {
    if (!segs) return;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    if (alpha !== undefined) ctx.globalAlpha = alpha;
    for (const s of segs) {
      const i0 = Math.max(0, Math.floor((view[0] - s.t0) / s.dt) - 1);
      const i1 = Math.min(s.v.length - 1, Math.ceil((view[1] - s.t0) / s.dt) + 1);
      if (i1 <= i0) continue;
      const pixels = Math.abs(X(s.t0 + i1 * s.dt) - X(s.t0 + i0 * s.dt));
      ctx.beginPath();
      if (i1 - i0 > pixels * 2) {
        let col = null;
        let mn = 0;
        let mx = 0;
        for (let i = i0; i <= i1; i++) {
          const x = Math.round(X(s.t0 + i * s.dt));
          const v = s.v[i];
          if (x !== col) {
            if (col === null) ctx.moveTo(x, Y(v));
            else { ctx.lineTo(col, Y(mn)); ctx.lineTo(col, Y(mx)); }
            col = x; mn = v; mx = v;
          } else {
            if (v < mn) mn = v;
            if (v > mx) mx = v;
          }
        }
        if (col !== null) { ctx.lineTo(col, Y(mn)); ctx.lineTo(col, Y(mx)); }
      } else {
        for (let i = i0; i <= i1; i++) {
          const x = X(s.t0 + i * s.dt);
          const y = Y(s.v[i]);
          if (i === i0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
    }
    ctx.restore();
  }

  function yTicks(ctx, box, Y, lo, hi, format) {
    const span = hi - lo;
    const raw = span / 3;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || raw;
    ctx.font = FONT_TICK;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) {
      const y = Math.round(Y(v)) + 0.5;
      if (y < box.y0 + 12 || y > box.y1 - 4) continue;
      ctx.strokeStyle = C.grid;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(box.x0, y);
      ctx.lineTo(box.x1, y);
      ctx.stroke();
      ctx.fillStyle = C.muted;
      ctx.fillText(format(v), box.x1 + 6, y);
    }
  }

  function wash(ctx, box, X, intervals, color) {
    ctx.fillStyle = color;
    for (const [a, b] of intervals) {
      if (b < view[0] || a > view[1]) continue;
      const x0 = Math.max(box.x0, X(a));
      const x1 = Math.min(box.x1, X(b));
      ctx.fillRect(x0, box.y0, Math.max(1, x1 - x0), box.y1 - box.y0);
    }
  }

  function label(ctx, box, title, value, color) {
    ctx.font = FONT_LABEL;
    const titleText = title.toUpperCase();
    const tw = ctx.measureText(titleText).width + 1.2 * titleText.length;
    ctx.font = FONT_VALUE;
    const vw = value ? ctx.measureText(value).width : 0;
    const w = 14 + tw + (value ? 10 + vw : 0);
    ctx.fillStyle = C.surface;
    ctx.globalAlpha = 0.9;
    ctx.fillRect(box.x0 + 2, box.y0 + 2, w, 16);
    ctx.globalAlpha = 1;
    ctx.fillStyle = color;
    ctx.fillRect(box.x0 + 6, box.y0 + 7, 6, 6);
    ctx.font = FONT_LABEL;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillStyle = C["ink-2"];
    if ("letterSpacing" in ctx) ctx.letterSpacing = "1.2px";
    ctx.fillText(titleText, box.x0 + 16, box.y0 + 10.5);
    if ("letterSpacing" in ctx) ctx.letterSpacing = "0px";
    if (value) {
      ctx.font = FONT_VALUE;
      ctx.fillStyle = C.ink;
      ctx.fillText(value, box.x0 + 16 + tw + 8, box.y0 + 10.5);
    }
  }

  function dot(ctx, x, y, r, fill, hollow) {
    ctx.beginPath();
    ctx.arc(x, y, r + 1.5, 0, Math.PI * 2);
    ctx.fillStyle = C.surface;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    if (hollow) { ctx.strokeStyle = fill; ctx.lineWidth = 1.4; ctx.stroke(); }
    else { ctx.fillStyle = fill; ctx.fill(); }
  }

  const f1 = (v) => v.toFixed(1);
  const f0 = (v) => v.toFixed(0);
  const f2 = (v) => v.toFixed(2);
  const fmt = (v, fn, unit) => (v === null || !isFinite(v) ? "—" : fn(v) + (unit || ""));

  // ----------------------------------------------------------------- strips
  const STRIPS = [
    { id: "events", title: "Protocol", weight: 44, color: () => C.ink, draw: drawEvents },
    { id: "ppg", title: "PPG · IR pulse", weight: 92, color: () => C.cardiac, draw: drawPPG },
    { id: "hr", title: "Heart rate", weight: 86, color: () => C.cardiac, draw: drawHR },
    { id: "riiv", title: "Breathing · optical", weight: 56, color: () => C.resp, draw: drawRIIV },
    { id: "rr", title: "Breathing rate", weight: 66, color: () => C.resp, draw: drawRR },
    { id: "spo2", title: "SpO₂", weight: 72, color: () => C.spo2, draw: drawSpO2 },
    { id: "eda", title: "Skin conductance", weight: 92, color: () => C.eda, draw: drawEDA },
    { id: "motion", title: "Motion · IMU", weight: 50, color: () => C.motion, draw: drawMotion },
    { id: "index", title: "Controller arousal index", weight: 70, color: () => C.ctrl, draw: drawIndex },
    { id: "arousal", title: "Twin latent arousal · truth", weight: 62, color: () => C.ctrl, draw: drawArousal },
  ];

  function drawEvents(ctx, box, X) {
    const mid = (box.y0 + box.y1) / 2 + 6;
    ctx.font = FONT_LABEL;
    ctx.textBaseline = "middle";
    DATA.phases.forEach(([name, a, b], i) => {
      if (b < view[0] || a > view[1]) return;
      const x0 = Math.max(box.x0, X(a));
      const x1 = Math.min(box.x1, X(b));
      ctx.fillStyle = i % 2 ? C.band : C.surface;
      ctx.fillRect(x0, box.y0 + 20, x1 - x0, box.y1 - box.y0 - 20);
      ctx.fillStyle = C["ink-2"];
      const text = name.replace("_", " ");
      const w = ctx.measureText(text).width;
      if (x1 - x0 > w + 10) {
        ctx.textAlign = "left";
        ctx.fillText(text, Math.max(x0, Math.min(x0 + 6, x1 - w - 4)), mid + 4);
      }
    });
    ctx.strokeStyle = C["ink-2"];
    ctx.fillStyle = C["ink-2"];
    for (const t of DATA.stimuli) {
      if (t < view[0] || t > view[1]) continue;
      const x = X(t);
      ctx.beginPath();
      ctx.moveTo(x - 3.5, box.y0 + 20);
      ctx.lineTo(x + 3.5, box.y0 + 20);
      ctx.lineTo(x, box.y0 + 26);
      ctx.closePath();
      ctx.fill();
    }
    ctx.strokeStyle = C.cue;
    ctx.lineWidth = 2;
    for (const c of DATA.cues.concat(DATA.sham_cues.map((t) => ({ t })))) {
      if (c.t < view[0] || c.t > view[1]) continue;
      const x = Math.round(X(c.t)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, box.y1 - 12);
      ctx.lineTo(x, box.y1);
      ctx.stroke();
    }
    ctx.font = FONT_VALUE;
    for (const d of DATA.decisions) {
      if (d.t < view[0] || d.t > view[1]) continue;
      const x = X(d.t);
      ctx.fillStyle = C.ctrl;
      ctx.fillRect(x - 1, box.y0 + 3, 2, 15);
      const stopping = d.action.startsWith("STOP");
      ctx.textAlign = stopping ? "right" : "left";
      ctx.fillStyle = C.ctrl;
      ctx.fillText(stopping ? "release" : d.id + " start", x + (stopping ? -4 : 4), box.y0 + 10.5);
    }
    let text = "";
    if (cursor !== null) {
      const phase = DATA.phases.find(([, a, b]) => cursor >= a && cursor < b);
      text = (phase ? phase[0].replace("_", " ").toLowerCase() : "") + "  t = " + cursor.toFixed(cursor < 100 ? 2 : 1) + " s";
    }
    label(ctx, box, "Protocol", text, C.ink);
  }

  function drawPPG(ctx, box, X, Yf) {
    const vals = visible(S.ppg, view[0], view[1], []);
    const [lo, hi] = quantileExtent(vals, 0.005, 0.18);
    const Y = Yf(lo, hi);
    wash(ctx, box, X, DATA.gaps.map((g) => [g.a, g.b]), C["gap-wash"]);
    lineSegs(ctx, S.ppg, X, Y, C.cardiac, 1.4);
    const span = view[1] - view[0];
    let readout = "";
    if (span < 50) {
      ctx.strokeStyle = C.muted;
      ctx.lineWidth = 1;
      for (const t of DATA.systolic) {
        if (t < view[0] || t > view[1]) continue;
        const x = Math.round(X(t)) + 0.5;
        ctx.beginPath();
        ctx.moveTo(x, box.y1 - 7);
        ctx.lineTo(x, box.y1);
        ctx.stroke();
      }
      DATA.beats.t.forEach((t, i) => {
        if (t < view[0] || t > view[1]) return;
        const v = valueAt(S.ppg, t);
        if (v === null) return;
        const q = DATA.beats.q[i];
        dot(ctx, X(t), Math.max(box.y0 + 4, Math.min(box.y1 - 4, Y(v))), 2.6, C.cardiac, q !== "G");
      });
    }
    for (const g of DATA.gaps) {
      if (g.b < view[0] || g.a > view[1] || span > 30) continue;
      ctx.font = FONT_VALUE;
      ctx.fillStyle = C.ink;
      ctx.textAlign = "center";
      ctx.fillText(`${g.last - g.first + 1} samples lost · #${g.first}–#${g.last}`, X((g.a + g.b) / 2), box.y1 - 16);
    }
    if (cursor !== null) {
      const i = nearest(DATA.beats.t, cursor);
      if (i >= 0 && Math.abs(DATA.beats.t[i] - cursor) < 0.35) {
        const names = { G: "good", M: "motion", E: "segment edge", L: "low template match" };
        readout = `beat ${DATA.beats.t[i].toFixed(3)} s · ${names[DATA.beats.q[i]]}`;
      }
    }
    label(ctx, box, "PPG · IR pulse", readout || (span < 50 ? "● detected  | truth" : ""), C.cardiac);
  }

  function drawHR(ctx, box, X, Yf) {
    const vals = visible(S.hr_est, view[0], view[1], visible(S.hr_truth, view[0], view[1], visible(S.hr_cf, view[0], view[1], [])));
    const [lo, hi] = extent(vals, 0.12, 8);
    const Y = Yf(lo, hi);
    yTicks(ctx, box, Y, lo, hi, f0);
    lineSegs(ctx, S.hr_truth, X, Y, C.truth, 6);
    lineSegs(ctx, S.hr_cf, X, Y, C.ghost, 1.3);
    lineSegs(ctx, S.hr_est, X, Y, C.cardiac, 1.8);
    let readout = "";
    if (cursor !== null) {
      readout = `${fmt(valueAt(S.hr_est, cursor), f1, " bpm")}  truth ${fmt(valueAt(S.hr_truth, cursor), f1)}`;
      if (S.hr_cf) readout += `  sham ${fmt(valueAt(S.hr_cf, cursor), f1)}`;
    }
    label(ctx, box, "Heart rate", readout, C.cardiac);
  }

  function drawRIIV(ctx, box, X, Yf) {
    const [lo, hi] = extent(visible(S.riiv, view[0], view[1], []), 0.1, 2);
    const Y = Yf(lo, hi);
    wash(ctx, box, X, DATA.apnea_truth, C.band);
    lineSegs(ctx, S.riiv, X, Y, C.resp, 1.5);
    ctx.fillStyle = C.resp;
    for (const t of P.breaths) {
      if (t < view[0] || t > view[1]) continue;
      const v = valueAt(S.riiv, t);
      if (v !== null) dot(ctx, X(t), Y(v), 2.2, C.resp, false);
    }
    for (const [a, b] of DATA.apnea_detected) {
      if (b < view[0] || a > view[1]) continue;
      const x0 = Math.max(box.x0, X(a));
      const x1 = Math.min(box.x1, X(b));
      ctx.strokeStyle = C.ink;
      ctx.lineWidth = 1;
      const y = box.y1 - 6.5;
      ctx.beginPath();
      ctx.moveTo(x0, y - 4); ctx.lineTo(x0, y); ctx.lineTo(x1, y); ctx.lineTo(x1, y - 4);
      ctx.stroke();
      ctx.font = FONT_VALUE;
      ctx.fillStyle = C.ink;
      ctx.textAlign = "center";
      if (x1 - x0 > 90) ctx.fillText("apnea detected", (x0 + x1) / 2, y - 8);
    }
    label(ctx, box, "Breathing · optical", cursor !== null ? `${fmt(valueAt(S.riiv, cursor), f2, " ‰ of DC")}` : "", C.resp);
  }

  function drawRR(ctx, box, X, Yf) {
    const pts = P.rr_est.filter((p) => p[0] >= view[0] - 10 && p[0] <= view[1] + 10);
    const vals = pts.map((p) => p[1]);
    visible(S.rr_truth, view[0], view[1], vals);
    visible(S.rr_cf, view[0], view[1], vals);
    const [lo, hi] = extent(vals.filter((v) => v > 1), 0.12, 6);
    const Y = Yf(Math.max(0, lo), hi);
    yTicks(ctx, box, Y, Math.max(0, lo), hi, f0);
    lineSegs(ctx, S.rr_truth, X, Y, C.truth, 6);
    lineSegs(ctx, S.rr_cf, X, Y, C.ghost, 1.3);
    ctx.strokeStyle = C.resp;
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.55;
    ctx.beginPath();
    pts.forEach((p, i) => (i ? ctx.lineTo(X(p[0]), Y(p[1])) : ctx.moveTo(X(p[0]), Y(p[1]))));
    ctx.stroke();
    ctx.globalAlpha = 1;
    for (const p of pts) dot(ctx, X(p[0]), Y(p[1]), 2.4, C.resp, false);
    let readout = "";
    if (cursor !== null) {
      const i = nearest(P.rr_est.map((p) => p[0]), cursor);
      const est = i >= 0 && Math.abs(P.rr_est[i][0] - cursor) < 8 ? P.rr_est[i][1] : null;
      readout = `${fmt(est, f1, " /min")}  truth ${fmt(valueAt(S.rr_truth, cursor), f1)}`;
      if (S.rr_cf) readout += `  sham ${fmt(valueAt(S.rr_cf, cursor), f1)}`;
    }
    label(ctx, box, "Breathing rate", readout, C.resp);
  }

  function drawSpO2(ctx, box, X, Yf) {
    const vals = visible(S.spo2_naive, view[0], view[1], visible(S.spo2_truth, view[0], view[1], []));
    const [lo, hi] = extent(vals, 0.1, 4);
    const Y = Yf(lo, Math.min(101, hi));
    yTicks(ctx, box, Y, lo, Math.min(101, hi), f0);
    lineSegs(ctx, S.spo2_truth, X, Y, C.truth, 6);
    lineSegs(ctx, S.spo2_naive, X, Y, C.spo2, 1, 0.38);
    lineSegs(ctx, S.spo2_gated, X, Y, C.spo2, 2);
    let readout = "";
    if (cursor !== null) {
      const gated = valueAt(S.spo2_gated, cursor);
      readout = `${gated === null ? "withheld" : f1(gated) + " %"}  naive ${fmt(valueAt(S.spo2_naive, cursor), f1)}  truth ${fmt(valueAt(S.spo2_truth, cursor), f1)}`;
    }
    label(ctx, box, "SpO₂", readout || "faint: naive · solid: IMU-gated", C.spo2);
  }

  function drawEDA(ctx, box, X, Yf) {
    const vals = visible(S.eda, view[0], view[1], visible(S.eda_truth, view[0], view[1], []));
    const [lo, hi] = extent(vals, 0.14, 0.3);
    const Y = Yf(lo, hi);
    yTicks(ctx, box, Y, lo, hi, (v) => v.toFixed(hi - lo < 1.5 ? 2 : 1));
    lineSegs(ctx, S.eda_truth, X, Y, C.truth, 6);
    lineSegs(ctx, S.eda_tonic, X, Y, C.eda, 1, 0.5);
    lineSegs(ctx, S.eda, X, Y, C.eda, 1.8);
    const span = view[1] - view[0];
    if (span < 160) {
      ctx.strokeStyle = C.muted;
      ctx.lineWidth = 1;
      for (const s of DATA.scr_truth) {
        if (s.o < view[0] || s.o > view[1] || s.a < 0.05) continue;
        const x = Math.round(X(s.o)) + 0.5;
        ctx.beginPath();
        ctx.moveTo(x, box.y1 - 7);
        ctx.lineTo(x, box.y1);
        ctx.stroke();
      }
      for (const s of DATA.scr) {
        if (s.o < view[0] || s.o > view[1]) continue;
        const x = X(s.o);
        const y = box.y1 - 12;
        ctx.beginPath();
        ctx.moveTo(x, y - 5); ctx.lineTo(x + 4, y + 2); ctx.lineTo(x - 4, y + 2); ctx.closePath();
        if (s.w) { ctx.strokeStyle = C.eda; ctx.lineWidth = 1.2; ctx.stroke(); }
        else { ctx.fillStyle = C.eda; ctx.fill(); }
        if (span < 40 && !s.w) {
          ctx.font = FONT_TICK;
          ctx.fillStyle = C["ink-2"];
          ctx.textAlign = "left";
          ctx.fillText(s.a.toFixed(2), x + 6, y - 2);
        }
      }
    }
    let readout = "";
    if (cursor !== null) {
      readout = `${fmt(valueAt(S.eda, cursor), f2, " µS")}  tonic ${fmt(valueAt(S.eda_tonic, cursor), f2)}  truth ${fmt(valueAt(S.eda_truth, cursor), f2)}`;
    }
    label(ctx, box, "Skin conductance", readout || (span < 160 ? "▲ SCR onset  △ withheld (motion)  | truth" : ""), C.eda);
  }

  function drawMotion(ctx, box, X, Yf) {
    const [, hi] = extent(visible(S.motion, view[0], view[1], []), 0.1, 0.05);
    const Y = Yf(0, Math.max(0.05, hi));
    lineSegs(ctx, S.motion, X, Y, C.motion, 1.6);
    label(ctx, box, "Motion · IMU", cursor !== null ? fmt(valueAt(S.motion, cursor), (v) => v.toFixed(3), " g rms") : "", C.motion);
  }

  function drawIndex(ctx, box, X, Yf) {
    const pts = P.index;
    const vals = pts.filter((p) => p[0] >= view[0] - 5 && p[0] <= view[1] + 5).map((p) => p[1]);
    vals.push(DATA.thresholds.trigger + 0.8, -0.8);
    const [lo, hi] = extent(vals, 0.08, 3);
    const Y = Yf(lo, hi);
    for (const [v, name, shift] of [[DATA.thresholds.trigger, "trigger", -6], [DATA.thresholds.release, "release", 6]]) {
      const y = Math.round(Y(v)) + 0.5;
      ctx.strokeStyle = C.rule;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(box.x0, y); ctx.lineTo(box.x1, y); ctx.stroke();
      ctx.font = FONT_TICK;
      ctx.fillStyle = C.muted;
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(name, box.x1 + 4, y + shift);
    }
    ctx.lineWidth = 1.8;
    for (let i = 1; i < pts.length; i++) {
      const [t0, v0, , armed0] = pts[i - 1];
      const [t1, v1] = pts[i];
      if (t1 < view[0] - 5 || t0 > view[1] + 5) continue;
      ctx.strokeStyle = armed0 ? C.ctrl : C.ghost;
      ctx.beginPath();
      ctx.moveTo(X(t0), Y(v0));
      ctx.lineTo(X(t1), Y(v0));
      ctx.lineTo(X(t1), Y(v1));
      ctx.stroke();
    }
    for (const [t, v, q, armed] of pts) {
      if (t < view[0] || t > view[1]) continue;
      dot(ctx, X(t), Y(v), 2.4, armed ? C.ctrl : C.ghost, !q);
    }
    let readout = "";
    if (cursor !== null) {
      const prior = pts.filter((p) => p[0] <= cursor);
      if (prior.length) {
        const p = prior[prior.length - 1];
        readout = `${p[1].toFixed(2)}  ${p[3] ? "armed" : "not armed"}${p[2] ? "" : " · quality hold"}`;
      }
    }
    label(ctx, box, "Controller arousal index", readout || "grey: not armed  hollow: quality hold", C.ctrl);
  }

  function drawArousal(ctx, box, X, Yf) {
    const vals = visible(S.arousal_truth, view[0], view[1], visible(S.arousal_cf, view[0], view[1], [0]));
    const [lo, hi] = extent(vals, 0.1, 0.4);
    const Y = Yf(Math.max(-0.05, lo), hi);
    yTicks(ctx, box, Y, Math.max(-0.05, lo), hi, (v) => v.toFixed(1));
    lineSegs(ctx, S.arousal_cf, X, Y, C.ghost, 1.3);
    lineSegs(ctx, S.arousal_truth, X, Y, C.ctrl, 1.8);
    let readout = "";
    if (cursor !== null) {
      readout = fmt(valueAt(S.arousal_truth, cursor), f2);
      if (S.arousal_cf) readout += `  sham ${fmt(valueAt(S.arousal_cf, cursor), f2)}`;
    }
    label(ctx, box, "Twin latent arousal · truth", readout, C.ctrl);
  }

  // ----------------------------------------------------------------- layout
  function layout() {
    const total = STRIPS.reduce((a, s) => a + s.weight, 0);
    const usable = cssHeight - AXIS_H - STRIP_GAP * (STRIPS.length - 1) - 4;
    let y = 4;
    return STRIPS.map((s) => {
      const h = (s.weight / total) * usable;
      const box = { x0: PAD_L, x1: cssWidth - PAD_R, y0: y, y1: y + h };
      y += h + STRIP_GAP;
      return { strip: s, box };
    });
  }

  function X(t) {
    return PAD_L + ((t - view[0]) / (view[1] - view[0])) * (cssWidth - PAD_L - PAD_R);
  }

  function T(x) {
    return view[0] + ((x - PAD_L) / (cssWidth - PAD_L - PAD_R)) * (view[1] - view[0]);
  }

  function draw() {
    if (!cssWidth) return;
    const ctx = tctx;
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssWidth, cssHeight);
    ctx.fillStyle = C.surface;
    ctx.fillRect(0, 0, cssWidth, cssHeight);
    const boxes = layout();
    const plotTop = boxes[0].box.y0;
    const plotBottom = boxes[boxes.length - 1].box.y1;
    const step = niceStep(view[1] - view[0], (cssWidth - PAD_L - PAD_R) / 95);
    ctx.strokeStyle = C.grid;
    ctx.lineWidth = 1;
    for (let t = Math.ceil(view[0] / step) * step; t <= view[1]; t += step) {
      const x = Math.round(X(t)) + 0.5;
      ctx.beginPath(); ctx.moveTo(x, plotTop); ctx.lineTo(x, plotBottom); ctx.stroke();
    }
    for (const { strip, box } of boxes) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(box.x0, box.y0, cssWidth - box.x0, box.y1 - box.y0);
      ctx.clip();
      if (strip.id !== "events") {
        wash(ctx, box, X, DATA.program_spans, C["loop-wash"]);
        wash(ctx, box, X, DATA.motion_detected, C["motion-wash"]);
      }
      const Yf = (lo, hi) => (v) => box.y1 - 3 - ((v - lo) / (hi - lo || 1)) * (box.y1 - box.y0 - 22);
      strip.draw(ctx, box, X, Yf);
      ctx.restore();
      ctx.strokeStyle = C.rule;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(box.x0, Math.round(box.y1) + 0.5);
      ctx.lineTo(box.x1, Math.round(box.y1) + 0.5);
      ctx.stroke();
    }
    ctx.font = FONT_TICK;
    ctx.fillStyle = C.muted;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (let t = Math.ceil(view[0] / step) * step; t <= view[1]; t += step) {
      ctx.fillText(step < 1 ? t.toFixed(1) : t.toFixed(0), X(t), plotBottom + 7);
    }
    ctx.textAlign = "left";
    ctx.fillText("s", cssWidth - PAD_R + 6, plotBottom + 7);
    if (drag && drag.mode === "select") {
      const x0 = Math.min(drag.x0, drag.x1);
      const x1 = Math.max(drag.x0, drag.x1);
      ctx.fillStyle = C.ink;
      ctx.globalAlpha = 0.07;
      ctx.fillRect(x0, plotTop, x1 - x0, plotBottom - plotTop);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = C["ink-2"];
      ctx.strokeRect(Math.round(x0) + 0.5, plotTop + 0.5, Math.round(x1 - x0), plotBottom - plotTop - 1);
    }
    if (cursor !== null && cursor >= view[0] && cursor <= view[1]) {
      const x = Math.round(X(cursor)) + 0.5;
      ctx.strokeStyle = C.ink;
      ctx.globalAlpha = 0.55;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, plotTop); ctx.lineTo(x, plotBottom); ctx.stroke();
      ctx.globalAlpha = 1;
    }
    drawOverview();
  }

  function drawOverview() {
    const w = overview.clientWidth;
    const h = overview.clientHeight;
    if (!w) return;
    const dpr = window.devicePixelRatio || 1;
    const ctx = octx;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = C.surface;
    ctx.fillRect(0, 0, w, h);
    const OX = (t) => 4 + (t / DURATION) * (w - 8);
    DATA.phases.forEach(([, a, b], i) => {
      ctx.fillStyle = i % 2 ? C.band : C.surface;
      ctx.fillRect(OX(a), 0, OX(b) - OX(a), h);
    });
    ctx.fillStyle = C["loop-wash"];
    for (const [a, b] of DATA.program_spans) ctx.fillRect(OX(a), 0, OX(b) - OX(a), h);
    const [lo, hi] = extent(visible(S.hr_est, 0, DURATION, []), 0.1, 5);
    ctx.strokeStyle = C.cardiac;
    ctx.lineWidth = 1.2;
    for (const s of S.hr_est) {
      ctx.beginPath();
      s.v.forEach((v, i) => {
        const x = OX(s.t0 + i * s.dt);
        const y = h - 5 - ((v - lo) / (hi - lo)) * (h - 10);
        if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      });
      ctx.stroke();
    }
    const x0 = OX(view[0]);
    const x1 = OX(view[1]);
    ctx.fillStyle = C.ink;
    ctx.globalAlpha = 0.1;
    ctx.fillRect(0, 0, x0, h);
    ctx.fillRect(x1, 0, w - x1, h);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = C.ink;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x0 + 0.75, 0.75, Math.max(2, x1 - x0 - 1.5), h - 1.5);
  }

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    cssWidth = trace.clientWidth;
    cssHeight = trace.clientHeight;
    trace.width = Math.round(cssWidth * dpr);
    trace.height = Math.round(cssHeight * dpr);
    overview.width = Math.round(overview.clientWidth * dpr);
    overview.height = Math.round(overview.clientHeight * dpr);
    micro.width = Math.round(micro.clientWidth * dpr);
    micro.height = Math.round(micro.clientHeight * dpr);
    draw();
    drawMicro();
  }

  // ------------------------------------------------------------ view control
  function clampView(v) {
    let [a, b] = v;
    let span = Math.max(MIN_SPAN, Math.min(DURATION, b - a));
    const mid = (a + b) / 2;
    a = mid - span / 2;
    b = mid + span / 2;
    if (a < 0) { b -= a; a = 0; }
    if (b > DURATION) { a -= b - DURATION; b = DURATION; }
    return [Math.max(0, a), Math.min(DURATION, b)];
  }

  function setView(target, animate) {
    target = clampView(target);
    if (animation) cancelAnimationFrame(animation);
    if (!animate || reduceMotion) { view = target; draw(); return; }
    const from = view.slice();
    const start = performance.now();
    const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
    const step = (now) => {
      const k = Math.min(1, (now - start) / 480);
      const e = ease(k);
      // Interpolate in log-span so zooms feel even.
      const spanFrom = from[1] - from[0];
      const spanTo = target[1] - target[0];
      const span = Math.exp(Math.log(spanFrom) + (Math.log(spanTo) - Math.log(spanFrom)) * e);
      const mid = (from[0] + from[1]) / 2 + (((target[0] + target[1]) / 2) - (from[0] + from[1]) / 2) * e;
      view = [mid - span / 2, mid + span / 2];
      draw();
      animation = k < 1 ? requestAnimationFrame(step) : null;
      if (!animation) { view = target; draw(); }
    };
    animation = requestAnimationFrame(step);
  }

  function zoom(factor, center) {
    const c = center === undefined ? (view[0] + view[1]) / 2 : center;
    const span = (view[1] - view[0]) * factor;
    const k = (c - view[0]) / (view[1] - view[0]);
    setView([c - span * k, c + span * (1 - k)], true);
  }

  // ---------------------------------------------------------------- events
  const chapterBar = document.getElementById("chapters");
  const buttons = [];
  function selectChapter(ch, animate) {
    for (const b of buttons) b.setAttribute("aria-pressed", String(b.dataset.id === ch.id));
    caption.textContent = ch.caption;
    setView([ch.t0, ch.t1], animate);
  }
  for (const ch of DATA.chapters) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = ch.label;
    b.dataset.id = ch.id;
    b.setAttribute("aria-pressed", "false");
    b.addEventListener("click", () => selectChapter(ch, true));
    chapterBar.appendChild(b);
    buttons.push(b);
  }
  function clearChapter() {
    for (const b of buttons) b.setAttribute("aria-pressed", "false");
  }

  function localX(e, el) {
    return e.clientX - el.getBoundingClientRect().left;
  }

  trace.addEventListener("pointerdown", (e) => {
    const x = localX(e, trace);
    drag = { mode: e.pointerType === "mouse" ? "select" : "pan", x0: x, x1: x, view0: view.slice(), moved: false };
    trace.setPointerCapture(e.pointerId);
  });
  trace.addEventListener("pointermove", (e) => {
    const x = localX(e, trace);
    cursor = Math.max(view[0], Math.min(view[1], T(x)));
    if (drag) {
      drag.x1 = x;
      if (Math.abs(drag.x1 - drag.x0) > 4) drag.moved = true;
      if (drag.mode === "pan" && drag.moved) {
        const dt = ((drag.x0 - x) / (cssWidth - PAD_L - PAD_R)) * (drag.view0[1] - drag.view0[0]);
        view = clampView([drag.view0[0] + dt, drag.view0[1] + dt]);
        clearChapter();
      }
    }
    draw();
  });
  trace.addEventListener("pointerup", () => {
    if (drag && drag.mode === "select" && Math.abs(drag.x1 - drag.x0) > 6) {
      const a = T(Math.min(drag.x0, drag.x1));
      const b = T(Math.max(drag.x0, drag.x1));
      drag = null;
      clearChapter();
      setView([a, b], true);
      return;
    }
    drag = null;
    draw();
  });
  trace.addEventListener("pointerleave", (e) => {
    if (e.pointerType === "mouse" && !drag) { cursor = null; draw(); }
  });
  trace.addEventListener("dblclick", () => selectChapter(DATA.chapters[0], true));
  trace.addEventListener("keydown", (e) => {
    const span = view[1] - view[0];
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      const d = (e.key === "ArrowLeft" ? -0.15 : 0.15) * span;
      clearChapter();
      setView([view[0] + d, view[1] + d], false);
      e.preventDefault();
    } else if (e.key === "+" || e.key === "=") { clearChapter(); zoom(0.6); e.preventDefault(); }
    else if (e.key === "-" || e.key === "_") { clearChapter(); zoom(1 / 0.6); e.preventDefault(); }
    else if (e.key === "0" || e.key === "Escape") { cursor = null; selectChapter(DATA.chapters[0], true); }
  });
  document.getElementById("zoom-in").addEventListener("click", () => { clearChapter(); zoom(0.6, cursor ?? undefined); });
  document.getElementById("zoom-out").addEventListener("click", () => { clearChapter(); zoom(1 / 0.6, cursor ?? undefined); });
  document.getElementById("zoom-reset").addEventListener("click", () => selectChapter(DATA.chapters[0], true));

  let ovDrag = null;
  function overviewTime(e) {
    const w = overview.clientWidth;
    return ((localX(e, overview) - 4) / (w - 8)) * DURATION;
  }
  overview.addEventListener("pointerdown", (e) => {
    overview.setPointerCapture(e.pointerId);
    const t = overviewTime(e);
    const span = view[1] - view[0];
    ovDrag = { offset: t >= view[0] && t <= view[1] ? t - view[0] : span / 2 };
    clearChapter();
    setView([t - ovDrag.offset, t - ovDrag.offset + span], false);
  });
  overview.addEventListener("pointermove", (e) => {
    if (!ovDrag) return;
    const t = overviewTime(e);
    const span = view[1] - view[0];
    setView([t - ovDrag.offset, t - ovDrag.offset + span], false);
  });
  overview.addEventListener("pointerup", () => { ovDrag = null; });

  for (const button of document.querySelectorAll("[data-copy]")) {
    button.addEventListener("click", () => {
      const code = document.getElementById(button.dataset.copy);
      const done = () => { button.textContent = "Copied"; setTimeout(() => { button.textContent = "Copy"; }, 1500); };
      const fallback = () => {
        const range = document.createRange();
        range.selectNodeContents(code);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        button.textContent = "Selected";
        setTimeout(() => { button.textContent = "Copy"; }, 1500);
      };
      try {
        navigator.clipboard.writeText(code.textContent).then(done, fallback);
      } catch (err) {
        fallback();
      }
    });
  }

  // ------------------------------------------------------------ micro chart
  function drawMicro() {
    const m = DATA.micro;
    const w = micro.clientWidth;
    const h = micro.clientHeight;
    if (!m || !w) return;
    const dpr = window.devicePixelRatio || 1;
    const ctx = micro.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = C.page;
    ctx.fillRect(0, 0, w, h);
    const x0 = 36;
    const x1 = w - 12;
    const top = 44;
    const bottom = h - 22;
    const t0 = -8;
    const t1 = 64;
    const MX = (t) => x0 + ((t - t0) / (t1 - t0)) * (x1 - x0);
    let amp = 0;
    m.raw.forEach((v, i) => { if (m.raw_t[i] >= t0 && m.raw_t[i] <= t1) amp = Math.max(amp, Math.abs(v)); });
    m.env.forEach((v) => { amp = Math.max(amp, v); });
    amp *= 1.1;
    const MY = (v) => (top + bottom) / 2 - (v / amp) * ((bottom - top) / 2);
    ctx.strokeStyle = C.grid;
    ctx.lineWidth = 1;
    ctx.font = FONT_TICK;
    ctx.fillStyle = C.muted;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (let t = 0; t <= t1; t += 10) {
      const x = Math.round(MX(t)) + 0.5;
      ctx.beginPath(); ctx.moveTo(x, top - 4); ctx.lineTo(x, bottom); ctx.stroke();
      ctx.fillText(t + (t === 60 ? " ms" : ""), x, bottom + 5);
    }
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (const v of [-0.1, 0, 0.1]) {
      if (Math.abs(v) > amp) continue;
      ctx.fillText(v === 0 ? "0 g" : v.toFixed(1), x0 - 6, MY(v));
    }
    ctx.save();
    ctx.beginPath();
    ctx.rect(x0, top - 6, x1 - x0, bottom - top + 6);
    ctx.clip();
    ctx.strokeStyle = C.muted;
    ctx.lineWidth = 1;
    ctx.beginPath();
    m.raw.forEach((v, i) => (i ? ctx.lineTo(MX(m.raw_t[i]), MY(v)) : ctx.moveTo(MX(m.raw_t[i]), MY(v))));
    ctx.stroke();
    m.raw.forEach((v, i) => { ctx.fillStyle = C.muted; ctx.fillRect(MX(m.raw_t[i]) - 1.5, MY(v) - 1.5, 3, 3); });
    ctx.strokeStyle = C.ctrl;
    ctx.lineWidth = 2;
    ctx.beginPath();
    m.env.forEach((v, i) => (i ? ctx.lineTo(MX(m.env_t[i]), MY(v)) : ctx.moveTo(MX(m.env_t[i]), MY(v))));
    ctx.stroke();
    ctx.restore();
    const markers = [
      { t: 0, text: "command", color: C.ink, row: 0 },
      { t: m.elec_ms, text: `current edge ${m.elec_ms?.toFixed(2)} ms`, color: C.cue, row: 1 },
      { t: m.phys_ms, text: `IMU onset ${m.phys_ms?.toFixed(2)} ms · truth ${m.truth_ms?.toFixed(2)}`, color: C.ctrl, row: 2 },
    ];
    if (m.truth_ms !== undefined) {
      ctx.strokeStyle = C.truth;
      ctx.lineWidth = 6;
      ctx.beginPath(); ctx.moveTo(MX(m.truth_ms), top - 2); ctx.lineTo(MX(m.truth_ms), bottom); ctx.stroke();
    }
    ctx.font = FONT_VALUE;
    ctx.textBaseline = "middle";
    ctx.textAlign = "left";
    for (const mk of markers) {
      if (mk.t === undefined || mk.t === null) continue;
      const x = Math.round(MX(mk.t)) + 0.5;
      const y = 10 + mk.row * 12;
      ctx.strokeStyle = mk.color;
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(x, y + 4); ctx.lineTo(x, bottom); ctx.stroke();
      ctx.fillStyle = C.ink;
      ctx.fillText(mk.text, x + 5, y);
    }
  }

  // ----------------------------------------------------------------- boot
  readColors();
  const ro = new ResizeObserver(() => resize());
  ro.observe(trace);
  ro.observe(micro);
  const refreshTheme = () => { readColors(); draw(); drawMicro(); };
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", refreshTheme);
  new MutationObserver(refreshTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { draw(); drawMicro(); });
  selectChapter(DATA.chapters[0], false);
  resize();
})();
