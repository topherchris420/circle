#!/usr/bin/env node
/* Build First Light recorded-session evidence bundles with the browser's own code.
 *
 * Replays a real BUT PPG camera recording through site/first-light-core.js, frame by
 * frame, exactly as the page does, and writes the deterministic bundle. Running it
 * twice, or pressing "Replay" in the page and downloading, yields the same bytes.
 *
 * Usage:
 *   node tools/build_first_light_bundle.js [--output path] [--check]
 *       the session the page replays (site/first-light-recording.js)
 *       --check  rebuild in memory and exit 1 if the committed bundle differs
 *   node tools/build_first_light_bundle.js --batch <dir>
 *       every <name>.recording.json in <dir> becomes <name>.zip beside it
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const CORE = path.join(ROOT, "site", "first-light-core.js");
const RECORDING = path.join(ROOT, "site", "first-light-recording.js");
const DEFAULT_OUTPUT = path.join(ROOT, "evidence", "first-light", "recorded-session.zip");

function loadRecording() {
  const sandbox = { window: {} };
  vm.runInNewContext(fs.readFileSync(RECORDING, "utf8"), sandbox, { filename: RECORDING });
  return sandbox.window.FIRST_LIGHT_RECORDING;
}

function build(recording) {
  const FirstLight = require(CORE);
  const frames = FirstLight.parseFramesCsv(recording.frames_csv);
  const session = FirstLight.runFrames(frames);
  if (FirstLight.framesCsv(session.frames) !== recording.frames_csv) {
    throw new Error("re-encoding the recording's frames changed them");
  }
  const coreSha = FirstLight.sha256(new Uint8Array(fs.readFileSync(CORE)));
  return { session, result: FirstLight.bundle(session, {
    mode: "recorded-reference", reference: recording.reference, created: null, core_sha256: coreSha }) };
}

function describe(session, result) {
  const acts = session.decisions.filter((d) => d.decision === "ACT").length;
  return `${session.frames.length} frames · ${session.decisions.length} evaluations · ${acts} ACT · ` +
    `${session.decisions.length - acts} REFUSE · manifest sha256 ${result.manifest_sha256}`;
}

function main(argv) {
  const batch = argv.indexOf("--batch");
  if (batch >= 0) {
    const dir = path.resolve(argv[batch + 1]);
    const names = fs.readdirSync(dir).filter((n) => n.endsWith(".recording.json")).sort();
    for (const file of names) {
      const { result } = build(JSON.parse(fs.readFileSync(path.join(dir, file), "utf8")));
      fs.writeFileSync(path.join(dir, file.replace(/\.recording\.json$/, ".zip")), result.zip);
    }
    console.log(`built ${names.length} bundles in ${dir}`);
    return 0;
  }
  const check = argv.includes("--check");
  const at = argv.indexOf("--output");
  const output = at >= 0 ? path.resolve(argv[at + 1]) : DEFAULT_OUTPUT;
  const { session, result } = build(loadRecording());
  if (check) {
    const committed = fs.existsSync(output) ? new Uint8Array(fs.readFileSync(output)) : null;
    const same = committed && committed.length === result.zip.length && committed.every((b, i) => b === result.zip[i]);
    console.log((same ? "MATCH " : "DIFFERS ") + describe(session, result));
    return same ? 0 : 1;
  }
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, result.zip);
  console.log(`wrote ${path.relative(ROOT, output)} (${result.zip.length} bytes): ${describe(session, result)}`);
  return 0;
}

if (require.main === module) { process.exitCode = main(process.argv.slice(2)); }
module.exports = { build, loadRecording };
