"""Seconds per batched decision of a brain on a device: act and lesson at several cell counts and
precisions, and the painting of the retinas with several worker pools.

    python -m arm091.speed --brain runs/c4_sur_best/brain_best.npz --device cuda:3
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import time
from pathlib import Path

import numpy as np
from cadence import Brain

from arm.eyes import Eyes
from arm.nursery import head_of, reach
from arm.world import ArmSpec, World

from .dagger import _render, _render_init
from .job import job_labels


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--brain", required=True)
    p.add_argument("--device", default="cuda:0")
    p.add_argument("--worlds", type=int, nargs="+", default=[64, 128, 256])
    p.add_argument("--pools", type=int, nargs="+", default=[6, 12, 20])
    p.add_argument("--reps", type=int, default=5)
    a = p.parse_args()
    head = head_of(json.loads((Path(a.brain).parent / "run.json").read_text()))
    out: dict = {"paint": {}, "brain": {}, "reach40": {}}
    for workers in a.pools:  # pools fork before any device is touched
        with multiprocessing.get_context("fork").Pool(workers, _render_init, (head,)) as pool:
            for b in a.worlds:
                worlds = [World(ArmSpec(), k) for k in range(b)]
                for w in worlds:
                    w.randomize(holding_rate=0.0)
                snaps = [w.snapshot() for w in worlds]
                pool.map(_render, snaps)
                t = time.perf_counter()
                for _ in range(a.reps):
                    pool.map(_render, snaps, chunksize=max(1, b // (2 * workers)))
                out["paint"][f"{workers}w_{b}"] = round((time.perf_counter() - t) / a.reps, 3)
    for precision in ("float64", "float32"):
        brain = Brain.load(a.brain, backend="torch", device=a.device, precision=precision)
        out["reach40"][precision] = reach(brain, World(ArmSpec(), 1), Eyes(head), 40, 10_002)
        for b in a.worlds:
            worlds = [World(ArmSpec(), k) for k in range(b)]
            eyes = [Eyes(head) for _ in range(b)]
            for w in worlds:
                w.randomize(holding_rate=0.0)
            x = np.stack([e.inputs(w) for w, e in zip(worlds, eyes, strict=True)])
            labels = np.array([job_labels(w, e) for w, e in zip(worlds, eyes, strict=True)], dtype=np.int64)
            brain.reset()
            brain.act(x, greedy=True)
            acts, lessons = [], []
            for _ in range(a.reps):
                t = time.perf_counter()
                drive = brain.stimulus(x)
                np.asarray(brain.act(x, greedy=True))
                t1 = time.perf_counter()
                brain.learner.step(drive, labels, warm=brain.basal_ganglia.state)
                lessons.append(time.perf_counter() - t1)
                acts.append(t1 - t)
            out["brain"][f"{precision}_{b}"] = {"act": round(float(np.median(acts)), 3),
                                                "lesson": round(float(np.median(lessons)), 3)}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
