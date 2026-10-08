"""The walker host of the page: one continuing ``Brain.live`` life on the beat paid by the
world, one moment at a time.

The same class runs natively in the tests and in Pyodide in the page's worker. Every moment
the host delivers the preceding step's pay with the next observation, once, through
``Brain.live``; the brain answers from a routine settle while calm and samples, learns and
keeps eligibility while aroused. The host reports what the world saw (the foot, whether it
changed, the pay, the place on the track) and what the brain reports of itself (its mode,
want, level and heat, the sweeps of the moment, the copy it carries of its own last command,
its two motor activations and its base policy's belief in the beat, the probability of the
other foot than the last). A refused answer keeps its outcome inside the brain for one retry,
as the library defines it, and is reported as a missed step; nothing is invented for it.

The brain is the reward-rhythm chamber's ``live`` arm of ``protocol-reward-2.json``:
``Brain.compose(4, 2, modules=(32,))`` at the chamber's operating point with the efference copy
(``efference_amplitude=3.0, efference_decay=0.0``) and the arousal founders with a youth of 100
moments and the chamber's need. The walker without the copy is the chamber's ``nocopy`` arm:
the same founder weights, the same point, no copy.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import time
from dataclasses import replace
from typing import Any

import numpy as np
from cadence import ArousalConfig, Brain

from .world import ACTIONS, INPUTS, KIND_DRIVE, KINDS, Track, observation

POINT: dict[str, Any] = {
    "modules": [32],
    "trace_amplitude": 0.3,
    "trace_decay": 0.1,
    "efference_amplitude": 3.0,
    "efference_decay": 0.0,
    "eta": 0.1,
    "lam": 0.0,
    "gamma": 0.95,
    "eta_critic": 5.0,
}
AROUSAL: dict[str, Any] = {
    "threshold": 0.2,
    "decay": 0.9,
    "tolerance": 2.0,
    "floor": 0.1,
    "fast": 0.05,
    "slow": 0.005,
    "heat": 2.0,
    "youth": 100,
    "value_surprise": 1.0,
    "record_surprise": 0.0,
    "need": 0.5,
}


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
        a, np.asarray(repeats).astype(np.intp), axis=axis
    )
    learning.np = shim
    return True


def newborn(seed: int, *, copy: bool = True) -> Brain:
    """The chamber's ``live`` brain at birth, or its ``nocopy`` control."""
    options: dict[str, Any] = {
        "episodic": False,
        "working_memory_amplitude": POINT["trace_amplitude"],
        "working_memory_decay": POINT["trace_decay"],
        "arousal": ArousalConfig(**AROUSAL),
    }
    if copy:
        options["efference_amplitude"] = POINT["efference_amplitude"]
        options["efference_decay"] = POINT["efference_decay"]
    brain = Brain.compose(INPUTS, ACTIONS, modules=tuple(POINT["modules"]), seed=seed, **options)
    brain.basal_ganglia.config = replace(
        brain.basal_ganglia.config,
        eta=POINT["eta"],
        eta_bias=POINT["eta"] / 10.0,  # the composed rule of issue 143
        lam=POINT["lam"],
        gamma=POINT["gamma"],
        eta_critic=POINT["eta_critic"],
    )
    return brain


