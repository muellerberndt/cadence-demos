"""The true-state observation: what a perfect eye would deliver, supplied by the world.

Every number is a population code of Gaussian bumps in the style of the joint senses
(``World.body``: ``BINS`` centres evenly spaced over a span, sigma 0.75 of the spacing). The
layout, ``INPUTS`` = 168 values:

| slice     | size   | what |
| --- | --- | --- |
| 0..45     | 3 x 15 | fingertip x, y, z over ``HAND_SPAN``, centres uniform in the metre |
| 45..90    | 3 x 15 | block centre minus fingertip, per axis, centres uniform in the warped coordinate ``u = sign(d) sqrt(min(abs(d), R) / R)`` with ``R = RELATIVE_REACH``: the bump nearest zero is centred 1.2 cm out, the next 4.9, 11, 20, 31, 44 and 60 cm (fine where the grasp is decided, coarse far away) |
| 90..135   | 3 x 15 | the release point (the ordered bin's centre at the carrying height ``LIFT``) minus the fingertip, the same warp; zero without an order |
| 135..165  | 30     | the body: four joints of seven spindles, gripper closed, holding (``World.body``) |
| 165..168  | 3      | the lamp: one-hot over the orders (none, A, B) |

The blind twin zeroes 45..135 (``OBJECT``): both object terms, the hand, body and lamp kept.
"""

from __future__ import annotations

import numpy as np

from arm.caregiver import LIFT
from arm.world import BODY_SENSES, ORDERS, World

BINS = 15
AXES = 3
HAND_SPAN = ((-0.40, 0.40), (0.00, 0.60), (0.00, 0.45))  # metres: x, y, z of the fingertip
RELATIVE_REACH = (0.60, 0.60, 0.45)  # metres: a relative term beyond this codes as the edge
HAND = slice(0, AXES * BINS)
BLOCK = slice(HAND.stop, HAND.stop + AXES * BINS)
BIN = slice(BLOCK.stop, BLOCK.stop + AXES * BINS)
OBJECT = slice(BLOCK.start, BIN.stop)
BODY = slice(BIN.stop, BIN.stop + BODY_SENSES)
LAMP = slice(BODY.stop, BODY.stop + len(ORDERS))
INPUTS = LAMP.stop

_CENTRES = np.linspace(-1.0, 1.0, BINS)
_SIGMA = 2.0 / (BINS - 1) * 0.75


def bumps(u: float) -> np.ndarray:
    """The population code of a value ``u`` in [-1, 1] (values outside fall off the end)."""
    return np.exp(-0.5 * ((u - _CENTRES) / _SIGMA) ** 2)


def absolute_code(value: float, span: tuple[float, float]) -> np.ndarray:
    lo, hi = span
    return bumps(2.0 * (value - lo) / (hi - lo) - 1.0)


def warp(d: float, reach: float) -> float:
    return float(np.sign(d) * np.sqrt(min(abs(d), reach) / reach))


def relative_code(d: float, reach: float) -> np.ndarray:
    return bumps(warp(d, reach))


def release_point(world: World) -> np.ndarray | None:
    ordered = world.ordered_bin()
    if ordered is None:
        return None
    return np.array([ordered[0], ordered[1], LIFT])


def observe(world: World) -> np.ndarray:
    tip = world.tip()
    parts = [absolute_code(float(tip[i]), HAND_SPAN[i]) for i in range(AXES)]
    parts += [relative_code(float(world.block[i] - tip[i]), RELATIVE_REACH[i]) for i in range(AXES)]
    release = release_point(world)
    for i in range(AXES):
        parts.append(np.zeros(BINS) if release is None else relative_code(float(release[i] - tip[i]), RELATIVE_REACH[i]))
    parts.append(world.body())
    lamp = np.zeros(len(ORDERS))
    lamp[int(world.order)] = 1.0
    parts.append(lamp)
    return np.concatenate(parts)


def observe_batch(worlds) -> np.ndarray:
    return np.stack([observe(w) for w in worlds])


def blind(x: np.ndarray) -> np.ndarray:
    """The blind twin's observation: the object terms zeroed."""
    out = np.array(x, dtype=float, copy=True)
    out[..., OBJECT] = 0.0
    return out


def layout() -> dict:
    """The layout as a record for ``run.json``."""
    return {
        "inputs": INPUTS, "bins": BINS,
        "hand": [HAND.start, HAND.stop], "block_minus_hand": [BLOCK.start, BLOCK.stop],
        "release_minus_hand": [BIN.start, BIN.stop], "body": [BODY.start, BODY.stop], "lamp": [LAMP.start, LAMP.stop],
        "hand_span_m": HAND_SPAN, "relative_reach_m": RELATIVE_REACH,
        "relative_warp": "u = sign(d) * sqrt(min(|d|, R) / R)", "blind_zeroes": [OBJECT.start, OBJECT.stop],
    }
