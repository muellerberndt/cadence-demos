// A JavaScript version of the Cadence 0.70.0 System 1 brain, as `Brain.compose(inputs, actions, seed=...)` builds it
// with its default single processing region: sensory neurons, an association cortex with a working trace
// (prefrontal neurons), a motor cortex with lateral inhibition, basal ganglia (a critic and dopamine) and an
// associative memory. It follows cadence/generic.py, brain.py, learning.py, plasticity.py, stream.py and memory.py of
// the released package step by step for one stream. NumPy's generator (SeedSequence and PCG64) is included, so a
// brain is born with the weights the library gives the same seed and samples its actions from the same draws.
// The Python library is the reference; parity.mjs checks this file against values recorded with it.

// ---- numpy.random.default_rng ---------------------------------------------------------------------------------
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

// numpy.random.default_rng(seed): PCG64 seeded through SeedSequence; random() is the 53-bit double.
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

  integers(high) {   // not numpy's algorithm; used only where the library draws nothing
    return Math.floor(this.random() * high);
  }
}

// ---- the neuron model of learning nets (cadence.learning.learning_neuron_model(dt=1.0)) ---------------------------
const SLOPE = 1.0, THRESHOLD = 0.0, LEAK = 0.1;
const REST = 1.0 / (1.0 + Math.exp(SLOPE * THRESHOLD));
const ABOVE = 1.0 / (1.0 - REST), BELOW = LEAK / REST;

function activation(v) {
  let r = Math.exp((-SLOPE) * (v - THRESHOLD));
  r += 1.0;
  r = 1.0 / r;
  r -= REST;
  return r > 0.0 ? r * ABOVE : r * BELOW;
}

export class Refusal extends Error {}

export const LEARNING = { beta: 0.1, eta: 0.5, eta_bias: 0.02, temperature: 0.2, tolerance: 3e-3, free_steps: 1024,
                          nudged_steps: 12, momentum: 0.9, normalize: 0.0, normalize_floor: 1e-3, scale_cap: 8.0 };
export const REWARD = { gamma: 0.9, lam: 0.8, eta: 1.0, eta_bias: 0.05, eta_critic: 0.3, normalize: 0.0, momentum: 0.0,
                        dopamine_cap: 1.0 };
const TRACE_DECAY = 0.2, TRACE_AMPLITUDE = 3.0;                 // the working trace of Brain.compose
const MEMORY_DECAY = 0.9, MEMORY_RATE = 1.0, CONSOLIDATION = 0.05;   // its associative memory
const CHUNK = 32;

// One settled or settling state of the whole graph: potentials and activations per population.
function newState(brain) {
  return { vS: new Float64Array(brain.nS), vH: new Float64Array(brain.nH), vP: new Float64Array(brain.nH),
           vM: new Float64Array(brain.nA), sS: new Float64Array(brain.nS), sH: new Float64Array(brain.nH),
           sP: new Float64Array(brain.nH), sM: new Float64Array(brain.nA), steps: 0, version: -1,
           sensoryInput: null };
}

function copyState(state) {
  return { vS: state.vS.slice(), vH: state.vH.slice(), vP: state.vP.slice(), vM: state.vM.slice(),
           sS: state.sS.slice(), sH: state.sH.slice(), sP: state.sP.slice(), sM: state.sM.slice(),
           steps: state.steps, version: state.version, sensoryInput: null };
}

function zeros(blocks) {
  return { sa: new Float64Array(blocks.sa.length), am: new Float64Array(blocks.am.length),
           ma: new Float64Array(blocks.ma.length), pa: new Float64Array(blocks.pa.length),
           mm: new Float64Array(blocks.mm.length) };
}

export class Brain {
  // The brain `cadence.Brain.compose(inputs, actions, seed=seed, learning=..., reward=...)` composes.
  static compose(inputs, actions, { seed = 0, hidden = 64, learning = {}, reward = {} } = {}) {
    return new Brain(inputs, actions, seed, hidden, { ...LEARNING, ...learning }, { ...REWARD, ...reward });
  }

