"""Phase C teacher: compiled alpha-beta over simultaneous rounds with the Voronoi leaf.

A round is my move then the opponent's reply (the opponent answers knowing my move: the
pessimistic reading of simultaneous moves, as `bots.voronoi2` uses). `depth` rounds is 2 x depth
ply. Alpha-beta at every level (the Python bots prune only inside); the leaf is `fastbots._leaf`
(cells reached first, or room difference once walled apart). Deaths score -BIG/+BIG scaled by
how soon they come, so a lost position is delayed and a won one taken early.

`prior` (optional): a bonus added at the root to the move the brain prefers; expert iteration
and the hybrid player use it.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from .fastbots import DC, DR, INF, ORDER, _apply, _leaf, _undo
from .world import Arena

BIG = INF * 16


@njit  # no cache: a cached self-recursive function segfaults when reloaded (Numba)
def _ab(grid, n, heads, headings, seat, depth, alpha, beta, a, b, queue, ply):
    if depth == 0:
        return _leaf(grid, n, heads, seat, a, b, queue)
    um = np.empty(4, np.int64)
    ut = np.empty(4, np.int64)
    best = -BIG * 4
    for ai in range(3):
        if not _apply(grid, n, heads, headings, seat, ORDER[ai], um):
            value = -BIG + ply  # I crash: later is better
        else:
            worst = BIG * 4
            lo = alpha if alpha > best else best
            for ri in range(3):
                o = 1 - seat
                h = (headings[o] + ORDER[ri] - 1) % 4
                r, c = heads[o, 0] + DR[h], heads[o, 1] + DC[h]
                if r == heads[seat, 0] and c == heads[seat, 1]:
                    v = -BIG // 2 + ply  # head-on: both die
                elif not _apply(grid, n, heads, headings, o, ORDER[ri], ut):
                    v = BIG - ply  # they crash: sooner is better
                else:
                    hi = beta if beta < worst else worst
                    v = _ab(grid, n, heads, headings, seat, depth - 1, lo, hi, a, b, queue, ply + 1)
                    _undo(grid, heads, headings, o, ut)
                if v < worst:
                    worst = v
                if worst <= lo:
                    break
            value = worst
            _undo(grid, heads, headings, seat, um)
        if value > best:
            best = value
        if best >= beta:
            break
    return best


@njit
def _root(grid, n, heads, headings, seat, depth, prior_move, prior_bonus):
    a = np.empty(n * n, np.int64)
    b = np.empty(n * n, np.int64)
    queue = np.empty(n * n, np.int64)
    um = np.empty(4, np.int64)
    ut = np.empty(4, np.int64)
    values = np.full(3, -BIG * 8, np.int64)
    best_move, best_value = 1, -BIG * 8
    for ai in range(3):
        act = ORDER[ai]
        if not _apply(grid, n, heads, headings, seat, act, um):
            value = -BIG
        else:
            worst = BIG * 4
            for ri in range(3):
                o = 1 - seat
                h = (headings[o] + ORDER[ri] - 1) % 4
                r, c = heads[o, 0] + DR[h], heads[o, 1] + DC[h]
                if r == heads[seat, 0] and c == heads[seat, 1]:
                    v = -BIG // 2
                elif not _apply(grid, n, heads, headings, o, ORDER[ri], ut):
                    v = BIG
                else:
                    v = _ab(grid, n, heads, headings, seat, depth - 1, -BIG * 4, worst, a, b, queue, 1)
                    _undo(grid, heads, headings, o, ut)
                if v < worst:
                    worst = v
            value = worst
            _undo(grid, heads, headings, seat, um)
        if act == prior_move:
            value += prior_bonus
        values[act] = value
        if value > best_value:
            best_move, best_value = act, value
    return best_move, values


def _state(arena: Arena):
    return (np.array(arena.grid, np.int64), np.array(arena.heads, np.int64),
            np.array(arena.headings, np.int64))


def search(arena: Arena, seat: int, depth: int, prior_move: int = -1, prior_bonus: int = 0):
    g, h, d = _state(arena)
    move, values = _root(g, arena.size, h, d, seat, depth, prior_move, prior_bonus)
    return int(move), values


def ab_bot(depth: int):
    def play(arena: Arena, seat: int, draw=None) -> int:
        return search(arena, seat, depth)[0]
    play.__name__ = f"ab{depth}"
    return play
