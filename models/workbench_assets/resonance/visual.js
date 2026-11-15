/* CIRCLE visual feedback field — restrained, cymatic-inspired geometry.
 *
 * An algorithmic rendering of signal features: ring radii follow feedback
 * intensity and breathing phase; ring texture follows brightness; quality
 * failures still the field and drain its color. It is explicitly a
 * visualization of recorded evidence, not a measurement of an unseen
 * physical phenomenon. With reduced motion preferred, the field renders
 * per-event stills without continuous drift.
 */
(function (global) {
  "use strict";

  function VisualField(canvas) {
    this.canvas = canvas;
    this.ctx2d = canvas.getContext("2d");
    this.drift = 0;
    this.lastStill = -1;
  }

  VisualField.prototype.render = function (point, breathPhase, qualityOk, opts) {
    opts = opts || {};
    var reduced = !!opts.reducedMotion;
    var t = opts.wallTime || 0;
    if (reduced) {
      // One still per distinct event time: no continuous animation.
      var key = point ? point.time_s : -1;
      if (key === this.lastStill && !opts.force) { return; }
      this.lastStill = key;
    }
    var w = this.canvas.width, h = this.canvas.height;
    var g = this.ctx2d;
    g.clearRect(0, 0, w, h);

    // Bench backdrop: faint concentric reference circles.
    g.strokeStyle = "rgba(103, 198, 195, 0.07)";
    g.lineWidth = 1;
    for (var r0 = 40; r0 < Math.max(w, h) / 2; r0 += 40) {
      g.beginPath(); g.arc(w / 2, h / 2, r0, 0, Math.PI * 2); g.stroke();
    }

    if (!point) {
      this._label(g, w, h, "no session loaded");
      return;
    }
    if (!qualityOk) {
      // Degraded evidence: the field holds, desaturated, and says so.
      g.strokeStyle = "rgba(217, 164, 65, 0.55)";
      g.lineWidth = 2;
      g.setLineDash([4, 6]);
      g.beginPath(); g.arc(w / 2, h / 2, 150, 0, Math.PI * 2); g.stroke();
      g.setLineDash([]);
      this._label(g, w, h, "holding · " + (point.gate_reasons || []).join(", ").toLowerCase());
    }

    var intensity = point.audible ? point.intensity : point.intensity * 0.4;
    var swell = 0.5 + 0.5 * Math.sin(2 * Math.PI * breathPhase);
    if (!reduced) { this.drift += 0.004 + 0.01 * intensity; }

    var rings = 7;
    for (var i = 0; i < rings; i++) {
      var f = i / (rings - 1);
      var radius = 40 + (1 - f) * (60 + 190 * intensity) * (0.75 + 0.25 * swell);
      var segments = 90;
      var wob = (2 + 26 * intensity * point.brightness) * (1 - f * 0.4);
      var alpha = (qualityOk ? 0.5 : 0.2) * (1 - f * 0.6);
      var hue = qualityOk ? (174 - 30 * intensity) : 40;
      g.strokeStyle = "hsla(" + hue + ", 45%, " + (58 + 12 * point.brightness) + "%, " + alpha + ")";
      g.lineWidth = 1 + 2 * (1 - f) * point.brightness;
      g.beginPath();
      for (var s = 0; s <= segments; s++) {
        var a = (s / segments) * Math.PI * 2;
        var wobble = Math.sin(a * (3 + i) + this.drift * (1 + i * 0.35)) * wob
                   + Math.sin(a * (11 + i * 2) - this.drift * 1.7) * wob * 0.4;
        var rr = radius + wobble;
        var x = w / 2 + Math.cos(a) * rr;
        var y = h / 2 + Math.sin(a) * rr * 0.86; // slight vertical perspective
        if (s === 0) { g.moveTo(x, y); } else { g.lineTo(x, y); }
      }
      g.closePath();
      g.stroke();
    }

    // Core: breath phase disc.
    var coreR = 10 + 26 * swell * (point.audible ? 1 : 0.4);
    g.fillStyle = qualityOk ? "rgba(103, 198, 195, " + (0.25 + 0.45 * intensity) + ")" : "rgba(217, 164, 65, 0.3)";
    g.beginPath(); g.arc(w / 2, h / 2, coreR, 0, Math.PI * 2); g.fill();
    g.strokeStyle = "rgba(232, 238, 240, 0.35)";
    g.lineWidth = 1;
    g.beginPath(); g.arc(w / 2, h / 2, coreR, 0, Math.PI * 2); g.stroke();
  };

  VisualField.prototype._label = function (g, w, h, text) {
    g.fillStyle = "rgba(167, 180, 186, 0.8)";
    g.font = "12px ui-monospace, monospace";
    g.textAlign = "center";
    g.fillText(text, w / 2, h - 14);
  };

  global.CircleVisual = { VisualField: VisualField };
})(typeof window !== "undefined" ? window : globalThis);
