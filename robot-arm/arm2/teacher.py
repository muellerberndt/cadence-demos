"""The teacher under contact physics: IK waypoints with targets continuous in the state.

Empty hand: the target sits over the block at a height that falls with the tcp's distance from
the block in the plane (``HOVER`` above the block centre at 4 cm or more, the block centre when
centred); the gripper closes in the grasp window (within 1.2 cm in the plane and in height).
Closed but not yet holding: hold still while the fingers close; after three decisions without a
hold, open and approach again. Holding: rise to the carrying height, move toward the ordered
bin as the hand rises, open within 2 cm above the bin. After a release: hold still until the
block is judged. Cartesian labels per axis: the waypoint minus the tcp rounded to whole
centimetres and clipped to two; joint labels from the reflex's own IK solution toward the
waypoint, each joint's change rounded to ``JOINT_STEP`` and clipped to two.

    python -m arm2.teacher --trials 20
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from arm1.actions import HOLD, STEP_M

from .actions import BOUND, JOINT_STEP
from .scene import GRASP_HEIGHT, GRASP_PLANAR, HOVER, LIFT, PandaWorld

CLOSING_PATIENCE = 3
GENTLE = 0.05  # m above the bin floor at which the recovering teacher opens (the plain plan opens at LIFT)
# A slower lift and carry (1 cm per decision) for blocks above SLOW_MASS or below SLOW_FRICTION
# was tried and is off: creep under soft contacts grows with the time in the hand, so the slower
# carry dropped more (wide carried 0.85 against 0.96, held-out-2 0.14 against 0.83).
SLOW_MASS = 1e9
SLOW_FRICTION = 0.0


def slow_block(world: PandaWorld) -> bool:
    m = world.model
    return bool(m.body_mass[world.block_body] > SLOW_MASS or m.geom_friction[world.block_geom, 0] < SLOW_FRICTION)


def plan(world: PandaWorld, recover: bool = False) -> tuple[np.ndarray, int, str]:
    """``recover``: the stage-2b teacher. A slip (holding lost with the gripper closed after a
    lift) reopens at once instead of after ``CLOSING_PATIENCE`` decisions, so the block is
    re-approached, re-closed and re-lifted where it landed."""
    tip = world.tip()
    if world.holding:
        release = world.release_point()
        if release is None:
            return np.array([tip[0], tip[1], LIFT]), 1, "hold"
        # (a put-down-and-regrasp on sag was tried and removed: under soft contacts the block sags
        # elastically by more than a centimetre without slipping, and the regrips dropped it:
        # wide 0.60, held-out 0.19 against the plain plan's 0.95 and 0.70)
        raised = float(np.clip((tip[2] - (LIFT - 0.06)) / 0.04, 0.0, 1.0))
        x = tip[0] + (release[0] - tip[0]) * raised
        y = tip[1] + (release[1] - tip[1]) * raised
        planar = float(np.hypot(tip[0] - release[0], tip[1] - release[1]))
        if planar <= 0.02 and tip[2] >= LIFT - 0.04 and not recover:
            return release, 0, "release"
        if recover and planar <= 0.02:
            # the gentle release: down to GENTLE above the bin floor before opening, so a bouncy
            # or slippery block does not leap out of the bin (the plain plan opens at 15 cm)
            low = world.half + GENTLE
            if tip[2] <= low + 0.012:
                return np.array([release[0], release[1], low]), 0, "release"
            return np.array([release[0], release[1], low]), 1, "lower"
        return np.array([x, y, LIFT]), 1, "carry" if raised >= 1.0 else "lift"
    if world.releasing:
        return tip, 0, "released"
    block = world.block_pos()
    planar = float(np.hypot(tip[0] - block[0], tip[1] - block[1]))
    window = planar <= GRASP_PLANAR and abs(tip[2] - block[2]) <= GRASP_HEIGHT
    if world.closed:
        # (reopening at once after a lost contact was tried and removed: holding flickers for a
        # decision during a carry, and the instant reopen dropped the block, wide 0.70 vs 0.95)
        patience = CLOSING_PATIENCE
        if world.closed_for < patience and (window or world.closed_for == 0):
            return tip, 1, "closing"
        return np.array([block[0], block[1], block[2] + HOVER]), 0, "reopen"
    height = block[2] + HOVER * min(1.0, planar / 0.04)
    return np.array([block[0], block[1], height]), int(window), "grasp" if window else ("lower" if planar < 0.04 else "approach")


def reach_of(world: PandaWorld, recover: bool) -> int:
    """Levels per axis per decision: two (2 cm), or one while the recovering teacher lifts or
    carries a heavy or slippery block."""
    return 1 if (recover and world.holding and slow_block(world)) else 2


def cartesian_labels(world: PandaWorld, recover: bool = False) -> list[int]:
    target, close, _ = plan(world, recover)
    reach = reach_of(world, recover)
    levels = np.clip(np.round((target - world.tip()) / STEP_M), -reach, reach).astype(int) + HOLD
    return [int(v) for v in levels] + [int(close)]


def joint_labels(world: PandaWorld, recover: bool = False) -> list[int]:
    target, close, _ = plan(world, recover)
    rest = world.rest()
    reach = reach_of(world, recover) * STEP_M
    step = np.clip(target - world.tip(), -reach, reach)  # the same bounded shift the Cartesian labels name
    q = world.solve_ik(rest, world.tip() + step, bound=BOUND)
    levels = np.clip(np.round((q - rest) / JOINT_STEP), -2, 2).astype(int) + HOLD
    return [int(v) for v in levels] + [int(close)]


def labels(world: PandaWorld, pools: str, recover: bool = False) -> list[int]:
    return cartesian_labels(world, recover) if pools == "cartesian" else joint_labels(world, recover)


def phase(world: PandaWorld, recover: bool = False) -> str:
    return plan(world, recover)[2]


def main() -> None:
    from .job import TeacherPolicy, job_assay

    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--trials", type=int, default=20)
    p.add_argument("--seed", type=int, default=60_001)
    p.add_argument("--cap", type=int, default=80)
    p.add_argument("--pools", choices=("cartesian", "joint"), default="cartesian")
    p.add_argument("--physics", choices=("nominal", "heldout", "wide", "heldout2"), default="nominal")
    p.add_argument("--recover", action="store_true", help="the stage-2b teacher: slip recovery and a slower lift of heavy or slippery blocks")
    a = p.parse_args()
    print(json.dumps(job_assay(TeacherPolicy(a.pools, recover=a.recover), a.pools, a.trials, a.seed, a.cap, physics=a.physics), indent=1))


if __name__ == "__main__":
    main()
