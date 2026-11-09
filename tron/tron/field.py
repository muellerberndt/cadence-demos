"""The sense: the entire field at full resolution, in the rider's frame, plus the fovea.

`field` turns the whole arena so the rider's heading points up (the frame turns with the cycle;
a board in the compass frame did not learn) and shows every cell, four
channels: blocked (walls and every trail), the opponent's trail, the rider's head, the
opponent's head. On top sits a fovea (9 x 9 cells around the head, blocked and the
opponent's head), which gives the near cells in a translation-free frame, and the opponent's
heading relative to the rider's (same, right, opposite, left).

    inputs = 4 * n * n + 2 * 81 + 4   (2,470 on the 24 x 24 arena)

`field_lite` drops the opponent-trail channel and the fovea: 3 * n * n + 4 (1,732).
"""

from __future__ import annotations

import numpy as np

from .world import Arena

FOVEA = 9


def _rotate(a: np.ndarray, heading: int) -> np.ndarray:
    # heading 0 north is already "up"; east must turn a quarter counter-clockwise, and so on.
    return np.rot90(a, k=heading)


def _planes(arena: Arena, seat: int):
    n = arena.size
    g = np.asarray(arena.grid, dtype=np.int8).reshape(n, n)
    blocked = (g != 0).astype(np.float64)
    theirs = (g == 2 - seat).astype(np.float64)
    me = np.zeros((n, n))
    me[arena.heads[seat]] = 1.0
    op = np.zeros((n, n))
    op[arena.heads[1 - seat]] = 1.0
    return blocked, theirs, me, op


def _fovea(blocked: np.ndarray, me_rc: tuple[int, int], op_rc: tuple[int, int]) -> np.ndarray:
    """9 x 9 around the head in the turned frame: forward -3..+5 (up is forward), side -4..+4."""
    n = blocked.shape[0]
    pad = np.ones((n + 2 * FOVEA, n + 2 * FOVEA))
    pad[FOVEA:FOVEA + n, FOVEA:FOVEA + n] = blocked
    r, c = me_rc[0] + FOVEA, me_rc[1] + FOVEA
    win = pad[r - 5:r + 4, c - 4:c + 5]  # rows: 5 ahead (up) to 3 behind
    head = np.zeros((9, 9))
    dr, dc = op_rc[0] - me_rc[0] + 5, op_rc[1] - me_rc[1] + 4
    if 0 <= dr < 9 and 0 <= dc < 9:
        head[dr, dc] = 1.0
    return np.concatenate([win.ravel(), head.ravel()])


def _heading(arena: Arena, seat: int) -> np.ndarray:
    rel = (arena.headings[1 - seat] - arena.headings[seat]) % 4
    out = np.zeros(4)
    out[rel] = 1.0
    return out


def field(arena: Arena, seat: int) -> np.ndarray:
    h = arena.headings[seat]
    planes = [_rotate(p, h) for p in _planes(arena, seat)]
    me_rc = tuple(int(v) for v in np.argwhere(planes[2])[0])
    op_rc = tuple(int(v) for v in np.argwhere(planes[3])[0])
    return np.concatenate([p.ravel() for p in planes] + [_fovea(planes[0], me_rc, op_rc), _heading(arena, seat)])


def field_lite(arena: Arena, seat: int) -> np.ndarray:
    h = arena.headings[seat]
    b, _, me, op = (_rotate(p, h) for p in _planes(arena, seat))
    return np.concatenate([b.ravel(), me.ravel(), op.ravel(), _heading(arena, seat)])


def field_size(n: int = 24) -> int:
    return 4 * n * n + 2 * FOVEA * FOVEA + 4


def field_lite_size(n: int = 24) -> int:
    return 3 * n * n + 4


def _ownership(arena: Arena, seat: int):
    """Voronoi ownership: free cells the rider reaches strictly first, and those the opponent does."""
    from .fastbots import _dist

    n = arena.size
    g = np.asarray(arena.grid, dtype=np.int64)
    a, b, q = np.empty(n * n, np.int64), np.empty(n * n, np.int64), np.empty(n * n, np.int64)
    _dist(g, n, arena.heads[seat][0], arena.heads[seat][1], a, q)
    _dist(g, n, arena.heads[1 - seat][0], arena.heads[1 - seat][1], b, q)
    free = g == 0
    mine = (free & (a < b)).astype(np.float64).reshape(n, n)
    theirs = (free & (b < a)).astype(np.float64).reshape(n, n)
    return mine, theirs


def field_vor(arena: Arena, seat: int) -> np.ndarray:
    """`field` plus two turned Voronoi-ownership planes (the territory arm of scripts/phasec.py)."""
    h = arena.headings[seat]
    mine, theirs = _ownership(arena, seat)
    return np.concatenate([field(arena, seat), _rotate(mine, h).ravel(), _rotate(theirs, h).ravel()])


def field_vor_size(n: int = 24) -> int:
    return field_size(n) + 2 * n * n


SENSES3 = {"field": (field, field_size), "field_lite": (field_lite, field_lite_size),
           "field_vor": (field_vor, field_vor_size)}


def make_sense3(name: str, n: int = 24):
    fn, size = SENSES3[name]
    return fn, size(n)
