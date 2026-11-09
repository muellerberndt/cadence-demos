"""Read the packed brains against bots, as the page plays them: every move settled from rest,
greedy, mirror pairs (each seed once from either seat). `--sims N` reads the page's search mode:
the brain guides a tree search of N simulations per move (`tron/mcts.py`, territory leaves).

    python scripts/reading.py --pairs 32 --opponents voronoi > evidence/reading-0952.json
    python scripts/reading.py --pairs 16 --opponents voronoi voronoi2 --sims 0 32

The seeds are the checkpoint set (2,200,000+) unless `--base` names another.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import time
from multiprocessing import get_context
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent))
import r3eval  # noqa: E402

PACK = HERE.parents[1] / "web" / "pack"


def _chunk(args):
    """Mirror pairs lo..hi of one brain (and search size) against one bot."""
    slot, sims, opp, lo, hi, base = args[:6]
    depth, bonus = (args[6], args[7]) if len(args) > 6 else (0, 0)
    from cadence import Brain
    from phasec import OPP
    from tron import absearch, mcts, r3
    from tron.world import Arena, mulberry32

    brain = Brain.load(str(PACK / slot / "brain" / "brain.npz"), backend="cpu")
    if sims > 0:
        ev = mcts.Evaluator(brain)
        pol = lambda a, seat: mcts.search(a, seat, ev, sims=sims)[0]  # noqa: E731
    else:
        pol = r3.policy(brain, "field")
    if depth > 0:  # the page's player: the brain proposes, the alpha-beta over the rules decides
        alone = pol
        pol = lambda a, seat: absearch.search(a, seat, depth, alone(a, seat), bonus)[0]  # noqa: E731
    play = OPP[opp]
    w = l = d = 0
    ms, moves = 0.0, 0
    for i in range(lo, hi):
        s = base + i
        for seat in (0, 1):
            a, dr = Arena(24, seed=s), mulberry32(s)
            while not a.over:
                t0 = time.perf_counter()
                m = pol(a, seat)
                ms += time.perf_counter() - t0
                moves += 1
                t = play(a, 1 - seat, dr)
                a.step((m, t) if seat == 0 else (t, m))
            w += a.winner == seat
            l += a.winner == 1 - seat
            d += a.winner is None
    return slot, sims, opp, w, l, d, ms, moves, depth


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=32)
    ap.add_argument("--opponents", nargs="+", default=["voronoi"])
    ap.add_argument("--slots", nargs="+", default=["flat", "deep"])
    ap.add_argument("--sims", nargs="+", type=int, default=[0])
    ap.add_argument("--depths", nargs="+", type=int, default=[0], help="alpha-beta rounds after the brain (0: the brain alone)")
    ap.add_argument("--bonus", type=int, default=8, help="leaf units added to the brain's move at the root")
    ap.add_argument("--base", type=int, default=r3eval.CHECKPOINT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--step", type=int, default=4, help="pairs per task")
    a = ap.parse_args()
    import cadence

    tasks = [(s, n, o, lo, min(lo + a.step, a.pairs), a.base, dp, a.bonus) for s in a.slots for n in a.sims for dp in a.depths
             for o in a.opponents for lo in range(0, a.pairs, a.step)]
    t0 = time.time()
    with get_context(r3eval.MP).Pool(max(1, min(a.workers, len(tasks)))) as pool:
        res = pool.map(_chunk, tasks, chunksize=1)
    out = {"cadence": cadence.__version__, "python": platform.python_version(), "pairs": a.pairs,
           "seeds": f"{a.base:,}+", "play": "brain.reset() then brain.act(field, greedy=True) each move; "
           "with sims > 0 the move is the root's most visited of a tree search the brain guides",
           "seconds": round(time.time() - t0, 1), "readings": {}}
    for slot, sims, opp, w, l, d, ms, moves, depth in res:
        key = slot if sims == 0 else f"{slot}+search{sims}"
        if depth:
            key += f"+ab{depth}"
        t = out["readings"].setdefault(key, {}).setdefault(opp, {"wins": 0, "losses": 0, "draws": 0, "_ms": 0.0, "_moves": 0})
        t["wins"] += w
        t["losses"] += l
        t["draws"] += d
        t["_ms"] += ms
        t["_moves"] += moves
    for per in out["readings"].values():
        for t in per.values():
            n = t["wins"] + t["losses"] + t["draws"]
            sc = (t["wins"] + 0.5 * t["draws"]) / n
            t.update(score=round(sc, 3), ci95=round(1.96 * math.sqrt(max(sc * (1 - sc), 1e-9) / n), 3),
                     ms_per_move=round(1e3 * t.pop("_ms") / max(t.pop("_moves"), 1), 1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
