// The real Cadence brain runs here, off the page's thread, in Python through Pyodide.
// The wheel, the Python host and the brain are checked against the pack manifest's SHA-256
// before anything runs. A settle is computed in chunks of sweeps; each chunk is posted as soon
// as it exists, so the page can draw the brain settling while the next chunk is computed.
let python = null;
let manifest = null;
let chain = Promise.resolve();
const cancelled = new Set();
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

async function initialize(pack) {
  if (python) return call({ command: 'init' });
  const began = performance.now();
  // The page names the pack's address (absolute): a bundler may move this script elsewhere.
  const base = new URL(pack || 'pack/', self.location.href);
  status('Opening the runtime pack…');
  const response = await fetch(new URL('manifest.json', base));
  if (!response.ok) throw new Error('The Cadence runtime pack is missing. Run pack.py first.');
  manifest = await response.json();
  if (manifest.schema !== 'cadence-connect-four-pack/1') throw new Error('This is not a Connect Four runtime pack.');
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  status('Starting Python in your browser. The first visit takes a moment…');
  const { loadPyodide } = await import(cdn + 'pyodide.mjs');
  python = await loadPyodide({ indexURL: cdn });
  status('Loading NumPy…');
  await python.loadPackage('numpy');
  status(`Loading Cadence ${manifest.cadence}…`);
  python.unpackArchive(await checked(new URL(manifest.wheel, base), manifest.wheel_sha256), 'wheel');
  python.FS.mkdirTree('/home/pyodide/connect4');
  for (const name of manifest.sources) {
    const bytes = await checked(new URL(`py/connect4/${name}`, base), manifest.sources_sha256?.[name]);
    python.FS.writeFile(`/home/pyodide/connect4/${name}`, bytes);
  }
  status('Loading the brain…');
  python.FS.writeFile('/home/pyodide/brain.npz',
    await checked(new URL(manifest.brain || 'brain.npz', base), manifest.brain_sha256));
  python.runPython(`
import sys, json
if '/home/pyodide' not in sys.path:
    sys.path.insert(0, '/home/pyodide')
from connect4.host import Host
_c4_host = Host('/home/pyodide/brain.npz')
def _c4_handle(text):
    return json.dumps(_c4_host.handle(json.loads(text)), allow_nan=False)
def _c4_buffer(name):
    return _c4_host.buffers[name]
`);
  const out = call({ command: 'init' });
  out.reply.startup_ms = Math.round(performance.now() - began);
  out.reply.manifest = manifest;
  return out;
}

// One request to the Python host. Returns its JSON reply and the typed arrays it filled.
function call(message) {
  if (!python) throw new Error('The brain is still loading.');
  const handle = python.globals.get('_c4_handle');
  const fetchBuffer = python.globals.get('_c4_buffer');
  const began = performance.now();
  try {
    const reply = JSON.parse(handle(JSON.stringify(message)));
    reply.worker_ms = Math.round((performance.now() - began) * 100) / 100;
    const arrays = {};
    for (const name of Object.keys(reply.buffers || {})) {
      const proxy = fetchBuffer(name);
      const view = proxy.getBuffer();
      try { arrays[name] = view.data.slice(); } finally { view.release(); proxy.destroy(); }
    }
    reply.pack = { cadence: manifest.cadence, pyodide: manifest.pyodide,
      wheel_sha256: manifest.wheel_sha256, brain_sha256: manifest.brain_sha256 };
    return { reply, arrays };
  } finally { handle.destroy(); fetchBuffer.destroy(); }
}

function post(rid, kind, payload) {
  const arrays = payload.arrays || {};
  const transfer = Object.values(arrays).map((a) => a.buffer);
  self.postMessage({ rid, [kind]: payload.reply, arrays }, transfer);
}

const pause = () => new Promise((resolve) => setTimeout(resolve, 0));

async function think(rid, payload) {
  const began = performance.now();
  let step = call({ command: 'think', payload });
  post(rid, 'progress', step);
  while (!step.reply.done) {
    await pause(); // lets a cancel message in between chunks
    if (cancelled.has(rid)) { cancelled.delete(rid); return { reply: { cancelled: true } }; }
    step = call({ command: 'more', payload: { id: step.reply.id } });
    post(rid, 'progress', step);
  }
  step.reply.final.wall_ms = Math.round((performance.now() - began) * 100) / 100;
  return { reply: step.reply.final };
}

self.onmessage = ({ data }) => {
  if (data.command === 'cancel') { cancelled.add(data.target); return; }
  chain = chain.then(async () => {
    const rid = data.rid;
    try {
      if (cancelled.has(rid)) { cancelled.delete(rid); post(rid, 'result', { reply: { cancelled: true } }); return; }
      let outcome;
      if (data.command === 'init') {
        outcome = await initialize(data.payload?.pack);
      } else if (data.command === 'think') {
        outcome = await think(rid, data.payload);
      } else {
        outcome = call({ command: data.command, payload: data.payload });
      }
      post(rid, 'result', outcome);
    } catch (error) {
      if (data.command === 'init') python = null;
      self.postMessage({ rid, error: error?.message || String(error) });
    }
  });
};
