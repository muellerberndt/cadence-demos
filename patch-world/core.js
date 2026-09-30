/* cadence-world core: the substrate, the genome, the brain, the population. No DOM.
   Used by web/index.html (inlined) and by sim/probe.js (node).

   The brains are deep recursive settlement networks in the Cadence 0.50 model,
   reimplemented here in JavaScript so a thousand of them fit in a browser tick:
   the same patch law (tanh prediction, e = x - p, one joint energy with a state
   prior), the same repair rule (projected analytic-gradient descent with
   sufficient-decrease backtracking and the Barzilai-Borwein secant step), the
   same anchored parameter repair for learning, and the Reinforcement helper's
   one-step Q target. It is a reimplementation, not the cadence-net reference
   engine: it runs at a page-scale tolerance and sweep budget, and it keeps no
   event custody or checkpoint identity. Refused solves are counted and acted
   on as waits; nothing hides behind a reflex fallback. */
(function (root, factory) { if (typeof module === 'object' && module.exports) module.exports = factory(); else root.CW = factory(); })(typeof self !== 'undefined' ? self : this, function () {
'use strict';

// ---------- Mulberry32, the generator the Python world uses ----------
function Mulberry(seed) { this.s = seed >>> 0; }
Mulberry.prototype.random = function () {
  let a = (this.s = (this.s + 0x6D2B79F5) >>> 0);
  let t = Math.imul(a ^ (a >>> 15), a | 1) >>> 0;
  t = (t ^ (t + Math.imul(t ^ (t >>> 7), t | 61))) >>> 0;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

// ---------- the rules: each a flag, each one physical rule ----------
const RULES = { ripen: false, rock: false, night: false, kinds: false, bite: false, carry: false, digest: false };
const CFG = { w: 96, h: 96, soil: 6, grow: 0.08, decay: 0.01, diffuse: 0.05, day: 900, season: 9000, contrastMin: 0.25, foodCap: 8, ripenTicks: 30, rockFraction: 0.12, nightBelow: 0.35, warmup: 400, digestTicks: 6 };
const POP = { initial: 300, birth: 12, max: 1500, base: 0.08, move: 0.05, emit: 0.02, bite: 0.10, read: 0.0004, patch: 0.0004, conn: 0.00001, sweep: 0.0005 };
const N = CFG.w * CFG.h;
const DIRS = [[0, -1], [1, 0], [0, 1], [-1, 0]];
const OUTCOMES = ['none', 'moved', 'blocked', 'ate', 'spoke', 'bit', 'spoiled', 'bitten'];
const GROUP_NAMES = ['food', 'occ', 'energy', 'out', 'light', 'green', 'rock', 'kind', 'lastkind', 'kin', 'dark', 'carried', 'heard'];
const WINDOW_WIDTH = { food: 9, occ: 1, green: 4, rock: 1, kind: 1, kin: 1 }; // per-cell width of the window groups

// the settlement engine's numbers: the library defaults except where the page
// pays for speed with a coarser tolerance and smaller sweep budgets (disclosed)
const BRAIN = {
  statePrior: 0.01, stateBound: 1, paramBound: 4, initScale: 0.3, // library defaults
  tolerance: 1e-3, step: 1.0, backtracks: 12,                     // page scale: the library default tolerance is 1e-6
  settleBudget: 12, learnBudget: 48, imagineBudget: 8, birthBudget: 64,
  valueScale: 0.9, rewardScale: 4,                                // the Reinforcement target's scales
  learnEvery: 4,                                                  // quiet transitions are admitted every fourth tick; rewarding ones always
};

// tanh by table interpolation (4096 cells over [-8, 8], error below 1e-5, far
// under the page tolerance); the derivative uses the interpolated value
const TANH_N = 4096, TANH_LO = -8, TANH_SCALE = TANH_N / 16;
const TANH_T = new Float64Array(TANH_N + 2);
for (let i = 0; i <= TANH_N + 1; i++) TANH_T[i] = Math.tanh(TANH_LO + i / TANH_SCALE);
function ftanh(x) {
  if (x >= 8) return 1; if (x <= -8) return -1;
  const u = (x - TANH_LO) * TANH_SCALE, i = u | 0, f = u - i;
  return TANH_T[i] + (TANH_T[i + 1] - TANH_T[i]) * f;
}

function actionsFor(rules, K) {
  const a = ['north', 'east', 'south', 'west', 'eat', 'wait'];
  if (rules.bite) a.push('bite');
  if (rules.carry) a.push('dig', 'drop');
  for (let k = 1; k <= K; k++) a.push('say ' + k);
  return a;
}

// blobs on the torus for rock and for the two kinds of ground
function blobs(rng, fraction, count, maxLen) {
  const out = new Uint8Array(N); let filled = 0; const target = fraction * N;
  for (let b = 0; b < count && filled < target; b++) {
    let x = (rng.random() * CFG.w) | 0, y = (rng.random() * CFG.h) | 0;
    const len = 6 + (rng.random() * (maxLen || 40)) | 0;
    for (let s = 0; s < len; s++) {
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) { const i = ((y + dy + CFG.h) % CFG.h) * CFG.w + (x + dx + CFG.w) % CFG.w; if (!out[i]) { out[i] = 1; filled++; } }
      const [dx, dy] = DIRS[(rng.random() * 4) | 0]; x = (x + dx + CFG.w) % CFG.w; y = (y + dy + CFG.h) % CFG.h;
    }
  }
  return out;
}

// ---------- the substrate ----------
class Substrate {
  constructor(seed, rules) {
    this.rules = Object.assign({}, RULES, rules || {}); this.rng = new Mulberry(seed); this.tick = 0;
    this.rock = this.rules.rock ? blobs(this.rng, CFG.rockFraction, 200) : new Uint8Array(N);
    this.kind = this.rules.kinds ? blobs(this.rng, 0.5, 1500, 10) : new Uint8Array(N); // the two kinds of ground in small patches
    this.soil = new Int32Array(N); for (let i = 0; i < N; i++) this.soil[i] = this.rock[i] ? 0 : CFG.soil;
    this.food = new Int32Array(N); this.green = new Int32Array(N);
    this.lightRow = new Float64Array(CFG.w); this.contrast = 0; this.eclipse = 0; this.peak = 0;
    for (let t = 0; t < CFG.warmup; t++) this.step(); // the sun was there before life: a grown world at tick 0
    this.tick = 0;
  }
  light() {
    const t = this.tick;
    let c = CFG.contrastMin + (1 - CFG.contrastMin) * 0.5 * (1 - Math.cos(2 * Math.PI * t / CFG.season));
    if (this.eclipse > 0) { c *= 0.15; this.eclipse--; }
    this.contrast = c; this.peak = ((t / CFG.day) % 1) * CFG.w;
    for (let x = 0; x < CFG.w; x++) this.lightRow[x] = 0.5 + 0.5 * c * Math.cos(2 * Math.PI * (x / CFG.w - t / CFG.day));
  }
  step() {
    this.light();
    const { soil, food, green, rng, rock } = this, ripen = this.rules.ripen;
    // growth: fertility scales with the soil, up to four units
    for (let i = 0; i < N; i++) {
      const u = rng.random();
      if (rock[i] || soil[i] <= 0 || food[i] + green[i] >= CFG.foodCap) continue;
      if (u < CFG.grow * this.lightRow[i % CFG.w] * Math.min(soil[i], 4) / 4) { soil[i]--; if (ripen) green[i]++; else food[i]++; }
    }
    if (ripen) for (let i = 0; i < N; i++) { const u = rng.random(); if (green[i] > 0 && u < 2 * this.lightRow[i % CFG.w] / CFG.ripenTicks) { green[i]--; food[i]++; } }
    for (let i = 0; i < N; i++) { const u = rng.random(); if (u < CFG.decay && food[i] > 0) { food[i]--; soil[i]++; } }
    const leaving = new Uint8Array(N), dir = new Uint8Array(N);
    for (let i = 0; i < N; i++) { const u = rng.random(); leaving[i] = (u < CFG.diffuse && soil[i] > 0) ? 1 : 0; }
    for (let i = 0; i < N; i++) { const d = rng.random(); dir[i] = Math.min((d * 4) | 0, 3); }
    for (let i = 0; i < N; i++) if (leaving[i]) {
      const x = i % CFG.w, y = (i / CFG.w) | 0; const [dx, dy] = DIRS[dir[i]];
      const j = ((y + dy + CFG.h) % CFG.h) * CFG.w + (x + dx + CFG.w) % CFG.w;
      if (rock[j]) continue; soil[i]--; soil[j]++;
    }
    this.tick++;
  }
  dark(i) { return this.rules.night && this.lightRow[i % CFG.w] < CFG.nightBelow; }
  get mass() { let m = 0; for (let i = 0; i < N; i++) m += this.soil[i] + this.food[i] + this.green[i]; return m; }
}

// ---------- the genome: what is inherited ----------
// The body of the brain is a body plan: how wide the perception population is,
// how many recursive observer stages stand above it, how many signals each
// patch reads, how strongly parameters are anchored when it learns, and which
// sense groups reach it at all. A child inherits the plan, never the parent's
// settled states or learned relations.
const GENE = { radius: [1, 2], width: [6, 10, 14, 20], depth: [1, 2, 3, 4], fanin: [6, 9, 12, 16], prior: [0.1, 0.3, 0.6, 1.0], horizon: [0, 1, 2], symbols: [0, 1, 2, 4], splitAt: [24, 32, 48, 64], eps: [0.02, 0.05, 0.1, 0.2], gamma: [0, 0.3, 0.6, 0.9] };
const G = (g, k) => GENE[k][g[k]];
const bit = name => 1 << GROUP_NAMES.indexOf(name);
const FIRST_MASK = bit('food') | bit('occ') | bit('energy') | bit('out') | bit('light');

function firstGenome(rng, available) { // the founders read everything the world offers and carry one observer stage between perception and policy
  const mask = available ? available.reduce((m, gi) => m | (1 << gi), 0) : FIRST_MASK;
  return { radius: 0, width: 1, depth: 1, fanin: 1, prior: 1, horizon: 0, symbols: 0, splitAt: 0, eps: 2, gamma: 2, hue: rng.random(),
    mask, wiring: (rng.random() * 4294967296) >>> 0 };
}
function stepGene(v, n, rng) { return Math.max(0, Math.min(n - 1, v + (rng.random() < 0.5 ? -1 : 1))); }
function mutate(g, rng, groupsAvailable) {
  const c = Object.assign({}, g);
  for (const k of Object.keys(GENE)) if (rng.random() < 0.12) c[k] = stepGene(c[k], GENE[k].length, rng);
  if (rng.random() < 0.10) { const b = 1 << (groupsAvailable[(rng.random() * groupsAvailable.length) | 0]); const m = c.mask ^ b; if (m) c.mask = m; }
  if (rng.random() < 0.03) c.wiring = (rng.random() * 4294967296) >>> 0;
  c.hue = (((g.hue + (rng.random() - 0.5) * 0.02) % 1) + 1) % 1;
  return c;
}

// ---------- the reading's layout for a rule set ----------
function layoutFor(rules, r, K) {
  const nWin = (2 * r + 1) ** 2; const groups = []; let off = 0;
  const add = (name, size) => { groups.push({ name, off, size }); off += size; };
  add('food', nWin * 9); add('occ', nWin); add('energy', 4); add('out', OUTCOMES.length); add('light', 3);
  if (rules.ripen) add('green', nWin * 4);
  if (rules.rock) add('rock', nWin);
  if (rules.kinds) { add('kind', nWin); add('lastkind', 3); }
  if (rules.bite) add('kin', nWin);
  if (rules.night) add('dark', 1);
  if (rules.carry) add('carried', 1);
  add('heard', K + 1);
  const byName = {}; for (const g of groups) byName[g.name] = g;
  return { groups, byName, D: off, nWin, r, available: groups.map(g => GROUP_NAMES.indexOf(g.name)) };
}

// perception plus `depth` observer stages, tapering toward the policy stage that carries the action values
function stageWidths(width, depth, A) {
  const policy = Math.max(A, Math.round(width / 2));
  const w = [];
  for (let s = 0; s <= depth; s++) w.push(Math.max(policy, Math.round(width + (policy - width) * s / depth)));
  return w;
}

// ---------- the brain: a deep recursive settlement network developed from the genome ----------
// Populations of patches; the first reads the masked senses, every later stage
// reads the senses and observes the states and prediction errors of all earlier
// stages; the last stage's first A states are the action values. One settle per
// tick answers all actions jointly; one anchored parameter repair per tick
// admits the previous transition against the Reinforcement one-step target.
class Brain {
  constructor(g, rules) {
    this.g = g; this.rules = rules; this.r = G(g, 'radius'); this.K = G(g, 'symbols'); this.horizon = G(g, 'horizon');
    this.actions = actionsFor(rules, this.K); this.A = this.actions.length; this.waitIndex = this.actions.indexOf('wait');
    this.eps = G(g, 'eps'); this.gamma = G(g, 'gamma'); this.prior = G(g, 'prior');
    this.L = layoutFor(rules, this.r, this.K); this.D = this.L.D; this.nWin = this.L.nWin;
    this.x = new Uint8Array(this.D); this.q = new Float32Array(this.A);
    this.depth = G(g, 'depth'); this.width = G(g, 'width'); this.F = G(g, 'fanin');
    this.widths = stageWidths(this.width, this.depth, this.A);
    this.pops = []; let off = 0;
    for (const w of this.widths) { this.pops.push({ off, n: w }); off += w; }
    this.P = off; this.polOff = this.pops[this.pops.length - 1].off;
    const P = this.P, F = this.F, D = this.D;
    // the sense units the mask names; every stage reads them, so depth never hides the world
    const sensed = []; for (const grp of this.L.groups) if (g.mask & bit(grp.name)) for (let u = 0; u < grp.size; u++) sensed.push(grp.off + u);
    this.readUnits = sensed.length;
    // wiring, developed deterministically from the genome: connection index space is
    // [0,D) the senses, [D,D+P) patch states, [D+P,D+2P) patch prediction errors
    const dev = new Mulberry(g.wiring ^ (sensed.length * 2654435761));
    this.cIdx = new Int32Array(P * F); this.W = new Float64Array(P * F); this.Bs = new Float64Array(P);
    for (let s = 0; s < this.pops.length; s++) {
      const pop = this.pops[s], lower = pop.off; // patches [0, lower) belong to earlier stages
      for (let i = pop.off; i < pop.off + pop.n; i++) {
        const base = i * F;
        for (let j = 0; j < F; j++) {
          let k = 0;
          const kind = s === 0 ? 0 : j % 3; // an observer stage reads senses, observes states, observes errors, in equal parts
          if (kind === 0 || lower === 0) k = sensed.length ? sensed[(dev.random() * sensed.length) | 0] : 0;
          else if (kind === 1) k = D + ((dev.random() * lower) | 0);
          else k = D + P + ((dev.random() * lower) | 0);
          this.cIdx[base + j] = k;
          this.W[base + j] = (dev.random() * 2 - 1) * BRAIN.initScale;
        }
        this.Bs[i] = (dev.random() * 2 - 1) * BRAIN.initScale;
      }
    }
    this.C = P * F;
    this.hears = (g.mask & bit('heard')) !== 0;
    // live activity and the solver's working memory, allocated once
    this.s = new Float64Array(P); this.e = new Float64Array(P); this.pv = new Float64Array(P);
    this.gS = new Float64Array(P); this.gE = new Float64Array(P); this.gW = new Float64Array(P * F); this.gB = new Float64Array(P);
    this.sT = new Float64Array(P); this.wT = new Float64Array(P * F); this.bT = new Float64Array(P);
    this.dS = new Float64Array(P); this.dW = new Float64Array(P * F); this.dB = new Float64Array(P);
    this.oS = new Float64Array(P); this.oW = new Float64Array(P * F); this.oB = new Float64Array(P);
    this.Wa = new Float64Array(P * F); this.Ba = new Float64Array(P); this.sSnap = new Float64Array(P);
    this.sig = new Float64Array(D + 2 * P);
    this.hS = [new Float64Array(P), new Float64Array(P), new Float64Array(P)]; // lookahead levels
    this.hE = [new Float64Array(P), new Float64Array(P), new Float64Array(P)];
    this.hP = [new Float64Array(P), new Float64Array(P), new Float64Array(P)];
    this.hQ = [new Float32Array(this.A), new Float32Array(this.A), new Float32Array(this.A)];
    this.pendX = new Uint8Array(this.D); this.pendS = new Float64Array(P); this.pending = false; this.pendA = -1; this.pendQ = 0;
    this.sweepsTick = 0; this.lastSettle = 0; this.lastLearn = 0; this.imagined = 0; this.lastDelta = 0;
    this.decides = 0; this.decideOk = 0; this.learns = 0; this.learnOk = 0; this.waits = 0; this.drops = 0; this.skips = 0; this.tickCount = 0;
    this.settledOk = false;
    // the hatchling settles once before its first reading: a rest state to warm-start every later solve
    this.x.fill(0);
    if (this.repair(this.x, this.s, this.e, this.pv, -1, 0, false, BRAIN.birthBudget) < 0)
      this.repair(this.x, this.s, this.e, this.pv, -1, 0, false, 4 * BRAIN.birthBudget);
  }

  read(pop, c) {
    const x = this.x; x.fill(0); const s = pop.sub, r = this.r, L = this.L, B = L.byName; let q = 0;
    this.sweepsTick = 0; this.imagined = 0; this.tickCount++;
    for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++, q++) {
      const i = ((c.y + dy + CFG.h) % CFG.h) * CFG.w + (c.x + dx + CFG.w) % CFG.w;
      if (B.rock) x[B.rock.off + q] = s.rock[i];
      if (B.kind) x[B.kind.off + q] = s.kind[i];
      if (s.dark(i)) continue; // nothing else is seen in the dark
      x[B.food.off + q * 9 + Math.min(s.food[i], 8)] = 1;
      if (B.green) x[B.green.off + q * 4 + Math.min(s.green[i], 3)] = 1;
      const k = pop.occ[i];
      if (k >= 0 && k !== c.slot) { x[B.occ.off + q] = 1; if (B.kin && pop.creatures[k].lineage === c.lineage) x[B.kin.off + q] = 1; }
    }
    x[B.energy.off + Math.min(3, (c.energy * 4 / G(this.g, 'splitAt')) | 0)] = 1;
    x[B.out.off + c.outcome] = 1;
    const l = s.lightRow[c.x]; x[B.light.off + (l < 0.4 ? 0 : l < 0.6 ? 1 : 2)] = 1;
    if (B.lastkind) x[B.lastkind.off + c.lastKind] = 1;
    if (B.dark) x[B.dark.off] = s.dark(c.y * CFG.w + c.x) ? 1 : 0;
    if (B.carried) x[B.carried.off] = c.carried;
    x[B.heard.off + Math.min(c.heard, this.K)] = 1;
  }

  // the joint energy: E = 1/2 sum e_i^2 + statePrior/2 sum x_i^2 (+ the anchor term during learning).
  // One forward pass in declaration order fills p, e and returns E; connections
  // point only at earlier stages, so every observer's error inputs are current.
  // Signals live in one flat buffer: [0,D) the senses (copied in by repair),
  // [D,D+P) patch states, [D+P,D+2P) prediction errors, written as the pass walks.
  forward(s, e, pv) {
    const { cIdx, W, Bs, F, D, P, sig } = this; const sp = BRAIN.statePrior; let E = 0;
    for (let i = 0; i < P; i++) {
      let a = Bs[i]; const base = i * F;
      for (let j = 0; j < F; j++) a += W[base + j] * sig[cIdx[base + j]];
      const p = ftanh(a); pv[i] = p;
      const x = s[i], err = x - p; e[i] = err;
      sig[D + i] = x; sig[D + P + i] = err;
      E += 0.5 * err * err + 0.5 * sp * x * x;
    }
    return E;
  }

  // exact analytic gradient by one reverse pass: observed errors carry their
  // transitive dependencies back into every state (and, when learning, into the
  // relations), so feedback flows through the whole joint problem. It expects
  // sig/e/pv from a forward pass on the same state.
  gradient(s, e, pv, withParams, pp) {
    const { cIdx, W, F, D, P, gS, gE, gW, gB, sig } = this; const sp = BRAIN.statePrior;
    for (let i = 0; i < P; i++) { gE[i] = e[i]; gS[i] = sp * s[i]; }
    if (withParams) { const { Bs, Wa, Ba } = this; for (let i = 0; i < P; i++) gB[i] = pp * (Bs[i] - Ba[i]); for (let i = 0; i < P * F; i++) gW[i] = pp * (W[i] - Wa[i]); }
    for (let i = P - 1; i >= 0; i--) {
      const ge = gE[i]; gS[i] += ge;
      const ga = -ge * (1 - pv[i] * pv[i]);
      if (ga === 0) continue;
      const base = i * F;
      if (withParams) {
        gB[i] += ga;
        for (let j = 0; j < F; j++) {
          const k = cIdx[base + j], w = W[base + j];
          gW[base + j] += ga * sig[k];
          if (k >= D) { if (k < D + P) gS[k - D] += ga * w; else gE[k - D - P] += ga * w; }
        }
      } else {
        for (let j = 0; j < F; j++) {
          const k = cIdx[base + j];
          if (k >= D) { const w = W[base + j]; if (k < D + P) gS[k - D] += ga * w; else gE[k - D - P] += ga * w; }
        }
      }
    }
  }

  // projected-gradient repair with backtracking and the BB secant step.
  // Returns accepted sweeps if the solve qualifies (projected stationarity at
  // most the tolerance over every eligible coordinate), -1 if it refuses.
  // clampIdx >= 0 fixes that policy state (a learning target); withParams also
  // repairs weights and biases toward the anchored objective. A refusal
  // restores the parameters and retains nothing.
  repair(xs, s, e, pv, clampIdx, clampVal, withParams, budget) {
    const { P, F, gS, gW, gB, sT, wT, bT, dS, dW, dB, oS, oW, oB, W, Bs } = this;
    const pp = this.prior, sb = BRAIN.stateBound, pb = BRAIN.paramBound, tol = BRAIN.tolerance;
    if (clampIdx >= 0) s[clampIdx] = clampVal;
    this.sSnap.set(s);
    const sig = this.sig; for (let i = 0; i < this.D; i++) sig[i] = xs[i]; // the sensory samples stay fixed for the whole solve
    if (withParams) { this.Wa.set(W); this.Ba.set(Bs); }
    let E = this.forward(s, e, pv); // the anchor term is zero at the anchor
    let t = BRAIN.step, sweeps = 0, haveDisp = false;
    for (;;) {
      this.gradient(s, e, pv, withParams, pp);
      // the qualification residual: a unit projected step, clamped coordinates excluded
      let res = 0;
      for (let i = 0; i < P; i++) { if (i === clampIdx) continue; const z = s[i]; const d = Math.abs(z - Math.min(sb, Math.max(-sb, z - gS[i]))); if (d > res) res = d; }
      if (withParams) {
        for (let i = 0; i < P * F; i++) { const z = W[i]; const d = Math.abs(z - Math.min(pb, Math.max(-pb, z - gW[i]))); if (d > res) res = d; }
        for (let i = 0; i < P; i++) { const z = Bs[i]; const d = Math.abs(z - Math.min(pb, Math.max(-pb, z - gB[i]))); if (d > res) res = d; }
      }
      if (res <= tol) return sweeps; // qualified; live arrays hold the settled proposal
      if (sweeps >= budget) break;   // budget exhausted: refuse
      // the BB secant step from the previous accepted displacement and gradient change
      if (haveDisp) {
        let ss = 0, sy = 0;
        for (let i = 0; i < P; i++) { if (i === clampIdx) continue; ss += dS[i] * dS[i]; sy += dS[i] * (gS[i] - oS[i]); }
        if (withParams) {
          for (let i = 0; i < P * F; i++) { ss += dW[i] * dW[i]; sy += dW[i] * (gW[i] - oW[i]); }
          for (let i = 0; i < P; i++) { ss += dB[i] * dB[i]; sy += dB[i] * (gB[i] - oB[i]); }
        }
        t = (sy > 0 && isFinite(sy) && ss > 0) ? ss / sy : BRAIN.step;
        if (!isFinite(t) || t <= 0) t = BRAIN.step;
      }
      oS.set(gS); if (withParams) { oW.set(gW); oB.set(gB); }
      // backtracking line search: project, demand a finite negative slope and sufficient decrease
      let accepted = false;
      for (let bt = 0; bt < BRAIN.backtracks; bt++, t *= 0.5) {
        let slope = 0;
        for (let i = 0; i < P; i++) {
          if (i === clampIdx) { sT[i] = s[i]; continue; }
          const z = Math.min(sb, Math.max(-sb, s[i] - t * gS[i])); sT[i] = z; slope += gS[i] * (z - s[i]);
        }
        if (withParams) {
          for (let i = 0; i < P * F; i++) { const z = Math.min(pb, Math.max(-pb, W[i] - t * gW[i])); wT[i] = z; slope += gW[i] * (z - W[i]); }
          for (let i = 0; i < P; i++) { const z = Math.min(pb, Math.max(-pb, Bs[i] - t * gB[i])); bT[i] = z; slope += gB[i] * (z - Bs[i]); }
        }
        if (!(slope < 0) || !isFinite(slope)) continue;
        let Et;
        if (withParams) {
          for (let i = 0; i < P; i++) dS[i] = sT[i] - s[i];
          for (let i = 0; i < P * F; i++) dW[i] = wT[i] - W[i];
          for (let i = 0; i < P; i++) dB[i] = bT[i] - Bs[i];
          W.set(wT); Bs.set(bT); // the trial parameters go live for the forward pass and revert on rejection
          Et = this.forward(sT, this.hE[2], this.hP[2]);
          let anchor = 0;
          for (let i = 0; i < P * F; i++) { const dv = W[i] - this.Wa[i]; anchor += dv * dv; }
          for (let i = 0; i < P; i++) { const dv = Bs[i] - this.Ba[i]; anchor += dv * dv; }
          Et += 0.5 * pp * anchor;
          if (Et <= E + 1e-4 * slope) { s.set(sT); e.set(this.hE[2]); pv.set(this.hP[2]); E = Et; accepted = true; haveDisp = true; break; }
          // rejected: restore the pre-trial parameters
          for (let i = 0; i < P * F; i++) W[i] -= dW[i];
          for (let i = 0; i < P; i++) Bs[i] -= dB[i];
        } else {
          Et = this.forward(sT, this.hE[2], this.hP[2]);
          if (Et <= E + 1e-4 * slope) {
            for (let i = 0; i < P; i++) dS[i] = sT[i] - s[i];
            s.set(sT); e.set(this.hE[2]); pv.set(this.hP[2]); E = Et; accepted = true; haveDisp = true; break;
          }
        }
      }
      if (!accepted) break; // line search failed: refuse
      sweeps++;
    }
    // a refused proposal retains nothing: parameters and state return to their pre-call values
    if (withParams) { W.set(this.Wa); Bs.set(this.Ba); }
    s.set(this.sSnap); this.forward(s, e, pv);
    return -1;
  }

  settleLive() { // one joint settle of the whole brain on the current reading; the six-plus action values are the policy states
    this.decides++;
    const r = this.repair(this.x, this.s, this.e, this.pv, -1, 0, false, BRAIN.settleBudget);
    this.settledOk = r >= 0;
    if (this.settledOk) {
      this.decideOk++; this.lastSettle = r; this.sweepsTick += r;
      for (let a = 0; a < this.A; a++) this.q[a] = this.s[this.polOff + a];
    } else this.lastSettle = -1;
  }

  learn(reward) { // admit the previous transition against the Reinforcement one-step target, parameters anchored
    if (!this.pending) return;
    if (!this.settledOk) { this.pending = false; this.drops++; return; } // no qualified value for the next reading: the transition is dropped, counted
    if (reward === 0 && (this.tickCount % BRAIN.learnEvery)) { this.pending = false; this.skips++; return; } // the live cadence: rewarding transitions always, quiet ones every fourth tick
    const v = BRAIN.valueScale, rs = BRAIN.rewardScale, gm = this.gamma;
    let best = -Infinity; for (let a = 0; a < this.A; a++) if (this.q[a] > best) best = this.q[a];
    const rw = Math.max(-rs, Math.min(rs, reward));
    const target = (1 - gm) * v * (rw / rs) + gm * Math.max(-v, Math.min(v, best));
    this.lastDelta = target - this.pendQ;
    this.learns++;
    // a one-row batch: private activity from the transition's own equilibrium, shared parameters, live state preserved
    const hs = this.hS[2]; hs.set(this.pendS);
    const r = this.repair(this.pendX, hs, this.hE[1], this.hP[1], this.polOff + this.pendA, target, true, BRAIN.learnBudget);
    if (r >= 0) { this.learnOk++; this.lastLearn = r; this.sweepsTick += r; } else this.lastLearn = -1;
    this.pending = false;
  }

  imagine(x, a) { // the reading after a move, as far as the window can tell; null if the move is blocked
    const L = this.L, B = L.byName, r = this.r, wn = 2 * r + 1, [dx, dy] = DIRS[a];
    const centre = (r + dy) * wn + (r + dx);
    if ((B.rock && x[B.rock.off + centre]) || x[B.occ.off + centre]) return null;
    const y = new Uint8Array(x);
    for (const grp of L.groups) {
      const wdt = WINDOW_WIDTH[grp.name]; if (!wdt) continue;
      for (let cy = 0; cy < wn; cy++) for (let cx = 0; cx < wn; cx++) {
        const sx = cx + dx, sy = cy + dy, dst = grp.off + (cy * wn + cx) * wdt;
        if (sx < 0 || sy < 0 || sx >= wn || sy >= wn) { for (let u = 0; u < wdt; u++) y[dst + u] = 0; continue; }
        const src = grp.off + (sy * wn + sx) * wdt; for (let u = 0; u < wdt; u++) y[dst + u] = x[src + u];
      }
    }
    for (let u = 0; u < B.out.size; u++) y[B.out.off + u] = 0; y[B.out.off + 1] = 1;
    return y;
  }

  settleImagined(xs, level) { // a pure hypothetical settle on scratch activity, warm from the live state; null if it refuses
    const s = this.hS[level], e = this.hE[level], pv = this.hP[level];
    s.set(this.s);
    const r = this.repair(xs, s, e, pv, -1, 0, false, BRAIN.imagineBudget);
    this.imagined++;
    if (r < 0) return null;
    this.sweepsTick += r;
    const q = this.hQ[level];
    for (let a = 0; a < this.A; a++) q[a] = s[this.polOff + a];
    return q;
  }

  lookahead(x, depth, level) { // the best value reachable from a reading within depth moves
    const q = this.settleImagined(x, level);
    if (!q) return -Infinity;
    let best = -Infinity; for (let a = 0; a < this.A; a++) if (q[a] > best) best = q[a];
    if (depth <= 1 || level + 1 >= this.hS.length - 1) return best;
    for (let a = 0; a < 4; a++) { const y = this.imagine(x, a); if (!y) continue; const v = this.gamma * this.lookahead(y, depth - 1, level + 1); if (v > best) best = v; }
    return best;
  }

  decide(rng) { // epsilon over the settled action values, with the horizon's search over imagined readings
    if (!this.settledOk) { this.waits++; return this.waitIndex; } // a refused settle waits, explicitly
    const score = this.q.slice();
    if (this.horizon > 0) for (let a = 0; a < 4; a++) { const y = this.imagine(this.x, a); if (!y) continue; const v = this.lookahead(y, this.horizon, 0); if (v > -Infinity) score[a] = 0.5 * this.q[a] + 0.5 * this.gamma * v; }
    const u = rng.random(); let a;
    if (u < this.eps) a = (rng.random() * this.A) | 0;
    else { let best = -Infinity; a = 0; for (let i = 0; i < this.A; i++) if (score[i] > best) { best = score[i]; a = i; } }
    this.pendX.set(this.x); this.pendS.set(this.s); this.pendA = a; this.pendQ = this.q[a]; this.pending = true;
    this.score = score;
    return a;
  }

  get structurePrice() { return POP.read * this.readUnits + POP.patch * this.P + POP.conn * this.C; }
}

// ---------- the population, with the known view kept incrementally ----------
class Population {
  constructor(sub, seed) {
    this.sub = sub; this.rules = sub.rules; this.rng = new Mulberry(seed); this.nextId = 0; this.creatures = []; this.births = 0; this.deaths = 0;
    this.count = new Int32Array(N); this.sum = new Float64Array(N); this.sumsq = new Float64Array(N); this.sumTick = new Float64Array(N);
    this.occ = new Int32Array(N).fill(-1); this.spoken = []; this.bitten = []; this.events = []; this.bites = 0; this.available = layoutFor(this.rules, 1, 0).available; this.onDeath = null;
    this.founder = () => firstGenome(this.rng, this.available);
    for (let k = 0; k < POP.initial; k++) {
      const x = (this.rng.random() * CFG.w) | 0, y = (this.rng.random() * CFG.h) | 0, i = y * CFG.w + x;
      if (this.occ[i] >= 0 || sub.rock[i]) continue;
      this.spawn(x, y, POP.birth, this.founder(), null, null); this.occ[i] = 1;
    }
    this.reindex();
  }
  make(x, y, energy, g, lineage, parent) {
    const id = this.nextId++;
    return { id, x, y, energy, g, brain: new Brain(g, this.rules), lineage: lineage === null ? id : lineage, parent, born: this.sub.tick, age: 0, last: 5, outcome: 0, heard: 0, symbol: 0, symbolPrev: 0, lastKind: 2, carried: 0, gut: [], reward: 0, mem: new Map(), slot: -1, px: x, py: y, face: 2, eats: 0, bites: 0, bitten: 0 };
  }
  spawn(x, y, energy, g, lineage, parent) { const c = this.make(x, y, energy, g, lineage, parent); this.creatures.push(c); return c; }
  get held() { let m = 0; for (const c of this.creatures) m += c.energy + c.carried + c.gut.length; return m; }
  get mass() { return this.sub.mass + this.held; }
  record(c, i, food) {
    const old = c.mem.get(i);
    if (old !== undefined) { const f = old & 15, t = old >>> 4; this.count[i]--; this.sum[i] -= f; this.sumsq[i] -= f * f; this.sumTick[i] -= t; }
    c.mem.set(i, food | (this.sub.tick << 4));
    this.count[i]++; this.sum[i] += food; this.sumsq[i] += food * food; this.sumTick[i] += this.sub.tick;
  }
  forget(c) { for (const [i, v] of c.mem) { const f = v & 15, t = v >>> 4; this.count[i]--; this.sum[i] -= f; this.sumsq[i] -= f * f; this.sumTick[i] -= t; } c.mem.clear(); }
  reindex() { this.occ.fill(-1); this.creatures.forEach((c, k) => { c.slot = k; this.occ[c.y * CFG.w + c.x] = k; }); }
  hear(c) {
    for (let d = 1; d <= 2; d++) for (let dy = -d; dy <= d; dy++) for (let dx = -d; dx <= d; dx++) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) !== d) continue;
      const k = this.occ[((c.y + dy + CFG.h) % CFG.h) * CFG.w + (c.x + dx + CFG.w) % CFG.w];
      if (k >= 0 && this.creatures[k].symbolPrev > 0) return this.creatures[k].symbolPrev;
    }
    return 0;
  }
  step() {
    const s = this.sub, cs = this.creatures, n = cs.length, R = this.rules; this.reindex(); this.spoken.length = 0; this.bitten.length = 0; this.events.length = 0;
    for (const c of cs) { c.symbolPrev = c.symbol; c.symbol = 0; c.px = c.x; c.py = c.y; }
    const order = new Int32Array(n); for (let i = 0; i < n; i++) order[i] = i;
    const draws = new Float64Array(Math.max(n - 1, 0)); for (let i = 0; i < draws.length; i++) draws[i] = this.rng.random();
    for (let i = n - 1; i > 0; i--) { const j = (draws[n - 1 - i] * (i + 1)) | 0; const t = order[i]; order[i] = order[j]; order[j] = t; }
    for (let qq = 0; qq < n; qq++) {
      const k = order[qq], c = cs[k], b = c.brain; c.age++;
      const r = b.r;
      for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) { const i = ((c.y + dy + CFG.h) % CFG.h) * CFG.w + (c.x + dx + CFG.w) % CFG.w; if (!s.dark(i)) this.record(c, i, s.food[i]); }
      c.heard = b.hears ? this.hear(c) : 0;
      b.read(this, c); b.settleLive(); b.learn(c.reward);
      const a = b.decide(this.rng), name = b.actions[a]; c.last = a; const before = c.energy; let moved = false, extra = 0;
      while (c.gut.length && c.gut[0] <= s.tick) { c.gut.shift(); c.energy++; } // digestion: a unit eaten digestTicks ago becomes energy now
      const here = c.y * CFG.w + c.x;
      if (a < 4) {
        const [dx, dy] = DIRS[a]; const nx = (c.x + dx + CFG.w) % CFG.w, ny = (c.y + dy + CFG.h) % CFG.h, ni = ny * CFG.w + nx;
        c.face = a;
        if (this.occ[ni] < 0 && !s.rock[ni]) { this.occ[here] = -1; this.occ[ni] = k; c.x = nx; c.y = ny; moved = true; c.outcome = 1; } else c.outcome = 2;
      } else if (name === 'eat') {
        if (s.food[here] > 0) {
          s.food[here]--;
          if (R.kinds && c.lastKind === s.kind[here] && this.rng.random() < 0.5) { s.food[here]++; c.outcome = 6; } /* the same kind again digests half the time; the unit stays otherwise */ else { if (R.digest) c.gut.push(s.tick + CFG.digestTicks); else c.energy++; c.lastKind = s.kind[here]; c.outcome = 3; c.eats++; this.events.push({ kind: 'eat', c }); }
          if (c.outcome === 6) this.events.push({ kind: 'spoiled', c });
        } else if (s.green[here] > 0) { s.green[here]--; s.soil[here]++; c.outcome = 6; this.events.push({ kind: 'unripe', c }); } else c.outcome = 0;
      } else if (name === 'wait') c.outcome = 0;
      else if (name === 'bite') {
        c.outcome = 0; extra = POP.bite;
        for (const [dx, dy] of DIRS) { const j = this.occ[((c.y + dy + CFG.h) % CFG.h) * CFG.w + (c.x + dx + CFG.w) % CFG.w]; if (j < 0) continue; const v = cs[j]; const take = Math.min(3, v.energy); v.energy -= take; c.energy += take; v.outcome = 7; c.outcome = 5; this.bites++; c.bites++; v.bitten++; c.face = DIRS.findIndex(d => d[0] === dx && d[1] === dy); this.bitten.push(v); this.events.push({ kind: 'bite', c, v, take }); break; }
      } else if (name === 'dig') { if (c.carried === 0 && s.soil[here] > 0) { s.soil[here]--; c.carried = 1; c.outcome = 3; this.events.push({ kind: 'dig', c }); } else c.outcome = 0; }
      else if (name === 'drop') { if (c.carried) { s.soil[here]++; c.carried = 0; c.outcome = 3; this.events.push({ kind: 'drop', c }); } else c.outcome = 0; }
      else { c.symbol = a - b.actions.indexOf('say 1') + 1; c.outcome = 4; this.spoken.push(c); this.events.push({ kind: 'speak', c, symbol: c.symbol }); }
      // the price of this tick: existing, the senses read, the brain's structure, and every accepted repair sweep it ran
      const price = POP.base + b.structurePrice + POP.sweep * b.sweepsTick + (moved ? POP.move : 0) + (c.outcome === 4 ? POP.emit : 0) + extra;
      if (this.rng.random() < price) { c.energy--; s.soil[c.y * CFG.w + c.x]++; }
      c.reward = c.energy - before;
    }
    const survivors = [];
    for (const c of cs) { if (c.energy <= 0) { this.deaths++; s.soil[c.y * CFG.w + c.x] += c.carried + c.energy + c.gut.length; c.carried = 0; c.energy = 0; c.gut.length = 0; this.forget(c); c.dead = true; c.diedAt = s.tick; this.events.push({ kind: 'die', c }); if (this.onDeath) this.onDeath(c); continue; } survivors.push(c); }
    this.creatures = survivors; this.reindex();
    const children = [];
    for (const c of this.creatures) {
      const splitAt = G(c.g, 'splitAt');
      if (c.energy < splitAt || this.creatures.length + children.length >= POP.max) continue;
      const free = DIRS.filter(([dx, dy]) => { const j = ((c.y + dy + CFG.h) % CFG.h) * CFG.w + (c.x + dx + CFG.w) % CFG.w; return this.occ[j] < 0 && !s.rock[j]; });
      if (!free.length) continue;
      const [dx, dy] = free[(this.rng.random() * free.length) | 0];
      const nx = (c.x + dx + CFG.w) % CFG.w, ny = (c.y + dy + CFG.h) % CFG.h;
      const share = c.energy >> 1; c.energy -= share;
      const child = this.make(nx, ny, share, mutate(c.g, this.rng, this.available), c.lineage, c.id);
      this.occ[ny * CFG.w + nx] = 1; children.push(child); this.births++; this.events.push({ kind: 'birth', c: child, parent: c });
    }
    this.creatures.push(...children); this.reindex();
  }
}

function mutualInformation(counts) { // counts: array of rows (symbol) of arrays (state)
  let n = 0; const rs = counts.map(r => r.reduce((a, b) => a + b, 0)); const cols = counts[0].length; const cs = new Array(cols).fill(0);
  for (const r of counts) r.forEach((v, j) => { cs[j] += v; n += v; });
  if (!n) return 0; let mi = 0;
  counts.forEach((r, i) => r.forEach((v, j) => { if (v > 0) mi += v / n * Math.log2((v / n) / ((rs[i] / n) * (cs[j] / n))); }));
  return mi;
}

return { Mulberry, RULES, CFG, POP, BRAIN, N, DIRS, OUTCOMES, GROUP_NAMES, GENE, G, bit, Substrate, Brain, Population, actionsFor, layoutFor, stageWidths, mutate, firstGenome, mutualInformation };
});
