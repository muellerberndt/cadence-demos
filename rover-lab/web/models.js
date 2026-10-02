// Motion models for the rover's two public motor/odometry ports: the JavaScript edition of models.py.
//
// Every learner sees only two commanded motor values and learns two measured motion values. Wheel gains, phase
// names, targets and simulator parameters are deliberately absent. Action selection and replay belong to rover.js.

import { Brain, Cortex, SettlementError } from './cadence.js';

export const SCHEMA = 'pragma.rover.model-js/1';
export const KINDS = ['coupled', 'observer', 'adaptive', 'mlp'];

// Python's built-in sum over floats (3.12 and later): a compensated running sum.
export function pysum(values) {
  let total = 0.0, compensation = 0.0;
  for (const x of values) {
    const t = total + x;
    compensation += Math.abs(total) >= Math.abs(x) ? (total - t) + x : (x - t) + total;
    total = t;
  }
  return compensation && Number.isFinite(compensation) ? total + compensation : total;
}

function pair(values, name, bound = null) {
  if (!Array.isArray(values) || values.length !== 2 || !values.every(v => typeof v === 'number' && Number.isFinite(v))) {
    throw new Error(`${name} must contain two finite numbers`);
  }
  if (bound !== null && values.some(v => Math.abs(v) > bound)) throw new Error(`${name} must lie in [-${bound}, ${bound}]`);
  return values.slice();
}

const action = value => pair(value, 'motor commands', 0.8);

function counter(value) {
  if (!Number.isInteger(value) || value < 0) throw new Error('model counters must be nonnegative integers');
  return value;
}

const baseSnapshot = model => ({ schema: SCHEMA, kind: model.kind, accepted: model.accepted, presentations: model.presentations });

// Four processing patches in three populations, settled as one equilibrium. `coupled` is the default brain:
// populations read the motors and one another's live states. `observer` is the optional addition: the same
// populations also read exact prediction errors. Candidate forecasts are unclamped solves in both layouts.
export class CadenceModel {
  constructor(kind, seed) {
    this.kind = kind;
    const cortex = new Cortex({ seed, parameter_prior: 0.1 });
    const motors = cortex.input('motors', { shape: 2 });
    const body = cortex.column('body', { patches: 1, inputs: motors });
    let middle, output;
    if (kind === 'coupled') {
      middle = cortex.column('integration', { patches: 1, inputs: [motors, body] });
      output = cortex.column('motion', { patches: 2, inputs: [motors, body, middle] });
    } else {
      middle = cortex.observer('integration', { patches: 1, inputs: motors, observes: body });
      output = cortex.observer('motion', { patches: 2, inputs: motors, observes: [body, middle] });
    }
    cortex.output('motion_readout', { shape: 2, reads: output });
    this.brain = cortex.build();
    this.accepted = this.presentations = 0;
    this.errors = new Array(this.brain.graph.nPatches).fill(0.0);
    this.names = this._patchNames();
  }

  _patchNames() {
    return this.brain.layout().populations.flatMap(p => Array.from({ length: p.patches }, (_, i) => `${p.name} ${i + 1}`));
  }

  static _qualified(result) {
    if (!result.qualified) {
      throw new SettlementError(`Rover motion solve refused: ${result.reason}; stationarity=${result.stationarity.toPrecision(6)}`);
    }
    return result.outputs.motion_readout.slice();
  }

  // forecast each candidate command with a pure, unclamped settle
  query(actions) {
    return actions.map(a => CadenceModel._qualified(this.brain.settle({ motors: action(a) })));
  }

  // settle on the chosen command, keeping the live activity
  activate(command) {
    const result = this.brain.step({ motors: action(command) });
    const prediction = CadenceModel._qualified(result);
    this.errors = result.errors.slice();
    return prediction;
  }

  // learn the consequence of a command that was executed
  learn(command, motion) {
    const inputs = { motors: action(command) };
    const targets = { motion_readout: pair(motion, 'measured motion', 1.0) };
    this.presentations += 1;
    const result = this.brain.observe(inputs, targets, { source: 'witness' });
    if (result.accepted) {
      this.accepted += 1;
      this.errors = result.errors.slice();
    }
    return result.accepted;
  }

  activity() {
    return this.names.map((name, i) => ({ name, state: this.brain.state[i], error: this.errors[i] }));
  }

  parameters() {
    return this.brain.weights.length + this.brain.biases.length;
  }

  snapshot() {
    return { ...baseSnapshot(this), brain: this.brain.snapshot(), errors: this.errors.slice() };
  }
}

