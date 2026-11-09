// The arcade's game side, shared by the emulator worker: the retina, the scripted teachers and the game loop
// (episodes, scores, the skill badge). The brain runs in brain_worker.js: the released cadence-net wheel and
// ../arcade_brain.py in Pyodide. It follows atari-arcade/server.py.

export const N_SCREEN = 84 * 84;
export const RETINA_FRAMES = 300;       // screens of random play averaged into the background
export const RETINA_GAIN = 2.0;

// A small seeded generator for the background's random play (mulberry32).
export class Generator {
  constructor(seed) { this.a = seed >>> 0; }
  next() {
    let t = (this.a = (this.a + 0x6D2B79F5) >>> 0);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  integers(n) { return Math.floor(this.next() * n); }
}

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
