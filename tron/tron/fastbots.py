"""`bots.voronoi2` / `bots.voronoi3` compiled with Numba: the same search, the same moves.

The pure-Python three-round search costs about 150 ms per position on one c7i core, which made
the school label-bound. This is a line-for-line port (no recursion: one function per depth);
`tests/test_fastbots.py` checks it returns the Python bot's move on held-out positions.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from .world import Arena

INF = 1 << 20
DR = np.array([-1, 0, 1, 0], np.int64)
DC = np.array([0, 1, 0, -1], np.int64)
ORDER = np.array([1, 0, 2], np.int64)


@njit(cache=True)
def _dist(grid, n, r0, c0, out, queue):
    for i in range(n * n):
        out[i] = INF
    out[r0 * n + c0] = 0
    head, tail = 0, 0
    queue[tail] = r0 * n + c0
    tail += 1
    while head < tail:
        i = queue[head]
        head += 1
        r, c = i // n, i % n
        d = out[i] + 1
        for k in range(4):
            rr, cc = r + DR[k], c + DC[k]
            if 0 <= rr < n and 0 <= cc < n:
                j = rr * n + cc
                if grid[j] == 0 and out[j] == INF:
                    out[j] = d
                    queue[tail] = j
                    tail += 1


@njit(cache=True)
def _leaf(grid, n, heads, seat, a, b, queue):
    mr, mc = heads[seat, 0], heads[seat, 1]
    tr, tc = heads[1 - seat, 0], heads[1 - seat, 1]
    _dist(grid, n, mr, mc, a, queue)
    _dist(grid, n, tr, tc, b, queue)
    shared = False
    for k in range(4):
        rr, cc = tr + DR[k], tc + DC[k]
        if 0 <= rr < n and 0 <= cc < n and a[rr * n + cc] < INF:
            shared = True
            break
    if shared:
        score = 0
        for i in range(n * n):
            if a[i] < b[i]:
                score += 1
            elif b[i] < a[i]:
                score -= 1
        return 4 * score
    mine = 0
    theirs = 0
    for i in range(n * n):
        if 0 < a[i] < INF:
            mine += 1
        if 0 < b[i] < INF:
            theirs += 1
    free = 0
    for k in range(4):
        rr, cc = mr + DR[k], mc + DC[k]
        if 0 <= rr < n and 0 <= cc < n and grid[rr * n + cc] == 0:
            free += 1
    return 4 * (mine - theirs) - free


@njit(cache=True)
def _apply(grid, n, heads, headings, seat, action, undo):
    """Move one cycle; returns False if it dies. undo: (head r, head c, heading, index)."""
    h = (headings[seat] + action - 1) % 4
    r, c = heads[seat, 0] + DR[h], heads[seat, 1] + DC[h]
    if not (0 <= r < n and 0 <= c < n) or grid[r * n + c] != 0:
        return False
    undo[0], undo[1], undo[2], undo[3] = heads[seat, 0], heads[seat, 1], headings[seat], r * n + c
    grid[r * n + c] = 1 + seat
    heads[seat, 0], heads[seat, 1] = r, c
    headings[seat] = h
    return True


@njit(cache=True)
def _undo(grid, heads, headings, seat, undo):
    grid[undo[3]] = 0
    heads[seat, 0], heads[seat, 1] = undo[0], undo[1]
    headings[seat] = undo[2]


@njit(cache=True)
def _round(grid, n, heads, headings, seat, depth, a, b, queue):
    """Max over my moves, min over their replies, with the Python bot's pruning."""
    best = -INF * 4
    um = np.empty(4, np.int64)
    ut = np.empty(4, np.int64)
    for ai in range(3):
        if not _apply(grid, n, heads, headings, seat, ORDER[ai], um):
            value = -INF * 2
        else:
            worst = INF * 4
            for ri in range(3):
                o = 1 - seat
                h = (headings[o] + ORDER[ri] - 1) % 4
                r, c = heads[o, 0] + DR[h], heads[o, 1] + DC[h]
                if r == heads[seat, 0] and c == heads[seat, 1]:
                    v = -INF
                elif not _apply(grid, n, heads, headings, o, ORDER[ri], ut):
                    v = INF
                else:
                    if depth == 1:
                        v = _leaf(grid, n, heads, seat, a, b, queue)
                    else:
                        v = _round2(grid, n, heads, headings, seat, depth - 1, a, b, queue)
                    _undo(grid, heads, headings, o, ut)
                if v < worst:
                    worst = v
                if worst <= best:
                    break
            value = worst
            _undo(grid, heads, headings, seat, um)
        if value > best:
            best = value
    return best


@njit(cache=True)
def _round2(grid, n, heads, headings, seat, depth, a, b, queue):
    # Depth 1 only (voronoi3 needs two nested rounds below the top): a copy of _round that
    # never descends further, so Numba sees no recursion.
    best = -INF * 4
    um = np.empty(4, np.int64)
    ut = np.empty(4, np.int64)
    for ai in range(3):
        if not _apply(grid, n, heads, headings, seat, ORDER[ai], um):
            value = -INF * 2
        else:
            worst = INF * 4
            for ri in range(3):
                o = 1 - seat
                h = (headings[o] + ORDER[ri] - 1) % 4
                r, c = heads[o, 0] + DR[h], heads[o, 1] + DC[h]
                if r == heads[seat, 0] and c == heads[seat, 1]:
                    v = -INF
                elif not _apply(grid, n, heads, headings, o, ORDER[ri], ut):
                    v = INF
                else:
                    v = _leaf(grid, n, heads, seat, a, b, queue)
                    _undo(grid, heads, headings, o, ut)
                if v < worst:
                    worst = v
                if worst <= best:
                    break
            value = worst
            _undo(grid, heads, headings, seat, um)
        if value > best:
            best = value
    return best


@njit(cache=True)
def _top(grid, n, heads, headings, seat, depth):
    a = np.empty(n * n, np.int64)
    b = np.empty(n * n, np.int64)
    queue = np.empty(n * n, np.int64)
    um = np.empty(4, np.int64)
    ut = np.empty(4, np.int64)
    best, best_value = 1, -INF * 8
    for ai in range(3):
        if not _apply(grid, n, heads, headings, seat, ORDER[ai], um):
            value = -INF * 3
        else:
            worst = INF * 4
            for ri in range(3):
                o = 1 - seat
                h = (headings[o] + ORDER[ri] - 1) % 4
                r, c = heads[o, 0] + DR[h], heads[o, 1] + DC[h]
                if r == heads[seat, 0] and c == heads[seat, 1]:
                    v = -INF
                elif not _apply(grid, n, heads, headings, o, ORDER[ri], ut):
                    v = INF
                else:
                    v = _round(grid, n, heads, headings, seat, depth - 1, a, b, queue)
                    _undo(grid, heads, headings, o, ut)
                if v < worst:
                    worst = v
            value = worst
            _undo(grid, heads, headings, seat, um)
        if value > best_value:
            best, best_value = ORDER[ai], value
    return best


def _state(arena: Arena):
    return (np.array(arena.grid, np.int64), np.array(arena.heads, np.int64),
            np.array(arena.headings, np.int64))


def voronoi2(arena: Arena, seat: int, draw=None) -> int:
    g, h, d = _state(arena)
    return int(_top(g, arena.size, h, d, seat, 2))


def voronoi3(arena: Arena, seat: int, draw=None) -> int:
    g, h, d = _state(arena)
    return int(_top(g, arena.size, h, d, seat, 3))
