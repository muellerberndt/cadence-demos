"""The scripted caregiver: what a competent arm would do next, as labels for the motor pools.

The caregiver knows the world. For a target point it tries every combination of joint steps
and picks the one that brings the fingertip closest once the reflex has settled there; within
tolerance it holds. For the job it runs a small plan: hover above the block, lower, close,
lift, carry above the ordered bin, open. Its answers are lessons, one label per motor pool,
and the control the brain is measured against.
"""

from __future__ import annotations

import itertools

import numpy as np

from .world import BLOCK, HOVER, LEVELS, World, forward, index_of

COMBOS = np.array(list(itertools.product(LEVELS, repeat=4)), dtype=float)
TOLERANCE = 0.015  # metres: close enough to hold still
LIFT = 0.12  # carrying height of the fingertip above the table


DEAD_ZONE = 0.004  # metres a joint's step must gain before the caregiver moves that joint


def ideal_steps(world: World, target: np.ndarray, tolerance: float = TOLERANCE, rule: str = "joint") -> np.ndarray:
    """Joint steps in -2..2 toward ``target``. The ``joint`` rule moves each joint on its own
    where a step of it alone brings the settled fingertip closer by more than the dead zone, so
    the labels are a smooth function of the geometry; ``search`` takes the best of every
    combination, which flips between near-equal combinations near the target."""
    spec = world.spec
    if np.linalg.norm(world.tip() - target) <= tolerance and np.linalg.norm(world.rest - world.q) < 0.05:
        return np.zeros(4)
    if rule == "search":
        best, best_cost = None, None
        for combo in COMBOS:
            q = np.clip(world.rest + combo * spec.step, world.low, world.high)
            d = float(np.linalg.norm(forward(spec, q)[3] - target))
            cost = d + 0.0015 * float(np.abs(combo).sum())
            if best_cost is None or cost < best_cost:
                best, best_cost = combo, cost
        return np.array(best)
    here = float(np.linalg.norm(forward(spec, world.rest)[3] - target))
    steps = np.zeros(4)
    for j in range(4):
        gains = {}
        for level in (-2.0, -1.0, 1.0, 2.0):
            q = world.rest.copy()
            q[j] = np.clip(q[j] + level * spec.step, world.low[j], world.high[j])
            gains[level] = here - float(np.linalg.norm(forward(spec, q)[3] - target))
        level = max(gains, key=gains.get)
        if gains[level] > DEAD_ZONE:
            steps[j] = level
    if not steps.any():  # no joint alone gains enough: a combination may (a bend of the reach)
        return ideal_steps(world, target, tolerance, rule="search")
    return steps


def hover_point(world: World) -> np.ndarray:
    return np.array([world.block[0], world.block[1], world.block_top() + HOVER])


def grasp_point(world: World) -> np.ndarray:
    return np.array([world.block[0], world.block[1], world.block_top() - 0.004])


def plan(world: World) -> tuple[np.ndarray, int, str]:
    """The caregiver's next move: a target for the fingertip, the gripper, and the phase name."""
    tip = world.tip()
    if not world.holding:
        planar = float(np.hypot(tip[0] - world.block[0], tip[1] - world.block[1]))
        if planar > 0.02 or tip[2] > world.block_top() + HOVER + 0.03:
            return hover_point(world), 0, "approach"
        target = grasp_point(world)
        top = world.block_top()
        in_window = planar <= world.spec.grasp_reach and top - world.spec.grasp_below <= tip[2] <= top + world.spec.grasp_above - world.wear
        return target, int(in_window), "grasp" if in_window else "lower"
    ordered = world.ordered_bin()
    if ordered is None:
        return np.array([tip[0], tip[1], LIFT]), 1, "hold"
    bx, by = ordered
    above = np.array([bx, by, LIFT])
    planar = float(np.hypot(tip[0] - bx, tip[1] - by))
    if tip[2] < LIFT - 0.03 and planar > 0.03:
        return np.array([tip[0], tip[1], LIFT]), 1, "lift"
    if planar > 0.02:
        return above, 1, "carry"
    return above, 0, "release"


def labels(world: World) -> list[int]:
    """One label per motor pool: the level index of each joint's step and the gripper."""
    target, close, _ = plan(world)
    steps = ideal_steps(world, target)
    return [index_of(s) for s in steps] + [int(close)]


def reach_labels(world: World, target: np.ndarray) -> list[int]:
    """Labels for reaching a point with the gripper left as it is."""
    steps = ideal_steps(world, target)
    return [index_of(s) for s in steps] + [int(world.closed)]
