// A JavaScript port of the Cadence 0.50.0 reference engine, for brains that are born and learn in the browser.
//
// It carries the parts the arcade uses: the seeded wiring of `Cortex`, the joint repair of `_repair.settle`
// (queries, live steps and batch admission with private row states, shared parameters and one parameter
// anchor), the `Brain` bookkeeping around it, and the `Reinforcement` helper with its replay store. Python's
// `random` module is reproduced (Mersenne Twister, `random`, `getrandbits`, `shuffle`, `uniform`, `choice`,
// `sample`) so that a brain born here from a seed carries exactly the weights the library would give it, and
// so that the learner draws the same exploration and replay samples.
//
// Numerics follow cadence/_repair.py term by term. Energies, slopes, distances and curvatures are summed exactly
// (Shewchuk's fsum, as the library does). Each patch's drive is summed with Neumaier compensation in the library's
// term order (bias first, then incoming connections); the library sums it exactly, and the difference is far below
// the settle tolerance. Everything else (gradient accumulation, projections, the line search and its acceptance
// rule, the secant step, qualification) is the same arithmetic in the same order. parity.mjs measures the
// agreement against the library on recorded fixtures.

export function bitLength(n) {
  return n === 0 ? 0 : 32 - Math.clz32(n);
}

// Python's random.Random: MT19937 seeded through init_by_array, 53-bit doubles, rejection sampling below n.
export class PyRandom {
  constructor(seed = 0) {
    this.mt = new Uint32Array(624);
    this.index = 624;
    this.seed(seed);
  }

  _initGenrand(s) {
    const mt = this.mt;
    mt[0] = s >>> 0;
    for (let i = 1; i < 624; i++) {
      const p = mt[i - 1] ^ (mt[i - 1] >>> 30);
      mt[i] = (Math.imul(1812433253, p) + i) >>> 0;
    }
    this.index = 624;
  }

  seed(seed) {
    if (!Number.isInteger(seed) || seed < 0 || seed > Number.MAX_SAFE_INTEGER) throw new Error('seed must be a nonnegative integer');
    const key = [];
    let n = seed;
    do { key.push(n % 4294967296); n = Math.floor(n / 4294967296); } while (n > 0);
    this._initGenrand(19650218);
    const mt = this.mt, N = 624;
    let i = 1, j = 0;
    for (let k = Math.max(N, key.length); k > 0; k--) {
      const p = mt[i - 1] ^ (mt[i - 1] >>> 30);
      mt[i] = ((mt[i] ^ Math.imul(p, 1664525)) >>> 0) + key[j] + j;
      i++; j++;
      if (i >= N) { mt[0] = mt[N - 1]; i = 1; }
      if (j >= key.length) j = 0;
    }
    for (let k = N - 1; k > 0; k--) {
      const p = mt[i - 1] ^ (mt[i - 1] >>> 30);
      mt[i] = ((mt[i] ^ Math.imul(p, 1566083941)) >>> 0) - i;
      i++;
      if (i >= N) { mt[0] = mt[N - 1]; i = 1; }
    }
    mt[0] = 0x80000000;
    this.index = N;
  }

  _genrand() {
    const mt = this.mt;
    if (this.index >= 624) {
      for (let kk = 0; kk < 624; kk++) {
        const y = (mt[kk] & 0x80000000) | (mt[(kk + 1) % 624] & 0x7fffffff);
        mt[kk] = mt[(kk + 397) % 624] ^ (y >>> 1) ^ ((y & 1) ? 0x9908b0df : 0);
      }
      this.index = 0;
    }
    let y = mt[this.index++];
    y ^= y >>> 11;
    y ^= (y << 7) & 0x9d2c5680;
    y ^= (y << 15) & 0xefc60000;
    y ^= y >>> 18;
    return y >>> 0;
  }

  random() {
    const a = this._genrand() >>> 5, b = this._genrand() >>> 6;
    return (a * 67108864 + b) / 9007199254740992;
  }

  getrandbits(k) {
    if (k <= 0) return 0;
    if (k > 32) throw new Error('getrandbits above 32 bits is not needed here');
    return this._genrand() >>> (32 - k);
  }

  randbelow(n) {
    const k = bitLength(n);
    let r = this.getrandbits(k);
    while (r >= n) r = this.getrandbits(k);
    return r;
  }

  shuffle(x) {
    for (let i = x.length - 1; i >= 1; i--) {
      const j = this.randbelow(i + 1);
      const t = x[i]; x[i] = x[j]; x[j] = t;
    }
  }

  uniform(a, b) {
    return a + (b - a) * this.random();
  }

  choice(seq) {
    if (!seq.length) throw new Error('Cannot choose from an empty sequence');
    return seq[this.randbelow(seq.length)];
  }

  // random.sample(range(n), k)
  sample(n, k) {
    if (!(k >= 0 && k <= n)) throw new Error('Sample larger than population or is negative');
    const result = new Array(k);
    let setsize = 21;
    if (k > 5) setsize += Math.pow(4, Math.ceil(Math.log(k * 3) / Math.log(4)));
    if (n <= setsize) {
      const pool = new Array(n);
      for (let i = 0; i < n; i++) pool[i] = i;
      for (let i = 0; i < k; i++) {
        const j = this.randbelow(n - i);
        result[i] = pool[j];
        pool[j] = pool[n - i - 1];
      }
    } else {
      const selected = new Set();
      for (let i = 0; i < k; i++) {
        let j = this.randbelow(n);
        while (selected.has(j)) j = this.randbelow(n);
        selected.add(j);
        result[i] = j;
      }
    }
    return result;
  }

  getState() { return { mt: Uint32Array.from(this.mt), index: this.index }; }
  setState(s) { this.mt.set(s.mt); this.index = s.index; }
}

