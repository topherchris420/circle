/* Browser end-to-end check for First Light (optional; needs Playwright and Chromium).
 *
 * 1. Recorded mode: replays a committed real recording in the page and requires the
 *    downloaded bundle to equal the committed bundle byte for byte.
 * 2. Live mode: drives the camera path with a SIMULATED camera (a canvas stream: a red
 *    field whose green level pulses at 72 bpm, going dark when the page asks for the
 *    finger to be lifted). This exercises capture, the guided protocol, the sound
 *    commands, and the bundle; it is not a physical measurement and its bundle is
 *    written to a temporary directory, never to evidence/.
 *
 * Usage: node tests/js/first_light_e2e.js [--out <dir>] [--shots <dir>]
 * Prints one JSON document; exits 0 when every check holds.
 */
"use strict";
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..", "..");
const SITE = path.join(ROOT, "site");
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };

function arg(name, fallback) {
  const at = process.argv.indexOf(name);
  return at >= 0 ? path.resolve(process.argv[at + 1]) : fallback;
}

function serve() {
  const server = http.createServer((request, response) => {
    const name = decodeURIComponent(request.url.split("?")[0]).replace(/^\/+/, "") || "first-light.html";
    const file = path.join(SITE, name);
    if (!file.startsWith(SITE) || !fs.existsSync(file)) { response.writeHead(404); response.end(); return; }
    response.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
    response.end(fs.readFileSync(file));
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

// Installed before the page's scripts: a canvas stands in for the camera.
function simulatedCamera() {
  const canvas = document.createElement("canvas");
  canvas.width = 320; canvas.height = 240;
  const g = canvas.getContext("2d");
  const draw = () => {
    const prompt = document.getElementById("prompt");
    const lifted = prompt && prompt.dataset.step === "fault";
    if (lifted) { g.fillStyle = "rgb(8,8,10)"; }
    else {
      const phase = ((performance.now() / 1000) * 72 / 60) % 1;
      const dip = phase < 0.18 ? phase / 0.18 : Math.exp(-4.5 * (phase - 0.18) / 0.82);
      g.fillStyle = "rgb(235," + (70 - 9 * dip).toFixed(2) + ",30)";
    }
    g.fillRect(0, 0, 320, 240);
    requestAnimationFrame(draw);
  };
  draw();
  navigator.mediaDevices.getUserMedia = () => Promise.resolve(canvas.captureStream(30));
}

async function download(page, dir) {
  const [item] = await Promise.all([page.waitForEvent("download"), page.click("#download")]);
  const target = path.join(dir, item.suggestedFilename());
  await item.saveAs(target);
  return target;
}

(async () => {
  const out = arg("--out", fs.mkdtempSync(path.join(os.tmpdir(), "first-light-e2e-")));
  const shots = arg("--shots", null);
  fs.mkdirSync(out, { recursive: true });
  const server = await serve();
  const base = "http://127.0.0.1:" + server.address().port + "/";
  const browser = await chromium.launch({ args: ["--autoplay-policy=no-user-gesture-required"] });
  const result = { checks: {}, errors: [] };
  try {
    // ---- 1. recorded replay
    let context = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true, deviceScaleFactor: shots ? 2 : 1 });
    let page = await context.newPage();
    page.on("pageerror", (e) => result.errors.push("recorded: " + e.message));
    await page.goto(base + "first-light.html?autostart");
    await page.waitForFunction(() => document.getElementById("state").textContent.startsWith("Session ended"), null, { timeout: 60000 });
    const recorded = await page.evaluate(() => ({
      selfcheck: document.getElementById("selfcheck").textContent, ok: document.getElementById("selfcheck").dataset.ok,
      lit: Array.from(document.querySelectorAll("#chain li.lit")).map((li) => li.dataset.step),
      rows: document.querySelectorAll("#ledger tr").length, dots: document.querySelectorAll("#plot .dot").length }));
    const bundle = await download(page, out);
    const committed = path.join(ROOT, "evidence", "first-light", "sessions", "149055-072.zip");
    result.checks.recorded_self_check = recorded.ok === "true";
    result.checks.recorded_chain_complete = recorded.lit.length === 6;
    result.checks.recorded_bundle_equals_committed = fs.readFileSync(bundle).equals(fs.readFileSync(committed));
    result.recorded = { ...recorded, bundle };
    if (shots) { fs.mkdirSync(shots, { recursive: true }); await page.screenshot({ path: path.join(shots, "first-light-recorded.png"), fullPage: true }); }
    await context.close();

    // ---- 2. live path, simulated camera
    context = await browser.newContext({ viewport: { width: 420, height: 900 }, acceptDownloads: true, deviceScaleFactor: shots ? 2 : 1 });
    page = await context.newPage();
    page.on("pageerror", (e) => result.errors.push("live: " + e.message));
    await page.addInitScript(simulatedCamera);
    await page.goto(base + "first-light.html");
    await page.click('.mode[data-mode="camera"]');
    await page.click("#sound");
    await page.click("#start");
    if (shots) {
      await page.waitForFunction(() => document.querySelector("#ring").dataset.state === "act", null, { timeout: 60000 });
      await page.waitForTimeout(2500);
      await page.screenshot({ path: path.join(shots, "first-light-live-acting.png") });
      await page.waitForFunction(() => document.querySelector("#ring").dataset.state === "refuse" && window.FirstLightPage.sawAct, null, { timeout: 60000 });
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(shots, "first-light-live-refusing.png") });
    }
    await page.waitForFunction(() => document.getElementById("state").textContent.startsWith("Session ended"), null, { timeout: 120000 });
    const live = await page.evaluate(() => ({
      state: document.getElementById("state").textContent, selfcheck: document.getElementById("selfcheck").textContent,
      ok: document.getElementById("selfcheck").dataset.ok, tiles: document.getElementById("tiles").innerText,
      lit: Array.from(document.querySelectorAll("#chain li.lit")).map((li) => li.dataset.step) }));
    result.checks.live_protocol_completed = live.state.includes("protocol complete");
    result.checks.live_self_check = live.ok === "true";
    result.checks.live_chain_complete = live.lit.length === 6;
    result.live = { ...live, bundle: await download(page, out) };
    await context.close();

    // ---- 3. the phantom screen renders and pulses
    context = await browser.newContext({ viewport: { width: 420, height: 800 } });
    page = await context.newPage();
    page.on("pageerror", (e) => result.errors.push("phantom: " + e.message));
    await page.goto(base + "first-light-phantom.html");
    const colours = new Set();
    for (let i = 0; i < 12; i++) { colours.add(await page.evaluate(() => document.getElementById("field").style.background)); await page.waitForTimeout(70); }
    result.checks.phantom_pulses = colours.size > 3;
    await context.close();
  } catch (error) {
    result.errors.push(String(error && error.stack ? error.stack : error));
  } finally {
    await browser.close();
    server.close();
  }
  result.checks.no_page_errors = result.errors.length === 0;
  result.ok = Object.values(result.checks).every(Boolean);
  console.log(JSON.stringify(result, null, 1));
  process.exitCode = result.ok ? 0 : 1;
})();
