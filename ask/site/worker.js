// The parrot's brain runs here, off the page's thread, in Python through Pyodide. The wheel, the
// brain file and the Python host are checked against the pack manifest's SHA-256 before anything
// runs. Messages: {rid, command, payload} in; {rid, result, arrays} or {rid, error} out; {status}
// while loading. `arrays` holds the typed arrays a reply names in `buffers`.
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
  // The page names the pack's address (absolute): a bundler may move this script elsewhere.
  const base = new URL(payload?.pack || 'pack/', self.location.href);
  status('Opening the brain pack');
  const response = await fetch(new URL('manifest.json', base));
  if (!response.ok) throw new Error('The brain pack is missing.');
  manifest = await response.json();
  if (manifest.schema !== 'cadence-ask-pack/1') throw new Error('This is not an Ask the Robot brain pack.');
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  status('Starting Python in your browser');
  const { loadPyodide } = await import(cdn + 'pyodide.mjs');
  python = await loadPyodide({ indexURL: cdn });
  status('Loading NumPy');
  await python.loadPackage('numpy');
  status(`Loading Cadence ${manifest.cadence}`);
  python.unpackArchive(await checked(new URL(manifest.wheel, base), manifest.wheel_sha256), 'wheel');
  python.FS.mkdirTree('/home/pyodide/askbrain');
  for (const name of manifest.sources) {
    const bytes = await checked(new URL(`py/askbrain/${name}`, base), manifest.sources_sha256[name]);
    python.FS.writeFile(`/home/pyodide/askbrain/${name}`, bytes);
  }
  status('Loading the brain');
  python.FS.mkdirTree('/home/pyodide/brain');
  const path = `/home/pyodide/brain/${manifest.brain.file}`;
  python.FS.writeFile(path, await checked(new URL(`brain/${manifest.brain.file}`, base), manifest.brain.sha256));
  status('Waking the brain');
  python.globals.set('_ask_config', JSON.stringify({ brain: path }));
  python.runPython(`
import sys, json, warnings
warnings.simplefilter('ignore')
if '/home/pyodide' not in sys.path:
    sys.path.insert(0, '/home/pyodide')
from askbrain.host import Host
_ask_host = Host(json.loads(_ask_config))
def _ask_handle(text):
    return json.dumps(_ask_host.handle(json.loads(text)), allow_nan=False)
def _ask_buffer(name):
    return _ask_host.buffers[name]
`);
  const out = call({ command: 'describe' });
  out.reply.startup_ms = Math.round(performance.now() - began);
  out.reply.manifest = manifest;
  return out;
}

// One request to the Python host: its JSON reply and the typed arrays it filled.
function call(message) {
  if (!python) throw new Error('The brain is loading.');
  const handle = python.globals.get('_ask_handle');
  const fetchBuffer = python.globals.get('_ask_buffer');
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

self.onmessage = ({ data }) => {
  chain = chain.then(async () => {
    const { rid, command, payload } = data;
    try {
      const outcome = command === 'init' ? await initialize(payload) : call({ command, ...(payload || {}) });
      const transfer = Object.values(outcome.arrays).map((a) => a.buffer);
      self.postMessage({ rid, result: outcome.reply, arrays: outcome.arrays }, transfer);
    } catch (error) {
      if (command === 'init') python = null;
      self.postMessage({ rid, error: error?.message || String(error) });
    }
  });
};
