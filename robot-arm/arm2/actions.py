"""Cartesian equilibrium-point actions through the IK reflex on the Panda, and joint pools.

Cartesian pools (5, 5, 5, 2) as in ``arm1.actions``: dx, dy, dz at -2..+2 cm per decision and
the gripper. The reflex: target = tcp + shift (height floored at ``FLOOR``), then
``PandaWorld.solve_ik`` from the present equilibrium posture (``data.ctrl[:7]``): three
damped-least-squares iterations on the tcp site's position and orientation (the hand kept
pointing down) with ``mj_jacSite``, a null-space bias toward the home posture, the change
clipped to ``BOUND`` radians per joint per decision. Joint pools: seven joints at five levels of
``JOINT_STEP`` radians each and the gripper.
"""

from __future__ import annotations

import numpy as np

from arm1.actions import HOLD, LEVELS_CM, STEP_M, delta_of

from .scene import PandaWorld

CARTESIAN_SLOTS = (5, 5, 5, 2)
JOINT_SLOTS = (5, 5, 5, 5, 5, 5, 5, 2)
POOLS = {"cartesian": CARTESIAN_SLOTS, "joint": JOINT_SLOTS}
JOINT_STEP = 0.03
FLOOR = 0.010
BOUND = 0.15
__all__ = [
    "CARTESIAN_SLOTS",
    "HOLD",
    "JOINT_SLOTS",
    "LEVELS_CM",
    "POOLS",
    "STEP_M",
    "execute",
    "grip_index",
    "hold_answer",
    "motion",
    "one_hot",
    "slots_of",
    "target_of",
]


def slots_of(pools: str) -> tuple[int, ...]:
    return POOLS[pools]


def grip_index(pools: str) -> int:
    return len(slots_of(pools)) - 1


def motion(pools: str) -> slice:
    return slice(0, grip_index(pools))


def hold_answer(pools: str, closed: bool) -> np.ndarray:
    return np.array([HOLD] * grip_index(pools) + [int(closed)], dtype=np.int64)


def one_hot(answer, pools: str) -> np.ndarray:
    out = np.zeros(int(sum(slots_of(pools))))
    offset = 0
    for k, size in enumerate(slots_of(pools)):
        out[offset + int(answer[k])] = 1.0
        offset += size
    return out


def target_of(world: PandaWorld, answer) -> np.ndarray:
    target = world.tip() + delta_of(answer)
    target[2] = max(float(target[2]), FLOOR)
    return target


def joint_target(world: PandaWorld, answer) -> np.ndarray:
    levels = np.asarray(answer[:7], dtype=float) - HOLD
    return np.clip(world.rest() + levels * JOINT_STEP, world.low, world.high)


def execute(world: PandaWorld, answer, pools: str, hook=None) -> dict:
    answer = np.asarray(answer)
    if pools == "cartesian":
        q, close = world.solve_ik(world.rest(), target_of(world, answer), bound=BOUND), int(answer[3])
    else:
        q, close = joint_target(world, answer), int(answer[7])
    world.last_command = one_hot(answer, pools)
    return world.decide(q, close, hook)
