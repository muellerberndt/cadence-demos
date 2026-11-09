"""The brain plus search (connect4/search.py of the demo) against the solver and against the brain
alone: games from the empty board, the player first and second.

    python -m c4train.play_search BRAIN.npz --games 40 --nodes 40000 --demo PATH/connect-four > out.json

Opponents: the perfect solver (strength 1.0; ties at random) and the solver at 0.9 and 0.7 (a
random column otherwise), from both seats; and the brain alone (one settle per move), from both
seats after two random opening moves (the brain alone is deterministic, so the openings vary
the games).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from cadence import Brain

from .policy import CadencePolicy, Planes
from .positions import own_game, solver_move
from .solver import Solver


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("brain")
    p.add_argument("--games", type=int, default=40)
    p.add_argument("--nodes", type=int, default=40_000)
    p.add_argument("--seed", type=int, default=31337)
    p.add_argument("--demo", default=str(Path(__file__).resolve().parents[2]))
    p.add_argument("--only", default="", help="comma list of conditions to run")
    p.add_argument("--alone", action="store_true", help="the brain alone plays (the baseline on the same seeds)")
    a = p.parse_args()
    sys.path.insert(0, a.demo)
    from connect4.game import Board as DemoBoard
    from connect4.search import choose as search_choose

    inner = CadencePolicy(modules=(8,), seed=0, surprise=False, verdict=True, inputs=126)
    inner.brain = Brain.load(a.brain, backend="cpu", precision="float64")
    policy = Planes(inner) if len(inner.brain.sensory_index) == 126 else inner
    temperature = float(inner.brain.learner.config.temperature)
    stats = {"overruled": 0, "moves": 0, "ms": [], "depth": []}

    def player(boards):
        if a.alone:
            return policy.choose(boards)
        out = []
        for b in boards:
            motor = policy.readout(b.encode()[None, :])[0]
            t = time.perf_counter()
            r = search_choose(DemoBoard(b.mine, b.theirs), motor, temperature, nodes=a.nodes)
            stats["ms"].append((time.perf_counter() - t) * 1000)
            stats["depth"].append(r["depth"])
            stats["moves"] += 1
            stats["overruled"] += int(r["column"] != r["brain"])
            out.append(r["column"])
        return np.array(out)

    solver = Solver()
    out = {"brain": Path(a.brain).name, "player": "brain alone" if a.alone else "brain + search", "nodes": a.nodes, "games": a.games, "conditions": []}
    only = set(filter(None, a.only.split(",")))
    for name, strength, first in (("solver100_first", 1.0, True), ("solver100_second", 1.0, False),
                                  ("solver090_first", 0.9, True), ("solver090_second", 0.9, False),
                                  ("solver070_first", 0.7, True), ("solver070_second", 0.7, False)):
        if only and name not in only:
            continue
        rng = np.random.default_rng(a.seed)
        res = {"win": 0, "draw": 0, "loss": 0}
        for _ in range(a.games):
            res[own_game(player, solver, rng, strength, policy_first=first, opening=0)["result"]] += 1
        out["conditions"].append({"name": name, **res})
        print(json.dumps(out["conditions"][-1]), file=sys.stderr, flush=True)
    for first in (True, False):
        name = "vs_brain_first" if first else "vs_brain_second"
        if only and name not in only:
            continue
        rng = np.random.default_rng(a.seed + 1)
        res = {"win": 0, "draw": 0, "loss": 0}
        for _ in range(a.games):
            board, turn, result = None, first, "draw"
            from .game import Board as B
            board = B.empty()
            for ply in range(42):
                if board.full():
                    break
                if ply < 2:
                    column = int(rng.choice(np.flatnonzero(board.legal())))
                elif turn:
                    column = int(player([board])[0])
                else:
                    column = int(policy.choose([board])[0])
                if board.winning(column):
                    result = "win" if turn else "loss"
                    break
                board = board.play(column)
                turn = not turn
            res[result] += 1
        out["conditions"].append({"name": name, **res})
        print(json.dumps(out["conditions"][-1]), file=sys.stderr, flush=True)
    solver.close()
    ms = np.array(stats["ms"]) if stats["ms"] else np.zeros(1)
    out["search"] = {"moves": stats["moves"], "overruled_share": round(stats["overruled"] / max(stats["moves"], 1), 4),
                     "ms_median": round(float(np.median(ms)), 1), "ms_max": round(float(ms.max()), 1),
                     "depth_median": float(np.median(stats["depth"])) if stats["depth"] else 0}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
