"""Four fixed trials of a frozen checkpoint as frame sequences, one PNG per decision.

    python -m arm1.render --checkpoint runs/x/brain.npz --out runs/x/frames/ep100

Each frame is the top view (``arm.view.top_view``) beside a side view of the same moment, grey,
128 px scaled twice; ``trial<k>.json`` beside the frames holds the trajectory (fingertip, block,
command, event per decision) and the trial's stages and gates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from arm.eyes import Camera, render
from arm.view import save_png, top_view
from arm.world import ArmSpec, World

from .inspect import load_policy
from .job import prepare, run_trial

SIDE = Camera((0.95, 0.30, 0.30), (0.0, 0.30, 0.06), 42.0, 128)


def frame_of(world: World) -> np.ndarray:
    return np.concatenate([top_view(world), render(world, SIDE)], axis=1)


def render_trials(checkpoint: str | Path, out: str | Path, *, pools: str, trials: int = 4, seed: int = 70_001,
                  cap: int = 80, scale: int = 2) -> list[dict]:
    out = Path(out)
    policy = load_policy(checkpoint, pools)
    world = World(ArmSpec(), seed)
    world.rng = np.random.default_rng(seed)
    results = []
    for k in range(trials):
        folder = out / f"trial{k}"
        folder.mkdir(parents=True, exist_ok=True)
        prepare(world)
        policy.reset()
        trajectory: list[dict] = []

        def observer(d: int, w: World, answer, event: str, folder=folder, trajectory=trajectory) -> None:
            save_png(frame_of(w), folder / f"{d:03d}.png", scale)
            trajectory.append({"decision": d, "tip": np.round(w.tip(), 4).tolist(), "block": np.round(w.block, 4).tolist(),
                               "holding": w.holding, "closed": w.closed, "order": w.order,
                               "command": None if answer is None else [int(v) for v in answer], "event": event})

        r = run_trial(world, policy, pools, cap, observer)
        record = {"trial": k, "seed": seed, "passed": sorted(r["passed"]), "decisions": r["decisions"], "steps": r["steps"],
                  "gates": r["gates"], "trajectory": trajectory}
        (out / f"trial{k}.json").write_text(json.dumps(record, indent=1))
        results.append({k2: v for k2, v in record.items() if k2 != "trajectory"})
    return results


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--pools", choices=("cartesian", "joint"), default="cartesian")
    p.add_argument("--trials", type=int, default=4)
    p.add_argument("--seed", type=int, default=70_001)
    p.add_argument("--cap", type=int, default=80)
    a = p.parse_args()
    print(json.dumps(render_trials(a.checkpoint, a.out, pools=a.pools, trials=a.trials, seed=a.seed, cap=a.cap), indent=1))


if __name__ == "__main__":
    main()
