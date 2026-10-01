"""Declared surprise scheduler, separate from learned patch dynamics.

The cheap first monitor predicts persistence of the next sensory features.
Prediction error is calibrated on TRAINING transitions. It is a control for a
future learned world-prediction monitor, not semantic surprise or a brain model.
It changes only observer duty; it never changes actions or settlement criteria.
"""

import numpy as np


def threshold_from_training(sequences, width):
    errors = np.concatenate(
        [
            np.sqrt(np.mean(np.diff(s["x"][:, :width], axis=0) ** 2, axis=1))
            for s in sequences
            if not s["split"]
        ]
    )
    return max(1e-6, float(np.quantile(errors, 0.95)))


class SurpriseAttention:
    def __init__(self, threshold, *, width, period=8, passive_blocks=4, burst_blocks=2):
        if (
            not np.isfinite(threshold)
            or threshold <= 0
            or min(width, period, passive_blocks, burst_blocks) < 1
        ):
            raise ValueError("positive finite threshold and dimensions required")
        self.threshold, self.width, self.period = threshold, width, period
        self.passive_blocks, self.burst_blocks = passive_blocks, burst_blocks
        self.previous = None
        self.active_until = -1
        self.rows = []

    def due(self, tick, features):
        current = np.asarray(features, dtype=float)[: self.width]
        error = (
            None
            if self.previous is None
            else float(np.sqrt(np.mean((current - self.previous) ** 2)))
        )
        surprising = error is not None and error > self.threshold
        if surprising:
            self.active_until = tick + self.burst_blocks * self.period
        active = tick <= self.active_until
        due = tick % self.period == 0 and (
            active or tick % (self.period * self.passive_blocks) == 0
        )
        self.rows.append(
            {
                "tick": tick,
                "prediction_error": error,
                "surprising": surprising,
                "active": active,
                "submit": due,
            }
        )
        self.previous = current.copy()
        return due
