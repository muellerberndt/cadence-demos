// The body of a Platynereis dumerilii larva at three days: a ciliated swimmer at low Reynolds
// number, drawn 2 mm long in the fish's tank. Plain numbers only, no three.js, so node can
// test it: node tests/larva.mjs.
//
// Units: millimetres, seconds, radians at the drawn size; SCALE turns the real larva's
// quantities into drawn ones. World: x along the long glass, y along the short glass, z up,
// origin at a floor corner of the tank (body.js). heading is the yaw of the course about world
// z, positive turns left; pitch is positive nose up; roll is the spin about the body's own
// axis, right-handed about x forward.
//
// The larva swims by cilia, not by a tail: the prototroch, a band of 23 multiciliated cells
// around its middle, and the smaller paratroch bands push it along its body axis at about
// 1 mm/s real size while the body spins slowly about that axis, so it swims in a helix. At low
// Reynolds number there is no coasting: the velocity is proportional to the ciliary beat now
// and vanishes when the cilia stop. The brain commands a ciliary drive per side, an arrest, a
// longitudinal muscle contraction per side and the parapodial elevation (command()); the body
// turns them into motion and reports its state with the senses (state()).
//
// The helix: the body axis is tilted by HELIX_ANGLE from the course and the spin sweeps the
// tilt around, so the centre traces a helix about the course line. The course is what the
// brain steers: a left-right difference of the ciliary drive, or of the longitudinal muscles,
// turns it about world z, the stronger ciliary side and the contracted side leading the turn
// (declared signs: the contracted side pulls the body round; the ciliary sign is the simplest
// wiring for the brain, light on one eye driving that side's cilia and turning toward it). A
// steady difference therefore turns the course steadily, and the eyes read the course, not
// the spin (larva_senses.js). The real larva steers by modulating its beat in phase with the
// spin; the steady turn is the declared abstraction of that.
import { TANK, WATER, PI, TWO_PI, DEG, wrap, clamp, mulberry32, rotation } from "./body.js";
import { senseLarva, MECHANICAL_DECAY } from "./larva_senses.js";

export { TANK, WATER, DEG, wrap, clamp, mulberry32 };

export const REAL_LENGTH = 0.3;                  // mm, the larva at three days
export const LENGTH = 2.0;                       // mm, drawn, so it shows in the tank
export const SCALE = LENGTH / REAL_LENGTH;       // drawn mm per real mm
export const HALF_LENGTH = LENGTH / 2;           // mm, the body centre to the snout
export const REAL_SPEED = 1.0;                   // mm/s, real, at full ciliary drive
export const REAL_SINK = 0.1;                    // mm/s, real, an arrested larva sinking
export const SPEED = REAL_SPEED * SCALE;         // mm/s, drawn
export const SINK = REAL_SINK * SCALE;           // mm/s, drawn
export const TURN = 1.5;                         // rad/s at a full left-right ciliary difference: declared
export const TURN_MUSCLE = 3.0;                  // rad/s at a full one-sided longitudinal contraction: declared
export const ROLL = TWO_PI * 1.0;                // rad/s, the spin at full drive: about one turn per second
export const HELIX_ANGLE = 20 * DEG;             // the body axis's tilt from the course that the spin sweeps into a helix
export const PITCH_UP = 15 * DEG;                // the course's nose-up tilt at full drive: the larva swims upward
export const PITCH_TAU = 0.8;                    // s, the course pitch's relaxation
export const MARGIN = 1.1;                       // mm, the body centre's distance from a pane at a reflection
export const CLEARANCE = 0.6;                    // mm, the body centre's distance from the floor and the surface
export const TAP_END = 0.5;                      // s, after which a tap is over
export const DT = 0.005;                         // s, physics substep
export const COMMANDS = ["ciliaLeft", "ciliaRight", "arrest", "muscleLeft", "muscleRight", "parapodia"];

const num = (x, fallback) => { x = Number(x); return Number.isFinite(x) ? x : fallback; };

// ---------------------------------------------------------------------------------------------

export class LarvaBody {
  constructor(seed = 1, position = [TANK[0] / 2, TANK[1] / 2, WATER / 2], heading = 0) {
    this.rng = mulberry32(seed);
    this.world = { light: { on: false, x: TANK[0] / 2, y: TANK[1] / 2, z: TANK[2] + 3 }, uv: null, tapSide: 0, tapAge: 0 };
    this.reset(position, heading);
  }

  reset(position = [TANK[0] / 2, TANK[1] / 2, WATER / 2], heading = 0) {
    this.p = [position[0], position[1], position[2]];
    this.v = [0, 0, 0];
    this.heading = wrap(heading); this.pitch = 0; this.roll = 0;
    this.axis = [Math.cos(this.heading), Math.sin(this.heading), 0];
    this.cmd = { ciliaLeft: 0, ciliaRight: 0, arrest: 0, muscleLeft: 0, muscleRight: 0, parapodia: 0 };
    this.swim = 0; this.turnRate = 0; this.sinking = false;
    this.tapSide = 0; this.tapAge = 0;
    this.t = 0; this.steps = 0;
    this.onFloor = false; this.atSurface = false; this.wallHit = null;
  }

