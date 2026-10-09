"""One worker process per robot brain, so a fight's brains settle in parallel.

The world lives in the main process. Each moment it sends every worker its robot's
observation and the outcome of the previous command, and collects the commands. ``workers=0``
keeps every brain in the main process (tests and single robots). Workers are spawned, so the
module must be importable: run the arena as ``python -m arena``.
"""

from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
from typing import Any

import numpy as np

from .brain import make_policy
from .parts import Blueprint, blueprint_from_dict


def _serve(conn: Any, threads: int) -> None:
    os.environ.setdefault("OMP_NUM_THREADS", str(threads))
    os.environ.setdefault("OPENBLAS_NUM_THREADS", str(threads))
    policies: dict[str, Any] = {}
    while True:
        message = conn.recv()
        kind = message[0]
        if kind == "add":
            _, name, blueprint, policy, path, need, reset, stage = message
            policies[name] = make_policy(blueprint_from_dict(blueprint), policy, path, need=need, reset=reset, stage=stage)
            conn.send(name)
        elif kind == "moment":
            out = []
            for name, observation, reward, done in message[1]:
                out.append((name, policies[name].moment(np.asarray(observation), reward, done)))
            conn.send(out)
        elif kind == "save":
            _, name, path = message
            policies[name].save(path)
            conn.send(name)
        elif kind == "describe":
            conn.send({name: p.describe() for name, p in policies.items()})
        elif kind == "close":
            conn.send(None)
            return


class BrainPool:
    """Policies by robot name, each living in a worker (round-robin) or in process."""

    def __init__(self, workers: int = 0, threads: int = 1) -> None:
        self.workers = int(workers)
        self.local: dict[str, Any] = {}
        self.owner: dict[str, int] = {}
        self.conns: list[Any] = []
        self.procs: list[Any] = []
        self._next = 0
        if self.workers:
            ctx = mp.get_context("spawn")
            for _ in range(self.workers):
                parent, child = ctx.Pipe()
                proc = ctx.Process(target=_serve, args=(child, threads), daemon=True)
                proc.start()
                self.conns.append(parent)
                self.procs.append(proc)

    def add(
        self, name: str, blueprint: Blueprint, policy: str = "brain", path: str | Path | None = None,
        need: float | None = None, reset: bool = False, stage: dict | None = None,
    ) -> None:
        if not self.workers:
            self.local[name] = make_policy(blueprint, policy, path, need=need, reset=reset, stage=stage)
            return
        w = self._next % self.workers
        self._next += 1
        self.owner[name] = w
        self.conns[w].send(("add", name, blueprint.to_dict(), policy, None if path is None else str(path), need, reset, stage))
        self.conns[w].recv()

    def moment(self, rows: list[tuple[str, np.ndarray, float | None, bool]]) -> dict[str, dict]:
        if not self.workers:
            return {
                name: self.local[name].moment(np.asarray(obs), reward, done)
                for name, obs, reward, done in rows
            }
        buckets: list[list] = [[] for _ in self.conns]
        for name, obs, reward, done in rows:
            buckets[self.owner[name]].append((name, np.asarray(obs), reward, done))
        for w, bucket in enumerate(buckets):
            if bucket:
                self.conns[w].send(("moment", bucket))
        out: dict[str, dict] = {}
        for w, bucket in enumerate(buckets):
            if bucket:
                for name, reading in self.conns[w].recv():
                    out[name] = reading
        return out

    def save(self, name: str, path: str | Path) -> None:
        if not self.workers:
            self.local[name].save(path)
            return
        w = self.owner[name]
        self.conns[w].send(("save", name, str(path)))
        self.conns[w].recv()

    def describe(self) -> dict[str, dict]:
        if not self.workers:
            return {name: p.describe() for name, p in self.local.items()}
        out: dict[str, dict] = {}
        for conn in self.conns:
            conn.send(("describe",))
        for conn in self.conns:
            out.update(conn.recv())
        return out

    def close(self) -> None:
        for conn in self.conns:
            try:
                conn.send(("close",))
                conn.recv()
            except (EOFError, BrokenPipeError, OSError):
                pass
        for proc in self.procs:
            proc.join(timeout=5)
        self.conns, self.procs = [], []

    def __enter__(self) -> BrainPool:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
