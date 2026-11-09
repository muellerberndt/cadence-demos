// One Pyodide worker. The page starts one in the role "world" (the ecosystem: world, births,
// deaths, inheritance) and two to four in the role "brain" (the creatures' Cadence brains, one
// continuing Brain.live life each). The wheel, the Python sources and the founders' brains are
// checked against the SHA-256 in the pack's manifest before anything runs. The page passes the
// pack's absolute URL in the init message (<meta name="cadence-pack"> or pack/ beside the page).
let python = null;
let manifest = null;
let role = null;
let chain = Promise.resolve();
const status = (message) => self.postMessage({ status: message });

async function checked(url, expected) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load ${url.pathname} (${response.status}).`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (!expected) throw new Error(`No checksum for ${url.pathname} in the manifest.`);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const actual = [...new Uint8Array(digest)].map((v) => v.toString(16).padStart(2, '0')).join('');
  if (actual !== expected) throw new Error(`Integrity check failed for ${url.pathname}.`);
  return bytes;
}

async function initialize(payload) {
  const began = performance.now();
  role = payload.role;
  // The page names the pack's absolute address: a bundler may move this script elsewhere, so
  // the worker never derives the pack from its own location.
  if (!payload.pack) throw new Error('The page did not name the runtime pack.');
  const base = new URL(payload.pack);
  const response = await fetch(new URL('manifest.json', base), { cache: 'no-cache' });
  if (!response.ok) throw new Error('The runtime pack is missing. Run pack.py first.');
  manifest = await response.json();
  if (manifest.schema !== 'cadence-patch-world-pack/1') throw new Error('This is not a Patch World pack.');
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  status('Starting Python…');
  const { loadPyodide } = await import(cdn + 'pyodide.mjs');
  python = await loadPyodide({ indexURL: cdn });
  status('Loading NumPy…');
  await python.loadPackage('numpy');
  if (role === 'brain') {
    status(`Loading Cadence ${manifest.cadence}…`);
    python.unpackArchive(await checked(new URL(manifest.wheel, base), manifest.wheel_sha256), 'wheel');
  }
  python.FS.mkdirTree('/home/pyodide/patchworld');
  for (const name of manifest.sources) {
    const bytes = await checked(new URL(`py/patchworld/${name}`, base), manifest.sources_sha256[name]);
    python.FS.writeFile(`/home/pyodide/patchworld/${name}`, bytes);
  }
  python.FS.mkdirTree('/home/pyodide/founders');
  python.FS.writeFile('/home/pyodide/founders/founders.json',
    await checked(new URL('founders/founders.json', base), manifest.roster_sha256));
  if (role === 'brain') {
    status('Loading the founders’ brains…');
    for (const f of manifest.founders) {
      python.FS.writeFile(`/home/pyodide/founders/${f.file}`,
        await checked(new URL(`founders/${f.file}`, base), f.sha256));
    }
  }
  const seed = Number(payload.seed) | 0;
  python.runPython(`
import sys, json
if '/home/pyodide' not in sys.path:
    sys.path.insert(0, '/home/pyodide')
import patchworld.host as _h
${role === 'brain' ? '_h.fit_32_bit_numpy()' : ''}
_pw_host = _h.${role === 'brain' ? 'BrainHost' : 'WorldHost'}('/home/pyodide/founders', seed=${seed})
def _pw_handle(text):
    return _h.as_json(_pw_host.handle(json.loads(text)))
`);
  return { ready: true, role, startup_ms: Math.round(performance.now() - began),
    manifest: { cadence: manifest.cadence, pyodide: manifest.pyodide, packed: manifest.packed,
      wheel_sha256: manifest.wheel_sha256, founders: manifest.founders.length } };
}

function call(message) {
  if (!python) throw new Error('The worker is still loading.');
  const handle = python.globals.get('_pw_handle');
  const began = performance.now();
  try {
    const reply = JSON.parse(handle(JSON.stringify(message)));
    reply.worker_ms = Math.round((performance.now() - began) * 100) / 100;
    return reply;
  } finally { handle.destroy(); }
}

self.onmessage = ({ data }) => {
  chain = chain.then(async () => {
    const rid = data.rid;
    try {
      const reply = data.command === 'init' ? await initialize(data.payload)
        : call({ command: data.command, payload: data.payload });
      self.postMessage({ rid, result: reply });
    } catch (error) {
      if (data.command === 'init') python = null;
      self.postMessage({ rid, error: error?.message || String(error) });
    }
  });
};
