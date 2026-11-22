/* CIRCLE demo guide: no instructions required.
 * Arrives on the dashboard with silent playback running (unless the visitor
 * prefers reduced motion), offers one click to hear the recorded adaptive
 * audio, and makes "inspect a decision" one click: it opens the Evidence view
 * on the first recorded decision.
 */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  function openView(name) {
    const tab = document.querySelector('.view-tab[data-view="' + name + '"]');
    if (tab) { tab.click(); }
  }
  function revealView(name) {
    const view = $("view-" + name);
    if (!view) { return; }
    const masthead = document.querySelector(".masthead");
    const sticky = masthead && getComputedStyle(masthead).position === "sticky" ? masthead.offsetHeight : 0;
    window.scrollTo({ top: Math.max(0, view.getBoundingClientRect().top + window.scrollY - sticky - 12), behavior: "smooth" });
  }
  ready(function () {
    // "Open the evidence": switch views and select the first recorded decision.
    document.querySelectorAll("[data-open-view]").forEach(function (link) {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        const name = link.dataset.openView;
        openView(name);
        if (name === "evidence") {
          const buttons = document.querySelectorAll("#evidence-list button");
          const decision = Array.prototype.find.call(buttons, function (b) {
            const kind = b.querySelector(".ev-kind");
            return kind && kind.textContent.indexOf("eval") !== 0;
          }) || buttons[0];
          if (decision) { decision.click(); }
        }
        revealView(name);
      });
    });

  });
})();
