// The body of the larva: discrete swimming bouts, water drag, a slow sink, glass walls that
// startle. Plain numbers only, no three.js, so node can test it: node tests/body.mjs.
//
// Units: millimetres, seconds; accelerations in mm/s^2. Frames. World: x along the long glass,
// y along the short glass, z up, origin at a floor corner of the tank. Body: x forward through
// the snout, y left, z up. heading is the yaw about world z, positive turns left; pitch is
// positive nose up; roll is right-handed about the body's x.
//
// A larva swims in bouts: 100 to 300 ms of tail beating at 30 to 60 Hz, a thrust impulse, then a
// glide that the drag ends within about half a second; bouts repeat about once a second. The
// brain commands a bout type, a side and a vigour (command()); the body shapes the thrust, the
// yaw and the tail, and reports its state with the vestibular quantities (state()).

export const TANK = [20, 10, 10];      // mm, the inside of the glass: x by y by z
export const WATER = 9.0;              // mm, the water surface above the floor
export const LENGTH = 4.0;             // mm, snout to tail tip
export const SNOUT = 1.3;              // mm, the snout ahead of the body centre
export const HALF_HEIGHT = 0.3;        // mm, half the body height: the floor contact
export const MARGIN = 0.25;            // mm, the body's clearance from the glass
export const DT = 0.001;               // s, physics substep
export const DRAG_LINEAR = 8.0;        // 1/s, viscous drag over mass along the body
export const DRAG_QUAD = 0.4;          // 1/mm, inertial drag over mass along the body
export const DRAG_SIDE = 4.0;          // drag across the body relative to the drag along it
export const SINK = 0.2;               // mm/s, the glide's slow sink: a little denser than water
export const SINK_ACCEL = DRAG_SIDE * DRAG_LINEAR * SINK;  // mm/s^2, the net downward pull
export const RESTITUTION = 0.3;        // the bounce off the glass
export const STARTLE_SPEED = 2.0;      // mm/s, a wall hit faster than this startles
export const STARTLE_COOLDOWN = 0.3;   // s, between two startles
export const FLOOR_FRICTION = 20.0;    // 1/s, a larva resting on the floor does not slide
export const TAIL_SEGMENTS = 12;
export const EYE_RANGE = [-30, 40];    // degrees per eye, positive converges toward the snout
export const BOUT_TYPES = ["scoot", "turn", "jturn", "cstart", "rest"];

// The bouts. Ranges run from vigour 0 to vigour 1 (duration, frequency, peak speed) and from
// |direction| 0 to 1 (yaw). turn: the window after the latency in which the yaw happens.
// amplitude: the tail beat for drawing, 0 to 1. curve: the one-sided bend at the peak yaw rate.
export const BOUTS = {
  scoot: { duration: [0.12, 0.30], frequency: [30, 60], peak: [5, 20], yaw: [0, 10], latency: 0.020, turn: 0.10, amplitude: 0.55, curve: 0.3 },
  turn: { duration: [0.15, 0.25], frequency: [30, 50], peak: [4, 12], yaw: [20, 60], latency: 0.020, turn: 0.10, amplitude: 0.5, curve: 0.7 },
  jturn: { duration: [0.15, 0.25], frequency: [25, 40], peak: [2, 5], yaw: [10, 30], latency: 0.020, turn: 0.12, amplitude: 0.3, curve: 0.5 },
  cstart: { duration: [0.10, 0.20], frequency: [50, 60], peak: [40, 100], yaw: [90, 180], latency: 0.004, turn: 0.020, amplitude: 0.9, curve: 1.0 },
};

export const PI = Math.PI, TWO_PI = 2 * Math.PI, DEG = Math.PI / 180;

export function wrap(a) { a = (a + PI) % TWO_PI; if (a < 0) a += TWO_PI; return a - PI; }
export function clamp(x, lo, hi) { return x < lo ? lo : x > hi ? hi : x; }
export function lerp(range, u) { return range[0] + (range[1] - range[0]) * u; }
const num = (x, fallback) => { x = Number(x); return Number.isFinite(x) ? x : fallback; };

