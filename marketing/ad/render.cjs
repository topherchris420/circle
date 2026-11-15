/* Render the CIRCLE film to MP4.
 *
 *   node marketing/ad/render.cjs [--cut 90|30] [--fps 30] [--scale 2] [--workers 3] [--crf 22]
 *                                [--python python3] [--stills 1,12.5,37.6]
 *
 * Steps, all local:
 *   1. Serve the repository to a headless Chromium and open the film page.
 *   2. Render CIRCLE's own adaptive audio engine (the workbench's synth.js) offline
 *      against the recorded session  ->  out/engine.wav
 *   3. Synthesize the score with soundtrack.py and mix the engine in  ->  out/circle-film-<cut>s.wav
 *   4. Step the film clock frame by frame, screenshot each frame at 2x, and pipe them to ffmpeg.
 *
 * Needs: Node with Playwright's Chromium, ffmpeg, and Python with NumPy.
 * The page is a pure function of film time, so a re-render of the same data is frame-identical.
 */
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const { spawn, spawnSync } = require("child_process");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..", "..");
const OUT = path.join(__dirname, "out");
const args = process.argv.slice(2);
const option = (name, fallback) => { const i = args.indexOf("--" + name); return i >= 0 ? args[i + 1] : fallback; };
const CUT = option("cut", "90");
const FPS = Number(option("fps", "30"));
const SCALE = Number(option("scale", "2"));
const PYTHON = option("python", "python3");
const STILLS = option("stills", "");
const WORKERS = Math.max(1, Number(option("workers", "3")));
const CRF = Number(option("crf", "22"));
const RANGE = option("range", "");               // "a,b" film seconds: picture only, for tests
const X264 = option("x264", "aq-mode=3:aq-strength=1.0:deblock=-1,-1");
const TARGET = option("output", path.join(ROOT, "marketing", "circle-film-" + CUT + "s.mp4"));

const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".m4a": "audio/mp4", ".wav": "audio/wav" };

