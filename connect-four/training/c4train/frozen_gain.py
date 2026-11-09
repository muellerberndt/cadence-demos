"""The apical normalization's gain set by the free phase and held through the nudged phases.

In the free phase every pool's apical drive is ``g * u`` with ``g = F rms(b) / sqrt(rms(u)^2 +
rms(b)^2)`` recomputed every sweep (the bound on the loop). Where the drive sits at its bound the
normalization keeps the direction of ``u`` alone: a nudged phase's change of ``u`` along ``u`` is
suppressed and the rest scaled down, so the credit a lower region receives is distorted. Here the
nudged phases read the free state's gain per row and pool and pass ``g_free * u``: the nudge's
change of the top-down input arrives undistorted at the gain the free phase set. The free phase and
its fixed point are the library's. NumPy path only (a test before any library form).
"""

from __future__ import annotations

import numpy as np

_HELD: dict = {"gain": None}


def install(brain) -> None:
    import cadence.brain as graph_module

    apical_cls = graph_module.Apical
    if not getattr(apical_cls, "_frozen_gain_installed", False):
        original = apical_cls.drive

        def drive(self, basal, raw, given=None):
            if given is not None:  # a library that holds the gain itself
                return original(self, basal, raw, given)
            held = _HELD["gain"]
            if held is None or held[0] is not self:
                return original(self, basal, raw)
            out = np.zeros_like(raw)
            for k, members in enumerate(self.members):
                out[:, members] = held[1][k] * raw[:, members]
            return out

        apical_cls.drive = drive
        apical_cls._frozen_gain_installed = True
    learner = brain.learner
    nudged = learner.nudged

    def frozen(drive, free_state, target, sign=1.0, weight=None):
        graph = learner.brain
        apical = graph.apical
        if apical is None:
            return nudged(drive, free_state, target, sign, weight)
        s = np.atleast_2d(np.asarray(free_state.activation))
        d = np.atleast_2d(np.asarray(drive, float))
        basal, raw = graph._split_input(s, *graph._apical_transports())
        basal = basal + d + graph.bias
        gains = []
        for members in apical.members:
            b2 = np.mean(basal[:, members] ** 2, axis=1, keepdims=True)
            u2 = np.mean(raw[:, members] ** 2, axis=1, keepdims=True)
            gains.append(apical.fraction * np.sqrt(b2) / np.sqrt(u2 + apical.floor ** 2 * b2 + 1e-24))
        _HELD["gain"] = (apical, gains)
        try:
            return nudged(drive, free_state, target, sign, weight)
        finally:
            _HELD["gain"] = None

    learner.nudged = frozen
