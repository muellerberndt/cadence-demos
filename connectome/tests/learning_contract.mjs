// Learning lifecycle, finite-update custody, and equal-duration continuation checks.
// These are independent invariants; library arithmetic parity remains learning_parity.mjs.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SettlingBrain, decodeArray } from "../web/brain.js";
import { TwinBrain } from "../web/twin.js";
import { LEARN } from "../web/dictionary.js";

const payload = JSON.parse(readFileSync(new URL("../web/data/brain_oculomotor.json", import.meta.url), "utf8"));
const snapshot = b => ({
  v: [...b.v], s: [...b.s], drive: [...b.drive], weight: [...b.w], bias: [...b.bias],
  efficacy: b.efficacy && [...b.efficacy], mass0: b.mass0 && [...b.mass0],
  secondMoment: b.secondMoment && [...b.secondMoment], secondMomentBias: b.secondMomentBias && [...b.secondMomentBias],
  contrastUpdates: b.contrastUpdates, lessons: b.lessons, steps: b.steps, gain: b.gain,
});
const twin = new TwinBrain(payload), b = twin.halves.left;
const compiled = decodeArray(payload.arrays.weight, Float64Array);
assert.deepEqual(b.w, compiled, "historical constructor keeps the compiled weights exactly");
twin.setLearning(true);
assert.equal(b.gain, LEARN.start * payload.gain);
b.stimulate("_Int_", .1);
for (let k = 0; k < 5; k++) b.step();
b.clearStimuli();
for (let k = 0; k < 25; k++) b.step();
const target = b.s.slice();
for (let k = 0; k < 100; k++) b.step();
const before = snapshot(b), report = twin.lesson("left", target);
assert.ok(report.plusSteps > 1 && report.plusSteps < LEARN.steps, "fixture exercises an early-stopping nudge");
assert.equal(report.minusSteps, report.plusSteps, "free continuation covers the same actual duration");
assert.deepEqual([...b.v], before.v);
assert.deepEqual([...b.s], before.s);
assert.deepEqual([...b.drive], before.drive);
assert.equal(b.steps, before.steps, "private phases do not advance the live state");
const measuredStep = b.efficacy.reduce((sum, x, i) => sum + Math.abs(x - before.efficacy[i]), 0) / b.edges;
assert.equal(report.appliedScaleStep, measuredStep, "reported change includes every bound/projection");
assert.ok(measuredStep > 0);

// A pause is not erasure. Repeated enable/freeze/resume keeps acquired parameters,
// the reference mass, neural state and optimizer counters byte-for-byte.
const learned = snapshot(b), lessons = twin.lessons;
twin.setLearning(false);
assert.deepEqual(snapshot(b), learned);
assert.throws(() => twin.lesson("left", target), /frozen/);
assert.deepEqual(snapshot(b), learned);
twin.setLearning(true); twin.setLearning(true);
assert.deepEqual(snapshot(b), learned);
assert.equal(twin.lessons, lessons);
assert.ok(twin.departure() > 0);

// Malformed lessons must not corrupt a learned continuation or consume a lesson.
for (const options of [
  { beta: 0 }, { beta: Infinity }, { eta: -1 }, { etaBias: NaN },
  { steps: 1.5 }, { tolerance: NaN }, { cap: 0 }, { normalize: 1 },
  { normalizeFloor: 0 }, { decay: 1 }, { massCap: .5 }, { centered: 1 },
]) {
  assert.throws(() => b.lesson(b.sets._Int_, target, options));
  assert.deepEqual(snapshot(b), learned);
}
for (const outputs of [[], [0, 0], [-1], [b.n]]) {
  assert.throws(() => b.lesson(outputs, target));
  assert.deepEqual(snapshot(b), learned);
}
const invalidTarget = target.slice(); invalidTarget[0] = NaN;
assert.throws(() => b.lesson(b.sets._Int_, invalidTarget));
assert.throws(() => b.lesson(b.sets._Int_, target.subarray(1)));
assert.deepEqual(snapshot(b), learned);