// Exactly rounded sum of finite doubles (Shewchuk's partials with Python's round-half-even correction).
const partials = new Float64Array(2048);
export function fsum(terms, count = terms.length) {
  let n = 0;
  for (let k = 0; k < count; k++) {
    let x = terms[k], i = 0;
    for (let j = 0; j < n; j++) {
      let y = partials[j];
      if (Math.abs(x) < Math.abs(y)) { const t = x; x = y; y = t; }
      const hi = x + y, lo = y - (hi - x);
      if (lo !== 0) partials[i++] = lo;
      x = hi;
    }
    if (!Number.isFinite(x)) throw new Error('fsum of a nonfinite value');
    partials[i] = x;
    n = i + 1;
  }
  if (n === 0) return 0;
  let m = n - 1, hi = partials[m], lo = 0;
  while (m > 0) {
    const x = hi, y = partials[--m];
    hi = x + y;
    const yr = hi - x;
    lo = y - yr;
    if (lo !== 0) break;
  }
  if (m > 0 && ((lo < 0 && partials[m - 1] < 0) || (lo > 0 && partials[m - 1] > 0))) {
    const y = lo * 2, x = hi + y, yr = x - hi;
    if (y === yr) hi = x;
  }
  return hi;
}

const ulpView = new DataView(new ArrayBuffer(8));
export function ulp(x) {
  x = Math.abs(x);
  if (!Number.isFinite(x)) return x;
  if (x === Number.MAX_VALUE) return Math.pow(2, 971);
  ulpView.setFloat64(0, x);
  ulpView.setBigUint64(0, ulpView.getBigUint64(0) + 1n);
  return ulpView.getFloat64(0) - x;
}

const clip = (v, bound) => Math.min(bound, Math.max(-bound, v));
const projected = (x, g, bound) => (g >= 0 ? Math.min(g, x + bound) : Math.max(g, x - bound));

export const KIND = { input: 0, state: 1, residual: 2 };
const KIND_NAMES = ['input', 'state', 'residual'];

// Immutable topology: kinds/sources/targets in edge order, incoming edges per target in insertion order, and the
// residual order (every error source before its consumer, found exactly as the library does).
export class Graph {
  constructor(nInputs, nPatches, kinds, sources, targets) {
    const E = kinds.length;
    if (sources.length !== E || targets.length !== E) throw new Error('edge arrays differ in length');
    this.nInputs = nInputs; this.nPatches = nPatches; this.nEdges = E;
    this.kinds = Uint8Array.from(kinds); this.sources = Int32Array.from(sources); this.targets = Int32Array.from(targets);
    const P = nPatches, start = new Int32Array(P + 1), degree = new Int32Array(P);
    const descendants = Array.from({ length: P }, () => []);
    const seen = new Set();
    for (let e = 0; e < E; e++) {
      const k = this.kinds[e], s = this.sources[e], t = this.targets[e];
      if (k > 2 || s < 0 || t < 0 || t >= P || s >= (k === 0 ? nInputs : P)) throw new Error('edge outside its declared population');
      const key = `${k}:${s}:${t}`;
      if (seen.has(key)) throw new Error('Identical edges must not be repeated');
      seen.add(key);
      start[t + 1]++;
      if (k === 2) { descendants[s].push(t); degree[t]++; }
    }
    for (let i = 0; i < P; i++) start[i + 1] += start[i];
    const incoming = new Int32Array(E), fill = start.slice(0, P);
    for (let e = 0; e < E; e++) incoming[fill[this.targets[e]]++] = e;
    this.inStart = start; this.inEdge = incoming;
    const queue = [];
    for (let i = 0; i < P; i++) if (degree[i] === 0) queue.push(i);
    const order = [];
    let head = 0;
    while (head < queue.length) {
      const s = queue[head++];
      order.push(s);
      for (const t of descendants[s]) if (--degree[t] === 0) queue.push(t);
    }
    if (order.length !== P) throw new Error('Residual-readback dependencies must be acyclic');
    this.residualOrder = Int32Array.from(order);
    // Slot order: every target's incoming connections contiguous, sensor connections first, then live states, then
    // observed errors. The hot loops stream through memory in this order; weights are permuted into it for a solve.
    // (Within one target the library's term order interleaves kinds; sums are exact or compensated, and gradient
    // contributions within a target go to distinct accumulators, so the grouping changes no result.)
    this.segA = new Int32Array(P + 1); this.segB = new Int32Array(P); this.segC = new Int32Array(P);
    this.slotEdge = new Int32Array(E); this.slotSrc = new Int32Array(E);
    let k = 0;
    for (let t = 0; t < P; t++) {
      this.segA[t] = k;
      for (const kind of [0, 1, 2]) {
        if (kind === 1) this.segB[t] = k;
        if (kind === 2) this.segC[t] = k;
        for (let j = start[t]; j < start[t + 1]; j++) {
          const e = incoming[j];
          if (this.kinds[e] === kind) { this.slotEdge[k] = e; this.slotSrc[k] = this.sources[e]; k++; }
        }
      }
    }
    this.segA[P] = k;
  }

  toSlot(edgeValues, out = new Float64Array(this.nEdges)) {
    for (let k = 0; k < this.nEdges; k++) out[k] = edgeValues[this.slotEdge[k]];
    return out;
  }

  toEdge(slotValues, out = new Float64Array(this.nEdges)) {
    for (let k = 0; k < this.nEdges; k++) out[this.slotEdge[k]] = slotValues[k];
    return out;
  }

  edge(e) { return [KIND_NAMES[this.kinds[e]], this.sources[e], this.targets[e]]; }
}

