// The arcade's loop, shared by the browser workers and the headless runner: the perception of the screen, the
// scripted teachers, the brain side (watching, admission, takeover, living) and the game side (episodes, scores,
// the skill badge). It follows atari-arcade/server.py line by line; the Python server remains the reference.
import { Cortex, PyRandom, Reinforcement } from './cadence.js';

export const TILE = 28, GRID = 3, N_SCREEN = 84 * 84;
export const BATCH = 24;
export const WATCH_MIN_WITNESSES = 240;
export const WATCH_MAX_WITNESSES = 720;
export const AGREE_TO_PLAY = {};
export const AGREE_DEFAULT = 0.6;
export const REPLAY_EVERY = 6;
export const BUDGET = 256;
// The server's torch brain needed about half a second per decision, so each lived transition spanned some
// forty environment steps at its full speed; the JavaScript brain decides in tens of milliseconds and would otherwise
// split the same experience into one-step transitions with rare rewards. It keeps the server's cadence.
export const DECISION_EVERY = 40;
export const NORM_FRAMES = 300;

export const AGENT_HINTS = {
  Atlantis: 'the brain fires the three gun bases',
  Freeway: 'the brain is the chicken crossing the road',
};
export const TEACHER = { Freeway: 'UP', Atlantis: 'FIRE' };
export const REWARD_SCALE = { Atlantis: 500.0, Freeway: 1.0 };

export function teacherAction(game, meanings) {
  const name = TEACHER[game];
  if (!name) throw new Error(`no teacher for ${game}`);
  return meanings.indexOf(name);
}

export function buildBrain(nActions, seed = 0) {
  const c = new Cortex({ seed, settle_budget: 4096, parameter_prior: 0.4 });
  const tiles = [];
  for (let i = 0; i < GRID * GRID; i++) tiles.push(c.input(`tile${i}`, { shape: [TILE, TILE] }));
  const act = c.input('action', { shape: [nActions] });
  const cols = tiles.map((tile, i) => c.column(`t${i}`, { patches: 8, inputs: [tile] }));
  const r = c.observer('r', { patches: 12, observes: cols });
  const p = c.observer('p', { patches: 16, observes: [...cols, r] });
  const v = c.observer('v', { patches: 8, inputs: [act], observes: [r, p] });
  c.output('motor', { shape: [nActions], reads: p });
  c.output('value', { shape: [1], reads: v });
  return c.build();
}

// 210 x 160 RGBA pixels to the 84 x 84 grey retina, the running normalization and the nine 28 x 28 tiles.
export class Perception {
  constructor() {
    this.rowEdges = new Int32Array(85);
    this.colEdges = new Int32Array(85);
    for (let i = 0; i < 84; i++) { this.rowEdges[i] = Math.trunc(i * 2.5); this.colEdges[i] = Math.trunc(i * (160 / 84)); }
    this.rowEdges[84] = 210; this.colEdges[84] = 160;
    this.normBuffer = [];
    this.normMean = null;
    this.normStd = null;
    this.rows = new Float64Array(84 * 160);
  }

  grey84(rgba) {
    const rows = this.rows, re = this.rowEdges, ce = this.colEdges;
    for (let gy = 0; gy < 84; gy++) {
      const base = gy * 160;
      for (let x = 0; x < 160; x++) rows[base + x] = 0;
      for (let y = re[gy]; y < re[gy + 1]; y++) {
        let o = y * 160 * 4;
        for (let x = 0; x < 160; x++, o += 4) rows[base + x] += rgba[o] * 0.299 + rgba[o + 1] * 0.587 + rgba[o + 2] * 0.114;
      }
    }
    const small = new Float64Array(84 * 84);
    for (let gy = 0; gy < 84; gy++) {
      const base = gy * 160;
      for (let gx = 0; gx < 84; gx++) {
        let s = 0;
        for (let x = ce[gx]; x < ce[gx + 1]; x++) s += rows[base + x];
        small[gy * 84 + gx] = Math.min(255, Math.max(0, s / (2.5 * 1.9047))) / 255.0;
      }
    }
    return small;
  }

