"""The brain plays: one decision every 12 frames, greedy, frozen (nothing is learned here).

Each decision the eye reads the screen and RAM, ``Brain.act`` settles the whole brain warm
from the previous decision's state and answers four slots, and the pad holds that answer for
12 frames. ``snapshot()`` is what the page draws.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from .eye import SLICES, Eye, fovea_window
from .pad import ACTIONS, SLOTS, buttons_of, from_slots, readings

BRAIN = Path(__file__).resolve().parents[1] / "brain" / "brain.npz"
SHOWN = ("module_0", "association", "prefrontal", "motor")


def load_brain(path: Path = BRAIN, backend: str = "cpu"):
    from cadence import Brain
    return Brain.load(path, backend=backend)


def populations(path: Path) -> dict[str, list[int]]:
    with np.load(path, allow_pickle=False) as f:
        return json.loads(str(f["meta"]))["populations"]


class Player:
    def __init__(self, brain, populations_: dict[str, list[int]]) -> None:
        self.brain = brain
        self.index = {k: np.asarray(v) for k, v in populations_.items() if k in SHOWN}
        self.eye = Eye()
        self.decisions = 0
        self.last = None

    def new_game(self) -> None:
        self.brain.reset()
        self.eye = Eye()
        self.decisions = 0
        self.last = None

    def decide(self, frame, ram) -> int:
        x = self.eye.observe(frame, ram)
        t0 = time.perf_counter()
        parts = self.brain.act(x[None, :], greedy=True)
        ms = (time.perf_counter() - t0) * 1000
        action = from_slots(parts[0])
        self.eye.executed(action)
        self.decisions += 1
        self.last = {"x": x, "action": action, "ms": ms, "ram": np.asarray(ram).copy(),
                     "settle": dict(self.brain.last_settlement or {})}
        return action

    def snapshot(self) -> dict:
        if self.last is None:
            return {"decisions": 0}
        x, ram = self.last["x"], self.last["ram"]
        activation = np.asarray(self.brain._activity().activation)[0]  # the settled state (read only)
        regions = {name: np.round(activation[idx], 3).tolist() for name, idx in self.index.items()}
        motor = activation[self.index["motor"]] if "motor" in self.index else np.zeros(sum(SLOTS))
        slots, start = [], 0
        for size in SLOTS:
            slots.append(np.round(motor[start:start + size], 3).tolist())
            start += size
        eye = {k: np.round(x[a:b], 3).tolist() for k, (a, b) in SLICES.items()}
        left, top, right, bottom, facing = fovea_window(ram)
        memory = {}
        recall = getattr(self.brain, "recall", None)
        if recall is not None:
            held = np.asarray(recall.held)
            memory = {"held": int(held[0].sum()) if held.ndim == 2 else int(held.sum()),
                      "capacity": int(getattr(recall, "capacity", held.shape[-1])),
                      "heads": int(getattr(recall, "heads", 1))}
            focus = getattr(recall, "focus", None)
            if focus is not None:
                f = np.asarray(focus, dtype=float)
                if f.ndim >= 2 and f.shape[0] == 1:
                    memory["focus"] = np.round(f[0], 3).reshape(-1, f.shape[-1]).tolist()
        settle = self.last["settle"]
        return {"decisions": self.decisions, "action": self.last["action"],
                "buttons": buttons_of(self.last["action"]), "act": list(ACTIONS[self.last["action"]]),
                "act_ms": round(self.last["ms"], 1), "sweeps": settle.get("steps"),
                "qualified": settle.get("qualified"), "residual": settle.get("max_residual"),
                "slots": slots, "regions": regions, "eye": eye, "memory": memory,
                "fovea": {"left": left, "top": top, "right": right, "bottom": bottom, "facing": facing},
                "game": readings(ram)}
