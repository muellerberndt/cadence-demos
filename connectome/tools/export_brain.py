"""Export the compiled brainstem for the browser engine.

The whole reconstruction (2,884 neurons) at the graded unit and the gain the oculomotor
protocol selected, with the axial module's gain attenuated by the smallest amount on a
declared grid that keeps the net from igniting under a saccadic burst (the axial module's
signs are not in the data; at the integrator's gain its loop ignites the whole net).
"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cadence-examples"))
from engine.export import write_payload, payload_of  # noqa: E402
from connectome_compiler import compile, brain  # noqa: E402
from connectome_compiler.sources import zebrafish_brainstem as zb  # noqa: E402
from connectome_compiler.verify.burst import GRADED_UNIT  # noqa: E402

ATTENUATIONS = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]


def select_attenuation(c, gain):
    P = {k: np.array(v) for k, v in c.populations.items()}; INT = P["_Int_"]
    trace = []
    for att in ATTENUATIONS:
        lg = np.zeros(c.n); lg[P["_Axl_"]] = -att
        b = brain(c, gain, backend="cpu", log_gain=lg, **GRADED_UNIT)
        s1 = b.settle({int(i): 0.03 for i in INT}, steps=20); s2 = b.settle(None, steps=600, state=s1, trajectory=True)
        m200, m600 = float(s2.trajectory[199][INT].mean()), float(s2.trajectory[-1][INT].mean())
        row = {"attenuation": att, "int_200": m200, "int_600": m600, "ratio": m600 / max(m200, 1e-12), "active_600": float((s2.trajectory[-1] >= 0.5).mean())}
        trace.append(row)
        if row["ratio"] < 1.0 and row["active_600"] < 0.05:
            return att, trace
    return None, trace


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipt", type=Path, default=Path("../connectome-research/receipts/zebrafish_brainstem_oculomotor.json"))
    p.add_argument("--scope", default="all")
    p.add_argument("--out", type=Path, default=Path("web/data/brain.json"))
    a = p.parse_args(argv)
    rec = json.loads(a.receipt.read_text()); gain = rec["wirings"]["measured"]["selected_gain"]
    t = zb.load(scope=a.scope); c = compile(t)
    att, trace = select_attenuation(c, gain)
    if att is None:
        raise SystemExit("no attenuation on the grid keeps the net from igniting")
    P = {k: np.array(v) for k, v in c.populations.items()}
    lg = np.zeros(c.n); lg[P["_Axl_"]] = -att
    b = brain(c, gain, backend="cpu", log_gain=lg, **GRADED_UNIT)
    sub = zb.submodules(t)
    extra = {"source": rec["source"], "scope": a.scope, "gain": gain, "axial_attenuation": att, "unit": GRADED_UNIT,
             "submodule": sub.tolist(), "kind": t.neurons.kind.tolist(), "id": t.neurons.id.tolist(), "tables_digest": t.digest(), "connectome_digest": c.digest()}
    out = write_payload(b, a.out, extra=extra)
    Path("receipts").mkdir(exist_ok=True)
    Path("receipts/brain_export.json").write_text(json.dumps({"gain": gain, "axial_attenuation": att, "trace": trace, "scope": a.scope, "neurons": c.n, "classes": int(c.synapses), "payload": str(out), "bytes": out.stat().st_size, "tables_digest": t.digest(), "connectome_digest": c.digest(), "protocol_digest": rec["protocol_digest"]}, indent=1))
    print("exported", out, out.stat().st_size // 1024, "KB; gain", gain, "axial attenuation", att, "| trace:", [(r["attenuation"], round(r["ratio"], 2), round(r["active_600"], 3)) for r in trace])


if __name__ == "__main__":
    main()
