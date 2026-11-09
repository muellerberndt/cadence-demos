"""Readings of a Connect Four policy against the perfect solver.

``Heldout`` is a fixed set of positions from games of the solver against itself at strengths
.5 to 1.0 (seeded apart from the teaching positions): the share of answers that are optimal, of
slips (a worse column that keeps the theoretical result) and of blunders (the result changes),
over all positions and per game phase. ``games`` plays full games against the solver from short
random openings and counts results and blunder-free games: a near-perfect player keeps the
theoretical result of every start.
"""

from __future__ import annotations

import numpy as np

from .positions import arrays, noisy_game, own_game
from .solver import INVALID, Solver

PHASES = {"opening (0-8 stones)": (0, 9), "early middle (9-16)": (9, 17),
          "late middle (17-24)": (17, 25), "end (25-42)": (25, 43)}


class Heldout:
    def __init__(self, solver: Solver, count: int = 3000, seed: int = 900_001) -> None:
        rng = np.random.default_rng(seed)
        items = []
        while len(items) < count:
            items += noisy_game(solver, rng, strength=float(rng.uniform(0.5, 1.0)))
        self.x, self.scores, self.legal, self.stones = arrays(items[:count], mirror=False)

    def read(self, policy) -> dict:
        chosen = np.concatenate([policy.choose_x(self.x[i:i + 512], self.legal[i:i + 512])
                                 for i in range(0, len(self.x), 512)])
        s = self.scores
        playable = np.where(s == INVALID, -10_000, s)
        best = playable.max(axis=1)
        got = s[np.arange(len(s)), chosen]
        optimal = got == best
        blunder = np.sign(got) != np.sign(best)
        out = {"optimal": float(optimal.mean()), "blunder": float(blunder.mean()),
               "blunder_not_lost": float(blunder[best >= 0].mean()), "illegal": float((got == INVALID).mean())}
        for name, (lo, hi) in PHASES.items():
            m = (self.stones >= lo) & (self.stones < hi)
            if m.any():
                out[name] = {"optimal": round(float(optimal[m].mean()), 4),
                             "blunder": round(float(blunder[m].mean()), 4), "n": int(m.sum())}
        return out


def checked(policy):
    """The policy behind a 2-ply rules check: take a winning column if there is one, else avoid
    columns after which the opponent wins at once, else the policy's own choice. The check uses
    the game's rules, not the brain; readings report it separately from the brain alone."""
    def choose(boards):
        out = []
        for board in boards:
            legal = np.flatnonzero(board.legal())
            wins = [c for c in legal if board.winning(int(c))]
            if wins:
                out.append(int(wins[0]))
                continue
            safe = [c for c in legal
                    if not any(board.play(int(c)).winning(int(r)) for r in np.flatnonzero(board.play(int(c)).legal()))]
            x = board.encode()[None, :]
            mask = np.zeros((1, 7), bool)
            mask[0, safe if safe else legal] = True
            out.append(int(policy.choose_x(x, mask)[0]))
        return np.array(out)
    return choose


def games(policy, solver: Solver, count: int, strength: float, seed: int, lookahead: bool = False) -> dict:
    """``count`` games against the solver at ``strength``, half with the policy first; with
    ``lookahead`` the policy plays behind the 2-ply rules check."""
    rng = np.random.default_rng(seed)
    choose = checked(policy) if lookahead else policy.choose
    results = {"win": 0, "draw": 0, "loss": 0}
    clean, moves, blunders = 0, 0, 0
    for g in range(count):
        game = own_game(choose, solver, rng, strength, policy_first=bool(g % 2 == 0))
        results[game["result"]] += 1
        moves += len(game["qualities"])
        b = game["qualities"].count("blunder")
        blunders += b
        clean += int(b == 0)
    return {"strength": strength, "lookahead": lookahead, "games": count, **results, "blunder_free_games": clean / count,
            "blunder_rate": blunders / max(moves, 1)}
