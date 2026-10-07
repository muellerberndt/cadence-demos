import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { TwinBrain } from "../web/twin.js";
import { probeLearning } from "../web/learning_probe.js";

const payload = JSON.parse(readFileSync(new URL("../web/data/brain_oculomotor.json", import.meta.url), "utf8"));
const twin = new TwinBrain(payload, { learning: true });
const first = probeLearning(twin);
for (const side of ["left", "right"]) {
  assert.equal(first[side].trace.length, first.baseline.trace.length);
  for (let k = 0; k < first.baseline.trace.length; k++) {
    assert.ok(Math.abs(first[side].trace[k] - first.baseline.trace[k]) < 1e-10,
      "fresh learning circuit and baseline use the same four-fifths gain (roundoff only)");
  }
}
twin.run({ left: { _Int_: .1 } }, 5);
twin.run({}, 25);
const target = twin.halves.left.s.slice();
twin.run({}, 100);
twin.lesson("left", target);
assert.ok(twin.departure() > 0, "fixture contains acquired weights");
twin.halves.left.setDrive(0, .123);
const before = structuredClone(twin);
const acquired = probeLearning(twin);
assert.deepEqual(structuredClone(twin), before,
  "probe leaves every live state, weight, drive, scratch array, optimizer and counter untouched");
assert.notDeepEqual(acquired.left.trace, first.left.trace, "probe can see acquisition");
twin.setLearning(false);
twin.run({ left: { _Int_: .1 }, right: { _Int_: .03 } }, 200);
twin.reset();
assert.deepEqual(probeLearning(twin), acquired,
  "frozen acquired response survives elapsed activity and a neural-state reset");

// Independent one-cell circuit: stronger positive recurrence must hold a pulse
// longer; removing recurrence must lose it. This checks the assay's behavioral
// sensitivity without using its own measurement formula as an oracle.
const b64 = a => Buffer.from(a.buffer).toString("base64");
const one = new TwinBrain({ n: 1, edges: 1, gain: 8,
  model: { dt: .2, slope: .25, threshold: 0, gain: 8, stimulus_amplitude: 1 },
  arrays: { row_ptr: b64(new Int32Array([0, 1])), pre: b64(new Int32Array([0])),
    weight: b64(new Float64Array([8])), count: b64(new Uint16Array([1])), sign: b64(new Float64Array([1])) },
  populations: { _Int_: [0], ABD_m: [0], ABD_i: [] } }, { learning: true });
one.halves.left.w[0] = 7.9; one.halves.right.w[0] = 0;
const perturbed = probeLearning(one);
assert.ok(perturbed.left.end > 10 * perturbed.baseline.end, "strong positive recurrence retains the pulse");
assert.ok(perturbed.right.end < perturbed.baseline.end, "ablated recurrence cannot retain the pulse");
assert.ok(perturbed.left.ratio > perturbed.baseline.ratio);
assert.throws(() => probeLearning(twin, { seconds: Infinity }));
assert.throws(() => probeLearning(twin, { level: 0 }));
console.log("learning probe ok: matched fresh baseline, live custody, frozen retention, and independent recurrent-weight sensitivity");
