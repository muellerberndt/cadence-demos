"""One continuing life in the cell: a decision, the frames until its outcome, the next decision.

Three ways a moment can go, chosen by the caller per decision:

- ``shown``: the caregiver drives the arm; the brain watches, and every observation is a
  lesson through ``step(x, teacher=labels)``. The episodic memory records demonstrations.
- ``corrected``: the brain drives; after an executed disagreement the caregiver labels the
  current observation, the recipe of the Stone Age V5 chamber.
- ``alone``: the brain drives with no labels, through ``step`` or, for a calm routine that
  learns only on surprise, through ``live``.

The world's reward and the end of an attempt (a placement) arrive with the next observation.
Frames between decisions can be waited: the brain settles them without taking an outcome.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from cadence import Brain

from . import caregiver
from .anatomy import EYE_SLOTS
from .eyes import Eyes
from .world import World, steps_of

EYE = len(EYE_SLOTS)  # the motor slots start after the eye's readouts


def labels_of(world: World, eyes: Eyes) -> np.ndarray:
    """One label per slot: the eye's readouts in its own coordinates, then the caregiver's pools."""
    return np.array([eyes.labels(world) + caregiver.labels(world)], dtype=np.int64)


def aroused_of(brain: Brain) -> bool | None:
    """Whether the stream is aroused this moment, when the brain has arousal genes."""
    a = getattr(brain, "arousal", None)
    if a is None:
        return None
    value = getattr(a, "aroused", None)
    if value is None:
        return None
    arr = np.atleast_1d(np.asarray(value))
    return bool(arr[0]) if arr.size else None


@dataclass
class Life:
    brain: Brain
    world: World
    eyes: Eyes
    waits: int = 0  # frames settled between decisions, evenly spaced
    continuation: str = "step"  # "step" or "live" for alone moments
    done_marks: bool = True  # a placement ends an attempt
    pending: tuple[float, bool] | None = None  # the last decision's outcome; None before the first
    moments: int = 0
    log: list[dict[str, Any]] = field(default_factory=list)
    last_error: str = ""

    def observe(self) -> np.ndarray:
        return self.eyes.inputs(self.world)[None]

    def moment(self, mode: str) -> dict[str, Any]:
        if mode not in ("shown", "corrected", "alone"):
            raise ValueError(mode)
        world, brain = self.world, self.brain
        x = self.observe()
        labels = labels_of(world, self.eyes)
        feedback = {} if self.pending is None else {"reward": [self.pending[0]], "done": [self.pending[1]]}
        start = time.perf_counter()
        teach = mode == "shown" or (mode == "corrected" and bool(self.log) and self.log[-1]["disagreed"])
        refused = False
        try:
            if mode == "alone" and self.continuation == "live":
                out = brain.live(x, **feedback)
            else:
                out = brain.step(x, teacher=labels if teach else None, **feedback)
        except RuntimeError as error:
            refused, out = True, None
            self.last_error = str(error)
        answer = None if out is None else np.asarray(out)[0]
        own = None if answer is None else [int(v) for v in answer[EYE:EYE + 5]]
        want = [int(v) for v in labels[0, EYE:EYE + 5]]
        if mode == "shown" or own is None:
            steps, close = steps_of(want[:4]), want[4]
        else:
            steps, close = steps_of(own[:4]), own[4]
        outcome = world.decide_frames(steps, close, self._wait_frames())
        self.pending = (float(outcome["reward"]), bool(outcome["done"] and self.done_marks))
        row = {
            "moment": self.moments, "mode": mode, "taught": bool(teach), "refused": refused,
            "own": own, "want": want, "disagreed": own is not None and own != want,
            "event": outcome["event"], "reward": outcome["reward"], "done": outcome["done"],
            "sweeps": int((brain.last_settlement or {}).get("steps", 0)),
            "aroused": aroused_of(brain),
            "ms": round((time.perf_counter() - start) * 1000, 1),
            "placed": world.placed, "wrong": world.wrong, "dropped": world.dropped,
        }
        self.log.append(row)
        self.moments += 1
        return row

    def _wait_frames(self):
        """A callback the world calls between frames; waits the brain where declared."""
        if self.waits <= 0:
            return None
        every = max(self.world.spec.frames_per_decision // (self.waits + 1), 1)

        def hook(frame_index: int) -> None:
            if frame_index % every == 0 and frame_index < self.world.spec.frames_per_decision:
                try:
                    self.brain.wait(self.observe())
                except (RuntimeError, ValueError):
                    pass

        return hook

    def run(self, decisions: int, mode: str) -> list[dict[str, Any]]:
        return [self.moment(mode) for _ in range(decisions)]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Placements right and wrong, drops, agreement with the caregiver, cost per decision."""
    if not rows:
        return {}
    n = len(rows)
    agree = [r["own"] == r["want"] for r in rows if r["own"] is not None]
    events = [r["event"] for r in rows]
    right = sum(1 for e in events if e and e.endswith(":right"))
    wrong = sum(1 for e in events if e and e.endswith(":wrong"))
    return {
        "decisions": n, "placed_right": right, "placed_wrong": wrong,
        "dropped": sum(1 for e in events if e == "dropped"),
        "grasped": sum(1 for e in events if e == "grasped"), "missed": sum(1 for e in events if e == "missed"),
        "agreement": None if not agree else round(float(np.mean(agree)), 3),
        "taught": sum(1 for r in rows if r["taught"]), "refused": sum(1 for r in rows if r["refused"]),
        "sweeps": round(float(np.mean([r["sweeps"] for r in rows])), 1),
        "ms": round(float(np.mean([r["ms"] for r in rows])), 1),
        "reward": round(float(sum(r["reward"] for r in rows)), 2),
    }
