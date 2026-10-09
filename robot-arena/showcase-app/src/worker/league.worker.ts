// The league in a worker: Pyodide runs the released Cadence wheel, the arena's own Python and
// the browser host; the page asks for moments and gets replay-format frames back. One request
// at a time. Messages in: {rid, op, ...}; out: {rid, result} | {rid, error}; {status} while loading.

let pyodide: any = null;
let manifest: any = null;
let handle: any = null;

export {};
const report = (stage: string, progress?: number) => (self as any).postMessage({ status: stage, progress });

async function sha256(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes as BufferSource);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function fetchChecked(url: URL, expected?: string): Promise<Uint8Array> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`cannot load ${url}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (expected && (await sha256(bytes)) !== expected) throw new Error(`${url} does not match its manifest`);
  return bytes;
}

async function start(pack: string): Promise<any> {
  const base = new URL(pack, self.location.href);
  report("reading the pack", 0.02);
  manifest = await (await fetch(new URL("manifest.json", base))).json();
  if (manifest.schema !== "cadence-showcase-pack/1") throw new Error("not a cadence-showcase-pack/1");
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  report(`loading Python (Pyodide ${manifest.pyodide})`, 0.08);
  const { loadPyodide } = await import(/* @vite-ignore */ cdn + "pyodide.mjs");
  pyodide = await loadPyodide({ indexURL: cdn });
  report("loading numpy", 0.45);
  await pyodide.loadPackage("numpy");
  report(`loading Cadence ${manifest.cadence}`, 0.65);
  pyodide.unpackArchive(await fetchChecked(new URL(manifest.wheel, base), manifest.wheel_sha256), "wheel");
  report("loading the arena", 0.75);
  pyodide.FS.mkdirTree("/home/pyodide/arena");
  pyodide.FS.mkdirTree("/home/pyodide/brains");
  for (const name of manifest.sources) {
    const text = new TextDecoder().decode(await fetchChecked(new URL(`py/arena/${name}`, base), manifest.sources_sha256[name]));
    pyodide.FS.writeFile(`/home/pyodide/arena/${name}`, text);
  }
  pyodide.FS.writeFile("/home/pyodide/host.py", new TextDecoder().decode(await fetchChecked(new URL("py/host.py", base), manifest.host_sha256)));
  report("loading the robots' brains", 0.85);
  for (const robot of manifest.roster) {
    const bytes = await fetchChecked(new URL(`brains/${robot.name}.npz`, base), robot.brain_sha256);
    pyodide.FS.writeFile(`/home/pyodide/brains/${robot.name}.npz`, bytes);
  }
  report("waking the brains", 0.92);
  pyodide.runPython(`
import sys, json, warnings
warnings.simplefilter("ignore")
if "/home/pyodide" not in sys.path:
    sys.path.insert(0, "/home/pyodide")
from host import Host
_manifest = json.loads(${JSON.stringify(JSON.stringify(manifest))})
_host = Host(_manifest["roster"], "/home/pyodide/brains", _manifest.get("stage"))

def _handle(text):
    return _host.handle_json(text)
`);
  handle = pyodide.globals.get("_handle");
  report("ready", 1);
  return { manifest, describe: JSON.parse(handle(JSON.stringify({ op: "describe" }))) };
}

self.onmessage = async (event: MessageEvent) => {
  const { rid, op } = event.data;
  try {
    if (op === "start") {
      (self as any).postMessage({ rid, result: await start(event.data.pack) });
      return;
    }
    if (!handle) throw new Error("the league is not loaded yet");
    const t0 = performance.now();
    const result = JSON.parse(handle(JSON.stringify(event.data)));
    result.worker_ms = Math.round((performance.now() - t0) * 10) / 10;
    (self as any).postMessage({ rid, result });
  } catch (error: any) {
    (self as any).postMessage({ rid, error: String(error && error.message ? error.message : error) });
  }
};
