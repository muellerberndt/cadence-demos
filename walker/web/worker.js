// The walkers, in a worker: Pyodide runs the released Cadence wheel and this repository's
// host, one brain per lane. The page asks for moments; the worker answers with what the world
// saw and what each brain reports of itself. One request at a time.
// Messages: {rid, op, lane, ...} in; {rid, result} or {rid, error} out; {status} while loading.

let pyodide = null;
let manifest = null;
let hosts = null;

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

async function start(pack, seed) {
  const base = new URL(pack, self.location.href);
  status("reading the pack");
  manifest = await (await fetch(new URL("manifest.json", base))).json();
  if (manifest.schema !== "cadence-walker-pack/1") throw new Error("not a cadence-walker-pack/1");
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  status(`loading Python (Pyodide ${manifest.pyodide})`);
  const { loadPyodide } = await import(cdn + "pyodide.mjs");
  pyodide = await loadPyodide({ indexURL: cdn });
  status("loading numpy");
  await pyodide.loadPackage("numpy");
  status(`loading Cadence ${manifest.cadence}`);
  pyodide.unpackArchive(await fetchChecked(new URL(manifest.wheel, base), manifest.wheel_sha256), "wheel");
  status("loading the track and the walkers");
  pyodide.FS.mkdirTree("/home/pyodide/walker");
  for (const name of manifest.sources) {
    const text = new TextDecoder().decode(
      await fetchChecked(new URL(`py/walker/${name}`, base), manifest.sources_sha256[name]));
    pyodide.FS.writeFile(`/home/pyodide/walker/${name}`, text);
  }
  pyodide.runPython(`
import sys, warnings
warnings.simplefilter("ignore")
if "/home/pyodide" not in sys.path:
    sys.path.insert(0, "/home/pyodide")
from walker.host import Host

_hosts = {}

def _born(seed):
    global _hosts
    _hosts = {"copy": Host(int(seed), copy=True), "bare": Host(int(seed), copy=False)}
    return _hosts

def _handle(lane, text):
    return _hosts[lane].handle_json(text)
`);
  hosts = pyodide.globals.get("_born")(seed);
  return describeAll();
}

function describeAll() {
  const handle = pyodide.globals.get("_handle");
  const out = { manifest };
  for (const lane of ["copy", "bare"]) {
    out[lane] = JSON.parse(handle(lane, JSON.stringify({ op: "describe" })));
  }
  return out;
}

self.onmessage = async (event) => {
  const { rid, op } = event.data;
  try {
    if (op === "start") {
      self.postMessage({ rid, result: await start(event.data.pack, event.data.seed) });
      return;
    }
    if (!hosts) throw new Error("the walkers are not loaded yet");
    if (op === "born") {
      hosts = pyodide.globals.get("_born")(event.data.seed);
      self.postMessage({ rid, result: describeAll() });
      return;
    }
    const handle = pyodide.globals.get("_handle");
    const t0 = performance.now();
    const lanes = event.data.lanes || ["copy", "bare"];
    const result = {};
    for (const lane of lanes) {
      result[lane] = JSON.parse(handle(lane, JSON.stringify(event.data)));
    }
    result.worker_ms = Math.round((performance.now() - t0) * 100) / 100;
    self.postMessage({ rid, result });
  } catch (error) {
    self.postMessage({ rid, error: String(error && error.message ? error.message : error) });
  }
};
