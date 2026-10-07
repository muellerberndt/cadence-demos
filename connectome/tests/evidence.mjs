// Reproduce the receipt's static comparison from its recorded LIF rates and an
// independent run of the browser rate engine. This verifies the reported metrics;
// it does not assert spike/rate dynamical equivalence or rerun the six LIF trials.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SettlingBrain } from "../web/brain.js";

const read = name => JSON.parse(readFileSync(new URL(`../web/data/${name}`, import.meta.url), "utf8"));
const payload = read("brain_oculomotor.json"), receipt = read("receipt_oculomotor.json");
assert.equal(payload.connectome_digest, receipt.connectome_digest, "payload and receipt must describe the same wiring");
const brain = new SettlingBrain(payload), recorded = receipt.spiking;
assert.equal(recorded.steady_rates.length, brain.n);
assert.ok(recorded.steady_rates.every(rate => Number.isFinite(rate) && rate >= 0));

// The payload rounds its gain to .3224; the frozen protocol selected .322445.
// Rebuild the declared weight = gain * count * sign at the receipt's exact gain.
const gain = receipt.wirings.measured.selected_gain;
assert.ok(Number.isFinite(gain) && gain > 0);
for (let e = 0; e < brain.edges; e++) brain.w[e] = gain * brain.count[e] * brain.sign[e];
brain.stimulate("_Int_", 0.3);
brain.settleFree(3000);
const driven = new Set(payload.populations._Int_);
const free = Array.from({ length: brain.n }, (_, i) => i).filter(i => !driven.has(i));
assert.equal(free.length, recorded.static_equivalence.neurons_compared);
assert.equal(free.length, 88, "include all undriven cells, including silent cells");
const activity = free.map(i => brain.s[i]), rates = free.map(i => recorded.steady_rates[i]);
const dot = (a, b) => a.reduce((sum, value, i) => sum + value * b[i], 0);
const cosine = dot(activity, rates) / (Math.sqrt(dot(activity, activity)) * Math.sqrt(dot(rates, rates)) + 1e-12);

function ranks(values) {
  const order = values.map((_, i) => i).sort((i, j) => values[i] - values[j]);
  const result = new Array(values.length);
  for (let first = 0; first < order.length;) {
    let end = first + 1;
    while (end < order.length && values[order[end]] === values[order[first]]) end++;
    for (let k = first; k < end; k++) result[order[k]] = (first + end + 1) / 2;
    first = end;
  }
  return result;
}
const centered = values => { const mean = values.reduce((sum, value) => sum + value, 0) / values.length; return values.map(value => value - mean); };
const a = centered(ranks(activity)), b = centered(ranks(rates));
const spearman = dot(a, b) / Math.sqrt(dot(a, a) * dot(b, b));
for (const [name, actual] of Object.entries({ cosine, spearman })) {
  const expected = recorded.static_equivalence[name];
  assert.ok(Number.isFinite(actual) && Math.abs(actual - expected) < 1e-12, `${name}: browser ${actual}, receipt ${expected}`);
}
console.log(`evidence ok: ${free.length} undriven neurons, receipt gain ${gain}, cosine ${cosine.toFixed(9)}, Spearman ${spearman.toFixed(9)}`);
