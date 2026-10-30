// The contact cell in the browser: MuJoCo 3.17 (WebAssembly) running the same compiled Panda,
// table, bins, lamps and block the brain was raised in, with the arm's IK reflex, its grasp and
// release judgement and its 262-value observation ported line for line from cadence-arm/arm2
// (scene.py, actions.py, senses.py). tests/parity.mjs checks this file against recorded Python
// trials: the same observation, the same reflex target and the same physics after each decision.

export const ARM = 7;
export const STEPS_PER_DECISION = 100;
export const RECORD_EVERY = 5;
export const HOME_Q = [0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853];
export const R_DOWN = [[0, 1, 0], [1, 0, 0], [0, 0, -1]];
export const ORDERS = ['none', 'A', 'B'];
export const BIN_HOME = { A: [0.62, -0.22], B: [0.62, 0.22] };
export const BIN_SIDE = 0.13;
export const BIN_HEIGHT = 0.04;
export const TABLE_X = [0.25, 0.85];
export const TABLE_Y = [-0.42, 0.42];
export const SPAWN_X = [0.36, 0.54];
export const SPAWN_Y = [-0.24, 0.24];
export const LIFT = 0.15;
export const SETTLE_SPEED = 0.03;
export const RELEASE_WAIT = 6;
export const SLOTS = [5, 5, 5, 2];
export const HOLD = 2;
export const STEP_M = 0.01;
export const FLOOR = 0.010;
export const BOUND = 0.15;
// The block the site uses: the middle of the training range (stage 2b's wide set spans it).
export const SITE_BLOCK = { half: 0.025, mass: 0.08, friction: 1.0, timeconst: 0.02, dampratio: 1.0 };

// senses.py
const BINS = 15;
const HAND_SPAN = [[0.20, 0.80], [-0.40, 0.40], [0.00, 0.50]];
const RELATIVE_REACH = [0.60, 0.60, 0.45];
const VELOCITY_SPAN = 2.0;
const OPENING_SPAN = [0.0, 0.04];
const JOINT_BINS = 7;
const CENTRES = Array.from({ length: BINS }, (_, i) => -1 + (2 * i) / (BINS - 1));
const SIGMA = (2.0 / (BINS - 1)) * 0.75;

function bumps(u, out) {
  for (let i = 0; i < BINS; i++) { const z = (u - CENTRES[i]) / SIGMA; out.push(Math.exp(-0.5 * z * z)); }
}
function absoluteCode(value, [lo, hi], out) { bumps((2.0 * (value - lo)) / (hi - lo) - 1.0, out); }
function warp(d, reach) { return Math.sign(d) * Math.sqrt(Math.min(Math.abs(d), reach) / reach); }
function relativeCode(d, reach, out) { bumps(warp(d, reach), out); }
function jointCode(value, lo, hi, out, bins = JOINT_BINS) {
  const sigma = ((hi - lo) / (bins - 1)) * 0.75;
  for (let i = 0; i < bins; i++) { const c = lo + ((hi - lo) * i) / (bins - 1); const z = (value - c) / sigma; out.push(Math.exp(-0.5 * z * z)); }
}

// Small dense linear algebra for the 6 x 6 damped least squares.
function solve(A, B) { // A n x n, B n x m (arrays of rows); returns A^-1 B by Gaussian elimination with pivoting
  const n = A.length, m = B[0].length;
  const M = A.map((row, i) => [...row, ...B[i]]);
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    const d = M[c][c];
    for (let k = c; k < n + m; k++) M[c][k] /= d;
    for (let r = 0; r < n; r++) {
      if (r === c) continue;
      const f = M[r][c];
      if (f !== 0) for (let k = c; k < n + m; k++) M[r][k] -= f * M[c][k];
    }
  }
  return M.map((row) => row.slice(n));
}