// One solve's buffers: two points (current and proposed, swapped on acceptance) and shared scratch space.
class Workspace {
  constructor(graph, B, learn) {
    const P = graph.nPatches, E = graph.nEdges;
    const point = () => ({
      state: new Float64Array(B * P), weights: learn ? new Float64Array(E) : null, biases: new Float64Array(P),
      predictions: new Float64Array(B * P), errors: new Float64Array(B * P), gradU: new Float64Array(B * P),
      gradW: learn ? new Float64Array(E) : null, gradB: learn ? new Float64Array(P) : null, energy: 0,
    });
    this.a = point(); this.b = point();
    this.sq = new Float64Array(P); this.adj = new Float64Array(P); this.rowEnergy = new Float64Array(B);
    this.compW = learn && B > 1 ? new Float64Array(E) : null; this.compB = learn && B > 1 ? new Float64Array(P) : null;
    this.dw = learn ? new Float64Array(E) : null; this.db = learn ? new Float64Array(P) : null;
    this.tw = learn ? new Float64Array(E + P) : null;
    const nAll = B * P + (learn ? E + P : 0);
    this.terms = new Float64Array(nAll); this.changes2 = new Float64Array(nAll); this.changesY = new Float64Array(nAll);
    this.fixedMask = new Uint8Array(B * P); this.fixedValue = new Float64Array(B * P);
  }
}

// Energy, exact predictions and errors, and the analytic derivatives of the batch objective at one point: private
// row states, shared parameters (slot order), mean row energy, one parameter anchor. Row state gradients are left
// unscaled (the library's gradient_state_unscaled); the mean objective's state derivative is that over the row count.
function evaluate(graph, cfg, inputs, pt, learn, B, anchorW, anchorB, ws, work) {
  const P = graph.nPatches, E = graph.nEdges, nI = graph.nInputs;
  const order = graph.residualOrder, segA = graph.segA, segB = graph.segB, segC = graph.segC, src = graph.slotSrc;
  const { state, weights, biases, predictions, errors, gradU, gradW, gradB } = pt;
  const { sq, adj, rowEnergy, compW, compB } = ws;
  const prior = cfg.state_prior;
  if (learn) { gradW.fill(0); gradB.fill(0); if (B > 1) { compW.fill(0); compB.fill(0); } }
  for (let r = 0; r < B; r++) {
    const xo = r * P, io = r * nI;
    for (let idx = 0; idx < P; idx++) {
      const t = order[idx];
      let s = biases[t], c = 0;
      const a0 = segA[t], b0 = segB[t], c0 = segC[t], e0 = segA[t + 1];
      for (let k = a0; k < b0; k++) {
        const v = weights[k] * inputs[io + src[k]], u = s + v;
        c += Math.abs(s) >= Math.abs(v) ? (s - u) + v : (v - u) + s; s = u;
      }
      for (let k = b0; k < c0; k++) {
        const v = weights[k] * state[xo + src[k]], u = s + v;
        c += Math.abs(s) >= Math.abs(v) ? (s - u) + v : (v - u) + s; s = u;
      }
      for (let k = c0; k < e0; k++) {
        const v = weights[k] * errors[xo + src[k]], u = s + v;
        c += Math.abs(s) >= Math.abs(v) ? (s - u) + v : (v - u) + s; s = u;
      }
      const a = s + c;
      if (!Number.isFinite(a)) throw new RangeError('A prediction exceeds the finite numeric range');
      const p = Math.tanh(a);
      predictions[xo + t] = p;
      errors[xo + t] = state[xo + t] - p;
    }
    for (let i = 0; i < P; i++) sq[i] = errors[xo + i] * errors[xo + i];
    let energy = 0.5 * fsum(sq, P);
    for (let i = 0; i < P; i++) sq[i] = state[xo + i] * state[xo + i];
    energy += 0.5 * prior * fsum(sq, P);
    rowEnergy[r] = energy;
    for (let i = 0; i < P; i++) { gradU[xo + i] = prior * state[xo + i]; adj[i] = errors[xo + i]; }
    for (let idx = P - 1; idx >= 0; idx--) {
      const t = order[idx], a = adj[t];
      gradU[xo + t] += a;
      const h = -a * (1.0 - predictions[xo + t] * predictions[xo + t]);
      const a0 = segA[t], b0 = segB[t], c0 = segC[t], e0 = segA[t + 1];
      if (learn && B > 1) {
        { const s0 = gradB[t], u = s0 + h; compB[t] += Math.abs(s0) >= Math.abs(h) ? (s0 - u) + h : (h - u) + s0; gradB[t] = u; }
        for (let k = a0; k < b0; k++) {
          const v = h * inputs[io + src[k]], s0 = gradW[k], u = s0 + v;
          compW[k] += Math.abs(s0) >= Math.abs(v) ? (s0 - u) + v : (v - u) + s0; gradW[k] = u;
        }
        for (let k = b0; k < c0; k++) {
          const v = h * state[xo + src[k]], s0 = gradW[k], u = s0 + v;
          compW[k] += Math.abs(s0) >= Math.abs(v) ? (s0 - u) + v : (v - u) + s0; gradW[k] = u;
          gradU[xo + src[k]] += h * weights[k];
        }
        for (let k = c0; k < e0; k++) {
          const v = h * errors[xo + src[k]], s0 = gradW[k], u = s0 + v;
          compW[k] += Math.abs(s0) >= Math.abs(v) ? (s0 - u) + v : (v - u) + s0; gradW[k] = u;
          adj[src[k]] += h * weights[k];
        }
      } else if (learn) {
        gradB[t] += h;
        for (let k = a0; k < b0; k++) gradW[k] += h * inputs[io + src[k]];
        for (let k = b0; k < c0; k++) { gradW[k] += h * state[xo + src[k]]; gradU[xo + src[k]] += h * weights[k]; }
        for (let k = c0; k < e0; k++) { gradW[k] += h * errors[xo + src[k]]; adj[src[k]] += h * weights[k]; }
      } else {
        for (let k = b0; k < c0; k++) gradU[xo + src[k]] += h * weights[k];
        for (let k = c0; k < e0; k++) adj[src[k]] += h * weights[k];
      }
    }
  }
  work.evaluations++;
  work.patch_visits += 2 * B * P;
  work.edge_visits += 2 * B * E;
  let energy = B === 1 ? rowEnergy[0] : fsum(rowEnergy, B) / B;
  if (learn) {
    if (B > 1) {
      for (let k = 0; k < E; k++) gradW[k] = (gradW[k] + compW[k]) / B;
      for (let t = 0; t < P; t++) gradB[t] = (gradB[t] + compB[t]) / B;
    }
    if (anchorW) {
      const { dw, db, tw } = ws, pp = cfg.parameter_prior;
      for (let k = 0; k < E; k++) { dw[k] = weights[k] - anchorW[k]; tw[k] = dw[k] * dw[k]; }
      for (let t = 0; t < P; t++) { db[t] = biases[t] - anchorB[t]; tw[E + t] = db[t] * db[t]; }
      if (B === 1) energy += 0.5 * pp * fsum(tw, E + P);
      else { energy += 0.5 * pp * fsum(tw, E); energy += 0.5 * pp * fsum(tw.subarray(E), P); }
      for (let k = 0; k < E; k++) gradW[k] += pp * dw[k];
      for (let t = 0; t < P; t++) gradB[t] += pp * db[t];
    }
  }
  if (!Number.isFinite(energy)) throw new RangeError('Energy or gradient exceeds the finite numeric range');
  for (let i = 0; i < B * P; i++) if (!Number.isFinite(gradU[i]) || !Number.isFinite(predictions[i])) throw new RangeError('Energy or gradient exceeds the finite numeric range');
  if (learn) {
    for (let k = 0; k < E; k++) if (!Number.isFinite(gradW[k])) throw new RangeError('Energy or gradient exceeds the finite numeric range');
    for (let t = 0; t < P; t++) if (!Number.isFinite(gradB[t])) throw new RangeError('Energy or gradient exceeds the finite numeric range');
  }
  pt.energy = energy;
  return pt;
}

