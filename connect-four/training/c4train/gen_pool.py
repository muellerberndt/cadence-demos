"""A shared pool of solver-labelled positions, generated in parallel.

Each worker runs its own solver and plays games of the solver against itself (strength .5 to 1.0,
short random openings); every non-terminal position is kept with its seven column scores. The
pool is written as packed bits (inputs), scores (int16) and stone counts, so millions of
positions stay small.

    python -m c4train.gen_pool --positions 1000000 --workers 90 --seed 1 --out runs/pool_1m.npz
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import time

import numpy as np


def _work(args):
    count, seed = args
    from .positions import noisy_game
    from .solver import Solver
    solver, rng, items = Solver(), np.random.default_rng(seed), []
    while len(items) < count:
        items += noisy_game(solver, rng, strength=float(rng.uniform(0.5, 1.0)))
    solver.close()
    items = items[:count]
    x = np.stack([b.encode() for b, _ in items]).astype(bool)
    s = np.stack([np.asarray(sc) for _, sc in items]).astype(np.int16)
    return np.packbits(x, axis=1), s


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--positions", type=int, default=1_000_000)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    t0 = time.time()
    per = -(-a.positions // a.workers)
    with mp.Pool(a.workers) as pool:
        parts = pool.map(_work, [(per, a.seed * 100_003 + k) for k in range(a.workers)])
    bits = np.concatenate([b for b, _ in parts])[: a.positions]
    scores = np.concatenate([s for _, s in parts])[: a.positions]
    np.savez_compressed(a.out, bits=bits, scores=scores)
    print(f"{len(bits)} positions in {time.time() - t0:.0f} s -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