  // The world the senses read: the lamp, the ultraviolet, a tap. Fields given replace the old.
  setWorld(world = {}) {
    if (world.light) this.world.light = { ...this.world.light, ...world.light };
    if ("uv" in world) this.world.uv = world.uv == null ? null : clamp(num(world.uv, 0), 0, 1);
    if (world.tapSide != null) { this.world.tapSide = Number(world.tapSide) < 0 ? -1 : Number(world.tapSide) > 0 ? 1 : 0; this.world.tapAge = Math.max(0, num(world.tapAge, 0)); }
    return this.world;
  }

  // A tap on the glass: "left" or -1 the pane at x = 0, "right" or +1 the pane at x = TANK[0].
  tap(side) {
    this.tapSide = side === "left" || Number(side) < 0 ? -1 : 1;
    this.tapAge = 0;
    return { side: this.tapSide, time: this.t };
  }

  // A command from the brain: {ciliaLeft, ciliaRight, arrest, muscleLeft, muscleRight,
  // parapodia}, each in [0, 1]. Fields given replace the old ones and persist until changed.
  // Returns the commands in force.
  command(c) {
    if (c) for (const k of COMMANDS) { if (c[k] == null) continue; const v = num(c[k], NaN); if (Number.isFinite(v)) this.cmd[k] = clamp(v, 0, 1); }
    return { ...this.cmd };
  }

  step(dt) {
    if (!(dt > 0)) return;
    const n = Math.max(1, Math.ceil(dt / DT)), h = dt / n;
    for (let i = 0; i < n; i++) this._substep(h);
  }

  _substep(h) {
    const c = this.cmd;
    const drive = 0.5 * (c.ciliaLeft + c.ciliaRight) * (1 - c.arrest);
    this.swim = SPEED * drive;
    this.turnRate = TURN * (c.ciliaLeft - c.ciliaRight) + TURN_MUSCLE * (c.muscleLeft - c.muscleRight);
    this.sinking = c.arrest > 0.5 || Math.max(c.muscleLeft, c.muscleRight) > 0.5;

    // the course: the turn about world z, the nose rising with the drive, the spin with it
    this.heading = wrap(this.heading + this.turnRate * h);
    this.pitch += (PITCH_UP * drive - this.pitch) * (1 - Math.exp(-h / PITCH_TAU));
    this.roll = wrap(this.roll + ROLL * drive * h);

    // the body axis: the course tilted by the helix angle in the direction the spin points
    const ca = Math.cos(HELIX_ANGLE), sa = Math.sin(HELIX_ANGLE), cr = Math.cos(this.roll), sr = Math.sin(this.roll);
    const ux = ca, uy = -sa * sr, uz = sa * cr;
    const R = rotation(this.heading, this.pitch, 0), a = this.axis;
    a[0] = R[0] * ux + R[1] * uy + R[2] * uz;
    a[1] = R[3] * ux + R[4] * uy + R[5] * uz;
    a[2] = R[6] * ux + R[7] * uy + R[8] * uz;

    // the velocity is the cilia's push along the axis now, plus the sink: no inertia
    const v = this.v, p = this.p;
    v[0] = this.swim * a[0]; v[1] = this.swim * a[1]; v[2] = this.swim * a[2] - (this.sinking ? SINK : 0);
    p[0] += v[0] * h; p[1] += v[1] * h; p[2] += v[2] * h;
    this._contacts();

    if (this.tapSide !== 0) { this.tapAge += h; if (this.tapAge > TAP_END) { this.tapSide = 0; this.tapAge = 0; } }
    this.t += h; this.steps++;
  }

  _contacts() {
    const p = this.p, v = this.v;
    // the floor and the surface hold the larva
    this.onFloor = false; this.atSurface = false;
    if (p[2] < CLEARANCE) { p[2] = CLEARANCE; if (v[2] < 0) v[2] = 0; this.onFloor = true; }
    if (p[2] > WATER - CLEARANCE) { p[2] = WATER - CLEARANCE; if (v[2] > 0) v[2] = 0; this.atSurface = true; }
    // the four panes reflect the course: the centre stays inside and a course into the pane
    // is mirrored
    for (let axis = 0; axis < 2; axis++) {
      let side = 0;
      if (p[axis] < MARGIN) { p[axis] = MARGIN; side = -1; }
      else if (p[axis] > TANK[axis] - MARGIN) { p[axis] = TANK[axis] - MARGIN; side = 1; }
      if (side === 0) continue;
      const along = axis === 0 ? Math.cos(this.heading) : Math.sin(this.heading);
      if (along * side > 0) {
        this.heading = wrap(axis === 0 ? PI - this.heading : -this.heading);
        this.wallHit = { axis, side, time: this.t };
      }
      if (v[axis] * side > 0) v[axis] = -v[axis];
    }
  }

