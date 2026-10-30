"""Inspect a stage-2 checkpoint frozen: the job assay under nominal and held-out physics.

    python -m arm2.inspect --checkpoint runs/x/brain.npz --trials 40 --seed 30001 --json
    python -m arm2.inspect --checkpoint runs/x/brain.npz --trials 200 --seed 80001 --controls \
        --newborn runs/x/brain_newborn.npz --heldout --json

The reading: the brain's stages, median decisions, the gates each against the teacher on the
same trials (ratio and difference), distinct commands at 40 fixed starts, the largest motor
activation, holds and sweeps; with ``--controls`` random, the blind twin, the frozen newborn and
the MLP where given; with ``--heldout`` the brain and the teacher again at ``--physics heldout``
(friction, mass and contact stiffness never used in training), reported apart.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from arm1.inspect import against_teacher

from .job import GATES, BrainPolicy, MLPPolicy, Policy, RandomPolicy, TeacherPolicy, commands_at_starts, job_assay


def load_policy(path: str | Path, pools: str, blind: bool = False, velocity: bool = True, slip: bool = False) -> Policy:
    path = Path(path)
    if path.suffix == ".pt":
        from arm1 import mlp

        return MLPPolicy(mlp.load(path), pools, blind=blind, velocity=velocity, slip=slip)
    from cadence import Brain

    return BrainPolicy(Brain.load(path), pools, blind=blind, velocity=velocity, slip=slip)


def inspect_checkpoint(checkpoint: str | Path, *, pools: str, trials: int, seed: int, cap: int = 80, starts: int = 40,
                       starts_seed: int = 90_001, controls: bool = False, newborn: str | None = None, mlp: str | None = None,
                       velocity: bool = True, physics: str = "nominal", heldout: bool = False, heldout_set: str = "heldout",
                       slip: bool = False) -> dict:
    t0 = time.time()
    policy = load_policy(checkpoint, pools, velocity=velocity, slip=slip)
    out: dict = {"checkpoint": str(checkpoint), "pools": pools, "trials": trials, "seed": seed, "cap": cap, "physics": physics,
                 "velocity": velocity, "slip": slip, "heldout_set": heldout_set}
    out["brain"] = job_assay(policy, pools, trials, seed, cap, physics)
    out["starts"] = commands_at_starts(policy, pools, starts, starts_seed, physics)
    out["teacher"] = job_assay(TeacherPolicy(pools), pools, trials, seed, cap, physics)
    out["gates_vs_teacher"] = against_teacher(out["brain"], out["teacher"], GATES)
    if controls:
        out["random"] = job_assay(RandomPolicy(pools, seed + 1), pools, trials, seed, cap, physics)
        out["blind"] = job_assay(load_policy(checkpoint, pools, blind=True, velocity=velocity, slip=slip), pools, trials, seed, cap, physics)
        if newborn:
            out["newborn"] = job_assay(load_policy(newborn, pools, velocity=velocity, slip=slip), pools, trials, seed, cap, physics)
        if mlp:
            out["mlp"] = job_assay(load_policy(mlp, pools, velocity=velocity, slip=slip), pools, trials, seed, cap, physics)
    if heldout:
        out["heldout"] = job_assay(load_policy(checkpoint, pools, velocity=velocity, slip=slip), pools, trials, seed + 5, cap, heldout_set)
        out["teacher_heldout"] = job_assay(TeacherPolicy(pools), pools, trials, seed + 5, cap, heldout_set)
        out["heldout_vs_teacher"] = against_teacher(out["heldout"], out["teacher_heldout"], GATES)
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
    p.add_argument("--newborn", default=None)
    p.add_argument("--mlp", default=None)
    p.add_argument("--no-velocity", dest="no_velocity", action="store_true", help="the checkpoint was raised without joint velocities")
    p.add_argument("--physics", choices=("nominal", "heldout", "wide", "heldout2"), default="nominal")
    p.add_argument("--heldout", action="store_true", help="also read the brain and the teacher at held-out physics")
    p.add_argument("--heldout-set", dest="heldout_set", choices=("heldout", "heldout2"), default="heldout")
    p.add_argument("--senses", choices=("basic", "slip"), default="basic", help="the checkpoint's observation layout")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    out = inspect_checkpoint(a.checkpoint, pools=a.pools, trials=a.trials, seed=a.seed, cap=a.cap, starts=a.starts,
                             starts_seed=a.starts_seed, controls=a.controls, newborn=a.newborn, mlp=a.mlp,
                             velocity=not a.no_velocity, physics=a.physics, heldout=a.heldout, heldout_set=a.heldout_set,
                             slip=a.senses == "slip")
    print(json.dumps(out) if a.json else json.dumps(out, indent=1), flush=True)


if __name__ == "__main__":
    main()
