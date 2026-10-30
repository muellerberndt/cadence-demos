"""A caregiver whose labels name a direction for every joint.

The 0.83 caregiver moves a joint only where its step gains more than a dead zone, so most joints
are labelled "hold" in most states; a brain that answers each joint on its own learned to hold
everything and froze short of the block. This caregiver labels each joint with its best level
whenever that level brings the settled fingertip closer at all, coarse when the gain of the coarse
step exceeds the fine step's, and holds only within tolerance or where no single step of that
joint helps. The step it labels is the one a joint would take alone, so labels are a smooth
function of the geometry.
"""

from __future__ import annotations

import numpy as np

from arm.caregiver import TOLERANCE
from arm.world import World, forward, index_of


def gradient_steps(world: World, target: np.ndarray, tolerance: float = TOLERANCE) -> np.ndarray:
    spec = world.spec
    if np.linalg.norm(world.tip() - target) <= tolerance and np.linalg.norm(world.rest - world.q) < 0.05:
        return np.zeros(4)
    here = float(np.linalg.norm(forward(spec, world.rest)[3] - target))
    steps = np.zeros(4)
    for j in range(4):
        best, gain = 0.0, 0.0
        for level in (-2.0, -1.0, 1.0, 2.0):
            q = world.rest.copy()
            q[j] = np.clip(q[j] + level * spec.step, world.low[j], world.high[j])
            g = here - float(np.linalg.norm(forward(spec, q)[3] - target))
            if g > gain:
                best, gain = level, g
        steps[j] = best
    return steps


def _cost(point: np.ndarray, target: np.ndarray, lateral: float) -> float:
    d = point - target
    return float(np.sqrt(lateral * (d[0] ** 2 + d[1] ** 2) + d[2] ** 2))


def job_steps(world: World, target: np.ndarray, phase: str, tolerance: float = TOLERANCE,
              near: float = 0.06, lateral: float = 4.0) -> np.ndarray:
    """The direction caregiver for the whole job. Within ``near`` of the target only fine steps
    (coarse steps of several joints at once carried the fingertip sideways out of the lowering
    phase and back, without end); while lowering and grasping the error in the plane counts
    ``lateral`` times the error in height, so the fingertip comes down over the block; where no
    joint alone helps, the best combination. Over 100 fresh jobs it places the block in the right
    bin every time (the reach labels of ``gradient_steps`` placed 0.74: the rest oscillated)."""
    from arm.caregiver import ideal_steps

    spec = world.spec
    if np.linalg.norm(world.tip() - target) <= tolerance and np.linalg.norm(world.rest - world.q) < 0.05:
        return np.zeros(4)
    weight = lateral if phase in ("lower", "grasp") else 1.0
    tip = forward(spec, world.rest)[3]
    here = _cost(tip, target, weight)
    levels = (-1.0, 1.0) if np.linalg.norm(tip - target) < near else (-2.0, -1.0, 1.0, 2.0)
    steps = np.zeros(4)
    for j in range(4):
        best, gain = 0.0, 0.0
        for level in levels:
            q = world.rest.copy()
            q[j] = np.clip(q[j] + level * spec.step, world.low[j], world.high[j])
            g = here - _cost(forward(spec, q)[3], target, weight)
            if g > gain:
                best, gain = level, g
        steps[j] = best
    if not steps.any():
        return ideal_steps(world, target, tolerance, rule="search")
    return steps


def reach_labels(world: World, target: np.ndarray) -> list[int]:
    return [index_of(s) for s in gradient_steps(world, target)] + [int(world.closed)]
