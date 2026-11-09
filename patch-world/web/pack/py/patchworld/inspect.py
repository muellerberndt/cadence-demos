"""What the page's brain view draws: one moment of one brain, read from its real state.

``Inspector`` wraps the ``live`` call (a twin's ``act``) of the creature the visitor clicked. It
records every settle of the call (``cadence.record_settlements``) and keeps the one the action
was read from, sweep by sweep; reads every synapse's efficacy before and after the call (the
synapses this moment's learning changed); sums, for every bundle of synapses between two
populations, the signal it carried in the settled state (weight times presynaptic activation,
excitatory and inhibitory apart); and reads the dopamine of the moment's lesson, the arousal,
the associative store's write, and the recall memory's attention over its slots, with the
moment each attended slot stored (its place and what lay underfoot, from the observation the
creature had then).

Nothing here changes the brain: recording copies, and the recall memory's attention is read.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any

import numpy as np

from .world import FOOD_NAMES, N_INPUTS

# where each block of the 38 sensory neurons comes from (patchworld/world.py: input_names)
SENSE_GROUPS = {
    "vision": [0, 24],  # four directions x six kinds
    "underfoot": [24, 29],  # berry, root, leaf, cache, water beside it
    "body": [29, 34],  # energy, thirst, light, nausea, cold
    "place": [34, 38],  # sin and cos of each coordinate
}
SHOWN = ("sensory", "module_0", "association", "prefrontal", "motor", "recall", "next")
FRAMES = 18  # sweeps of the settle sent to the page (evenly spaced, the last always)


class Inspector:
    def __init__(self, brain: Any, width: int = 48, height: int = 32) -> None:
        self.brain = brain
        self.width, self.height = width, height
        self.history: deque = deque(maxlen=200)  # this creature's observations, newest last
        c = brain.connectome
        # the drawn populations only (a slot group such as "motor/actions" is part of "motor")
        self.pops = {k: np.asarray(v) for k, v in c.populations.items() if len(v) and k in SHOWN}
        owner = np.full(c.n, "", dtype=object)
        for k in SHOWN:
            if k in self.pops:
                owner[self.pops[k]] = k
        self.pre, self.post = np.asarray(c.pre), np.asarray(c.post)
        # sensory synapses are bundled by sense (vision, underfoot, body, place)
        if "sensory" in self.pops:
            sens = self.pops["sensory"]
            for group, (lo, hi) in SENSE_GROUPS.items():
                owner[sens[lo:hi]] = "sensory:" + group
        names = owner[self.pre] + ">" + owner[self.post]
        self.tracts: dict[str, np.ndarray] = {}
        for key in np.unique(names):
            a, b = key.split(">")
            if a and b:
                self.tracts[str(key)] = np.nonzero(names == key)[0]

    def anatomy(self) -> dict[str, Any]:
        """The populations and tracts (sent once per selection)."""
        recall = self.brain.recall
        return {"populations": {k: int(len(v)) for k, v in self.pops.items()},
                "tracts": {k: int(len(v)) for k, v in self.tracts.items()},
                "senses": SENSE_GROUPS,
                "slots": int(recall.capacity) if recall is not None else 0,
                "neurons": int(self.brain.connectome.n), "synapses": int(len(self.pre))}

    def efficacy(self) -> np.ndarray:
        return np.asarray(self.brain.learner.brain.efficacy, dtype=float).copy()

    def observe(self, observation: np.ndarray) -> None:
        self.history.append(np.asarray(observation, dtype=float).copy())

    def read(self, records: list, before: np.ndarray | None) -> dict[str, Any]:
        brain = self.brain
        out: dict[str, Any] = {}
        state = brain.basal_ganglia.state
        final = None if state is None else np.asarray(state.activation)[0]
        act = None  # the settle the action was read from: its last state is the acted state
        if final is not None:
            for r in reversed(records):
                a = np.asarray(r.activation)
                if a.ndim == 3 and a.shape[2] == len(final) and np.allclose(a[-1, 0], final, atol=1e-9):
                    act = r
                    break
        weights = None
        if act is not None:
            hist = np.asarray(act.activation)[:, 0, :]
            pot = np.asarray(act.potential)[:, 0, :]
            steps = hist.shape[0] - 1
            pick = sorted(set(np.linspace(0, steps, min(FRAMES, steps + 1)).round().astype(int).tolist()))
            out["frames"] = [{k: [round(float(x), 3) for x in hist[i, v]]
                              for k, v in self.pops.items() if k in SHOWN} for i in pick]
            moves = np.abs(np.diff(pot, axis=0)).max(axis=1) if steps else np.zeros(0)
            out["frame_sweeps"] = [int(i) for i in pick]
            out["movement"] = [float(moves[i - 1]) if i else None for i in pick]
            out["sweeps"] = int(steps)
            w = np.asarray(act.weights, dtype=float).ravel()
            weights = w if len(w) == len(self.pre) else None
        out["settles_recorded"] = len(records)
        if final is not None and weights is not None:
            flow = weights * final[self.pre]
            out["tracts"] = {k: [round(float(flow[v][flow[v] > 0].sum()), 4),
                                 round(float(-flow[v][flow[v] < 0].sum()), 4)]
                             for k, v in self.tracts.items()}
        if before is not None:
            after = self.efficacy()
            if len(before) == len(after):
                dw = after - before
                changed = np.abs(dw) > 1e-12
                out["changed"] = int(changed.sum())
                out["changed_by_tract"] = {k: [int(changed[v].sum()), round(float(np.abs(dw[v]).sum()), 6)]
                                           for k, v in self.tracts.items() if changed[v].any()}
        ar = brain.last_arousal or {}
        out["arousal"] = {"mode": ar.get("mode"), "level": float(ar.get("level", 0.0) or 0.0),
                          "surprise": float(ar.get("surprise", 0.0) or 0.0),
                          "want": float(ar.get("want", 0.0) or 0.0),
                          "learned": bool(ar.get("learned", False)),
                          "recorded": bool(ar.get("recorded", False))}
        ll = brain.last_learning or {}
        if out["arousal"]["learned"] and ll:
            out["dopamine"] = {k: float(ll[k]) for k in ("dopamine", "td_error", "value") if k in ll}
        out["recall"] = self._recall()
        return out

    def _recall(self) -> dict[str, Any] | None:
        recall = self.brain.recall
        if recall is None:
            return None
        try:
            _, attention = recall.reading()
            ages = np.asarray(recall.ages()).ravel()
        except Exception:  # no read this moment (a first or a refused moment)
            return {"slots": int(recall.capacity), "read": []}
        att = None if attention is None else np.asarray(attention, dtype=float).reshape(-1)
        if att is None or len(att) != len(ages):
            return {"slots": int(recall.capacity), "read": []}
        read = []
        for s in np.argsort(-att)[:6]:
            if att[s] < 0.02:
                continue
            age = int(ages[s])
            entry: dict[str, Any] = {"slot": int(s), "weight": round(float(att[s]), 4), "age": age}
            if 0 <= age < len(self.history):  # age k: the moment k moments before this one
                entry.update(self._moment(self.history[-1 - age]))
            read.append(entry)
        return {"slots": int(recall.capacity), "read": read,
                "ages": [int(a) for a in ages]}

    def _moment(self, obs: np.ndarray) -> dict[str, Any]:
        sx, cx, sy, cy = (2.0 * obs[34:38] - 1.0)
        x = (math.atan2(sx, cx) / (2 * math.pi)) % 1.0 * self.width
        y = (math.atan2(sy, cy) / (2 * math.pi)) % 1.0 * self.height
        under = [FOOD_NAMES[k + 1] for k in range(3) if obs[24 + k] > 0.5]
        if obs[27] > 0.5:
            under.append("cache")
        if obs[28] > 0.5:
            under.append("water")
        return {"x": round(float(x), 1), "y": round(float(y), 1), "underfoot": under,
                "nausea": round(float(obs[32]), 2)}


assert N_INPUTS == 38
