import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { TwinBrain } from "../web/twin.js";
import { learningView } from "../web/learning_view.js";

// Signed weights and an empty CSR row: only receivers of changed connections
// flash; opposite signed changes cannot cancel when a cell receives both.
const rows = new Int32Array([0, 2, 2, 4]);
const before = new Float64Array([1, -1, 4, 6]);
const after = new Float64Array([1.01, -.99, 4, 6]);
const original = [rows.slice(), before.slice(), after.slice()];
const result = learningView(rows, before, after);
assert.equal(result.changedEdges, 2); assert.equal(result.changedCells, 1);
assert.ok(Math.abs(result.levels[0] - Math.sqrt(.4)) < 1e-6);
assert.equal(result.levels[1], 0); assert.equal(result.levels[2], 0);
assert.deepEqual([rows, before, after], original, "mapping must not mutate graph or weights");
after[3] += 100;
const otherChanged = learningView(rows, before, after);
assert.equal(otherChanged.levels[0], result.levels[0], "a different row cannot rescale this receiver's flash");
assert.equal(otherChanged.levels[2], 1);
assert.equal(otherChanged.changedEdges, 3); assert.equal(otherChanged.changedCells, 2);
const tiny = learningView(new Int32Array([0, 1]), new Float64Array([0]), new Float64Array([1e-11]));
assert.equal(tiny.changedEdges, 0); assert.equal(tiny.levels[0], 0);
assert.throws(() => learningView(new Int32Array([0, 2]), before, after), /cover every weight/);
assert.throws(() => learningView(new Int32Array([0, 1]), [0], [NaN]), /finite/);

// Real frozen brain: neurons move under a pulse, but its plasticity channel must
// remain black. For a real lesson, changed-cell count follows actual applied
// weights rather than the requested/proposed update or current firing activity.
const payload = JSON.parse(readFileSync(new URL("../web/data/brain_oculomotor.json", import.meta.url), "utf8"));
const twin = new TwinBrain(payload, { learning: true }), b = twin.halves.left;
twin.setLearning(false);
const frozen = b.w.slice();
twin.run({ left: { _Int_: .1 } }, 5);
assert.ok(b.s.some(x => x > 0));
const activityOnly = learningView(b.rowPtr, frozen, b.w);
assert.equal(activityOnly.changedEdges, 0); assert.equal(activityOnly.changedCells, 0);
assert.ok(activityOnly.levels.every(x => x === 0));
twin.run({}, 25); const target = b.s.slice(); twin.run({}, 100);
twin.setLearning(true);
const weightsBefore = b.w.slice(); twin.lesson("left", target);
const state = structuredClone(twin), learned = learningView(b.rowPtr, weightsBefore, b.w);
assert.ok(learned.changedEdges > 0); assert.ok(learned.changedCells > 0);
for (let i = 0; i < b.n; i++) {
  const rowChanged = b.w.subarray(b.rowPtr[i], b.rowPtr[i + 1]).some((w, offset) => Math.abs(w - weightsBefore[b.rowPtr[i] + offset]) > 1e-10);
  assert.equal(learned.levels[i] > 0, rowChanged);
}
assert.deepEqual(structuredClone(twin), state);
console.log("learning view ok: applied-weight flashes, frozen-activity separation, receiver-local scaling, and immutable inputs");
