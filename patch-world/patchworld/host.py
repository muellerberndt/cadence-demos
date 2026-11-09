"""The page's Python: the world host and the brain host, in Pyodide workers.

One worker runs ``WorldHost``: the ecosystem (world, births, deaths, inheritance, controls).
Two to four workers run ``BrainHost``: the brains of the creatures assigned to them, each one
continuing ``Brain.live`` life. The page carries the observations from the world to the brains
and the actions back, one moment at a time; a newborn's brain is its parent's, copied inside a
worker or carried between workers as the library's own checkpoint bytes.

Every request and reply is JSON; observations travel as lists of floats (36 per creature).
"""

from __future__ import annotations

import base64
import copy
import io
import json
import os
import types
from typing import Any

import numpy as np


def fit_32_bit_numpy() -> bool:
    """Pyodide's numpy is 32-bit: ``np.repeat`` with int64 counts refuses the cast. The
    library's learning module gets a numpy whose ``repeat`` casts the counts; nothing changes
    on 64 bits."""
    if np.dtype(np.intp).itemsize >= 8:
        return False
    import cadence.learning as learning

    shim = types.ModuleType("numpy")
    shim.__dict__.update(np.__dict__)
    shim.repeat = lambda a, repeats, axis=None: np.repeat(
        a, np.asarray(repeats).astype(np.intp), axis=axis
    )
    learning.np = shim
    return True


ROSTER = "founders.json"


def read_roster(folder: str) -> list[dict[str, Any]]:
    with open(os.path.join(folder, ROSTER)) as f:
        return json.load(f)["founders"]


class WorldHost:
    """The ecosystem, as the page drives it."""

    def __init__(self, folder: str, seed: int = 1, cap: int = 12, frozen: int = 2,
                 random: int = 2) -> None:
        from .ecosystem import Ecosystem
        from .world import Rules

        self.roster = read_roster(folder)
        founders = [{"genes": f["genes"], "lineage": i} for i, f in enumerate(self.roster)]
        self.eco = Ecosystem(seed, Rules(), founders=founders, cap=cap, frozen=frozen,
                             random=random)
        self.births = self.eco.populate()
        self.flips: list[int] = []
        self.history: list[dict[str, Any]] = []  # per 50 moments: berries and poisonings by kind
        self._window: dict[str, dict[str, int]] = {}

    def opening(self) -> dict[str, Any]:
        w = self.eco.world
        return {"width": w.rules.width, "height": w.rules.height,
                "terrain": w.terrain_bytes(), "births": self.births,
                "rules": {k: v for k, v in vars(w.rules).items()},
                "requests": self._requests(), "snapshot": self._snapshot()}

    def _requests(self) -> list[dict[str, Any]]:
        out = []
        for r in self.eco.requests():
            out.append({"id": r["id"], "obs": [round(float(v), 4) for v in r["obs"]],
                        "reward": r["reward"], "kind": r["kind"]})
        return out

    def _snapshot(self) -> dict[str, Any]:
        s = self.eco.world.snapshot()
        lives = self.eco.lives
        for c in s["creatures"]:
            lf = lives.get(c["id"])
            if lf is None:
                continue
            c["poisonings"] = len(lf.poison_times)
            c["last_poison"] = lf.poison_times[-1] if lf.poison_times else None
            c["good_berries"] = int(lf.stats.get("berry_summer", 0))
            c["passed_berries"] = int(lf.stats.get("refused_berry", 0))
            c["children"] = lf.children
            c["recall"] = bool(lf.genes.get("recall"))
            c["width"] = int(lf.genes.get("width", 0))
            c["depth"] = int(lf.genes.get("depth", 0))
        s["tally"] = self.eco.tally()
        s["reseeded"] = self.eco.reseeded
        s["history"] = self.history[-120:]
        s["flips"] = self.flips[-20:]
        return s

    def advance(self, replies: dict[str, Any]) -> dict[str, Any]:
        replies_int = {int(k): v for k, v in replies.items()}
        changes = self.eco.advance(replies_int)
        for e in changes["events"]:
            win = self._window.setdefault(e["kind"], {})
            win[e["event"]] = win.get(e["event"], 0) + 1
        t = self.eco.world.t
        if t % 50 == 0:
            alive: dict[str, int] = {}
            for lf in self.eco.lives.values():
                if lf.died is None:
                    alive[lf.kind] = alive.get(lf.kind, 0) + 1
            learners = [lf for lf in self.eco.lives.values() if lf.died is None and lf.kind == "live"]
            genes = {}
            if learners:
                for k in ("eta", "temperature", "threshold", "memory_rate", "sense", "size", "speed"):
                    genes[k] = round(float(np.mean([float(lf.genes[k]) for lf in learners])), 4)
                genes["recall"] = round(float(np.mean([bool(lf.genes["recall"]) for lf in learners])), 3)
                genes["generation"] = round(float(np.mean([lf.generation for lf in learners])), 2)
                genes["lineages"] = len({lf.lineage for lf in learners})
            self.history.append({"t": t, "summer": self.eco.world.summer,
                                 "events": self._window, "alive": alive, "genes": genes})
            self._window = {}
        return {"births": changes["births"], "deaths": changes["deaths"],
                "events": changes["events"], "requests": self._requests(),
                "snapshot": self._snapshot()}

    def control(self, action: str, **kw: Any) -> dict[str, Any]:
        w = self.eco.world
        if action == "flip":
            w.flip_season()
            self.flips.append(w.t)
        elif action == "food":
            from .world import BERRY, LEAF, ROOT

            kind = {"berry": BERRY, "root": ROOT, "leaf": LEAF}[kw.get("kind", "berry")]
            w.drop_food(int(kw["x"]), int(kw["y"]), kind, radius=int(kw.get("radius", 1)))
        elif action == "predator":
            if len(w.predators) < 4:
                w.add_predator(at=(int(kw["x"]), int(kw["y"])) if "x" in kw else None)
        elif action == "calm":
            w.remove_predator()
        return {"snapshot": self._snapshot()}

    def inspect(self, cid: int) -> dict[str, Any]:
        lf = self.eco.lives.get(int(cid))
        if lf is None:
            return {"gone": True}
        c = self.eco.world.creatures.get(lf.id)
        return {"id": lf.id, "kind": lf.kind, "genes": lf.genes, "lineage": lf.lineage,
                "generation": lf.generation, "parent": lf.parent, "born": lf.born,
                "income": round(lf.income, 2), "expense": round(lf.expense, 2),
                "children": lf.children, "poison_times": lf.poison_times[-12:],
                "berry_times": lf.berry_times[-12:], "age": c.age if c else None,
                "stats": {k: int(v) for k, v in lf.stats.items()}}

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        cmd = message.get("command")
        p = message.get("payload") or {}
        if cmd == "opening":
            return self.opening()
        if cmd == "advance":
            return self.advance(p["replies"])
        if cmd == "control":
            return self.control(p.pop("action"), **p)
        if cmd == "inspect":
            return self.inspect(p["id"])
        raise ValueError(f"unknown command {cmd!r}")