  constructor(nS, nA, seed, nH, learning, reward) {
    this.nS = nS; this.nH = nH; this.nA = nA;
    this.learning = learning; this.reward = reward;
    // development: cadence.genome.develop over the composed genome, projection by projection
    const rng = new Generator(seed);
    const draw = (rows, cols, scale) => {
      const n = rows * cols, out = new Float64Array(n), bound = Math.sqrt(6.0 / (rows + cols));
      for (let k = 0; k < n; k++) rng.random();                     // the density mask (density 1 keeps all)
      for (let k = 0; k < n; k++) out[k] = rng.random() * bound * scale;   // magnitudes
      for (let k = 0; k < n; k++) out[k] = (rng.random() < 0.5 ? 1.0 : -1.0) * out[k];   // signs
      return out;
    };
    const w = { sa: draw(nS, nH, 1.0) };                // sensory i -> association h at [i * nH + h]
    w.am = draw(nH, nA, 1.0);                           // association h -> motor m at [h * nA + m]
    w.ma = new Float64Array(nA * nH);                   // its reverse, motor m -> association h at [m * nH + h]
    for (let h = 0; h < nH; h++) for (let m = 0; m < nA; m++) w.ma[m * nH + h] = w.am[h * nA + m];
    w.pa = draw(nH, nH, 12.0);                          // working trace p -> association h at [p * nH + h]
    w.mm = new Float64Array(nA * nA);                   // motor i -> motor j at [i * nA + j]: lateral inhibition
    for (let i = 0; i < nA; i++) for (let j = 0; j < nA; j++) if (i !== j) w.mm[i * nA + j] = -0.5;
    this.w = w;
    this.bH = new Float64Array(nH); this.bM = new Float64Array(nA);
    this.version = 0;                                   // changes with every parameter update
    // the learner's optimizer history (cadence.learning.Learner)
    this.velocity = zeros(w); this.second = zeros(w);
    this.velocityBias = { H: new Float64Array(nH), M: new Float64Array(nA) };
    this.secondBias = { H: new Float64Array(nH), M: new Float64Array(nA) };
    this.contrastUpdates = 0;
    // the basal ganglia (cadence.plasticity.ActorCritic)
    this.actorRng = new Generator(seed);
    this.wCritic = new Float64Array(nH); this.bCritic = 0.0;
    this.actorVelocity = zeros(w); this.actorSecond = zeros(w);
    this.actorVelocityBias = { H: new Float64Array(nH), M: new Float64Array(nA) };
    this.actorSecondBias = { H: new Float64Array(nH), M: new Float64Array(nA) };
    this.actorUpdates = 0;
    this.trace = null; this.traceBias = null; this.traceCritic = null;
    this.free = null;                                   // the free phase of the latest moment
    this.pending = null;                                // {plus, minus, value}: an action awaiting its outcome
    this.moment = null;                                 // {x, action}: what the memory will be told about
    // the working trace and the associative memory
    this.workingTrace = null;
    this.consolidated = new Float64Array(nS * nA);      // key i, action a at [i * nA + a]
    this.strength = null;
    this.lastLearning = {};
  }

  // ---- drive ------------------------------------------------------------------------------------------------
  // Brain.stimulus: the screen on the sensory neurons, the working trace on the prefrontal neurons, the memory's
  // recall on the motor neurons.
  stimulus(x) {
    const drive = { S: Float64Array.from(x), P: new Float64Array(this.nH), M: this.recall(x) };
    if (this.workingTrace !== null) for (let p = 0; p < this.nH; p++) drive.P[p] = TRACE_AMPLITUDE * this.workingTrace[p];
    return drive;
  }

