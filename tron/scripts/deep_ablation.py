"""how much a skip-built deep brain's deep pathway carries its play.

    python scripts/deep_ablation.py runs/r3/best/sp-deep3n-m2000.npz

The brain as it is, and the same brain with every synapse of the deep pathway (among the modules
above `module_0`, the top module and `motor`, and `module_0` into the next module) at zero, so
only the skip (`module_0` -> `motor`) decides: their greedy agreement on the turn set (2,213
positions), and each one's score over 64 mirror pairs against `voronoi` (checkpoint seeds).
Disagreement and the score drop measure what the deep pathway contributes.
"""
import json
import sys
import tempfile
import os
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3eval  # noqa: E402
from net2net import mask, edit  # noqa: E402


def main():
    from cadence import Brain
    path = sys.argv[1]
    b = Brain.load(path, backend="cpu")
    c = b.connectome
    new = [q for q in c.populations if q.startswith("module_") and q != "module_0"] + ["association"]
    deep = mask(c, "association", "motor") | mask(c, "motor", "association")
    for x in ["module_0"] + new:
        for y in new:
            if x != y:
                deep |= mask(c, x, y) | mask(c, y, x)

    def fn(z, _):
        z["efficacy"] = z["efficacy"].copy()
        z["efficacy"][deep] = 0.0
    cut = edit(b, fn)
    d = tempfile.mkdtemp()
    cut_path = cut.save(os.path.join(d, "cut.npz"))
    ts = np.load("runs/r3/turnset.npz")
    X = ts["x"].astype(np.float64)

    def moves(x):  # every position settled from rest
        out = []
        for r in X:
            x.reset()
            out.append(int(x.act(r[None], greedy=True)[0]))
        return np.array(out)
    m1, m0 = moves(b), moves(cut)
    r = r3eval.readings([(path, "voronoi", 64, r3eval.CHECKPOINT), (cut_path, "voronoi", 64, r3eval.CHECKPOINT)], 16)
    out = {"brain": path, "deep_synapses": int(deep.sum()), "agreement_with_pathway_cut": float((m1 == m0).mean()),
           "turns_with": float((m1 != 1).mean()), "turns_cut": float((m0 != 1).mean()),
           "voronoi_64_with": r[(path, "voronoi")]["score"], "voronoi_64_cut": r[(cut_path, "voronoi")]["score"]}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
