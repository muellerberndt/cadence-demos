"""The true-state observation of the contact cell, in ``arm1.senses``'s style.

Population codes of Gaussian bumps (15 centres over a span, sigma 0.75 of the spacing; the
relative terms in the warped coordinate ``u = sign(d) sqrt(min(|d|, R) / R)``). The layout for
the Cartesian pools, ``inputs("cartesian")`` = 262 values:

| slice | size | what |
| --- | --- | --- |
| 0..45 | 3 x 15 | tcp x, y, z over ``HAND_SPAN`` |
| 45..90 | 3 x 15 | block centre minus tcp, warped |
| 90..135 | 3 x 15 | release point (the ordered bin at the carrying height) minus tcp, warped; zero without an order |
| 135..184 | 7 x 7 | the seven joint angles, seven bumps over each joint's range (the spindles) |
| 184..191 | 7 | the gripper's opening, seven bumps over 0..4 cm |
| 191..193 | 2 | gripper commanded closed; holding (from contacts) |
| 193..242 | 7 x 7 | the seven joint velocities, seven bumps over +-2 rad/s; zero under ``--no-velocity`` |
| 242..259 | 17 | the efference copy: the brain's own last command, one-hot per slot (37 on joint pools) |
| 259..262 | 3 | the lamp, one-hot over (none, A, B) |

The blind twin zeroes 45..135 (both object terms).
"""

from __future__ import annotations

import numpy as np

from arm1.senses import BINS, absolute_code, relative_code

from .actions import slots_of
from .scene import ORDERS, PandaWorld

AXES = 3
JOINT_BINS = 7
HAND_SPAN = ((0.20, 0.80), (-0.40, 0.40), (0.00, 0.50))
RELATIVE_REACH = (0.60, 0.60, 0.45)
VELOCITY_SPAN = 2.0
OPENING_SPAN = (0.0, 0.04)
HAND = slice(0, AXES * BINS)
BLOCK = slice(HAND.stop, HAND.stop + AXES * BINS)
BIN = slice(BLOCK.stop, BLOCK.stop + AXES * BINS)
OBJECT = slice(BLOCK.start, BIN.stop)
JOINTS = slice(BIN.stop, BIN.stop + 7 * JOINT_BINS)
OPENING = slice(JOINTS.stop, JOINTS.stop + JOINT_BINS)
FLAGS = slice(OPENING.stop, OPENING.stop + 2)
VELOCITY = slice(FLAGS.stop, FLAGS.stop + 7 * JOINT_BINS)


def efference(pools: str) -> slice:
    return slice(VELOCITY.stop, VELOCITY.stop + int(sum(slots_of(pools))))


def lamp(pools: str) -> slice:
    e = efference(pools)
    return slice(e.stop, e.stop + len(ORDERS))


SLIP_REACH = 0.5  # m/s: the block's velocity relative to the fingertips, warped like the relative positions
FORCE_SPAN = (0.0, 30.0)  # N: the fingers' normal force on the block, seven bumps


def slip_slice(pools: str) -> slice:
    """Stage 2b's slip senses, appended after the lamp so every earlier slice keeps its place:
    relative velocity x, y, z (3 x 15) and the finger contact force (7)."""
    la = lamp(pools)
    return slice(la.stop, la.stop + AXES * BINS + JOINT_BINS)


def inputs(pools: str, slip: bool = False) -> int:
    return slip_slice(pools).stop if slip else lamp(pools).stop


def joint_code(value: float, lo: float, hi: float, bins: int = JOINT_BINS) -> np.ndarray:
    centres = np.linspace(lo, hi, bins)
    sigma = (hi - lo) / (bins - 1) * 0.75
    return np.exp(-0.5 * ((value - centres) / sigma) ** 2)


def observe(world: PandaWorld, pools: str, velocity: bool = True, slip: bool = False) -> np.ndarray:
    tip = world.tip()
    block = world.block_pos()
    parts = [absolute_code(float(tip[i]), HAND_SPAN[i]) for i in range(AXES)]
    parts += [relative_code(float(block[i] - tip[i]), RELATIVE_REACH[i]) for i in range(AXES)]
    release = world.release_point()
    for i in range(AXES):
        parts.append(np.zeros(BINS) if release is None else relative_code(float(release[i] - tip[i]), RELATIVE_REACH[i]))
    q = world.joints()
    parts += [joint_code(float(q[j]), float(world.low[j]), float(world.high[j])) for j in range(7)]
    parts.append(joint_code(world.opening(), *OPENING_SPAN))
    parts.append(np.array([float(world.closed), float(world.holding)]))
    if velocity:
        v = world.velocities()
        parts += [joint_code(float(v[j]), -VELOCITY_SPAN, VELOCITY_SPAN) for j in range(7)]
    else:
        parts.append(np.zeros(7 * JOINT_BINS))
    size = int(sum(slots_of(pools)))
    parts.append(np.zeros(size) if world.last_command is None else np.asarray(world.last_command, dtype=float))
    lit = np.zeros(len(ORDERS))
    lit[int(world.order)] = 1.0
    parts.append(lit)
    if slip:
        rel = world.relative_velocity()
        parts += [relative_code(float(rel[i]), SLIP_REACH) for i in range(AXES)]
        parts.append(joint_code(world.contact_force(), *FORCE_SPAN))
    return np.concatenate(parts)


def observe_batch(worlds, pools: str, velocity: bool = True, slip: bool = False) -> np.ndarray:
    return np.stack([observe(w, pools, velocity, slip) for w in worlds])


def blind(x: np.ndarray) -> np.ndarray:
    out = np.array(x, dtype=float, copy=True)
    out[..., OBJECT] = 0.0
    return out


def layout(pools: str, slip: bool = False) -> dict:
    e, la, sl = efference(pools), lamp(pools), slip_slice(pools)
    return {"inputs": inputs(pools, slip), "slip": [sl.start, sl.stop] if slip else None, "bins": BINS, "joint_bins": JOINT_BINS,
            "hand": [HAND.start, HAND.stop],
            "block_minus_hand": [BLOCK.start, BLOCK.stop], "release_minus_hand": [BIN.start, BIN.stop],
            "joints": [JOINTS.start, JOINTS.stop], "opening": [OPENING.start, OPENING.stop], "flags": [FLAGS.start, FLAGS.stop],
            "velocity": [VELOCITY.start, VELOCITY.stop], "efference": [e.start, e.stop], "lamp": [la.start, la.stop],
            "hand_span_m": HAND_SPAN, "relative_reach_m": RELATIVE_REACH, "velocity_span_rad_s": VELOCITY_SPAN,
            "relative_warp": "u = sign(d) * sqrt(min(|d|, R) / R)", "blind_zeroes": [OBJECT.start, OBJECT.stop]}
