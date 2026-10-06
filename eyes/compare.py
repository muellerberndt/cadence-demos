"""The page's eye against its control, on the same tests and seeds.

    .venv/bin/python compare.py [--trials 60] [--frames 600] [--out evidence/comparison.json]

The foveated eye (``web/pack/brain.npz``, as the page runs it) and the window eye it replaced
(``controls/window-eye.npz``): a 26×26 window at full resolution, raised on eight shapes
without faces. Both run the dart test (the eye's own shape jumps 10, 20 or 30 px while
everything else stays still: is the eye centred on it again after one, two and three frames?),
the same test with another shape jumping (does the eye stay on its own?), and every shape
followed by its own eye on a surface where all of them freeze, walk and dart (the share of eye
frames centred on the eye's own shape). Shapes include faces in every test.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tracker.eyes import EyeConfig, scene_assay, window_dart
from tracker.fovea import FOVEA_KINDS, FovealConfig, fovea_dart, fovea_scene

HERE = Path(__file__).resolve().parent


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--trials", type=int, default=60)
    p.add_argument("--frames", type=int, default=600)
    p.add_argument("--seeds", type=int, default=2)
    p.add_argument("--out", default=str(HERE / "evidence" / "comparison.json"))
    a = p.parse_args()
    fovea, window = HERE / "web" / "pack" / "brain.npz", HERE / "controls" / "window-eye.npz"
    out = {
        "foveated eye": {
            "dart": fovea_dart(fovea, FovealConfig(), a.trials, seed=1),
            "another shape darts": fovea_dart(fovea, FovealConfig(), a.trials, seed=2, distractor=True),
            "scene": {str(n): [fovea_scene(fovea, FovealConfig(), objects=n, frames=a.frames, seed=100 + s,
                                           kinds=FOVEA_KINDS)["on_own_shape"] for s in range(a.seeds)]
                      for n in (4, 8)},
        },
        "window eye (control)": {
            "dart": window_dart(window, EyeConfig(), a.trials, seed=1),
            "another shape darts": window_dart(window, EyeConfig(), a.trials, seed=2, distractor=True),
            "scene": {str(n): [scene_assay(window, EyeConfig(), objects=n, frames=a.frames, seed=100 + s,
                                           kinds=FOVEA_KINDS)["on_own_shape"] for s in range(a.seeds)]
                      for n in (4, 8)},
        },
        "trials": a.trials, "frames": a.frames, "seeds": a.seeds,
    }
    Path(a.out).write_text(json.dumps(out, indent=1))
    for eye, r in out.items():
        if not isinstance(r, dict):
            continue
        print(f"{eye}: own shape jumps (centred again after 3 frames) "
              + ", ".join(f"{j} px {v['3']:.2f}" for j, v in r["dart"].items())
              + f"; another shape jumps 20 px, stays on its own {r['another shape darts']['20.0']['3']:.2f}"
              + "; moving scene, on own shape " + ", ".join(f"{n} shapes {v}" for n, v in r["scene"].items()))


if __name__ == "__main__":
    main()