  _cue(x) {
    let scale = 0;
    for (let i = 0; i < this.nS; i++) { const a = Math.abs(x[i]); if (a > scale) scale = a; }
    const cue = new Float64Array(this.nS), div = scale > 0 ? scale : 1.0;
    let norm = 0;
    for (let i = 0; i < this.nS; i++) { cue[i] = x[i] / div; norm += cue[i] * cue[i]; }
    norm = Math.sqrt(norm);
    if (norm > 0) for (let i = 0; i < this.nS; i++) cue[i] /= norm;
    return cue;
  }

  // SynapticMemory.recall: the reward remembered for each action under a similar screen.
  recall(x) {
    const out = new Float64Array(this.nA), table = this.strength ?? this.consolidated, cue = this._cue(x), nA = this.nA;
    for (let i = 0; i < this.nS; i++) {
      const c = cue[i];
      if (c === 0) continue;
      const base = i * nA;
      for (let a = 0; a < nA; a++) out[a] += c * table[base + a];
    }
    return out;
  }

  // SynapticMemory.observe for the one action taken: persistent synapses consolidate, the fast residual corrects.
  _remember(x, action, reward) {
    const nS = this.nS, nA = this.nA, C = this.consolidated;
    if (this.strength === null) this.strength = C.slice();
    else { const S = this.strength; for (let k = 0; k < S.length; k++) S[k] = C[k] + MEMORY_DECAY * (S[k] - C[k]); }
    const S = this.strength;
    let nonzero = false;
    for (let i = 0; i < nS; i++) if (x[i] !== 0) { nonzero = true; break; }
    if (!nonzero) return;
    const cue = this._cue(x), salience = Math.abs(reward);
    const rate = Math.min(1.0, CONSOLIDATION + Math.min(1.0, CONSOLIDATION * salience));
    let predicted = 0;
    for (let i = 0; i < nS; i++) predicted += cue[i] * C[i * nA + action];
    const error = reward - predicted;
    for (let i = 0; i < nS; i++) { const change = rate * cue[i] * error; C[i * nA + action] += change; S[i * nA + action] += change; }
    let fast = 0;
    for (let i = 0; i < nS; i++) fast += cue[i] * S[i * nA + action];
    const correction = reward - fast;
    for (let i = 0; i < nS; i++) S[i * nA + action] += MEMORY_RATE * cue[i] * correction;
  }

  // ---- settling (NeuralGraph.settle_batch, residual, equilibrate) -------------------------------------------------
  _sensoryInput(sS) {
    const nH = this.nH, wsa = this.w.sa, out = new Float64Array(nH);
    for (let i = 0; i < this.nS; i++) {
      const s = sS[i];
      if (s === 0) continue;
      const base = i * nH;
      for (let h = 0; h < nH; h++) out[h] += wsa[base + h] * s;
    }
    return out;
  }

  // Synaptic input to the association and motor neurons for the activations of `state`.
  _transport(state) {
    const nH = this.nH, nA = this.nA, w = this.w;
    if (state.sensoryInput === null) state.sensoryInput = this._sensoryInput(state.sS);
    const inH = Float64Array.from(state.sensoryInput), inM = new Float64Array(nA);
    for (let p = 0; p < nH; p++) { const s = state.sP[p]; if (s !== 0) { const base = p * nH; for (let h = 0; h < nH; h++) inH[h] += w.pa[base + h] * s; } }
    for (let m = 0; m < nA; m++) { const s = state.sM[m]; if (s !== 0) { const base = m * nH; for (let h = 0; h < nH; h++) inH[h] += w.ma[base + h] * s; } }
    for (let h = 0; h < nH; h++) { const s = state.sH[h]; if (s !== 0) { const base = h * nA; for (let m = 0; m < nA; m++) inM[m] += w.am[base + m] * s; } }
    for (let i = 0; i < nA; i++) { const s = state.sM[i]; if (s !== 0) { const base = i * nA; for (let j = 0; j < nA; j++) inM[j] += w.mm[base + j] * s; } }
    return { inH, inM };
  }

