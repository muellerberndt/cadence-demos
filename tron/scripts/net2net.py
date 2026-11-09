"""function-preserving deep growth of a flat brain.

    python scripts/net2net.py --donor runs/r3/best/exitsel-mako-d3-m7500.npz --out runs/r3/c/n2n

Two constructions of a (256, 256) brain from the flat donor (Mako 1.6), each scored at 0 moments
by its greedy agreement with the donor on the fixed turn set (runs/r3/turnset.npz) and, for the
best variants, 128 mirror pairs against `voronoi` on the checkpoint seeds:

- `skip`: the (256, 256) connectome plus synapses between `module_0` and `motor` both ways (a
  custom anatomy, `Brain.compose(connectome=...)`), the donor grafted as `sensory`, `association`
  -> `module_0` and `motor`: its trained input and readout run through the skip; the new top
  module's joints start at this brain's construction scaled by `eps` (0: disconnected, the
  donor's function exactly, but no learning signal reaches the top module).
- `relay`: the plain (256, 256) layout; the donor's input side grafted into `module_0` and its
  readout side (`association`, `motor`, `prefrontal`) into the top module; the synapses
  `module_0` -> top set to `g` on the diagonal and 0 elsewhere, top -> `module_0` to `back` x
  the diagonal: the top module relays `module_0` through the rectified sigmoid.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tron import r3  # noqa: E402

GENES = {"sense": "field", "apical": 0, "teaching": "normalized", "eta_scale": 0.3, "temperature": 0.1,
         "lateral": -0.5, "trace_amp": 0.0, "trace_decay": 0.5, "sensory": 1.0}


def mask(c, a, b):
    pa, pb = np.zeros(c.n, bool), np.zeros(c.n, bool)
    pa[list(c.populations[a])] = True
    pb[list(c.populations[b])] = True
    return pa[c.pre] & pb[c.post]


def edit(brain, fn):
    """Save, change arrays of the checkpoint with fn(dict, connectome), load (CPU)."""
    from cadence import Brain
    with tempfile.TemporaryDirectory() as d:
        p = brain.save(os.path.join(d, "a.npz"))
        z = dict(np.load(p, allow_pickle=False))
        fn(z, brain.connectome)
        q = os.path.join(d, "b.npz")
        np.savez(q, **z)
        return Brain.load(q, backend="cpu")


def body(layout, seed, connectome=None):
    from cadence import Brain
    g = dict(GENES, layout=layout)
    b = r3.compose(g, seed, backend="cpu")
    if connectome is None:
        return b
    return b, g


def skip_brain(donor, seed, eps, layout="deep2w"):
    from cadence import Brain
    from cadence.connectome import Connectome
    base = r3.compose(dict(GENES, layout=layout), seed, backend="cpu")
    c = base.connectome
    m0, mo = list(c.populations["module_0"]), list(c.populations["motor"])
    pre = np.r_[c.pre, np.repeat(m0, len(mo)), np.tile(mo, len(m0))]
    post = np.r_[c.post, np.tile(mo, len(m0)), np.repeat(m0, len(mo))]
    count = np.r_[c.count, np.ones(2 * len(m0) * len(mo))]
    sign = np.r_[c.sign, np.ones(2 * len(m0) * len(mo))]
    cc = Connectome.from_synapses(c.n, pre=pre, post=post, count=count, sign=sign,
                                  populations=dict(c.populations), label=layout + "+skip")
    cfg = base.learner.config
    b = Brain.compose(r3.make_sense3("field")[1], 3, connectome=cc, recall=False, seed=seed, learning=cfg,
                      arousal=True, working_memory_amplitude=0.0)
    g = b.graft(donor, {"sensory": "sensory", "association": "module_0", "motor": "motor"}, joints="kept")
    if eps != 1.0:
        c2 = g.connectome
        # every synapse of the new pathway: among the modules above module_0, the top module and
        # motor, and module_0 to the next module (not the grafted input or the skip)
        new = [q for q in c2.populations if q.startswith("module_") and q != "module_0"] + ["association"]
        top = mask(c2, "association", "motor") | mask(c2, "motor", "association")
        for x in ["module_0"] + new:
            for y in new:
                if x != y:
                    top |= mask(c2, x, y) | mask(c2, y, x)

        def fn(z, _):
            z["efficacy"] = z["efficacy"].copy()
            z["efficacy"][top] *= eps
        g = edit(g, fn)
    return g


def relay_brain(donor, seed, gain, back):
    base = r3.compose(dict(GENES, layout="deep2w"), seed, backend="cpu")
    b = base.graft(donor, {"sensory": "sensory", "association": "module_0"}, joints="zero")
    b = b.graft(donor, {"association": "association", "motor": "motor", "prefrontal": "prefrontal"}, joints="zero")
    c = b.connectome
    up, down = mask(c, "module_0", "association"), mask(c, "association", "module_0")
    m0 = {v: i for i, v in enumerate(sorted(c.populations["module_0"]))}
    top = {v: i for i, v in enumerate(sorted(c.populations["association"]))}

    sel = up | down
    idx = np.flatnonzero(sel)
    is_diag = np.array([(m0.get(int(c.pre[k])) == top.get(int(c.post[k]))) if up[k] else
                        (top.get(int(c.pre[k])) == m0.get(int(c.post[k]))) for k in idx])
    target = np.where(up[idx], gain, back) * is_diag

    def ones(z, _):
        z["efficacy"] = z["efficacy"].copy()
        z["efficacy"][sel] = 1.0
    probe = edit(b, ones)
    scale = np.asarray(probe.brain.weights)[sel]  # effective weight per unit efficacy

    def fn(z, _):
        z["efficacy"] = z["efficacy"].copy()
        z["efficacy"][sel] = np.where(np.abs(scale) > 1e-12, target / np.where(np.abs(scale) > 1e-12, scale, 1.0), 0.0)
    return edit(b, fn)


def main():
    from cadence import Brain
    import r3eval
    p = argparse.ArgumentParser()
    p.add_argument("--donor", default="runs/r3/best/exitsel-mako-d3-m7500.npz")
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=101)
    p.add_argument("--probe", action="store_true")
    p.add_argument("--layouts", default="deep2w", help="skip layouts to build (comma-separated)")
    p.add_argument("--eps", default="0,0.05,0.2,1", help="skip: scales of the new pathway")
    p.add_argument("--relay", action="store_true", help="also the relay constructions")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    donor = Brain.load(a.donor, backend="cpu")
    ts = np.load("runs/r3/turnset.npz")
    X = ts["x"].astype(np.float64)

    def moves(b):
        b.reset()
        return np.array([int(b.act(x[None], greedy=True)[0]) for x in X])
    d = moves(donor)
    turn = d != 1
    crit = ts["crit"].astype(bool)
    rows = []
    variants = [("skip", dict(eps=float(e), layout=L)) for L in a.layouts.split(",") for e in a.eps.split(",")]
    if a.relay:
        variants += [("relay", dict(gain=g, back=bk)) for g in (1.0, 2.0, 4.0, 8.0) for bk in (0.0,)]
    for kind, kw in variants:
        name = kind + "-" + "-".join(f"{k}{v}" for k, v in kw.items())
        try:
            b = skip_brain(donor, a.seed, **kw) if kind == "skip" else relay_brain(donor, a.seed, **kw)
            m = moves(b)
            row = {"name": name, "agree": float((m == d).mean()), "agree_turns": float((m == d)[turn].mean()),
                   "agree_critical": float((m == d)[crit].mean()), "turns": float((m != 1).mean())}
            path = out / f"{name}.npz"
            b.save(str(path))
            row["path"] = str(path)
        except Exception as e:  # noqa: BLE001
            row = {"name": name, "error": str(e)[:400]}
        print(json.dumps(row), flush=True)
        rows.append(row)
    ok = sorted([r for r in rows if "agree" in r], key=lambda r: -r["agree"])[:3]
    for r in ok:
        r["voronoi_128"] = r3eval.reading(r["path"], "voronoi", 128, r3eval.CHECKPOINT, 24)
        print(json.dumps({"name": r["name"], "voronoi": r["voronoi_128"]["score"]}), flush=True)
    (out / "constructions.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