function stationarity(pt, ws, learn, cfg) {
  let r = 0;
  const sb = cfg.state_bound, pb = cfg.parameter_bound, { state, weights, biases, gradU, gradW, gradB } = pt, mask = ws.fixedMask;
  for (let i = 0; i < state.length; i++) {
    if (mask[i]) continue;
    const v = Math.abs(projected(state[i], gradU[i], sb));
    if (v > r) r = v;
  }
  if (learn) {
    for (let k = 0; k < weights.length; k++) { const v = Math.abs(projected(weights[k], gradW[k], pb)); if (v > r) r = v; }
    for (let t = 0; t < biases.length; t++) { const v = Math.abs(projected(biases[t], gradB[t], pb)); if (v > r) r = v; }
  }
  return r;
}

// One joint repair with projected gradient, scalar secant steps and Armijo backtracking; cadence/_repair.settle.
// `weights0`/`anchorW` are in edge order; `weightsSlot` may supply the same weights already in slot order.
export function settleCore(graph, cfg, inputs, state0, weights0, biases0, { clamps = new Map(), learn = false, budget, B = 1, anchorW = null, anchorB = null, weightsSlot = null } = {}) {
  const P = graph.nPatches, E = graph.nEdges;
  if (inputs.length !== B * graph.nInputs || state0.length !== B * P) throw new Error('Batch inputs and states must match the declared row count');
  const sb = cfg.state_bound, pb = cfg.parameter_bound, tol = cfg.tolerance;
  for (let i = 0; i < state0.length; i++) if (Math.abs(state0[i]) > sb) throw new Error('Initial state exceeds state_bound');
  for (let e = 0; e < E; e++) if (Math.abs(weights0[e]) > pb) throw new Error('Initial parameters exceed parameter_bound');
  for (let t = 0; t < P; t++) if (Math.abs(biases0[t]) > pb) throw new Error('Initial parameters exceed parameter_bound');
  if (!learn && anchorW) throw new Error('Query solves freeze parameters and do not accept anchors');
  for (const [i, v] of clamps) if (i >= state0.length || Math.abs(v) > sb) throw new Error('Clamp index or value is outside its declared bounds');
  const ws = new Workspace(graph, B, learn);
  let cur = ws.a, prop = ws.b;
  cur.state.set(state0);
  for (const [i, v] of clamps) { cur.state[i] = v; ws.fixedMask[i] = 1; ws.fixedValue[i] = v; }
  const slotWeights = weightsSlot || graph.toSlot(weights0);
  if (learn) cur.weights.set(slotWeights); else { cur.weights = slotWeights; prop.weights = slotWeights; }
  cur.biases.set(biases0);
  let aW = null, aB = null;
  if (learn) {
    aW = anchorW ? graph.toSlot(anchorW) : Float64Array.from(cur.weights);
    aB = anchorW ? Float64Array.from(anchorB) : Float64Array.from(cur.biases);
    for (let k = 0; k < E; k++) if (Math.abs(aW[k]) > pb) throw new Error('Parameter anchors exceed parameter_bound');
    for (let t = 0; t < P; t++) if (Math.abs(aB[t]) > pb) throw new Error('Parameter anchors exceed parameter_bound');
  }
  const work = { evaluations: 0, patch_visits: 0, edge_visits: 0, proposals: 0, backtracks: 0 };
  const compute = pt => evaluate(graph, cfg, inputs, pt, learn, B, aW, aB, ws, work);
  compute(cur);
  const history = [cur.energy];
  let sweeps = 0, reason = 'budget', nextStep = cfg.step;
  const nState = B * P, nAll = nState + (learn ? E + P : 0);
  const { terms, fixedMask, fixedValue } = ws;
  for (let sweep = 0; sweep < budget; sweep++) {
    if (stationarity(cur, ws, learn, cfg) <= tol) { reason = 'qualified'; break; }
    let trial = nextStep, accepted = false;
    for (let attempt = 0; attempt < cfg.backtracks; attempt++) {
      work.proposals++;
      let moved = false;
      for (let i = 0; i < nState; i++) {
        const v = fixedMask[i] ? fixedValue[i] : clip(cur.state[i] - trial * cur.gradU[i], sb);
        prop.state[i] = v;
        if (v !== cur.state[i]) moved = true;
      }
      if (learn) {
        for (let k = 0; k < E; k++) { const v = clip(cur.weights[k] - trial * cur.gradW[k], pb); prop.weights[k] = v; if (v !== cur.weights[k]) moved = true; }
        for (let t = 0; t < P; t++) { const v = clip(cur.biases[t] - trial * cur.gradB[t], pb); prop.biases[t] = v; if (v !== cur.biases[t]) moved = true; }
      } else {
        prop.biases.set(cur.biases);
      }
      try {
        for (let i = 0; i < nState; i++) terms[i] = (cur.gradU[i] / B) * (prop.state[i] - cur.state[i]);
        if (learn) {
          for (let k = 0; k < E; k++) terms[nState + k] = cur.gradW[k] * (prop.weights[k] - cur.weights[k]);
          for (let t = 0; t < P; t++) terms[nState + E + t] = cur.gradB[t] * (prop.biases[t] - cur.biases[t]);
        }
        const slope = fsum(terms, nAll);
        compute(prop);
        accepted = moved && Number.isFinite(slope) && slope < 0 && (
          prop.energy <= cur.energy + 1e-4 * slope ||
          (Math.abs(prop.energy - cur.energy) <= 8 * ulp(cur.energy) && stationarity(prop, ws, learn, cfg) <= tol));
      } catch (error) {
        if (!(error instanceof RangeError)) throw error;
        accepted = false;
      }
      if (accepted) {
        nextStep = secantStep(cur, prop, learn, B, cfg, ws);
        const swap = cur; cur = prop; prop = swap;
        history.push(cur.energy);
        sweeps++;
        break;
      }
      work.backtracks++;
      trial *= 0.5;
    }
    if (!accepted) { reason = 'line_search'; break; }
  }
  // A fresh final qualification at the finishing point, as the library performs it.
  prop.state.set(cur.state);
  if (learn) prop.weights.set(cur.weights);
  prop.biases.set(cur.biases);
  compute(prop);
  const residual = stationarity(prop, ws, learn, cfg);
  const qualified = Number.isFinite(residual) && residual <= tol;
  if (qualified) reason = 'qualified';
  let predictionResidual = 0;
  for (let i = 0; i < prop.errors.length; i++) predictionResidual = Math.max(predictionResidual, Math.abs(prop.errors[i]));
  return { state: prop.state, weights: learn ? graph.toEdge(prop.weights) : weights0, weightsSlot: learn ? Float64Array.from(prop.weights) : slotWeights,
           biases: learn ? Float64Array.from(prop.biases) : biases0, predictions: prop.predictions, errors: prop.errors, energy: prop.energy,
           stationarity: residual, prediction_residual: predictionResidual, qualified, sweeps, reason, energy_history: history, work };
}