  // Nudge.drive with a softmax temperature: beta * (target - softmax(s / T)) over the motor neurons.
  _nudge(sM, nudge) {
    const nA = this.nA, T = this.learning.temperature, out = new Float64Array(nA);
    let top = -Infinity;
    for (let m = 0; m < nA; m++) { const z = sM[m] / T; if (z > top) top = z; }
    let sum = 0;
    for (let m = 0; m < nA; m++) { out[m] = Math.exp(sM[m] / T - top); sum += out[m]; }
    for (let m = 0; m < nA; m++) out[m] = nudge.beta * ((m === nudge.action ? 1.0 : 0.0) - out[m] / sum);
    return out;
  }

  // The fixed-point equations' largest defect at `state` (activations recomputed from the potentials).
  residual(drive, state, nudge = null) {
    const probe = { ...state, sS: Float64Array.from(state.vS, activation), sH: Float64Array.from(state.vH, activation),
                    sP: Float64Array.from(state.vP, activation), sM: Float64Array.from(state.vM, activation), sensoryInput: null };
    const { inH, inM } = this._transport(probe);
    const push = nudge ? this._nudge(probe.sM, nudge) : null;
    let worst = 0;
    for (let i = 0; i < this.nS; i++) worst = Math.max(worst, Math.abs(0.0 + drive.S[i] + 0.0 - state.vS[i]));
    for (let p = 0; p < this.nH; p++) worst = Math.max(worst, Math.abs(0.0 + drive.P[p] + 0.0 - state.vP[p]));
    for (let h = 0; h < this.nH; h++) worst = Math.max(worst, Math.abs(inH[h] + 0.0 + this.bH[h] - state.vH[h]));
    for (let m = 0; m < this.nA; m++) {
      let e = inM[m] + drive.M[m] + this.bM[m] - state.vM[m];
      if (push) e += push[m];
      worst = Math.max(worst, Math.abs(e));
    }
    return Number.isFinite(worst) ? worst : Infinity;
  }

  // settle_batch: up to `steps` sweeps from `start` (rest when null); with a tolerance it stops once no
  // activation moved more than that in a sweep.
  settle(drive, start, steps, { nudge = null, tolerance = null, dt = 1.0 } = {}) {
    const nS = this.nS, nH = this.nH, nA = this.nA;
    const state = start ? copyState(start) : newState(this);
    for (let i = 0; i < nS; i++) state.sS[i] = activation(state.vS[i]);
    for (let h = 0; h < nH; h++) { state.sH[h] = activation(state.vH[h]); state.sP[h] = activation(state.vP[h]); }
    for (let m = 0; m < nA; m++) state.sM[m] = activation(state.vM[m]);
    state.sensoryInput = null;
    let taken = 0, sensorySettled = false;
    for (let t = 0; t < steps; t++) {
      const { inH, inM } = this._transport(state);
      const push = nudge ? this._nudge(state.sM, nudge) : null;
      let movement = 0;
      if (!sensorySettled) {
        let changed = false, still = true;
        for (let i = 0; i < nS; i++) {
          let total = 0.0 + drive.S[i];
          total -= state.vS[i];
          total *= dt;
          if (total !== 0) { still = false; state.vS[i] += total; }
          const s = activation(state.vS[i]);
          if (s !== state.sS[i]) { const d = Math.abs(s - state.sS[i]); if (d > movement) movement = d; state.sS[i] = s; changed = true; }
        }
        if (changed) state.sensoryInput = null;
        sensorySettled = still;
      }
      for (let p = 0; p < nH; p++) {
        let total = 0.0 + drive.P[p];
        total -= state.vP[p];
        total *= dt;
        state.vP[p] += total;
        const s = activation(state.vP[p]), d = Math.abs(s - state.sP[p]);
        if (d > movement) movement = d;
        state.sP[p] = s;
      }
      for (let h = 0; h < nH; h++) {
        let total = inH[h] + this.bH[h];
        total -= state.vH[h];
        total *= dt;
        state.vH[h] += total;
        const s = activation(state.vH[h]), d = Math.abs(s - state.sH[h]);
        if (d > movement) movement = d;
        state.sH[h] = s;
      }
      for (let m = 0; m < nA; m++) {
        let total = inM[m] + (drive.M[m] + this.bM[m]);
        if (push) total += push[m];
        total -= state.vM[m];
        total *= dt;
        state.vM[m] += total;
        const s = activation(state.vM[m]), d = Math.abs(s - state.sM[m]);
        if (d > movement) movement = d;
        state.sM[m] = s;
      }
      taken = t + 1;
      if (tolerance !== null && movement < tolerance) break;
    }
    state.steps = taken;
    state.version = this.version;
    return state;
  }

