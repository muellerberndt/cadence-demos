// The game's thread: the Atari 2600 core and the perception, stepping at the chosen pace and never waiting for
// the brain. Every observation goes to the brain worker over a direct channel; frames and the score go to the page.
import { Environment, GAMES } from './emulator.js';
import { GameSide } from './arcade.js';

let env = null, side = null, port = null;
let sleepMs = 0, running = false, lastFrameAt = 0, lastRetina = null;
const FRAME_EVERY_MS = 100;
// Full speed is four times real time (sixty agent steps a second); the slider adds a pause per step.
const STEP_MS = 1000 / 60;

self.onmessage = async event => {
  const m = event.data;
  try {
    if (m.type === 'boot') {
      port = m.port;
      port.onmessage = ev => {
        const d = ev.data;
        if (d.type === 'action') side.currentAction = d.action;
        else if (d.type === 'phase') side.phase = d.phase;
      };
      const response = await fetch(new URL(GAMES[m.game].rom, m.base).href);
      if (!response.ok) throw new Error(`cannot load ${GAMES[m.game].rom}: ${response.status}`);
      env = new Environment(m.game, new Uint8Array(await response.arrayBuffer()), { seed: m.seed ?? 0 });
      side = new GameSide(env, m.game);
      self.postMessage({ type: 'ready', meanings: env.actions, teacher: side.teacher });
      running = true;
      loop();
    } else if (m.type === 'pace') {
      sleepMs = Math.max(0, Math.round(m.sleep * 1000));
    } else if (m.type === 'pause') {
      running = false;
    } else if (m.type === 'resume') {
      if (!running) { running = true; loop(); }
    }
  } catch (error) {
    self.postMessage({ type: 'error', message: `${error.name}: ${error.message}` });
  }
};

function loop() {
  if (!running) return;
  const started = performance.now();
  const snap = side.step();
  if (snap.retina) lastRetina = snap.retina;
  port.postMessage({ type: 'step', tiles: snap.tiles, teacher: snap.teacher, reward: snap.reward, done: snap.done }, [snap.tiles.buffer]);
  const now = performance.now();
  if (now - lastFrameAt >= FRAME_EVERY_MS || snap.done) {
    lastFrameAt = now;
    const rgba = env.screen().slice();
    const message = { type: 'frame', rgba, state: side.state(), retina: lastRetina };
    const transfer = [rgba.buffer];
    if (lastRetina) { transfer.push(lastRetina.buffer); lastRetina = null; }
    self.postMessage(message, transfer);
  }
  setTimeout(loop, Math.max(0, Math.max(STEP_MS, sleepMs) - (performance.now() - started)));
}
