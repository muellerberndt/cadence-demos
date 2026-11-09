// The brain, in a module worker: Pyodide runs the released cadence-net wheel and the arena's
// host (pack/py/tron/fieldhost.py: frozen, greedy, the moves round 3 measured). The page owns
// the clock; the worker answers one request at a time.
//
// In:  {rid, op, ...}.  Out: {rid, result} | {rid, error}; {status} while loading.
//   start    {pack, games}  -> {manifest, describe}   games: arenas continue from this count
//   begin    {seed?}        -> the new game's state and the brain's first settle
//   tick     {move}         -> the state after both cycles moved, the next settle

let pyodide = null;
let manifest = null;
const status = (stage) => self.postMessage({ status: stage });

async function sha256(bytes) {
  if (!self.crypto || !self.crypto.subtle) return null; // not a secure context (a LAN address over http)
  const digest = await self.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function fetchChecked(url, expected) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`cannot load ${url.pathname}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  const got = await sha256(bytes);
  if (got !== null && got !== expected) throw new Error(`${url.pathname} does not match its manifest`);
  return bytes;
}

async function start(pack, games) {
  const base = new URL(pack, self.location.href);
  status("reading the pack");
  manifest = await (await fetch(new URL("manifest.json", base), { cache: "no-cache" })).json();
  if (manifest.schema !== "cadence-tron-play/1") throw new Error("not a cadence-tron-play/1 pack");
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  status("loading Python");
  const { loadPyodide } = await import(cdn + "pyodide.mjs");
  pyodide = await loadPyodide({ indexURL: cdn });
  status("loading numpy");
  await pyodide.loadPackage("numpy");
  status("loading Cadence");
  pyodide.unpackArchive(await fetchChecked(new URL(manifest.wheel, base), manifest.wheel_sha256), "wheel");
  pyodide.FS.mkdirTree("/home/pyodide/tron");
  for (const name of manifest.sources) {
    const text = new TextDecoder().decode(await fetchChecked(new URL(`py/tron/${name}`, base), manifest.sources_sha256[name]));
    pyodide.FS.writeFile(`/home/pyodide/tron/${name}`, text);
  }
  status(`waking ${manifest.brain.title}`);
  const brain = await fetchChecked(new URL(manifest.brain.file, base), manifest.brain.sha256);
  const meta = JSON.parse(new TextDecoder().decode(await fetchChecked(new URL(manifest.brain.meta, base), manifest.brain.meta_sha256)));
  meta.games = games || 0;
  const [module, cls] = manifest.host.split(":");
  pyodide.globals.set("_brain_bytes", brain);
  pyodide.globals.set("_meta_text", JSON.stringify(meta));
  pyodide.runPython(`
import sys, warnings, json, importlib
warnings.simplefilter("ignore")
if "/home/pyodide" not in sys.path:
    sys.path.insert(0, "/home/pyodide")
_host = getattr(importlib.import_module("${module}"), "${cls}")(bytes(_brain_bytes.to_py()), json.loads(_meta_text))
del _brain_bytes

def _handle(text):
    return _host.handle_json(text)
`);
  const describe = JSON.parse(pyodide.globals.get("_handle")('{"op": "describe"}'));
  return { manifest, describe };
}

self.onmessage = async (event) => {
  const { rid, op } = event.data;
  try {
    let result;
    if (op === "start") result = await start(event.data.pack, event.data.games);
    else if (!pyodide) throw new Error("the brain is not loaded yet");
    else {
      const t0 = performance.now();
      const message = { op };
      if (op === "tick") message.move = event.data.move;
      if (op === "begin" && event.data.seed !== undefined) message.seed = event.data.seed;
      result = JSON.parse(pyodide.globals.get("_handle")(JSON.stringify(message)));
      result.worker_ms = Math.round((performance.now() - t0) * 10) / 10;
    }
    self.postMessage({ rid, result });
  } catch (error) {
    self.postMessage({ rid, error: String(error && error.message ? error.message : error) });
  }
};