class Host:
    """One walker: its brain, its track and the ledger of its life."""

    def __init__(self, seed: int, *, copy: bool = True) -> None:
        self.shimmed = fit_32_bit_numpy()
        self.seed = seed
        self.copy = copy
        self.brain = newborn(seed, copy=copy)
        self.track = Track()
        self.moments = 0
        self.refusals = 0
        self.last_error: str | None = None
        self.modes = {"routine": 0, "aroused": 0}
        self.sweeps = {"routine": 0, "aroused": 0}
        self.learning_sweeps = 0
        self.ms = 0.0
        self.pending: float | None = None  # the pay of the last step, owed at the next moment
        self.aroused_log: list[bool] = []
        self.found: int | None = None  # the moment the beat was first held for 20 steps

    # -- one moment

    def moment(self, kind: int = KIND_DRIVE) -> dict:
        brain, track = self.brain, self.track
        x = observation(kind)
        feedback = {} if self.pending is None else {"reward": [self.pending], "done": [False]}
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
                "kind": KINDS[kind],
                "sweeps": 0 if settlement is None else int(settlement["steps"]),
                "moment": self.moments,
                "position": track.position,
            }
        elapsed = time.perf_counter() - began
        self.pending = None
        reading = brain.last_arousal or {}
        arousal = brain.arousal
        mode = reading.get("mode", arousal.mode)
        aroused = mode == "aroused"
        agent = brain.basal_ganglia
        state = agent.state
        policy = np.asarray(agent.probabilities(state))[0]
        previous = track.previous
        belief = None if previous is None else float(policy[1 - previous])
        record = track.step(action)
        self.pending = record["reward"]
        self.moments += 1
        self.modes[mode] += 1
        sweeps = int(reading.get("sweeps", 0))
        self.sweeps[mode] += sweeps
        self.learning_sweeps += int(reading.get("learning_sweeps", 0))
        self.ms += elapsed * 1000.0
        self.aroused_log.append(aroused)
        activation = np.atleast_2d(np.asarray(state.activation))[0]
        motor = activation[brain.motor_index]
        association = activation[brain.association_index]
        echo = brain.efference
        recent = track.recent_beat(20)
        if self.found is None and len(track.steps) >= 21 and recent == 1.0:
            self.found = self.moments
        record.update(
            {
                "refused": False,
                "kind": KINDS[kind],
                "moment": self.moments,
                "mode": mode,
                "aroused": aroused,
                "want": round(float(arousal.want), 4),
                "level": round(float(arousal.level), 4),
                "heat": round(float(arousal.heat), 3),
                "surprise": round(float(reading.get("surprise", 0.0)), 4),
                "sweeps": sweeps,
                "learning_sweeps": int(reading.get("learning_sweeps", 0)),
                "ms": round(elapsed * 1000.0, 2),
                "belief": None if belief is None else round(belief, 4),
                "policy": [round(float(p), 4) for p in policy],
                "motor": [round(float(m), 4) for m in motor],
                "association": [round(float(a), 3) for a in association],
                "copy": None if echo is None else [round(float(v), 3) for v in echo.trace[0]],
                "beat20": round(recent, 3),
                "beat50": round(track.recent_beat(50), 3),
                "income100": round(track.income(100), 3),
                "found": self.found,
                "age": int(arousal.age),
            }
        )
        return record

    def run(self, moments: int = 1, kind: int = KIND_DRIVE) -> dict:
        """Live ``moments`` more moments of ``kind``, fast; returns the compact trail and the
        last moment's record."""
        last: dict | None = None
        feet: list[int | None] = []
        modes: list[bool] = []
        for _ in range(moments):
            last = self.moment(kind)
            feet.append(None if last["refused"] else int(last["action"]))
            modes.append(bool(last.get("aroused", False)))
        return {"feet": feet, "aroused": modes, "last": last, **self.status()}

    def forget(self) -> dict:
        """Erase the copy of the last command: the walker keeps its learned relations and loses
        one step of phase. A walker without the copy has nothing to forget."""
        echo = self.brain.efference
        if echo is None:
            return {"forgot": False}
        echo.reset(1, rows=np.array([0]))
        return {"forgot": True}

    # -- readings

    def status(self) -> dict:
        arousal = self.brain.arousal
        total = self.modes["routine"] + self.modes["aroused"]
        recent = self.aroused_log[-50:]
        return {
            "moments": self.moments,
            "position": self.track.position,
            "beat20": round(self.track.recent_beat(20), 3),
            "beat50": round(self.track.recent_beat(50), 3),
            "income100": round(self.track.income(100), 3),
            "found": self.found,
            "mode": arousal.mode,
            "want": round(float(arousal.want), 4),
            "level": round(float(arousal.level), 4),
            "heat": round(float(arousal.heat), 3),
            "age": int(arousal.age),
            "copy": self.copy,
            "work": {
                "routine": self.modes["routine"],
                "aroused": self.modes["aroused"],
                "aroused_share": self.modes["aroused"] / total if total else 0.0,
                "aroused_recent": float(np.mean(recent)) if recent else 0.0,
                "sweeps_routine": self.sweeps["routine"],
                "sweeps_aroused": self.sweeps["aroused"],
                "learning_sweeps": self.learning_sweeps,
                "refusals": self.refusals,
                "ms_per_moment": self.ms / self.moments if self.moments else 0.0,
            },
        }

    def describe(self) -> dict:
        import cadence

        w = self.brain.brain.connectome
        return {
            "cadence": cadence.__version__,
            "neurons": int(w.n),
            "synapses": int(w.synapses),
            "point": POINT,
            "arousal": self.brain.arousal.config.to_dict(),
            "seed": self.seed,
            "copy": self.copy,
            "shimmed": self.shimmed,
        }

    # -- continuation

    def snapshot(self) -> bytes:
        """The brain as saved, with the outcome it awaits; the track continues as it is."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.brain.save(os.path.join(directory, "brain.npz"))
            with open(path, "rb") as handle:
                return handle.read()

    def restore(self, data: bytes) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brain.npz")
            with open(path, "wb") as handle:
                handle.write(data)
            self.brain = Brain.load(path)

    # -- the page's messages

    def handle_json(self, text: str) -> str:
        message = json.loads(text)
        op = message.get("op")
        kind = int(message.get("kind", KIND_DRIVE))
        if op == "moment":
            return json.dumps(self.moment(kind))
        if op == "run":
            return json.dumps(self.run(int(message.get("moments", 1)), kind))
        if op == "status":
            return json.dumps(self.status())
        if op == "describe":
            return json.dumps(self.describe())
        if op == "forget":
            return json.dumps(self.forget())
        if op == "snapshot":
            return json.dumps({"brain": base64.b64encode(self.snapshot()).decode()})
        if op == "restore":
            self.restore(base64.b64decode(message["brain"]))
            return json.dumps({"restored": True, **self.status()})
        raise ValueError(f"unknown op {op!r}")