// Two-output affine recursive least squares with forgetting factor 0.97. The estimator knows only that
// command-to-motion dynamics may be affine. It does not receive the wheel equation or perturbation information.
export class AdaptiveModel {
  constructor() {
    this.kind = 'adaptive';
    this.forgetting = 0.97;
    this.coefficients = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]];
    this.covariance = [0, 1, 2].map(row => [0, 1, 2].map(column => (row === column ? 100.0 : 0.0)));
    this.accepted = this.presentations = 0;
    this.last = [0.0, 0.0];
    this.errors = [0.0, 0.0];
  }

  query(actions) {
    return actions.map(a => {
      const features = [...action(a), 1.0];
      return this.coefficients.map(row => pysum(row.map((weight, i) => weight * features[i])));
    });
  }

  activate(command) {
    this.last = this.query([command])[0];
    this.errors = [0.0, 0.0];
    return this.last.slice();
  }

  learn(command, motion) {
    command = action(command);
    const target = pair(motion, 'measured motion', 1.0);
    const features = [...command, 1.0];
    const forecast = this.query([command])[0];
    const projected = this.covariance.map(row => pysum(row.map((value, i) => value * features[i])));
    const denominator = this.forgetting + pysum(projected.map((value, i) => value * features[i]));
    const gain = projected.map(value => value / denominator);
    const residual = target.map((actual, i) => actual - forecast[i]);
    const coefficients = this.coefficients.map((row, r) => row.map((weight, i) => weight + residual[r] * gain[i]));
    let covariance = [0, 1, 2].map(row => [0, 1, 2].map(column =>
      (this.covariance[row][column] - gain[row] * projected[column]) / this.forgetting));
    // Roundoff can otherwise destroy symmetry over long online lives.
    covariance = [0, 1, 2].map(row => [0, 1, 2].map(column => (covariance[row][column] + covariance[column][row]) / 2));
    if (![...coefficients, ...covariance].every(row => row.every(Number.isFinite))) {
      throw new Error('adaptive estimator update became nonfinite');
    }
    this.coefficients = coefficients;
    this.covariance = covariance;
    this.presentations += 1;
    this.accepted += 1;
    this.last = this.query([command])[0];
    this.errors = target.map((actual, i) => actual - this.last[i]);
    return true;
  }

  activity() {
    return ['forward estimate', 'turn estimate'].map((name, i) => ({ name, state: this.last[i], error: this.errors[i] }));
  }

  parameters() {
    return 6;
  }

  snapshot() {
    return { ...baseSnapshot(this), forgetting: this.forgetting, coefficients: this.coefficients.map(r => r.slice()),
             covariance: this.covariance.map(r => r.slice()), last: this.last.slice(), errors: this.errors.slice() };
  }
}

// ---- numpy.random.default_rng: PCG64 seeded through SeedSequence -------------------------------------------------
const M32 = 0xffffffffn, M64 = (1n << 64n) - 1n, M128 = (1n << 128n) - 1n;
const PCG_MULT = 0x2360ED051FC65DA44385DF649FCCF645n;

function seedSequenceState(seed, words = 4) {
  const INIT_A = 0x43b0d7e5n, MULT_A = 0x931e8875n, INIT_B = 0x8b51f9ddn, MULT_B = 0x58f38dedn;
  const MIX_L = 0xca01f9ddn, MIX_R = 0x4973f715n, XSHIFT = 16n;
  const entropy = [];
  let rest = BigInt(seed);
  do { entropy.push(rest & M32); rest >>= 32n; } while (rest > 0n);
  let hashConst = INIT_A;
  const hashmix = value => {
    value = (value ^ hashConst) & M32;
    hashConst = (hashConst * MULT_A) & M32;
    value = (value * hashConst) & M32;
    return (value ^ (value >> XSHIFT)) & M32;
  };
  const mix = (x, y) => {
    const result = ((MIX_L * x) - (MIX_R * y)) & M32;
    return (result ^ (result >> XSHIFT)) & M32;
  };
  const pool = [0n, 0n, 0n, 0n];
  for (let i = 0; i < 4; i++) pool[i] = hashmix(i < entropy.length ? entropy[i] : 0n);
  for (let src = 0; src < 4; src++) for (let dst = 0; dst < 4; dst++) if (src !== dst) pool[dst] = mix(pool[dst], hashmix(pool[src]));
  for (let src = 4; src < entropy.length; src++) for (let dst = 0; dst < 4; dst++) pool[dst] = mix(pool[dst], hashmix(entropy[src]));
  let hashB = INIT_B;
  const out32 = [];
  for (let i = 0; i < words * 2; i++) {
    let value = pool[i % 4];
    value = (value ^ hashB) & M32;
    hashB = (hashB * MULT_B) & M32;
    value = (value * hashB) & M32;
    out32.push((value ^ (value >> XSHIFT)) & M32);
  }
  const out = [];
  for (let k = 0; k < words; k++) out.push(out32[2 * k] | (out32[2 * k + 1] << 32n));
  return out;
}