function secantStep(cur, prop, learn, B, cfg, ws) {
  const { changes2, changesY } = ws;
  let n = 0;
  for (let i = 0; i < cur.state.length; i++) {
    if (prop.state[i] !== cur.state[i]) {
      const s = prop.state[i] - cur.state[i], y = prop.gradU[i] / B - cur.gradU[i] / B;
      changes2[n] = s * s / B; changesY[n] = s * y; n++;
    }
  }
  if (learn) {
    for (let k = 0; k < cur.weights.length; k++) if (prop.weights[k] !== cur.weights[k]) { const s = prop.weights[k] - cur.weights[k], y = prop.gradW[k] - cur.gradW[k]; changes2[n] = s * s; changesY[n] = s * y; n++; }
    for (let t = 0; t < cur.biases.length; t++) if (prop.biases[t] !== cur.biases[t]) { const s = prop.biases[t] - cur.biases[t], y = prop.gradB[t] - cur.gradB[t]; changes2[n] = s * s; changesY[n] = s * y; n++; }
  }
  try {
    const distance = fsum(changes2, n), curvature = fsum(changesY, n);
    if (curvature > 0) {
      const estimate = distance / curvature;
      const ceiling = cfg.step * Math.pow(2, Math.min(cfg.backtracks - 1, 1023));
      if (Number.isFinite(estimate) && estimate > 0) return Math.min(estimate, ceiling);
    }
  } catch (error) { /* unsafe curvature: fall back to the configured step */ }
  return cfg.step;
}

export const DEFAULT_CONFIG = {
  seed: 0, fan_in: null, initial_scale: 0.3, settle_budget: 2048, tolerance: 1e-6, state_prior: 0.01, parameter_prior: 0.1,
  state_bound: 1.0, parameter_bound: 4.0, step: 1.0, backtracks: 32, max_patches: 10000, max_connections: 1000000, max_inputs: 1000000,
  device: 'python', dtype: 'float64',
};

const prod = shape => shape.reduce((a, b) => a * b, 1);

// Declare sensors, populations and outputs; build() wires them with the library's seeded procedure.
export class Cortex {
  constructor(options = {}) {
    this.config = { ...DEFAULT_CONFIG, ...options };
    if (this.config.initial_scale > this.config.parameter_bound) throw new Error('initial_scale must not exceed parameter_bound');
    this.nodes = new Map();
    this.inputs = []; this.populations = []; this.outputs = [];
    this.built = false;
  }

  _name(name) {
    if (this.built) throw new Error('A built layout is frozen; create a new Cortex');
    if (typeof name !== 'string' || !name) throw new Error('Names must be nonempty strings');
    if (this.nodes.has(name)) throw new Error(`Duplicate layout name: ${name}`);
    return name;
  }

  input(name, { shape }) {
    name = this._name(name);
    shape = Array.isArray(shape) ? shape.slice() : [shape];
    const node = { kind: 'input', name, shape, size: prod(shape) };
    this.inputs.push(node); this.nodes.set(name, node);
    return node;
  }

  _population(name, patches, inputs, observes) {
    for (const s of [...inputs, ...observes]) if (this.nodes.get(s.name) !== s) throw new Error('Connections must reference existing nodes in this Cortex');
    const node = { kind: 'population', name, patches, inputs: inputs.slice(), observes: observes.slice() };
    this.populations.push(node); this.nodes.set(name, node);
    return node;
  }