class BrainHost:
    """The brains of the creatures assigned to this worker."""

    def __init__(self, folder: str, seed: int = 0) -> None:
        from .brain import load

        self.roster = read_roster(folder)
        self.founders = [load(os.path.join(folder, f["file"])) for f in self.roster]
        from .ecosystem import LocalMinds

        self.minds = LocalMinds(self.founders, seed=seed)
        self.last: dict[int, dict[str, Any]] = {}

    def born(self, births: list[dict[str, Any]], brains: dict[str, str] | None = None) -> dict:
        """New creatures for this worker. A child whose parent lives in another worker comes
        with its parent's brain as checkpoint bytes (base64) in ``brains``."""
        from .brain import FrozenMind, LiveMind, RandomMind, retune

        brains = brains or {}
        for b in births:
            key = str(b["id"])
            if key in brains:
                brain = self._from_bytes(brains[key])
                if b["genes"]["recall"] and brain.recall is None:
                    brain = brain.grow(recall=True)
                retune(brain, b["genes"])
                self.minds.minds[b["id"]] = LiveMind(brain)
            else:
                self.minds.born([b])
        return {"minds": len(self.minds.minds)}

    def export(self, cid: int) -> str:
        """A living creature's brain as checkpoint bytes, for its child in another worker."""
        mind = self.minds.minds[int(cid)]
        return self._to_bytes(mind.brain)

    @staticmethod
    def _to_bytes(brain: Any) -> str:
        path = "/tmp/_export.npz"
        brain.save(path)
        with open(path, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()

    @staticmethod
    def _from_bytes(text: str) -> Any:
        from .brain import load

        path = "/tmp/_import.npz"
        with open(path, "wb") as f:
            f.write(base64.b64decode(text))
        return load(path)

    def answer(self, requests: list[dict[str, Any]], detail: int | None = None) -> dict:
        out: dict[str, Any] = {}
        for r in requests:
            mind = self.minds.minds.get(int(r["id"]))
            if mind is None:
                continue
            reply = mind.moment(np.asarray(r["obs"], dtype=float), r["reward"],
                                detail=int(r["id"]) == detail)
            out[str(r["id"])] = reply
        return {"replies": out}

    def died(self, ids: list[int]) -> dict:
        self.minds.died([{"id": int(i)} for i in ids])
        return {"minds": len(self.minds.minds)}

    def describe(self, cid: int) -> dict:
        mind = self.minds.minds.get(int(cid))
        if mind is None or not hasattr(mind, "brain"):
            return {"brain": None}
        brain = mind.brain
        c = brain.connectome
        d: dict[str, Any] = {"neurons": int(c.n), "synapses": int(c.synapses),
                             "populations": {k: len(v) for k, v in c.populations.items()},
                             "moments": mind.moments, "refusals": mind.refusals,
                             "learning_sweeps": int(mind.sweeps_total)}
        if brain.arousal is not None:
            d["arousal"] = {"age": int(brain.arousal.age),
                            "modes": {k: int(v) for k, v in brain.arousal.moments.items()}}
        return d

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        cmd = message.get("command")
        p = message.get("payload") or {}
        if cmd == "born":
            return self.born(p["births"], p.get("brains"))
        if cmd == "answer":
            return self.answer(p["requests"], p.get("detail"))
        if cmd == "died":
            return self.died(p["ids"])
        if cmd == "export":
            return {"brain": self.export(p["id"])}
        if cmd == "describe":
            return self.describe(p["id"])
        if cmd == "anatomy":
            mind = self.minds.minds.get(int(p["id"]))
            if mind is None or not hasattr(mind, "brain"):
                return {"anatomy": None}
            return {"anatomy": mind._inspector().anatomy()}
        if cmd == "ping":
            return {"minds": len(self.minds.minds)}
        raise ValueError(f"unknown command {cmd!r}")


def as_json(obj: Any) -> str:
    def default(o: Any) -> Any:
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(type(o).__name__)

    return json.dumps(obj, default=default, allow_nan=False)
