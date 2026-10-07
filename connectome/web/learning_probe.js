// A standardized, teaching-free response assay. All activity runs in disposable
// copies; the animal's states, parameters, counters and pending lessons are untouched.
import { SettlingBrain } from "./brain.js";
import { LEARN, STEP_MS, SACCADE_STEPS, GAZE_DEGREES_PER_UNIT } from "./dictionary.js";

export function probeLearning(twin, { level = 0.07, seconds = 5 } = {}) {
  if (!(Number.isFinite(level) && level > 0 && level <= 1 && Number.isFinite(seconds) && seconds > 0 && seconds <= 30)) throw new Error("invalid response probe");
  const steps = Math.round(seconds * 1000 / STEP_MS);
  function response(source) {
    const b = new SettlingBrain(twin.payload);
    if (source) { b.w.set(source.w); b.bias.set(source.bias); }
    else for (let e = 0; e < b.edges; e++) b.w[e] *= LEARN.start;
    b.stimulate("_Int_", level);
    for (let k = 0; k < SACCADE_STEPS; k++) b.step();
    b.clearStimuli();
    for (let k = 0; k < LEARN.targetDelay; k++) b.step();
    const read = () => GAZE_DEGREES_PER_UNIT * (b.mean("ABD_m") + b.mean("ABD_i"));
    const start = read(), trace = [start];
    for (let k = 1; k <= steps; k++) { b.step(); if (k % 25 === 0 || k === steps) trace.push(read()); }
    const end = read(), ratio = start > 1e-9 ? end / start : null;
    return { start, end, ratio, trace, growing: ratio !== null && ratio > 1.05 };
  }
  return { seconds: steps * STEP_MS / 1000, level, baseline: response(null), left: response(twin.halves.left), right: response(twin.halves.right) };
}
