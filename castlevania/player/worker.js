// Live mode: the brain itself, in Python through Pyodide, with the released cadence-net wheel and
// the demo's own player (simon/player.py). Every file is checked against the pack manifest's
// SHA-256 before it runs. The page feeds the recorded eye inputs in order from the game's start;
// each one is settled for real and the chosen action and the brain's state come back.
let py = null;
const status = (s) => self.postMessage({ status: s });

async function checked(url, expected) {
  const r = await fetch(url); if (!r.ok) throw new Error(`cannot load ${url.pathname}`);
  const bytes = new Uint8Array(await r.arrayBuffer());
  if (expected && self.crypto && self.crypto.subtle) {
    const got = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map((b) => b.toString(16).padStart(2, "0")).join("");
    if (got !== expected) throw new Error(`${url.pathname} does not match its manifest`);
  }
  return bytes;
}

async function start(pack) {
  const base = new URL(pack, self.location.href);
  const manifest = await (await fetch(new URL("manifest.json", base), { cache: "no-cache" })).json();
  status("loading Python (Pyodide); the first visit takes a moment…");
  const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;
  const { loadPyodide } = await import(cdn + "pyodide.mjs");
  py = await loadPyodide({ indexURL: cdn });
  status("loading NumPy…");
  await py.loadPackage("numpy");
  status("loading cadence-net…");
  py.unpackArchive(await checked(new URL(manifest.wheel, base), manifest.wheel_sha256), "wheel");
  py.FS.mkdirTree("/home/pyodide/simon");
  for (const name of manifest.sources) {
    const bytes = await checked(new URL(`py/simon/${name}`, base), manifest.sources_sha256[name]);
    py.FS.writeFile(`/home/pyodide/simon/${name}`, bytes);
  }
  status("loading the brain (37 MB)…");
  py.FS.writeFile("/home/pyodide/brain.npz", await checked(new URL(manifest.brain.file, base), manifest.brain.sha256));
  status("waking the brain…");
  py.runPython(`
import sys, json, base64, warnings
warnings.simplefilter("ignore")
sys.path.insert(0, "/home/pyodide")
import numpy as np
from pathlib import Path
# Pyodide's numpy is 32-bit (int32 indices): cadence-net sets up a learner with several slots by
# np.repeat(..., slot_sizes) on int64 sizes, which a 32-bit numpy refuses to cast. The library's
# learning module gets a numpy whose repeat casts the counts to the index type; every other call
# is numpy's own (the same shim as the Eyes demo).
if np.dtype(np.intp).itemsize < 8:
    import types
    import cadence.learning as _learning
    _shim = types.ModuleType("numpy")
    _shim.__dict__.update(np.__dict__)
    _shim.repeat = lambda a, repeats, axis=None: np.repeat(a, np.asarray(repeats).astype(np.intp), axis=axis)
    _learning.np = _shim
from simon.player import Player, load_brain, populations
_path = Path("/home/pyodide/brain.npz")
_player = Player(load_brain(_path), populations(_path))
_player.new_game()

def _feed(x64):
    x = np.frombuffer(base64.b64decode(x64), "<f8")
    action = _player.decide_input(x)
    return json.dumps({"action": int(action), "ms": _player.last["ms"], "snap": _player.snapshot()})

def _reset():
    _player.new_game()
`);
}

self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.op === "start") { await start(m.pack); self.postMessage({ op: "ready" }); }
    else if (m.op === "reset") { py.globals.get("_reset")(); self.postMessage({ op: "reset" }); }
    else if (m.op === "feed") {
      const out = JSON.parse(py.globals.get("_feed")(m.x));
      self.postMessage({ op: "fed", k: m.k, action: out.action, ms: out.ms, snap: out.snap });
    }
  } catch (error) {
    self.postMessage({ error: String(error && error.message ? error.message : error) });
  }
};
