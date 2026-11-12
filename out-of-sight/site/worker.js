// The real Cadence brain runs here, off the page's thread, in Python through Pyodide. The wheel
// and the Python host are checked against the pack manifest's SHA-256 before anything runs.
// Messages: {rid, command, payload} in; {rid, result, arrays} or {rid, error} out; {status}
// while loading. `arrays` holds the typed arrays a reply names in `buffers`.
//
// The sight evidence. A place module's space moves a thing it does not see along its last seen
// movement. The page sends the scene as it stands at each moment (the camera's position,
// heading and field, the pillar where it stands, the arm's joints, and whether the camera is
// on), and `visible` of world.js is the scene's own rule for what the camera sees. Where the
// host's space takes a function, Python is given `look` below and asks it about any places it
// likes: the places it predicts, and the places ahead of a thing along its seen movement.
// Where the space takes flags alone, a moment is taken in two halves here: the host predicts
// every thing's place, this worker says for each whether the camera would see a thing there,
// and the host is given those flags with the camera's reports.
import { visible, forward } from './world.js';

let python = null;
let manifest = null;
let takesSight = false; // how the host's space takes the sight evidence: 'function', 'flags' or false
let view = null;        // the scene as it stands at the moment being answered

// Would the camera see a thing at each of these places? `flat` holds x, y, x, y, ...; one flag
// a place comes back. The arm's own hand tops its link: a place within a link's width of the
// arm's end is the hand's own, which its link does not hide.
function look(flat) {
  const out = new Array(flat.length >> 1).fill(false);
  if (!view || !view.on) return out;
  const g = view.geometry, chain = forward(g, view.joints), tip = chain.at(-1);
  for (let k = 0; k < out.length; k++) {
    const p = [flat[2 * k], flat[2 * k + 1]];
    const own = !!view.own && Math.hypot(p[0] - tip[0], p[1] - tip[1]) <= g.arm.width;
    out[k] = visible(g, p, view.joints, own, chain);
  }
  return out;
}
let chain = Promise.resolve();
const status = (message) => self.postMessage({ status: message });

async function checked(url, expected) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load ${url.pathname} (${response.status}).`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (expected) {
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    const actual = [...new Uint8Array(digest)].map((v) => v.toString(16).padStart(2, '0')).join('');
    if (actual !== expected) throw new Error(`Integrity check failed for ${url.pathname}.`);
  }
  return bytes;
}

async function initialize(payload) {
  const began = performance.now();
  // The page names the pack's address (absolute): a bundler may move this script elsewhere.
  const base = new URL(payload?.pack || 'pack/', self.location.href);
  status('Opening the brain pack');
  const response = await fetch(new URL('manifest.json', base));
  if (!response.ok) throw new Error('The brain pack is missing.');
  manifest = await response.json();
  if (manifest.schema !== 'cadence-out-of-sight-pack/1') throw new Error('This is not an Out of sight brain pack.');
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  status('Starting Python in your browser');
  const { loadPyodide } = await import(cdn + 'pyodide.mjs');
  python = await loadPyodide({ indexURL: cdn });
  status('Loading NumPy');
  await python.loadPackage('numpy');
  status(`Loading Cadence ${manifest.cadence}`);
  python.unpackArchive(await checked(new URL(manifest.wheel, base), manifest.wheel_sha256), 'wheel');
  python.FS.mkdirTree('/home/pyodide/spacebrain');
  for (const name of manifest.sources) {
    const bytes = await checked(new URL(`py/spacebrain/${name}`, base), manifest.sources_sha256[name]);
    python.FS.writeFile(`/home/pyodide/spacebrain/${name}`, bytes);
  }
  // The trained brain arrives as a module: a file of arrays with a JSON record. Where the pack
  // ships module files they are checked and written beside the host, which loads them with
  // cadence.load_module(path); a module named without files is loaded from the wheel with
  // cadence.modules.load(name). The module's own host (place_host.py) then answers the page's
  // messages. A pack without a module composes the baseline brain (host.py).
  const config = { ...(manifest.config || {}), ...(payload?.config || {}) };
  if (manifest.module) {
    status(`Loading the ${manifest.module.name} module`);
    const files = manifest.module.files || [];
    if (files.length) python.FS.mkdirTree('/home/pyodide/module');
    for (const file of files) python.FS.writeFile(`/home/pyodide/module/${file.name}`, await checked(new URL(`module/${file.name}`, base), file.sha256));
    config.module = { name: manifest.module.name, label: manifest.module.label || null, note: manifest.module.note || null,
      space: manifest.module.space || null, path: files.length ? `/home/pyodide/module/${files[0].name}` : null };
  }
  status(manifest.module ? 'Waking the brain' : 'Composing the brain');
  python.globals.set('_space_config', JSON.stringify(config));
  python.runPython(`
