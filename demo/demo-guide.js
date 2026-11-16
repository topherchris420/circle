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

    // One-click hearing: the only deliberate gesture a visitor needs.
    const hear = document.createElement("button");
    hear.className = "primary";
    hear.type = "button";
    hear.textContent = "\u266B Hear this session";
    hear.style.marginRight = "10px";
    hear.addEventListener("click", function () {
      const enable = $("audio-enable");
      if (enable && !enable.disabled) { enable.checked = true; enable.dispatchEvent(new Event("change")); }
      const play = $("play");
      if (play && play.textContent.indexOf("Play") !== -1) { play.click(); }
      hear.textContent = "\u266A Playing \u2014 mute any time";
    });
    const bar = document.querySelector(".playback");
    if (bar) { bar.insertBefore(hear, bar.firstChild); }

    // Arrive already watching: dashboard view, silent playback running.
    const still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setTimeout(function () {
      openView("dashboard");
      const play = $("play");
      if (!still && play && !play.disabled && play.textContent.indexOf("Play") !== -1) { play.click(); }
    }, 1800);
  });
})();
