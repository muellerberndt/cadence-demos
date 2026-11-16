"""The Showcase League's host: the ring, the robots and their continuing brains, in the browser.

The same arena code that ran the leagues on the laptop and the 192-vCPU box runs here in
Pyodide: ``arena.world`` for the physics, ``arena.senses`` for the observation, ``arena.brain``
for one continuing ``Brain.live`` life per robot, and the royale's own reward and frame
functions, so a fight in the page is the fight the league would have run. The page asks for
moments; the host answers with the replay-format frames (pose, hit points, mood and the
settled brain activity of every robot) and, when a fight ends, the placements and what each
brain is owed at the start of its next fight. Brains are saved and restored as the library's
own checkpoints, so the page can keep them in the browser between visits.
"""

from __future__ import annotations

import base64
import json
from contextlib import nullcontext
import math
import os
import time
import types
from typing import Any

import numpy as np


def fit_32_bit_numpy() -> bool:
    """Pyodide's numpy is 32-bit: ``np.repeat`` with int64 counts refuses the cast. The
    library's learning module gets a numpy whose ``repeat`` casts the counts; nothing changes
    on 64 bits (the walker demo's shim)."""
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


SHIMMED = fit_32_bit_numpy()

from arena.brain import RobotBrain, hold_commands, motor_names, set_stage  # noqa: E402
from arena.parts import blueprint_from_dict  # noqa: E402
from arena.royale import (  # noqa: E402
    APPROACH_CAP,
    APPROACH_PAY,
    DAMAGE_SCALE,
    Fighter,
    _frame,
    _nearest_gap,
    place_score,
)
from arena.senses import input_names, observe  # noqa: E402
from arena.world import Arena, Robot  # noqa: E402
from cadence import record_settlements  # noqa: E402

TRAJECTORY_EVERY = 8  # the inspected brain's full settle, sweep by sweep, every this many moments
TRAJECTORY_FRAMES = 18  # sweeps sent per settle (first, last and evenly between; the movement of every sweep)
TRACT_SAMPLE = 36  # synapses drawn per projection, the strongest
TOP_CHANGES = 48  # the largest synaptic changes of a moment that the page flashes


def _value(brain) -> float | None:
    """The critic's value of the state the brain last acted from (``Brain.live`` keeps it with its
    pending action), or None before a first action."""
    lived = getattr(brain, "_lived", None)
    return None if lived is None else float(lived[2])


def _prediction_error(brain, before: float | None, owed) -> float | None:
    """The reward prediction error of this moment's outcome, signed: the library's TD error when the
    outcome was learned from, otherwise reward + gamma * value(now) - value(before), the formula the
    arousal law reads (unsigned there)."""
    learning = getattr(brain, "last_learning", None) or {}
    if "td_error" in learning and (brain.last_arousal or {}).get("learned"):
        return round(float(learning["td_error"]), 4)
    if before is None or owed is None:
        return None
    reward, ended = float(owed[0]), bool(owed[1])
    now = _value(brain)
    following = 0.0 if ended or now is None else now
    return round(reward + float(brain.basal_ganglia.config.gamma) * following - before, 4)


