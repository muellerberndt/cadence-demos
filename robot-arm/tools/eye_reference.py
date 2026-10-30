"""The Eyes demo's own visual brain (cadence-demos/eyes/tracker/anatomy.py) raised on this lane's
block-only scene: the reference for whether the scene and labels are learnable at all.

    python tools/eye_reference.py --lessons 400
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import replace

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import numpy as np  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cadence-demos", "eyes"))
from tracker.anatomy import Anatomy, Stage, build  # noqa: E402

from arm.eyes import Eyes, HeadSpec  # noqa: E402
from arm.world import ArmSpec, World  # noqa: E402

ONLY_BLOCK = dict(table=0.0, bin=0.0, block=1.0, link=0.0, hand=0.0, lamp_on=0.0, lamp_off=0.0, background=0.0)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--lessons", type=int, default=400)
    p.add_argument("--size", type=int, default=24)
    p.add_argument("--tie-rate", dest="tie_rate", default="sum")
    p.add_argument("--full-scene", dest="full", action="store_true")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args()
    sheet = (a.size - 5) // 2 + 1
    bins = sheet  # one map column per bin, as the Eyes demo has it
    anatomy = Anatomy(size=a.size, bins=bins, channels=1, stages=(Stage(8, 5, 2),), kernels="tied",
                      sheet=sheet, sheet_input="topographic", reach=1.5, lateral=None, memory=None,
                      readout="topographic")
    brain = build(anatomy, seed=a.seed, trace=None, tie_rate=a.tie_rate)
    brain.learner.config = replace(brain.learner.config, eta=0.1, eta_bias=None, momentum=0.0, nudge="quadratic")
    head = HeadSpec(size=a.size, eyes=1) if a.full else HeadSpec(size=a.size, eyes=1, bright=ONLY_BLOCK)
    world, eyes = World(ArmSpec(), a.seed), Eyes(head)
    print(f"reference eye: {brain.connectome.n} neurons {brain.connectome.synapses} synapses, bins {bins}, tie {a.tie_rate}")
    t0, window = time.time(), []
    for lesson in range(a.lessons):
        world.randomize(holding_rate=0.0)
        frame = eyes.see(world)[0]
        x = frame.reshape(1, -1)
        px, _ = eyes.cameras[0].project(world.block[None])
        col = int(np.clip(np.floor(px[0, 0] / a.size * bins), 0, bins - 1))
        row = int(np.clip(np.floor(px[0, 1] / a.size * bins), 0, bins - 1))
        labels = np.array([[col, row]], dtype=np.int64)
        drive = brain.stimulus(x)
        try:
            answer = brain.act(x, greedy=True)[0]
        except RuntimeError:
            answer = None
        sweeps = int((brain.last_settlement or {}).get("steps", 0))
        if answer is None:
            window.append((6.0, 0.0, sweeps))
        else:
            err = np.mean([abs(int(answer[0]) - col), abs(int(answer[1]) - row)])
            hit = float(abs(int(answer[0]) - col) <= 1 and abs(int(answer[1]) - row) <= 1)
            window.append((err, hit, sweeps))
        brain.learner.step(drive, labels, warm=brain.basal_ganglia.state if answer is not None else None)
        if (lesson + 1) % 100 == 0:
            w = np.array(window)
            print(f"lesson {lesson + 1:5d}  bin error {w[:, 0].mean():.2f}  within one bin {w[:, 1].mean():.2f}  sweeps {w[:, 2].mean():5.1f}  {time.time() - t0:4.0f} s", flush=True)
            window = []


if __name__ == "__main__":
    main()
