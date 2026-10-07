// Two halves of the brainstem from one reconstruction: the measured side and its mirror.
// The data covers one side of the hindbrain; the other half is a copy, and the mutual
// inhibition between the halves is absent from the data. Each half integrates its own
// direction. Pure logic, no worker API, so node can test it.
import { SettlingBrain } from "./brain.js";
import { LEARN } from "./dictionary.js";

export const SIDES = ["left", "right"];
export const READOUTS = ["_Int_", "ABD_m", "ABD_i", "_DOs_", "_Axl_", "vSPNs", "periphery"];

export class TwinBrain {
  constructor(payload, { learning = false } = {}) {
    this.payload = payload;
    this.halves = { left: new SettlingBrain(payload), right: new SettlingBrain(payload) };
    this.n = this.halves.left.n;
    this.steps = 0;
    this.learning = false; this.lessons = 0;
    if (learning) this.setLearning(true);
  }
  /** Learning on: both halves start at LEARN.start of the selected gain with every synapse plastic; off: both
   *  halves are the compiled net at the selected gain, as exported. Either way the live state is kept. */
  setLearning(on) {
    this.learning = !!on;
    for (const side of SIDES) {
      const b = this.halves[side];
      if (this.learning) { b.enableLearning(); b.setGain(LEARN.start * this.payload.gain); }
      else { b.enableLearning(); b.efficacy.set(b.efficacy0 || b.sign); b.bias.fill(0); b.mass0 = null; b.setGain(this.payload.gain); }
    }
    this.lessons = 0;
  }
  /** One lesson for one half toward `target` (one activation per neuron). Returns the engine's report. */
  /** How far the synapses have moved from their measured strengths: the mean |efficacy - 1| over both halves (0 with learning off). */
  departure() {
    let sum = 0, n = 0;
    for (const side of ["left", "right"]) { const b = this.halves[side]; if (!b.efficacy) continue; for (let e = 0; e < b.edges; e++) sum += Math.abs(Math.abs(b.efficacy[e]) - 1); n += b.edges; }
    return n ? sum / n : 0;
  }
  lesson(side, target) {
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
