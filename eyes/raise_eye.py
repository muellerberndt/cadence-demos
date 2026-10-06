"""Raise the foveated eye the page runs, then assay it.

    .venv/bin/python raise_eye.py --out runs/eye-s1 --seed 1     # the shipped brain

The eye is one connectome (``tracker/anatomy.py``) run by ``cadence.Brain``: a two-channel
foveated retina (brightness and change), one tied convolutional V1 stage, a 13×13 retinotopic
superior colliculus map with a balanced topographic readout, and two gaze slots of 13 bins.
Every frame the whole connectome settles together; there is no separate stage solve.

Raising is open loop: the world (``tracker/fovea.py`` ``FovealWorld``) places the eye near its
shape and moves it as a competent eye would, and every frame is a lesson on where the eye's own
shape is (``Learner.step``, the library's local contrast rule, warm from the answer's own free
state). Faces are among the shapes it is raised on; stars, tees and ells are never shown.

The assays run on the raised brain, frozen: first glance from rest; the dart test (the eye's own
shape jumps 10, 20 or 30 px while everything else stays still); another shape's jump; and every
shape followed by its own eye on a surface where all of them move. ``summary.json`` holds them.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from dataclasses import replace
from pathlib import Path

import cadence
import numpy as np

from tracker.anatomy import Anatomy, Stage, build, describe
from tracker.fovea import FovealConfig, FovealWorld, fovea_dart, fovea_glance, fovea_scene
from tracker.life import Life, Teaching
from tracker.shapes import HELD_OUT

UNSEEN = tuple(k for k in HELD_OUT if k != "face")


def make_eye(seed: int, features: int = 8) -> tuple[cadence.Brain, Anatomy]:
    """The eye's brain at birth, with the learning settings it is raised with."""
    anatomy = Anatomy(size=25, bins=13, channels=2, stages=(Stage(features, 5, 2),), kernels="tied",
                      sheet=13, sheet_input="topographic", reach=1.5, lateral=None, memory=None,
                      readout="topographic")
    brain = build(anatomy, seed=seed, trace=None, tie_rate="sum")
    brain.learner.config = replace(brain.learner.config, eta=0.1, eta_bias=None, momentum=0.0,
                                   nudge="quadratic")
    return brain, anatomy


def assay(path: Path, cfg: FovealConfig, seed: int, trials: dict) -> dict:
    s = 10_000 + seed
    return {
        "glance": fovea_glance(path, cfg, trials["glance"], s),
        "glance_unseen": fovea_glance(path, cfg, trials["glance"], s + 1, kinds=UNSEEN),
        "dart": fovea_dart(path, cfg, trials["dart"], s + 2),
        "dart_distractor": fovea_dart(path, cfg, trials["dart"], s + 3, distractor=True),
        "scene": {str(n): fovea_scene(path, cfg, objects=n, frames=trials["scene"], seed=s + 4)
                  for n in (4, 8)},
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--features", type=int, default=8)
    p.add_argument("--lessons", type=int, default=20000)
    p.add_argument("--glance-trials", dest="glance", type=int, default=300)
    p.add_argument("--dart-trials", dest="dart", type=int, default=60)
    p.add_argument("--scene-frames", dest="scene", type=int, default=600)
    p.add_argument("--report-every", dest="report_every", type=int, default=1000)
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = FovealConfig()
    brain, anatomy = make_eye(a.seed, a.features)
    meta = {"fovea": cfg.__dict__, "anatomy": {**anatomy.to_dict(), **describe(brain)},
            "learning": {k: getattr(brain.learner.config, k) for k in
                         ("eta", "eta_bias", "momentum", "nudge", "tolerance", "free_steps")},
            "seed": a.seed, "lessons": a.lessons, "cadence": cadence.__version__,
            "numpy": np.__version__, "python": platform.python_version()}
    (out / "run.json").write_text(json.dumps(meta, indent=1, default=str))
    print(f"brain {brain.connectome.n} neurons, {brain.connectome.synapses} synapses", flush=True)

    world = FovealWorld(cfg, a.seed)
    life = Life(brain, world, teaching=Teaching("always"), seed=a.seed)
    t0, window = time.time(), []
    for _ in range(a.lessons):
        row = life.see(world.step(), "bootstrap")
        window.append(row)
        if len(window) == a.report_every:
            vis = [r for r in window if r["visible"]]
            print(f"lesson {row['tick'] + 1:6d}  hit {np.mean([r['hit'] for r in vis]):.3f}  "
                  f"sweeps {np.mean([r['sweeps'] for r in window]):5.1f}  "
                  f"ms {np.mean([r['ms'] for r in window]):5.1f}", flush=True)
            window.clear()
    path = brain.save(out / "brain.npz")
    summary = {"lessons": a.lessons, "seconds": round(time.time() - t0, 1),
               "world": dict(world.counts),
               "assays": assay(path, cfg, a.seed, {"glance": a.glance, "dart": a.dart, "scene": a.scene})}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    g, d = summary["assays"]["glance"], summary["assays"]["dart"]
    print(f"glance near {g['near']['hit']} mid {g['mid']['hit']} far {g['far']['hit']}  "
          f"faces {g['by_kind'].get('face')}  dart after 3 frames "
          + " ".join(f"{j} px {v['3']}" for j, v in d.items()), flush=True)


if __name__ == "__main__":
    main()