  // The first NORM_FRAMES retinas fix a per-pixel mean and deviation, as the server does.
  observe(small) {
    if (this.normMean !== null) return;
    this.normBuffer.push(small);
    if (this.normBuffer.length < NORM_FRAMES) return;
    const n = this.normBuffer.length, mean = new Float64Array(N_SCREEN), std = new Float64Array(N_SCREEN);
    for (const frame of this.normBuffer) for (let i = 0; i < N_SCREEN; i++) mean[i] += frame[i];
    for (let i = 0; i < N_SCREEN; i++) mean[i] /= n;
    for (const frame of this.normBuffer) for (let i = 0; i < N_SCREEN; i++) { const d = frame[i] - mean[i]; std[i] += d * d; }
    for (let i = 0; i < N_SCREEN; i++) std[i] = Math.sqrt(std[i] / n) + 1e-6;
    this.normMean = mean; this.normStd = std;
    this.normBuffer = [];
  }

  // The nine tiles in tile order (tile0 top-left, row-major), each 28 x 28 row-major.
  tiles(small) {
    const flat = new Float64Array(N_SCREEN);
    if (this.normMean !== null) {
      for (let i = 0; i < N_SCREEN; i++) flat[i] = Math.min(3, Math.max(-3, (small[i] - this.normMean[i]) / this.normStd[i])) * 0.2;
    } else {
      for (let i = 0; i < N_SCREEN; i++) flat[i] = (small[i] - 0.35) * 0.5;
    }
    const out = new Float64Array(N_SCREEN);
    for (let t = 0; t < GRID * GRID; t++) {
      const r0 = Math.floor(t / GRID) * TILE, c0 = (t % GRID) * TILE, base = t * TILE * TILE;
      for (let y = 0; y < TILE; y++) for (let x = 0; x < TILE; x++) out[base + y * TILE + x] = flat[(r0 + y) * 84 + c0 + x];
    }
    return out;
  }

  // The 42 x 42 image shown inside the brain: 2 x 2 means of the retina, as bytes.
  retina(small) {
    const out = new Uint8Array(42 * 42);
    for (let y = 0; y < 42; y++) for (let x = 0; x < 42; x++) {
      const i = (2 * y) * 84 + 2 * x;
      out[y * 42 + x] = Math.trunc(((small[i] + small[i + 1] + small[i + 84] + small[i + 85]) / 4) * 255);
    }
    return out;
  }
}

const mean = values => values.reduce((a, b) => a + b, 0) / values.length;

// The brain's side of a runner: witnesses, probes, the takeover gate, then acting and feedback through
// Reinforcement. One serial owner calls iterate(); the game side never waits for it.
export class BrainSide {
  constructor(game, meanings, { seed = 0, lifeLearn = true } = {}) {
    this.game = game;
    this.meanings = meanings;
    this.nActions = meanings.length;
    this.seed = seed;
    this.lifeLearn = lifeLearn;
    this.zeroAct = new Float64Array(this.nActions);
    this.brain = buildBrain(this.nActions, seed);
    this.rf = null;
    this.phase = 'watching';
    this.witnesses = 0;
    this.batches = 0;
    this.admissions = 0;
    this.lastSweeps = null;
    this.sweepsHist = [];
    this.agreeHist = [];
    this.coherence = 0.0;
    this.firstSweeps = null;
    this.agreement = [];
    this.transitions = 0;
    this.lifeAdmissions = 0;
    this.scoreSums = new Float64Array(this.nActions);
    this.scoreN = 0;
    this.batchBuf = [];
    this.pending = false;
    this.currentAction = 0;
    this.faults = 0;
    this.lastError = null;
    this.beat = Date.now();
    this.prevState = null;
    this.viz = null;
    this.vizT = 0;
    this.takeoverAt = null;
    this.lastDecisionSeq = -Infinity;
  }