  column(name, { patches, inputs = [] }) {
    return this._population(this._name(name), patches, inputs, []);
  }

  observer(name, { patches, inputs = [], observes }) {
    if (!observes || !observes.length) throw new Error('An observer must observe at least one population');
    return this._population(this._name(name), patches, inputs, observes);
  }

  output(name, { shape, reads, indices = null }) {
    name = this._name(name);
    shape = Array.isArray(shape) ? shape.slice() : [shape];
    const count = prod(shape);
    if (count > reads.patches) throw new Error('Output size exceeds its source population');
    if (indices === null) indices = Array.from({ length: count }, (_, i) => i);
    const node = { kind: 'output', name, shape, reads, indices: indices.slice() };
    this.outputs.push(node); this.nodes.set(name, node);
    return node;
  }

  build() {
    if (this.built || !this.populations.length || !this.outputs.length) throw new Error('Build requires an unbuilt layout with patches and outputs');
    const cfg = this.config, rng = new PyRandom(cfg.seed);
    const inputRanges = new Map(), populationRanges = new Map();
    let nInputs = 0, nPatches = 0;
    for (const s of this.inputs) { inputRanges.set(s.name, [nInputs, nInputs + s.size]); nInputs += s.size; }
    for (const p of this.populations) { populationRanges.set(p.name, [nPatches, nPatches + p.patches]); nPatches += p.patches; }
    const kinds = [], sources = [], targets = [];
    for (const population of this.populations) {
      const groups = [];
      const seen = new Set();
      const add = (kind, name) => { const key = kind + ':' + name; if (!seen.has(key)) { seen.add(key); groups.push([kind, name]); } };
      for (const s of population.inputs) add(s.kind === 'input' ? 'input' : 'state', s.name);
      for (const s of population.observes) { add('state', s.name); add('residual', s.name); }
      const [t0, t1] = populationRanges.get(population.name);
      for (const [kind, name] of groups) {
        const [a, b] = kind === 'input' ? inputRanges.get(name) : populationRanges.get(name);
        const count = b - a;
        let fanIn = count;
        if (cfg.fan_in !== null) fanIn = Math.min(fanIn, Math.max(cfg.fan_in, Math.ceil(count / (t1 - t0))));
        if (kinds.length + (t1 - t0) * fanIn > cfg.max_connections) throw new Error('Connection budget exceeded');
        const indices = new Array(count);
        for (let i = 0; i < count; i++) indices[i] = a + i;
        rng.shuffle(indices);
        const k = KIND[kind];
        for (let local = 0, target = t0; target < t1; local++, target++) {
          for (let slot = 0; slot < fanIn; slot++) {
            kinds.push(k); sources.push(indices[(local * fanIn + slot) % count]); targets.push(target);
          }
        }
      }
    }
    const graph = new Graph(nInputs, nPatches, kinds, sources, targets);
    const scale = cfg.initial_scale, weights = new Float64Array(graph.nEdges);
    for (let e = 0; e < graph.nEdges; e++) {
      const t = graph.targets[e];
      weights[e] = rng.uniform(-1.0, 1.0) * scale / Math.sqrt(graph.inStart[t + 1] - graph.inStart[t]);
    }
    const layout = {
      inputs: this.inputs.map(i => ({ name: i.name, shape: i.shape })),
      populations: this.populations.map(p => ({ name: p.name, patches: p.patches, inputs: p.inputs.map(s => s.name), observes: p.observes.map(s => s.name) })),
      outputs: this.outputs.map(o => ({ name: o.name, shape: o.shape, reads: o.reads.name, indices: o.indices })),
    };
    this.built = true;
    return new Brain(this, graph, weights, inputRanges, populationRanges, layout);
  }
}

// A compiled layout with private parameters, live state and atomic admission; cadence/brain.py.
export class Brain {
  constructor(builder, graph, weights, inputRanges, populationRanges, layout) {
    this.config = Object.freeze({ ...builder.config });
    this.graph = graph;
    this.inputs = builder.inputs.slice(); this.populations = builder.populations.slice(); this.outputs = builder.outputs.slice();
    this.inputRanges = inputRanges; this.populationRanges = populationRanges;
    this.layout = layout;
    this.weights = weights;
    this.weightsSlot = graph.toSlot(weights);
    this.biases = new Float64Array(graph.nPatches);
    this.state = new Float64Array(graph.nPatches);
    this.eventId = -1;
    this.admissions = 0;
    this.outputIndices = this.outputs.map(o => { const [a] = populationRanges.get(o.reads.name); return o.indices.map(i => a + i); });
  }

  // Flatten a {name: values} map of every declared sensor into the solver's input vector.
  flatten(inputs) {
    const flat = new Float64Array(this.graph.nInputs);
    let supplied = 0;
    for (const source of this.inputs) {
      const values = inputs[source.name];
      if (values === undefined) throw new Error(`Supply every declared sensor exactly once; missing: ${source.name}`);
      if (values.length !== source.size) throw new Error(`${source.name} does not match shape ${JSON.stringify(source.shape)}`);
      const [a] = this.inputRanges.get(source.name);
      for (let i = 0; i < source.size; i++) {
        const v = values[i];
        if (typeof v !== 'number' || !Number.isFinite(v)) throw new Error(`${source.name} must be finite numbers`);
        flat[a + i] = v;
      }
      supplied++;
    }
    if (supplied !== Object.keys(inputs).length) throw new Error('Unknown layout reference among the supplied inputs');
    return flat;
  }