// Reset clears an actual running RMS history, restores baseline bias and efficacy,
// and preserves live state. It is distinct from the historical compiled control.
b.lesson(b.sets._Int_, target, { normalize: .9, eta: .001 });
assert.equal(b.contrastUpdates, 1);
const live = { v: [...b.v], s: [...b.s], drive: [...b.drive], steps: b.steps };
twin.resetLearning();
assert.equal(twin.lessons, 0); assert.equal(b.lessons, 0);
assert.equal(b.mass0, null); assert.equal(b.secondMoment, undefined);
assert.equal(b.secondMomentBias, undefined); assert.equal(b.contrastUpdates, undefined);
assert.deepEqual(b.efficacy, Float64Array.from(b.efficacy0 || b.sign));
assert.deepEqual(b.bias, b.bias0);
assert.equal(b.gain, LEARN.start * payload.gain);
assert.equal(twin.departure(), 0);
assert.deepEqual({ v: [...b.v], s: [...b.s], drive: [...b.drive], steps: b.steps }, live);
twin.restoreCompiled();
assert.equal(twin.learning, false); assert.deepEqual(b.w, compiled);
assert.deepEqual({ v: [...b.v], s: [...b.s], drive: [...b.drive], steps: b.steps }, live);
twin.setLearning(true);
assert.equal(b.gain, LEARN.start * payload.gain);

// Controlled phase endpoints isolate update-boundary behavior: saturation reports
// zero applied change even when a positive update was proposed. A finite but
// overflowing learning rate must leave both parameters and RMS history untouched.
const b64 = a => Buffer.from(a.buffer).toString("base64");
const small = new SettlingBrain({ n: 2, edges: 1, gain: 1,
  model: { dt: .2, slope: .25, threshold: 0, gain: 1, stimulus_amplitude: 1 },
  arrays: { row_ptr: b64(new Int32Array([0, 0, 1])), pre: b64(new Int32Array([0])),
    weight: b64(new Float64Array([1])), sign: b64(new Float64Array([1])),
    bias: b64(new Float64Array([.25, -.5])) }, populations: {} });
small.enableLearning();
small.nudgedPhase = (_outputs, _target, beta) => ({ s: Float64Array.from(beta > 0 ? [1, 1] : [0, 0]), v: new Float64Array(2), taken: 1 });
const saturated = small.lesson([1], new Float64Array(2), { etaBias: 0, cap: 1 });
assert.ok(saturated.scaleStep > 0); assert.equal(saturated.appliedScaleStep, 0);
const finite = snapshot(small);
assert.throws(() => small.lesson([1], new Float64Array(2), { beta: 1e-10, eta: Number.MAX_VALUE }), /nonfinite/);
assert.deepEqual(snapshot(small), finite);
assert.throws(() => small.lesson([1], new Float64Array(2), { beta: 1e-200, normalize: .9 }), /nonfinite/);
assert.deepEqual(snapshot(small), finite);
const bounded = small.lesson([1], new Float64Array(2), { eta: 0, etaBias: 0, cap: .25, massCap: 1 });
assert.equal(small.efficacy[0], .25, "the hard cap survives a conflicting lower-mass adjustment");
assert.equal(bounded.massLowerUnmetRows, 1, "an infeasible lower-mass target is reported");
small.bias.fill(9); small.resetLearning();
assert.deepEqual([...small.bias], [.25, -.5], "reset restores exported biases, including nonzero values");

// A disconnected component must not change a contact's relative update. The former
// graph-wide product mean failed this counterexample and could exceed eta. Test
// both potentiation and depression, including a silent disconnected component.
for (const direction of [1, -1]) {
  let reference;
  for (const unrelated of [0, .01, 1]) {
    const isolated = new SettlingBrain({ n: 4, edges: 2, gain: 1,
      model: { dt: .2, slope: .25, threshold: 0, gain: 1, stimulus_amplitude: 1 },
      arrays: { row_ptr: b64(new Int32Array([0, 0, 1, 1, 2])), pre: b64(new Int32Array([0, 2])),
        weight: b64(new Float64Array([1, 1])), sign: b64(new Float64Array([1, 1])) }, populations: {} });
    isolated.nudgedPhase = (_o, _t, beta) => {
      const value = ((beta > 0) === (direction > 0)) ? 1 : 0;
      return { s: Float64Array.from([value, value, unrelated, unrelated]), v: new Float64Array(4), taken: 1 };
    };
    isolated.lesson([1], new Float64Array(4), { centered: false, relative: true, beta: 3, eta: .05, etaBias: .01 });
    const local = [isolated.efficacy[0], isolated.bias[0], isolated.bias[1]];
    if (reference) assert.deepEqual(local, reference, "disconnected activities cannot rescale a local update");
    reference = local;
    assert.ok(Math.abs(isolated.efficacy[0] - 1) <= .05, "nonnegative endpoint products bound the proposed contact step by eta");
    assert.equal(Math.sign(isolated.efficacy[0] - 1), direction);
  }
}
console.log("learning contract ok: equal phase duration, freeze/resume/reset, atomic finite updates, applied deltas, contact-local bounded normalization");