  populations() {
    return this.brain.inspect().populations.map(p => ({ name: p.name, count: p.patches, start: p.indices[0] }));
  }

  // A sample of the wiring for the visualization, drawn as the server draws it.
  graphSample(maxEdges = 520) {
    const rng = new PyRandom(7), g = this.brain.graph, byKind = new Map();
    for (let e = 0; e < g.nEdges; e++) {
      const kind = ['input', 'state', 'residual'][g.kinds[e]];
      if (!byKind.has(kind)) byKind.set(kind, []);
      byKind.get(kind).push(e);
    }
    const picked = [];
    for (const [kind, members] of byKind) {
      if (kind === 'input') for (const i of rng.sample(members.length, Math.min(members.length, 260))) picked.push(members[i]);
      else if (members.length <= 300) picked.push(...members);
      else for (const i of rng.sample(members.length, 300)) picked.push(members[i]);
    }
    picked.sort((a, b) => a - b);
    return picked.slice(0, maxEdges).map(e => [g.kinds[e] === 0 ? 0 : g.kinds[e] === 1 ? 1 : 2, g.sources[e], g.targets[e], Math.round(this.brain.weights[e] * 1000) / 1000]);
  }

  inputsFor(tiles, action = this.zeroAct) {
    const flat = new Float64Array(this.brain.graph.nInputs);
    flat.set(tiles, 0);
    flat.set(action, N_SCREEN);
    return flat;
  }

  _admit() {
    const size = Math.min(this.batchBuf.length, this.batches === 0 ? 8 : this.batches === 1 ? 16 : BATCH);
    const batch = this.batchBuf.slice(-size);
    this.batchBuf = [];
    let res;
    try {
      res = this.brain.observeBatch(batch);
    } catch (error) {
      console.log(`${this.game}: admission refused: ${error.message}`);
      return;
    }
    this.batches++;
    this.lastSweeps = res.sweeps;
    this.sweepsHist.push(res.sweeps);
    this.sweepsHist = this.sweepsHist.slice(-48);
    if (res.accepted) {
      const perWitness = res.sweeps / Math.max(1, batch.length);
      if (this.firstSweeps === null) this.firstSweeps = Math.max(0.01, perWitness);
      this.coherence = Math.round(Math.max(0, Math.min(1, 1 - perWitness / this.firstSweeps)) * 1000) / 1000;
      this.admissions++;
      this.witnesses += batch.length;
    }
  }

  // One real settle; the visualization gets the new equilibrium and how far every patch moved to reach it.
  _settleViz(flat) {
    const result = this.brain.settleFlat(flat, { budget: 64 });
    const state = Array.from(result.state, x => Math.round(x * 1000) / 1000);
    const prev = this.prevState;
    const delta = prev && prev.length === state.length ? state.map((a, i) => Math.round(Math.abs(a - prev[i]) * 1000) / 1000) : state.map(() => 0);
    this.prevState = state;
    this.viz = { state, errors: Array.from(result.errors, e => Math.round(e * 1000) / 1000), delta,
                 energy: Math.round(result.energy * 100000) / 100000, q: !!result.qualified };
    this.vizT = Date.now();
    return result;
  }

  _probe(tiles, teacher) {
    const result = this._settleViz(this.inputsFor(tiles));
    const motor = result.outputs.motor;
    for (let j = 0; j < this.nActions; j++) this.scoreSums[j] += motor[j];
    this.scoreN++;
    const decoded = this._decode(motor);
    this.agreement.push(decoded === teacher ? 1 : 0);
    this.agreement = this.agreement.slice(-120);
    if (this.agreement.length >= 10) {
      this.agreeHist.push(Math.round(mean(this.agreement) * 1000) / 1000);
      this.agreeHist = this.agreeHist.slice(-60);
    }
    return decoded;
  }

