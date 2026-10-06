// The brain, in a worker: Pyodide runs the released Cadence wheel and this repository's eye
// host. The page sends the pixels it drew and the player's eye commands; the worker answers
// with every eye's answer and the selected eye's activity. One request at a time.
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
  status("reading the brain pack");
  manifest = await (await fetch(new URL("manifest.json", base))).json();
  if (manifest.schema !== "cadence-eyes-pack/1") throw new Error("not a cadence-eyes-pack/1");
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  status(`loading Python (Pyodide ${manifest.pyodide})`);
  const { loadPyodide } = await import(cdn + "pyodide.mjs");
  pyodide = await loadPyodide({ indexURL: cdn });
  status("loading numpy");
  await pyodide.loadPackage("numpy");
  status(`loading Cadence ${manifest.cadence}`);
  pyodide.unpackArchive(await fetchChecked(new URL(manifest.wheel, base), manifest.wheel_sha256), "wheel");
  status("loading the eyes and the brain");
  pyodide.FS.mkdirTree("/home/pyodide/tracker");
  for (const name of manifest.sources) {
    const text = new TextDecoder().decode(
      await fetchChecked(new URL(`py/tracker/${name}`, base), manifest.sources_sha256[name]));
    pyodide.FS.writeFile(`/home/pyodide/tracker/${name}`, text);
  }
  pyodide.FS.writeFile("/home/pyodide/brain.npz", await fetchChecked(new URL(manifest.brain, base), manifest.brain_sha256));
  pyodide.runPython(`
import sys, warnings
warnings.simplefilter("ignore")
if "/home/pyodide" not in sys.path:
    sys.path.insert(0, "/home/pyodide")
from tracker.eye_host import Host
import json
_host = Host("/home/pyodide/brain.npz", ${manifest.window}, ${manifest.bins}, ${manifest.width}, ${manifest.height},
             eye="${manifest.eye || "window"}", fovea=json.loads('${JSON.stringify(manifest.fovea || null)}'))
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
    if (!host) throw new Error("the brain is not loaded yet");
    if (op === "see") {
      const t0 = performance.now();
      const result = JSON.parse(host.see(new Float32Array(event.data.pixels)));
      result.worker_ms = Math.round((performance.now() - t0) * 100) / 100;
      self.postMessage({ rid, result });
      return;
    }
    self.postMessage({ rid, result: JSON.parse(host.handle_json(JSON.stringify(event.data))) });
  } catch (error) {
    self.postMessage({ rid, error: String(error && error.message ? error.message : error) });
  }
};
