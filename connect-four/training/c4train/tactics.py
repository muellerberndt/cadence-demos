"""Immediate tactics of many positions at once: where the mover wins now, and where it must
block a win the opponent has next move. Inputs are the 84-cell encodings (mover's stones first,
row-major from the bottom left)."""

from __future__ import annotations

import numpy as np

from .game import COLUMNS, LINES, ROWS


def tactics(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``(win, block)``, each ``(n, 7)`` boolean: the columns that win now, and the columns that
    stop the opponent's win next move (only where the mover has no win of its own)."""
    cells = np.asarray(x).reshape(-1, 2, ROWS * COLUMNS) > 0.5
    mine, theirs = cells[:, 0], cells[:, 1]
    occupied = mine | theirs
    heights = occupied.reshape(-1, ROWS, COLUMNS).sum(axis=1)  # (n, 7)
    landing = np.zeros_like(occupied)
    rows, cols = np.nonzero(heights < ROWS)
    landing[rows, heights[rows, cols] * COLUMNS + cols] = True

    def completes(side: np.ndarray) -> np.ndarray:
        on, empty = side[:, LINES], ~occupied[:, LINES]  # (n, 69, 4)
        ready = (on.sum(axis=2) == 3) & (empty.sum(axis=2) == 1)
        hole = np.take_along_axis(np.broadcast_to(LINES, on.shape), empty.argmax(axis=2)[..., None], axis=2)[..., 0]
        ok = ready & np.take_along_axis(landing, hole, axis=1)
        out = np.zeros((len(side), COLUMNS), dtype=bool)
        n_idx, l_idx = np.nonzero(ok)
        out[n_idx, hole[n_idx, l_idx] % COLUMNS] = True
        return out

    win = completes(mine)
    block = completes(theirs) & ~win.any(axis=1, keepdims=True)
    return win, block