export class Cell {
  constructor(mujoco, model) {
    this.mj = mujoco;
    this.model = model;
    this.data = new mujoco.MjData(model);
    this.scratch = new mujoco.MjData(model);
    const id = (type, name) => mujoco.mj_name2id(model, mujoco.mjtObj[type].value, name);
    this.tcp = id('mjOBJ_SITE', 'tcp');
    this.blockBody = id('mjOBJ_BODY', 'block');
    this.blockGeom = id('mjOBJ_GEOM', 'block');
    const joint = id('mjOBJ_JOINT', 'block');
    this.blockQpos = model.jnt_qposadr[joint];
    this.blockQvel = model.jnt_dofadr[joint];
    this.fingers = [id('mjOBJ_BODY', 'left_finger'), id('mjOBJ_BODY', 'right_finger')];
    this.lamps = { A: id('mjOBJ_GEOM', 'lamp_A'), B: id('mjOBJ_GEOM', 'lamp_B') };
    this.key = id('mjOBJ_KEY', 'home');
    this.low = []; this.high = [];
    for (let j = 0; j < ARM; j++) { this.low.push(model.jnt_range[2 * j]); this.high.push(model.jnt_range[2 * j + 1]); }
    this.binGeoms = { A: [], B: [] };
    for (let g = 0; g < model.ngeom; g++) {
      const name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM.value, g) || '';
      for (const k of ['A', 'B']) if (name.startsWith(`bin_${k}_`)) this.binGeoms[k].push(g);
    }
    this.bins = { A: [...BIN_HOME.A], B: [...BIN_HOME.B] };
    this.nv = model.nv;
    this.jacp = new mujoco.DoubleBuffer(3 * model.nv);
    this.jacr = new mujoco.DoubleBuffer(3 * model.nv);
    this.order = 1;
    this.half = SITE_BLOCK.half;
    this.lastCommand = null;
    this.setBlockPhysics(SITE_BLOCK);
    this.home();
  }

  // --- state ---------------------------------------------------------------------------------
  setBlockPhysics(p) {
    const m = this.model, g = this.blockGeom, b = this.blockBody;
    m.geom_size[3 * g] = p.half; m.geom_size[3 * g + 1] = p.half; m.geom_size[3 * g + 2] = p.half;
    m.geom_friction[3 * g] = p.friction;
    m.geom_solref[2 * g] = p.timeconst; m.geom_solref[2 * g + 1] = p.dampratio;
    m.body_mass[b] = p.mass;
    const inertia = (p.mass * (2 * p.half) ** 2) / 6.0;
    m.body_inertia[3 * b] = inertia; m.body_inertia[3 * b + 1] = inertia; m.body_inertia[3 * b + 2] = inertia;
    this.half = p.half;
  }

  home() {
    const d = this.data;
    this.mj.mj_resetDataKeyframe(this.model, d, this.key);
    for (let j = 0; j < ARM; j++) d.ctrl[j] = HOME_Q[j];
    d.ctrl[7] = 255.0;
    this.closed = false; this.closedFor = 0; this.releasing = 0; this.holding = false;
    this.liftedOnce = false; this.graspOffset = 0; this.lastCommand = null;
    this.mj.mj_forward(this.model, d);
  }

  placeBlock(x, y) {
    const d = this.data, q = this.blockQpos;
    const v = [x, y, this.half, 1, 0, 0, 0];
    for (let i = 0; i < 7; i++) d.qpos[q + i] = v[i];
    for (let i = 0; i < 6; i++) d.qvel[this.blockQvel + i] = 0;
    this.liftedOnce = false;
    this.mj.mj_forward(this.model, d);
  }

  moveBin(name, x, y) {
    const [bx, by] = this.bins[name];
    for (const g of this.binGeoms[name]) { this.model.geom_pos[3 * g] += x - bx; this.model.geom_pos[3 * g + 1] += y - by; }
    this.bins[name] = [x, y];
    this.mj.mj_forward(this.model, this.data);
  }

  setOrder(name) {
    this.order = ORDERS.indexOf(name);
    for (const k of ['A', 'B']) {
      const g = this.lamps[k], lit = k === name;
      const rgba = lit ? [1.0, 0.95, 0.4, 1.0] : [0.3, 0.3, 0.3, 1.0];
      for (let i = 0; i < 4; i++) this.model.geom_rgba[4 * g + i] = rgba[i];
    }
  }

  // --- kinematics ----------------------------------------------------------------------------
  tip(d = this.data) { const s = 3 * this.tcp; return [d.site_xpos[s], d.site_xpos[s + 1], d.site_xpos[s + 2]]; }
  blockPos() { const b = 3 * this.blockBody; const x = this.data.xpos; return [x[b], x[b + 1], x[b + 2]]; }
  blockSpeed() { const v = this.data.qvel, i = this.blockQvel; return Math.hypot(v[i], v[i + 1], v[i + 2]); }
  joints() { return Array.from(this.data.qpos.subarray(0, ARM)); }
  velocities() { return Array.from(this.data.qvel.subarray(0, ARM)); }
  opening() { return this.data.qpos[7]; }
  rest() { return Array.from(this.data.ctrl.subarray(0, ARM)); }
  releasePoint() { const name = ORDERS[this.order]; if (name === 'none') return null; const [x, y] = this.bins[name]; return [x, y, LIFT]; }

  jacobian(d) {
    this.mj.mj_jacSite(this.model, d, this.jacp, this.jacr, this.tcp);
    const view = (buf) => (buf.GetView ? buf.GetView() : buf.getView());
    const P = view(this.jacp), R = view(this.jacr), nv = this.nv;
    const jp = [0, 1, 2].map((r) => Array.from({ length: ARM }, (_, c) => P[r * nv + c]));
    const jr = [0, 1, 2].map((r) => Array.from({ length: ARM }, (_, c) => R[r * nv + c]));
    return [jp, jr];
  }

  solveIK(q0, target, { iterations = 3, damping = 0.05, posture = 0.05, rotWeight = 0.5, bound = 0.15 } = {}) {
    let q = q0.slice();
    const s = this.scratch, m = this.model;
    for (let it = 0; it < iterations; it++) {
      for (let j = 0; j < ARM; j++) s.qpos[j] = q[j];
      this.mj.mj_kinematics(m, s);
      this.mj.mj_comPos(m, s);
      const pos = this.tip(s);
      const r0 = 9 * this.tcp, X = s.site_xmat;
      const rot = [[X[r0], X[r0 + 1], X[r0 + 2]], [X[r0 + 3], X[r0 + 4], X[r0 + 5]], [X[r0 + 6], X[r0 + 7], X[r0 + 8]]];
      const [jp, jr] = this.jacobian(s);
      const J = [...jp, ...jr.map((row) => row.map((v) => rotWeight * v))]; // 6 x 7
      const rotErr = [0, 0, 0];
      for (let i = 0; i < 3; i++) {
        const a = [rot[0][i], rot[1][i], rot[2][i]], b = [R_DOWN[0][i], R_DOWN[1][i], R_DOWN[2][i]];
        rotErr[0] += 0.5 * (a[1] * b[2] - a[2] * b[1]); rotErr[1] += 0.5 * (a[2] * b[0] - a[0] * b[2]); rotErr[2] += 0.5 * (a[0] * b[1] - a[1] * b[0]);
      }
      const err = [target[0] - pos[0], target[1] - pos[1], target[2] - pos[2], ...rotErr.map((v) => rotWeight * v)];
      // inverse = J^T (J J^T + damping^2 I)^-1   (7 x 6)
      const JJt = J.map((ri, i) => J.map((rk, k) => ri.reduce((acc, v, c) => acc + v * rk[c], 0) + (i === k ? damping * damping : 0)));
      const JinvT = solve(JJt, J); // (JJ^T + d^2 I)^-1 J   (6 x 7)
      const inverse = Array.from({ length: ARM }, (_, c) => JinvT.map((row) => row[c])); // 7 x 6
      const bias = HOME_Q.map((h, j) => posture * (h - q[j]));
      const dq = new Array(ARM).fill(0);
      for (let c = 0; c < ARM; c++) {
        let v = 0;
        for (let k = 0; k < 6; k++) v += inverse[c][k] * err[k];
        // (I - inverse J) bias
        let null_ = bias[c];
        for (let r = 0; r < ARM; r++) {
          let ij = 0;
          for (let k = 0; k < 6; k++) ij += inverse[c][k] * J[k][r];
          null_ -= ij * bias[r];
        }
        dq[c] = v + null_;
      }
      q = q.map((v, j) => Math.min(Math.max(v + dq[j], this.low[j]), this.high[j]));
    }
    if (bound !== null) q = q.map((v, j) => Math.min(Math.max(v, q0[j] - bound), q0[j] + bound));
    return q.map((v, j) => Math.min(Math.max(v, this.low[j]), this.high[j]));
  }

  // --- contacts ------------------------------------------------------------------------------
  fingerContacts() {
    const m = this.model, d = this.data, touched = [false, false];
    const contacts = d.contact;
    try {
      for (let i = 0; i < d.ncon; i++) {
        const c = contacts.get(i);
        const g1 = c.geom1, g2 = c.geom2;
        if (c.delete) c.delete();
        if (g1 !== this.blockGeom && g2 !== this.blockGeom) continue;
        const other = g1 === this.blockGeom ? g2 : g1;
        const body = m.geom_bodyid[other];
        for (let k = 0; k < 2; k++) if (body === this.fingers[k]) touched[k] = true;
      }
    } finally { contacts.delete(); }
    return touched;
  }

  // --- physics -------------------------------------------------------------------------------
  // One decision: the equilibrium posture and the gripper, then 100 physics steps; hook(i) every
  // RECORD_EVERY steps. Returns {event, done}. Unlike the training cell, a placement or a drop
  // ends the run here instead of spawning the next block: the visitor places the next one.
  decide(qTarget, close, hook = null) {
    this.decideBegin(qTarget, close);
    for (let i = 0; i < STEPS_PER_DECISION; i++) {
      this.mj.mj_step(this.model, this.data);
      if (hook && (i + 1) % RECORD_EVERY === 0) hook((i + 1) / RECORD_EVERY);
    }
    return this.decideEnd();
  }

  // The page runs a decision in three parts so the 100 physics steps can be spread over
  // animation frames: decideBegin, stepPhysics(n) until stepsLeft is 0, decideEnd.
  decideBegin(qTarget, close) {
    const d = this.data;
    for (let j = 0; j < ARM; j++) d.ctrl[j] = Math.min(Math.max(qTarget[j], this.low[j]), this.high[j]);
    close = Boolean(close);
    if (close !== this.closed) {
      this.closedFor = 0;
      if (this.closed && this.holding) this.releasing = 1;
    }
    this.closed = close;
    d.ctrl[7] = close ? 0.0 : 255.0;
    this.wasHolding = this.holding;
    this.stepsLeft = STEPS_PER_DECISION;
  }

  stepPhysics(n) {
    const k = Math.min(n, this.stepsLeft);
    for (let i = 0; i < k; i++) this.mj.mj_step(this.model, this.data);
    this.stepsLeft -= k;
    return this.stepsLeft;
  }

  decideEnd() {
    const d = this.data;
    const outcome = { event: null, done: false };
    const wasHolding = this.wasHolding;
    const blockZ = this.blockPos()[2];
    let finite = true;
    for (let i = 0; i < d.qpos.length; i++) if (!Number.isFinite(d.qpos[i])) { finite = false; break; }
    if (!finite || Math.abs(blockZ) > 1.0) {
      outcome.event = 'dropped'; outcome.done = true; outcome.lost = true;
      return outcome;
    }
    const [left, right] = this.fingerContacts();
    this.holding = this.closed && left && right;
    if (this.closed && !this.holding) this.closedFor += 1;
    if (this.holding && !wasHolding) {
      outcome.event = 'grasped'; this.releasing = 0; this.graspOffset = this.tip()[2] - blockZ;
    } else if (wasHolding && !this.holding && this.closed) {
      outcome.event = 'slipped'; this.releasing = 1;
    }
    if (this.holding && this.blockPos()[2] - this.half >= 0.05) this.liftedOnce = true;
    if (this.releasing && !this.holding) {
      const [x, y, z] = this.blockPos();
      const settled = this.blockSpeed() < SETTLE_SPEED && z < BIN_HEIGHT + 2 * this.half;
      if (settled || this.releasing > RELEASE_WAIT) {
        const name = this.inBin(x, y);
        if (name !== null && z < BIN_HEIGHT + this.half + 0.01) {
          const right_ = ORDERS[this.order] === name;
          outcome.event = `placed:${name}:${right_ ? 'right' : 'wrong'}`;
          outcome.done = true;
        } else {
          outcome.event = outcome.event === null ? 'dropped' : outcome.event;
          outcome.dropped = true;
        }
        this.releasing = 0;
      } else {
        this.releasing += 1;
      }
    }
    return outcome;
  }

  inBin(x, y, margin = 0.0) {
    for (const name of ['A', 'B']) {
      const [bx, by] = this.bins[name];
      if (Math.abs(x - bx) <= BIN_SIDE / 2 + margin && Math.abs(y - by) <= BIN_SIDE / 2 + margin) return name;
    }
    return null;
  }

  // --- the brain's senses and acts ------------------------------------------------------------
  observe() {
    const out = [];
    const tip = this.tip(), block = this.blockPos();
    for (let i = 0; i < 3; i++) absoluteCode(tip[i], HAND_SPAN[i], out);
    for (let i = 0; i < 3; i++) relativeCode(block[i] - tip[i], RELATIVE_REACH[i], out);
    const release = this.releasePoint();
    for (let i = 0; i < 3; i++) {
      if (release === null) for (let k = 0; k < BINS; k++) out.push(0); else relativeCode(release[i] - tip[i], RELATIVE_REACH[i], out);
    }
    const q = this.joints();
    for (let j = 0; j < ARM; j++) jointCode(q[j], this.low[j], this.high[j], out);
    jointCode(this.opening(), OPENING_SPAN[0], OPENING_SPAN[1], out);
    out.push(this.closed ? 1 : 0, this.holding ? 1 : 0);
    const v = this.velocities();
    for (let j = 0; j < ARM; j++) jointCode(v[j], -VELOCITY_SPAN, VELOCITY_SPAN, out);
    if (this.lastCommand === null) for (let k = 0; k < 17; k++) out.push(0); else out.push(...this.lastCommand);
    for (let k = 0; k < 3; k++) out.push(k === this.order ? 1 : 0);
    return Float64Array.from(out);
  }

  targetOf(answer) {
    const tip = this.tip();
    const t = [0, 1, 2].map((i) => tip[i] + (answer[i] - HOLD) * STEP_M);
    t[2] = Math.max(t[2], FLOOR);
    return t;
  }

  // Executes the brain's answer (slot indices dx, dy, dz, grip) through the IK reflex.
  execute(answer, hook = null) {
    const { target, qTarget } = this.command(answer);
    const outcome = this.decide(qTarget, answer[3], hook);
    outcome.target = target; outcome.qTarget = qTarget;
    return outcome;
  }

  // The reflex's equilibrium posture for an answer, and the efference copy the next observation reads.
  command(answer) {
    const target = this.targetOf(answer);
    const qTarget = this.solveIK(this.rest(), target, { bound: BOUND });
    const oneHot = new Array(17).fill(0);
    let offset = 0;
    SLOTS.forEach((size, k) => { oneHot[offset + answer[k]] = 1; offset += size; });
    this.lastCommand = oneHot;
    return { target, qTarget };
  }

  // Restores a recorded state (the parity test and the page's reset use it).
  setState(s) {
    const d = this.data;
    s.qpos.forEach((v, i) => { d.qpos[i] = v; });
    s.qvel.forEach((v, i) => { d.qvel[i] = v; });
    s.ctrl.forEach((v, i) => { d.ctrl[i] = v; });
    if (s.act) s.act.forEach((v, i) => { d.act[i] = v; });
    d.time = s.time ?? 0;
    this.closed = s.closed; this.closedFor = s.closed_for; this.releasing = s.releasing; this.holding = s.holding;
    this.liftedOnce = s.lifted_once; this.lastCommand = s.last_command;
    this.mj.mj_forward(this.model, d);
  }
}
