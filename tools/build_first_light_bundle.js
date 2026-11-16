#!/usr/bin/env node
/* Build First Light's committed recorded-session evidence bundle with the browser's own code.
 *
 * Replays site/first-light-recording.js (a real BUT PPG camera recording) through
 * site/first-light-core.js, frame by frame, exactly as the page does, and writes the
 * deterministic bundle to evidence/first-light/recorded-session.zip. Running it twice,
 * or pressing "Replay" in the page and downloading, yields the same bytes.
 *
 * Usage: node tools/build_first_light_bundle.js [--output path] [--check]
 *   --check  rebuild in memory and exit 1 if the committed bundle differs
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

function build() {
  const FirstLight = require(CORE);
  const recording = loadRecording();
  const frames = FirstLight.parseFramesCsv(recording.frames_csv);
  const session = FirstLight.runFrames(frames);
  if (FirstLight.framesCsv(session.frames) !== recording.frames_csv) {
    throw new Error("re-encoding the recording's frames changed them");
  }
  const coreSha = FirstLight.sha256(new Uint8Array(fs.readFileSync(CORE)));
  return { FirstLight, session, result: FirstLight.bundle(session, {
    mode: "recorded-reference", reference: recording.reference, created: null, core_sha256: coreSha }) };
}

function main(argv) {
  const check = argv.includes("--check");
  const at = argv.indexOf("--output");
  const output = at >= 0 ? path.resolve(argv[at + 1]) : DEFAULT_OUTPUT;
  const { session, result } = build();
  const acts = session.decisions.filter((d) => d.decision === "ACT").length;
  const summary = `${session.frames.length} frames · ${session.decisions.length} evaluations · ${acts} ACT · ` +
    `${session.decisions.length - acts} REFUSE · manifest sha256 ${result.manifest_sha256}`;
  if (check) {
    const committed = fs.existsSync(output) ? new Uint8Array(fs.readFileSync(output)) : null;
    const same = committed && committed.length === result.zip.length && committed.every((b, i) => b === result.zip[i]);
    console.log((same ? "MATCH " : "DIFFERS ") + summary);
    return same ? 0 : 1;
  }
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, result.zip);
  console.log(`wrote ${path.relative(ROOT, output)} (${result.zip.length} bytes): ${summary}`);
  return 0;
}

if (require.main === module) { process.exitCode = main(process.argv.slice(2)); }
module.exports = { build, loadRecording };
