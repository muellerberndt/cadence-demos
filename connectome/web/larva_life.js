// The larva's life: its senses land on the compiled connectome's sensory cells, the net
// settles, its effector cells' activity moves the body. One brain step per STEP_MS of the
// larva's time; nothing in between is a pilot.
import { LarvaBody } from "./larva_body.js";
import { stimuli, commands, READOUTS, STEP_MS, TAP_HOLD } from "./larva_dictionary.js";

export class LarvaLife {
  /** brain: a SettlingBrain on web/data/larva_brain.json (populations by name). */
  constructor(brain, seed = 1, position = [10, 5, 5], heading = 0) {
    this.brain = brain; this.body = new LarvaBody(seed, position, heading);
    this.world = { light: { on: false, x: 10, y: 5, z: 14 }, tapSide: 0, tapAge: 1, uv: 1 };
    this.body.setWorld(this.world);
    this.time = 0; this.clock = 0; this.steps = 0; this.senses = null; this.readouts = {}; this.command = commands({});
    this.brainOn = true; this.log = []; this.tapHeld = 0;
  }
  read() {
    const r = {};
    for (const k of READOUTS) { const m = this.brain.mean(k); if (Number.isFinite(m)) r[k] = m; }
    return r;
  }
  step(dt) {
    const state = this.body.state();
    this.clock += dt * 1000;
    if (this.clock >= STEP_MS) {
      this.clock -= STEP_MS; this.steps++;
      this.tapHeld = Math.max(this.tapHeld * TAP_HOLD, state.senses.mechanical);
      this.senses = { ...state.senses, mechanical: this.tapHeld };  // the body senses its world: eyes, eyespots, cPRC, pressure, the tap held by the receptors
      if (this.brainOn) {
        this.brain.clearStimuli();
        for (const [pop, level] of Object.entries(stimuli(this.senses))) this.brain.stimulate(pop, level);
        this.brain.step();
        this.readouts = this.read(); this.command = commands(this.readouts);
      } else {
        this.command = commands({});  // the cilia beat on their own, nothing steers
      }
      this.body.command(this.command);
      this.log.push([this.time, this.command.ciliaLeft, this.command.ciliaRight, this.command.arrest, this.senses.eye_left, this.senses.eye_right, this.senses.mechanical]);
      if (this.log.length > 1500) this.log.shift();
    }
    this.body.step(dt); this.time += dt;
    return state;
  }
  tap(side) { this.body.tap(side); }
  setLight(light) { Object.assign(this.world.light, light); this.body.setWorld({ light: this.world.light }); }
  setUv(uv) { this.world.uv = uv; this.body.setWorld({ uv }); }
}
