// The creature, in a worker: Pyodide runs the released Cadence wheel and this repository's
// host. The page asks for moments and trips; the worker answers with what the world saw and
// what the brain reports of itself. One request at a time.
// Messages: {rid, op, ...} in; {rid, result} or {rid, error} out; {status} while loading.

let pyodide = null;
let host = null;
let manifest = null;

const status = (stage) => self.postMessage({ status: stage });

async function sha256(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function fetchChecked(url, expected) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`cannot load ${url}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (expected && (await sha256(bytes)) !== expected) throw new Error(`${url} does not match its manifest`);
  return bytes;
}

async function start(pack) {
  const base = new URL(pack, self.location.href);
  status("reading the creature pack");
  manifest = await (await fetch(new URL("manifest.json", base))).json();
  if (manifest.schema !== "cadence-keydoor-pack/1") throw new Error("not a cadence-keydoor-pack/1");
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  status(`loading Python (Pyodide ${manifest.pyodide})`);
  const { loadPyodide } = await import(cdn + "pyodide.mjs");
  pyodide = await loadPyodide({ indexURL: cdn });
  status("loading numpy");
  await pyodide.loadPackage("numpy");
  status(`loading Cadence ${manifest.cadence}`);
  pyodide.unpackArchive(await fetchChecked(new URL(manifest.wheel, base), manifest.wheel_sha256), "wheel");
  status("loading the corridor and the creature");
  pyodide.FS.mkdirTree("/home/pyodide/keydoor");
  for (const name of manifest.sources) {
    const text = new TextDecoder().decode(
      await fetchChecked(new URL(`py/keydoor/${name}`, base), manifest.sources_sha256[name]));
    pyodide.FS.writeFile(`/home/pyodide/keydoor/${name}`, text);
  }
  pyodide.FS.writeFile("/home/pyodide/raised.npz", await fetchChecked(new URL(manifest.brain, base), manifest.brain_sha256));
  pyodide.runPython(`
import sys, warnings
warnings.simplefilter("ignore")
if "/home/pyodide" not in sys.path:
    sys.path.insert(0, "/home/pyodide")
from keydoor.host import Host
_raised = ("/home/pyodide/raised.npz", ${manifest.delay}, ${manifest.seed}, ${manifest.raised_trips})
_host = Host(_raised[0], _raised[1], _raised[2], raised_trips=_raised[3])

def _reborn(delay, seed):
    global _host
    _host = Host(None, int(delay), int(seed))
    return _host

def _raised_again():
    global _host
    _host = Host(_raised[0], _raised[1], _raised[2], raised_trips=_raised[3])
    return _host
`);
  host = pyodide.globals.get("_host");
  return { manifest, describe: JSON.parse(host.handle_json(JSON.stringify({ op: "describe" }))) };
}

self.onmessage = async (event) => {
  const { rid, op } = event.data;
  try {
    if (op === "start") {
      self.postMessage({ rid, result: await start(event.data.pack) });
      return;
    }
    if (!host) throw new Error("the creature is not loaded yet");
    if (op === "newborn") {
      host = pyodide.globals.get("_reborn")(event.data.delay, event.data.seed);
      self.postMessage({ rid, result: JSON.parse(host.handle_json(JSON.stringify({ op: "describe" }))) });
      return;
    }
    if (op === "raised") {
      host = pyodide.globals.get("_raised_again")();
      self.postMessage({ rid, result: JSON.parse(host.handle_json(JSON.stringify({ op: "describe" }))) });
      return;
    }
    const t0 = performance.now();
    const result = JSON.parse(host.handle_json(JSON.stringify(event.data)));
    result.worker_ms = Math.round((performance.now() - t0) * 100) / 100;
    self.postMessage({ rid, result });
  } catch (error) {
    self.postMessage({ rid, error: String(error && error.message ? error.message : error) });
  }
};
