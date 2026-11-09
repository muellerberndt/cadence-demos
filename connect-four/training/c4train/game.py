"""Connect Four rules on a 6 x 7 board, row 0 at the bottom.

A ``Board`` keeps the stones of the side to move (``mine``) and of the other side (``theirs``)
as boolean 6 x 7 arrays, so every board is read from the mover's side; ``play`` returns the
board the opponent then faces.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ROWS, COLUMNS = 6, 7
CENTRE_ORDER = (3, 2, 4, 1, 5, 0, 6)


def _lines() -> np.ndarray:
    """Every four-in-a-row as four flat cell indices (69 lines)."""
    out = []
    for r in range(ROWS):
        for c in range(COLUMNS):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = [(r + k * dr, c + k * dc) for k in range(4)]
                if all(0 <= rr < ROWS and 0 <= cc < COLUMNS for rr, cc in cells):
                    out.append([rr * COLUMNS + cc for rr, cc in cells])
    return np.array(out)


LINES = _lines()


@dataclass(frozen=True)
class Board:
    mine: np.ndarray
    theirs: np.ndarray

    @staticmethod
    def empty() -> Board:
        return Board(np.zeros((ROWS, COLUMNS), bool), np.zeros((ROWS, COLUMNS), bool))

    @property
    def stones(self) -> int:
        return int(self.mine.sum() + self.theirs.sum())

    def heights(self) -> np.ndarray:
        return (self.mine | self.theirs).sum(axis=0)

    def legal(self) -> np.ndarray:
        return self.heights() < ROWS

    def play(self, column: int) -> Board:
        """The board after the mover drops a stone in ``column``, read by the opponent."""
        height = int(self.heights()[column])
        if height >= ROWS:
            raise ValueError(f"column {column} is full")
        mine = self.mine.copy()
        mine[height, column] = True
        return Board(self.theirs.copy(), mine)

    def winning(self, column: int) -> bool:
        """Whether dropping in ``column`` completes four for the mover."""
        height = int(self.heights()[column])
        if height >= ROWS:
            return False
        mine = self.mine.copy()
        mine[height, column] = True
        flat = mine.reshape(-1)
        return bool(flat[LINES].all(axis=1).any())

    def lost(self) -> bool:
        """Whether the side that just moved (``theirs``) has four in a row."""
        return bool(self.theirs.reshape(-1)[LINES].all(axis=1).any())

    def full(self) -> bool:
        return self.stones == ROWS * COLUMNS

    def line(self) -> str:
        """The solver's 42-character board: row-major from the bottom left, 'x' the mover."""
        cells = np.full((ROWS, COLUMNS), ".")
        cells[self.mine] = "x"
        cells[self.theirs] = "o"
        return "".join(cells.reshape(-1))

    def encode(self) -> np.ndarray:
        """84 inputs: the mover's stones, then the opponent's, row-major from the bottom."""
        return np.concatenate([self.mine.reshape(-1), self.theirs.reshape(-1)]).astype(float)

    def mirrored(self) -> Board:
        return Board(self.mine[:, ::-1].copy(), self.theirs[:, ::-1].copy())
