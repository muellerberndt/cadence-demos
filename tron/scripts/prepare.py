"""Build the data files the training scripts read, in runs/r3/ (run from the tron/ folder):

- corpus3.jsonl: the teacher's games (`voronoi3` against the school pool), replayed through any
  sense by the corpus lessons (`tron.corpus`);
- scenarios.json: fixed strategy positions (walled in, cutting off, space filling) from bot games
  on seeds 2,000,000+, never trained on (`tron.scenarios`);
- turnset.npz: a fixed set of positions a brain reaches against the labelling opponents, each
  with the 10-ply alpha-beta (`ab5`) label, whether it turns and whether the position is critical
  (some move loses); the selection gate and the deep scripts score agreement on it.

    python scripts/prepare.py                                   # the sizes the shipped brains used
    python scripts/prepare.py --games 60 --scenario-games 30 --turn-games 4   # a smoke run

The turn set needs a brain to ride: `--turn-brain` (default: the packed flat brain).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent))
from tron import absearch, corpus, scenarios  # noqa: E402
from tron.field import make_sense3  # noqa: E402
from tron.world import Arena, mulberry32  # noqa: E402


def turnset(brain_path: str, games: int, out: Path) -> dict:
    from cadence import Brain
    from phasec import LABEL_OPPS, OPP

    see = make_sense3("field")[0]
    brain = Brain.load(brain_path, backend="cpu")
    X, Y, T, C = [], [], [], []
    for g in range(games):
        s = 6_500_000 + g
        arena, draw = Arena(24, seed=s), mulberry32(s)
        while not arena.over:
            x = see(arena, 0)
            y, values = absearch.search(arena, 0, 5)
            X.append(x)
            Y.append(y)
            T.append(y != 1)
            C.append((max(values) - min(values)) > absearch.BIG // 4)
            brain.reset()
            mine = int(brain.act(x[None, :], greedy=True)[0])
            arena.step((mine, OPP[LABEL_OPPS[g % len(LABEL_OPPS)]](arena, 1, draw)))
    np.savez_compressed(out, x=np.array(X, np.float32), y=np.array(Y), turn=np.array(T), crit=np.array(C))
    return {"positions": len(Y), "turns": float(np.mean(T)), "critical": float(np.mean(C))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/r3")
    ap.add_argument("--games", type=int, default=3000, help="corpus games")
    ap.add_argument("--scenario-games", type=int, default=400)
    ap.add_argument("--turn-games", type=int, default=24)
    ap.add_argument("--turn-brain", default=str(HERE.parents[1] / "web" / "pack" / "flat" / "brain" / "brain.npz"))
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    t = time.time()
    report["corpus"] = corpus.build(out / "corpus3.jsonl", a.games, teacher="voronoi3", workers=a.workers)
    report["corpus"]["seconds"] = round(time.time() - t, 1)
    t = time.time()
    report["scenarios"] = scenarios.build(out / "scenarios.json", games=a.scenario_games)
    report["scenarios"]["seconds"] = round(time.time() - t, 1)
    t = time.time()
    report["turnset"] = turnset(a.turn_brain, a.turn_games, out / "turnset.npz")
    report["turnset"]["seconds"] = round(time.time() - t, 1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
