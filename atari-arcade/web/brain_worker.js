// The brain's thread: one serial owner of the brain and its learner. It consumes the latest observation the game
// sent, admits witnesses, probes, takes over, acts and feeds rewards back; the page receives equilibria and numbers.
import { BrainSide, GRID, N_SCREEN, TILE } from './arcade.js';

let side = null, port = null;
const inbox = { latest: null, seq: 0, consumed: 0, rewardAcc: 0, done: false };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

self.onmessage = event => {
  const m = event.data;
  if (m.type !== 'boot') return;
  try {
    port = m.port;
    port.onmessage = ev => {
      const d = ev.data;
      if (d.type !== 'step') return;
      inbox.latest = d;
      inbox.seq++;
      inbox.rewardAcc += d.reward;
      inbox.done = inbox.done || d.done;
    };
    side = new BrainSide(m.game, m.meanings, { seed: m.seed ?? 0 });
    self.postMessage({ type: 'ready', graph: { populations: side.populations(), n_screen: N_SCREEN, grid: GRID, tile: TILE,
                                                n_action: side.nActions, meanings: m.meanings, edges: side.graphSample() } });
    run();
  } catch (error) {
    self.postMessage({ type: 'error', message: `${error.name}: ${error.message}` });
  }
};

async function run() {
  let lastState = 0;
  for (;;) {
    // Every iteration sees a fresh observation: the brain never decides twice on one frame.
    if (!inbox.latest || inbox.consumed === inbox.seq) { await sleep(4); continue; }
    const snap = { tiles: inbox.latest.tiles, teacher: inbox.latest.teacher, reward: inbox.rewardAcc, done: inbox.done, seq: inbox.seq };
    inbox.consumed = inbox.seq;
    const vizBefore = side.vizT, admittedBefore = side.admissions + side.lifeAdmissions;
    let out = {};
    try {
      out = side.iterate(snap);
    } catch (error) {
      side.faults++;
      side.lastError = `${error.name}: ${error.message}`;
      console.error(error);
      await sleep(500);
    }
    if (!out.skipped) inbox.done = false;
    if (out.consumedReward) inbox.rewardAcc = 0;
    if (out.takeover) port.postMessage({ type: 'phase', phase: 'playing' });
    if (out.action !== undefined) port.postMessage({ type: 'action', action: out.action });
    const admitted = side.admissions + side.lifeAdmissions;
    if (side.vizT !== vizBefore || admitted !== admittedBefore) {
      self.postMessage({ type: 'brain', traj: side.viz ? [side.viz] : [], t: side.vizT, admissions: admitted });
    }
    const now = performance.now();
    if (now - lastState > 300 || out.takeover) {
      lastState = now;
      self.postMessage({ type: 'state', state: side.state() });
    }
    await sleep(0);
  }
}