  _decode(motor) {
    let best = 0, bestValue = -Infinity;
    const n = Math.max(1, this.scoreN);
    for (let j = 0; j < this.nActions; j++) {
      const v = motor[j] - this.scoreSums[j] / n;
      if (v > bestValue) { bestValue = v; best = j; }
    }
    return best;
  }

  agree() {
    return this.agreement.length >= 30 ? mean(this.agreement) : 0.0;
  }

  // One brain iteration over the latest snapshot {tiles, teacher, reward, done, seq}; `reward` is the reward
  // accumulated since the last consumed feedback, `done` whether an episode ended since the last consumed
  // snapshot, `seq` the environment step count. Returns what the game side must know: a phase change or a
  // chosen action. The caller keeps `reward` accumulating until `consumedReward` is reported and keeps `done`
  // raised while `skipped` is reported (the held action continues until the next decision is due).
  iterate(snap) {
    this.beat = Date.now();
    const out = {};
    if (this.phase === 'playing' && this.pending && snap.seq !== undefined && snap.seq - this.lastDecisionSeq < DECISION_EVERY) {
      return { skipped: true };
    }
    if (this.phase === 'watching') {
      const target = new Array(this.nActions).fill(-0.6);
      target[snap.teacher] = 0.6;
      this.batchBuf.push({ inputs: this.inputsFor(snap.tiles), targets: { motor: target } });
      if (this.batchBuf.length >= BATCH) this._admit();
      if (this.batchBuf.length % 5 === 0) this._probe(snap.tiles, snap.teacher);
      const agree = this.agree();
      const gate = AGREE_TO_PLAY[this.game] ?? AGREE_DEFAULT;
      if ((this.witnesses >= WATCH_MIN_WITNESSES && agree >= gate) || this.witnesses >= WATCH_MAX_WITNESSES) {
        console.log(`${this.game}: TAKEOVER at ${this.witnesses} witnesses, agreement ${agree.toFixed(2)}`);
        this.rf = new Reinforcement(this.brain, { actions: this.nActions, action_input: 'action', value_output: 'value',
                                                   discount: 0.95, exploration: 0.05, reward_scale: 1.0, capacity: 2048, batch_size: 16, seed: 0 });
        this.phase = 'playing';
        this.takeoverAt = { witnesses: this.witnesses, agreement: agree, time: Date.now() };
        out.takeover = true;
      }
      return out;
    }
    if (this.pending) {
      const reward = Math.max(-1, Math.min(1, snap.reward / REWARD_SCALE[this.game]));
      out.consumedReward = true;
      try {
        const fb = this.rf.feedback(reward, snap.done ? null : snap.tiles, { terminal: !!snap.done, learn: false });
        this.transitions = fb.transitions ?? this.transitions;
        if (this.lifeLearn && this.transitions % REPLAY_EVERY === 0) {
          const rp = this.rf.replay({ budget: 2048 });
          if (rp.accepted) this.lifeAdmissions++;
        }
      } catch (error) {
        if (error instanceof RangeError || /must|exceeds|requires|pending/.test(error.message)) this.rf.reset();
        else throw error;
      }
      this.pending = false;
      if (snap.done) return out;
    }
    let picked;
    try {
      picked = this.rf.act(snap.tiles, { budget: BUDGET });
    } catch (error) {
      if (error instanceof RangeError || /must|exceeds|requires|pending/.test(error.message)) { this.rf.reset(); return out; }
      throw error;
    }
    if (picked.action !== null) {
      this.currentAction = picked.action;
      this.pending = true;
      if (this.transitions % 4 === 0) this._settleViz(this.inputsFor(snap.tiles));
    } else {
      const result = this._settleViz(this.inputsFor(snap.tiles));
      this.currentAction = this._decode(result.outputs.motor);
    }
    if (snap.seq !== undefined) this.lastDecisionSeq = snap.seq;
    out.action = this.currentAction;
    return out;
  }

