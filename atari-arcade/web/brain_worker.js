// The brain's thread: one serial owner of the brain. Pyodide runs the released cadence-net wheel and
// arcade_brain.py, the same recipe the Python server composes; each file is checked against the SHA-256 in
// pack/manifest.json before it runs. The worker takes the latest screen the game sent, each screen at most once:
// a lesson while the teacher plays, a decision after the takeover. The page receives settled states and numbers.
const status = text => self.postMessage({ type: 'status', text });
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let port = null;
const inbox = { latest: null, seq: 0, consumed: 0, rewardAcc: 0, done: false };

async function checked(url, expected) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`cannot load ${url.pathname} (${response.status})`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (expected && self.crypto && self.crypto.subtle) {
    const digest = await self.crypto.subtle.digest('SHA-256', bytes);
    const actual = [...new Uint8Array(digest)].map(v => v.toString(16).padStart(2, '0')).join('');
    if (actual !== expected) throw new Error(`${url.pathname} does not match its manifest`);
  }
  return bytes;
}

async function loadBrain(game, meanings, seed) {
  const base = new URL('pack/', self.location.href);
  status('opening the runtime pack…');
  const response = await fetch(new URL('manifest.json', base), { cache: 'no-cache' });
  if (!response.ok) throw new Error('the runtime pack is missing: run pack.py');
  const manifest = await response.json();
  if (manifest.schema !== 'cadence-arcade-pack/1') throw new Error('not an arcade runtime pack');
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  status('starting Python in your browser…');
  const { loadPyodide } = await import(cdn + 'pyodide.mjs');
  const py = await loadPyodide({ indexURL: cdn });
  status('loading NumPy…');
  await py.loadPackage('numpy');
  status(`loading Cadence ${manifest.cadence}…`);
  py.unpackArchive(await checked(new URL(manifest.wheel, base), manifest.wheel_sha256), 'wheel');
  for (const name of manifest.sources) {
    py.FS.writeFile(`/home/pyodide/${name}`, await checked(new URL(`py/${name}`, base), manifest.sources_sha256[name]));
  }
  status('the brain is being born…');
  py.globals.set('_game', game);
  py.globals.set('_meanings', JSON.stringify(meanings));
  py.globals.set('_seed', seed);
  py.runPython(`
import sys, json, warnings
warnings.simplefilter("ignore")
if "/home/pyodide" not in sys.path:
    sys.path.insert(0, "/home/pyodide")
import numpy as np
from arcade_brain import BrainSide
_side = BrainSide(_game, json.loads(_meanings), seed=int(_seed))

def _iterate(drive, teacher, reward, done, games):
    out = _side.iterate(np.asarray(drive.to_py(), dtype=np.float64), teacher, reward, done, games)
    reply = {"out": out, "viz_t": _side.viz_t}
    return json.dumps(reply)

def _viz():
    return json.dumps({"traj": [_side.viz] if _side.viz else [], "t": _side.viz_t, "rewarded": _side.rewarded})

def _state():
    return json.dumps(_side.state())

def _graph():
    return json.dumps({"populations": _side.populations(), "edges": _side.graph_sample(),
                       "cadence": __import__("cadence").__version__, "compose_ms": round(_side.compose_ms)})
`);
  return { py, manifest };
}

self.onmessage = async event => {
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
    const { py, manifest } = await loadBrain(m.game, m.meanings, m.seed ?? 0);
    const g = JSON.parse(py.globals.get('_graph')());
    self.postMessage({ type: 'ready', graph: { populations: g.populations, n_screen: 84 * 84,
                                                n_action: m.meanings.length, meanings: m.meanings, edges: g.edges,
                                                cadence: manifest.cadence } });
    run(py);
  } catch (error) {
    self.postMessage({ type: 'error', message: `${error.name}: ${error.message}` });
  }
};

async function run(py) {
  const iterate = py.globals.get('_iterate'), viz = py.globals.get('_viz'), state = py.globals.get('_state');
  let lastState = 0, vizT = 0;
  for (;;) {
    // Every iteration sees a fresh screen: the brain never decides twice on one frame.
    if (!inbox.latest || inbox.consumed === inbox.seq) { await sleep(2); continue; }
    const snap = inbox.latest;
    const reward = inbox.rewardAcc, done = inbox.done;
    inbox.consumed = inbox.seq;
    const reply = JSON.parse(iterate(snap.drive, snap.teacher, reward, done, snap.teacherGames ?? 0));
    const out = reply.out;
    if (out.consumed) { inbox.rewardAcc = 0; inbox.done = false; }
    if (out.takeover) port.postMessage({ type: 'phase', phase: 'playing' });
    if (out.action !== undefined) port.postMessage({ type: 'action', action: out.action });
    if (reply.viz_t !== vizT) {
      vizT = reply.viz_t;
      self.postMessage({ type: 'brain', ...JSON.parse(viz()) });
    }
    const now = performance.now();
    if (now - lastState > 300 || out.takeover) {
      lastState = now;
      self.postMessage({ type: 'state', state: JSON.parse(state()) });
    }
    await sleep(0);
  }
}
