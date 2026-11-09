"""parallel mirror-pair readings of frozen brains.

`reading(path, opp, pairs, base, workers)` plays `pairs` mirror pairs (2 x pairs games) of the
brain at `path` (field sense, CPU twin, greedy) against `opp` (a bot name of `phasec.OPP` or
`brain:<path>`) on seeds base, base+1, ...; it returns the head-to-head dict (wins,
losses, draws, score, ci95). Chunks of 8 pairs run in a process pool, so a 128-pair reading of
a deep brain takes minutes, not an hour.
"""
from __future__ import annotations

import math
import os
import sys
import warnings
from multiprocessing import get_context

# Process pools fork on Linux; on macOS a fork after NumPy or Numba threads have run can hang,
# so pools spawn there. TRON_MP=fork|spawn|forkserver overrides.
MP = os.environ.get("TRON_MP") or ("spawn" if sys.platform == "darwin" else "fork")
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tron import r3  # noqa: E402
from tron.world import Arena, mulberry32  # noqa: E402
from phasec import OPP  # noqa: E402

CHECKPOINT, GATE, DUEL, CONFIRM, MAKO = 2_200_000, 4_500_000, 4_000_000, 7_000_000, 8_000_000
# Smoke runs: TRON_MAX_PAIRS=n caps every reading at n mirror pairs (0: no cap).
MAX_PAIRS = int(os.environ.get("TRON_MAX_PAIRS", "0"))


def _cap(n):
    return min(n, MAX_PAIRS) if MAX_PAIRS > 0 else n


def _chunk(args):
    path, opp, lo, hi, base = args
    from cadence import Brain
    b = Brain.load(path, backend="cpu")
    pol = r3.policy(b, "field")
    ob = None
    if opp.startswith("brain:"):
        ob = Brain.load(opp[6:], backend="cpu")
        op = r3.policy(ob, "field")
        play = lambda a, s, d: op(a, s)  # noqa: E731
    else:
        play = OPP[opp]
    w = l = d = 0
    for i in range(lo, hi):
        s = base + i
        for seat in (0, 1):
            a, dr = Arena(24, seed=s), mulberry32(s)
            b.reset()
            if ob is not None:
                ob.reset()
            while not a.over:
                m, t = pol(a, seat), play(a, 1 - seat, dr)
                a.step((m, t) if seat == 0 else (t, m))
            w += a.winner == seat
            l += a.winner == 1 - seat
            d += a.winner is None
    return path, opp, int(w), int(l), int(d)


def readings(jobs, workers=16, step=8):
    """jobs: [(path, opp, pairs, base)] -> {(path, opp): result dict}, all in one pool."""
    tasks = [(p, o, lo, min(lo + step, _cap(n)), base) for p, o, n, base in jobs for lo in range(0, _cap(n), step)]
    with get_context(MP).Pool(max(1, min(workers, len(tasks)))) as pool:
        res = pool.map(_chunk, tasks, chunksize=1)
    out = {}
    for p, o, w, l, d in res:
        t = out.setdefault((p, o), {"wins": 0, "losses": 0, "draws": 0})
        t["wins"] += w
        t["losses"] += l
        t["draws"] += d
    for t in out.values():
        n = t["wins"] + t["losses"] + t["draws"]
        sc = (t["wins"] + 0.5 * t["draws"]) / n
        t.update(score=sc, ci95=1.96 * math.sqrt(max(sc * (1 - sc), 1e-9) / n))
    return out


def reading(path, opp="voronoi", pairs=128, base=CHECKPOINT, workers=16):
    return readings([(str(path), opp, pairs, base)], workers)[(str(path), opp)]


def _pairs(args):
    """Per-pair scores (0, 0.25, ..., 1: the mean of the two seats) for seeds base+lo .. base+hi-1."""
    path, opp, lo, hi, base = args
    from cadence import Brain
    b = Brain.load(path, backend="cpu")
    pol = r3.policy(b, "field")
    ob = None
    if opp.startswith("brain:"):
        ob = Brain.load(opp[6:], backend="cpu")
        op = r3.policy(ob, "field")
        play = lambda a, s, d: op(a, s)  # noqa: E731
    else:
        play = OPP[opp]
    out = []
    for i in range(lo, hi):
        s = base + i
        sc = 0.0
        for seat in (0, 1):
            a, dr = Arena(24, seed=s), mulberry32(s)
            b.reset()
            if ob is not None:
                ob.reset()
            while not a.over:
                m, t = pol(a, seat), play(a, 1 - seat, dr)
                a.step((m, t) if seat == 0 else (t, m))
            sc += 1.0 if a.winner == seat else 0.5 if a.winner is None else 0.0
        out.append(sc / 2)
    return path, opp, base, lo, out


def pair_scores(jobs, workers=16, step=8):
    """jobs: [(path, opp, lo, hi, base)] -> {(path, opp, base): {pair index: score}}."""
    jobs = [(p, o, lo, min(hi, lo + _cap(hi - lo)), base) for p, o, lo, hi, base in jobs]
    tasks = [(p, o, s, min(s + step, hi), base) for p, o, lo, hi, base in jobs for s in range(lo, hi, step)]
    out = {}
    if not tasks:
        return out
    with get_context(MP).Pool(max(1, min(workers, len(tasks)))) as pool:
        for p, o, base, lo, sc in pool.map(_pairs, tasks, chunksize=1):
            d = out.setdefault((p, o, base), {})
            for k, v in enumerate(sc):
                d[lo + k] = v
    return out


def llr(x, mu0, mu1, min_n=32, var_floor=0.02):
    """Normal-approximation log-likelihood ratio of mean mu1 against mu0 for the samples x; 0 until
    `min_n` samples, the variance floored (identical brains give zero-variance differences)."""
    import numpy as np
    x = np.asarray(x, float)
    if len(x) < min_n:
        return 0.0
    v = max(float(x.var(ddof=1)), var_floor)
    m = float(x.mean())
    return len(x) * ((m - mu0) ** 2 - (m - mu1) ** 2) / (2 * v)
