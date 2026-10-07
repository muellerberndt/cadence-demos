import assert from "node:assert/strict";
import { Life } from "../web/life.js";

function example(leftLevel, rightLevel) {
  const calls = [];
  const brain = { learning: true, setLearning(on) { this.learning = on; }, mean(side) { return (side === "left" ? leftLevel : rightLevel) / 2; }, activity(side) { return [this.mean(side)]; }, lesson(side) { calls.push(side); return { scaleStep: 0.01, plusSteps: 12, minusSteps: 12 }; } };
  const life = new Life(brain); life.time = 4;
  for (const [side, level] of [["left", leftLevel], ["right", rightLevel]]) Object.assign(life.learning.sides[side], { target: [level], level, since: 1 });
  return { life, calls };
}
for (const [left, right, expected] of [[0.2, 0.01, "left"], [0.01, 0.2, "right"]]) {
  const { life, calls } = example(left, right);
  life._endFixations("saccade");
  assert.deepEqual(calls, [expected], "only the half carrying the reference gaze may learn, independent of loop order");
}
{
  const { life, calls } = example(0.2, 0.01);
  life.setWorld("back"); life._endFixations("saccade");
  assert.deepEqual(calls, [], "a pending reference from the old feedback condition must not teach under the new one");
  assert.throws(() => life.setWorld("toString"), /no such world/);
}
{
  const { life, calls } = example(0.2, 0.01);
  life.learning.lessons = 7; life.setLearning(false); life._endFixations("saccade");
  life.setLearning(true); life._endFixations("saccade");
  assert.equal(life.learning.lessons, 7, "pause/resume preserves the acquired life history");
  assert.deepEqual(calls, [], "pause/resume must not replay unfinished lessons");
}
console.log("lesson life contracts: carrying half, feedback custody, and pause/resume passed");
