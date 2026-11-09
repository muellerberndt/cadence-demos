"""Pascal Pons' perfect solver as the teacher and the grader.

``Solver.scores`` answers the exact score of every column for the side to move: positive when it
wins with perfect play (larger is sooner), negative when it loses, 0 a draw, ``INVALID`` for a
full column. The bridge (``training/bridge.cpp``) and the 7x6 opening book live in ``training/pons``
(``C4_PONS`` names another place); see the README. A disk cache keeps every answer across runs.
"""

from __future__ import annotations

import os
import pickle
import subprocess
from pathlib import Path

import numpy as np

from .game import CENTRE_ORDER, Board

INVALID = -1000
PONS = Path(os.environ.get("C4_PONS", Path(__file__).resolve().parents[1] / "pons"))
BRIDGE, BOOK = PONS / "c4bridge", PONS / "7x6.book"


class Solver:
    def __init__(self, cache: Path | None = None) -> None:
        if not BRIDGE.exists():
            raise FileNotFoundError(f"{BRIDGE}: build the bridge in {PONS}")
        args = [str(BRIDGE)] + ([str(BOOK)] if BOOK.exists() else [])
        self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.cache_path = cache
        self.cache: dict[str, tuple[int, ...]] = {}
        if cache is not None and Path(cache).exists():
            with open(cache, "rb") as handle:
                self.cache = pickle.load(handle)
        self.calls = 0

    def scores(self, board: Board) -> np.ndarray:
        line = board.line()
        hit = self.cache.get(line)
        if hit is None:
            assert self.process.stdin and self.process.stdout
            self.process.stdin.write(line + "\n")
            self.process.stdin.flush()
            answer = self.process.stdout.readline().split()
            if len(answer) != 8:
                raise RuntimeError(f"solver answered {answer!r} for {line}")
            hit = tuple(int(v) for v in answer[:7])
            self.cache[line] = hit
            self.calls += 1
        return np.array(hit)

    def save(self) -> None:
        if self.cache_path is not None:
            tmp = Path(f"{self.cache_path}.{os.getpid()}.tmp")  # one per process: runs share the cache
            with open(tmp, "wb") as handle:
                pickle.dump(self.cache, handle, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(self.cache_path)

    def close(self) -> None:
        self.save()
        if self.process.stdin:
            self.process.stdin.close()
        self.process.wait(timeout=5)


def optimal(scores: np.ndarray) -> np.ndarray:
    """The score-maximal playable columns."""
    playable = scores != INVALID
    return np.flatnonzero(playable & (scores == scores[playable].max()))


def label(scores: np.ndarray) -> int:
    """The centre-most optimal column: one deterministic answer per position."""
    best = set(optimal(scores).tolist())
    return next(c for c in CENTRE_ORDER if c in best)


def quality(scores: np.ndarray, column: int) -> str:
    """'optimal' (score-maximal), 'slip' (keeps the theoretical result) or 'blunder'."""
    best = int(scores[scores != INVALID].max())
    chosen = int(scores[column])
    if chosen == INVALID:
        return "illegal"
    if chosen == best:
        return "optimal"
    return "slip" if np.sign(chosen) == np.sign(best) else "blunder"