  // NeuralGraph.equilibrate: whole chunks of sweeps until the equations hold or the budget is spent.
  equilibrate(drive, start, budget, tolerance, dt = 1.0) {
    let current = this.settle(drive, start, 0, { dt });
    let error = this.residual(drive, current), used = 0;
    while (used < budget && !(error <= tolerance)) {
      if (!Number.isFinite(error)) break;
      current = this.settle(drive, current, Math.min(CHUNK, budget - used), { dt });
      used += current.steps;
      error = this.residual(drive, current);
    }
    return { state: current, residual: error, steps: used };
  }

  // Brain._qualified: half the budget at the model's own step, the rest at half the step if needed; the answer is
  // checked against the original equations and refused when they do not hold.
  _qualified(drive, start) {
    const budget = this.learning.free_steps, tolerance = this.learning.tolerance;
    const first = budget < 2 ? budget : Math.floor((budget + 1) / 2);
    let phase = this.equilibrate(drive, start, first, tolerance);
    if (!(phase.residual <= tolerance) && phase.steps < budget && Number.isFinite(phase.residual)) {
      const following = this.equilibrate(drive, phase.state, budget - phase.steps, tolerance, 0.5);
      phase = { state: following.state, residual: this.residual(drive, following.state), steps: phase.steps + following.steps };
    }
    if (!(phase.residual <= tolerance)) {
      throw new Refusal(`brain did not settle within ${budget} steps: residual=${phase.residual}, tolerance=${tolerance}; no action issued`);
    }
    phase.state.steps = phase.steps;
    return phase.state;
  }

  // ---- the two-phase contrast and the parameter step ------------------------------------------------------------
  // a+ (b+ - b-) + (a+ - a-) b- for every synapse, over `span`.
  _contrast(plus, minus, span) {
    const nS = this.nS, nH = this.nH, nA = this.nA, out = zeros(this.w);
    const block = (target, aP, aM, bP, bM, rows, cols, skipDiagonal) => {
      for (let i = 0; i < rows; i++) {
        const a = aP[i], da = aP[i] - aM[i], base = i * cols;
        for (let j = 0; j < cols; j++) {
          if (skipDiagonal && i === j) continue;
          let c = a * (bP[j] - bM[j]);
          if (da !== 0) c += da * bM[j];
          target[base + j] = c / span;
        }
      }
    };
    block(out.sa, plus.sS, minus.sS, plus.sH, minus.sH, nS, nH, false);
    block(out.am, plus.sH, minus.sH, plus.sM, minus.sM, nH, nA, false);
    block(out.ma, plus.sM, minus.sM, plus.sH, minus.sH, nA, nH, false);
    block(out.pa, plus.sP, minus.sP, plus.sH, minus.sH, nH, nH, false);
    block(out.mm, plus.sM, minus.sM, plus.sM, minus.sM, nA, nA, true);
    const bias = { H: new Float64Array(nH), M: new Float64Array(nA) };
    for (let h = 0; h < nH; h++) bias.H[h] = (plus.sH[h] - minus.sH[h]) / span;
    for (let m = 0; m < nA; m++) bias.M[m] = (plus.sM[m] - minus.sM[m]) / span;
    return { synapse: out, bias };
  }

