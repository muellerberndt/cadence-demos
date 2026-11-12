// The brain's map runs here, off the page's thread, in Python through Pyodide. The wheel, the
// map file and the Python host are checked against the pack manifest's SHA-256 before anything
// runs. Messages: {rid, command, payload} in; {rid, result, arrays} or {rid, error} out; {status}
// while loading. `arrays` holds the typed arrays a reply names in `buffers`.
//
// What the camera sees. The map is told at every moment what the camera sees: a thing whose held
// place the camera sees, with no report from there, is not where it was. The page sends the scene
// as it stands (the camera's position, heading and field, the pillar, the arm's joints, whether
// the camera is on), and `visible` of world.js, the scene's own rule for what the camera reports,
// is asked about each cell's middle and about any place the map asks of (`look`).
import { visible, forward } from './world.js';

let python = null;
let manifest = null;
let centers = null; // the map's cells' middles: [[x, y], ...]
let view = null;    // the scene as it stands at the moment being answered

// Would the camera see a thing at each of these places, as the scene stands? `flat` holds x, y,
// x, y, ...; one flag a place comes back. The map asks it about the places where it holds things.
function look(flat) {
  const out = new Array(flat.length >> 1).fill(false);
  if (!view || !view.on) return out;
  const chain = forward(view.geometry, view.joints);
  for (let k = 0; k < out.length; k++) out[k] = visible(view.geometry, [flat[2 * k], flat[2 * k + 1]], view.joints, false, chain);
  return out;
}

/** One flag a cell of the map, as a string of 0s and 1s: whether the camera sees the cell's
 *  middle, as the scene stands. */
function litCells(view) {
  if (!view || !view.on) return '0'.repeat(centers.length);
  const chain = forward(view.geometry, view.joints);
  let out = '';
  for (let k = 0; k < centers.length; k++) out += visible(view.geometry, centers[k], view.joints, false, chain) ? '1' : '0';
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
  if (manifest.schema !== 'cadence-out-of-sight-pack/2') throw new Error('This is not an Out of sight brain pack.');
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
  status('Loading the map');
  python.FS.mkdirTree('/home/pyodide/map');
  const path = `/home/pyodide/map/${manifest.map.file}`;
  python.FS.writeFile(path, await checked(new URL(`map/${manifest.map.file}`, base), manifest.map.sha256));
  const config = { map: { path, kinds: manifest.map.kinds, label: manifest.map.label, note: manifest.map.note } };
  status('Waking the map');
  python.globals.set('_space_config', JSON.stringify(config));
  python.runPython(`
import sys, json, warnings
warnings.simplefilter('ignore')
if '/home/pyodide' not in sys.path:
    sys.path.insert(0, '/home/pyodide')
from spacebrain.map_host import MapHost
_space_host = MapHost(json.loads(_space_config))
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
  { const give = python.globals.get('_space_looks'); try { give(look); } finally { give.destroy(); } }
  const out = call({ command: 'describe' });
  const flat = out.arrays.centers;
  centers = Array.from({ length: flat.length >> 1 }, (_, k) => [flat[2 * k], flat[2 * k + 1]]);
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

// One moment: the senses' reports, and the cells the camera sees as the scene stands.
function step(payload) {
  const { view: scene, ...moment } = payload || {};
  view = scene || null;
  return call({ command: 'step', ...moment, lit: scene ? litCells(scene) : null });
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
