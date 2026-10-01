"""A trained fast actor and separately owned recursive feedback worker.

Every action is a qualified settlement. Feedback is a fixed input, delayed one
block and valid for one block, with an additional sensory-age expiry. Create a
new actor per episode. No learning occurs in this actor: trained candidates are
loaded before the worker starts. Thread scheduling provides no hard deadline.
"""

from __future__ import annotations

import time

import numpy as np
from cadence import LiveController


class Observer:
    def __init__(self, brain):
        self.brain = brain
        self.records = []

    def __call__(self, observation):
        started = time.monotonic()
        result = self.brain.settle(observation["inputs"])
        self.records.append(
            {
                "source_tick": observation["tick"],
                "qualified": result["qualified"],
                "sweeps": result["sweeps"],
                "work": result["work"],
                "seconds": time.monotonic() - started,
            }
        )
        return {
            "qualified": result["qualified"],
            "command": (
                observation["tick"],
                observation["time"],
                *result["outputs"]["answer"],
            ),
        }


class FastSlowActor:
    def __init__(
        self,
        fast,
        slow,
        outputs,
        *,
        period=8,
        max_age=4.0,
        enabled=True,
        attention=None,
        clock=time.monotonic,
    ):
        if (
            type(period) is not int
            or period <= 0
            or type(outputs) is not int
            or outputs <= 0
        ):
            raise ValueError("positive integer period and output width required")
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        self.fast, self.outputs = fast, outputs
        self.period, self.max_age, self.enabled, self.clock = (
            period,
            max_age,
            enabled,
            clock,
        )
        self.observer = Observer(slow)
        self.attention = attention
        self.controller = LiveController(
            self.observer,
            fallback=(-1, 0, *([0] * outputs)),
            max_age=max_age,
            clock=clock,
        )
        self.tick = 0
        self.pending = {}
        self.rows = []
        self.closed = False

    def step(self, features):
        if self.closed:
            raise ValueError("actor closed")
        started = self.clock()
        source, submitted, *values = self.controller.read()
        source = int(source)
        if source < 0:
            self.pending.clear()  # refusal, error or expired latest result
        else:
            self.pending[source] = (submitted, values)
        self.pending = {
            t: value
            for t, value in self.pending.items()
            if self.tick < t + 2 * self.period and started - value[0] <= self.max_age
        }
        eligible = [t for t in self.pending if t + self.period <= self.tick]
        used = max(eligible) if eligible and self.enabled else -1
        feedback = self.pending[used][1] if used >= 0 else [0.0] * self.outputs
        result = self.fast.settle(
            {"features": np.asarray(features).tolist(), "feedback": feedback}
        )
        due = (
            self.attention.due(self.tick, features)
            if self.attention
            else self.tick % self.period == 0
        )
        if result["qualified"] and due:
            self.controller.submit(
                {
                    "tick": self.tick,
                    "time": started,
                    "inputs": {
                        "features": np.asarray(features).tolist(),
                        "readback": [*result["state"], *result["errors"]],
                    },
                }
            )
        row = {
            "tick": self.tick,
            "qualified": result["qualified"],
            "output": result["outputs"]["answer"] if result["qualified"] else None,
            "feedback_source_tick": used,
            "feedback_age_seconds": started - self.pending[used][0]
            if used >= 0
            else None,
            "feedback": feedback,
            "sweeps": result["sweeps"],
            "work": result["work"],
            "seconds": self.clock() - started,
        }
        self.rows.append(row)
        self.tick += 1
        return row

    def close(self):
        self.closed = True
        if not self.controller.close(timeout=10):
            raise RuntimeError(
                "slow worker still owns the observer after close timeout"
            )
        return {
            "fast": self.rows,
            "slow": self.observer.records,
            "runtime": self.controller.inspect(),
            "attention": self.attention.rows if self.attention else None,
        }
