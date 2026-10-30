"""Cartesian equilibrium-point actions through a disclosed IK reflex, and the joint pools.

**Cartesian pools** (``CARTESIAN_SLOTS`` = (5, 5, 5, 2)): dx, dy, dz, each at five levels
``LEVELS_CM`` = (-2, -1, 0, 1, 2) centimetres per decision (index 2 holds), and the gripper
(0 open, 1 closed). The command is a shift of the fingertip's equilibrium point.

**The IK reflex** (``ik_steps``). The target is the fingertip's present position plus the
commanded shift, its height floored at ``FLOOR`` above the table. From the rest angles (the
equilibrium point the reflex holds) it takes ``ITERATIONS`` damped-least-squares steps with the
analytic Jacobian J (3 x 4) of ``arm.world.forward``:

    dq = J^T (J J^T + lambda^2 I)^-1 (target - tip(q))  +  (I - J^+ J) k (home - q)

with lambda = ``DAMPING`` (0.05), the second term a posture bias in the null space of the
redundant arm (k = ``POSTURE``, 0.05 per iteration) toward the body's home posture, whose hand
points down; every iterate is clipped to the joint limits. The change of the rest angles is then
clipped to two fine steps (0.09 rad) per joint, the body's own bound, and handed to
``World.decide`` as fractional steps. The body is not changed: ``World.decide`` already takes
real-valued steps within -2..2.

**Joint pools** (``JOINT_SLOTS`` = (5, 5, 5, 5, 2)): the existing per-joint levels (``steps_of``)
and the gripper, for the arm D2.
"""

from __future__ import annotations

import numpy as np

from arm.world import ArmSpec, World, forward, steps_of

LEVELS_CM = (-2, -1, 0, 1, 2)
STEP_M = 0.01
HOLD = 2
CARTESIAN_SLOTS = (5, 5, 5, 2)
JOINT_SLOTS = (5, 5, 5, 5, 2)
POOLS = {"cartesian": CARTESIAN_SLOTS, "joint": JOINT_SLOTS}
FLOOR = 0.002
DAMPING = 0.05
POSTURE = 0.05
ITERATIONS = 3


def slots_of(pools: str) -> tuple[int, ...]:
    return POOLS[pools]


def grip_index(pools: str) -> int:
    return len(slots_of(pools)) - 1


def motion(pools: str) -> slice:
    return slice(0, grip_index(pools))


def hold_answer(pools: str, closed: bool) -> np.ndarray:
    """What a refused act executes: every motion slot holds, the gripper as it is."""
    return np.array([HOLD] * grip_index(pools) + [int(closed)], dtype=np.int64)


def delta_of(answer) -> np.ndarray:
    """The commanded shift of the fingertip (metres) from the Cartesian slot indices."""
    return (np.asarray(answer[:3], dtype=float) - HOLD) * STEP_M


def jacobian(spec: ArmSpec, q: np.ndarray) -> np.ndarray:
    """d(fingertip)/d(q), (3, 4), analytic from ``forward``'s geometry."""
    yaw, a1, a2, a3 = (float(v) for v in q)
    l1, l2, l3 = spec.links
    t1, t2, t3 = a1, a1 + a2, a1 + a2 + a3
    c1, c2, c3 = np.cos(t1), np.cos(t2), np.cos(t3)
    s1, s2, s3 = np.sin(t1), np.sin(t2), np.sin(t3)
    r = l1 * c1 + l2 * c2 + l3 * c3
    dr = np.array([-(l1 * s1 + l2 * s2 + l3 * s3), -(l2 * s2 + l3 * s3), -l3 * s3])
    dz = np.array([l1 * c1 + l2 * c2 + l3 * c3, l2 * c2 + l3 * c3, l3 * c3])
    s, c = np.sin(yaw), np.cos(yaw)
    out = np.zeros((3, 4))
    out[:, 0] = (-r * c, -r * s, 0.0)
    out[0, 1:] = -s * dr
    out[1, 1:] = c * dr
    out[2, 1:] = dz
    return out


def ik_steps(world: World, delta: np.ndarray, *, damping: float = DAMPING, posture: float = POSTURE,
             iterations: int = ITERATIONS) -> np.ndarray:
    """Joint steps (units of ``spec.step``, in -2..2) that move the rest angles so the fingertip's
    equilibrium point shifts by ``delta`` from where the fingertip is now."""
    spec = world.spec
    target = world.tip() + np.asarray(delta, dtype=float)
    target[2] = max(float(target[2]), FLOOR)
    home = np.asarray(spec.home, dtype=float)
    q = world.rest.copy()
    eye3 = np.eye(3)
    for _ in range(iterations):
        err = target - forward(spec, q)[3]
        j = jacobian(spec, q)
        inverse = j.T @ np.linalg.inv(j @ j.T + damping * damping * eye3)  # damped pseudo-inverse (4, 3)
        dq = inverse @ err + (np.eye(4) - inverse @ j) @ (posture * (home - q))
        q = np.clip(q + dq, world.low, world.high)
    return np.clip((q - world.rest) / spec.step, -2.0, 2.0)


def execute(world: World, answer, pools: str, hook=None) -> dict:
    """One decision of the world from slot indices: Cartesian through the reflex, or joint
    levels as they are. ``hook(frame_index)`` runs after each physics frame when given."""
    answer = np.asarray(answer)
    if pools == "cartesian":
        steps, close = ik_steps(world, delta_of(answer)), int(answer[3])
    else:
        steps, close = steps_of(answer[:4]), int(answer[4])
    return world.decide_frames(steps, close, hook)