  speed() { const v = this.v; return Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]); }

  // Everything LarvaMesh.update takes, and the senses the brain reads from the body's world.
  state() {
    const p = this.p, v = this.v, c = this.cmd, a = this.axis;
    const tap = this.tapSide !== 0 ? { tapSide: this.tapSide, tapAge: this.tapAge } : { tapSide: this.world.tapSide, tapAge: this.world.tapAge };
    const s = {
      time: this.t,
      position: [p[0], p[1], p[2]], velocity: [v[0], v[1], v[2]], speed: this.speed(), swim: this.swim,
      heading: this.heading, pitch: this.pitch, roll: this.roll, axis: [a[0], a[1], a[2]],
      turnRate: this.turnRate,
      cilia: { left: c.ciliaLeft, right: c.ciliaRight }, arrest: c.arrest,
      muscle: { left: c.muscleLeft, right: c.muscleRight }, parapodia: c.parapodia,
      sinking: this.sinking, onFloor: this.onFloor, atSurface: this.atSurface,
      wallHit: this.wallHit ? { ...this.wallHit } : null,
      tap: this.tapSide !== 0 ? { side: this.tapSide, age: this.tapAge } : null,
    };
    s.senses = senseLarva(s, { light: this.world.light, uv: this.world.uv, ...tap });
    return s;
  }
}

// ---------------------------------------------------------------------------------------------
// The hand-written pilot: routine behaviour from the senses alone, the control condition for
// the brain. The cilia beat with a random slow left-right difference renewed every one to
// three seconds; a lamp seen by one eye more than the other turns the course toward it; a tap
// on the glass arrests the cilia, contracts the longitudinal muscles and raises the parapodia
// for STARTLE_TIME, so the larva stops and sinks; ultraviolet near the surface arrests the
// cilia for a while, so the larva sinks away from it.

export const CRUISE = 0.75;          // the routine ciliary drive per side
export const WANDER = 0.4;           // the range of the random left-right difference
export const STEER = 1.5;            // ciliary difference per unit of eye difference
export const STARTLE_TIME = 0.4;     // s, the arrest and the contraction after a tap
export const UV_DIVE = 0.75;         // the cPRC level above which the larva arrests and sinks
export const DIVE_CALM = 2.0;        // s, after a dive, before the next one

export class LarvaPilot {
  constructor(seed = 1) {
    this.rng = mulberry32(seed);
    this.clock = 0;
    this.next = 0; this.bias = 0;
    this.until = 0; this.calm = 0;
    this.tapAnswered = false;
    this.mode = "swim";
    this.decisions = 0;
  }

  // The command for this moment from the body's senses.
  decide(state, dt = 0) {
    this.clock += dt;
    const s = state.senses || {}, rng = this.rng;
    const mech = num(s.mechanical, 0);
    if (mech < 0.05) this.tapAnswered = false;
    if (mech > 0.3 && !this.tapAnswered) { this.tapAnswered = true; this.mode = "startle"; this.until = this.clock + STARTLE_TIME; this.decisions++; }
    if (this.mode === "startle") {
      if (this.clock < this.until) return { ciliaLeft: 0, ciliaRight: 0, arrest: 1, muscleLeft: 1, muscleRight: 1, parapodia: 1 };
      this.mode = "swim";
    }
    if (this.mode === "dive") {
      if (this.clock < this.until) return { ciliaLeft: 0, ciliaRight: 0, arrest: 1, muscleLeft: 0, muscleRight: 0, parapodia: 0 };
      this.mode = "swim"; this.calm = this.clock + DIVE_CALM;
    }
    if (num(s.cprc, 0) > UV_DIVE && this.clock >= this.calm) {
      this.mode = "dive"; this.until = this.clock + 0.5 + rng(); this.decisions++;
      return { ciliaLeft: 0, ciliaRight: 0, arrest: 1, muscleLeft: 0, muscleRight: 0, parapodia: 0 };
    }
    if (this.clock >= this.next) { this.bias = WANDER * (2 * rng() - 1); this.next = this.clock + 1 + 2 * rng(); this.decisions++; }
    let diff = this.bias, mode = "swim";
    const lit = num(s.eye_left, 0) - num(s.eye_right, 0) + 0.5 * (num(s.eyespot_left, 0) - num(s.eyespot_right, 0));
    if (Math.abs(lit) > 0.01) { diff = STEER * lit; mode = "steer"; }
    this.mode = mode;
    return { ciliaLeft: clamp(CRUISE + diff / 2, 0, 1), ciliaRight: clamp(CRUISE - diff / 2, 0, 1), arrest: 0, muscleLeft: 0, muscleRight: 0, parapodia: 0 };
  }

  // Decides and applies. Returns the command with the mode of behaviour.
  drive(body, dt) {
    const d = this.decide(body.state(), dt);
    body.command(d);
    d.mode = this.mode;
    return d;
  }
}
