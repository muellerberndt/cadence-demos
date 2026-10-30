"""The cells of a run across processes: each worker owns some worlds and runs their physics,
teacher labels, senses and warm starts; the brain stays in the parent.

``CellPool`` forks the workers (fork them before the brain is built, so no numba thread pool is
inherited); ``LocalPool`` is the same interface in one process. Per decision the parent asks for
the observations and labels (``sense``), acts, then hands each cell its executed command
(``act``); a worker restarts a cell that placed its block or spent ``cap`` decisions on one job,
with the teacher driving the fresh job alone with probability ``chance`` for up to ``most``
decisions, as ``arm1.train.warm_start`` did.
"""

from __future__ import annotations

import multiprocessing as mp

import numpy as np

from . import teacher
from .actions import execute
from .scene import PandaWorld
from .senses import observe

COUNTS = ("jobs", "rights", "wrongs", "grasps", "drops")


class _Cells:
    """The worlds of one worker (or of the whole run, in ``LocalPool``)."""

    def __init__(self, seeds: list[int], physics: str, pools: str, velocity: bool, cap: int, slip: bool = False,
                 recover: bool = False) -> None:
        self.worlds = [PandaWorld(s, physics) for s in seeds]
        self.since = [0] * len(self.worlds)
        self.rng = np.random.default_rng(seeds[0] + 99)
        self.pools, self.velocity, self.cap, self.slip, self.recover = pools, velocity, cap, slip, recover

    def fresh(self, w: PandaWorld, chance: float, most: int) -> int:
        w.randomize()
        w.last_command = None
        driven = 0
        if chance and self.rng.random() < chance:
            for _ in range(int(self.rng.integers(0, most + 1))):
                event = execute(w, teacher.labels(w, self.pools, self.recover), self.pools)["event"] or ""
                driven += 1
                if event.startswith("placed"):
                    w.randomize()
                    w.last_command = None
                    break
        return driven

    def warm(self, chance: float, most: int) -> int:
        self.since = [0] * len(self.worlds)
        return sum(self.fresh(w, chance, most) for w in self.worlds)

    def sense(self) -> tuple[np.ndarray, np.ndarray]:
        x = np.stack([observe(w, self.pools, self.velocity, self.slip) for w in self.worlds])
        labels = np.array([teacher.labels(w, self.pools, self.recover) for w in self.worlds], dtype=np.int64)
        return x, labels

    def act(self, chosen: np.ndarray, chance: float, most: int) -> dict:
        """Execute each cell's command; the counts, and each cell's event (the live stage reads
        rewards from them: ``placed:<bin>:right``, ``...:wrong``, ``dropped``, ``slipped``)."""
        counts: dict = dict.fromkeys(COUNTS, 0)
        events = []
        for k, w in enumerate(self.worlds):
            event = execute(w, chosen[k], self.pools)["event"] or ""
            events.append(event)
            counts["grasps"] += event == "grasped"
            counts["drops"] += event in ("dropped", "slipped")
            self.since[k] += 1
            if event.startswith("placed") or self.since[k] >= self.cap:
                counts["jobs"] += 1
                counts["rights"] += event.endswith("right")
                counts["wrongs"] += event.endswith("wrong")
                self.fresh(w, chance, most)
                self.since[k] = 0
        counts["events"] = events
        return counts


def _serve(conn, seeds, physics, pools, velocity, cap, slip=False, recover=False) -> None:
    cells = _Cells(seeds, physics, pools, velocity, cap, slip, recover)
    while True:
        msg = conn.recv()
        if msg[0] == "warm":
            conn.send(cells.warm(msg[1], msg[2]))
        elif msg[0] == "sense":
            conn.send(cells.sense())
        elif msg[0] == "act":
            conn.send(cells.act(msg[1], msg[2], msg[3]))
        else:
            conn.close()
            return


class LocalPool:
    def __init__(self, cells: int, seed: int, physics: str, pools: str, velocity: bool, cap: int, slip: bool = False,
                 recover: bool = False) -> None:
        self.cells = _Cells([seed * 1000 + k for k in range(cells)], physics, pools, velocity, cap, slip, recover)
        self.workers = 0

    def warm(self, chance: float, most: int) -> int:
        return self.cells.warm(chance, most)

    def sense(self) -> tuple[np.ndarray, np.ndarray]:
        return self.cells.sense()

    def act(self, chosen: np.ndarray, chance: float, most: int) -> dict:
        return self.cells.act(np.asarray(chosen), chance, most)

    def close(self) -> None:
        pass


class CellPool:
    def __init__(self, cells: int, workers: int, seed: int, physics: str, pools: str, velocity: bool, cap: int,
                 slip: bool = False, recover: bool = False) -> None:
        ctx = mp.get_context("fork")
        self.parts = [p for p in np.array_split(np.arange(cells), min(workers, cells)) if len(p)]
        self.workers = len(self.parts)
        self.conns, self.procs = [], []
        for part in self.parts:
            parent, child = ctx.Pipe()
            proc = ctx.Process(target=_serve, args=(child, [seed * 1000 + int(k) for k in part], physics, pools, velocity, cap,
                                                    slip, recover), daemon=True)
            proc.start()
            self.conns.append(parent)
            self.procs.append(proc)

    def _ask(self, messages: list) -> list:
        for conn, msg in zip(self.conns, messages, strict=True):
            conn.send(msg)
        return [conn.recv() for conn in self.conns]

    def warm(self, chance: float, most: int) -> int:
        return int(sum(self._ask([("warm", chance, most)] * self.workers)))

    def sense(self) -> tuple[np.ndarray, np.ndarray]:
        parts = self._ask([("sense",)] * self.workers)
        return np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts])

    def act(self, chosen: np.ndarray, chance: float, most: int) -> dict:
        chosen = np.asarray(chosen)
        parts = self._ask([("act", chosen[part], chance, most) for part in self.parts])
        out: dict = {k: int(sum(p[k] for p in parts)) for k in COUNTS}
        out["events"] = [e for p in parts for e in p["events"]]
        return out

    def close(self) -> None:
        for conn in self.conns:
            try:
                conn.send(("close",))
            except (BrokenPipeError, OSError):
                pass
        for proc in self.procs:
            proc.join(timeout=5)
