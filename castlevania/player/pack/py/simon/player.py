"""The brain plays: one decision every 12 frames, greedy, frozen (nothing is learned here).

Each decision the eye reads the screen and RAM, ``Brain.act`` settles the whole brain warm
from the previous decision's state and answers four slots, and the pad holds that answer for
12 frames. ``snapshot()`` is what the page draws, all of it read from the brain at that
decision: the settle sweep by sweep (``cadence.recording.record_settlements``), the strength of
every projection between populations (|weight x presynaptic activation| summed, excitatory and
inhibitory apart), the strongest synapses, the motor slots' choice probabilities, and which
recall slots the read attended, each slot tied to the decision that wrote it.
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import numpy as np

from .eye import SLICES, Eye, fovea_window
from .pad import ACTIONS, SLOTS, buttons_of, from_slots, readings

BRAIN = Path(__file__).resolve().parents[1] / "brain" / "brain.npz"
# populations drawn neuron by neuron (the recall memory's 827-wide regions by their scene part)
DRAWN = ("module_0", "association", "prefrontal", "motor")
SCENE = SLICES["scene"]
MEMORY = ("recall", "recall_1", "next", "next_1")
BUNDLES = (("sensory", "module_0"), ("module_0", "association"), ("association", "module_0"),
           ("prefrontal", "association"), ("association", "motor"), ("motor", "association"),
           ("recall", "association"), ("recall_1", "association"), ("next", "association"),
           ("next_1", "association"))
THREADS = 10  # strongest synapses kept per drawn bundle


def load_brain(path: Path = BRAIN, backend: str = "cpu"):
    from cadence import Brain
    brain = Brain.load(path, backend=backend)
    brain.reset()
    return brain


def populations(path: Path) -> dict[str, list[int]]:
    with np.load(path, allow_pickle=False) as f:
        return json.loads(str(f["meta"]))["populations"]


def q8(values, lo: float = -0.1, hi: float = 1.0) -> str:
    """Activations as bytes (0..255 over [lo, hi]), base64: the page decodes them per sweep."""
    v = np.clip((np.asarray(values, float) - lo) / (hi - lo), 0, 1)
    return base64.b64encode(np.round(v * 255).astype(np.uint8).tobytes()).decode()


class Player:
    def __init__(self, brain, populations_: dict[str, list[int]]) -> None:
        self.brain = brain
        self.index = {k: np.asarray(v) for k, v in populations_.items() if "/" not in k}
        graph = brain.brain
        self.pre, self.post = np.asarray(graph.connectome.pre), np.asarray(graph.connectome.post)
        owner = np.full(graph.connectome.n, -1)
        names = list(self.index)
        for i, name in enumerate(names):
            owner[self.index[name]] = i
        self.bundle_rows = {}
        for a, z in BUNDLES:
            if a in self.index and z in self.index:
                rows = np.flatnonzero((owner[self.pre] == names.index(a)) & (owner[self.post] == names.index(z)))
                if len(rows):
                    self.bundle_rows[f"{a}>{z}"] = rows
        self.position = {}  # a neuron's index within its population
        for name, idx in self.index.items():
            for k, n in enumerate(idx):
                self.position[int(n)] = (name, k)
        self.eye = Eye()
        self.decisions = 0
        self.last = None
        self.thumbs: dict[int, str] = {}  # decision -> the frame it saw (small PNG), for the recall view

    def new_game(self) -> None:
        self.brain.reset()
        self.eye = Eye()
        self.decisions = 0
        self.last = None
        self.thumbs = {}

    def decide(self, frame, ram, thumb: str | None = None) -> int:
        x = self.eye.observe(frame, ram)
        action = self.decide_input(x, ram, thumb)
        self.eye.executed(action)
        return action

    def decide_input(self, x, ram=None, thumb: str | None = None) -> int:
        """One decision from a given eye input (the player page's live mode feeds recorded ones)."""
        from cadence.recording import record_settlements
        x = np.asarray(x, float)
        records = []
        t0 = time.perf_counter()
        with record_settlements(records.append):
            parts = self.brain.act(x[None, :], greedy=True)
        ms = (time.perf_counter() - t0) * 1000
        action = from_slots(parts[0])
        if thumb is not None:
            self.thumbs[self.decisions] = thumb
            for old in [k for k in self.thumbs if k < self.decisions - 400]:
                del self.thumbs[old]
        self.decisions += 1
        free = max(records, key=lambda r: np.asarray(r.activation).shape[0]) if records else None
        self.last = {"x": x, "action": action, "ms": ms, "ram": None if ram is None else np.asarray(ram).copy(),
                     "settle": dict(self.brain.last_settlement or {}),
                     "trajectory": None if free is None else np.asarray(free.activation)[:, 0, :]}
        return action

    def _recall(self) -> dict:
        recall = getattr(self.brain, "recall", None)
        if recall is None:
            return {}
        held = np.asarray(recall.held)[0]
        ages = np.asarray(recall.ages(), float)
        told = int(np.asarray(recall.told).reshape(-1)[0])
        attended = getattr(recall, "_attended", None)
        weights = np.zeros(len(held)) if attended is None else np.asarray(attended, float)[0]
        written = [int(told - 1 - a) if h else -1 for a, h in zip(ages, held)]
        order = np.argsort(-weights)[:3]
        top = [{"slot": int(j), "weight": round(float(weights[j]), 3), "decision": written[j],
                "ago": int(self.decisions - 1 - written[j]),
                "thumb": self.thumbs.get(written[j])} for j in order if weights[j] > 0.05 and written[j] >= 0]
        return {"capacity": int(getattr(recall, "capacity", len(held))), "held": int(held.sum()),
                "heads": int(getattr(recall, "heads", 1)), "slots": len(held),
                "weights": np.round(weights, 3).tolist(),
                "ages": [int(a) if h else -1 for a, h in zip(ages, held)], "top": top}

    def snapshot(self) -> dict:
        if self.last is None:
            return {"decisions": 0}
        x, ram, traj = self.last["x"], self.last["ram"], self.last["trajectory"]
        activation = np.asarray(self.brain._activity().activation)[0]  # the settled state (read only)
        if traj is None:
            traj = activation[None, :]
        sweeps = {name: [q8(traj[s, self.index[name]]) for s in range(len(traj))]
                  for name in DRAWN if name in self.index}
        memory = {name: q8(traj[-1, self.index[name][SCENE[0]:SCENE[1]]])
                  for name in MEMORY if name in self.index}
        change = np.abs(np.diff(traj, axis=0)).max(axis=1) if len(traj) > 1 else np.zeros(1)
        weights = np.asarray(self.brain.brain.weights)
        bundles, threads = {}, []
        for key, rows in self.bundle_rows.items():
            flow = weights[rows] * activation[self.pre[rows]]
            bundles[key] = [round(float(flow[flow > 0].sum()), 3), round(float(-flow[flow < 0].sum()), 3)]
            for r in rows[np.argsort(-np.abs(flow))[:THREADS]]:
                pa, ia = self.position[int(self.pre[r])]
                pz, iz = self.position[int(self.post[r])]
                threads.append([pa, ia, pz, iz, round(float(flow[np.searchsorted(rows, r)]), 3)])
        motor = activation[self.index["motor"]]
        temp = float(self.brain.learner.config.temperature)
        slots, probs, start = [], [], 0
        for size in SLOTS:
            m = motor[start:start + size]
            z = np.exp((m - m.max()) / temp)
            slots.append(np.round(m, 3).tolist())
            probs.append(np.round(z / z.sum(), 3).tolist())
            start += size
        eye = {k: np.round(x[a:b], 3).tolist() for k, (a, b) in SLICES.items()}
        fovea, game = None, None
        if ram is not None:
            left, top, right, bottom, facing = fovea_window(ram)
            fovea = {"left": left, "top": top, "right": right, "bottom": bottom, "facing": facing}
            game = readings(ram)
        settle = self.last["settle"]
        return {"decisions": self.decisions, "action": self.last["action"],
                "buttons": buttons_of(self.last["action"]), "act": list(ACTIONS[self.last["action"]]),
                "act_ms": round(self.last["ms"], 1), "sweeps": settle.get("steps"),
                "qualified": settle.get("qualified"), "residual": settle.get("max_residual"),
                "slots": slots, "probs": probs, "eye": eye,
                "drive": round(float(np.abs(x).mean()), 4),
                "motion": round(float(np.abs(x[SLICES["motion"][0]:SLICES["motion"][1]]).mean()), 4),
                "trajectory": {"sweeps": len(traj) - 1, "change": np.round(change, 5).tolist(),
                               "regions": sweeps, "memory": memory},
                "bundles": bundles, "threads": threads,
                "regions": {name: np.round(activation[self.index[name]], 3).tolist()
                            for name in DRAWN if name in self.index},
                "memory": self._recall(),
                "fovea": fovea, "game": game}