export class Generator {
  constructor(seed) {
    const s = seedSequenceState(seed, 4);
    this.inc = ((((s[2] << 64n) | s[3]) << 1n) | 1n) & M128;
    this.state = 0n;
    this.state = (this.state * PCG_MULT + this.inc) & M128;
    this.state = (this.state + ((s[0] << 64n) | s[1])) & M128;
    this.state = (this.state * PCG_MULT + this.inc) & M128;
  }

  next64() {
    this.state = (this.state * PCG_MULT + this.inc) & M128;
    const value = ((this.state >> 64n) ^ this.state) & M64, rot = this.state >> 122n;
    return ((value >> rot) | (value << ((64n - rot) & 63n))) & M64;
  }

  random() {
    return Number(this.next64() >> 11n) * (1.0 / 9007199254740992.0);
  }

  uniform(low, high) {
    return low + (high - low) * this.random();
  }
}

// ---- the small neural baseline ------------------------------------------------------------------------------------
const zerosLike = array => array.map(row => (Array.isArray(row) ? row.map(() => 0.0) : 0.0));
const flatEvery = (array, test) => array.every(row => (Array.isArray(row) ? row.every(test) : test(row)));
// (vector) @ (matrix[in][out])
const through = (vector, matrix, bias) => bias.map((b, j) => Math.tanh(vector.reduce((s, v, i) => s + v * matrix[i][j], 0.0) + b));
// (vector) @ (matrix[in][out]).T
const back = (vector, matrix) => matrix.map(row => row.reduce((s, w, j) => s + vector[j] * w, 0.0));
const outer = (a, b) => a.map(x => b.map(y => x * y));
const zip3 = (a, b, c, f) => a.map((row, i) => (Array.isArray(row) ? row.map((x, j) => f(x, b[i][j], c ? c[i][j] : undefined))
                                                                    : f(row, b[i], c ? c[i] : undefined)));

// Float64 2 -> 24 -> 24 -> 2 tanh network, trained by full-state Adam (learning rate 0.01).
export class MLPModel {
  constructor(seed) {
    this.kind = 'mlp';
    const rng = new Generator(seed);
    this.arrays = [];
    for (const [widthIn, widthOut] of [[2, 24], [24, 24], [24, 2]]) {
      const limit = 1.0 / Math.sqrt(widthIn);
      this.arrays.push(Array.from({ length: widthIn }, () => Array.from({ length: widthOut }, () => rng.uniform(-limit, limit))));
      this.arrays.push(Array.from({ length: widthOut }, () => rng.uniform(-limit, limit)));
    }
    this.firstMoments = this.arrays.map(zerosLike);
    this.secondMoments = this.arrays.map(zerosLike);
    this.learningRate = 0.01;
    this.steps = this.accepted = this.presentations = 0;
    this.last = [0.0, 0.0];
    this.errors = [0.0, 0.0];
  }

  _forward(values) {
    const hidden1 = through(values, this.arrays[0], this.arrays[1]);
    const hidden2 = through(hidden1, this.arrays[2], this.arrays[3]);
    const output = through(hidden2, this.arrays[4], this.arrays[5]);
    return [hidden1, hidden2, output];
  }

  query(actions) {
    return actions.map(a => {
      const output = this._forward(action(a))[2];
      if (!output.every(Number.isFinite)) throw new Error('MLP forecast became nonfinite');
      return output;
    });
  }

  activate(command) {
    this.last = this.query([command])[0];
    this.errors = [0.0, 0.0];
    return this.last.slice();
  }

  learn(command, motion) {
    const values = action(command);
    const target = pair(motion, 'measured motion', 1.0);
    const [hidden1, hidden2, output] = this._forward(values);
    // Mean squared error over both motion coordinates: 2 / outputs = 1.
    const derivative3 = output.map((o, i) => (o - target[i]) * (1.0 - o * o));
    const derivative2 = back(derivative3, this.arrays[4]).map((d, i) => d * (1.0 - hidden2[i] * hidden2[i]));
    const derivative1 = back(derivative2, this.arrays[2]).map((d, i) => d * (1.0 - hidden1[i] * hidden1[i]));
    const gradients = [outer(values, derivative1), derivative1, outer(hidden1, derivative2), derivative2,
                       outer(hidden2, derivative3), derivative3];
    const nextStep = this.steps + 1;
    const moments1 = this.firstMoments.map((old, k) => zip3(old, gradients[k], null, (m, g) => 0.9 * m + 0.1 * g));
    const moments2 = this.secondMoments.map((old, k) => zip3(old, gradients[k], null, (m, g) => 0.999 * m + 0.001 * g * g));
    const correction1 = 1.0 - Math.pow(0.9, nextStep), correction2 = 1.0 - Math.pow(0.999, nextStep);
    const arrays = this.arrays.map((parameter, k) => zip3(parameter, moments1[k], moments2[k], (p, first, second) =>
      p - this.learningRate * (first / correction1) / (Math.sqrt(second / correction2) + 1e-8)));
    if (![...arrays, ...moments1, ...moments2].every(array => flatEvery(array, Number.isFinite))) {
      throw new Error('MLP optimizer update became nonfinite');
    }
    this.arrays = arrays; this.firstMoments = moments1; this.secondMoments = moments2;
    this.steps = nextStep;
    this.accepted += 1;
    this.presentations += 1;
    this.last = this.query([values])[0];
    this.errors = target.map((t, i) => t - this.last[i]);
    return true;
  }

