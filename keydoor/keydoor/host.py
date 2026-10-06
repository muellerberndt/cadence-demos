"""The creature host of the page: one continuing ``Brain.compose`` life in the key-door
corridor, one moment at a time.

The same class runs natively in the tests and in Pyodide in the page's worker. Every moment
the host delivers the preceding action's outcome with the next observation, once, through
``Brain.live``; the brain answers from a routine settle while calm and samples, learns and
writes memory while aroused. The host reports what the world saw (the cell, the action, the
event, the outcome) and what the brain reports of itself (its mode, want, level, heat, the
sweeps of the moment, the probability of interacting under the behaviour that acted and under
its base policy). A refused answer keeps its outcome inside the brain for one retry, as the
library defines it, and is reported as such; nothing is invented for it.

The brain is the frozen key-door protocol's ``live`` arm: ``Brain.compose(6, 2, modules=(32,))``
at the chamber's operating point, with the arousal founders and the chamber's need. A raised
creature is one that lived rule A on that protocol before it was saved; a newborn starts here.
"""

from __future__ import annotations

import base64
import io
import json
import os
import tempfile
from dataclasses import replace
from typing import Any

import numpy as np
from cadence import ArousalConfig, Brain

from .world import CHEST, INTERACT, KINDS, LAMP, World, observe

POINT: dict[str, Any] = {
    "modules": [32],
    "trace_amplitude": 0.3,
    "consolidation": 0.25,
    "eta": 0.1,
    "lam": 0.95,
    "gamma": 0.95,
    "eta_critic": 5.0,
}
NEED = 0.03


def fit_32_bit_numpy() -> bool:
    """Pyodide's numpy is 32-bit: its index type is int32, and ``np.repeat`` with int64
    counts refuses the cast. The library's learning module gets a numpy whose ``repeat`` casts
    the counts; every other call is numpy's own. Nothing changes on 64 bits."""
    if np.dtype(np.intp).itemsize >= 8:
        return False
    import types

    import cadence.learning as learning

    shim = types.ModuleType("numpy")
    shim.__dict__.update(np.__dict__)
    shim.repeat = lambda a, repeats, axis=None: np.repeat(
        a, np.asarray(repeats).astype(np.intp), axis=axis)
    learning.np = shim
    return True


def newborn(seed: int) -> Brain:
    """The frozen protocol's ``live`` brain at birth."""
    brain = Brain.compose(
        6, 2, modules=tuple(POINT["modules"]), seed=seed,
        working_memory_amplitude=POINT["trace_amplitude"], consolidation=POINT["consolidation"],
        arousal=ArousalConfig(need=NEED),
    )
    actor = brain.basal_ganglia.config
    brain.basal_ganglia.config = replace(
        actor, eta=POINT["eta"], eta_bias=POINT["eta"] / 10.0, lam=POINT["lam"],
        gamma=POINT["gamma"], eta_critic=POINT["eta_critic"],
    )
    return brain


