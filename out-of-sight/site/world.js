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

export const FORMAT = 'cadence-tracking-scene/1';
const UNITS = { length: 'm', time: 's', angle: 'rad' };

/** Read a scene file (the tracking chamber's `cadence-tracking-scene/1`, as its `world.load`
 *  reads it) into one shape whatever the file holds: every per-step field has one row a step
 *  and, for `truth`, `report`, `in_view` and `cue`, one cell a thing. A scene of one thing (the
 *  hand's rows written plainly) and a scene of several read alike. A report out of view and a
 *  silent cue are null. Where the file leaves them out: `start` is the truth at step 0, `dt`
 *  is 1/30, `commands` and `joints` are an arm at rest and `geometry` is the chamber's own. */
export function readScene(data) {
  if (!data || data.format !== FORMAT) throw new Error(`A scene file states format "${FORMAT}"; this one states ${JSON.stringify(data?.format)}.`);
  const units = data.units || UNITS;
  for (const key of Object.keys(UNITS)) if (units[key] !== UNITS[key]) throw new Error('A scene is in metres, seconds and radians.');
  for (const name of ['case', 'report', 'in_view', 'truth']) if (!(name in data)) throw new Error(`A scene file holds "${name}".`);
  const steps = data.truth.length;
  if (!steps) throw new Error('A scene holds one row of truth a step.');
  const one = typeof data.truth[0][0] === 'number'; // the hand's rows written plainly
  const cells = (rows) => rows.map((row) => (one ? [row] : row).map((cell) => (cell === null || cell === undefined || cell.some((v) => v === null || Number.isNaN(v)) ? null : [Number(cell[0]), Number(cell[1])])));
  const truth = cells(data.truth), things = truth[0].length;
  const inView = data.in_view.map((row) => (Array.isArray(row) ? row.map(Boolean) : [Boolean(row)]));
  const report = cells(data.report).map((row, t) => row.map((cell, k) => (inView[t][k] ? cell : null)));
  const geometry = cloneGeometry(data.geometry || GEOMETRY);
  if (!geometry.ear) geometry.ear = geometry.camera.position.slice();
  geometry.camera = { heading: 0, fov: 2 * Math.PI, range: 1e9, ...geometry.camera };
  geometry.occluders = geometry.occluders || [];
  geometry.arm = { width: 0, ...geometry.arm };
  const joints = geometry.arm.lengths.length;
  if (!geometry.arm.limits) geometry.arm.limits = geometry.arm.lengths.map(() => [-Math.PI, Math.PI]);
  const atRest = () => Array.from({ length: steps }, () => new Array(joints).fill(0));
  const bad = (rows, width) => rows.length !== steps || rows.some((row) => !row || row.length !== width);
  const scene = {
    format: FORMAT, case: String(data.case), steps, things,
    truth, report, in_view: inView,
    cue: data.cue ? cells(data.cue) : null,
    commands: (data.commands || atRest()).map((row) => row.map(Number)),
    joints: (data.joints || atRest()).map((row) => row.map(Number)),
    start: data.start ? (one ? [data.start.map(Number)] : data.start.map((p) => p.map(Number))) : truth[0].map((p) => p.slice()),
    what: data.what ? data.what.map(Number) : new Array(things).fill(0),
    geometry, dt: Number(data.dt ?? 1 / 30), kind: String(data.kind ?? ''), event: Number(data.event ?? -1),
    camera_noise: data.camera_noise ?? null, name: String(data.name ?? ''),
  };
  if (!['own', 'other', 'room'].includes(scene.case)) throw new Error(`A scene's case is "own", "other" or "room"; this one states "${scene.case}".`);
  if (truth.some((row) => row.length !== things || row.some((cell) => cell === null))) throw new Error('truth holds one finite (x, y) per step and thing.');
  if (bad(report, things) || bad(inView, things) || (scene.cue && bad(scene.cue, things))) throw new Error('report, in_view and cue match truth\'s steps and things.');
  if (bad(scene.commands, joints) || bad(scene.joints, joints)) throw new Error('commands and joints hold one row of joint values per step.');
  if (report.some((row, t) => row.some((cell, k) => inView[t][k] && cell === null))) throw new Error('The report is finite wherever a thing is in view.');
  if (scene.start.length !== things || scene.what.length !== things) throw new Error('start and what hold one entry per thing.');
  return scene;
}

/** Steps since each thing was last seen, per step and thing. Step 0 counts as seen: the
 *  starting positions are given. */
