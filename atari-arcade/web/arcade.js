// The arcade's loop, shared by the browser workers and the headless runner: the retina, the scripted teachers, the
// brain side (watching, the takeover, living on reward) and the game side (episodes, scores, the skill badge). It
// follows atari-arcade/server.py; the Python server remains the reference.
import { Brain, Generator, Refusal } from './cadence.js';

export const N_SCREEN = 84 * 84;
export const RETINA_FRAMES = 300;       // screens of random play averaged into the background
export const RETINA_GAIN = 2.0;
export const MIN_LESSONS = 500;
export const MAX_LESSONS = 2000;
export const AGREE_WINDOW = 120;
export const AGREE_TO_PLAY = {};
export const AGREE_DEFAULT = 0.9;
// The server's settings: Brain.compose defaults, with each synapse stepping on its own running mean over its own
// running size.
export const LEARNING = { beta: 0.1, temperature: 0.2, tolerance: 3e-3, free_steps: 1024, nudged_steps: 12,
                          eta_bias: 0.02, eta: 0.003, momentum: 0.9, normalize: 0.99, normalize_floor: 1e-4 };
export const REWARD = { gamma: 0.97, lam: 0.9, eta: 0.001, eta_critic: 0.3, momentum: 0.9, normalize: 0.99 };

export const AGENT_HINTS = {
  Atlantis: 'the brain fires the three gun bases',
  Freeway: 'the brain is the chicken crossing the road',
};
export const TEACHER = { Freeway: 'UP', Atlantis: 'FIRE' };

export function teacherAction(game, meanings) {
  const name = TEACHER[game];
  if (!name) throw new Error(`no teacher for ${game}`);
  return meanings.indexOf(name);
}

export function buildBrain(nActions, seed = 0) {
  return Brain.compose(N_SCREEN, nActions, { seed, learning: LEARNING, reward: REWARD });
}