  activity() {
    return ['forward readout', 'turn readout'].map((name, i) => ({ name, state: this.last[i], error: this.errors[i] }));
  }

  parameters() {
    return this.arrays.reduce((n, array) => n + array.flat().length, 0);
  }

  snapshot() {
    const copy = arrays => arrays.map(array => array.map(row => (Array.isArray(row) ? row.slice() : row)));
    return { ...baseSnapshot(this), arrays: copy(this.arrays), first_moments: copy(this.firstMoments),
             second_moments: copy(this.secondMoments), learning_rate: this.learningRate, steps: this.steps,
             last: this.last.slice(), errors: this.errors.slice() };
  }
}

export function makeModel(kind, seed) {
  if (!KINDS.includes(kind)) throw new Error(`unknown rover model '${kind}'; choose from ${KINDS}`);
  if (!Number.isInteger(seed) || seed < 0) throw new Error('seed must be a nonnegative integer');
  if (kind === 'adaptive') return new AdaptiveModel();
  if (kind === 'mlp') return new MLPModel(seed);
  return new CadenceModel(kind, seed);
}

function matrix(data, shape, name) {
  const ok = shape.length === 1
    ? Array.isArray(data) && data.length === shape[0] && data.every(Number.isFinite)
    : Array.isArray(data) && data.length === shape[0] && data.every(row => Array.isArray(row) && row.length === shape[1] && row.every(Number.isFinite));
  if (!ok) throw new Error(`checkpoint ${name} must have finite shape (${shape})`);
  return shape.length === 1 ? data.slice() : data.map(row => row.slice());
}

// Restore parameters, admission counts, optimizer and retained display state.
export function modelFromSnapshot(data) {
  if (!data || typeof data !== 'object' || data.schema !== SCHEMA) throw new Error('unsupported rover model checkpoint');
  const model = makeModel(data.kind, 0);
  model.accepted = counter(data.accepted);
  model.presentations = counter(data.presentations);
  if (model.accepted > model.presentations) throw new Error('checkpoint accepted count exceeds presentations');
  if (model instanceof CadenceModel) {
    const original = JSON.stringify(model.brain.layout());
    model.brain = Brain.fromSnapshot(data.brain);
    if (JSON.stringify(model.brain.layout()) !== original) throw new Error('checkpoint brain layout does not match rover model kind');
    model.errors = matrix(data.errors, [model.brain.graph.nPatches], 'errors');
    model.names = model._patchNames();
  } else {
    model.last = pair(data.last, 'checkpoint readout');
    model.errors = pair(data.errors, 'checkpoint errors');
    if (model instanceof AdaptiveModel) {
      if (data.forgetting !== model.forgetting) throw new Error('checkpoint changed adaptive forgetting factor');
      model.coefficients = matrix(data.coefficients, [2, 3], 'coefficients');
      model.covariance = matrix(data.covariance, [3, 3], 'covariance');
    } else {
      if (data.learning_rate !== model.learningRate) throw new Error('checkpoint changed MLP learning rate');
      const shapes = model.arrays.map(array => (Array.isArray(array[0]) ? [array.length, array[0].length] : [array.length]));
      for (const [field, property] of [['arrays', 'arrays'], ['first_moments', 'firstMoments'], ['second_moments', 'secondMoments']]) {
        if (!Array.isArray(data[field]) || data[field].length !== shapes.length) throw new Error(`checkpoint has wrong number of ${field}`);
        model[property] = data[field].map((value, k) => matrix(value, shapes[k], field));
      }
      if (!model.secondMoments.every(array => flatEvery(array, v => v >= 0))) throw new Error('checkpoint Adam second moments must be nonnegative');
      model.steps = counter(data.steps);
      if (model.steps !== model.accepted) throw new Error('checkpoint Adam steps disagree with admissions');
    }
  }
  return model;
}
