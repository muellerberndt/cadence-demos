"""a skip-built deep brain with its skip scaled.

    python scripts/skip_scale.py <brain.npz> <scale> <out.npz>

Every synapse between `module_0` and `motor` (the skip, both ways) has its efficacy multiplied by
<scale>; with the skip weaker the deep pathway must carry more of the play. Prints the new
brain's agreement with the original on the turn set, the share of its moves the deep pathway
decides (disagreement with the same brain with the deep pathway cut), and 64 mirror pairs against
`voronoi` (checkpoint seeds).
"""
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
import r3eval  # noqa: E402
from net2net import mask, edit  # noqa: E402


def deep_mask(c):
    new = [q for q in c.populations if q.startswith("module_") and q != "module_0"] + ["association"]
    deep = mask(c, "association", "motor") | mask(c, "motor", "association")
    for x in ["module_0"] + new:
        for y in new:
            if x != y:
                deep |= mask(c, x, y) | mask(c, y, x)
    return deep


def main():
    from cadence import Brain
    src, scale, dst = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    b = Brain.load(src, backend="cpu")
    c = b.connectome
    skip = mask(c, "module_0", "motor") | mask(c, "motor", "module_0")

    def fn(z, _):
        z["efficacy"] = z["efficacy"].copy()
        z["efficacy"][skip] *= scale
    s = edit(b, fn)
    s.save(dst)
    deep = deep_mask(c)

    def fn2(z, _):
        z["efficacy"] = z["efficacy"].copy()
        z["efficacy"][deep] = 0.0
    cut = edit(s, fn2)
    ts = np.load("runs/r3/turnset.npz")
    X = ts["x"].astype(np.float64)

    def moves(x):  # every position settled from rest
        out = []
        for r in X:
            x.reset()
            out.append(int(x.act(r[None], greedy=True)[0]))
        return np.array(out)
    m_src, m_new, m_cut = moves(b), moves(s), moves(cut)
    r = r3eval.reading(dst, "voronoi", 64, r3eval.CHECKPOINT, 16)
    print(json.dumps({"src": src, "scale": scale, "out": dst, "agree_with_src": float((m_new == m_src).mean()),
                      "deep_decides": float((m_new != m_cut).mean()), "turns": float((m_new != 1).mean()),
                      "voronoi_64": r["score"]}), flush=True)


if __name__ == "__main__":
    main()
