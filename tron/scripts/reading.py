"""Read the packed brains against bots, as the page plays them: every move settled from rest,
greedy, mirror pairs (each seed once from either seat).

    python scripts/reading.py --pairs 32 --opponents voronoi > evidence/reading-0952.json

The seeds are the checkpoint set (2,200,000+) unless `--base` names another.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent))
import r3eval  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=32)
    ap.add_argument("--opponents", nargs="+", default=["voronoi"])
    ap.add_argument("--slots", nargs="+", default=["flat", "deep"])
    ap.add_argument("--base", type=int, default=r3eval.CHECKPOINT)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    import cadence

    pack = HERE.parents[1] / "web" / "pack"
    jobs = [(str(pack / s / "brain" / "brain.npz"), o, a.pairs, a.base) for s in a.slots for o in a.opponents]
    t0 = time.time()
    got = r3eval.readings(jobs, a.workers)
    out = {"cadence": cadence.__version__, "python": platform.python_version(), "pairs": a.pairs,
           "seeds": f"{a.base:,}+", "play": "brain.reset() then brain.act(field, greedy=True) each move",
           "seconds": round(time.time() - t0, 1), "readings": {}}
    for s in a.slots:
        meta = json.loads((pack / s / "brain" / "meta.json").read_text())
        out["readings"][s] = {"brain": meta["name"],
                              **{o: got[(str(pack / s / "brain" / "brain.npz"), o)] for o in a.opponents}}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
