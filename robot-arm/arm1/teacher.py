"""Teacher labels in Cartesian terms from the smooth plan.

``arm091.job.smooth_plan`` names the fingertip's next waypoint and the gripper for every state
of the job (approach, lower, grasp, lift, carry, release), with targets continuous in the state;
as a policy through the joint pools it places 100 of 100 blocks. Here the same plan labels the
Cartesian pools: per axis the waypoint minus the fingertip, rounded to whole centimetres and
clipped to two (so under 5 mm on an axis labels hold), the gripper from the plan's phase. The
joint labels (``arm091.teacher.job_steps``) stay for ``--pools joint``.

    python -m arm1.teacher --trials 100            # the teacher as a policy through the reflex
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from arm.world import World, index_of
from arm091.job import smooth_plan
from arm091.teacher import job_steps

from .actions import HOLD, STEP_M


def cartesian_labels(world: World) -> list[int]:
    target, close, _ = smooth_plan(world)
    d = target - world.tip()
    levels = np.clip(np.round(d / STEP_M), -2, 2).astype(int) + HOLD
    return [int(v) for v in levels] + [int(close)]


def joint_labels(world: World) -> list[int]:
    target, close, phase = smooth_plan(world)
    return [index_of(s) for s in job_steps(world, target, phase)] + [int(close)]


def labels(world: World, pools: str) -> list[int]:
    return cartesian_labels(world) if pools == "cartesian" else joint_labels(world)


def phase(world: World) -> str:
    return smooth_plan(world)[2]


def main() -> None:
    from .job import TeacherPolicy, job_assay

    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--trials", type=int, default=100)
    p.add_argument("--seed", type=int, default=60_001)
    p.add_argument("--cap", type=int, default=80)
    p.add_argument("--pools", choices=("cartesian", "joint"), default="cartesian")
    a = p.parse_args()
    print(json.dumps(job_assay(TeacherPolicy(a.pools), a.pools, a.trials, a.seed, a.cap), indent=1))


if __name__ == "__main__":
    main()
