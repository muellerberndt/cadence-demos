// Two halves of the brainstem from one reconstruction: the measured side and its mirror.
// The data covers one side of the hindbrain; the other half is a copy, and the mutual
// inhibition between the halves is absent from the data. Each half integrates its own
// direction. Pure logic, no worker API, so node can test it.
import { SettlingBrain } from "./brain.js";

export const SIDES = ["left", "right"];
export const READOUTS = ["_Int_", "ABD_m", "ABD_i", "_DOs_", "_Axl_", "vSPNs", "periphery"];

export class TwinBrain {
  constructor(payload) {
    this.payload = payload;
    this.halves = { left: new SettlingBrain(payload), right: new SettlingBrain(payload) };
    this.n = this.halves.left.n;
    this.steps = 0;
  }
  /** Stimuli: {left: {population: level}, right: {population: level}}; levels in [0, 1]. */
  run(stimuli, steps) {
    const out = { steps: this.steps + steps, sides: {} };
    for (const side of SIDES) {
      const b = this.halves[side];
      b.clearStimuli();
      for (const [pop, level] of Object.entries((stimuli && stimuli[side]) || {})) if (level > 0) b.stimulate(pop, level);
      for (let k = 0; k < steps; k++) b.step();
      const readouts = {};
      for (const r of READOUTS) if (this.payload.populations[r]) readouts[r] = b.mean(r);
      out.sides[side] = { readouts, active: b.activeCount(0.05) };
    }
    this.steps += steps;
    return out;
  }
  activity(side) { return this.halves[side].s; }
  reset() { for (const side of SIDES) { this.halves[side].reset(); this.halves[side].clearStimuli(); } this.steps = 0; }
}
