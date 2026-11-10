"""Positions labelled by the brain-plus-search player, for distilling the search into the brain.

Every game is played by the player (the brain's settle ranks the columns; the search of
connect4/search.py vets them, at ``--nodes`` positions a move) from the empty board after a few
random opening moves:

- self-play: the player on both sides; with probability ``--explore`` a move is drawn at random
  among the columns the search keeps (alive and within the margin of the best), so games differ;
- against the solver at 1.0, 0.9 or 0.7 (a random column otherwise), the player first or second,
  on a share ``--fixed`` of the games.

Each position where the player moves is kept with: the board (84 packed bits), the solver's
seven scores, the search's seven root values (-2000 for a full column), the search's column and
reason, the brain's own column and the depth reached. Shards of ``--per-shard`` games go to
``--out/shard-<worker>-<n>.npz``.

    python -m c4train.label BRAIN.npz --games 4000 --workers 60 --out runs/labels/g0
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from multiprocessing import get_context
from pathlib import Path

import numpy as np

STATE: dict = {}


def _init(brain_path: str, demo: str, nodes: int) -> None:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    sys.path.insert(0, demo)
    from cadence import Brain

    from .policy import CadencePolicy, Planes
    from .solver import Solver

    inner = CadencePolicy(modules=(8,), seed=0, surprise=False, verdict=True, inputs=126)
    inner.brain = Brain.load(brain_path, backend="cpu", precision="float64")
    STATE["policy"] = Planes(inner)
    STATE["temperature"] = float(inner.brain.learner.config.temperature)
    STATE["solver"] = Solver()
    STATE["nodes"] = nodes


def _player(board, rng, explore: float):
    from connect4.game import Board as DemoBoard
    from connect4.search import MARGIN, WIN, choose

    motor = STATE["policy"].readout(board.encode()[None, :])[0]
    r = choose(DemoBoard(board.mine, board.theirs), motor, STATE["temperature"], nodes=STATE["nodes"])
    column = r["column"]
    values = np.full(7, -2000.0, dtype=np.float32)
    for c, v in r.get("values", {}).items():
        values[int(c)] = v
    if explore and rng.random() < explore and r["reason"] != "win":
        alive = [c for c in range(7) if values[c] > -(WIN - 50)]
        if alive:
            top = max(values[c] for c in alive)
            kept = [c for c in alive if values[c] >= top - MARGIN]
            column = int(rng.choice(kept))
    return column, r, values


def _game(args):
    from .game import Board
    from .positions import solver_move

    seed, kind, strength, player_first, explore, opening = args
    rng = np.random.default_rng(seed)
    solver = STATE["solver"]
    board = Board.empty()
    rows = []
    player_turn = player_first
    for ply in range(42):
        if board.full():
            break
        if ply < opening:
            column = int(rng.choice(np.flatnonzero(board.legal())))
        elif kind == "self" or player_turn:
            column, r, values = _player(board, rng, explore if kind == "self" else 0.0)
            rows.append((np.packbits(board.encode()[:84].astype(np.uint8)), solver.scores(board).astype(np.int16),
                         values, int(r["column"]), int(r["brain"]), {"win": 2, "search": 1}.get(r["reason"], 0),
                         int(r.get("depth", 0))))
        else:
            column = solver_move(solver, board, rng, strength)
        if board.winning(column):
            break
        board = board.play(column)
        player_turn = not player_turn
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("brain")
    p.add_argument("--demo", default=str(Path(__file__).resolve().parents[2]), help="the connect-four folder (its connect4 package)")
    p.add_argument("--games", type=int, default=2000)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--nodes", type=int, default=120_000)
    p.add_argument("--fixed", type=float, default=0.4, help="share of games against the solver")
    p.add_argument("--explore", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--per-shard", type=int, default=50)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    jobs = []
    for g in range(a.games):
        if rng.random() < a.fixed:
            jobs.append((int(rng.integers(1 << 62)), "solver", float(rng.choice([1.0, 0.9, 0.7])),
                         bool(g % 2 == 0), 0.0, int(rng.integers(0, 3))))
        else:
            jobs.append((int(rng.integers(1 << 62)), "self", 1.0, True, a.explore, int(rng.integers(2, 5))))
    began = time.time()
    shard, buffer, done, positions = 0, [], 0, 0

    def flush():
        nonlocal shard, buffer
        if not buffer:
            return
        bits, scores, values, search, brain, reason, depth = (np.stack([r[k] for r in buffer]) if k < 3 else
                                                              np.array([r[k] for r in buffer]) for k in range(7))
        np.savez_compressed(a.out / f"shard-{a.seed}-{shard:04d}.npz", bits=bits, scores=scores, values=values,
                            search=search, brain=brain, reason=reason, depth=depth)
        shard += 1
        buffer = []

    with get_context("spawn").Pool(a.workers, initializer=_init, initargs=(a.brain, a.demo, a.nodes)) as pool:
        for rows in pool.imap_unordered(_game, jobs, chunksize=1):
            buffer += rows
            done += 1
            positions += len(rows)
            if done % a.per_shard == 0:
                flush()
                print(json.dumps({"games": done, "positions": positions, "seconds": round(time.time() - began, 1)}), flush=True)
    flush()
    print(json.dumps({"games": done, "positions": positions, "seconds": round(time.time() - began, 1), "done": True}), flush=True)


if __name__ == "__main__":
    main()