// A small seeded generator, so a seed replays a life.
export function mulberry32(seed) {
  let a = (seed >>> 0) || 1;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Where a tap on the glass comes from: -1 the pane at x = 0, +1 the pane at x = TANK[0].
export function tapPosition(side) {
  return [side < 0 ? 0 : TANK[0], TANK[1] / 2, WATER / 2];
}

// The body-to-world rotation, row major: yaw about z, then pitch (nose up), then roll.
export function rotation(heading, pitch, roll) {
  const cy = Math.cos(heading), sy = Math.sin(heading), cp = Math.cos(pitch), sp = Math.sin(pitch), cr = Math.cos(roll), sr = Math.sin(roll);
  return [
    cy * cp, -sy * cr - cy * sp * sr, sy * sr - cy * sp * cr,
    sy * cp, cy * cr - sy * sp * sr, -cy * sr - sy * sp * cr,
    sp, cp * sr, cp * cr,
  ];
}

// The thrust amplitude that brings the forward speed from v0 to `peak` under the drag, by
// bisection on the one-dimensional glide equation with the bout's envelope.
export function thrustFor(peak, T, v0 = 0) {
  if (peak <= v0) return 0;
  const n = Math.max(8, Math.ceil(T / 0.002)), h = T / n;
  let lo = 0, hi = 50000;
  for (let i = 0; i < 30; i++) {
    const A = 0.5 * (lo + hi);
    let v = v0, vmax = v0;
    for (let k = 0; k < n; k++) {
      const env = Math.sin(PI * (k + 0.5) * h / T);
      v += h * (A * env - DRAG_LINEAR * v - DRAG_QUAD * v * v);
      if (v > vmax) vmax = v;
    }
    if (vmax > peak) hi = A; else lo = A;
  }
  return 0.5 * (lo + hi);
}

// ---------------------------------------------------------------------------------------------

export class Body {
  constructor(seed = 1, position = [TANK[0] / 2, TANK[1] / 2, WATER / 2], heading = 0) {
    this.rng = mulberry32(seed);
    this.reset(position, heading);
  }

  reset(position = [TANK[0] / 2, TANK[1] / 2, WATER / 2], heading = 0) {
    this.p = [position[0], position[1], position[2]];
    this.v = [0, 0, 0];
    this.heading = wrap(heading); this.pitch = 0; this.roll = 0;
    this.rates = [0, 0, 0];           // rad/s, about body x (roll), y (pitch), z (yaw)
    this.accel = [0, 0, 0];           // mm/s^2, in the body frame
    this.eyeLeft = 0; this.eyeRight = 0;
    this.tailPhase = 0; this.tailAmplitude = 0; this.tailCurvature = 0;
    this.bout = null; this.bouts = 0; this.lastBout = null;
    this.t = 0; this.steps = 0;
    this.onFloor = false; this.wallHit = null; this.startled = -Infinity;
  }

  // A command from the brain: {type, direction: -1..+1, vigour: 0..1, climb: -1..+1}.
  // type: scoot, turn, jturn, cstart or rest. direction: the side and, by its magnitude, the yaw.
  // A bout runs to its end; only an escape interrupts one. Returns whether a bout started.
  command(c) {
    if (!c || c.type == null || c.type === "rest") return false;
    const spec = BOUTS[c.type];
    if (!spec) throw new Error(`unknown bout type: ${c.type}`);
    if (this.bout && c.type !== "cstart") return false;
    const direction = clamp(num(c.direction, 0), -1, 1);
    const vigour = clamp(num(c.vigour, 0.5), 0, 1);
    const climb = clamp(num(c.climb, 0), -1, 1);
    let side = Math.sign(direction);
    if (side === 0) side = this.rng() < 0.5 ? -1 : 1;
    const yaw = side * lerp(spec.yaw, Math.abs(direction)) * DEG;
    return this._begin(c.type, yaw, vigour, climb);
  }

  // Eye angles in degrees, positive converging toward the snout.
  eyes(angles) {
    if (!angles) return;
    if (angles.left != null) this.eyeLeft = clamp(num(angles.left, 0), EYE_RANGE[0], EYE_RANGE[1]);
    if (angles.right != null) this.eyeRight = clamp(num(angles.right, 0), EYE_RANGE[0], EYE_RANGE[1]);
  }

  _begin(type, yaw, vigour, climb) {
    const spec = BOUTS[type];
    const jitter = () => 1 + 0.1 * (2 * this.rng() - 1);
    const T = lerp(spec.duration, vigour) * jitter();
    const frequency = lerp(spec.frequency, vigour) * jitter();
    const peak = lerp(spec.peak, vigour) * jitter();
    const turn = Math.min(spec.turn, T);
    const R = rotation(this.heading, this.pitch, this.roll);
    const forward = R[0] * this.v[0] + R[3] * this.v[1] + R[6] * this.v[2];
    this.bout = {
      type, t: 0, T, latency: spec.latency, frequency, peak, yaw, climb, vigour, turn,
      omega: yaw * PI / (2 * turn), A: thrustFor(peak, T, Math.max(0, forward)),
      amplitude: spec.amplitude, curve: spec.curve,
    };
    this.bouts++;
    this.lastBout = { type, time: this.t, yaw, peak, duration: T, vigour, climb };
    return true;
  }

  // The reflex at the glass: an escape turned toward the inside of the tank.
  _startle(axis, side) {
    const inward = Math.atan2(axis === 1 ? -side : 0, axis === 0 ? -side : 0);
    const delta = wrap(inward - this.heading);
    let sign = Math.sign(delta);
    if (sign === 0) sign = this.rng() < 0.5 ? -1 : 1;
    const yaw = sign * Math.max(90 * DEG, Math.abs(delta));
    this._begin("cstart", yaw, 0.15 + 0.1 * this.rng(), 0);
    this.startled = this.t;
  }

  step(dt) {
    if (!(dt > 0)) return;
    const n = Math.max(1, Math.ceil(dt / DT)), h = dt / n;
    for (let i = 0; i < n; i++) this._substep(h);
  }

  _substep(h) {
    const B = this.bout;
    let thrust = 0, yawRate = 0, pitchWant = 0, amp = 0, curve = 0, active = false;
    if (B) {
      B.t += h;
      const t = B.t - B.latency;
      if (t >= 0) {
        if (t < B.T) {
          active = true;
          const env = Math.sin(PI * t / B.T);
          thrust = B.A * env;
          amp = B.amplitude * Math.min(1, t / 0.02, (B.T - t) / 0.04);
          this.tailPhase += TWO_PI * B.frequency * h;
          pitchWant = 0.5 * B.climb;
        }
        if (t < B.turn) {
          const s = Math.sin(PI * t / B.turn);
          yawRate = B.omega * s;
          curve = B.curve * Math.sign(B.yaw) * s;
        }
        if (t >= B.T) this.bout = null;
      }
    }
    if (this.tailPhase > TWO_PI) this.tailPhase -= TWO_PI;
    const kt = Math.min(1, h / 0.01);
    this.tailAmplitude += (amp - this.tailAmplitude) * kt;
    this.tailCurvature += (curve - this.tailCurvature) * kt;

    // attitude: the yaw integrates the bout's rate; the pitch follows the climb and levels out
    // in the glide; the roll wobbles with the tail beat
    const p0 = this.pitch, r0 = this.roll;
    this.heading = wrap(this.heading + yawRate * h);
    this.pitch += (pitchWant - this.pitch) * (1 - Math.exp(-h / (active ? 0.08 : 0.4)));
    const rollWant = 0.1 * this.tailAmplitude * Math.sin(this.tailPhase);
    this.roll += (rollWant - this.roll) * (1 - Math.exp(-h / 0.02));
    this.rates[0] = (this.roll - r0) / h; this.rates[1] = (this.pitch - p0) / h; this.rates[2] = yawRate;

    // forces per mass in the body frame: thrust forward, drag against the water, more across
    const R = rotation(this.heading, this.pitch, this.roll), v = this.v;
    const ux = R[0] * v[0] + R[3] * v[1] + R[6] * v[2];
    const uy = R[1] * v[0] + R[4] * v[1] + R[7] * v[2];
    const uz = R[2] * v[0] + R[5] * v[1] + R[8] * v[2];
    const s = Math.sqrt(ux * ux + uy * uy + uz * uz);
    const k = DRAG_LINEAR + DRAG_QUAD * s;
    const ax = thrust - k * ux, ay = -DRAG_SIDE * k * uy, az = -DRAG_SIDE * k * uz;
    let wx = R[0] * ax + R[1] * ay + R[2] * az;
    let wy = R[3] * ax + R[4] * ay + R[5] * az;
    let wz = R[6] * ax + R[7] * ay + R[8] * az - SINK_ACCEL;
    if (this.onFloor && !active) { wx -= FLOOR_FRICTION * v[0]; wy -= FLOOR_FRICTION * v[1]; }
    const v0x = v[0], v0y = v[1], v0z = v[2];
    v[0] += wx * h; v[1] += wy * h; v[2] += wz * h;
    this.p[0] += v[0] * h; this.p[1] += v[1] * h; this.p[2] += v[2] * h;
    this._contacts(R);

    // the accelerometer: the change of velocity in the body frame
    const dx = (v[0] - v0x) / h, dy = (v[1] - v0y) / h, dz = (v[2] - v0z) / h;
    this.accel[0] = R[0] * dx + R[3] * dy + R[6] * dz;
    this.accel[1] = R[1] * dx + R[4] * dy + R[7] * dz;
    this.accel[2] = R[2] * dx + R[5] * dy + R[8] * dz;
    this.t += h; this.steps++;
  }

  _contacts(R) {
    const p = this.p, v = this.v;
    // the floor and the surface hold the fish without a startle
    this.onFloor = false;
    if (p[2] < HALF_HEIGHT) { p[2] = HALF_HEIGHT; if (v[2] < 0) v[2] = 0; this.onFloor = true; }
    if (p[2] > WATER - HALF_HEIGHT) { p[2] = WATER - HALF_HEIGHT; if (v[2] > 0) v[2] = 0; }
    // the four panes: the snout and the body centre stay inside; a fast hit bounces and startles
    for (let axis = 0; axis < 2; axis++) {
      const f = axis === 0 ? R[0] : R[3];
      const snout = p[axis] + SNOUT * f, centre = p[axis];
      const low = Math.min(snout, centre), high = Math.max(snout, centre);
      let side = 0;
      if (low < MARGIN) { p[axis] += MARGIN - low; side = -1; }
      else if (high > TANK[axis] - MARGIN) { p[axis] -= high - (TANK[axis] - MARGIN); side = 1; }
      if (side === 0) continue;
      const into = v[axis] * side;
      if (into > 0) v[axis] = -RESTITUTION * v[axis];
      this.wallHit = { axis, side, time: this.t, speed: Math.max(0, into) };
      const B = this.bout;
      const escaping = B && B.type === "cstart" && B.t < B.latency + B.turn;
      if (into > STARTLE_SPEED && this.t - this.startled > STARTLE_COOLDOWN && !escaping) this._startle(axis, side);
    }
  }

  speed() { const v = this.v; return Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]); }

  // Everything FishMesh.update takes, and the senses the brain reads.
  state() {
    const B = this.bout, p = this.p, v = this.v, R = rotation(this.heading, this.pitch, this.roll);
    const speed = this.speed();
    return {
      time: this.t,
      position: [p[0], p[1], p[2]], velocity: [v[0], v[1], v[2]], speed,
      heading: this.heading, pitch: this.pitch, roll: this.roll,
      eyeLeft: this.eyeLeft, eyeRight: this.eyeRight,
      tailPhase: this.tailPhase, tailAmplitude: this.tailAmplitude, tailCurvature: this.tailCurvature,
      bout: B ? { type: B.type, t: B.t, duration: B.T, latency: B.latency, yaw: B.yaw, peak: B.peak, climb: B.climb, vigour: B.vigour } : null,
      busy: B !== null, bouts: this.bouts, lastBout: this.lastBout ? { ...this.lastBout } : null,
      onFloor: this.onFloor, wallHit: this.wallHit ? { ...this.wallHit } : null, startled: this.startled,
      senses: {
        angularVelocity: [this.rates[0], this.rates[1], this.rates[2]],
        acceleration: [this.accel[0], this.accel[1], this.accel[2]],
        up: [R[6], R[7], R[8]],
        speed, tailPhase: this.tailPhase,
      },
    };
  }
}

