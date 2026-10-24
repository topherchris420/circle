"use strict";
const $ = (id) => document.getElementById(id);
let config, runs = [], selected = null, busy = false, connected = false;
let previousHistory = "", previousDetail = "", detailGeneration = 0;
const statusLabels = {running: "In progress", cancelling: "Stopping", completed: "Completed", failed: "Could not finish", cancelled: "Cancelled", interrupted: "Interrupted"};
const isActive = (run) => ["running", "cancelling"].includes(run.status);
const scenario = (id) => config.scenarios.find((item) => item.id === id);
const date = (value) => new Date(value).toLocaleString([], {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"});
const node = (tag, text, className) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; };

async function api(path, data, refreshToken = true) {
  const options = data === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json", "X-Circle-Token": config.token}, body: JSON.stringify(data)};
  const response = await fetch(path, {...options, signal: AbortSignal.timeout(15000)});
  const result = await response.json();
  // A restart can happen between polls without a visible connection failure.
  // Refresh and retry only a rejected request, never an uncertain submission.
  if (response.status === 403 && data !== undefined && refreshToken) {
    config = await api("/api/config");
    return api(path, data, false);
  }
  if (!response.ok) {
    const failure = new Error(result.error || "The workbench could not complete that request.");
    failure.status = response.status; throw failure;
  }
  return result;
}
function error(message) { $("error").textContent = message; $("error").hidden = !message; }
function updateStart() { $("start").disabled = busy || !connected || runs.some(isActive); }
function selectScenario(id) {
  const chosen = scenario(id);
  $("scenario-title").textContent = chosen.title;
  $("scenario-question").textContent = chosen.question;
}
function renderScenarios() {
  $("scenarios").replaceChildren(...config.scenarios.map((item, index) => {
    const label = node("label", undefined, "scenario-option");
    const radio = document.createElement("input");
    Object.assign(radio, {type: "radio", name: "scenario", value: item.id, checked: index === 0, required: true});
    radio.addEventListener("change", () => selectScenario(item.id));
    const card = node("span", undefined, "scenario-card");
    card.append(node("span", item.category, "scenario-category"), node("span", item.title, "scenario-name"), node("span", item.description, "scenario-description"));
    label.append(radio, card); return label;
  }));
  selectScenario("clean");
}
function outcome(run) {
  if (run.status !== "completed") return statusLabels[run.status] || run.status;
  const card = run.summary.scorecard;
  return `${card.passed}/${card.total} measurement checks · ${run.summary.audit_valid ? "Audit passed" : "Audit needs review"}`;
}
function renderHistory() {
  const query = $("history-search").value.trim().toLowerCase();
  const filtered = runs.filter((run) => `${scenario(run.settings.scenario)?.title} ${run.settings.scenario} ${run.settings.seed} ${run.settings.arm} ${statusLabels[run.status]}`.toLowerCase().includes(query));
  $("history-count").textContent = String(runs.length);
  const signature = JSON.stringify([filtered, selected, query]);
  if (signature === previousHistory) return;
  previousHistory = signature;
  if (!filtered.length) {
    const empty = node("div", undefined, "empty-state");
    empty.append(node("span", "", "empty-circle"), node("h3", query ? "No matching sessions." : "Your first session starts a record."), node("p", query ? "Try another scenario name or seed." : "Run a scenario above. Its report and evidence will stay here when you return."));
    $("history-list").replaceChildren(empty); return;
  }
  const focused = document.activeElement?.dataset?.runId;
  $("history-list").replaceChildren(...filtered.map((run) => {
    const row = node("button", undefined, `history-row${run.id === selected ? " selected" : ""}`);
    row.type = "button"; row.dataset.runId = run.id;
    row.setAttribute("aria-pressed", String(run.id === selected));
    const label = node("span");
    label.append(node("strong", scenario(run.settings.scenario)?.title || run.settings.scenario), node("small", `${date(run.created_at)} · ${run.settings.arm === "active" ? "Active" : "Sham"} · Seed ${run.settings.seed} · ${run.id.slice(0, 8)}`));
    row.append(label, node("span", outcome(run), "history-outcome"), node("span", "↗", "arrow"));
    row.addEventListener("click", () => showRun(run.id, true).catch((exc) => error(exc.message))); return row;
  }));
  if (focused) $("history-list").querySelector(`[data-run-id="${focused}"]`)?.focus({preventScroll: true});
}
function renderRun(run) {
  const signature = JSON.stringify(run);
  if (signature === previousDetail) return;
  previousDetail = signature;
  $("session").hidden = false;
  $("session-title").textContent = scenario(run.settings.scenario)?.title || run.settings.scenario;
  $("session-meta").textContent = `${date(run.created_at)} · ${run.settings.arm === "active" ? "Active" : "Sham"} · Seed ${run.settings.seed} · ${run.settings.compare ? "Matched comparison included" : "Single arm"} · ${run.id.slice(0, 8)}`;
  $("session-status").textContent = statusLabels[run.status] || run.status;
  $("progress").hidden = !isActive(run);
  $("results").hidden = run.status !== "completed";
  $("reuse").hidden = isActive(run);
  $("session-message").hidden = true;
  if (isActive(run)) {
    $("stage").textContent = run.stage;
    document.querySelectorAll(".stage-list li").forEach((el, index) => {
      el.className = run.step > index + 1 ? "done" : run.step === index + 1 ? "current" : "";
      if (run.step === index + 1) el.setAttribute("aria-current", "step"); else el.removeAttribute("aria-current");
    });
    $("cancel").disabled = run.status === "cancelling";
    $("cancel").textContent = run.status === "cancelling" ? "Stopping after the current stage…" : "Cancel session";
  } else if (run.status === "completed") {
    const summary = run.summary, card = summary.scorecard;
    $("measurement-value").textContent = `${card.passed} / ${card.total} passed`;
    $("measurement-value").className = card.passed === card.total ? "good" : "caution";
    $("measurement-note").textContent = card.passed === card.total ? "Every measurement check met its target for this simulated session." : `${card.total - card.passed} check(s) missed their targets. Disturbance scenarios can expose measurement limits; inspect the retained results below.`;
    $("audit-value").textContent = summary.audit_valid ? "Reconstruction passed" : "Review needed";
    $("audit-value").className = summary.audit_valid ? "good" : "bad";
    $("audit-note").textContent = summary.audit_valid ? "The independent auditor reconstructed the exported session and verified its evidence checks." : `Audit status: ${summary.replay_status}. Download the audit details to inspect failed checks.`;
    $("decision-value").textContent = String(summary.decisions.length);
    $("report-link").href = `/runs/${run.id}/report.html`;
    $("download-link").href = `/runs/${run.id}/bundle.zip`;
    $("audit-link").href = `/runs/${run.id}/audit.json`;
    $("check-rows").replaceChildren(...summary.checks.map((check) => {
      const row = node("tr");
      const value = typeof check.value === "number" ? new Intl.NumberFormat(undefined, {maximumSignificantDigits: 5}).format(check.value) : "Unavailable";
      row.append(node("td", check.label), node("td", `${value} ${check.unit || ""}`), node("td", check.target), node("td", check.passed ? "Passed" : "Missed target", check.passed ? "good" : "caution")); return row;
    }));
  } else {
    $("session-message").hidden = false;
    $("session-message").textContent = run.error || "This session was cancelled. Its partial output is retained locally, but is not offered as a completed report. You can start a fresh session with the same settings.";
  }
}
async function showRun(id, focus = false) {
  selected = id;
  const generation = ++detailGeneration;
  let run;
  try { run = await api(`/api/runs/${id}`); }
  catch (exc) {
    if (exc.status === 404 && selected === id) {
      selected = null; previousDetail = ""; $("session").hidden = true;
      history.replaceState(null, "", location.pathname);
      error("That saved session is no longer available. Choose another session or start a new one.");
      return;
    }
    throw exc;
  }
  if (generation !== detailGeneration || selected !== id) return;
  if (!location.hash || location.hash.startsWith("#session-")) history.replaceState(null, "", `#session-${id}`);
  renderRun(run); renderHistory();
  if (focus) { history.replaceState(null, "", `#session-${id}`); $("session").scrollIntoView({behavior: "auto", block: "start"}); $("session-title").focus({preventScroll: true}); }
}
async function refresh() {
  runs = await api("/api/runs");
  connected = true; $("connection").hidden = true;
  if (!selected && runs.length) selected = runs.find(isActive)?.id || runs[0].id;
  renderHistory(); updateStart();
  if (selected) await showRun(selected);
}
$("run-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || !connected || runs.some(isActive)) return;
  busy = true; updateStart(); error("");
  try {
    const data = new FormData(event.currentTarget);
    const run = await api("/api/runs", {scenario: data.get("scenario"), seed: Number(data.get("seed")), arm: data.get("arm"), compare: $("compare").checked});
    selected = run.id; previousDetail = "";
    await refresh(); await showRun(run.id, true);
  } catch (exc) { error(exc.message); }
  finally { busy = false; updateStart(); }
});
$("cancel").addEventListener("click", async () => {
  $("cancel").disabled = true;
  try { renderRun(await api(`/api/runs/${selected}/cancel`, {})); await refresh(); }
  catch (exc) { error(exc.message); $("cancel").disabled = false; }
});
$("reuse").addEventListener("click", () => {
  const run = runs.find((item) => item.id === selected); if (!run) return;
  document.querySelector(`input[name="scenario"][value="${run.settings.scenario}"]`).checked = true;
  selectScenario(run.settings.scenario);
  $("seed").value = run.settings.seed; $("arm").value = run.settings.arm; $("compare").checked = run.settings.compare;
  $("new-session").scrollIntoView({behavior: "auto"}); $("seed").focus({preventScroll: true});
});
$("history-search").addEventListener("input", renderHistory);

async function poll() {
  try {
    if (!config || !connected) {
      config = await api("/api/config");
      if (!document.querySelector('input[name="scenario"]')) renderScenarios();
      $("storage").textContent = `Saved on this computer: ${config.output}`;
    }
    await refresh();
  } catch (exc) {
    connected = false; updateStart();
    $("connection").textContent = "Connection interrupted. Your saved sessions remain on disk. Keep the workbench terminal running; this page will reconnect automatically.";
    $("connection").hidden = false;
  } finally { setTimeout(poll, document.hidden ? 6000 : 2000); }
}
const initial = location.hash.match(/^#session-([0-9a-f]{32})$/);
if (initial) selected = initial[1];
poll();
