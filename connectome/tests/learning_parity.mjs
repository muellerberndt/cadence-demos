// The browser engine's learning against the library: three saccades and a lesson after each, on the
// oculomotor net from a leaky start, every synapse and every bias plastic. Every efficacy and bias after
// every lesson must match the library's (tools/learning_cases.py) to near machine precision.
import { readFileSync } from "node:fs";
import { SettlingBrain, decodeArray } from "../web/brain.js";
globalThis.atob ??= (b) => Buffer.from(b, "base64").toString("binary");
const cases = JSON.parse(readFileSync(new URL("./learning_cases.json", import.meta.url), "utf8"));
const payload = JSON.parse(readFileSync(new URL("../" + cases.payload, import.meta.url), "utf8"));
if (payload.connectome_digest !== cases.connectome_digest) throw new Error("the cases were recorded on another wiring");
const brain = new SettlingBrain(payload);
brain.setGain(cases.start_gain_factor * payload.gain);
const Int = payload.populations[cases.outputs];
const meanInt = (s) => { let t = 0; for (const i of Int) t += s[i]; return t / Int.length; };
const cfg = cases.config;
let worst = 0, worstBias = 0;
cases.lessons.forEach((L, k) => {
  brain.clearStimuli(); brain.stimulate(cases.burst.population, cases.burst.level);
  for (let i = 0; i < cases.burst.steps; i++) brain.step();
  const target = Float64Array.from(brain.s);
  const burstEnd = meanInt(brain.s);
  brain.clearStimuli();
  for (let i = 0; i < cases.drift_steps; i++) brain.step();
  const free = meanInt(brain.s);
  const r = brain.lesson(Int, target, { beta: cfg.beta, eta: cfg.eta, etaBias: cfg.eta_bias, steps: cfg.nudged_steps, tolerance: cfg.tolerance, cap: cfg.scale_cap });
  const efficacy = decodeArray(L.efficacy, Float64Array), bias = decodeArray(L.bias, Float64Array);
  let dE = 0, dB = 0;
  for (let e = 0; e < brain.edges; e++) dE = Math.max(dE, Math.abs(brain.efficacy[e] - efficacy[e]));
  for (let i = 0; i < brain.n; i++) dB = Math.max(dB, Math.abs(brain.bias[i] - bias[i]));
  worst = Math.max(worst, dE); worstBias = Math.max(worstBias, dB);
  const row = [`lesson ${k + 1}`, `burst end ${burstEnd.toFixed(6)} (py ${L.burst_end_int.toFixed(6)})`, `free ${free.toFixed(6)} (py ${L.free_int.toFixed(6)})`,
    `nudged ${meanInt(r.plus).toFixed(6)} in ${r.plusSteps} (py ${L.nudged_int.toFixed(6)} in ${L.nudged_steps})`, `opposite ${meanInt(r.minus).toFixed(6)} in ${r.minusSteps} (py ${L.opposite_int.toFixed(6)} in ${L.opposite_steps})`,
    `scale step ${r.scaleStep.toExponential(3)} (py ${L.scale_step.toExponential(3)})`, `max |efficacy diff| ${dE.toExponential(2)}`, `max |bias diff| ${dB.toExponential(2)}`];
  console.log(row.join(" | "));
  if (r.plusSteps !== L.nudged_steps || r.minusSteps !== L.opposite_steps) throw new Error(`lesson ${k + 1}: the nudged phases stopped at different steps`);
});
const TOL = 1e-9;
if (worst > TOL || worstBias > TOL) throw new Error(`learning parity failed: efficacy ${worst}, bias ${worstBias}`);
console.log(`learning parity ok: ${cases.lessons.length} lessons, ${brain.edges} synapses and ${brain.n} biases plastic, worst efficacy difference ${worst.toExponential(2)}, bias ${worstBias.toExponential(2)}`);