  // The server's /state view of the brain side.
  state() {
    const agree = this.agreement.length ? Math.round(mean(this.agreement) * 100) / 100 : null;
    const gate = AGREE_TO_PLAY[this.game] ?? AGREE_DEFAULT;
    const toTakeover = Math.min(1, Math.min(1, this.witnesses / WATCH_MIN_WITNESSES)
      * (this.agreement.length >= 30 ? Math.min(1, (agree || 0) / gate) : this.agreement.length / 60));
    return {
      phase: this.phase,
      watch: { witnesses: this.witnesses, batches: this.batches, to_takeover: Math.round(toTakeover * 100) / 100,
               admissions: this.admissions, sweeps: this.lastSweeps, agreement: agree,
               sweeps_hist: this.sweepsHist, agree_hist: this.agreeHist, coherence: this.coherence },
      brain: { beat_age: Math.round((Date.now() - this.beat) / 100) / 10, faults: this.faults, last_error: this.lastError },
      life: { transitions: this.transitions, admissions: this.lifeAdmissions },
      takeover: this.takeoverAt,
    };
  }
}

// The game's side of a runner: the emulator loop that never waits for the brain, the scores and the badge.
export class GameSide {
  constructor(env, game) {
    this.env = env;
    this.game = game;
    this.meanings = env.actions;
    this.teacher = teacherAction(game, this.meanings);
    this.perception = new Perception();
    this.phase = 'watching';
    this.currentAction = 0;
    this.execAction = 0;
    this.tick = 0;
    this.episode = 0;
    this.score = 0;
    this.best = null;
    this.returns = [];
    this.teacherReturns = [];
    this.badge = 'hatchling';
    this.done = true;
  }

  updateBadge() {
    if (!this.returns.length || !this.teacherReturns.length) return;
    const t = Math.max(1e-9, mean(this.teacherReturns));
    const recent = mean(this.returns.slice(-5));
    const frac = recent / t;
    this.badge = frac > 1.0 ? 'legend' : frac >= 0.8 ? 'expert' : frac >= 0.3 ? 'intermediate' : 'noob';
  }

  // One environment step. Returns the brain's snapshot of the observation before the step and the step's outcome.
  step() {
    if (this.done) {
      this.env.reset();
      this.episode++;
      this.score = 0;
      this.done = false;
    }
    const small = this.perception.grey84(this.env.screen());
    this.perception.observe(small);
    this.tick++;
    const tiles = this.perception.tiles(small);
    const retina = this.tick % 3 === 0 ? this.perception.retina(small) : null;
    const action = this.phase === 'watching' ? this.teacher : this.currentAction;
    this.execAction = action;
    const r = this.env.step(action);
    this.score += r.reward;
    this.done = r.terminal || r.truncated;
    if (this.done) {
      if (this.phase === 'watching') {
        this.teacherReturns.push(this.score);
        this.teacherReturns = this.teacherReturns.slice(-20);
      } else {
        this.returns.push(this.score);
        this.returns = this.returns.slice(-60);
        if (this.best === null || this.score > this.best) this.best = this.score;
        this.updateBadge();
      }
    }
    return { tiles, teacher: this.teacher, reward: r.reward, done: this.done, score: this.score, episode: this.episode, retina };
  }

  metaAction() {
    return this.meanings[this.execAction] ?? 'NOOP';
  }

  state() {
    return {
      game: this.game, phase: this.phase, badge: this.badge, score: this.score, best: this.best, episode: this.episode,
      teacher: this.teacherReturns.length ? Math.round(mean(this.teacherReturns) * 10) / 10 : null,
      agent: AGENT_HINTS[this.game] ?? 'the brain is the player',
      returns: this.returns, action: this.metaAction(),
    };
  }
}
