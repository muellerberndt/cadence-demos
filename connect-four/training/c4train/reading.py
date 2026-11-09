"""Readings of a saved Connect Four brain, loaded on the CPU, the brain alone (one memory-free
settle per move, the strongest legal column):

- held out: 3,000 positions from solver games never taught (``Heldout``, seed 900,001): the
  solver's optimal move, a move keeping the result where the mover is not lost, an immediate
  win taken, a forced block made, and the verdict slot against the solver's result;
- games from the empty board: first against the perfect solver, second against the solver
  playing its best move 90% of the time (random moves otherwise), ``GAMES`` each.

    python -m c4train.reading BRAIN.npz [GAMES=200] [SEED=20991] > reading.json
"""
import json
import sys
import time

import numpy as np

from cadence import Brain

from .evaluate import Heldout
from .policy import CadencePolicy, Planes
from .positions import own_game
from .solver import INVALID, Solver
from .tactics import tactics


def main(path: str, games: int = 200, seed: int = 20991) -> None:
    inner = CadencePolicy(modules=(8,), seed=0, surprise=False, verdict=True, inputs=126)
    inner.brain = Brain.load(path, backend="cpu", precision="float64")
    policy = Planes(inner) if len(inner.brain.sensory_index) == 126 else inner
    solver = Solver()
    began = time.time()
    held = Heldout(solver)
    chosen = np.concatenate([policy.choose_x(held.x[i:i + 500], held.legal[i:i + 500])
                             for i in range(0, len(held.x), 500)])
    rows = np.arange(len(chosen))
    best = np.where(held.scores == INVALID, -10_000, held.scores).max(axis=1)
    got = held.scores[rows, chosen]
    win, block = tactics(held.x)
    out = {"brain": path.rsplit("/", 1)[-1], "heldout": {
        "positions": int(len(chosen)), "optimal": round(float(np.mean(got == best)), 4),
        "keep_not_lost": round(float(np.mean((np.sign(got) == np.sign(best))[best >= 0])), 4),
        "wins_now": round(float(win[rows, chosen][win.any(axis=1)].mean()), 4),
        "blocks": round(float(block[rows, chosen][block.any(axis=1)].mean()), 4)}}
    if len(inner.brain.learner.output_index) > 7:
        judged = np.concatenate([policy.verdict(held.x[i:i + 500]).argmax(axis=1)
                                 for i in range(0, len(held.x), 500)])
        out["heldout"]["verdict"] = round(float(np.mean(judged == np.sign(best) + 1)), 4)
    out["games"] = []
    for first, strength in ((True, 1.0), (False, 0.9)):
        rng = np.random.default_rng(seed)
        results = {"win": 0, "draw": 0, "loss": 0}
        clean = 0
        for _ in range(games):
            game = own_game(policy.choose, solver, rng, strength, policy_first=first, opening=0)
            results[game["result"]] += 1
            clean += int(game["qualities"].count("blunder") == 0)
        out["games"].append({"policy_first": first, "strength": strength, "games": games, **results,
                             "blunder_free_games": round(clean / games, 4)})
        print(json.dumps(out["games"][-1]), file=sys.stderr, flush=True)
    solver.close()
    out["seconds"] = round(time.time() - began, 1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], *(int(v) for v in sys.argv[2:4]))