  // Output targets as clamps on their patches (a Map of patch index to value).
  clamps(targets, row = 0) {
    const clamps = new Map();
    if (!targets) return clamps;
    const width = this.graph.nPatches, sb = this.config.state_bound;
    for (const [name, values] of Object.entries(targets)) {
      const k = this.outputs.findIndex(o => o.name === name);
      if (k < 0) throw new Error(`Unknown output ${name}`);
      const output = this.outputs[k], list = typeof values === 'number' ? [values] : values;
      if (list.length !== prod(output.shape)) throw new Error(`${name} does not match shape ${JSON.stringify(output.shape)}`);
      for (let i = 0; i < list.length; i++) {
        const v = list[i], index = row * width + this.outputIndices[k][i];
        if (typeof v !== 'number' || !Number.isFinite(v) || Math.abs(v) > sb) throw new Error(`${name} clamp exceeds state_bound=${sb}`);
        if (clamps.has(index) && clamps.get(index) !== v) throw new Error(`${name} conflicts with another clamp on patch ${index}`);
        clamps.set(index, v);
      }
    }
    return clamps;
  }

  outputsFrom(state, offset = 0) {
    const out = {};
    this.outputs.forEach((o, k) => { out[o.name] = this.outputIndices[k].map(i => state[offset + i]); });
    return out;
  }

  _solve(flat, clamps, { learn, budget, B = 1 }) {
    budget = budget === undefined || budget === null ? this.config.settle_budget : budget;
    if (!Number.isInteger(budget) || budget < 0) throw new Error('budget must be an integer >= 0');
    const P = this.graph.nPatches, state = new Float64Array(B * P);
    for (let r = 0; r < B; r++) state.set(this.state, r * P);
    const result = settleCore(this.graph, this.config, flat, state, this.weights, this.biases, { clamps, learn, budget, B, weightsSlot: this.weightsSlot });
    result.outputs = this.outputsFrom(result.state);
    return result;
  }

  // A pure query from the retained live state; nothing changes.
  settle(inputs, { budget = null, targets = null } = {}) {
    return this._solve(this.flatten(inputs), this.clamps(targets), { learn: false, budget });
  }

  settleFlat(flat, { budget = null, clamps = new Map() } = {}) {
    return this._solve(flat, clamps, { learn: false, budget });
  }

  // Continue live activity with frozen relations; retain only a qualified complete state.
  step(inputs, { budget = null } = {}) {
    const result = this.settle(inputs, { budget });
    if (result.qualified) this.state = result.state;
    return { ...result, accepted: result.qualified };
  }

  stepFlat(flat, { budget = null } = {}) {
    const result = this.settleFlat(flat, { budget });
    if (result.qualified) this.state = result.state;
    return { ...result, accepted: result.qualified };
  }

  // Learn one batch: private row activities, shared parameters, one anchor; parameters commit only if the whole
  // batch qualifies, and the live activity is preserved. examples: [{inputs: {name: values} | Float64Array, targets}]
  observeBatch(examples, { budget = null, source = 'witness' } = {}) {
    if (!Array.isArray(examples) || !examples.length) throw new Error('examples must be a nonempty finite sequence of pairs');
    if (source !== 'witness' && source !== 'estimate') throw new Error("source must be 'witness' or 'estimate'");
    const B = examples.length, nI = this.graph.nInputs, flat = new Float64Array(B * nI), clamps = new Map();
    examples.forEach((example, row) => {
      const inputs = example.inputs instanceof Float64Array ? example.inputs : this.flatten(example.inputs);
      if (inputs.length !== nI) throw new Error(`examples[${row}]: inputs must contain ${nI} numbers`);
      flat.set(inputs, row * nI);
      const rowClamps = this.clamps(example.targets, row);
      if (!rowClamps.size) throw new Error(`examples[${row}]: Supply at least one output target`);
      for (const [i, v] of rowClamps) clamps.set(i, v);
    });
    const eventId = this.eventId + 1;
    const result = this._solve(flat, clamps, { learn: true, budget, B });
    const width = this.graph.nPatches, states = [], predictions = [], errors = [], outputs = [];
    for (let r = 0; r < B; r++) {
      states.push(result.state.subarray(r * width, (r + 1) * width));
      predictions.push(result.predictions.subarray(r * width, (r + 1) * width));
      errors.push(result.errors.subarray(r * width, (r + 1) * width));
      outputs.push(this.outputsFrom(result.state, r * width));
    }
    if (result.qualified) {
      this.weights = result.weights; this.weightsSlot = result.weightsSlot; this.biases = result.biases;
      this.eventId = eventId; this.admissions++;
    }
    return { ...result, state: undefined, states, predictions, errors, outputs, accepted: result.qualified, duplicate: false,
             event_id: eventId, batch_size: B, source };
  }

  inspect() {
    const populations = this.layout.populations.map(p => {
      const [a, b] = this.populationRanges.get(p.name);
      return { ...p, role: p.observes.length ? 'observer' : 'processing', indices: Array.from({ length: b - a }, (_, i) => a + i) };
    });
    return { ...this.layout, populations, config: { ...this.config }, patches: this.graph.nPatches, input_samples: this.graph.nInputs,
             connections: this.graph.nEdges, admissions: this.admissions, last_event_id: this.eventId };
  }
}

// Discrete choices from bounded rewards and observed transitions through the same repair; cadence/reinforcement.py.
export class Reinforcement {
  constructor(brain, { actions, action_input = 'action', value_output = 'value', discount = 0.95, exploration = 0.1, reward_scale = 1.0,
                       value_scale = 0.9, capacity = 1024, batch_size = 16, seed = 0 }) {
    if (!(brain instanceof Brain)) throw new Error('brain must be a compiled Brain');
    if (!Number.isInteger(actions) || actions < 2) throw new Error('actions must be an integer >= 2');
    if (batch_size > capacity) throw new Error('batch_size must not exceed capacity');
    if (!(discount >= 0 && discount < 1) || !(exploration >= 0 && exploration <= 1)) throw new Error('discount must be in [0,1); exploration in [0,1]');
    if (value_scale >= Math.min(1 / (1 + brain.config.state_prior), brain.config.state_bound)) throw new Error('value_scale must be below the attainable output bound');
    const input = brain.inputs.find(i => i.name === action_input);
    if (!input || input.size !== actions) throw new Error('action_input must name a sensor with one coordinate per action');
    const outputIndex = brain.outputs.findIndex(o => o.name === value_output);
    if (outputIndex < 0 || brain.outputs[outputIndex].indices.length !== 1) throw new Error('value_output must name scalar-valued outputs');
    this.brain = brain;
    this.config = Object.freeze({ actions, action_input, value_output, discount, exploration, reward_scale, value_scale, capacity, batch_size, seed });
    this.actionOffset = brain.inputRanges.get(action_input)[0];
    this.contextSize = brain.graph.nInputs - actions;
    this.valueIndex = brain.outputIndices[outputIndex][0];
    this.rng = new PyRandom(seed);
    this.records = [];
    this.pending = null;
    this.transitions = 0;
    this.updates = 0;
  }