class Host:
    def __init__(self, roster: list[dict[str, Any]], brain_dir: str, stage: dict[str, Any] | None = None) -> None:
        # the ring stage of a life: need, heat, temperature as the manifest says; the reset of
        # "what life used to pay" happens once, when a brain enters the ring from the pack
        self.stage = dict(stage or {})
        self.roster = {r["name"]: r for r in roster}
        self.blueprints = {n: blueprint_from_dict(r["blueprint"]) for n, r in self.roster.items()}
        self.brain_dir = brain_dir
        self.brains: dict[str, RobotBrain] = {}
        self.owed: dict[str, tuple[float, bool] | None] = {n: None for n in self.roster}
        self.fight: dict[str, Any] | None = None
        self.ms_per_moment = 0.0
        for name in self.roster:
            self.load_pack_brain(name)

    # -- brains

    def load_pack_brain(self, name: str) -> None:
        self.brains[name] = RobotBrain.load(self.blueprints[name], os.path.join(self.brain_dir, f"{name}.npz"))
        set_stage(self.brains[name].brain, self.stage)
        owed = self.roster[name].get("owed")
        self.owed[name] = None if owed is None else (float(owed[0]), bool(owed[1]))

    def restore(self, brains: dict[str, str], owed: dict[str, Any] | None = None) -> dict[str, Any]:
        restored = []
        for name, b64 in brains.items():
            if name not in self.roster:
                continue
            path = f"/tmp/restore-{name}.npz"
            with open(path, "wb") as f:
                f.write(base64.b64decode(b64))
            self.brains[name] = RobotBrain.load(self.blueprints[name], path)
            set_stage(self.brains[name].brain, {k: v for k, v in self.stage.items() if k != "reset"})
            self.owed[name] = None  # a restored checkpoint carries its own saved outcome
            restored.append(name)
        if owed:
            for name, o in owed.items():
                if name in self.owed:
                    self.owed[name] = None if o is None else (float(o[0]), bool(o[1]))
        return {"restored": restored}

    def save(self) -> dict[str, Any]:
        out = {}
        for name, brain in self.brains.items():
            path = brain.save(f"/tmp/save-{name}.npz")
            with open(path, "rb") as f:
                out[name] = base64.b64encode(f.read()).decode()
        return {"brains": out, "owed": {n: (None if o is None else [o[0], o[1]]) for n, o in self.owed.items()}}

    def reset(self, names: list[str] | None = None) -> dict[str, Any]:
        for name in names or list(self.roster):
            self.load_pack_brain(name)
        return {"reset": names or list(self.roster)}

    def describe(self) -> dict[str, Any]:
        return {
            "shimmed": SHIMMED,
            "stage": self.stage,
            "robots": {
                name: {
                    **self.roster[name],
                    "inputs": input_names(self.blueprints[name]),
                    "slots": self.blueprints[name].slots,
                    "motors": motor_names(self.blueprints[name]),
                    "radius": self.blueprints[name].radius,
                    "hp": self.blueprints[name].hp,
                    "chassis": self.blueprints[name].chassis,
                    "parts": [p.to_dict() for p in self.blueprints[name].parts],
                    "brain": self.brains[name].describe(),
                }
                for name in self.roster
            },
        }

    # -- a fight, moment by moment

    def new_fight(
        self, names: list[str], seed: int, duration: int = 1200, zone_moments: int = 1000, zone_end: float = 2.5
    ) -> dict[str, Any]:
        fighters = [
            Fighter(name=n, blueprint=self.blueprints[n], policy="brain", owed=self.owed[n]) for n in names
        ]
        robots = [Robot.build(i, f.blueprint) for i, f in enumerate(fighters)]
        arena = Arena(robots, radius=10.0, zone_end=float(zone_end), zone_moments=zone_moments, seed=int(seed))
        self.fight = {
            "fighters": fighters,
            "robots": robots,
            "arena": arena,
            "duration": int(duration),
            "seed": int(seed),
            "t": 0,
            "feedback": {f.name: f.owed for f in fighters},
            "last_reward": {f.name: 0.0 for f in fighters},
            "acc": {
                f.name: {"moments": 0, "aroused": 0, "sweeps": 0, "learning_sweeps": 0, "refused": 0,
                         "dealt": 0.0, "taken": 0.0, "burn": 0.0, "hits": 0, "outside": 0, "travelled": 0.0}
                for f in fighters
            },
            "done": False,
            "results": None,
        }
        specs = [
            {
                "name": f.name, "policy": "brain", "chassis": f.blueprint.chassis, "radius": f.blueprint.radius,
                "hp": f.blueprint.hp, "parts": [p.to_dict() for p in f.blueprint.parts],
                "inputs": input_names(f.blueprint), "slots": f.blueprint.slots, "motors": motor_names(f.blueprint),
                "lineage": self.roster[f.name].get("lineage"), "elo": self.roster[f.name].get("elo"),
            }
            for f in fighters
        ]
        return {"robots": specs, "frame": _frame(arena, fighters, {}, {}), "seed": int(seed), "duration": int(duration)}

    def step(self, n: int = 1, inspect: str | None = None) -> dict[str, Any]:
        F = self.fight
        if F is None:
            raise ValueError("no fight; call new_fight first")
        frames = []
        began = time.perf_counter()
        moments = 0
        for _ in range(int(n)):
            if F["done"]:
                break
            arena: Arena = F["arena"]
            alive = arena.alive()
            if len(alive) <= 1 or F["t"] >= F["duration"]:
                F["done"] = True
                F["results"] = self._finish()
                break
            fighters = F["fighters"]
            readings = {}
            inspected = None
            for robot in alive:
                f = fighters[robot.rid]
                owed = F["feedback"][f.name]
                watched = f.name == inspect
                records: list = []
                life = self.brains[f.name]
                w0 = np.array(life.brain.learner.brain.weights, copy=True) if watched else None
                v0 = _value(life.brain) if watched else None
                with record_settlements(records.append) if watched else nullcontext():
                    reading = life.moment(
                        observe(robot, arena), None if owed is None else owed[0], False if owed is None else owed[1]
                    )
                readings[f.name] = reading
                if watched:
                    inspected = self._inspect(life.brain, records, w0, F["t"])
                    inspected["rpe"] = _prediction_error(life.brain, v0, None if owed is None else owed)
            before = {robot.rid: (robot.x, robot.y) for robot in alive}
            gap_before = {robot.rid: _nearest_gap(robot, alive) for robot in alive}
            commands = {}
            for robot in alive:
                f = fighters[robot.rid]
                r = readings[f.name]
                commands[robot.rid] = r["commands"] if not r["refused"] else hold_commands(f.blueprint)
                a = F["acc"][f.name]
                a["moments"] += 1
                a["aroused"] += int(r["aroused"])
                a["sweeps"] += r["sweeps"]
                a["learning_sweeps"] += r["learning_sweeps"]
                a["refused"] += int(r["refused"])
            out = arena.step(commands)
            for robot in alive:
                f = fighters[robot.rid]
                o = out[robot.rid]
                reward = (o["dealt"] - o["taken"]) / DAMAGE_SCALE
                closed = gap_before[robot.rid] - _nearest_gap(robot, arena.alive())
                if math.isfinite(closed):
                    reward += float(np.clip(APPROACH_PAY * closed, -APPROACH_CAP, APPROACH_CAP))
                F["last_reward"][f.name] = reward
                F["feedback"][f.name] = (reward, False)
                a = F["acc"][f.name]
                a["dealt"] += o["dealt"]
                a["taken"] += o["taken"]
                a["burn"] += o["zone"]
                a["hits"] += len(robot.hits)
                a["outside"] += int(o["outside"])
                bx, by = before[robot.rid]
                a["travelled"] += math.hypot(robot.x - bx, robot.y - by)
            frame = _frame(arena, fighters, readings, F["last_reward"])
            if inspected is not None:
                frame["inspect"] = inspected
            frames.append(frame)
            F["t"] += 1
            moments += 1
        if moments:
            self.ms_per_moment = (time.perf_counter() - began) * 1000.0 / moments
        if not F["done"]:
            arena = F["arena"]
            if len(arena.alive()) <= 1 or F["t"] >= F["duration"]:
                F["done"] = True
                F["results"] = self._finish()
        return {
            "frames": frames,
            "t": F["t"],
            "done": F["done"],
            "results": F["results"],
            "ms_per_moment": round(self.ms_per_moment, 2),
        }

    def _finish(self) -> dict[str, Any]:
        F = self.fight
        assert F is not None
        arena: Arena = F["arena"]
        arena.finish()
        n = len(F["fighters"])
        results = []
        for robot in F["robots"]:
            f = F["fighters"][robot.rid]
            assert robot.place is not None
            score = place_score(robot.place, n)
            self.owed[f.name] = (F["last_reward"][f.name] + score, True)
            a = F["acc"][f.name]
            m = max(1, a["moments"])
            results.append(
                {
                    "name": f.name, "place": robot.place, "score": round(score, 3), "alive": robot.alive,
                    "hp": round(robot.hp, 1), "died_at": robot.died_at, "moments": a["moments"],
                    "dealt": round(a["dealt"], 1), "taken": round(a["taken"], 1), "burn": round(a["burn"], 1),
                    "hits": a["hits"], "moments_outside": a["outside"], "travelled_m": round(a["travelled"], 1),
                    "aroused_share": round(a["aroused"] / m, 3), "sweeps_per_moment": round(a["sweeps"] / m, 1),
                    "learning_sweeps": a["learning_sweeps"], "refused": a["refused"],
                }
            )
        results.sort(key=lambda r: r["place"])
        return {"results": results, "owed": {k: (None if v is None else [v[0], v[1]]) for k, v in self.owed.items()}, "seed": F["seed"], "moments": F["t"]}

    # -- the page's protocol

    # -- the brain inspector: real state of one brain

    def anatomy(self, name: str) -> dict[str, Any]:
        """The brain's populations and, per projection, its strongest synapses (the tracts the
        inspector draws), with every population's neuron indices."""
        brain = self.brains[name].brain
        c = brain.connectome
        groups: dict[tuple[int, ...], str] = {}
        for pop, members in c.populations.items():
            key = tuple(int(i) for i in members)
            if key and (key not in groups or len(pop) < len(groups[key])):
                groups[key] = pop
        pops = sorted(({"name": n, "index": list(k)} for k, n in groups.items()), key=lambda p: p["index"][0])
        label = np.full(c.n, -1, dtype=np.int64)
        for k, p in enumerate(pops):
            label[p["index"]] = k
        pre, post = np.asarray(c.pre), np.asarray(c.post)
        w = np.asarray(brain.learner.brain.weights)
        tracts = []
        for a, b in sorted(set(zip(label[pre].tolist(), label[post].tolist()))):
            idx = np.flatnonzero((label[pre] == a) & (label[post] == b))
            top = idx[np.argsort(-np.abs(w[idx]), kind="stable")[:TRACT_SAMPLE]]
            tracts.append({"pre": pops[a]["name"] if a >= 0 else "?", "post": pops[b]["name"] if b >= 0 else "?",
                           "synapses": int(len(idx)), "drawn": [int(i) for i in top],
                           "from": [int(i) for i in pre[top]], "to": [int(i) for i in post[top]],
                           "w": [round(float(x), 4) for x in w[top]]})
        recall = getattr(brain, "recall", None)
        return {"name": name, "neurons": int(c.n), "synapses": int(c.synapses), "populations": pops, "tracts": tracts,
                "sensory": [int(i) for i in brain.sensory_index], "motor": [int(i) for i in brain.motor_index],
                "recall_capacity": int(recall.capacity) if recall is not None else 0}

    def _inspect(self, brain, records: list, w0: np.ndarray, t: int) -> dict[str, Any]:
        """What the watched brain did in this moment, read from the brain itself: its act's settle
        (every sweep's movement; the sweeps themselves every TRAJECTORY_EVERY moments), the learning
        settles, the synapses that changed, the critic's error, arousal and the recall memory's reads."""
        free = [r for r in records if r.nudge is None and r.steps > 0]
        nudged = [r for r in records if r.nudge is not None]
        act = max(free, key=lambda r: r.steps) if free else None
        out: dict[str, Any] = {"t": int(t), "settles": len(records), "learning_settles": len(nudged),
                               "learning_sweeps": int(sum(r.steps for r in nudged))}
        if act is not None:
            a = np.asarray(act.activation)[:, 0, :]
            move = np.abs(np.diff(a, axis=0)).max(axis=1) if len(a) > 1 else np.zeros(0)
            out["sweeps"] = int(act.steps)
            out["movement"] = [round(float(x), 5) for x in move]
            out["state"] = [round(float(x), 2) for x in a[-1]]
            if t % TRAJECTORY_EVERY == 0 and len(a) > 1:
                pick = np.unique(np.linspace(0, len(a) - 1, min(TRAJECTORY_FRAMES, len(a))).round().astype(int))
                q = np.clip((a[pick] + 0.1) / 1.1 * 255.0, 0, 255).astype(np.uint8)
                out["trajectory"] = {"sweeps": [int(k) for k in pick], "neurons": int(a.shape[1]),
                                     "q": base64.b64encode(q.tobytes()).decode("ascii")}
        w1 = np.asarray(brain.learner.brain.weights)
        dw = w1 - w0
        changed = np.flatnonzero(dw)
        top = changed[np.argsort(-np.abs(dw[changed]), kind="stable")[:TOP_CHANGES]] if len(changed) else changed
        pre, post = np.asarray(brain.connectome.pre), np.asarray(brain.connectome.post)
        out["plasticity"] = {"changed": int(len(changed)), "max": round(float(np.abs(dw).max()), 6) if len(changed) else 0.0,
                             "top": [int(i) for i in top], "delta": [round(float(dw[i]), 6) for i in top],
                             "pre": [int(pre[i]) for i in top], "post": [int(post[i]) for i in top],
                             "w": [round(float(w1[i]), 4) for i in top]}
        info = brain.last_arousal or {}
        out["arousal"] = {k: (round(float(info[k]), 4) if isinstance(info.get(k), float) else info.get(k))
                          for k in ("mode", "level", "error", "surprise", "want", "learned", "heated_slot")}
        recall = getattr(brain, "recall", None)
        if recall is not None:
            ages = np.atleast_1d(np.asarray(recall.ages(), dtype=float))  # moments since each slot was written
            # every head's attention over the slots in the latest read, (streams, slots) each, or None before
            # a read; the strongest read of each stored moment over the heads and streams
            heads = [np.asarray(h, dtype=float) for h in (recall.attended_heads or ()) if h is not None]
            read = np.max([h.reshape(-1, h.shape[-1]).max(axis=0) for h in heads], axis=0) if heads else np.zeros(0)
            k = min(len(ages), len(read))
            order = np.argsort(-read[:k])[:6] if k else []
            out["recall"] = {"stored": int(len(ages)), "capacity": int(recall.capacity),
                             "reads": [[int(j), int(ages[j]), round(float(read[j]), 3)] for j in order if read[j] > 0.01]}
        return out

    def handle_json(self, text: str) -> str:
        m = json.loads(text)
        op = m.get("op")
        if op == "describe":
            return json.dumps(self.describe())
        if op == "new_fight":
            return json.dumps(self.new_fight(m["names"], int(m.get("seed", 0)), int(m.get("duration", 1200)), int(m.get("zone_moments", 1000))))
        if op == "step":
            return json.dumps(self.step(int(m.get("n", 1)), m.get("inspect")))
        if op == "anatomy":
            return json.dumps(self.anatomy(m["name"]))
        if op == "save":
            return json.dumps(self.save())
        if op == "restore":
            return json.dumps(self.restore(m.get("brains", {}), m.get("owed")))
        if op == "reset":
            return json.dumps(self.reset(m.get("names")))
        raise ValueError(f"unknown op {op!r}")
