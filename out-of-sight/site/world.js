// The scene: a plane, an arm, things and a camera with a blind spot.
//
// The geometry, the arm's kinematics, the camera's view, the ear's cue and the step are a port of
// the tracking chamber's world (benchmarks/tracking/world.py in the Cadence library);
// tests/parity.mjs replays steps recorded by the Python world, with the same draws, and checks
// every number. Everything lies in one plane, in metres and radians, one step every DT seconds.
// Thing 0 is the hand. A thing is in view where it lies in the camera's field and range, inside
// the plane, and the straight line from the camera to it crosses no occluding disc and no link
// of the arm. The ear hears a thing that sounds, in view or out of it: the direction to the thing
// and its distance, each with noise.

export const DT = 1 / 30;

export const GEOMETRY = Object.freeze({
  plane: [-1.0, 1.0, -0.2, 1.4], // x low, x high, y low, y high
  camera: { position: [0.95, 1.35], heading: -2.443, fov: 2.0944, range: 2.6 },
  ear: [0.95, 1.35],
  occluders: [{ center: [0.25, 0.85], radius: 0.08 }],
  arm: { base: [0.0, 0.0], lengths: [0.45, 0.35], width: 0.06, limits: [[0.35, 2.79], [-2.6, -0.3]] },
});

export const NOISE = Object.freeze({ camera: 0.01, motor: 0.03, encoder: 0.001, cue: [0.04, 0.08] });

export const cloneGeometry = (g) => JSON.parse(JSON.stringify(g));

/** The arm's points for its joint angles: the base first and the hand last. Joint 0's angle is
 *  measured from the x axis and every further joint's from the link before it. */
export function forward(geometry, joints) {
  const { base, lengths } = geometry.arm;
  const points = [[base[0], base[1]]];
  let angle = 0, x = base[0], y = base[1];
  for (let k = 0; k < lengths.length; k++) {
    angle += joints[k];
    x += Math.cos(angle) * lengths[k];
    y += Math.sin(angle) * lengths[k];
    points.push([x, y]);
  }
  return points;
}

export const hand = (geometry, joints) => forward(geometry, joints).at(-1);

/** Distance from the point p to the segment a-b. */
export function pointSegment(p, a, b) {
  const abx = b[0] - a[0], aby = b[1] - a[1];
  const apx = p[0] - a[0], apy = p[1] - a[1];
  const along = (apx * abx + apy * aby) / Math.max(abx * abx + aby * aby, 1e-12);
  const t = Math.min(1, Math.max(0, along));
  return Math.hypot(p[0] - (a[0] + t * abx), p[1] - (a[1] + t * aby));
}

const cross = (ux, uy, vx, vy) => ux * vy - uy * vx;

/** Distance between the segments a-b and c-d: zero where they cross. */
export function segments(a, b, c, d) {
  const ends = Math.min(pointSegment(a, c, d), pointSegment(b, c, d), pointSegment(c, a, b), pointSegment(d, a, b));
  const s1 = Math.sign(cross(b[0] - a[0], b[1] - a[1], c[0] - a[0], c[1] - a[1]));
  const s2 = Math.sign(cross(b[0] - a[0], b[1] - a[1], d[0] - a[0], d[1] - a[1]));
  const s3 = Math.sign(cross(d[0] - c[0], d[1] - c[1], a[0] - c[0], a[1] - c[1]));
  const s4 = Math.sign(cross(d[0] - c[0], d[1] - c[1], b[0] - c[0], b[1] - c[1]));
  return s1 !== s2 && s3 !== s4 ? 0 : ends;
}

/** Why the camera does not see a point: null where it does, else 'field' (outside the field,
 *  the range or the plane), 'occluder' or 'arm'. `own` marks the arm's own end: its link hides
 *  nothing within a link's width of it. */