import sys, json, warnings
warnings.simplefilter('ignore')
if '/home/pyodide' not in sys.path:
    sys.path.insert(0, '/home/pyodide')
from spacebrain.host import make
_space_host = make(json.loads(_space_config))
def _space_handle(text):
    return json.dumps(_space_host.handle(json.loads(text)), allow_nan=False)
def _space_buffer(name):
    return _space_host.buffers[name]
def _space_looks(look):
    # the page's rule for what the camera sees, as a function of places for the host
    from pyodide.ffi import to_js
    import numpy as np
    _space_host.looks = lambda points: np.array(look(to_js(np.asarray(points, dtype=float).ravel().tolist())).to_py(), dtype=bool)
`);
  const out = call({ command: 'describe' });
  takesSight = out.reply.sight || false;
  if (takesSight === 'function') { const give = python.globals.get('_space_looks'); try { give(look); } finally { give.destroy(); } }
  out.reply.startup_ms = Math.round(performance.now() - began);
  out.reply.manifest = manifest;
  return out;
}

// One request to the Python host: its JSON reply and the typed arrays it filled.
function call(message) {
  if (!python) throw new Error('The brain is loading.');
  const handle = python.globals.get('_space_handle');
  const fetchBuffer = python.globals.get('_space_buffer');
  const began = performance.now();
  try {
    const reply = JSON.parse(handle(JSON.stringify(message)));
    const arrays = {};
    for (const name of reply.buffers || []) {
      const proxy = fetchBuffer(name);
      const view = proxy.getBuffer();
      try { arrays[name] = view.data.slice(); } finally { view.release(); proxy.destroy(); }
    }
    reply.worker_ms = Math.round((performance.now() - began) * 100) / 100;
    return { reply, arrays };
  } finally { handle.destroy(); fetchBuffer.destroy(); }
}

// One moment. With a view of the scene and a host that takes the sight evidence: the host's
// predicted places, which of them the camera would see, and the host's answer given that.
function step(payload) {
  const { view: scene, ...moment } = payload || {};
  view = scene ? { ...scene, own: !!moment.own } : null;
  if (!takesSight || !view) return call({ command: 'step', ...moment });
  // a function: Python asks `look` during the moment; flags: the two halves
  if (takesSight === 'function') return call({ command: 'step', ...moment, in_sight: true });
  const first = call({ command: 'predict', ...moment });
  const inSight = first.reply.predicted.map((place, k) => !!view.on && visible(view.geometry, place, view.joints, !!moment.own && k === 0));
  const out = call({ command: 'observe', in_sight: inSight });
  out.reply.worker_ms = Math.round((first.reply.worker_ms + out.reply.worker_ms) * 100) / 100;
  return out;
}

self.onmessage = ({ data }) => {
  chain = chain.then(async () => {
    const { rid, command, payload } = data;
    try {
      const outcome = command === 'init' ? await initialize(payload) : command === 'step' ? step(payload) : call({ command, ...(payload || {}) });
      const transfer = Object.values(outcome.arrays).map((a) => a.buffer);
      self.postMessage({ rid, result: outcome.reply, arrays: outcome.arrays }, transfer);
    } catch (error) {
      if (command === 'init') python = null;
      self.postMessage({ rid, error: error?.message || String(error) });
    }
  });
};
