"""Inspect a checkpoint frozen: the job assay, the controls and the policy's shape.

    python -m arm1.inspect --checkpoint runs/x/brain.npz --trials 40 --seed 30001 --json
    python -m arm1.inspect --checkpoint runs/x/brain.npz --trials 200 --seed 80001 --controls \
        --newborn runs/x/brain_newborn.npz --mlp runs/mlp_s1/mlp.pt --json

The checkpoint (``.npz`` a brain, ``.pt`` the MLP control) is loaded in this process and never
taught. The reading: every stage rate, the median decisions to a right placement, the motion
gates each against the teacher's value on the same trials, distinct commands at 40 fixed starts,
the largest motor activation, the share of holds and the sweeps per settle. ``--controls`` adds
uniform random, the blind twin (object terms zeroed), the frozen newborn and the MLP where given.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .job import GATES, BrainPolicy, MLPPolicy, Policy, RandomPolicy, TeacherPolicy, commands_at_starts, job_assay


def load_policy(path: str | Path, pools: str, blind: bool = False) -> Policy:
    path = Path(path)
    if path.suffix == ".pt":
        from . import mlp

        return MLPPolicy(mlp.load(path), pools, blind=blind)
    from cadence import Brain

    return BrainPolicy(Brain.load(path), pools, blind=blind)


def against_teacher(reading: dict, teacher: dict, gates: tuple[str, ...] = GATES) -> dict:
    """Each gate as a ratio to the teacher's value (None where the teacher's is zero or either is
    missing) and as a difference, brain minus teacher."""
    ratio, minus = {}, {}
    for k in gates:
        a, b = reading["gates"].get(k), teacher["gates"].get(k)
        ratio[k] = None if a is None or not b else round(a / b, 3)
        minus[k] = None if a is None or b is None else round(a - b, 4)
    return {"ratio": ratio, "minus": minus}


def inspect_checkpoint(checkpoint: str | Path, *, pools: str, trials: int, seed: int, cap: int = 80, starts: int = 40,
                       starts_seed: int = 90_001, controls: bool = False, newborn: str | None = None,
                       mlp: str | None = None) -> dict:
    t0 = time.time()
    policy = load_policy(checkpoint, pools)
    out: dict = {"checkpoint": str(checkpoint), "pools": pools, "trials": trials, "seed": seed, "cap": cap}
    out["brain"] = job_assay(policy, pools, trials, seed, cap)
    out["starts"] = commands_at_starts(policy, pools, starts, starts_seed)
    out["teacher"] = job_assay(TeacherPolicy(pools), pools, trials, seed, cap)
    out["gates_vs_teacher"] = against_teacher(out["brain"], out["teacher"])
    if controls:
        out["random"] = job_assay(RandomPolicy(pools, seed + 1), pools, trials, seed, cap)
        out["blind"] = job_assay(load_policy(checkpoint, pools, blind=True), pools, trials, seed, cap)
        if newborn:
            out["newborn"] = job_assay(load_policy(newborn, pools), pools, trials, seed, cap)
        if mlp:
            out["mlp"] = job_assay(load_policy(mlp, pools), pools, trials, seed, cap)
    out["seconds"] = round(time.time() - t0, 1)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--pools", choices=("cartesian", "joint"), default="cartesian")
    p.add_argument("--trials", type=int, default=40)
    p.add_argument("--seed", type=int, default=30_001)
    p.add_argument("--cap", type=int, default=80)
    p.add_argument("--starts", type=int, default=40)
    p.add_argument("--starts-seed", dest="starts_seed", type=int, default=90_001)
    p.add_argument("--controls", action="store_true")
    p.add_argument("--newborn", default=None, help="the frozen newborn's checkpoint (with --controls)")
    p.add_argument("--mlp", default=None, help="the MLP control's checkpoint (with --controls)")
    p.add_argument("--json", action="store_true", help="one JSON object on the last line")
    a = p.parse_args()
    out = inspect_checkpoint(a.checkpoint, pools=a.pools, trials=a.trials, seed=a.seed, cap=a.cap, starts=a.starts,
                             starts_seed=a.starts_seed, controls=a.controls, newborn=a.newborn, mlp=a.mlp)
    print(json.dumps(out) if a.json else json.dumps(out, indent=1), flush=True)


if __name__ == "__main__":
    main()
