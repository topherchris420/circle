/* Phone-width check for the published website (optional; needs Playwright and Chromium).
 *
 * Serves demo/ under /circle/, as GitHub Pages does, opens every page on emulated phones, and
 * requires that no page scrolls sideways and that none logs an error or fails a request. First
 * Light's live path is meant to be used on a phone, so a sideways-scrolling page there is a bug
 * a visitor meets before anything else (it happened: a long <select> option widened its grid).
 *
 * Usage: node tests/js/site_phone_layout.js
 * Prints one JSON document; exits 0 when every check holds.
 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("fs");
const http = require("http");
const path = require("path");
const { chromium, devices } = require("playwright");

const DEMO = path.resolve(__dirname, "..", "..", "demo");
const PAGES = ["", "workbench.html", "first-light.html", "first-light-phantom.html"];
const PHONES = ["iPhone 13", "Pixel 5"];
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png" };

function serve() {
  const server = http.createServer((request, response) => {
    const url = new URL(request.url, "http://localhost");
    const relative = decodeURIComponent(url.pathname).replace(/^\/circle\//, "") || "index.html";
    const file = path.join(DEMO, relative);
    if (!file.startsWith(DEMO) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      response.writeHead(404); response.end(); return;
    }
    response.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(response);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

(async () => {
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}/circle/`;
  const browser = await chromium.launch();
  const results = [];
  try {
    for (const phone of PHONES) {
      const context = await browser.newContext({ ...devices[phone] });
      const flow = await context.newPage();
      await flow.emulateMedia({ reducedMotion: "reduce" });
      await flow.goto(base);
      await flow.locator(".hero-cta a[href='workbench.html']").tap();
      const hear = flow.locator("#hear-session");
      await flow.waitForFunction(() => document.querySelector("#hear-session")?.disabled === false);
      assert.equal(await flow.locator("#play").textContent(), "▶ Play");
      await hear.tap();
      await flow.getByRole("button", { name: "Mute session" }).waitFor();
      await flow.waitForFunction(() => Number(document.querySelector("#scrub").value) > 0);
      await hear.tap();
      assert.equal(await flow.locator("#demo-audio-status").textContent(), "Muted");
      await flow.close();
      for (const page of PAGES) {
        const tab = await context.newPage();
        const errors = [];
        tab.on("pageerror", (error) => errors.push(error.message));
        tab.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
        tab.on("requestfailed", (request) => errors.push(`failed ${request.url()}`));
        tab.on("response", (response) => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
        await tab.goto(base + page, { waitUntil: "networkidle" });
        await tab.waitForTimeout(500);
        const layout = await tab.evaluate(() => {
          const viewport = document.documentElement.clientWidth;
          const wide = [...document.querySelectorAll("body *")].filter((element) => {
            const box = element.getBoundingClientRect();
            return box.width > 0 && box.right > viewport + 1 && getComputedStyle(element).position !== "fixed";
          }).slice(0, 5).map((element) => element.tagName.toLowerCase() + (element.id ? `#${element.id}` : ""));
          return { viewport, scrollWidth: document.documentElement.scrollWidth, wide };
        });
        const ok = layout.scrollWidth <= layout.viewport && errors.length === 0;
        results.push({ phone, page: "/" + page, ok, ...layout, errors });
        await tab.close();
      }
      await context.close();
    }
  } finally {
    await browser.close();
    server.close();
  }
  const ok = results.every((result) => result.ok);
  console.log(JSON.stringify({ ok, results }, null, 2));
  process.exit(ok ? 0 : 1);
})();
