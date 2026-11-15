/* CIRCLE phantom evidence view — renders the /api/phantom document.
 * The headline is provenance: SIMULATED_BOARD rehearses the evidence path;
 * HARDWARE records a physical board through the same bridge.
 */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const node = (tag, text, cls) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (cls) el.className = cls; return el; };

  function chip(text, cls) { return node("span", text, "chip" + (cls ? " " + cls : "")); }

  function render(document_) {
    $("phantom-chips").replaceChildren(
      chip(document_.provenance === "HARDWARE" ? "physical board" : "simulated board",
           document_.provenance === "HARDWARE" ? "good" : "warn"),
      chip("verdict: " + (document_.phantom.verdict || "—"),
           document_.phantom.verdict === "PASS" ? "good" : "bad"),
      chip(document_.bridge_version || "")
    );
    $("phantom-note").textContent = document_.provenance_note + " " + document_.interpretation;
    $("phantom-checks").replaceChildren(...(document_.phantom.checks || []).map((check) => {
      const row = node("tr");
      row.append(node("td", check.id), node("td", check.status, check.status === "PASS" ? "good" : "bad"),
                 node("td", check.criterion || "—"));
      return row;
    }));
    $("phantom-clock").replaceChildren(...(document_.clock || []).map((entry) => {
      const row = node("tr");
      row.append(node("td", String(entry.segment)),
                 node("td", entry.rate_hz != null ? entry.rate_hz.toFixed(4) + " Hz" : "—"),
                 node("td", entry.ppm != null ? (entry.ppm > 0 ? "+" : "") + entry.ppm.toFixed(0) + " ppm" : "—"));
      return row;
    }));
    $("phantom-channels").replaceChildren(...(document_.channels || []).map((entry) => {
      const row = node("tr");
      row.append(node("td", String(entry.channel)),
                 node("td", entry.status || "—", entry.status === "OK" ? "good" : "warn"),
                 node("td", entry.detail || "—"));
      return row;
    }));
    $("phantom-body").hidden = false;
  }

  async function boot() {
    try {
      const response = await fetch("/api/phantom", { signal: AbortSignal.timeout(15000) });
      if (response.status === 404) { $("phantom-missing").hidden = false; return; }
      if (!response.ok) throw new Error("phantom request failed");
      render(await response.json());
    } catch (exc) {
      $("phantom-missing").hidden = false;
      $("phantom-missing").querySelector("p").textContent =
        "The phantom view needs the workbench server. " + exc.message;
    }
  }
  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", boot); }
  else { boot(); }
})();