// ---------------------------------------------------------------------------------------------
// The hand-written pilot: routine behaviour from the senses alone, the control condition for
// the brain. Bouts every one to two seconds with small turns, J-turns toward the nearest prey
// within 3 mm with converged eyes, an escape away from a tap, the optomotor following of
// moving stripes, a turn away from the glass ahead, and a slow pull toward the lamp.
//
// world: { prey: [{x, y, z}], tapSide: -1 | 0 | +1, tapAge: s, stripes: {on, direction, speed},
//          light: {on, x, y, z} }, as senses.js reads it.

export class Instincts {
  constructor(seed = 1) {
    this.rng = mulberry32(seed);
    this.clock = 0;
    this.next = 0.5 + this.rng();
    this.tapAnswered = false;
    this.mode = "routine";
    this.decisions = 0;
  }

  // The command for this moment, or null, with the eye angles and the mode of behaviour.
  decide(state, world = {}, dt = 0) {
    this.clock += dt;
    const rng = this.rng, [x, y, z] = state.position, h = state.heading;
    const bearingTo = (q) => wrap(Math.atan2(q[1] - y, q[0] - x) - h);
    let command = null, eyes = { left: 0, right: 0 }, mode = "routine";

    // a tap on the glass: an escape away from it, once per tap, interrupting anything
    const tapSide = Number(world.tapSide) || 0, tapAge = Number(world.tapAge) || 0;
    if (tapSide === 0 || tapAge > 0.3) this.tapAnswered = false;
    if (tapSide !== 0 && tapAge <= 0.1 && !this.tapAnswered) {
      this.tapAnswered = true;
      const away = wrap(bearingTo(tapPosition(tapSide)) + PI);
      const m = Math.max(90 * DEG, Math.abs(away));
      const side = away === 0 ? (rng() < 0.5 ? -1 : 1) : Math.sign(away);
      command = { type: "cstart", direction: side * clamp((m - 90 * DEG) / (90 * DEG), 0, 1), vigour: 0.6 + 0.4 * rng() };
      this.next = this.clock + 1 + rng();
      this.mode = "escape"; this.decisions++;
      return { command, eyes, mode: this.mode };
    }

    // the nearest prey within 3 mm is hunted with converged eyes
    let prey = null, preyD = Infinity;
    for (const q of world.prey || []) {
      const d = Math.hypot(q.x - x, q.y - y, (q.z ?? z) - z);
      if (d < preyD) { preyD = d; prey = q; }
    }
    const hunting = prey !== null && preyD < 3;
    if (hunting) { eyes = { left: 30, right: 30 }; mode = "hunt"; }
    if (state.busy || this.clock < this.next) { this.mode = mode; return { command: null, eyes, mode }; }

    if (hunting) {
      const b = bearingTo([prey.x, prey.y]), dxy = Math.hypot(prey.x - x, prey.y - y);
      const climb = clamp(Math.atan2((prey.z ?? z) - z, Math.max(dxy, 0.1)) / 0.5, -1, 1);
      if (Math.abs(b) > 10 * DEG) command = { type: "jturn", direction: Math.sign(b) * clamp((Math.abs(b) - 10 * DEG) / (20 * DEG), 0, 1), vigour: 0.3 + 0.3 * rng(), climb };
      else if (preyD > 1.0) command = { type: "scoot", direction: 0.3 * b / (10 * DEG), vigour: 0.1, climb };
      else command = { type: "scoot", direction: 0.3 * b / (10 * DEG), vigour: 0.35, climb };   // the capture strike
      this.next = this.clock + 0.4 + 0.4 * rng();
    }

    // the stripes: turn with their motion, then swim with it
    const st = world.stripes;
    if (!command && st && st.on) {
      const sv = (Number(st.direction) || 1) * (Number(st.speed) || 0);
      const fx = sv - state.velocity[0], fy = -state.velocity[1];
      const ff = fx * Math.cos(h) + fy * Math.sin(h), fl = -fx * Math.sin(h) + fy * Math.cos(h);
      if (Math.hypot(ff, fl) > 0.5) {
        mode = "optomotor";
        const a = Math.atan2(fl, ff);
        if (Math.abs(a) > 25 * DEG) command = { type: "turn", direction: Math.sign(a) * clamp((Math.abs(a) - 20 * DEG) / (40 * DEG), 0.05, 1), vigour: 0.3 };
        else command = { type: "scoot", direction: 0.5 * clamp(a / (25 * DEG), -1, 1), vigour: clamp(Math.abs(sv) / 20, 0.1, 0.8) };
        this.next = this.clock + 0.5 + 0.5 * rng();
      }
    }

    // routine: a scoot or a turn, up from the floor, down from the surface, away from the glass
    if (!command) {
      let climb = 0;
      if (z < 2.5) climb = 0.5 + 0.5 * rng(); else if (z > WATER - 1.2) climb = -0.4;
      const cx = Math.cos(h), cy = Math.sin(h), sx = x + SNOUT * cx, sy = y + SNOUT * cy;
      let ahead = Infinity;
      if (cx > 1e-6) ahead = Math.min(ahead, (TANK[0] - sx) / cx); else if (cx < -1e-6) ahead = Math.min(ahead, -sx / cx);
      if (cy > 1e-6) ahead = Math.min(ahead, (TANK[1] - sy) / cy); else if (cy < -1e-6) ahead = Math.min(ahead, -sy / cy);
      if (ahead < 2.5) {
        const b = bearingTo([TANK[0] / 2, TANK[1] / 2]);
        command = { type: "turn", direction: (b === 0 ? 1 : Math.sign(b)) * clamp(Math.abs(b) / (60 * DEG), 0.3, 1), vigour: 0.2 + 0.2 * rng(), climb };
      } else {
        const L = world.light;
        let lightSide = 0, lightBearing = 0;
        if (L && L.on) {
          lightBearing = bearingTo([Number(L.x) || 0, Number(L.y) || 0]);
          if (Math.abs(lightBearing) > 40 * DEG && rng() < 0.5) lightSide = Math.sign(lightBearing);
        }
        const r = rng();
        if (lightSide !== 0) command = { type: "turn", direction: lightSide * clamp(Math.abs(lightBearing) / (60 * DEG), 0.2, 1), vigour: 0.2 + 0.3 * rng(), climb };
        else if (r < 0.6 || climb > 0) command = { type: "scoot", direction: 0.6 * (rng() - 0.5), vigour: 0.2 + 0.5 * rng(), climb };
        else command = { type: "turn", direction: (rng() < 0.5 ? -1 : 1) * (0.2 + 0.8 * rng()), vigour: 0.2 + 0.3 * rng(), climb };
      }
      this.next = this.clock + 1 + rng();
    }
    this.mode = mode; this.decisions++;
    return { command, eyes, mode };
  }

  // Decides and applies: the eyes, then the command. Returns the decision with `issued`.
  drive(body, world, dt) {
    const d = this.decide(body.state(), world, dt);
    body.eyes(d.eyes);
    d.issued = d.command ? body.command(d.command) : false;
    return d;
  }
}