  // Learner.apply: a reciprocal pair moves by the mean of its two steps; efficacies stay within the cap.
  _apply(step, stepBias) {
    const nH = this.nH, nA = this.nA, w = this.w, cap = this.learning.scale_cap;
    for (let h = 0; h < nH; h++) for (let m = 0; m < nA; m++) {
      const mean = 0.5 * (step.am[h * nA + m] + step.ma[m * nH + h]);
      step.am[h * nA + m] = mean; step.ma[m * nH + h] = mean;
    }
    for (let i = 0; i < nA; i++) for (let j = i + 1; j < nA; j++) {
      const mean = 0.5 * (step.mm[i * nA + j] + step.mm[j * nA + i]);
      step.mm[i * nA + j] = mean; step.mm[j * nA + i] = mean;
    }
    for (const name of ['sa', 'am', 'ma', 'pa', 'mm']) {
      const target = w[name], delta = step[name];
      for (let k = 0; k < target.length; k++) {
        const value = target[k] + delta[k];
        target[k] = value > cap ? cap : value < -cap ? -cap : value;
      }
    }
    for (let h = 0; h < nH; h++) this.bH[h] += stepBias.H[h];
    for (let m = 0; m < nA; m++) this.bM[m] += stepBias.M[m];
    this.version++;
  }

  // The adaptive local step both learners share: each synapse steps on a running mean of its own terms over
  // their running size. `count` is that optimizer's own number of updates, this one included.
  _adaptive(raw, rawBias, velocity, second, velocityBias, secondBias, count, cfg, floor, eta, etaBias) {
    const m = cfg.momentum, rho = cfg.normalize;
    const corrM = m > 0 ? 1.0 - Math.pow(m, count) : 1.0, corrN = rho > 0 ? 1.0 - Math.pow(rho, count) : 1.0;
    const pass = (terms, vel, sec, rate) => {
      const out = new Float64Array(terms.length);
      for (let k = 0; k < terms.length; k++) {
        const term = terms[k];
        let value = term;
        if (m > 0) { vel[k] = m * vel[k] + (1 - m) * term; value = vel[k] / corrM; }
        if (rho > 0) { sec[k] = rho * sec[k] + (1 - rho) * (term * term); value = value / (Math.sqrt(sec[k] / corrN) + floor); }
        out[k] = rate * value;
      }
      return out;
    };
    const step = {};
    for (const name of ['sa', 'am', 'ma', 'pa', 'mm']) step[name] = pass(raw[name], velocity[name], second[name], eta);
    const stepBias = { H: pass(rawBias.H, velocityBias.H, secondBias.H, etaBias), M: pass(rawBias.M, velocityBias.M, secondBias.M, etaBias) };
    return { step, stepBias };
  }

  // Learner.step(drive, [label]): the free phase from rest, both nudged phases, one update. This is the lesson
  // `brain.step(..., teacher=label)` gives, without issuing an action.
  teach(drive, label) {
    const cfg = this.learning;
    const free = this.settle(drive, null, cfg.free_steps, { tolerance: cfg.tolerance });
    const plus = this.settle(drive, free, cfg.nudged_steps, { nudge: { beta: cfg.beta, action: label }, tolerance: cfg.tolerance });
    const minus = this.settle(drive, free, cfg.nudged_steps, { nudge: { beta: -cfg.beta, action: label }, tolerance: cfg.tolerance });
    const contrast = this._contrast(plus, minus, 2.0 * cfg.beta);
    const { step, stepBias } = this._adaptive(contrast.synapse, contrast.bias, this.velocity, this.second, this.velocityBias,
      this.secondBias, this.contrastUpdates + 1, cfg, cfg.normalize_floor, cfg.eta, cfg.eta_bias);
    this._apply(step, stepBias);
    this.contrastUpdates++;
    return { free_steps: free.steps, nudged_steps: plus.steps };
  }

  // ---- acting and learning from reward (Brain.act, Brain.learn, Brain.step) ------------------------------------------
  value(state) {
    let v = 0;
    for (let h = 0; h < this.nH; h++) v += state.sH[h] * this.wCritic[h];
    return v + this.bCritic;
  }

