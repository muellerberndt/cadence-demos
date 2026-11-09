"""Look-ahead in the brain's own imagination, judged by its own verdict slot.

For each legal column the brain pictures the board the opponent would face once the stone has
dropped (the game's mechanics place the stone; no rule judges the result) and reads its verdict
slot on that board, as the opponent: loss, draw or win for the side to move. The mover's value of
the column is the opponent's loss less the opponent's win; the brain plays the column of the
highest value, its own motor preference breaking ties. Every judgement is a settle of the brain.

``finished`` builds the boards a verdict has to read for this to see an immediate win: a won
position after the winning stone, from the loser's side (verdict: loss).
"""

from __future__ import annotations

import numpy as np

from .tactics import tactics


def after(x: np.ndarray, column: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The opponent's view after the mover drops a stone in ``column``: encodings (opponent's
    stones first), the opponent's legal columns, and which rows could take the column."""
    cells = np.asarray(x, float).reshape(-1, 2, 6, 7).copy()
    height = cells.any(axis=1).sum(axis=1)[:, column]
    rows = np.arange(len(cells))
    ok = height < 6
    cells[rows[ok], 0, height[ok], column] = 1.0
    swapped = cells[:, ::-1].reshape(-1, 84)
    legal = ~(swapped.reshape(-1, 2, 6, 7).any(axis=1)[:, 5, :])
    return swapped, legal, ok


def softmax_legal(z: np.ndarray, legal: np.ndarray) -> np.ndarray:
    z = np.where(legal, z, -np.inf)
    z = z - z.max(axis=1, keepdims=True)
    p = np.exp(z)
    return p / p.sum(axis=1, keepdims=True)


def values(policy, x: np.ndarray, legal: np.ndarray) -> np.ndarray:
    """``(rows, 7)``: the mover's value of each legal column as the brain imagines it."""
    out = np.full((len(x), 7), -np.inf)
    for c in range(7):
        xo, _, ok = after(x, c)
        take = ok & legal[:, c]
        if not take.any():
            continue
        seen = xo[take]
        p = np.concatenate([policy.verdict(seen[i:i + 512]) for i in range(0, len(seen), 512)])
        out[take, c] = p[:, 0] - p[:, 2]  # the opponent's loss less the opponent's win
    return out


def imagined(policy):
    """A chooser over boards: the brain's imagined values, its motor breaking ties."""
    def choose_x(x: np.ndarray, legal: np.ndarray) -> np.ndarray:
        v = values(policy, x, legal)
        motor = np.concatenate([policy.motor(x[i:i + 512]) for i in range(0, len(x), 512)])
        tie = softmax_legal(motor, legal)
        return np.where(legal, v + 1e-3 * tie, -np.inf).argmax(axis=1)

    def choose(boards) -> np.ndarray:
        x = np.stack([b.encode() for b in boards])
        return choose_x(x, np.stack([b.legal() for b in boards]))

    choose.choose_x = choose_x  # type: ignore[attr-defined]
    return choose


def hybrid(policy, sure: float = 0.8):
    """The brain's own move, overruled by its imagination only when the imagination is nearly
    sure: a column whose pictured board it judges lost for the opponent at ``sure`` or more is
    taken; its own column, if it judges that board won for the opponent at ``sure`` or more, is
    replaced by the column it judges best."""
    def choose_x(x: np.ndarray, legal: np.ndarray) -> np.ndarray:
        v = values(policy, x, legal)
        motor = np.concatenate([policy.motor(x[i:i + 512]) for i in range(0, len(x), 512)])
        own = np.where(legal, motor, -np.inf).argmax(axis=1)
        best = np.where(legal, v, -np.inf).argmax(axis=1)
        rows = np.arange(len(x))
        take = (v[rows, best] >= sure) | (v[rows, own] <= -sure)
        return np.where(take, best, own)

    def choose(boards) -> np.ndarray:
        x = np.stack([b.encode() for b in boards])
        return choose_x(x, np.stack([b.legal() for b in boards]))

    choose.choose_x = choose_x  # type: ignore[attr-defined]
    return choose


def finished(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Boards just won: for each row with a win available, the winning stone dropped (one
    winning column at random) and the board seen by the side that lost."""
    win, _ = tactics(x)
    rows = np.flatnonzero(win.any(axis=1))
    out = []
    for r in rows:
        column = int(rng.choice(np.flatnonzero(win[r])))
        xo, _, _ = after(x[r:r + 1], column)
        out.append(xo[0])
    return np.array(out).reshape(-1, 84)
