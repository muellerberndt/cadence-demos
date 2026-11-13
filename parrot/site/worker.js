// The parrot's brain runs here, off the page's thread, in Python through Pyodide (INTERFACES P6).
// The pack's manifest names the host's sources, any brain files and any wheel; each is checked
// against its SHA-256 before anything runs. Messages: {rid, command, payload} in; {rid, result,
// arrays} or {rid, error} out; {status} while loading. A step carries the two eyes' images and the
// proprioception as typed arrays; `arrays` holds the typed arrays a reply names in `buffers`.
let python = null;
let manifest = null;
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
  const base = new URL(payload?.pack || 'pack/', self.location.href);
  status('Opening the brain pack');
  const response = await fetch(new URL('manifest.json', base));
  if (!response.ok) throw new Error('The brain pack is missing.');
  manifest = await response.json();
  if (manifest.schema !== 'cadence-parrot-pack/1') throw new Error('This is not a parrot brain pack.');
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  status('Starting Python in your browser');
  const { loadPyodide } = await import(cdn + 'pyodide.mjs');
  python = await loadPyodide({ indexURL: cdn });
  status('Loading NumPy');
  await python.loadPackage(manifest.packages || ['numpy']);
  if (manifest.wheel) {
    status(`Loading Cadence ${manifest.cadence || ''}`.trim());
    python.unpackArchive(await checked(new URL(manifest.wheel, base), manifest.wheel_sha256), 'wheel');
  }
  const pkg = manifest.package || 'parrotbrain';
  python.FS.mkdirTree(`/home/pyodide/${pkg}`);
  for (const name of manifest.sources) {
    python.FS.writeFile(`/home/pyodide/${pkg}/${name}`, await checked(new URL(`py/${pkg}/${name}`, base), manifest.sources_sha256[name]));
  }
  python.FS.mkdirTree('/home/pyodide/brain');
  for (const [name, sha] of Object.entries(manifest.files || {})) {
    status(`Loading ${name}`);
    python.FS.writeFile(`/home/pyodide/brain/${name}`, await checked(new URL(name, base), sha));
  }
  status('Waking the brain');
  python.globals.set('_parrot_config', JSON.stringify({ ...(manifest.config || {}), ...(payload?.config || {}), files: '/home/pyodide/brain' }));
  python.runPython(`
import sys, json, warnings
import numpy as np
warnings.simplefilter('ignore')
if '/home/pyodide' not in sys.path:
    sys.path.insert(0, '/home/pyodide')
from ${pkg}.host import Host
_parrot_host = Host(json.loads(_parrot_config))
def _parrot_handle(text):
    return json.dumps(_parrot_host.handle(json.loads(text)), allow_nan=False)
def _parrot_step(text, left, right, proprio):
    meta = json.loads(text)
    out = _parrot_host.step(meta, np.frombuffer(left.to_bytes(), dtype=np.uint8), np.frombuffer(right.to_bytes(), dtype=np.uint8),
                            np.frombuffer(proprio.to_bytes(), dtype=np.float32))
    return json.dumps(out, allow_nan=False)
def _parrot_buffer(name):
    return _parrot_host.buffers[name]
`);
  const out = call({ command: 'describe' });
  out.reply.startup_ms = Math.round(performance.now() - began);
  out.reply.manifest = { schema: manifest.schema, packed: manifest.packed, cadence: manifest.cadence || null, brain: manifest.brain || null };
  return out;
}

function arraysOf(reply) {
  const arrays = {};
  if (!reply.buffers?.length) return arrays;
  const fetchBuffer = python.globals.get('_parrot_buffer');
  try {
    for (const name of reply.buffers) {
      const proxy = fetchBuffer(name);
      const view = proxy.getBuffer();
      try { arrays[name] = view.data.slice(); } finally { view.release(); proxy.destroy(); }
    }
  } finally { fetchBuffer.destroy(); }
  return arrays;
}

function call(message) {
  if (!python) throw new Error('The brain is loading.');
  const handle = python.globals.get('_parrot_handle');
  const began = performance.now();
  try {
    const reply = JSON.parse(handle(JSON.stringify(message)));
    reply.worker_ms = Math.round((performance.now() - began) * 100) / 100;
    return { reply, arrays: arraysOf(reply) };
  } finally { handle.destroy(); }
}

function step(payload) {
  if (!python) throw new Error('The brain is loading.');
  const fn = python.globals.get('_parrot_step');
  const began = performance.now();
  try {
    const reply = JSON.parse(fn(JSON.stringify(payload.meta || {}), payload.left, payload.right, payload.proprio));
    reply.worker_ms = Math.round((performance.now() - began) * 100) / 100;
    return { reply, arrays: arraysOf(reply) };
  } finally { fn.destroy(); }
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