  probabilities(state) {
    const nA = this.nA, T = this.learning.temperature, p = new Float64Array(nA);
    let top = -Infinity, sum = 0;
    for (let m = 0; m < nA; m++) { const z = state.sM[m] / T; if (z > top) top = z; }
    for (let m = 0; m < nA; m++) { p[m] = Math.exp(state.sM[m] / T - top); sum += p[m]; }
    for (let m = 0; m < nA; m++) p[m] /= sum;
    return p;
  }

  // Brain.act: qualify the whole graph, then choose. A greedy read carries no eligibility.
  act(x, { greedy = false } = {}) {
    const drive = this.stimulus(x);
    const free = this._qualified(drive, this.free);
    this.free = free;
    this.pending = null;
    const p = this.probabilities(free);
    let action = 0;
    if (greedy) {
      for (let m = 1; m < this.nA; m++) if (p[m] > p[action]) action = m;
    } else {
      const u = this.actorRng.random();
      let cumulative = 0;
      for (let m = 0; m < this.nA; m++) { cumulative += p[m]; if (cumulative < u) action++; }
      action = Math.min(action, this.nA - 1);
      const cfg = this.learning;
      const plus = this.settle(drive, free, cfg.nudged_steps, { nudge: { beta: cfg.beta, action }, tolerance: cfg.tolerance });
      const minus = this.settle(drive, free, cfg.nudged_steps, { nudge: { beta: -cfg.beta, action }, tolerance: cfg.tolerance });
      this.pending = { plus, minus, value: this.value(free) };
    }
    // the working trace takes this moment's association activity
    if (this.workingTrace === null) this.workingTrace = new Float64Array(this.nH);
    for (let h = 0; h < this.nH; h++) this.workingTrace[h] = TRACE_DECAY * this.workingTrace[h] + (1.0 - TRACE_DECAY) * free.sH[h];
    this.moment = greedy ? null : { x: Float64Array.from(x), action };
    return action;
  }

