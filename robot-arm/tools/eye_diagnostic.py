"""A fast diagnostic of the eye's learning machinery on a trivially segmentable scene: only the
block is visible (everything else black), one eye, small retina, one map, topographic readouts.
If this cannot be learned in a few hundred lessons, the machinery is wrong, not the scene.

    python tools/eye_diagnostic.py --tie-rate sqrt --lessons 400
"""

from __future__ import annotations

import argparse
import os
import time

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import numpy as np  # noqa: E402

from arm import caregiver  # noqa: E402
from arm.anatomy import Anatomy, Stage, build, raising_config  # noqa: E402
from arm.eyes import Eyes, HeadSpec  # noqa: E402
from arm.world import ArmSpec, World  # noqa: E402

ONLY_BLOCK = dict(table=0.0, bin=0.0, block=1.0, link=0.0, hand=0.0, lamp_on=0.0, lamp_off=0.0, background=0.0)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tie-rate", dest="tie_rate", default="sqrt")
    p.add_argument("--lessons", type=int, default=400)
    p.add_argument("--size", type=int, default=24)
    p.add_argument("--eta", type=float, default=0.1)
    p.add_argument("--full-scene", dest="full", action="store_true")
    p.add_argument("--sheets", type=int, default=1)
    p.add_argument("--readout", default="topographic")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--eye-only", dest="eye_only", action="store_true", help="only the four position readouts")
    p.add_argument("--colour", action="store_true")
    p.add_argument("--eyes", type=int, default=1)
    p.add_argument("--eye-streams", dest="eye_streams", action="store_true")
    p.add_argument("--priors", action="store_true")
    p.add_argument("--readout-forward", dest="readout_forward", action="store_true")
    p.add_argument("--map-input-forward", dest="map_input_forward", action="store_true")
    a = p.parse_args()
    head = HeadSpec(size=a.size, eyes=a.eyes, colour=a.colour) if a.full else HeadSpec(size=a.size, eyes=a.eyes, bright=ONLY_BLOCK)
    sheet = (a.size - 5) // 2 + 1
    slots = (12, 12, 12, 12) if a.eye_only else None
    extra = {} if slots is None else {"slots": slots}
    anatomy = Anatomy(size=a.size, channels=head.channels, eyes=a.eyes, eye_streams=a.eye_streams, hidden=64,
                      stages=(Stage(8, 5, 2),), sheet=sheet, sheets=a.sheets, readout=a.readout,
                      map_reciprocal=False, map_density=0.5, priors=a.priors,
                      readout_reciprocal=not a.readout_forward, map_input_reciprocal=not a.map_input_forward, **extra)
    brain = build(anatomy, seed=a.seed, trace=None, tie_rate=a.tie_rate)
    raising_config(brain, a.eta)
    world, eyes = World(ArmSpec(), a.seed), Eyes(head)
    print(f"{brain.connectome.n} neurons {brain.connectome.synapses} synapses, tie {a.tie_rate}, size {a.size}, scene {'full' if a.full else 'block only'}")
    t0 = time.time()
    window = []
    for lesson in range(a.lessons):
        world.randomize(holding_rate=0.0)
        x = eyes.inputs(world)[None]
        labels = np.array([eyes.labels(world)[:4] if a.eye_only else eyes.labels(world) + caregiver.labels(world)], dtype=np.int64)
        drive = brain.stimulus(x)
        try:
            answer = brain.act(x, greedy=True)[0]
        except RuntimeError:
            answer = None
        sweeps = int((brain.last_settlement or {}).get("steps", 0))
        if answer is None:
            window.append((6.0, 0.0, sweeps, 0.0, 0.0))
        else:
            err_b = np.mean([abs(int(answer[k]) - int(labels[0, k])) for k in (0, 1)])
            hit_b = float(all(abs(int(answer[k]) - int(labels[0, k])) <= 1 for k in (0, 1)))
            hit_h = float(all(abs(int(answer[k]) - int(labels[0, k])) <= 1 for k in (2, 3)))
            window.append((err_b, hit_b, sweeps, 1.0, hit_h))
        warm = brain.basal_ganglia.state if answer is not None else None
        brain.learner.step(drive, labels, warm=warm)
        if (lesson + 1) % 100 == 0:
            w = np.array(window)
            print(f"lesson {lesson + 1:5d}  block bin error {w[:, 0].mean():.2f}  block within one bin {w[:, 1].mean():.2f}  "
                  f"hand within one bin {w[:, 4].mean():.2f}  sweeps {w[:, 2].mean():5.1f}  answered {w[:, 3].mean():.2f}  {time.time() - t0:5.0f} s", flush=True)
            window = []


if __name__ == "__main__":
    main()
