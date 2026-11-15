/* CIRCLE demo guide: no instructions required.
 * Opens on the dashboard, starts silent playback, explains what each trace is,
 * and offers one click to hear the recorded adaptive audio. A first decision
 * is opened in the evidence explorer so "inspect a decision" is one tab away.
 */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  ready(function () {
    // One explainer, in plain words, above everything.
    const intro = document.createElement("section");
    intro.className = "panel";
    intro.style.marginBottom = "14px";
    intro.innerHTML = "<h2>What you are looking at</h2>" +
      "<p class='lead'>A simulated person's <b>sensors</b> — heart pulse (PPG), skin conductance (EDA), and motion (IMU) — " +
      "replayed second by second. The <b>top charts</b> are what the instrument measured. " +
      "<b>Sensor confidence</b> shows when the evidence was good enough to act on. The <b>feedback engine</b> strip is " +
      "the sound level that was presented, held, and released.</p>" +
      "<p class='lead'><b>Listen:</b> click <b>Hear this session</b> once (browsers require one click before sound). " +
      "The sound follows the recorded signals — calmer stretches are quieter and darker, impaired evidence holds it. " +
      "<b>Inspect a decision:</b> open the <b>Evidence</b> tab; every action shows its measurements, its rule, and " +
      "whether replay reproduces it.</p>";
    const main = $("main");
    main.insertBefore(intro, main.firstChild);

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
    setTimeout(function () {
      const tabs = document.querySelectorAll(".view-tab");
      const dash = Array.prototype.find.call(tabs, (t) => t.dataset.view === "dashboard");
      if (dash) { dash.click(); }
      const play = $("play");
      if (play && !play.disabled && play.textContent.indexOf("Play") !== -1) { play.click(); }
    }, 1800);
  });
})();
