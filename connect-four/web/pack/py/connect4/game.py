"""Connect Four on a 6 x 7 board, row 0 at the bottom.

A ``Board`` holds the stones of the side to move (``mine``) and of the other side
(``theirs``) as boolean 6 x 7 arrays, so every board is read from the mover's side.
``play`` returns the board the opponent then faces. Cells are numbered row-major from
the bottom left: cell ``r * 7 + c``, with ``r = 0`` the bottom row.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

ROWS, COLUMNS = 6, 7
CELLS = ROWS * COLUMNS


def _lines() -> np.ndarray:
    """Every four-in-a-row as four cell indices (69 lines)."""
    out = []
    for r in range(ROWS):
        for c in range(COLUMNS):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = [(r + k * dr, c + k * dc) for k in range(4)]
                if all(0 <= rr < ROWS and 0 <= cc < COLUMNS for rr, cc in cells):
                    out.append([rr * COLUMNS + cc for rr, cc in cells])
    return np.array(out, dtype=np.int64)


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
        """One flag per column: whether it still has room."""
        return self.heights() < ROWS

    def play(self, column: int) -> Board:
        """The board after the mover drops a stone in ``column``, read by the opponent."""
        if not 0 <= int(column) < COLUMNS:
            raise ValueError(f"column {column} is not on the board")
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
        return bool(mine.reshape(-1)[LINES].all(axis=1).any())

    def lost(self) -> bool:
        """Whether the side that just moved (``theirs``) has four in a row."""
        return bool(self.theirs.reshape(-1)[LINES].all(axis=1).any())

    def full(self) -> bool:
        return self.stones == CELLS

    def playable(self) -> np.ndarray:
        """6 x 7 flags: the cell where a stone dropped in each column with room would land."""
        cells = np.zeros((ROWS, COLUMNS), bool)
        heights = self.heights()
        for c in np.flatnonzero(heights < ROWS):
            cells[heights[c], c] = True
        return cells

    def encode(self, planes: int = 3) -> np.ndarray:
        """Inputs in {0, 1}, row-major from the bottom left: the mover's 42 cells, then the
        opponent's 42, then (``planes=3``) the 42 playable cells. 126 inputs, or 84 with two."""
        parts = [self.mine.reshape(-1), self.theirs.reshape(-1)]
        if planes == 3:
            parts.append(self.playable().reshape(-1))
        elif planes != 2:
            raise ValueError("planes is 2 or 3")
        return np.concatenate(parts).astype(float)

    def mirrored(self) -> Board:
        return Board(self.mine[:, ::-1].copy(), self.theirs[:, ::-1].copy())


@dataclass(frozen=True)
class Game:
    """A game replayed from its columns; player 0 moved first."""

    moves: tuple[int, ...]
    board: Board  # read by the side to move
    cells: tuple[int, ...]  # 42 cells: 0 empty, 1 player 0's stone, 2 player 1's stone
    winner: int | None  # the player with four in a row
    line: tuple[int, ...]  # the cells of that four, else empty

    @property
    def to_move(self) -> int:
        return len(self.moves) % 2

    @property
    def over(self) -> bool:
        return self.winner is not None or self.board.full()

    def summary(self) -> dict:
        legal = [] if self.over else [bool(v) for v in self.board.legal()]
        return {
            "moves": list(self.moves),
            "cells": list(self.cells),
            "to_move": self.to_move,
            "legal": legal,
            "winner": self.winner,
            "draw": self.winner is None and self.board.full(),
            "over": self.over,
            "line": list(self.line),
        }


def replay(moves: Sequence[int]) -> Game:
    """Replay ``moves`` from the empty board; refuse an illegal move or a move after the end."""
    board = Board.empty()
    cells = [0] * CELLS
    played: list[int] = []
    for ply, raw in enumerate(moves):
        column = int(raw)
        if board.full() or board.lost():
            raise ValueError("the game is already over")
        if not 0 <= column < COLUMNS or not board.legal()[column]:
            raise ValueError(f"illegal move {raw!r} at ply {ply}")
        cells[int(board.heights()[column]) * COLUMNS + column] = ply % 2 + 1
        board = board.play(column)
        played.append(column)
    winner, line = None, ()
    if board.lost():
        winner = (len(played) - 1) % 2
        stones = board.theirs.reshape(-1)
        fours = LINES[stones[LINES].all(axis=1)]
        line = tuple(sorted({int(c) for four in fours for c in four}))
    return Game(tuple(played), board, tuple(cells), winner, line)
