"""The teacher's games, computed once and replayed through any sense.

A corpus game is the arena seed, the opponent's name and both cycles' moves. The teacher rides
seat 0; replaying the moves reproduces every arena exactly, so a candidate with any sense
watches the same games, and the costly look-ahead runs once.
"""

from __future__ import annotations

import json
from multiprocessing import Pool
from pathlib import Path

from . import school
from .world import Arena, mulberry32

OPPONENTS = ("voronoi20", "survivor", "chaser", "hugger", "racer", "voronoi", "voronoi40", "safe")


def _teacher(name: str):
    """The look-ahead bots through their Numba ports (identical moves, tests/test_fastbots.py)."""
    if name in ("voronoi2", "voronoi3"):
        from . import fastbots
        bot = getattr(fastbots, name)
        return lambda arena, seat, draw: bot(arena, seat)
    return school.POOL[name]


def play(args):
    index, teacher, seed = args
    arena = Arena(24, seed=seed)
    draw = mulberry32(seed)
    opponent = OPPONENTS[index % len(OPPONENTS)]
    teach = _teacher(teacher)
    moves = []
    while not arena.over:
        a = teach(arena, 0, draw)
        b = school.POOL[opponent](arena, 1, draw)
        moves.append((a, b))
        arena.step((a, b))
    return {"index": index, "seed": seed, "opponent": opponent, "moves": moves, "winner": arena.winner}


def build(path: Path, games: int, teacher: str = "voronoi3", seed: int = 1_000_000, workers: int = 90):
    jobs = [(i, teacher, seed + i) for i in range(games)]
    if workers <= 1:
        rows = [play(j) for j in jobs]
    else:
        with Pool(workers) as pool:
            rows = pool.map(play, jobs, chunksize=1)
    rows.sort(key=lambda r: r["index"])
    path.write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n")
    return {"games": len(rows), "moments": sum(len(r["moves"]) for r in rows),
            "teacher_wins": sum(r["winner"] == 0 for r in rows)}


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


class Replay:
    """One stream of corpus games, moment by moment."""

    def __init__(self, games: list[dict], start: int, step: int):
        self.games, self.index, self.step = games, start, step
        self._open()

    def _open(self):
        g = self.games[self.index % len(self.games)]
        self.arena = Arena(24, seed=g["seed"])
        self.moves = g["moves"]
        self.t = 0

    def teacher_move(self) -> int:
        return self.moves[self.t][0]

    def advance(self) -> None:
        self.arena.step(self.moves[self.t])
        self.t += 1
        if self.arena.over:
            self.index += self.step
            self._open()
