// The simulator of the browser edition: one life, stepped in real time inside a worker so that drawing the page
// never delays a control step. It plays the part server.py's Runtime plays in the Python edition.
import { AUTOMATIC_STEPS, Life, MAX_STEPS, PROTOCOL } from './rover.js';

let life = null, running = false, hidden = false;
let seed = 17, weakGain = PROTOCOL.weak_gain;
let deadline = performance.now(), timer = null;

function publish(extra = {}) {
  const state = life ? life.state() : { ready: false, models: [] };
  postMessage({ type: 'state', state: { ...state, running, status: null, ...extra } });
}

function gain(data, fallback) {
  const value = data.weak_gain ?? fallback;
  if (typeof value !== 'number' || !(value >= 0.25 && value <= 0.5)) throw new Error('Wheel strength must be between 0.25 and 0.50');
  return value;
}

function control(data) {
  const action = data.action;
  if (action === 'reset') {
    const nextSeed = data.seed ?? seed, nextGain = gain(data, weakGain);
    running = false;
    life = new Life(nextSeed, nextGain);
    seed = nextSeed; weakGain = nextGain;
  } else if (action === 'start') {
    if (life.step >= MAX_STEPS) throw new Error('This life reached the 3,600-step limit; save it and restart');
    if (life.auto && life.step >= AUTOMATIC_STEPS) throw new Error('Automatic run complete; choose Run automatic demo to start a fresh life');
    running = true;
  } else if (action === 'pause') {
    running = false;
  } else if (action === 'weaken' || action === 'restore') {
    if (action === 'weaken') life.weakGain = gain(data, life.weakGain);
    life.auto = false;
    life.changePhase(action === 'weaken' ? 'weakened' : 'restored_probe');
  } else if (action === 'auto') {
    // The automatic sequence starts a fresh comparable life.
    const nextGain = gain(data, weakGain);
    running = false;
    life = new Life(seed, nextGain);
    weakGain = nextGain;
    running = true;
  } else if (action === 'relearn') {
    life.auto = false;
    life.changePhase('restored_learning');
  } else {
    throw new Error('Unknown control action');
  }
  deadline = performance.now();
  publish();
  return { ok: true };
}

function work() {
  timer = null;
  if (running && !hidden) {
    const queueDelay = Math.max(0, performance.now() - deadline);
    try {
      life.tick(queueDelay);
      if (life.step >= MAX_STEPS || (life.auto && life.step >= AUTOMATIC_STEPS)) running = false;
      publish();
    } catch (error) {
      running = false;
      publish({ error: `Simulation stopped: ${error.message}` });
    }
    // No catch-up burst: a slow command is measured and the simulation slows.
    deadline = Math.max(deadline + 1000 * PROTOCOL.dt, performance.now());
  } else {
    deadline = performance.now();
  }
  schedule();
}

function schedule() {
  if (timer === null) timer = setTimeout(work, running && !hidden ? Math.max(0, deadline - performance.now()) : 50);
}

onmessage = event => {
  const { id, operation, data } = event.data;
  try {
    let value;
    if (operation === 'control') value = control(data);
    else if (operation === 'checkpoint') value = life.snapshot();
    else if (operation === 'receipt') value = life.receipt();
    else if (operation === 'restore') {
      const candidate = Life.fromSnapshot(data);
      life = candidate; running = false;
      seed = candidate.seed; weakGain = candidate.weakGain;
      publish();
      value = { ok: true };
    } else if (operation === 'visibility') {
      // A hidden tab's timers are throttled by the browser. The life waits instead of recording false delays.
      hidden = Boolean(data.hidden);
      deadline = performance.now();
      value = { ok: true };
    } else throw new Error('Unknown request');
    postMessage({ type: 'reply', id, value });
  } catch (error) {
    postMessage({ type: 'reply', id, error: error.message });
  }
  if (timer !== null) { clearTimeout(timer); timer = null; }
  schedule();
};

try {
  postMessage({ type: 'state', state: { ready: false, running: false, error: null, models: [], status: 'Preparing measured motor experience' } });
  const requested = Number(new URLSearchParams(self.location.search).get('seed'));
  if (Number.isInteger(requested) && requested >= 0 && requested <= 2147483647 && self.location.search.includes('seed=')) seed = requested;
  life = new Life(seed, weakGain);
  publish();
} catch (error) {
  postMessage({ type: 'state', state: { ready: false, running: false, models: [], error: error.message } });
}
schedule();
