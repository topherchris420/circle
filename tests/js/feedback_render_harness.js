/* Check audible synthesis topology and rendered field using deterministic API fakes. */
"use strict";
function check(ok, why) { if (!ok) throw new Error(why); }
class Param { constructor() { this.value = 0; this.last = null; }
  setTargetAtTime(value) { this.value = value; this.last = value; } }
class Node {
  constructor() { this.connections = [];
    for (const key of ["gain","frequency","Q","pan","threshold","knee","ratio","attack","release"]) this[key] = new Param();
  }
  connect(dest) { this.connections.push(dest); return dest; }
  start() {}
}
class FakeContext {
  constructor() { this.currentTime = 0; this.sampleRate = 8000; this.destination = new Node(); }
  createGain() { return new Node(); }
  createOscillator() { return new Node(); }
  createBiquadFilter() { return new Node(); }
  createDynamicsCompressor() { return new Node(); }
  createStereoPanner() { return new Node(); }
  createBufferSource() { return new Node(); }
  createBuffer() { return { getChannelData() { return new Float32Array(16000); } }; }
}
globalThis.AudioContext = FakeContext;
require("../../models/workbench_assets/resonance/synth.js");
require("../../models/workbench_assets/resonance/visual.js");
const synth = new globalThis.CircleSynth.AdaptiveSynth({});
synth.ensureContext();
const n = synth._nodes;
check(n.boGain.connections.includes(n.boDepth), "breathing LFO must enter modulator");
check(n.boDepth.connections.includes(n.breathGain.gain), "modulator must reach audible gain");
synth.enabled = true;
const low = { time_s: 0, audible: true, level: 0.15, intensity: 0, brightness: 0.2,
              tempo: 0.75, spatial: 0.3, breath_period_s: 10, gate_reasons: [] };
const high = { time_s: 2, audible: true, level: 0.45, intensity: 0.9, brightness: 0.9,
               tempo: 1.2, spatial: 0.8, breath_period_s: 6, gate_reasons: [] };
synth.update(low, 0, 0);
const quiet = n.master.gain.last, lowFilter = n.filter.frequency.last;
check(n.boDepth.gain.last > 0, "breathing guidance enabled");
synth.update(high, 2, 2);
check(n.master.gain.last > quiet, "audible amplitude responds");
check(n.filter.frequency.last > lowFilter, "filter responds to brightness");
check(n.noiseGain.gain.last > 0, "noise bed responds to intensity");
synth.enabled = false;
synth.update(high, 3, 3);
check(n.master.gain.last === 0, "revoked consent silences master");
function frame(point, quality) {
  const xs = [], labels = [];
  const ctx = {clearRect(){},beginPath(){},closePath(){},stroke(){},fill(){},
    moveTo(x){xs.push(x);},lineTo(x){xs.push(x);},arc(){},setLineDash(){},
    fillText(s){labels.push(s);} };
  const canvas = {width:700,height:400,getContext(){return ctx;}};
  new globalThis.CircleVisual.VisualField(canvas).render(point,0.25,quality,{force:true});
  return {span:Math.max(...xs)-Math.min(...xs),labels};
}
const a = frame(low,true), b = frame(high,true);
check(b.span > a.span + 80, "visual geometry responds");
const held = frame({...high,audible:false,gate_reasons:["MOTION_EXCESSIVE"]},false);
check(held.labels.some(x=>x.includes("holding")),"refusal visible");
console.log(JSON.stringify({breathing_connected:true,audio_responds:true,
  consent_silences:true,visual_responds:true,visual_refuses:true}));
