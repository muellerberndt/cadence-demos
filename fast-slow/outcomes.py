"""Causal interface for longer-horizon outcome prediction and later learning.

This ledger is bookkeeping, not a planner or credit-assignment algorithm. It
retains the inputs and goal that existed when a prediction was issued. Outcomes
must come from an ordered, durable environment/action journal supplied by the
application. Matched rows can train an outcome-predicting Cadence candidate with
public observe_batch(source='witness'); policy/value targets derived from those
rows remain estimates. Association with an outcome does not prove action credit.
"""

import copy

import numpy as np


class OutcomeLedger:
    def __init__(self, episode, *, max_pending=1024):
        self.episode = episode
        self.tick = -1
        self.pending = {}
        self.records = []
        self.max_pending = max_pending
        self.serial = 0
        self.closed = False

    def observe(self, episode, tick, values):
        if (
            self.closed
            or episode != self.episode
            or type(tick) is not int
            or tick != self.tick + 1
        ):
            raise ValueError("outcomes must be consecutive within one episode")
        actual = np.asarray(values, dtype=float)
        if actual.ndim != 1 or not actual.size or not np.isfinite(actual).all():
            raise ValueError("finite outcome vector required")
        due = [k for k, p in self.pending.items() if p["due_tick"] == tick]
        if any(len(self.pending[k]["prediction"]) != len(actual) for k in due):
            raise ValueError("outcome dimensions differ from the forecast")
        self.tick = tick
        completed = []
        for key in due:
            forecast = self.pending.pop(key)
            record = {
                **forecast,
                "status": "observed",
                "actual": actual.tolist(),
                "residual": (actual - forecast["prediction"]).tolist(),
                "outcome_tick": tick,
            }
            self.records.append(record)
            completed.append(copy.deepcopy(record))
        return completed

    def forecast(self, *, goal, horizon, inputs, prediction, model_sha256, qualified):
        if qualified is not True:
            raise ValueError("only qualified outcome predictions may be issued")
        if self.closed or self.tick < 0 or type(horizon) is not int or horizon <= 0:
            raise ValueError(
                "observe current context before predicting a positive horizon"
            )
        if len(self.pending) >= self.max_pending:
            raise OverflowError(
                "persist or resolve pending predictions; never silently drop them"
            )
        expected = np.asarray(prediction, dtype=float)
        if expected.ndim != 1 or not expected.size or not np.isfinite(expected).all():
            raise ValueError("finite predicted vector required")
        self.serial += 1
        self.pending[self.serial] = copy.deepcopy(
            {
                "id": self.serial,
                "episode": self.episode,
                "source_tick": self.tick,
                "due_tick": self.tick + horizon,
                "goal": goal,
                "inputs": inputs,
                "prediction": expected.tolist(),
                "model_sha256": model_sha256,
            }
        )
        return self.serial

    def end(self, reason):
        """Unobserved horizons are censored, never invented zero-reward targets."""
        for forecast in self.pending.values():
            self.records.append(
                {
                    **forecast,
                    "status": "censored",
                    "reason": reason,
                    "end_tick": self.tick,
                }
            )
        self.pending.clear()
        self.closed = True
        return copy.deepcopy(self.records)
