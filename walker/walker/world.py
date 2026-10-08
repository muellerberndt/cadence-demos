"""The beat paid by the world, as the reward-rhythm chamber of Cadence's ``benchmarks/rhythm``
defines it (``protocol-reward-2.json``).

Every moment the walker sees the same drive and pays nothing. A step on the other foot than
its last step earns ``ALTERNATE``, paid at the next moment as the outcome of that step; a
repeated step earns ``REPEAT``; the first step of a life earns ``REPEAT``. A silent moment
(the floor frozen) is all zeros and a distractor moment sets the distractor coordinate alone;
the rule holds at every moment. Nothing in the observation says which foot moved last.

On the page's track a changed step moves the walker one cell forward and a repeated step is
a stumble. ``tests/test_world.py`` compares this module against the chamber's own code when a
Cadence checkout is at hand.
"""

from __future__ import annotations

import numpy as np

INPUTS = 4
ACTIONS = 2
DRIVE, DISTRACTOR, CUE_A, CUE_B = range(INPUTS)
KIND_DRIVE, KIND_PAUSE, KIND_DISTRACTOR = range(3)
KINDS = ("drive", "pause", "distractor")
FEET = ("L", "R")
ALTERNATE = 1.0
REPEAT = 0.0


def observation(kind: int) -> np.ndarray:
    """One stream's observation for a moment of ``kind``: ``(1, INPUTS)``."""
    x = np.zeros((1, INPUTS))
    if kind == KIND_PAUSE:
        return x
    if kind == KIND_DISTRACTOR:
        x[0, DISTRACTOR] = 1.0
        return x
    if kind != KIND_DRIVE:
        raise ValueError(f"unknown moment kind {kind!r}")
    x[0, DRIVE] = 1.0
    return x


def pay(previous: int | None, action: int) -> float:
    """The world's rule: a step that differs from the last step earns, a repeat does not."""
    if previous is None:
        return REPEAT
    return ALTERNATE if action != previous else REPEAT


def beat(actions: list[int]) -> float:
    """The share of successive steps that changed foot."""
    if len(actions) < 2:
        return 0.0
    return float(np.mean([a != b for a, b in zip(actions, actions[1:], strict=False)]))


class Track:
    """The walker's place on the track and its ledger: a changed step moves it one cell."""

    def __init__(self) -> None:
        self.previous: int | None = None
        self.position = 0
        self.steps: list[int] = []
        self.paid: list[float] = []

    def step(self, action: int) -> dict:
        reward = pay(self.previous, action)
        changed = self.previous is not None and action != self.previous
        if changed:
            self.position += 1
        self.previous = action
        self.steps.append(action)
        self.paid.append(reward)
        return {
            "action": action,
            "foot": FEET[action],
            "changed": bool(changed),
            "reward": reward,
            "position": self.position,
        }

    def recent_beat(self, window: int = 50) -> float:
        return beat(self.steps[-window:])

    def income(self, window: int = 100) -> float:
        recent = self.paid[-window:]
        return float(np.mean(recent)) if recent else 0.0