  // Brain.learn: the outcome of the pending action. The memory records its reward, a finished episode clears the
  // working trace, and every synapse moves by its eligibility trace times the dopamine.
  learn(reward, done, x) {
    if (this.pending === null) throw new Error('feedback needs a preceding action');
    const cfg = this.reward, nH = this.nH, nA = this.nA;
    if (this.moment !== null) this._remember(this.moment.x, this.moment.action, reward);
    if (done) this.workingTrace = new Float64Array(nH);
    const nextDrive = this.stimulus(x);
    const { plus, minus, value } = this.pending, free = this.free, decay = cfg.gamma * cfg.lam;
    if (this.trace === null) {
      this.trace = zeros(this.w);
      this.traceBias = { H: new Float64Array(nH), M: new Float64Array(nA) };
      this.traceCritic = new Float64Array(nH + 1);
    }
    const contrast = this._contrast(plus, minus, 2.0 * this.learning.beta);
    for (const name of ['sa', 'am', 'ma', 'pa', 'mm']) {
      const trace = this.trace[name], c = contrast.synapse[name];
      for (let k = 0; k < trace.length; k++) { trace[k] *= decay; trace[k] += c[k]; }
    }
    for (const name of ['H', 'M']) {
      const trace = this.traceBias[name], c = contrast.bias[name];
      for (let k = 0; k < trace.length; k++) { trace[k] *= decay; trace[k] += c[k]; }
    }
    for (let h = 0; h <= nH; h++) this.traceCritic[h] *= cfg.gamma * cfg.lam;
    for (let h = 0; h < nH; h++) this.traceCritic[h] += free.sH[h];
    this.traceCritic[nH] += 1.0;
    // the next state, warm from this one; a finished stream starts from rest
    let warm = free;
    if (done) {
      warm = copyState(free);
      warm.vS.fill(0); warm.vH.fill(0); warm.vP.fill(0); warm.vM.fill(0);
    }
    const next = this.settle(nextDrive, warm, this.learning.free_steps, { tolerance: this.learning.tolerance });
    const nextValue = done ? 0.0 : this.value(next);
    const tdError = reward + cfg.gamma * nextValue - value;
    if (!Number.isFinite(tdError)) throw new Error('TD errors must remain finite');
    let delta = tdError;
    if (cfg.dopamine_cap > 0) delta = Math.max(-cfg.dopamine_cap, Math.min(cfg.dopamine_cap, delta));
    const raw = zeros(this.w), rawBias = { H: new Float64Array(nH), M: new Float64Array(nA) };
    for (const name of ['sa', 'am', 'ma', 'pa', 'mm']) { const t = this.trace[name], r = raw[name]; for (let k = 0; k < t.length; k++) r[k] = delta * t[k]; }
    for (const name of ['H', 'M']) { const t = this.traceBias[name], r = rawBias[name]; for (let k = 0; k < t.length; k++) r[k] = delta * t[k]; }
    this.actorUpdates++;
    const { step, stepBias } = this._adaptive(raw, rawBias, this.actorVelocity, this.actorSecond, this.actorVelocityBias,
      this.actorSecondBias, this.actorUpdates, cfg, 1e-3, cfg.eta, cfg.eta_bias);
    // the critic: its own trace over that trace's energy, moved by the same bounded signal
    let energy = 0;
    for (let h = 0; h <= nH; h++) energy += this.traceCritic[h] * this.traceCritic[h];
    const criticStep = new Float64Array(nH + 1);
    for (let h = 0; h <= nH; h++) criticStep[h] = cfg.eta_critic * (delta * (this.traceCritic[h] / (1.0 + energy)));
    this._apply(step, stepBias);
    for (let h = 0; h < nH; h++) this.wCritic[h] += criticStep[h];
    this.bCritic += criticStep[nH];
    if (done) {
      for (const name of ['sa', 'am', 'ma', 'pa', 'mm']) this.trace[name].fill(0);
      this.traceBias.H.fill(0); this.traceBias.M.fill(0); this.traceCritic.fill(0);
    }
    this.free = next;                 // settled under the parameters before this update; act qualifies it again
    this.pending = null;
    this.moment = null;
    this.lastLearning = { delta: Math.abs(delta), dopamine: delta, td_error: Math.abs(tdError), value, free_steps: next.steps };
    return this.lastLearning;
  }

  // Brain.step: learn from the outcome of the preceding action, then act again.
  step(x, { reward = null, done = false } = {}) {
    if (this.pending !== null) this.learn(reward ?? 0.0, done, x);
    else { this.lastLearning = {}; if (reward !== null) throw new Error('feedback needs a preceding action; start with step(observations)'); }
    return this.act(x);
  }

  // Brain.reset: every stream starts afresh; the memory's persistent synapses stay.
  reset() {
    this.free = null; this.pending = null; this.moment = null;
    this.trace = null; this.traceBias = null; this.traceCritic = null;
    this.workingTrace = null;
    this.lastLearning = {};
  }

  // ---- inspection --------------------------------------------------------------------------------------------
  // Efficacies in the library's synapse order (by postsynaptic, then presynaptic neuron), for digests.
  efficacy() {
    const nS = this.nS, nH = this.nH, nA = this.nA, w = this.w;
    const out = new Float64Array(nS * nH + nH * nH + 2 * nH * nA + nA * (nA - 1));
    let k = 0;
    for (let h = 0; h < nH; h++) {
      for (let i = 0; i < nS; i++) out[k++] = w.sa[i * nH + h];
      for (let p = 0; p < nH; p++) out[k++] = w.pa[p * nH + h];
      for (let m = 0; m < nA; m++) out[k++] = w.ma[m * nH + h];
    }
    for (let m = 0; m < nA; m++) {
      for (let h = 0; h < nH; h++) out[k++] = w.am[h * nA + m];
      for (let i = 0; i < nA; i++) if (i !== m) out[k++] = w.mm[i * nA + m];
    }
    return out;
  }
}