function serve() {
  const server = http.createServer((request, response) => {
    const file = path.normalize(path.join(ROOT, decodeURIComponent(request.url.split("?")[0])));
    if (!file.startsWith(ROOT + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      response.writeHead(404); response.end("not found"); return;
    }
    response.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream", "cache-control": "no-store" });
    fs.createReadStream(file).pipe(response);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

function writeWav(file, pcm, sampleRate, channels) {
  const header = Buffer.alloc(44);
  header.write("RIFF", 0); header.writeUInt32LE(36 + pcm.length, 4); header.write("WAVE", 8); header.write("fmt ", 12);
  header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(channels, 22); header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(sampleRate * channels * 2, 28); header.writeUInt16LE(channels * 2, 32); header.writeUInt16LE(16, 34);
  header.write("data", 36); header.writeUInt32LE(pcm.length, 40);
  fs.writeFileSync(file, Buffer.concat([header, pcm]));
}

function run(command, commandArgs) {
  const result = spawnSync(command, commandArgs, { stdio: "inherit" });
  if (result.status !== 0) throw new Error(command + " " + commandArgs.join(" ") + " failed");
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const server = await serve();
  const base = "http://127.0.0.1:" + server.address().port + "/marketing/ad/index.html?render=1&cut=" + CUT;
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: SCALE });
  const problems = [];
  page.on("pageerror", (error) => problems.push(String(error)));
  await page.goto(base);
  const film = await page.evaluate(() => window.__ready);
  const frames = Math.round(film.duration * FPS);
  console.log("film: cut " + film.cut + ", " + film.duration + " s, " + frames + " frames at " + FPS + " fps, capture scale " + SCALE);

  if (STILLS) {
    for (const t of STILLS.split(",").map(Number)) {
      await page.evaluate((tau) => window.__seek(tau), t);
      const file = path.join(OUT, "still-" + CUT + "-" + t.toFixed(2).padStart(6, "0") + ".png");
      await page.screenshot({ path: file, type: "png" });
      console.log("still " + file);
    }
    await browser.close(); server.close();
    return;
  }

  // 2. the product's own sound, on the master timeline
  const engine = await page.evaluate(() => window.__engineLayer(48000));
  const master = Buffer.alloc(Math.round(90 * engine.sampleRate) * 4);
  Buffer.from(engine.base64, "base64").copy(master, Math.round(engine.from * engine.sampleRate) * 4);
  const engineWav = path.join(OUT, "engine.wav");
  writeWav(engineWav, master, engine.sampleRate, 2);
  console.log("engine layer: " + engine.from + "–" + engine.to + " s, peak " + engine.peak.toFixed(4) + " -> " + engineWav);

  // 3. score + mix
  const soundtrack = path.join(OUT, "circle-film-" + CUT + "s.wav");
  run(PYTHON, [path.join(__dirname, "soundtrack.py"), "--cut", CUT, "--engine", engineWav, "--output", soundtrack]);

  // 4. picture: contiguous chunks, one page each, joined losslessly
  await page.close();
  const started = Date.now();
  const x264 = ["-vf", "scale=1920:1080:flags=lanczos:in_color_matrix=bt601:in_range=pc:out_color_matrix=bt709:out_range=tv,format=yuv420p",
    "-c:v", "libx264", "-preset", "slow", "-crf", String(CRF), "-g", String(FPS * 5), "-x264-params", X264,
    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"];
  const [firstFrame, lastFrame] = RANGE ? RANGE.split(",").map((value) => Math.round(Number(value) * FPS)) : [0, frames];
  const bounds = Array.from({ length: WORKERS + 1 }, (_, k) => firstFrame + Math.round(((lastFrame - firstFrame) * k) / WORKERS));
  const parts = await Promise.all(bounds.slice(0, -1).map(async (first, k) => {
    const last = bounds[k + 1];
    const part = path.join(OUT, "part-" + CUT + "-" + k + ".mp4");
    const worker = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: SCALE });
    worker.on("pageerror", (error) => problems.push(String(error)));
    await worker.goto(base);
    await worker.evaluate(() => window.__ready);
    const encoder = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
      ...x264, "-an", part], { stdio: ["pipe", "inherit", "inherit"] });
    const encoded = new Promise((resolve, reject) => encoder.on("close", (code) => (code === 0 ? resolve() : reject(new Error("ffmpeg exited " + code)))));
    for (let i = first; i < last; i++) {
      await worker.evaluate((tau) => window.__seek(tau), i / FPS);
      const frame = await worker.screenshot({ type: "jpeg", quality: 98 });
      if (!encoder.stdin.write(frame)) await new Promise((resolve) => encoder.stdin.once("drain", resolve));
      if (k === 0 && (i - first) % 90 === 0) console.log("  worker 0: frame " + (i - first) + "/" + (last - first) + "  " + ((Date.now() - started) / 1000).toFixed(0) + " s");
    }
    encoder.stdin.end();
    await encoded;
    await worker.close();
    return part;
  }));
  await browser.close(); server.close();
  const list = path.join(OUT, "parts-" + CUT + ".txt");
  fs.writeFileSync(list, parts.map((part) => "file '" + part.replace(/'/g, "'\\''") + "'").join("\n") + "\n");
  if (RANGE) run("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-c:v", "copy", "-an", TARGET]);
  else run("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-i", soundtrack, "-c:v", "copy",
    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", TARGET]);
  parts.forEach((part) => fs.unlinkSync(part));

  // a preview soundtrack for the HTML page, and a poster frame
  run("ffmpeg", ["-y", "-loglevel", "error", "-i", soundtrack, "-c:a", "aac", "-b:a", "192k", path.join(OUT, "circle-film-" + CUT + "s.m4a")]);
  if (problems.length) console.log("page errors:\n  " + problems.join("\n  "));
  console.log("wrote " + TARGET + " in " + ((Date.now() - started) / 1000).toFixed(0) + " s");
})().catch((error) => { console.error(error); process.exit(1); });