// 210 x 160 RGBA pixels to the 84 x 84 luminance retina; the brain's input is what differs from a fixed background.
export class Perception {
  constructor() {
    this.rowEdges = new Int32Array(85);
    this.colEdges = new Int32Array(85);
    for (let i = 0; i < 84; i++) { this.rowEdges[i] = Math.trunc(i * 2.5); this.colEdges[i] = Math.trunc(i * (160 / 84)); }
    this.rowEdges[84] = 210; this.colEdges[84] = 160;
    this.rows = new Float64Array(84 * 160);
    this.background = new Float64Array(N_SCREEN);
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

  // The mean screen of random play, taken once before the brain is born and never updated.
  learnBackground(env, seed) {
    const rng = new Generator(10000 + seed), total = new Float64Array(N_SCREEN);
    env.reset();
    for (let f = 0; f < RETINA_FRAMES; f++) {
      const small = this.grey84(env.screen());
      for (let i = 0; i < N_SCREEN; i++) total[i] += small[i];
      const r = env.step(rng.integers(env.actions.length));
      if (r.terminal || r.truncated) env.reset();
    }
    for (let i = 0; i < N_SCREEN; i++) this.background[i] = total[i] / RETINA_FRAMES;
  }

  drive(small) {
    const out = new Float64Array(N_SCREEN), background = this.background;
    for (let i = 0; i < N_SCREEN; i++) out[i] = (small[i] - background[i]) * RETINA_GAIN;
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
const round = (value, digits) => Math.round(value * 10 ** digits) / 10 ** digits;

// The brain's side of a runner: a lesson per watched screen, the takeover gate, then one decision per screen it gets
// to see, learning from the reward since its last decision. One serial owner calls iterate(); the game side never
// waits for it.
export class BrainSide {
  constructor(game, meanings, { seed = 0, lifeLearn = true } = {}) {
    this.game = game;
    this.meanings = meanings;
    this.nActions = meanings.length;
    this.seed = seed;
    this.lifeLearn = lifeLearn;
    this.brain = buildBrain(this.nActions, seed);
    this.phase = 'watching';
    this.lessons = 0;
    this.agreement = [];
    this.agreeHist = [];
    this.sweepsHist = [];
    this.lastSweeps = null;
    this.decisions = 0;
    this.outcomes = 0;       // outcomes of its own actions learned from
    this.rewarded = 0;       // those with a reward in them
    this.refused = 0;
    this.value = 0;
    this.dopamine = 0;
    this.pending = false;    // an own executed action awaits its outcome
    this.currentAction = 0;
    this.faults = 0;
    this.lastError = null;
    this.beat = Date.now();
    this.thinkMs = [];
    this.prevState = null;
    this.viz = null;
    this.vizT = 0;
    this.takeoverAt = null;
    this.born = Date.now();
  }

  // The page's nodes: association cortex, working trace, motor cortex, memory, value.
  populations() {
    const n = this.brain.nH, a = this.nActions;
    return [{ name: 'association', count: n, start: 0 }, { name: 'trace', count: n, start: n },
            { name: 'motor', count: a, start: 2 * n }, { name: 'memory', count: a, start: 2 * n + a },
            { name: 'value', count: 1, start: 2 * n + 2 * a }];
  }

  // Synapses as [kind, source, target, weight]; kind 0 starts at a retina pixel, kind 1 at another node. The
  // strongest of a random tenth, with their current weights.
  graphSample(perKind = 260) {
    const brain = this.brain, nH = brain.nH, nA = this.nActions, rng = new Generator(7);
    const trim = e => [e[0], e[1], e[2], round(e[3], 3)];
    const fromPixels = [];
    for (let k = 0; k < 10 * perKind; k++) {
      const i = rng.integers(brain.nS), h = rng.integers(nH);
      fromPixels.push([0, i, h, brain.w.sa[i * nH + h]]);
    }
    fromPixels.sort((x, y) => Math.abs(y[3]) - Math.abs(x[3]));
    const inner = [];
    for (let p = 0; p < nH; p++) for (let h = 0; h < nH; h++) inner.push([1, nH + p, h, brain.w.pa[p * nH + h]]);
    for (let h = 0; h < nH; h++) for (let m = 0; m < nA; m++) inner.push([1, h, 2 * nH + m, brain.w.am[h * nA + m]]);
    for (let m = 0; m < nA; m++) for (let h = 0; h < nH; h++) inner.push([1, 2 * nH + m, h, brain.w.ma[m * nH + h]]);
    for (let i = 0; i < nA; i++) for (let j = 0; j < nA; j++) if (i !== j) inner.push([1, 2 * nH + i, 2 * nH + j, brain.w.mm[i * nA + j]]);
    inner.sort((x, y) => Math.abs(y[3]) - Math.abs(x[3]));
    return [...fromPixels.slice(0, perKind).map(trim), ...inner.slice(0, 2 * perKind).map(trim)];
  }

  // What the page sees of one settled state.
  _show(state, sweeps, x, wrongAction = null) {
    const brain = this.brain, memory = brain.recall(x);
    const vec = [...state.sH, ...state.sP, ...state.sM, ...memory, this.value];
    const prev = this.prevState;
    const delta = prev && prev.length === vec.length ? vec.map((v, i) => Math.abs(v - prev[i])) : vec.map(() => 0);
    this.prevState = vec;
    const errors = vec.map(() => 0);
    errors[errors.length - 1] = Math.min(1, Math.abs(this.dopamine));
    if (wrongAction !== null) errors[2 * brain.nH + wrongAction] = 1;
    this.lastSweeps = sweeps;
    this.sweepsHist.push(sweeps);
    this.sweepsHist = this.sweepsHist.slice(-48);
    this.viz = { state: vec.map(v => round(v, 3)), errors: errors.map(v => round(v, 3)), delta: delta.map(v => round(v, 3)), q: true };
    this.vizT = Date.now();
  }

  // One watched screen. First the brain's own answer, read greedily from its settled state: the teacher is at the
  // controls, so that answer is not executed and carries no eligibility. Then the lesson: the teacher's action as
  // the label of this screen.
  _watch(snap) {
    const brain = this.brain, x = snap.drive;
    const drive = brain.stimulus(x);
    let own = null;
    try {
      own = brain.act(x, { greedy: true });
    } catch (error) {
      if (!(error instanceof Refusal)) throw error;
      this.refused++;
      this.lastError = `refused: ${error.message}`;
    }
    this.agreement.push(own === snap.teacher ? 1 : 0);
    this.agreement = this.agreement.slice(-AGREE_WINDOW);
    if (own !== null && this.lessons % 3 === 0) {
      this.value = brain.value(brain.free);
      this._show(brain.free, brain.free.steps, x, own === snap.teacher ? null : snap.teacher);
    }
    brain.teach(drive, snap.teacher);
    this.lessons++;
    if (this.lessons % 10 === 0) {
      this.agreeHist.push(round(mean(this.agreement), 3));
      this.agreeHist = this.agreeHist.slice(-60);
    }
    const agree = mean(this.agreement), gate = AGREE_TO_PLAY[this.game] ?? AGREE_DEFAULT;
    // The badge measures the brain against the teacher's own games, so it watches at least one whole game.
    const ready = (this.lessons >= MIN_LESSONS && this.agreement.length >= AGREE_WINDOW && agree >= gate) || this.lessons >= MAX_LESSONS;
    if (ready && (snap.teacherGames ?? 1) >= 1) {
      console.log(`${this.game}: TAKEOVER at ${this.lessons} lessons, agreement ${agree.toFixed(2)}`);
      this.takeoverAt = { lessons: this.lessons, agreement: round(agree, 3), seconds: round((Date.now() - this.born) / 1000, 1), time: Date.now() };
      this.currentAction = snap.teacher;
      this.pending = false;
      this.phase = 'playing';
      return { takeover: true, action: this.currentAction, consumed: true };
    }
    return {};
  }

  // One decision of the brain at the controls: the outcome of its last action (the reward since then, whether an
  // episode ended), then the next action.
  _play(snap) {
    const brain = this.brain, x = snap.drive;
    try {
      let action;
      if (!this.lifeLearn) {          // the frozen twin: no outcome reaches it
        if (snap.done) brain.reset();
        action = brain.act(x);
      } else if (this.pending) {
        const signal = Math.sign(snap.reward);
        action = brain.step(x, { reward: signal, done: !!snap.done });
        this.outcomes++;
        if (signal !== 0) this.rewarded++;
        this.dopamine = brain.lastLearning.dopamine ?? 0;
      } else {
        action = brain.step(x);
      }
      this.currentAction = action;
    } catch (error) {
      if (!(error instanceof Refusal)) throw error;
      // The brain did not settle: no action was issued. The body keeps holding its last action and that stretch
      // is never credited.
      this.refused++;
      this.lastError = `refused: ${error.message}`;
      this.pending = false;
      if (snap.done) brain.reset();
      return { consumed: true };
    }
    this.pending = true;
    this.decisions++;
    this.agreement.push(this.currentAction === snap.teacher ? 1 : 0);
    this.agreement = this.agreement.slice(-AGREE_WINDOW);
    this.value = brain.value(brain.free);
    if (this.decisions % 3 === 0) this._show(brain.free, brain.free.steps + (brain.lastLearning.free_steps ?? 0), x);
    if (this.decisions % 10 === 0) {
      this.agreeHist.push(round(mean(this.agreement), 3));
      this.agreeHist = this.agreeHist.slice(-60);
    }
    return { action: this.currentAction, consumed: true };
  }

  // One brain iteration over the latest snapshot {drive, teacher, reward, done, teacherGames}; `reward` is the
  // reward since the brain's last decision and `done` whether an episode ended since then. The caller clears both
  // when `consumed` is reported.
  iterate(snap) {
    this.beat = Date.now();
    const started = performance.now();
    const out = this.phase === 'watching' ? this._watch(snap) : this._play(snap);
    this.thinkMs.push(performance.now() - started);
    if (this.thinkMs.length > 20000) this.thinkMs = this.thinkMs.slice(-20000);
    return out;
  }

  // The server's /state view of the brain side.
  state() {
    const agree = this.agreement.length ? round(mean(this.agreement), 2) : null;
    const gate = AGREE_TO_PLAY[this.game] ?? AGREE_DEFAULT;
    const recent = this.thinkMs.slice(-200).sort((a, b) => a - b);
    return {
      phase: this.phase,
      watch: { lessons: this.lessons, to_takeover: round(Math.min(1, this.lessons / MIN_LESSONS) * Math.min(1, (agree || 0) / gate), 2),
               sweeps: this.lastSweeps, agreement: agree, sweeps_hist: this.sweepsHist, agree_hist: this.agreeHist,
               takeover: this.takeoverAt },
      brain: { beat_age: Math.round((Date.now() - this.beat) / 100) / 10, faults: this.faults, last_error: this.lastError },
      life: { decisions: this.decisions, outcomes: this.outcomes, refused: this.refused, rewarded: this.rewarded,
              think_ms: recent.length ? round(recent[Math.floor(recent.length / 2)], 1) : null,
              think_ms_scope: 'median of latest 200 brain handlers; watching and play, including handled refusals; excludes uncaught faults',
              value: round(this.value, 3), dopamine: round(this.dopamine, 3) },
    };
  }
}

// The game's side of a runner: the emulator loop that never waits for the brain, the scores and the badge.
export class GameSide {
  constructor(env, game, { seed = 0 } = {}) {
    this.env = env;
    this.game = game;
    this.meanings = env.actions;
    this.teacher = teacherAction(game, this.meanings);
    this.perception = new Perception();
    this.perception.learnBackground(env, seed);
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
    this.watched = true;       // the running episode began with the teacher at the controls
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
      this.watched = this.phase === 'watching';
    }
    const small = this.perception.grey84(this.env.screen());
    this.tick++;
    const drive = this.perception.drive(small);
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
      } else if (!this.watched) {       // a whole episode at the brain's controls
        this.returns.push(this.score);
        this.returns = this.returns.slice(-60);
        if (this.best === null || this.score > this.best) this.best = this.score;
        this.updateBadge();
      }
    }
    return { drive, teacher: this.teacher, reward: r.reward, done: this.done, score: this.score, episode: this.episode,
             retina, teacherGames: this.teacherReturns.length };
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