  // The situation without its action coordinates, in declared sensor order.
  context(inputs) {
    if (inputs instanceof Float64Array && inputs.length === this.contextSize) return inputs;
    const flat = this.brain.flatten({ ...inputs, [this.config.action_input]: new Float64Array(this.config.actions) });
    return this.contextOfFlat(flat);
  }

  contextOfFlat(flat) {
    const out = new Float64Array(this.contextSize), a = this.actionOffset, n = this.config.actions;
    out.set(flat.subarray(0, a), 0);
    out.set(flat.subarray(a + n), a);
    return out;
  }

  inputsOf(context, action) {
    const flat = new Float64Array(this.brain.graph.nInputs), a = this.actionOffset, n = this.config.actions;
    flat.set(context.subarray(0, a), 0);
    flat[a + action] = 1.0;
    flat.set(context.subarray(a), a + n);
    return flat;
  }

  values(context, budget) {
    const results = [];
    for (let a = 0; a < this.config.actions; a++) results.push(this.brain.settleFlat(this.inputsOf(context, a), { budget }));
    return [results, results.map(r => r.state[this.valueIndex])];
  }

  act(inputs, { explore = true, budget = null } = {}) {
    if (this.pending !== null) throw new Error('Supply feedback or reset the pending action first');
    const context = this.context(inputs);
    const [results, values] = this.values(context, budget);
    const work = sumWork(results.map(r => r.work));
    if (!results.every(r => r.qualified)) return { accepted: false, action: null, values, reason: 'query_refused', work };
    const before = this.rng.getState();
    const exploratory = explore && this.rng.random() < this.config.exploration;
    const best = Math.max(...values);
    const choices = exploratory ? values.map((_, i) => i) : values.map((v, i) => [v, i]).filter(([v]) => v === best).map(([, i]) => i);
    const action = this.rng.choice(choices);
    let result;
    try {
      result = this.brain.stepFlat(this.inputsOf(context, action), { budget });
    } catch (error) {
      this.rng.setState(before);
      throw error;
    }
    addWork(work, result.work);
    if (!result.accepted) { this.rng.setState(before); return { accepted: false, action: null, values, reason: 'step_refused', work }; }
    this.pending = [context, action];
    return { accepted: true, action, values, exploratory, settlement: result, work };
  }

  feedback(reward, nextInputs = null, { terminal = false, learn = true, budget = null } = {}) {
    if (this.pending === null) throw new Error('feedback requires a preceding accepted act');
    if (typeof reward !== 'number' || !Number.isFinite(reward)) throw new Error('reward must be a finite real number');
    if (Math.abs(reward) > this.config.reward_scale) throw new Error('reward exceeds reward_scale; scale rewards explicitly');
    let following = null;
    if (terminal) { if (nextInputs !== null) throw new Error('Terminal feedback requires next_inputs=None'); }
    else following = this.context(nextInputs);
    const [context, action] = this.pending;
    this.records.push([context, action, reward, following]);
    if (this.records.length > this.config.capacity) this.records.shift();
    this.transitions++;
    this.pending = null;
    const result = learn ? this.replay({ budget }) : { accepted: false, reason: 'learning_disabled' };
    return { ...result, stored: true, transitions: this.transitions };
  }

  replay({ budget = null } = {}) {
    if (!this.records.length) return { accepted: false, reason: 'empty_replay' };
    const before = this.rng.getState();
    const count = Math.min(this.records.length, this.config.batch_size);
    const indices = this.rng.sample(this.records.length - 1, count - 1);
    indices.push(this.records.length - 1);
    const examples = [], targets = [], work = { evaluations: 0, patch_visits: 0, edge_visits: 0, proposals: 0, backtracks: 0 };
    const scale = this.config.value_scale, discount = this.config.discount;
    let result;
    try {
      for (const index of indices) {
        const [context, action, reward, following] = this.records[index];
        let target = (1 - discount) * scale * (reward / this.config.reward_scale);
        if (following !== null) {
          const [results, values] = this.values(following, budget);
          for (const r of results) addWork(work, r.work);
          if (!results.every(r => r.qualified)) { this.rng.setState(before); return { accepted: false, reason: 'bootstrap_refused', work }; }
          target += discount * Math.max(-scale, Math.min(scale, Math.max(...values)));
        }
        targets.push(target);
        examples.push({ inputs: this.inputsOf(context, action), targets: { [this.config.value_output]: [target] } });
      }
      result = this.brain.observeBatch(examples, { budget, source: 'estimate' });
    } catch (error) {
      this.rng.setState(before);
      throw error;
    }
    if (result.accepted) this.updates++;
    else this.rng.setState(before);
    addWork(work, result.work);
    return { ...result, indices, targets, updates: this.updates, work };
  }

  reset() { this.pending = null; }

  inspect() {
    return { config: { ...this.config }, records: this.records.length, transitions: this.transitions, updates: this.updates, pending: this.pending !== null };
  }
}

function addWork(total, work) {
  for (const key of Object.keys(work)) total[key] = (total[key] || 0) + work[key];
  return total;
}

function sumWork(list) {
  const total = { evaluations: 0, patch_visits: 0, edge_visits: 0, proposals: 0, backtracks: 0 };
  for (const w of list) addWork(total, w);
  return total;
}
