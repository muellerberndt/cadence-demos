"""Where a brain loses the reach: per decision of brain-alone trials, the fingertip's distance
to the hover point and whether each joint's command matches the caregiver's at that state.

    python -m arm091.diagnose --brain runs/n10-xent/brain.npz --trials 20
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from cadence import Brain

from arm import caregiver
from arm.anatomy import EYE_SLOTS
from arm.eyes import Eyes
from arm.nursery import answer_of, head_of
from arm.world import ArmSpec, World, steps_of

from . import teacher

BANDS = (0.025, 0.05, 0.10, 0.20, 10.0)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--brain", required=True)
    p.add_argument("--trials", type=int, default=20)
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--seed", type=int, default=10_002)
    p.add_argument("--teacher", choices=("gradient", "joint"), default="joint")
    a = p.parse_args()
    run = json.loads((Path(a.brain).parent / "run.json").read_text())
    brain = Brain.load(a.brain)
    world, eyes = World(ArmSpec(), 1), Eyes(head_of(run))
    world.rng = np.random.default_rng(a.seed)
    rows = []
    for _ in range(a.trials):
        world.randomize(holding_rate=0.0)
        world.closed = False
        eyes.reset()
        brain.reset()
        for d in range(a.limit):
            target = caregiver.hover_point(world)
            dist = float(np.linalg.norm(world.tip() - target))
            rule = teacher.reach_labels if a.teacher == "gradient" else caregiver.reach_labels
            want = np.array(rule(world, target)[:4])
            answer = answer_of(brain, eyes.inputs(world)[None])
            got = np.array(answer[len(EYE_SLOTS):len(EYE_SLOTS) + 4]) if answer is not None else np.full(4, 2)
            rows.append((dist, *(got == want), int(np.all(got == 2)), int(np.all(want == 2)),
                         float(np.mean(np.sign(steps_of(got)) == np.sign(steps_of(want))))))
            if dist <= 0.025:
                break
            world.decide(steps_of(got), 0)
    r = np.array(rows, float)
    out = {}
    lo = 0.0
    for hi in BANDS:
        m = (r[:, 0] >= lo) & (r[:, 0] < hi)
        if m.any():
            out[f"{lo:.3f}-{hi:.3f}"] = {"states": int(m.sum()), "joint_match": r[m, 1:5].mean(axis=0).round(2).tolist(),
                                       "brain_holds": round(float(r[m, 5].mean()), 2), "caregiver_holds": round(float(r[m, 6].mean()), 2),
                                       "direction_match": round(float(r[m, 7].mean()), 2)}
        lo = hi
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
