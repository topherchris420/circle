/* CIRCLE film — serves the recorded session to the unmodified Resonance Workbench.
 *
 * The film embeds the real workbench page and operates it through its own
 * controls. This shim only answers the page's API calls from ad-data.js (built
 * by tools/build_ad.py) and keeps the embedded page silent: the film carries
 * its own soundtrack, so the page's audio context is created but never resumed.
 * The engine's state — sounding, holding, muted, and why — stays real.
 */
(function () {
  "use strict";
  var data = window.CIRCLE_AD.workbench;
  function json(value, status) {
    return new Response(JSON.stringify(value), { status: status || 200, headers: { "content-type": "application/json" } });
  }
  window.fetch = function (url, options) {
    var path = String(url).split("?")[0];
    function ends(p) { return path === p || path.slice(-p.length) === p; }
    if (options && options.method === "POST") {
      if (ends("/api/runs")) { return Promise.resolve(json(data.runs[0])); }
      if (/\/consent$/.test(path)) { return Promise.resolve(json({ state: "EXECUTED" })); }
      if (/\/revoke$/.test(path)) { return Promise.resolve(json({ state: "REVOKED" })); }
      if (/\/cancel$/.test(path)) { return Promise.resolve(json(data.runs[0])); }
    }
    if (ends("/api/config")) { return Promise.resolve(json(data.config)); }
    if (ends("/api/runs")) { return Promise.resolve(json(data.runs)); }
    if (/\/timeline$/.test(path)) { return Promise.resolve(json(data.timeline)); }
    if (/\/api\/runs\/[0-9a-f]{32}$/.test(path)) { return Promise.resolve(json(data.runs[0])); }
    if (ends("/api/phantom")) { return Promise.resolve(json({ error: "No phantom session is attached." }, 404)); }
    return Promise.reject(new Error("film: unexpected request " + path));
  };

  var Real = window.AudioContext || window.webkitAudioContext;
  if (Real) {
    var Silent = function (options) {
      var ctx = new Real(options);
      ctx.suspend().catch(function () {});
      ctx.resume = function () { return Promise.resolve(); };
      return ctx;
    };
    Silent.prototype = Real.prototype;
    window.AudioContext = Silent;
    window.webkitAudioContext = undefined;
  }
})();
