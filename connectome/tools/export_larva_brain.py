"""Export the compiled Platynereis whole-body connectome for the browser engine, with the
sided populations the page's dictionary reads, at the gain the protocol selected."""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cadence-examples"))
from engine.export import write_payload  # noqa: E402
from connectome_compiler import compile, brain  # noqa: E402
from connectome_compiler.sources import platynereis as pl  # noqa: E402
from connectome_compiler.verify.burst import GRADED_UNIT  # noqa: E402
from connectome_compiler.verify.platynereis import _members, _sided  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipt", type=Path, default=Path("../connectome-research/receipts/platynereis_v1.json"))
    p.add_argument("--out", type=Path, default=Path("web/data/larva_brain.json"))
    p.add_argument("--gain-factor", type=float, default=0.8, help="the demo's gain as a fraction of the protocol's selected gain (declared: the selected gain sits within three percent of the critical gain, where a startle releases in thirteen seconds; at 0.8 it releases in two, as the animal's does)")
    a = p.parse_args(argv)
    rec = json.loads(a.receipt.read_text()); selected = rec["wirings"]["measured"]["selected_gain"]; gain = selected * a.gain_factor
    t = pl.load(); names = json.loads((Path(pl.DEFAULT_ROOT) / "names.json").read_text())
    pops = {}
    for key, prefix in (("PRC", "PRC"), ("eyespot", "eyespot-PRC"), ("prototroch", "prototroch"), ("MUSlong", "MUSlong")):
        L, R = _sided(t, names, prefix); pops[f"{key}:left"] = tuple(int(i) for i in L); pops[f"{key}:right"] = tuple(int(i) for i in R)
    pops["collar"] = tuple(int(i) for i in _members(t, ("hCR", "ventralpygCR")))
    pops["parapodial"] = tuple(int(i) for i in _members(t, ("MUSac", "MUSchae")))
    pops["muscles"] = tuple(int(i) for i in _members(t, ("MUS",)))
    pops["sensory"] = tuple(int(i) for i in np.flatnonzero(t.neurons.role == "sensory"))
    pops["effectors"] = tuple(int(i) for i in np.flatnonzero(t.neurons.role == "effector"))
    pops["neurons"] = tuple(int(i) for i in np.flatnonzero(np.isin(t.neurons.role, ["sensory", "inter", "motor"])))
    c = compile(t, populations=pops)
    b = brain(c, gain, backend="cpu", **GRADED_UNIT)
    extra = {"source": "Verasztó et al. 2025 eLife 13:RP97964, CATMAID project 11", "gain": gain, "selected_gain": selected, "demo_gain_factor": a.gain_factor, "unit": GRADED_UNIT, "kind": t.neurons.kind.tolist(), "role": t.neurons.role.tolist(), "id": t.neurons.id.tolist(), "name": [names.get(str(int(i)), "") for i in t.neurons.id], "tables_digest": t.digest(), "connectome_digest": c.digest(), "protocol_digest": rec["protocol_digest"]}
    out = write_payload(b, a.out, extra=extra)
    Path("receipts").mkdir(exist_ok=True)
    Path("receipts/larva_brain_export.json").write_text(json.dumps({"gain": gain, "selected_gain": selected, "demo_gain_factor": a.gain_factor, "why": "at the selected gain a startle releases in 12.9 s and at 0.8 of it in 2.2 s (receipts/larva_gain_scan.json)", "neurons": c.n, "classes": int(c.synapses), "payload": str(out), "bytes": out.stat().st_size, "populations": {k: len(v) for k, v in pops.items()}, "tables_digest": t.digest(), "connectome_digest": c.digest(), "protocol_digest": rec["protocol_digest"]}, indent=1))
    print("exported", out, out.stat().st_size // 1024, "KB; gain", round(gain, 4), "=", a.gain_factor, "x selected", selected, "| populations", {k: len(v) for k, v in pops.items()})


if __name__ == "__main__":
    main()
