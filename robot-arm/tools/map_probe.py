"""Raise a small eye briefly, then picture its maps: does a blob form where the block is?

    python tools/map_probe.py --out runs/probe-readout --lessons 300
    python tools/map_probe.py --out runs/probe-maps --lessons 300 --teach-maps
"""

from __future__ import annotations

import argparse
import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

from arm.anatomy import Anatomy, Stage, build, eye_learner, map_cells, raising_config, share_graph  # noqa: E402
from arm.eyes import Eyes, HeadSpec  # noqa: E402
from arm.view import save_png  # noqa: E402
from arm.world import ArmSpec, World  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--lessons", type=int, default=300)
    p.add_argument("--size", type=int, default=28)
    p.add_argument("--teach-maps", dest="teach_maps", action="store_true")
    p.add_argument("--scenes", type=int, default=4)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--priors", action="store_true")
    p.add_argument("--readout-forward", dest="readout_forward", action="store_true")
    p.add_argument("--map-input-forward", dest="map_input_forward", action="store_true")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    head = HeadSpec(size=a.size, eyes=1, colour=True)
    sheet = (a.size - 5) // 2 + 1
    anatomy = Anatomy(size=a.size, channels=head.channels, eyes=1, hidden=64, stages=(Stage(8, 5, 2),), sheet=sheet,
                      sheets=3, readout="topographic", map_reciprocal=False, map_density=0.5, priors=a.priors,
                      readout_reciprocal=not a.readout_forward, map_input_reciprocal=not a.map_input_forward)
    brain = build(anatomy, seed=a.seed, trace=None)
    raising_config(brain)
    learner = eye_learner(brain, teach_maps=a.teach_maps)
    world, eyes = World(ArmSpec(), a.seed), Eyes(head)
    maps = map_cells(brain)

    def dump(tag: str) -> None:
        rng_state = world.rng
        world.rng = np.random.default_rng(7)
        for k in range(a.scenes):
            world.randomize(holding_rate=0.0)
            x = eyes.inputs(world)[None]
            brain.reset()
            try:
                answer = brain.act(x, greedy=True)[0]
            except RuntimeError:
                answer = None
            state = brain.basal_ganglia.state
            act = np.asarray(state.activation)[0]
            frames = eyes.see(world)
            save_png(frames[0], out / f"{tag}_scene{k}_retina.png", 6)
            for m, cells in enumerate(maps):
                img = act[cells].reshape(sheet, sheet)
                lo, hi = float(img.min()), float(img.max())
                save_png((img - lo) / (hi - lo + 1e-9), out / f"{tag}_scene{k}_map{m}.png", 12)
            labels = eyes.labels(world)
            cells_true = eyes.map_labels(world, sheet)
            print(f"{tag} scene {k}: answer {None if answer is None else answer[:4].tolist()} labels {labels[:4]} "
                  f"map cells block/hand {cells_true[:2]} map0 range {act[maps[0]].min():.2f}..{act[maps[0]].max():.2f} "
                  f"argmax {int(np.argmax(act[maps[0]]))} map1 argmax {int(np.argmax(act[maps[1]]))}", flush=True)
        world.rng = rng_state

    dump("birth")
    for lesson in range(a.lessons):
        world.randomize(holding_rate=0.0)
        x = eyes.inputs(world)[None]
        drive = brain.stimulus(x)
        try:
            brain.act(x, greedy=True)
            warm = brain.basal_ganglia.state
        except RuntimeError:
            warm = None
        taught = eyes.labels(world)
        if a.teach_maps:
            taught = eyes.map_labels(world, sheet)[:3] + taught
        learner.step(drive, np.array([taught], dtype=np.int64), warm=warm)
        share_graph(brain, learner)
    dump("raised")


if __name__ == "__main__":
    main()