export function hiddenBy(geometry, point, joints, own = false, chain = null) {
  const cam = geometry.camera, eye = cam.position;
  const rx = point[0] - eye[0], ry = point[1] - eye[1];
  const distance = Math.hypot(rx, ry);
  const twoPi = 2 * Math.PI;
  let bearing = Math.atan2(ry, rx) - cam.heading + Math.PI;
  bearing = Math.abs((((bearing % twoPi) + twoPi) % twoPi) - Math.PI);
  const [lowX, highX, lowY, highY] = geometry.plane;
  if (!(distance <= cam.range) || !(bearing <= cam.fov / 2)) return 'field';
  if (!(point[0] >= lowX && point[0] <= highX && point[1] >= lowY && point[1] <= highY)) return 'field';
  for (const o of geometry.occluders) if (!(pointSegment(o.center, eye, point) > o.radius)) return 'occluder';
  chain = chain || forward(geometry, joints);
  const links = geometry.arm.lengths.length, width = geometry.arm.width;
  for (let k = 0; k < links; k++) {
    const a = chain[k];
    let b = chain[k + 1];
    if (own && k === links - 1) {
      // the hand's own link, its length less a width at the hand, which the hand tops
      const span = Math.max(Math.hypot(b[0] - a[0], b[1] - a[1]), 1e-9);
      const f = Math.min(1, Math.max(0, 1 - width / span));
      b = [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
    }
    if (!(segments(eye, point, a, b) > width / 2)) return 'arm';
  }
  return null;
}

/** Whether the camera sees a point with the arm at these joint angles. */
export const visible = (geometry, point, joints, own = false, chain = null) => hiddenBy(geometry, point, joints, own, chain) === null;

/** The direction and distance from the ear to a point. */
export function polar(geometry, point) {
  const dx = point[0] - geometry.ear[0], dy = point[1] - geometry.ear[1];
  return [Math.atan2(dy, dx), Math.hypot(dx, dy)];
}

/** The point a (direction, distance) cue names. */
export function cartesian(geometry, cue) {
  return [geometry.ear[0] + cue[1] * Math.cos(cue[0]), geometry.ear[1] + cue[1] * Math.sin(cue[0])];
}

/** The minimum-jerk profile from 0 to 1. */
export function smooth(fraction) {
  const f = Math.min(1, Math.max(0, fraction));
  return 10 * f ** 3 - 15 * f ** 4 + 6 * f ** 5;
}

/** Steps since a thing was last seen, per step: 0 in view, 1 on the first step out of view.
 *  Step 0 counts as seen. */
export function unseen(inView) {
  const out = new Array(inView.length).fill(0);
  for (let t = 1; t < inView.length; t++) out[t] = inView[t] ? 0 : out[t - 1] + 1;
  return out;
}

/** What moves: the arm's true joint angles and the things' true positions (thing 0 the hand).
 *  `own`: the hand is the arm's own end. */
export function makeWorld({ geometry = GEOMETRY, joints = [1.3, -1.1], things = [[-0.55, 0.55]], own = false, noise = NOISE } = {}) {
  return {
    geometry: cloneGeometry(geometry), joints: joints.slice(), things: things.map((p) => p.slice()), own,
    cameraNoise: noise.camera, motorNoise: noise.motor, encoderNoise: noise.encoder, cueNoise: noise.cue.slice(),
  };
}

/** Advance the world by one step and return its record. `command` is the joint increment asked
 *  of the arm, `moves` each thing's own displacement (the arm's own hand takes none) and
 *  `sounds` which things sound at this step. `noise` holds the step's standard normal draws:
 *  motor and encoder (one per joint), camera and cue (two per thing). The record: truth,
 *  in_view, report (null while out of view), cue (direction and distance from the ear, null
 *  while silent), joints (the readings) and commands. */
export function step(world, command, moves, sounds, noise) {
  const g = world.geometry;
  world.joints = world.joints.map((q, k) => q + command[k] * (1.0 + world.motorNoise * noise.motor[k]));
  world.things = world.things.map((p, k) => [p[0] + moves[k][0], p[1] + moves[k][1]]);
  const chain = forward(g, world.joints);
  if (world.own) world.things[0] = chain.at(-1).slice();
  const inView = world.things.map((p, k) => visible(g, p, world.joints, world.own && k === 0, chain));
  const report = world.things.map((p, k) => (inView[k]
    ? [p[0] + world.cameraNoise * noise.camera[k][0], p[1] + world.cameraNoise * noise.camera[k][1]] : null));
  const cue = world.things.map((p, k) => {
    if (!sounds[k]) return null;
    const heard = polar(g, p);
    return [heard[0] + world.cueNoise[0] * noise.cue[k][0], heard[1] * (1.0 + world.cueNoise[1] * noise.cue[k][1])];
  });
  return {
    truth: world.things.map((p) => p.slice()), in_view: inView, report, cue,
    joints: world.joints.map((q, k) => q + world.encoderNoise * noise.encoder[k]),
    commands: command.slice(), chain,
  };
}

/** A seeded generator (mulberry32) with standard normal draws, for the page's noise. */
export class Random {
  constructor(seed = 1) { this.state = seed >>> 0; this.spare = null; }
  uniform() {
    let t = (this.state += 0x6d2b79f5) >>> 0;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  normal() {
    if (this.spare !== null) { const v = this.spare; this.spare = null; return v; }
    let u = 0;
    while (u < 1e-12) u = this.uniform();
    const r = Math.sqrt(-2 * Math.log(u)), a = 2 * Math.PI * this.uniform();
    this.spare = r * Math.sin(a);
    return r * Math.cos(a);
  }
  /** One step's draws in the Python world's order: motor, encoder, camera, cue. */
  draws(joints, things) {
    const row = (n) => Array.from({ length: n }, () => this.normal());
    return { motor: row(joints), encoder: row(joints), camera: Array.from({ length: things }, () => row(2)), cue: Array.from({ length: things }, () => row(2)) };
  }
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export const THINGS = Object.freeze([
  { name: 'hand', what: 0, radius: 0.06 },
  { name: 'cup', what: 1, radius: 0.055 },
  { name: 'wrench', what: 2, radius: 0.06 },
  { name: 'box', what: 3, radius: 0.06 },
]);

/** The page's stage: the world as it stands, stepped once per moment. The visitor moves the
 *  hand, the things and the occluder and switches the camera off; a recorded reach moves the
 *  things as a scene file scripts them. `advance()` returns the moment's record. */
export class Stage {
  constructor({ geometry = GEOMETRY, seed = 20261112, noise = NOISE } = {}) {
    this.world = makeWorld({ geometry, noise, joints: [1.3, -1.1], things: [[-0.55, 0.55], [0.5, 0.36], [-0.5, 1.0], [0.22, 1.12]] });
    this.names = THINGS.map((t) => t.name);
    this.random = new Random(seed);
    this.cameraOn = true;
    this.targets = this.world.things.map(() => null); // where the visitor drags each thing
    this.maxSpeed = 1.6;   // metres a second: a dragged thing's limit
    this.sounding = this.world.things.map(() => false);
    this.reach = null;     // a recorded scene being played: { scene, t }
    this.armPlan = null;   // a move of the arm: { from, to, t, steps }
    this.moment = 0;
  }

  get geometry() { return this.world.geometry; }
  get own() { return this.world.own; }

  setCase(kind) {
    this.world.own = kind === 'own';
    this.reach = null;
    if (!this.world.own) this.armPlan = null;
  }

  /** Play a scene file: its commands move the arm and its true positions move the things. */
  play(scene) {
    this.reach = { scene, t: 0 };
    this.world.own = scene.case === 'own';
    this.world.joints = scene.joints[0].slice();
    const rows = Array.isArray(scene.truth[0][0]) ? scene.truth[0] : [scene.truth[0]];
    rows.slice(0, this.world.things.length).forEach((p, k) => { this.world.things[k] = p.slice(); });
    this.targets.fill(null); this.armPlan = null;
  }

  stop() { this.reach = null; }

  moveArm(to, steps = 40) {
    const limits = this.geometry.arm.limits;
    this.armPlan = { from: this.world.joints.slice(), to: to.map((v, k) => clamp(v, limits[k][0], limits[k][1])), t: 0, steps };
  }

  /** A thing sounds at the next step: the ear hears its direction and distance. */
  knock(name) { const k = this.names.indexOf(name); if (k >= 0) this.sounding[k] = true; }

  why(k) {
    if (!this.cameraOn) return 'off';
    return hiddenBy(this.geometry, this.world.things[k], this.world.joints, this.world.own && k === 0);
  }

  advance() {
    const w = this.world, g = w.geometry;
    const joints = w.joints.length, count = w.things.length;
    let command = w.joints.map(() => 0);
    const moves = w.things.map(() => [0, 0]);
    const noise = this.random.draws(joints, count);
    let sounds = this.sounding.slice();
    this.sounding.fill(false);
    if (this.reach) {
      // a recorded scene: the arm takes the file's joint readings, the things its true
      // positions, and a thing sounds where the file holds a cue
      const { scene } = this.reach;
      const t = Math.min(this.reach.t, scene.truth.length - 1);
      const rows = Array.isArray(scene.truth[t][0]) ? scene.truth[t] : [scene.truth[t]];
      command = scene.commands[t].slice();
      noise.motor.fill(0);
      w.joints = scene.joints[t].map((q, k) => q - command[k]); // step() adds the command
      for (let k = w.own ? 1 : 0; k < Math.min(count, rows.length); k++) moves[k] = [rows[k][0] - w.things[k][0], rows[k][1] - w.things[k][1]];
      const cues = scene.cue ? scene.cue[t] : null;
      if (cues) sounds = sounds.map((v, k) => v || (cues[k] !== null && cues[k] !== undefined));
      this.reach.t += 1;
      if (this.reach.t >= scene.truth.length) this.reach = null;
    } else if (this.armPlan) {
      const p = this.armPlan;
      const f0 = smooth(p.t / p.steps), f1 = smooth((p.t + 1) / p.steps);
      command = p.from.map((v, k) => (f1 - f0) * (p.to[k] - v));
      p.t += 1;
      if (p.t >= p.steps) this.armPlan = null;
    }
    const [lx, hx, ly, hy] = g.plane;
    for (let k = 0; k < count; k++) {
      const target = this.targets[k];
      if (!target || this.reach || (k === 0 && w.own)) continue;
      const dx = target[0] - w.things[k][0], dy = target[1] - w.things[k][1];
      const d = Math.hypot(dx, dy), limit = this.maxSpeed * DT;
      const f = d > limit ? limit / d : 1;
      const nx = clamp(w.things[k][0] + dx * f, lx + 0.02, hx - 0.02), ny = clamp(w.things[k][1] + dy * f, ly + 0.02, hy - 0.02);
      moves[k] = [nx - w.things[k][0], ny - w.things[k][1]];
    }
    const record = step(w, command, moves, sounds, noise);
    if (!this.cameraOn) { record.in_view = record.in_view.map(() => false); record.report = record.report.map(() => null); }
    this.moment += 1;
    record.moment = this.moment;
    record.case = w.own ? 'own' : 'other';
    record.sounds = sounds;
    return record;
  }
}

/** The lit part of the plane as a polygon: rays from the camera across its field, each cut
 *  short by the range, the plane's edge, the occluding discs and the arm's links. */
export function litPolygon(geometry, joints, rays = 220, own = false) {
  const cam = geometry.camera, eye = cam.position;
  const [lowX, highX, lowY, highY] = geometry.plane;
  const chain = forward(geometry, joints);
  const half = geometry.arm.width / 2;
  const out = [];
  for (let i = 0; i <= rays; i++) {
    const angle = cam.heading - cam.fov / 2 + (cam.fov * i) / rays;
    const dx = Math.cos(angle), dy = Math.sin(angle);
    let reach = cam.range;
    if (dx > 0) reach = Math.min(reach, (highX - eye[0]) / dx); else if (dx < 0) reach = Math.min(reach, (lowX - eye[0]) / dx);
    if (dy > 0) reach = Math.min(reach, (highY - eye[1]) / dy); else if (dy < 0) reach = Math.min(reach, (lowY - eye[1]) / dy);
    reach = Math.max(0, reach);
    for (const o of geometry.occluders) {
      const cx = o.center[0] - eye[0], cy = o.center[1] - eye[1];
      const along = cx * dx + cy * dy, off2 = cx * cx + cy * cy - along * along;
      const r2 = o.radius * o.radius;
      if (along > 0 && off2 < r2) reach = Math.min(reach, Math.max(0, along - Math.sqrt(r2 - off2)));
    }
    for (let k = 0; k < chain.length - 1; k++) {
      const a = chain[k];
      let b = chain[k + 1];
      if (own && k === chain.length - 2) {
        const span = Math.max(Math.hypot(b[0] - a[0], b[1] - a[1]), 1e-9);
        const f = Math.min(1, Math.max(0, 1 - geometry.arm.width / span));
        b = [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
      }
      const end = [eye[0] + dx * reach, eye[1] + dy * reach];
      if (segments(eye, end, a, b) <= half) {
        let lo = 0, hi = reach; // bisect for where the ray first comes within half a width of the link
        for (let it = 0; it < 16; it++) {
          const mid = (lo + hi) / 2;
          if (segments(eye, [eye[0] + dx * mid, eye[1] + dy * mid], a, b) <= half) hi = mid; else lo = mid;
        }
        reach = lo;
      }
    }
    out.push([eye[0] + dx * reach, eye[1] + dy * reach]);
  }
  return out;
}
