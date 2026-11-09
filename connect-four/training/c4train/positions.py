"""Where the positions come from, each labelled by the solver.

``noisy_game`` plays the solver against itself at a given strength from a short random opening:
the positions of games that are played well, with mistakes. ``own_game`` lets a policy play
against such a solver: the positions the policy itself reaches, the ones a recorded game never
shows (the own-path recipe). Every position carries its seven column scores, so a lesson can take
the centre-most optimal column and a reading can grade any answer.
"""

from __future__ import annotations

import numpy as np

from .game import Board
from .solver import INVALID, Solver, optimal


def solver_move(solver: Solver, board: Board, rng: np.random.Generator, strength: float) -> int:
    legal = np.flatnonzero(board.legal())
    if rng.random() >= strength:
        return int(rng.choice(legal))
    return int(rng.choice(optimal(solver.scores(board))))


def noisy_game(solver: Solver, rng: np.random.Generator, strength: float,
               opening: int = 4) -> list[tuple[Board, np.ndarray]]:
    """The non-terminal positions of one game of the solver against itself."""
    board, out = Board.empty(), []
    for ply in range(42):
        if board.full():
            break
        scores = solver.scores(board)
        out.append((board, scores))
        if ply < opening:
            column = int(rng.choice(np.flatnonzero(board.legal())))
        else:
            column = solver_move(solver, board, rng, strength)
        if board.winning(column):
            break
        board = board.play(column)
    return out


def own_game(choose, solver: Solver, rng: np.random.Generator, strength: float,
             policy_first: bool, opening: int = 2) -> dict:
    """One game of ``choose(boards) -> columns`` against the solver at ``strength``. Returns the
    positions the policy faced (with scores), its move qualities and the result for the policy."""
    board, faced, qualities = Board.empty(), [], []
    policy_turn = policy_first
    result = "draw"
    for ply in range(42):
        if board.full():
            break
        if ply < opening:
            column = int(rng.choice(np.flatnonzero(board.legal())))
        elif policy_turn:
            scores = solver.scores(board)
            column = int(choose([board])[0])
            faced.append((board, scores))
            best = int(scores[scores != INVALID].max())
            chosen = int(scores[column])
            qualities.append("optimal" if chosen == best else
                             ("slip" if np.sign(chosen) == np.sign(best) else "blunder"))
        else:
            column = solver_move(solver, board, rng, strength)
        if board.winning(column):
            result = "win" if policy_turn else "loss"
            break
        board = board.play(column)
        policy_turn = not policy_turn
    return {"faced": faced, "qualities": qualities, "result": result}


def arrays(items: list[tuple[Board, np.ndarray]], mirror: bool = True) -> tuple[np.ndarray, ...]:
    """Inputs, column scores and stone counts; with ``mirror`` each position twice, reflected."""
    boards, scores = [], []
    for board, s in items:
        boards.append(board)
        scores.append(s)
        if mirror:
            boards.append(board.mirrored())
            scores.append(np.asarray(s)[::-1])
    x = np.stack([b.encode() for b in boards])
    legal = np.stack([b.legal() for b in boards])
    stones = np.array([b.stones for b in boards])
    return x, np.stack(scores), legal, stones
