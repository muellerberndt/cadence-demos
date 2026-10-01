// The browser arcade without a browser: the same emulator, perception, brain and loop in one Node process, run
// until the brain has taken the controls and lived a few episodes. The game advances as it would beside a live
// brain (sixty steps per second of brain time, the page's full speed). Writes a receipt.
//   node headless.mjs --game Freeway --episodes 5 --minutes 30 --out receipts/freeway.json [--frozen]
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Environment, GAMES } from './emulator.js';
import { BrainSide, GameSide } from './arcade.js';

const root = dirname(fileURLToPath(import.meta.url));
const args = Object.fromEntries(process.argv.slice(2).map((a, i, all) => a.startsWith('--') ? [a.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : true] : null).filter(Boolean));
const game = args.game || 'Freeway';
const episodesTarget = Number(args.episodes || 5);
const minutes = Number(args.minutes || 30);
const seed = Number(args.seed || 0);
const lifeLearn = !args.frozen;
const stepMs = 1000 / 60;   // the page's full speed: sixty agent steps a second

const env = new Environment(game, readFileSync(join(root, GAMES[game].rom)), { seed });
const side = new GameSide(env, game);
const brain = new BrainSide(game, env.actions, { seed, lifeLearn });
const inbox = { latest: null, seq: 0, consumed: 0, rewardAcc: 0, done: false };
const t0 = Date.now(), deadline = t0 + minutes * 60000;
const log = [];
let stepsRun = 0, iterations = 0;

function advance(steps) {
  for (let i = 0; i < steps; i++) {
    const snap = side.step();
    inbox.latest = snap; inbox.seq++;
    inbox.rewardAcc += snap.reward;
    inbox.done = inbox.done || snap.done;
    stepsRun++;
  }
}

advance(1);
while (Date.now() < deadline) {
  if (brain.phase === 'watching' && inbox.consumed === inbox.seq) advance(1);
  const snap = { tiles: inbox.latest.tiles, teacher: inbox.latest.teacher, reward: inbox.rewardAcc, done: inbox.done, seq: inbox.seq };
  inbox.consumed = inbox.seq;
  const started = Date.now();
  let out;
  try {
    out = brain.iterate(snap);
  } catch (error) {
    brain.faults++; brain.lastError = `${error.name}: ${error.message}`;
    console.log(`${game}: BRAIN FAULT ${brain.lastError}`);
    out = {};
  }
  if (!out.skipped) inbox.done = false;
  if (out.consumedReward) inbox.rewardAcc = 0;
  if (out.takeover) { side.phase = 'playing'; log.push({ t: (Date.now() - t0) / 1000, event: 'takeover', ...brain.takeoverAt }); }
  if (out.action !== undefined) side.currentAction = out.action;
  const elapsed = Date.now() - started;
  advance(Math.max(1, Math.round(elapsed / stepMs)));
  if (side.phase === 'playing' && side.returns.length >= episodesTarget) break;
  if (++iterations % 50 === 0 || elapsed > 1000 || out.takeover) {
    const s = brain.state();
    console.log(`${((Date.now() - t0) / 1000).toFixed(0)}s ${brain.phase} ep ${side.episode} score ${side.score} witnesses ${s.watch.witnesses} agree ${s.watch.agreement} sweeps ${s.watch.sweeps} understanding ${s.watch.coherence} lived ${JSON.stringify(side.returns)} badge ${side.badge}`);
  }
}

const receipt = {
  game, seed, life_learn: lifeLearn, seconds: (Date.now() - t0) / 1000, env_steps: stepsRun,
  takeover: brain.takeoverAt ? { ...brain.takeoverAt, seconds_after_birth: (brain.takeoverAt.time - t0) / 1000 } : null,
  teacher_returns: side.teacherReturns, teacher_mean: side.teacherReturns.length ? side.teacherReturns.reduce((a, b) => a + b, 0) / side.teacherReturns.length : null,
  returns: side.returns, best: side.best, badge: side.badge, understanding: brain.coherence, witnesses: brain.witnesses,
  admissions: brain.admissions, life_admissions: brain.lifeAdmissions, transitions: brain.transitions, faults: brain.faults, last_error: brain.lastError,
  sweeps_hist: brain.sweepsHist, agree_hist: brain.agreeHist, log,
};
if (args.out) { mkdirSync(dirname(join(root, args.out)), { recursive: true }); writeFileSync(join(root, args.out), JSON.stringify(receipt, null, 1) + '\n'); }
console.log(JSON.stringify({ ...receipt, sweeps_hist: undefined, agree_hist: undefined }));
console.log('HEADLESS-DONE');
