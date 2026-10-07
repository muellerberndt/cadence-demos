// The fish's life: the body under the pilot, the compiled brainstem fed by the dictionary,
// the eyes from the brain. One object the page steps at the frame rate; the brain runs one
// step per STEP_MS of fish time, synchronously (TwinBrain) or through the worker.
import { Body, Instincts } from "./body.js";
import { sense } from "./senses.js";
import { stimuli, gaze, eyeAngles, Saccades, STEP_MS } from "./dictionary.js";

export class Life {
  /** brain: an object with run(stimuli, steps) returning {sides} and activity(side); the twin. */
  constructor(brain, seed = 1) {
    this.brain = brain; this.seed = seed;
    this.body = new Body(seed); this.pilot = new Instincts(seed); this.saccades = new Saccades(seed);
    this.world = { prey: [], tapSide: 0, tapAge: 1, stripes: { on: false, direction: 1, speed: 0 }, light: { on: false, x: 0, y: 0, z: 0 } };
    this.time = 0; this.clock = 0; this.steps = 0; this.sides = { left: null, right: null };
    this.gaze = 0; this.burst = 0; this.vergence = 0; this.lastDecision = null; this.senses = null;
    this.brainOn = true;  // when off, the eyes follow the pilot alone: the control
    this.log = [];        // (time, gaze, burst, yawRate) rows for the strip chart
  }
  /** Advance the fish by dt seconds of its own time. */
  step(dt) {
    const state = this.body.state();
    this.world.tapAge += dt;
    const decision = this.pilot.decide(state, this.world, dt);
    this.lastDecision = decision;
    if (decision.command) this.body.command(decision.command);
    this.vergence = decision.eyes ? (decision.eyes.left + decision.eyes.right) / 2 : 0;
    this.clock += dt * 1000;
    if (this.clock >= STEP_MS) {
      this.clock -= STEP_MS; this.steps++;
      const yaw = state.senses.angularVelocity[2];
      const wish = decision.command && decision.command.type === "jturn" ? decision.command.direction : 0;
      this.burst = this.saccades.tick(this.time, wish);
      if (this.brainOn) {
        const out = this.brain.run(stimuli({ saccade: this.burst, yawRate: yaw }), 1);
        this.sides = out.sides; this.gaze = gaze(out.sides, this.burst);
      } else {
        this.gaze = 0;
      }
      this.senses = sense(state, this.world);
      this.log.push([this.time, this.gaze, this.burst, yaw]); if (this.log.length > 1500) this.log.shift();
    }
    this.body.eyes(eyeAngles(this.gaze, this.vergence));
    this.body.step(dt);
    this.time += dt;
    return state;
  }
  /** A saccade requested from outside (a button): -1 right .. +1 left. */
  requestSaccade(direction) { this.saccades.request(direction); }
  readouts(side) { return this.sides[side] ? this.sides[side].readouts : null; }
}
