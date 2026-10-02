// A JavaScript version of the population solver of cadence-net 0.70.0 (`cadence.experimental.equilibrium`), for
// brains that are born, settle and learn in the page.
//
// It carries what Rover Lab uses: the seeded wiring of `Cortex` (columns and observers), the joint repair of
// `_repair.settle` for one experience (queries, live steps and supervised admission with a parameter anchor), and
// the `Brain` bookkeeping around it. It follows cortex.py, brain.py and _repair.py of the released package line by
// line. Python's `random.Random` is included (Mersenne Twister, `random`, `shuffle`, `uniform`), so a brain born
// here from a seed carries the wiring and the weights the library gives that seed.
//
// Arithmetic is the library's, in the library's order: every sum the library takes with `math.fsum` is taken here
// with the same exactly rounded sum. The Python library is the reference; parity.mjs checks this file against
// values recorded with it.

// ---- random.Random ------------------------------------------------------------------------------------------------
export function bitLength(n) {
  return n === 0 ? 0 : 32 - Math.clz32(n);
}

// MT19937 seeded through init_by_array, 53-bit doubles, rejection sampling below n.
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
}

// ---- math.fsum, math.ulp -------------------------------------------------------------------------------------------
// Exactly rounded sum of finite doubles (Shewchuk's partials with Python's round-half-even correction).
export function fsum(terms) {
  const partials = [];
  for (let k = 0; k < terms.length; k++) {
    let x = terms[k], i = 0;
    for (let j = 0; j < partials.length; j++) {
      let y = partials[j];
      if (Math.abs(x) < Math.abs(y)) { const t = x; x = y; y = t; }
      const hi = x + y, lo = y - (hi - x);
      if (lo !== 0) partials[i++] = lo;
      x = hi;
    }
    if (!Number.isFinite(x)) throw new RangeError('fsum of a nonfinite value');
    partials.length = i;
    if (x !== 0) partials.push(x);
  }
  let n = partials.length;
  if (n === 0) return 0;
  let hi = partials[--n], lo = 0;
  while (n > 0) {
    const x = hi, y = partials[--n];
    hi = x + y;
    const yr = hi - x;
    lo = y - yr;
    if (lo !== 0) break;
  }
  if (n > 0 && ((lo < 0 && partials[n - 1] < 0) || (lo > 0 && partials[n - 1] > 0))) {
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

const clip = (value, bound) => Math.min(bound, Math.max(-bound, value));
// Stable form of x - clip(x - g): avoids cancellation of a tiny g at a large x.
const projected = (value, gradient, bound) => (gradient >= 0 ? Math.min(gradient, value + bound) : Math.max(gradient, value - bound));

export class SettlementError extends Error {}

// The one transcendental function of the solver. Python takes it from the platform's C library and JavaScript from
// the engine, and the two can differ in the last bit. parity.mjs replaces it on both sides with one formula of
// plain arithmetic to show that everything else is the same computation.
export const numerics = { tanh: Math.tanh };

// ---- _repair.Graph -------------------------------------------------------------------------------------------------
// Immutable port topology. `edges` holds [kind, source, target] with kind 'input', 'state' or 'residual'.
// `residualOrder` puts every error source before its consumer; `incoming` lists each patch's edges in edge order.
export class Graph {
  constructor(nInputs, nPatches, edges) {
    const seen = new Set();
    const incoming = Array.from({ length: nPatches }, () => []);
    const descendants = Array.from({ length: nPatches }, () => []);
    const degree = new Array(nPatches).fill(0);
    this.edges = [];
    for (const [kind, source, target] of edges) {
      if (!['input', 'state', 'residual'].includes(kind)) throw new Error('Edge kind must be input, state or residual');
      if (source < 0 || source >= (kind === 'input' ? nInputs : nPatches)) throw new Error('Edge source is outside its declared population');
      if (target < 0 || target >= nPatches) throw new Error('Edge target is outside its declared population');
      const key = `${kind}:${source}:${target}`;
      if (seen.has(key)) throw new Error('Identical edges must not be repeated');
      seen.add(key);
      incoming[target].push(this.edges.length);
      this.edges.push([kind, source, target]);
      if (kind === 'residual') { descendants[source].push(target); degree[target] += 1; }
    }
    const ready = [];
    for (let i = 0; i < nPatches; i++) if (degree[i] === 0) ready.push(i);
    const order = [];
    for (let head = 0; head < ready.length; head++) {
      const source = ready[head];
      order.push(source);
      for (const target of descendants[source]) if (--degree[target] === 0) ready.push(target);
    }
    if (order.length !== nPatches) throw new Error('Residual-readback dependencies must be acyclic');
    this.nInputs = nInputs;
    this.nPatches = nPatches;
    this.residualOrder = order;
    this.incoming = incoming;
  }
}

// ---- _repair._evaluate ---------------------------------------------------------------------------------------------
// Energy, exact error readback and all analytic derivatives at one point.
function evaluate(graph, inputs, state, weights, biases, statePrior, anchorWeights, anchorBiases, parameterPrior,
                  parameterGradients, queryCache) {
  const P = graph.nPatches, edges = graph.edges;
  const predictions = new Array(P).fill(0), errors = new Array(P).fill(0);
  const signals = queryCache === null ? new Array(edges.length).fill(0) : queryCache[1].slice();
  for (const target of graph.residualOrder) {
    // Only input-only predictions are constant within a frozen-parameter query. Their errors stay live.
    if (queryCache !== null && queryCache[0][target] !== null) {
      predictions[target] = queryCache[0][target];
      errors[target] = state[target] - predictions[target];
      continue;
    }
    const terms = [biases[target]];
    for (const edgeIndex of graph.incoming[target]) {
      const kind = edges[edgeIndex][0], source = edges[edgeIndex][1];
      signals[edgeIndex] = kind === 'input' ? inputs[source] : kind === 'state' ? state[source] : errors[source];
      terms.push(weights[edgeIndex] * signals[edgeIndex]);
    }
    const activation = fsum(terms);
    predictions[target] = numerics.tanh(activation);
    errors[target] = state[target] - predictions[target];
  }
  let energy = 0.5 * fsum(errors.map(e => e * e));
  energy += 0.5 * statePrior * fsum(state.map(x => x * x));
  const gradState = state.map(x => statePrior * x);
  let gradWeights = parameterGradients ? new Array(weights.length).fill(0) : [];
  let gradBiases = parameterGradients ? new Array(biases.length).fill(0) : [];
  const adjError = errors.slice();
  for (let k = graph.residualOrder.length - 1; k >= 0; k--) {
    const target = graph.residualOrder[k];
    const adj = adjError[target];
    gradState[target] += adj;
    const adjPrediction = -adj * (1.0 - predictions[target] * predictions[target]);
    if (parameterGradients) gradBiases[target] += adjPrediction;
    for (const edgeIndex of graph.incoming[target]) {
      const kind = edges[edgeIndex][0], source = edges[edgeIndex][1];
      if (parameterGradients) gradWeights[edgeIndex] += adjPrediction * signals[edgeIndex];
      if (kind === 'state') gradState[source] += adjPrediction * weights[edgeIndex];
      else if (kind === 'residual') adjError[source] += adjPrediction * weights[edgeIndex];
    }
  }
  if (anchorWeights !== null) {
    const deltaWeights = weights.map((w, i) => w - anchorWeights[i]);
    const deltaBiases = biases.map((b, i) => b - anchorBiases[i]);
    energy += 0.5 * parameterPrior * fsum([...deltaWeights, ...deltaBiases].map(d => d * d));
    gradWeights = gradWeights.map((g, i) => g + parameterPrior * deltaWeights[i]);
    gradBiases = gradBiases.map((g, i) => g + parameterPrior * deltaBiases[i]);
  }
  const finite = values => values.every(Number.isFinite);
  if (!Number.isFinite(energy) || !finite(predictions) || !finite(errors) || !finite(gradState) || !finite(gradWeights)
      || !finite(gradBiases)) {
    throw new RangeError('Energy or gradient exceeds the finite numeric range');
  }
  return { energy, predictions, errors, signals, gradient_state: gradState, gradient_weights: gradWeights,
           gradient_biases: gradBiases };
}

function stationarity(state, weights, biases, evaluated, fixed, learn, stateBound, bound) {
  let residual = 0.0;
  for (let i = 0; i < state.length; i++) {
    if (fixed.has(i)) continue;
    residual = Math.max(residual, Math.abs(projected(state[i], evaluated.gradient_state[i], stateBound)));
  }
  if (learn) {
    for (let i = 0; i < weights.length; i++) residual = Math.max(residual, Math.abs(projected(weights[i], evaluated.gradient_weights[i], bound)));
    for (let i = 0; i < biases.length; i++) residual = Math.max(residual, Math.abs(projected(biases[i], evaluated.gradient_biases[i], bound)));
  }
  return residual;
}

// Observed curvature sets the next trial step; unsafe curvature falls back to the configured step.
function nextStepSize(groups, current, proposed, step, backtracks) {
  try {
    const distances = [], curvatures = [];
    for (const [oldValues, newValues, key] of groups) {
      for (let i = 0; i < oldValues.length; i++) {
        if (newValues[i] === oldValues[i]) continue;
        const s = newValues[i] - oldValues[i], y = proposed[key][i] - current[key][i];
        distances.push(s * s / 1);
        curvatures.push(s * y);
      }
    }
    const distance = fsum(distances), curvature = fsum(curvatures);
    if (curvature > 0) {
      const estimate = distance / curvature;
      const ceiling = step * Math.pow(2, Math.min(backtracks - 1, 1023));
      if (Number.isFinite(estimate) && estimate > 0) return Math.min(estimate, ceiling);
    }
  } catch (error) {
    if (!(error instanceof RangeError)) throw error;
  }
  return step;
}

// ---- _repair.settle ------------------------------------------------------------------------------------------------
// One joint repair by projected gradient with a scalar secant step and Armijo backtracking, then a fresh
// qualification of the complete final state. A query freezes parameters; a learning solve repairs state and
// parameters together, anchored to the parameters it started from.
export function settle(graph, inputs, state, weights, biases, {
  clamps = new Map(), learn = false, budget = 2048, tolerance = 1e-6, state_prior: statePrior = 0.01,
  parameter_prior: parameterPrior = 0.1, state_bound: stateBound = 1.0, parameter_bound: parameterBound = 4.0,
  step = 1.0, backtracks = 32,
} = {}) {
  if (inputs.length !== graph.nInputs || state.length !== graph.nPatches || weights.length !== graph.edges.length
      || biases.length !== graph.nPatches) throw new Error('Arguments do not match the graph');
  if (![...inputs, ...state, ...weights, ...biases].every(Number.isFinite)) throw new Error('Arguments must be finite numbers');
  if (state.some(x => Math.abs(x) > stateBound)) throw new Error('Initial state exceeds state_bound');
  if (weights.some(x => Math.abs(x) > parameterBound) || biases.some(x => Math.abs(x) > parameterBound)) {
    throw new Error('Initial parameters exceed parameter_bound');
  }
  let anchorWeights = null, anchorBiases = null;
  if (learn) { anchorWeights = weights; anchorBiases = biases; }
  const fixed = new Map();
  for (const [index, value] of clamps) {
    if (!(index >= 0 && index < state.length) || !Number.isFinite(value) || Math.abs(value) > stateBound) {
      throw new Error('Clamp index or value is outside its declared bounds');
    }
    fixed.set(index, value);
  }
  state = state.map((x, i) => (fixed.has(i) ? fixed.get(i) : x));
  let evaluations = 0, proposals = 0, rejected = 0;
  let queryCache = null;
  const compute = (x, w, b, fresh = false) => {
    evaluations += 1;
    return evaluate(graph, inputs, x, w, b, statePrior, anchorWeights, anchorBiases, parameterPrior, learn,
                    fresh ? null : queryCache);
  };
  let current = compute(state, weights, biases);
  const history = [current.energy];
  let sweeps = 0, reason = 'budget', nextStep = step;
  for (let sweep = 0; sweep < budget; sweep++) {
    if (stationarity(state, weights, biases, current, fixed, learn, stateBound, parameterBound) <= tolerance) {
      reason = 'qualified';
      break;
    }
    if (proposals === 0 && !learn) {
      const invariant = graph.incoming.map((incoming, target) =>
        (incoming.every(edge => graph.edges[edge][0] === 'input') ? current.predictions[target] : null));
      if (invariant.some(prediction => prediction !== null)) queryCache = [invariant, current.signals];
    }
    let trialStep = nextStep, accepted = false;
    for (let attempt = 0; attempt < backtracks; attempt++) {
      proposals += 1;
      const nextState = state.map((x, i) => (fixed.has(i) ? fixed.get(i) : clip(x - trialStep * current.gradient_state[i], stateBound)));
      let nextWeights = weights, nextBiases = biases;
      if (learn) {
        nextWeights = weights.map((x, i) => clip(x - trialStep * current.gradient_weights[i], parameterBound));
        nextBiases = biases.map((x, i) => clip(x - trialStep * current.gradient_biases[i], parameterBound));
      }
      const groups = [[state, nextState, 'gradient_state']];
      if (learn) groups.push([weights, nextWeights, 'gradient_weights'], [biases, nextBiases, 'gradient_biases']);
      let proposed = null;
      try {
        const terms = [];
        let moved = false;
        for (const [oldValues, newValues, key] of groups) {
          for (let i = 0; i < oldValues.length; i++) {
            terms.push(current[key][i] * (newValues[i] - oldValues[i]));
            if (newValues[i] !== oldValues[i]) moved = true;
          }
        }
        const slope = fsum(terms);
        proposed = compute(nextState, nextWeights, nextBiases);
        accepted = moved && Number.isFinite(slope) && slope < 0 && (
          proposed.energy <= current.energy + 1e-4 * slope
          || (Math.abs(proposed.energy - current.energy) <= 8 * ulp(current.energy)
              && stationarity(nextState, nextWeights, nextBiases, proposed, fixed, learn, stateBound, parameterBound) <= tolerance));
      } catch (error) {
        if (!(error instanceof RangeError)) throw error;
        accepted = false;
      }
      if (accepted) {
        nextStep = nextStepSize(groups, current, proposed, step, backtracks);
        state = nextState; weights = nextWeights; biases = nextBiases;
        current = proposed;
        history.push(current.energy);
        sweeps += 1;
        break;
      }
      rejected += 1;
      trialStep *= 0.5;
    }
    if (!accepted) { reason = 'line_search'; break; }
  }
  // With no proposal the initial full evaluation already describes these arrays; otherwise qualify afresh.
  const final = proposals === 0 ? current : compute(state, weights, biases, true);
  const residual = stationarity(state, weights, biases, final, fixed, learn, stateBound, parameterBound);
  const qualified = Number.isFinite(residual) && residual <= tolerance;
  if (qualified) reason = 'qualified';
  return {
    state, weights, biases, predictions: final.predictions, errors: final.errors, energy: final.energy,
    stationarity: residual, prediction_residual: final.errors.reduce((m, e) => Math.max(m, Math.abs(e)), 0.0),
    qualified, sweeps, reason, energy_history: history, work: { evaluations, proposals, backtracks: rejected },
  };
}

// ---- cortex.Cortex -------------------------------------------------------------------------------------------------
export const DEFAULT_CONFIG = Object.freeze({
  seed: 0, fan_in: null, initial_scale: 0.3, settle_budget: 2048, tolerance: 1e-6, state_prior: 0.01,
  parameter_prior: 0.1, state_bound: 1.0, parameter_bound: 4.0, step: 1.0, backtracks: 32,
});

// Declare populations and compile their wiring into one jointly settling brain. `inputs` read sensor or
// represented values; `observes` additionally reads exact live prediction errors inside the same settlement.
export class Cortex {
  constructor(config = {}) {
    for (const key of Object.keys(config)) if (!(key in DEFAULT_CONFIG)) throw new Error(`Unknown configuration: ${key}`);
    this.config = Object.freeze({ ...DEFAULT_CONFIG, ...config });
    this._nodes = new Map();
    this._inputs = [];
    this._populations = [];
    this._outputs = [];
    this._built = false;
  }

  _name(name) {
    if (this._built) throw new Error('A built layout is frozen; create a new Cortex');
    if (typeof name !== 'string' || !name) throw new Error('Names must be nonempty strings');
    if (this._nodes.has(name)) throw new Error(`Duplicate layout name: ${name}`);
    return name;
  }

  _sources(values) {
    values = Array.isArray(values) ? values : [values];
    for (const value of values) if (this._nodes.get(value.name) !== value) throw new Error('Connections must reference existing nodes in this Cortex');
    if (new Set(values).size !== values.length) throw new Error('Duplicate source reference');
    return values;
  }

  input(name, { shape }) {
    const node = { role: 'input', name: this._name(name), size: shape };
    this._inputs.push(node);
    this._nodes.set(node.name, node);
    return node;
  }

  column(name, { patches, inputs = [] }) {
    return this._population(this._name(name), patches, this._sources(inputs), []);
  }

  observer(name, { patches, inputs = [], observes }) {
    name = this._name(name);
    inputs = this._sources(inputs);
    observes = this._sources(observes);
    if (!observes.length || observes.some(node => node.role !== 'population')) throw new Error('An observer must observe at least one population');
    return this._population(name, patches, inputs, observes);
  }

  _population(name, patches, inputs, observes) {
    const node = { role: 'population', name, patches, inputs, observes };
    this._populations.push(node);
    this._nodes.set(name, node);
    return node;
  }

  output(name, { shape, reads }) {
    name = this._name(name);
    [reads] = this._sources(reads);
    if (reads.role !== 'population' || shape > reads.patches) throw new Error('Output size exceeds its source population');
    const node = { role: 'output', name, size: shape, reads, indices: Array.from({ length: shape }, (_, i) => i) };
    this._outputs.push(node);
    this._nodes.set(name, node);
    return node;
  }

  // Every population must read another population's states or errors, or be read by one, and the reads must
  // connect all populations into one component: one brain is one connected equilibrium.
  _requireSettlementBetweenPopulations() {
    const neighbours = new Map(this._populations.map(p => [p.name, new Set()]));
    for (const population of this._populations) {
      for (const source of [...population.inputs, ...population.observes]) {
        if (source.role === 'population') {
          neighbours.get(population.name).add(source.name);
          neighbours.get(source.name).add(population.name);
        }
      }
    }
    for (const population of this._populations) {
      if (!neighbours.get(population.name).size) throw new Error(`Population '${population.name}' settles with no other population`);
    }
    const reached = new Set(), frontier = [this._populations[0].name];
    while (frontier.length) {
      const name = frontier.pop();
      if (reached.has(name)) continue;
      reached.add(name);
      for (const other of neighbours.get(name)) if (!reached.has(other)) frontier.push(other);
    }
    if (reached.size !== this._populations.length) throw new Error('Some populations settle apart from the rest');
  }

  // Sparse population contacts must join the actual processing patches; shared sensors do not couple patches.
  _requireSettlementBetweenPatches(nPatches, edges) {
    const parents = Array.from({ length: nPatches }, (_, i) => i);
    const root = index => {
      while (parents[index] !== index) { parents[index] = parents[parents[index]]; index = parents[index]; }
      return index;
    };
    let components = nPatches;
    for (const [kind, source, target] of edges) {
      if (kind === 'input') continue;
      const a = root(source), b = root(target);
      if (a !== b) { parents[b] = a; components -= 1; }
    }
    if (components !== 1) throw new Error(`Compiled patches form ${components} disconnected settlement components`);
  }

  build() {
    if (this._built || !this._populations.length || !this._outputs.length) throw new Error('Build requires an unbuilt layout with patches and outputs');
    this._requireSettlementBetweenPopulations();
    const rng = new PyRandom(this.config.seed);
    const inputRanges = new Map(), populationRanges = new Map();
    let nInputs = 0, nPatches = 0;
    const range = (start, count) => Array.from({ length: count }, (_, i) => start + i);
    for (const source of this._inputs) { inputRanges.set(source.name, range(nInputs, source.size)); nInputs += source.size; }
    for (const population of this._populations) { populationRanges.set(population.name, range(nPatches, population.patches)); nPatches += population.patches; }
    const edges = [];
    for (const population of this._populations) {
      const sources = [], seen = new Set();
      const add = (kind, name) => { const key = `${kind}:${name}`; if (!seen.has(key)) { seen.add(key); sources.push([kind, name]); } };
      for (const s of population.inputs) add(s.role === 'input' ? 'input' : 'state', s.name);
      for (const s of population.observes) for (const kind of ['state', 'residual']) add(kind, s.name);
      const targets = populationRanges.get(population.name);
      for (const [kind, name] of sources) {
        const indices = (kind === 'input' ? inputRanges : populationRanges).get(name).slice();
        let fanIn = indices.length;
        if (this.config.fan_in !== null) fanIn = Math.min(fanIn, Math.max(this.config.fan_in, Math.ceil(indices.length / targets.length)));
        rng.shuffle(indices);
        targets.forEach((target, localTarget) => {
          for (let slot = 0; slot < fanIn; slot++) edges.push([kind, indices[(localTarget * fanIn + slot) % indices.length], target]);
        });
      }
    }
    this._requireSettlementBetweenPatches(nPatches, edges);
    const graph = new Graph(nInputs, nPatches, edges);
    const scale = this.config.initial_scale;
    const weights = edges.map(([, , target]) => rng.uniform(-1.0, 1.0) * scale / Math.sqrt(graph.incoming[target].length));
    this._built = true;
    return new Brain(this, graph, weights, populationRanges);
  }
}

// ---- brain.Brain ---------------------------------------------------------------------------------------------------
// A compiled layout with private parameters, live state and atomic admission. Query methods freeze parameters;
// `step` retains qualified live state; `observe` jointly repairs live state and local relations under output
// targets and commits only a qualified complete proposal.
export class Brain {
  constructor(builder, graph, weights, populationRanges) {
    this.config = builder.config;
    this.graph = graph;
    this._inputs = builder._inputs;
    this._populations = builder._populations;
    this._outputs = builder._outputs;
    this._populationRanges = populationRanges;
    this.weights = weights;
    this.biases = new Array(graph.nPatches).fill(0.0);
    this.state = new Array(graph.nPatches).fill(0.0);
    this.eventId = -1;
    this.admissions = 0;
  }

  layout() {
    return {
      inputs: this._inputs.map(i => ({ name: i.name, shape: [i.size] })),
      populations: this._populations.map(p => ({ name: p.name, patches: p.patches, inputs: p.inputs.map(s => s.name),
                                                 observes: p.observes.map(s => s.name) })),
      outputs: this._outputs.map(o => ({ name: o.name, shape: [o.size], reads: o.reads.name, indices: o.indices.slice() })),
    };
  }

  _arguments(inputs, targets = null) {
    const flat = [];
    for (const source of this._inputs) {
      const values = inputs[source.name];
      if (!Array.isArray(values) || values.length !== source.size || !values.every(Number.isFinite)) {
        throw new Error(`${source.name} does not match its declared shape`);
      }
      flat.push(...values);
    }
    const clamps = new Map();
    if (targets !== null) {
      for (const output of this._outputs) {
        if (!(output.name in targets)) continue;
        const values = targets[output.name];
        if (!Array.isArray(values) || values.length !== output.size || !values.every(Number.isFinite)) {
          throw new Error(`${output.name} does not match its declared shape`);
        }
        output.indices.forEach((i, k) => {
          if (Math.abs(values[k]) > this.config.state_bound) throw new Error(`'${output.name}' clamp ${values[k]} exceeds state_bound`);
          clamps.set(this._populationRanges.get(output.reads.name)[i], values[k]);
        });
      }
    }
    return [flat, clamps];
  }

  _solve(inputs, clamps, learn, budget) {
    const config = this.config;
    const result = settle(this.graph, inputs, this.state, this.weights, this.biases, {
      clamps, learn, budget: budget ?? config.settle_budget, tolerance: config.tolerance, state_prior: config.state_prior,
      parameter_prior: config.parameter_prior, state_bound: config.state_bound, parameter_bound: config.parameter_bound,
      step: config.step, backtracks: config.backtracks,
    });
    result.outputs = this._outputsFrom(result.state);
    return result;
  }

  _outputsFrom(state) {
    const outputs = {};
    for (const output of this._outputs) {
      outputs[output.name] = output.indices.map(i => state[this._populationRanges.get(output.reads.name)[i]]);
    }
    return outputs;
  }

  // Query a full coupled solve without changing live or durable state. Inspect `qualified` before use.
  settle(inputs, { targets = null, budget = null } = {}) {
    const [flat, clamps] = this._arguments(inputs, targets);
    return this._solve(flat, clamps, false, budget);
  }

  // Retain qualified activity with frozen relations. A refusal retains no proposed state.
  step(inputs, { targets = null, budget = null } = {}) {
    const result = this.settle(inputs, { targets, budget });
    if (result.qualified) this.state = result.state.slice();
    return { ...result, accepted: result.qualified };
  }

  // Jointly repair and atomically retain a labeled input/target experience. A refusal changes nothing.
  observe(inputs, targets, { budget = null, source = 'witness' } = {}) {
    if (source !== 'witness' && source !== 'estimate') throw new Error("source must be 'witness' or 'estimate'");
    if (!targets || !Object.keys(targets).length) throw new Error('Observation requires at least one output target');
    const [flat, clamps] = this._arguments(inputs, targets);
    const eventId = this.eventId + 1;
    const result = this._solve(flat, clamps, true, budget);
    if (result.qualified) {
      this.state = result.state.slice();
      this.weights = result.weights.slice();
      this.biases = result.biases.slice();
      this.eventId = eventId;
      this.admissions += 1;
    }
    return { ...result, accepted: result.qualified, duplicate: false, event_id: eventId, source };
  }

  // The whole continuation state as plain data. The format belongs to this JavaScript edition.
  snapshot() {
    return { schema: 'population-brain-js/1', config: { ...this.config }, layout: this.layout(), edges: this.graph.edges.map(e => e.slice()),
             state: this.state.slice(), weights: this.weights.slice(), biases: this.biases.slice(), event_id: this.eventId,
             admissions: this.admissions };
  }

  static fromSnapshot(data) {
    if (!data || data.schema !== 'population-brain-js/1') throw new Error('Unsupported population checkpoint');
    const builder = new Cortex(data.config);
    const nodes = new Map();
    for (const record of data.layout.inputs) nodes.set(record.name, builder.input(record.name, { shape: record.shape[0] }));
    for (const record of data.layout.populations) {
      const inputs = record.inputs.map(n => nodes.get(n)), observes = record.observes.map(n => nodes.get(n));
      if (inputs.includes(undefined) || observes.includes(undefined)) throw new Error('Malformed population checkpoint');
      nodes.set(record.name, observes.length ? builder.observer(record.name, { patches: record.patches, inputs, observes })
                                             : builder.column(record.name, { patches: record.patches, inputs }));
    }
    for (const record of data.layout.outputs) builder.output(record.name, { shape: record.shape[0], reads: nodes.get(record.reads) });
    const brain = builder.build();
    if (JSON.stringify(brain.graph.edges) !== JSON.stringify(data.edges)) throw new Error('Checkpoint wiring does not match its layout and seed');
    for (const [key, length, bound] of [['state', brain.graph.nPatches, brain.config.state_bound],
                                        ['weights', brain.graph.edges.length, brain.config.parameter_bound],
                                        ['biases', brain.graph.nPatches, brain.config.parameter_bound]]) {
      const values = data[key];
      if (!Array.isArray(values) || values.length !== length || !values.every(v => Number.isFinite(v) && Math.abs(v) <= bound)) {
        throw new Error(`Invalid ${key} in checkpoint`);
      }
    }
    if (!Number.isInteger(data.event_id) || !Number.isInteger(data.admissions) || data.event_id < -1 || data.admissions < 0
        || (data.admissions === 0) !== (data.event_id === -1) || data.admissions > data.event_id + 1) {
      throw new Error('Invalid event ownership');
    }
    if (data.event_id === -1 && (JSON.stringify(data.weights) !== JSON.stringify(brain.weights) || data.biases.some(b => b !== 0))) {
      throw new Error('Retained parameters changed without an admitted event');
    }
    brain.state = data.state.slice(); brain.weights = data.weights.slice(); brain.biases = data.biases.slice();
    brain.eventId = data.event_id; brain.admissions = data.admissions;
    return brain;
  }
}