export function unseenSteps(scene) {
  const out = [new Array(scene.things).fill(0)];
  for (let t = 1; t < scene.steps; t++) out.push(scene.in_view[t].map((seen, k) => (seen ? 0 : out[t - 1][k] + 1)));
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

// What stands in the room: the hand, and three kinds of thing.
export const THINGS = Object.freeze([
  { name: 'hand', what: 0, radius: 0.06 },
  { name: 'cup', what: 1, radius: 0.055 },
  { name: 'apple', what: 2, radius: 0.05 },
  { name: 'bread', what: 3, radius: 0.06 },
]);

// Where everything stands when the page opens. The body, which carries the camera and the ear,
// stands inside the room, so that things lie around it: in front of it, beside it and behind it.
export const HOME = Object.freeze({
  body: { position: [0.45, 0.5], heading: (170 * Math.PI) / 180 },
  pillar: { center: [-0.2, 0.62], radius: 0.1 }, // a little wider than the chamber's, to hide a hand behind with ease
  joints: [2.6, -0.5],
  things: [[-0.6, 1.0], [-0.2, 0.32], [-0.05, 1.1], [0.82, 0.3]],
});

/** An angle brought into (-pi, pi]. */
export const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));

/** A point as the body has it: its distance, and its bearing from the way the body faces
 *  (0 straight ahead, positive to the left, pi behind). */
export function around(geometry, point) {
  const cam = geometry.camera, dx = point[0] - cam.position[0], dy = point[1] - cam.position[1];
  return { distance: Math.hypot(dx, dy), bearing: wrap(Math.atan2(dy, dx) - cam.heading) };
}

/** The page's stage: the world as it stands, stepped once per moment. The visitor moves the
 *  hand, the things and the pillar (the occluding disc), turns the camera and switches it off;
 *  a recorded scene moves the things as a scene file scripts them. `advance()` returns the
 *  moment's record. The camera's position and heading are the body's pose: they are read at
 *  every moment, so a body that moves across the room needs nothing more than its position
 *  changed. */
export class Stage {
  constructor({ geometry = GEOMETRY, seed = 20261112, noise = NOISE, home = HOME } = {}) {
    // where everything stands when the page opens, and where Reset puts it back
    const room = cloneGeometry(geometry);
    room.camera.position = home.body.position.slice(); room.camera.heading = home.body.heading;
    room.ear = home.body.position.slice();
    room.occluders = [{ center: home.pillar.center.slice(), radius: home.pillar.radius }];
    this.home = { joints: home.joints.slice(), things: home.things.map((p) => p.slice()), geometry: room };
    this.world = makeWorld({ geometry: room, noise, joints: this.home.joints, things: this.home.things });
    this.names = THINGS.map((t) => t.name);
    this.random = new Random(seed);
    this.cameraOn = true;
    this.targets = this.world.things.map(() => null); // where the visitor drags each thing
    this.maxSpeed = 1.6;   // metres a second: a dragged thing's limit
    this.facing = null;    // the heading the visitor turns the camera to
    this.turnRate = 4.2;   // radians a second: the camera's limit
    this.sounding = this.world.things.map(() => false);
    this.reach = null;     // a recorded scene being played: { scene, t }
    this.armPlan = null;   // a move of the arm: { from, to, t, steps }
    this.moment = 0;
  }

  /** Everything back where it stood when the page opened; the camera on. */
  reset() {
    this.world.joints = this.home.joints.slice();
    this.world.things = this.home.things.map((p) => p.slice());
    this.world.geometry = cloneGeometry(this.home.geometry);
    this.world.own = false;
    this.cameraOn = true; this.facing = null;
    this.targets.fill(null); this.sounding.fill(false);
    this.reach = null; this.armPlan = null; this.route = null;
  }

  /** A route: legs taken one scene step at a time, whatever the clock does. A leg moves a
   *  thing to a point at `speed` metres a second ({ name, to, speed }) or rests for a number
   *  of moments ({ rest }). The same route from the same start gives the same rows. */
  follow() {
    const leg = this.route?.[0];
    if (!leg) return;
    // a leg done; with the last of them, `routeEnd` is the moment the route ended at
    const done = () => { this.route.shift(); if (!this.route.length) this.routeEnd = this.moment + 1; };
    if (leg.rest !== undefined) { leg.rest -= 1; if (leg.rest <= 0) done(); return; }
    const k = this.names.indexOf(leg.name), p = this.world.things[k];
    const dx = leg.to[0] - p[0], dy = leg.to[1] - p[1], d = Math.hypot(dx, dy), stride = (leg.speed ?? 0.5) * DT;
    if (d <= stride) { this.world.things[k] = leg.to.slice(); done(); return; }
    this.world.things[k] = [p[0] + (dx / d) * stride, p[1] + (dy / d) * stride];
  }

