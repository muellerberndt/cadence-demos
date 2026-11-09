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

The lessons use the quadratic nudge, which the library keeps on a standalone ``Learner``; a
``Brain`` checkpoint takes the cross-entropy nudge only. The raised brain is saved under the
cross-entropy nudge: the assays and the page never teach it, so its answers are the same.

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


def make_eye(seed: int, features: int = 8, backend: str | None = None) -> tuple[cadence.Brain, Anatomy]:
    """The eye's brain at birth, with the learning settings it is raised with."""
    anatomy = Anatomy(size=25, bins=13, channels=2, stages=(Stage(features, 5, 2),), kernels="tied",
                      sheet=13, sheet_input="topographic", reach=1.5, lateral=None, memory=None,
                      readout="topographic")
    brain = build(anatomy, seed=seed, trace=None, tie_rate="sum", **({"backend": backend} if backend else {}))
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
    p.add_argument("--init", default=None, help="continue raising this raised brain (a raise_eye.py brain.npz) instead of a newborn")
    p.add_argument("--eta", type=float, default=None, help="the learner's step at the start (0.1)")
    p.add_argument("--other-dart", dest="other_dart", type=float, default=None, help="world: every other shape darts per tick (0.06)")
    p.add_argument("--own-dart", dest="own_dart", type=float, default=None, help="world: the eye's own shape darts per tick (0.1)")
    p.add_argument("--dart-px", dest="dart_px", type=float, nargs=2, default=None, help="world: dart length range in px (8 34)")
    p.add_argument("--placement", type=float, nargs=2, default=None, help="world: shares of landings near and mid (0.2 0.3); the rest far")
    p.add_argument("--far-weight", dest="far_weight", type=float, default=1.0,
                   help="a lesson whose target lies 6 bins from the centre pulls this hard, rising from 1 at 2 bins")
    p.add_argument("--move-weight", dest="move_weight", type=float, default=1.0,
                   help="a lesson on a dart, slip, jump or lost frame pulls this many times harder")
    p.add_argument("--eta-final", dest="eta_final", type=float, default=None, help="the step falls linearly to this")
    p.add_argument("--decay-from", dest="decay_from", type=float, default=0.5, help="share of the lessons after which it falls")
    p.add_argument("--backend", default=None, help='e.g. "mlx" on a Mac (float32): faster lessons; the page runs the brain on the CPU')
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = FovealConfig()
    world_changes = {k: tuple(v) if isinstance(v, list) else v for k, v in
                     (("dart", a.other_dart), ("own_dart", a.own_dart), ("dart_px", a.dart_px), ("placement", a.placement)) if v is not None}
    cfg = cfg.with_(**world_changes)
    brain, anatomy = make_eye(a.seed, a.features, a.backend)
    if a.init:  # the same anatomy, raised further: its synapses, with the raise's learning settings
        learning = brain.learner.config
        brain = cadence.Brain.load(a.init, backend=a.backend or "cpu")
        brain.learner.config = replace(brain.learner.config, eta=learning.eta, eta_bias=learning.eta_bias,
                                       momentum=learning.momentum, nudge=learning.nudge, tolerance=learning.tolerance)
    if a.eta is not None:
        brain.learner.config = replace(brain.learner.config, eta=a.eta, eta_bias=a.eta / 10)
    meta = {"fovea": cfg.__dict__, "anatomy": {**anatomy.to_dict(), **describe(brain)},
            "learning": {k: getattr(brain.learner.config, k) for k in
                         ("eta", "eta_bias", "momentum", "nudge", "tolerance", "free_steps")},
            "seed": a.seed, "lessons": a.lessons, "cadence": cadence.__version__, "init": a.init, "eta": a.eta,
            "world_changes": world_changes,
            "schedule": {"far_weight": a.far_weight, "move_weight": a.move_weight,
                         "eta_final": a.eta_final, "decay_from": a.decay_from},
            "placement": getattr(brain, "placement", None),
            "numpy": np.__version__, "python": platform.python_version()}
    (out / "run.json").write_text(json.dumps(meta, indent=1, default=str))
    print(f"brain {brain.connectome.n} neurons, {brain.connectome.synapses} synapses", flush=True)

    world = FovealWorld(cfg, a.seed)
    life = Life(brain, world, teaching=Teaching("always"), seed=a.seed)
    middle = cfg.bins // 2
    if a.far_weight != 1.0 or a.move_weight != 1.0:
        def weigh(frame) -> float:
            far = max(abs(frame.target[0] - middle), abs(frame.target[1] - middle))
            w = 1.0 + (a.far_weight - 1.0) * min(max((far - 2) / 4.0, 0.0), 1.0)
            return w * (a.move_weight if frame.event in ("dart", "slip", "jump", "lost") else 1.0)
        life.weigh = weigh
    eta0 = brain.learner.config.eta
    t0, window = time.time(), []
    for i in range(a.lessons):
        if a.eta_final is not None and i % 250 == 0:
            f = min(max((i / a.lessons - a.decay_from) / max(1.0 - a.decay_from, 1e-9), 0.0), 1.0)
            eta = eta0 + (a.eta_final - eta0) * f
            brain.learner.config = replace(brain.learner.config, eta=eta, eta_bias=eta / 10)
        row = life.see(world.step(), "bootstrap")
        window.append(row)
        if len(window) == a.report_every:
            vis = [r for r in window if r["visible"]]
            print(f"lesson {row['tick'] + 1:6d}  hit {np.mean([r['hit'] for r in vis]):.3f}  "
                  f"sweeps {np.mean([r['sweeps'] for r in window]):5.1f}  "
                  f"ms {np.mean([r['ms'] for r in window]):5.1f}", flush=True)
            window.clear()
    # saved under the nudge a Brain checkpoint takes; nothing teaches the brain after this
    brain.learner.config = replace(brain.learner.config, nudge="cross_entropy")
    path = brain.save(out / "brain.npz")
    summary = {"lessons": a.lessons, "seconds": round(time.time() - t0, 1),
               "world": dict(world.counts),
               "assays": assay(path, FovealConfig(), a.seed, {"glance": a.glance, "dart": a.dart, "scene": a.scene})}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    g, d = summary["assays"]["glance"], summary["assays"]["dart"]
    print(f"glance near {g['near']['hit']} mid {g['mid']['hit']} far {g['far']['hit']}  "
          f"faces {g['by_kind'].get('face')}  dart after 3 frames "
          + " ".join(f"{j} px {v['3']}" for j, v in d.items()), flush=True)


if __name__ == "__main__":
    main()
