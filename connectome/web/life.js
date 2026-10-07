// The fish's life: the body under the pilot, the compiled brainstem fed by the dictionary,
// the eyes from the brain. One object the page steps at the frame rate; the brain runs one
// step per STEP_MS of fish time, synchronously (TwinBrain) or through the worker.
import { Body, Instincts } from "./body.js";
import { sense } from "./senses.js";
import { stimuli, gaze, eyeAngles, Saccades, STEP_MS, SACCADE_STEPS, LEARN, WORLDS, HUNT_SACCADE } from "./dictionary.js";

const fresh = () => ({ target: null, level: 0, since: 0, at: -1, landing: null, landLevel: 0, landSince: 0, landAt: -1 });

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
    // the synapses learning to hold the gaze (dictionary.js LEARN): per half, the target taken one second
    // after a saccade and the fixation since; the lessons taken, the last one, and a short log
    this.learning = { on: !!brain.learning, world: "still", lessons: 0, fixations: 0, last: null, log: [], sides: { left: fresh(), right: fresh() } };
  }
  /** Choose a declared activity-feedback condition; these are not rendered visual inputs. */
  setWorld(name) {
    if (!Object.hasOwn(WORLDS, name)) throw new Error(`no such world: ${name}`);
    if (name !== this.learning.world) {
      // A fixation belongs to the feedback condition in which it began. Switching the
      // lesson discards unfinished evidence, while retaining the acquired brain.
      this.learning.world = name;
      this._clearFixations();
    }
    return name;
  }
  _clearFixations() { this.learning.sides = { left: fresh(), right: fresh() }; this.turning = false; }
  /** Pause/resume plasticity in the same acquired brain. No lesson or weight is reset. */
  setLearning(on) {
    this.brain.setLearning(on);
    this.learning.on = !!on;
    this._clearFixations();
    return this.learning.on;
  }
  /** Explicit fresh learner, in the same body: restore starting relations and clear
   *  transient brain activity and pending lessons. Ordinary pause/resume never does this. */
  resetLearning() {
    this.brain.resetLearning(); this.brain.reset();
    this.learning = { on: true, world: this.learning.world, lessons: 0, fixations: 0, last: null, log: [], sides: { left: fresh(), right: fresh() } };
    this.sides = { left: null, right: null }; this.gaze = 0; this.burst = 0; this.turning = false;
    this.saccades.pending = 0; this.saccades.stepsLeft = 0; this.saccades.next = this.time + 3;
  }
  /** Both decisions read the same pre-lesson references, independent of iteration order. */
  _endFixations(why) {
    const levels = {};
    for (const side of ["left", "right"]) { const st = this.learning.sides[side]; levels[side] = st.target ? st.level : why === "limit" && st.landing ? st.landLevel : 0; }
    for (const side of ["left", "right"]) this._lesson(side, why, levels);
  }
  /** The slip of one half's fixation, and a lesson if it is worth one: the level must be held, the fixation
   *  undisturbed by a turn, and the slip beyond the dead zone. Clears that half's target. */
  _lesson(side, why, referenceLevels = null) {
    const L = this.learning, st = L.sides[side];
    if (!L.on || !this.brainOn) return null;
    // a quick phase means the eye ran on to its limit: that is a lesson however short the fixation, and if the burst's
    // transient has not passed yet the state the eye landed in is the target
    const limit = why === "limit", picked = st.target || (limit ? st.landing : null);
    if (!picked) return null;
    const level0 = st.target ? st.level : st.landLevel, since = st.target ? st.since : st.landSince;
    const fixation = this.time - since, level1 = this.brain.mean(side, LEARN.outputs), slip = level1 - level0;
    const ratio = level0 > 0 ? level1 / level0 : 0;
    // a saccade drives one half and silences the other: the half that carries the gaze, the one whose level is at least the
    // other's, is the one whose drift is the eye's; the silenced half's small level moves for its own reasons and teaches nothing
    const otherSide = side === "left" ? "right" : "left", other = L.sides[otherSide];
    const otherLevel = referenceLevels ? referenceLevels[otherSide] : other.target ? other.level : limit && other.landing ? other.landLevel : 0;
    const carries = level0 >= otherLevel;
    // The declared teacher compares internal activity with a fraction of its saved pattern,
    // or an amplified correction. The target mismatch must pass the dead zone.
    const w = WORLDS[L.world], wanted = w.k ? level1 + w.k * (level0 - level1) : w.m * level0, seen = level1 - wanted;
    const entry = { time: this.time, side, why, world: L.world, fixation, level0, level1, slip, drift: level0 > 0 ? slip / level0 : 0, seen: level0 > 0 ? seen / level0 : 0, hold: ratio > 0 && ratio < 1 ? -fixation / Math.log(ratio) : ratio >= 1 ? Infinity : 0, carries, taken: false, scaleStep: 0 };
    L.fixations++;
    if (carries && (limit ? seen > 0 : fixation >= LEARN.minFixation) && level0 >= LEARN.levelMin && Math.abs(seen) >= LEARN.deadZone * level0) {
      const free = this.brain.activity(side);
      const target = w.k ? Float64Array.from(free, (f, i) => f + w.k * (picked[i] - f)) : w.m === 1 ? picked : Float64Array.from(picked, (x) => w.m * x);
      const report = this.brain.lesson(side, target);
      entry.taken = true; entry.scaleStep = report.appliedScaleStep ?? report.scaleStep; entry.plusSteps = report.plusSteps; entry.minusSteps = report.minusSteps;
      L.lessons++; L.last = entry;
    }
    L.log.push(entry); if (L.log.length > 60) L.log.shift();
    L.sides[side] = fresh();
    return entry;
  }
  /** Advance by a small dt in seconds (the browser and assays use 0.01 s). */
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
      const wish = decision.command && decision.command.type === "jturn" ? HUNT_SACCADE * decision.command.direction : 0;
      const before = this.burst, quickBefore = this.saccades.quick;
      this.burst = this.saccades.tick(this.time, wish, this.gaze);
      const L = this.learning;
      if (L.on && this.brainOn) {
        if (this.burst !== 0 && before === 0) {  // a saccade begins: the fixations end, their lessons are taken, new targets are due after the burst
          const why = this.saccades.quick > quickBefore ? "limit" : "saccade";
          this._endFixations(why);
          for (const side of ["left", "right"]) { const st = L.sides[side]; st.landAt = this.steps + SACCADE_STEPS; st.at = st.landAt + LEARN.targetDelay; }
        }
        // a turn moves the eyes for the vestibular reason, not a slip: the fixation ends as the turn begins, what the eye saw up to then
        // is its lesson if it lasted long enough, and a new fixation begins once the eyes are still again
        if (Math.abs(yaw) > LEARN.turn) { if (!this.turning) this._endFixations("turn"); for (const side of ["left", "right"]) { L.sides[side].at = -1; L.sides[side].landAt = -1; } this.turning = true; }
        else if (this.turning) { this.turning = false; for (const side of ["left", "right"]) if (!L.sides[side].target && L.sides[side].at < 0) L.sides[side].at = this.steps + LEARN.targetDelay; }
      }
      if (this.brainOn) {
        const out = this.brain.run(stimuli({ saccade: this.burst, yawRate: yaw }), 1);
        this.sides = out.sides; this.gaze = gaze(out.sides, this.burst);
        const expired = L.on && ["left", "right"].some((side) => { const st = L.sides[side]; return st.target && this.time - st.since >= LEARN.maxFixation; });
        if (expired) this._endFixations("fixation");
        if (L.on) for (const side of ["left", "right"]) {
          const st = L.sides[side];
          if (st.landAt === this.steps) { st.landing = Float64Array.from(this.brain.activity(side)); st.landLevel = this.brain.mean(side, LEARN.outputs); st.landSince = this.time; st.landAt = -1; }
          if (st.at === this.steps) { st.target = Float64Array.from(this.brain.activity(side)); st.level = this.brain.mean(side, LEARN.outputs); st.since = this.time; st.at = -1; }
        }
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