  /** Turn the camera toward a heading; it gets there at its own rate. */
  turnTo(heading) { this.facing = heading; }

  /** Where a thing (or the pillar, 'pillar') stands, or the way the camera faces ('heading'), for Undo. */
  where(name) {
    if (name === 'heading') return this.world.geometry.camera.heading;
    if (name === 'pillar') return this.world.geometry.occluders[0].center.slice();
    const k = this.names.indexOf(name);
    return k >= 0 ? this.world.things[k].slice() : null;
  }

  /** Put a thing (or the pillar) at a point at once, as a hand that lifts it would. */
  place(name, point) {
    if (name === 'heading') { this.world.geometry.camera.heading = point; this.facing = null; return; }
    if (name === 'pillar') { this.world.geometry.occluders[0].center = point.slice(); return; }
    const k = this.names.indexOf(name);
    if (k < 0 || (k === 0 && this.world.own)) return;
    this.targets[k] = null;
    this.world.things[k] = point.slice();
  }

  get geometry() { return this.world.geometry; }
  get own() { return this.world.own; }

  setCase(kind) {
    this.world.own = kind === 'own';
    this.reach = null;
    if (!this.world.own) this.armPlan = null;
  }

  /** Play a scene (as `readScene` gives it): its geometry stands on the stage, its commands
   *  and joint readings move the arm, and its things take the file's true positions, in-view
   *  flags, reports and cues as they are, so the brain is given exactly what the file holds.
   *  Things of the stage beyond the file's stay where they are, seen by the stage's camera. */
  play(scene) {
    this.reach = { scene, t: 0 };
    const g = cloneGeometry(scene.geometry);
    this.world.geometry = g;
    this.world.own = scene.case === 'own';
    this.world.joints = scene.joints[0].slice();
    scene.truth[0].slice(0, this.world.things.length).forEach((p, k) => { this.world.things[k] = p.slice(); });
    this.cameraOn = true; this.facing = null;
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
    const sounds = this.sounding.slice();
    this.sounding.fill(false);
    this.follow();
    let row = null;
    if (this.reach) {
      // a recorded scene: the arm takes the file's readings and the things its true positions
      const { scene } = this.reach;
      const t = Math.min(this.reach.t, scene.steps - 1);
      row = { t, scene, things: Math.min(count, scene.things) };
      command = scene.commands[t].slice();
      noise.motor.fill(0); noise.encoder.fill(0);
      w.joints = scene.joints[t].map((q, k) => q - command[k]); // step() adds the command
      for (let k = 0; k < row.things; k++) moves[k] = [scene.truth[t][k][0] - w.things[k][0], scene.truth[t][k][1] - w.things[k][1]];
      this.reach.t += 1;
      if (this.reach.t >= scene.steps) this.reach = null;
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
      if (!target || row || (k === 0 && w.own)) continue;
      const dx = target[0] - w.things[k][0], dy = target[1] - w.things[k][1];
      const d = Math.hypot(dx, dy), limit = this.maxSpeed * DT;
      const f = d > limit ? limit / d : 1;
      const nx = clamp(w.things[k][0] + dx * f, lx + 0.02, hx - 0.02), ny = clamp(w.things[k][1] + dy * f, ly + 0.02, hy - 0.02);
      moves[k] = [nx - w.things[k][0], ny - w.things[k][1]];
    }
    // the body's own turn: the camera swings toward where the visitor turns it
    let turn = 0;
    if (this.facing !== null && !row) {
      const gap = wrap(this.facing - g.camera.heading), limit = this.turnRate * DT;
      turn = clamp(gap, -limit, limit);
      g.camera.heading = wrap(g.camera.heading + turn);
      if (Math.abs(gap) <= limit) this.facing = null;
    }
    const record = step(w, command, moves, sounds, noise);
    record.body = { position: g.camera.position.slice(), heading: g.camera.heading, turn };
    if (row) {
      // what the file holds of its things stands as it is: the flags, the reports, the cues
      const { scene, t } = row;
      for (let k = 0; k < row.things; k++) {
        record.truth[k] = scene.truth[t][k].slice(); w.things[k] = scene.truth[t][k].slice();
        record.in_view[k] = scene.in_view[t][k];
        record.report[k] = scene.report[t][k] ? scene.report[t][k].slice() : null;
        record.cue[k] = scene.cue?.[t][k] ? scene.cue[t][k].slice() : record.cue[k];
      }
      record.joints = scene.joints[t].slice();
      record.replayed = row.things;
    }
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