class Host:
    """One creature: its brain, its corridor and the ledger of its life."""

    def __init__(self, brain: Brain | str | None, delay: int, seed: int, *, keyed: int = CHEST,
                 raised_trips: int = 0) -> None:
        self.shimmed = fit_32_bit_numpy()
        if brain is None:
            brain = newborn(seed)
        elif isinstance(brain, str):
            brain = Brain.load(brain)
        self.brain = brain
        self.world = World(delay, seed, keyed=keyed)
        self.seed = seed
        self.raised_trips = raised_trips
        self.moments = 0
        self.refusals = 0
        self.last_error: str | None = None
        self.modes = {"routine": 0, "aroused": 0}
        self.sweeps = {"routine": 0, "aroused": 0}
        self.learning_sweeps = 0
        self.ms = 0.0
        self.trip_modes: list[int] = []  # aroused moments of the trip in progress
        self.trip_wants: list[float] = []
        self.trips: list[dict] = []  # one row per trip that ended

    # -- one moment

    def moment(self) -> dict:
        import time

        world, brain = self.world, self.brain
        kind, holding = world.face()
        reward, done = world.feedback()
        x = observe(kind, holding)
        feedback = {} if reward is None else {"reward": [reward], "done": [done]}
        began = time.perf_counter()
        try:
            action = int(brain.live(x, **feedback)[0])
        except Exception as error:  # the brain keeps the outcome for one retry
            self.refusals += 1
            self.last_error = f"{type(error).__name__}: {error}"[:200]
            settlement = brain.last_settlement
            return {
                "refused": True,
                "error": self.last_error,
                "sweeps": 0 if settlement is None else int(settlement["steps"]),
                "kind": kind,
                "holding": holding,
                "trip": world.trips,
                "index": world.trip.index if world.trip else 0,
            }
        elapsed = time.perf_counter() - began
        reading = brain.last_arousal or {}
        arousal = brain.arousal
        mode = reading.get("mode", arousal.mode)
        aroused = mode == "aroused"
        agent = brain.basal_ganglia
        state = agent.state
        policy = np.asarray(agent.probabilities(state))[0]
        temperature = reading.get("temperature")
        if temperature is None:
            behaviour = np.zeros(2)
            behaviour[int(np.argmax(policy))] = 1.0
        else:
            behaviour = np.asarray(agent.probabilities(state, temperature))[0]
        cells = list(world.trip.cells) if world.trip is not None and world.trip.index == 0 else None
        record = world.act(action)
        if cells is not None:
            record["cells"] = cells  # the trip's corridor, at its first cell
        self.moments += 1
        self.modes[mode] += 1
        sweeps = int(reading.get("sweeps", 0))
        self.sweeps[mode] += sweeps
        self.learning_sweeps += int(reading.get("learning_sweeps", 0))
        self.ms += elapsed * 1000.0
        self.trip_modes.append(int(aroused))
        self.trip_wants.append(float(arousal.want))
        record.update({
            "refused": False,
            "mode": mode,
            "aroused": aroused,
            "want": round(float(arousal.want), 4),
            "level": round(float(arousal.level), 4),
            "heat": round(float(arousal.heat), 3),
            "surprise": round(float(reading.get("surprise", 0.0)), 4),
            "sweeps": sweeps,
            "learning_sweeps": int(reading.get("learning_sweeps", 0)),
            "ms": round(elapsed * 1000.0, 2),
            "p_interact": round(float(behaviour[INTERACT]), 4),
            "p_interact_policy": round(float(policy[INTERACT]), 4),
            "age": int(arousal.age),
            "keyed": world.keyed,
        })
        if record["done"] or record["cut"]:
            trip = world.trip
            assert trip is not None
            row = {
                "trip": record["trip"],
                "fed": trip.got,
                "took": trip.took,
                "wrongs": trip.wrongs,
                "cut": bool(trip.cut),
                "cells": len(trip.cells),
                "aroused": float(np.mean(self.trip_modes)) if self.trip_modes else 0.0,
                "want": float(np.mean(self.trip_wants)) if self.trip_wants else 0.0,
                "keyed": world.keyed,
            }
            self.trips.append(row)
            self.trip_modes, self.trip_wants = [], []
            record["trip_row"] = row
        return record

    def run(self, trips: int = 1, limit: int = 10_000) -> dict:
        """Live until ``trips`` more trips have ended (or ``limit`` moments), fast; returns the
        trip rows and the last moment."""
        before = len(self.trips)
        last: dict | None = None
        count = 0
        while len(self.trips) < before + trips and count < limit:
            last = self.moment()
            count += 1
        return {"rows": self.trips[before:], "last": last, "lived": count, **self.status()}

    # -- readings

    def status(self) -> dict:
        world, arousal = self.world, self.brain.arousal
        recent = world.recent(20)
        total = self.modes["routine"] + self.modes["aroused"]
        return {
            "recent": recent,
            "trips": world.trips,
            "moments": self.moments,
            "keyed": world.keyed,
            "keyed_name": KINDS[world.keyed],
            "delay": world.delay,
            "mode": arousal.mode,
            "want": round(float(arousal.want), 4),
            "level": round(float(arousal.level), 4),
            "heat": round(float(arousal.heat), 3),
            "age": int(arousal.age),
            "work": {
                "routine": self.modes["routine"],
                "aroused": self.modes["aroused"],
                "aroused_share": self.modes["aroused"] / total if total else 0.0,
                "sweeps_routine": self.sweeps["routine"],
                "sweeps_aroused": self.sweeps["aroused"],
                "learning_sweeps": self.learning_sweeps,
                "memory_writes": 0 if self.brain.hippocampus is None else int(self.brain.hippocampus.writes),
                "refusals": self.refusals,
                "ms_per_moment": self.ms / self.moments if self.moments else 0.0,
            },
        }

    def probe(self) -> dict:
        """The base policy's probability of interacting and the greedy choice per cell and pouch
        state, read on saved and reloaded copies with a blank trace; the living brain is not
        touched."""
        choices, probs = [], []
        with tempfile.TemporaryDirectory() as directory:
            path = self.brain.save(os.path.join(directory, "brain.npz"))
            for holding in (False, True):
                row_c, row_p = [], []
                for kind in range(5):
                    copy = Brain.load(path)
                    row_c.append(int(copy.act(observe(kind, holding), greedy=True)[0]))
                    st = copy.basal_ganglia.state
                    row_p.append(round(float(copy.basal_ganglia.probabilities(st)[0, INTERACT]), 4))
                choices.append(row_c)
                probs.append(row_p)
        return {"greedy": choices, "p_interact": probs}

    def describe(self) -> dict:
        import cadence

        w = self.brain.brain.connectome
        return {
            "cadence": cadence.__version__,
            "neurons": int(w.n),
            "synapses": int(w.synapses),
            "point": POINT,
            "need": NEED,
            "arousal": self.brain.arousal.config.to_dict(),
            "delay": self.world.delay,
            "seed": self.seed,
            "raised_trips": self.raised_trips,
            "shimmed": self.shimmed,
        }

    # -- continuation

    def snapshot(self) -> bytes:
        """The brain as saved, with any outcome it awaits; the world continues as it is."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.brain.save(os.path.join(directory, "brain.npz"))
            return open(path, "rb").read()

    def restore(self, data: bytes) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brain.npz")
            with open(path, "wb") as f:
                f.write(data)
            self.brain = Brain.load(path)

    # -- the page's messages

    def handle_json(self, text: str) -> str:
        message = json.loads(text)
        op = message.get("op")
        if op == "moment":
            return json.dumps(self.moment())
        if op == "run":
            return json.dumps(self.run(int(message.get("trips", 1))))
        if op == "status":
            return json.dumps(self.status())
        if op == "describe":
            return json.dumps(self.describe())
        if op == "probe":
            return json.dumps(self.probe())
        if op == "move_key":
            return json.dumps({"keyed": self.world.move_key()})
        if op == "cut":
            self.world.cut_next()
            return json.dumps({"cut": True})
        if op == "snapshot":
            return json.dumps({"brain": base64.b64encode(self.snapshot()).decode()})
        if op == "restore":
            self.restore(base64.b64decode(message["brain"]))
            return json.dumps({"restored": True, **self.status()})
        raise ValueError(f"unknown op {op!r}")
