// The real Cadence brain runs here, off the page's thread, in Python through Pyodide. The wheel,
// the host and the brain are checked against the pack manifest's SHA-256 before anything runs.
// Messages: {rid, command, payload} in; {rid, result} or {rid, error} out; {status} while loading.
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

async function initialize() {
  const began = performance.now();
  const base = new URL('pack/', self.location.href);
  status('Opening the brain pack');
  const response = await fetch(new URL('manifest.json', base));
  if (!response.ok) throw new Error('The brain pack is missing.');
  manifest = await response.json();
  if (manifest.schema !== 'cadence-arm-site-pack/1') throw new Error('This is not an arm brain pack.');
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  status('Starting Python in your browser');
  const { loadPyodide } = await import(cdn + 'pyodide.mjs');
  python = await loadPyodide({ indexURL: cdn });
  status('Loading NumPy');
  await python.loadPackage('numpy');
  status(`Loading Cadence ${manifest.cadence}`);
  python.unpackArchive(await checked(new URL(manifest.wheel, base), manifest.wheel_sha256), 'wheel');
  python.FS.mkdirTree('/home/pyodide/armbrain');
  for (const name of manifest.sources) {
    const bytes = await checked(new URL(`py/armbrain/${name}`, base), manifest.sources_sha256[name]);
    python.FS.writeFile(`/home/pyodide/armbrain/${name}`, bytes);
  }
  status('Loading the brain');
  python.FS.writeFile('/home/pyodide/brain.npz', await checked(new URL(manifest.brain, base), manifest.brain_sha256));
  python.FS.writeFile('/home/pyodide/run.json', await checked(new URL(manifest.run, base), manifest.run_sha256));
  python.runPython(`
import sys, json
if '/home/pyodide' not in sys.path:
    sys.path.insert(0, '/home/pyodide')
from armbrain.host import Host
_arm_host = Host('/home/pyodide/brain.npz', '/home/pyodide/run.json')
def _arm_handle(text):
    return json.dumps(_arm_host.handle(json.loads(text)), allow_nan=False)
`);
  const out = call({ command: 'describe' });
  out.startup_ms = Math.round(performance.now() - began);
  out.manifest = manifest;
  return out;
}

function call(message) {
  if (!python) throw new Error('The brain is still loading.');
  const handle = python.globals.get('_arm_handle');
  try {
    const began = performance.now();
    const reply = JSON.parse(handle(JSON.stringify(message)));
    reply.worker_ms = Math.round((performance.now() - began) * 10) / 10;
    return reply;
  } finally { handle.destroy(); }
}

self.onmessage = ({ data }) => {
  chain = chain.then(async () => {
    const { rid, command, payload } = data;
    try {
      const result = command === 'init' ? await initialize() : call({ command, ...(payload || {}) });
      self.postMessage({ rid, result });
    } catch (error) {
      if (command === 'init') python = null;
      self.postMessage({ rid, error: error?.message || String(error) });
    }
  });
};
