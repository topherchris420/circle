/* CIRCLE offline demo shim: serves the recorded session to the workbench UI.
 * No network: every fetch the interface makes resolves from this page's data.
 */
(function () {
  "use strict";
  const data = window.CIRCLE_DEMO;
  const json = (value) => new Response(JSON.stringify(value), {"content-type": "application/json"});
  window.fetch = function (url, options) {
    const path = String(url);
    const suffix = (p) => path === p || path.endsWith(p) || path.split("?")[0] === p;
    if (options && options.method === "POST") {
      if (suffix("/api/runs")) { return Promise.resolve(json(data.runs[0])); }
      if (/\/consent$/.test(path)) { return Promise.resolve(json({"state": "EXECUTED"})); }
      if (/\/revoke$/.test(path)) { return Promise.resolve(json({"state": "REVOKED"})); }
      if (/\/cancel$/.test(path)) { return Promise.resolve(json(data.runs[0])); }
    }
    if (suffix("/api/config")) { return Promise.resolve(json(data.config)); }
    if (suffix("/api/runs")) { return Promise.resolve(json(data.runs)); }
    if (/\/timeline$/.test(path)) { return Promise.resolve(json(data.timeline)); }
    if (/\/api\/runs\/[0-9a-f]{32}$/.test(path)) {
      return Promise.resolve(json(data.runs[0]));
    }
    if (suffix("/api/phantom")) {
      return Promise.resolve(new Response(JSON.stringify({"error": "offline demo"}), {"status": 404}));
    }
    return Promise.reject(new Error("offline demo: unexpected request " + path));
  };
  // Self-test (only with ?selftest in the URL, so visitors keep a real tab title):
  // report how many API calls the interface made and whether any script failed.
  if (!/[?&]selftest\b/.test(window.location.search)) { return; }
  let served = 0;
  let uncaught = 0;
  window.addEventListener("error", function () { uncaught += 1; });
  window.addEventListener("unhandledrejection", function () { uncaught += 1; });
  const counting = window.fetch;
  window.fetch = function (url, options) {
    return counting(url, options).then(function (response) { served += 1; return response; });
  };
  window.addEventListener("load", function () {
    setTimeout(function () {
      const state = !window.CIRCLE_DEMO ? "BROKEN" : (uncaught ? uncaught + " UNCAUGHT ERRORS" : "READY");
      document.title = "DEMO " + served + " API CALLS · " + state;
    }, 3500);
  });
})();
