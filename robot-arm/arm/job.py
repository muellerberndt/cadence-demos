"""The job stage: pick the block and place it in the ordered bin, learned in a continuing life.

    python -m arm.job --brain runs/n1-s1/brain.npz --out runs/j1-s1 --shown 300 --corrected 900 --alone 900

Phases, in one continuing stream of the raised brain: ``shown`` (the caregiver drives, the
brain watches and its memory records the demonstrations), ``corrected`` (the brain drives,
the caregiver labels the observation after an executed disagreement), ``alone`` (no labels).
Every phase is summarized: placements right and wrong, drops, agreement with the caregiver,
sweeps and milliseconds per decision. Twins read beside the life: the same brain with its
records erased before the alone phase, and a frozen copy answering greedily.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import numpy as np  # noqa: E402
from cadence import Brain  # noqa: E402

from .eyes import Eyes, HeadSpec  # noqa: E402
from .life import EYE, Life, summarize  # noqa: E402
from .world import ArmSpec, World, steps_of  # noqa: E402


def head_of(run: dict) -> HeadSpec:
    h = run["head"]
    return HeadSpec(size=h["size"], eyes=h["eyes"], baseline=h["baseline"], position=tuple(h["position"]),
                    target=tuple(h["target"]), fov=h["fov"], change=h["change"], colour=h.get("colour", False))


def frozen_life(path: Path, head: HeadSpec, seed: int, decisions: int) -> dict:
    """A copy answering greedily with no learning at all, on its own world seed."""
    brain = Brain.load(path)
    world, eyes = World(ArmSpec(), seed), Eyes(head)
    rows = []
    for _ in range(decisions):
        x = eyes.inputs(world)[None]
        try:
            answer = brain.act(x, greedy=True)[0]
        except RuntimeError:
            answer = None
        if answer is None:
            steps, close = np.zeros(4), int(world.closed)
        else:
            steps, close = steps_of(answer[EYE:EYE + 4]), int(answer[EYE + 4])
        out = world.decide(steps, close)
        rows.append({"own": None, "want": None, "event": out["event"], "reward": out["reward"], "taught": False,
                     "refused": answer is None, "sweeps": int((brain.last_settlement or {}).get("steps", 0)), "ms": 0.0})
    return summarize(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--brain", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--shown", type=int, default=300)
    p.add_argument("--corrected", type=int, default=900)
    p.add_argument("--alone", type=int, default=900)
    p.add_argument("--waits", type=int, default=0)
    p.add_argument("--continuation", default="step", choices=("step", "live"))
    p.add_argument("--no-done", dest="done_marks", action="store_false")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    run = json.loads((Path(a.brain).parent / "run.json").read_text())
    head = head_of(run)
    seed = run["seed"] if a.seed is None else a.seed
    world, eyes = World(ArmSpec(), 20_000 + seed), Eyes(head)
    brain = Brain.load(a.brain)
    brain.reset()
    life = Life(brain, world, eyes, waits=a.waits, continuation=a.continuation, done_marks=a.done_marks)
    report: dict = {"brain": str(a.brain), "seed": seed, "phases": {}}
    for phase, n in (("shown", a.shown), ("corrected", a.corrected)):
        rows = life.run(n, phase)
        report["phases"][phase] = summarize(rows)
        print(phase, json.dumps(report["phases"][phase]), flush=True)
    taught_path = brain.save(out / "brain-taught.npz")
    erased_world = copy.deepcopy(world)
    rows = life.run(a.alone, "alone")
    report["phases"]["alone"] = summarize(rows)
    print("alone", json.dumps(report["phases"]["alone"]), flush=True)
    brain.save(out / "brain-after.npz")
    # Twins from the taught brain on a copy of the world as it was at the end of teaching.
    erased = Brain.load(taught_path)
    erased.reset()
    erased.hippocampus.clear()
    if erased.context_memory is not None:
        erased.context_memory.clear()
    twin = Life(erased, erased_world, Eyes(head), waits=a.waits, continuation=a.continuation, done_marks=a.done_marks)
    report["phases"]["alone_erased_memory"] = summarize(twin.run(a.alone, "alone"))
    print("alone, memory erased", json.dumps(report["phases"]["alone_erased_memory"]), flush=True)
    report["phases"]["frozen"] = frozen_life(taught_path, head, 20_000 + seed, a.alone)
    print("frozen", json.dumps(report["phases"]["frozen"]), flush=True)
    (out / "log.json").write_text(json.dumps(life.log))
    (out / "report.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
