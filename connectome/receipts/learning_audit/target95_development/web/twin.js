// Two halves of the brainstem from one reconstruction: the measured side and its mirror.
// The data covers one side of the hindbrain; the other half is a copy, and the mutual
// inhibition between the halves is absent from the data. Each half integrates its own
// direction. Pure logic, no worker API, so node can test it.
import { SettlingBrain, decodeArray } from "./brain.js";
import { LEARN } from "./dictionary.js";

export const SIDES = ["left", "right"];
export const READOUTS = ["_Int_", "ABD_m", "ABD_i", "_DOs_", "_Axl_", "vSPNs", "periphery"];

export class TwinBrain {
  constructor(payload, { learning = false } = {}) {
    this.payload = payload;
    this.halves = { left: new SettlingBrain(payload), right: new SettlingBrain(payload) };
    this.n = this.halves.left.n;
    this.steps = 0;
    this.learning = false; this.learningInitialized = false; this.lessons = 0;
    if (learning) this.setLearning(true);
  }
  /** First enable starts leaky. Later toggles freeze/resume the acquired parameters and history. */
  setLearning(on) {
    if (on && !this.learningInitialized) { this.resetLearning(); return; }
    this.learning = !!on;
  }
  /** Explicitly restart acquisition at the exported parameters and leaky gain; keep live v/s. */
  resetLearning() {
    for (const side of SIDES) {
      const b = this.halves[side];
      b.resetLearning(LEARN.start * this.payload.gain);
    }
    this.learning = true; this.learningInitialized = true; this.lessons = 0;
  }
  /** Restore the historical compiled circuit and freeze it, without resetting the live state. */
  restoreCompiled() {
    for (const side of SIDES) {
      const b = this.halves[side];
      b.resetLearning(this.payload.gain);
      b.w.set(decodeArray(this.payload.arrays.weight, Float64Array));
    }
    this.learning = false; this.learningInitialized = false; this.lessons = 0;
  }
  /** Mean absolute efficacy departure from the exported baseline, including while frozen. */
  departure() {
    let sum = 0, n = 0;
    for (const side of SIDES) { const b = this.halves[side]; if (!b.efficacy) continue; const baseline = b.efficacy0 || b.sign; for (let e = 0; e < b.edges; e++) sum += Math.abs(b.efficacy[e] - baseline[e]); n += b.edges; }
    return n ? sum / n : 0;
  }
  /** One admitted lesson for one half; a frozen twin never changes its parameters. */
  lesson(side, target) {
    if (!this.learning) throw new Error("learning is frozen");
    if (!SIDES.includes(side)) throw new RangeError("unknown brain side");
    const b = this.halves[side], outputs = this.payload.populations[LEARN.outputs];
    const report = b.lesson(outputs, target, LEARN);
    this.lessons++;
    return report;
  }
  /** Stimuli: {left: {population: level}, right: {population: level}}; levels in [0, 1]. */
  run(stimuli, steps) {
    const out = { steps: this.steps + steps, sides: {} };
    for (const side of SIDES) {
      const b = this.halves[side];
      b.clearStimuli();
      for (const [pop, level] of Object.entries((stimuli && stimuli[side]) || {})) { if (level > 0) b.stimulate(pop, level); else if (level < 0) for (const i of b.sets[pop] || []) b.setDrive(i, level); }
      for (let k = 0; k < steps; k++) b.step();
      const readouts = {};
      for (const r of READOUTS) if (this.payload.populations[r]) readouts[r] = b.mean(r);
      out.sides[side] = { readouts, active: b.activeCount(0.05) };
    }
    this.steps += steps;
    return out;
  }
  activity(side) { return this.halves[side].s; }
  /** The mean activity of a population on one side. */
  mean(side, name) { return this.halves[side].mean(name); }
  reset() { for (const side of SIDES) { this.halves[side].reset(); this.halves[side].clearStimuli(); } this.steps = 0; }
}
