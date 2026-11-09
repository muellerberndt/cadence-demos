"""A creature's brain: one continuing ``Brain.live`` life from birth to death.

``Brain.compose`` builds one neural graph from the genes: the senses drive one or two
association regions, the motor region holds one neuron per action (north, east, south, west,
eat, drink), a working trace carries the last settled interpretation into the next settle, the
associative store keeps what each action brought in each situation, and with the ``recall``
gene a recall memory gives back earlier moments of the life. Every moment is one ``live`` call:
the outcome of the previous action goes in, the next action comes out. Calm, the brain answers
greedily from one settle and learns nothing; surprised (a berry that poisoned where berries
used to nourish) or in want, it samples, learns from the outcome and writes it to memory.

``FrozenMind`` is the frozen twin: the same brain sampling its policy at its own temperature,
never learning (a twin answering greedily barely forages: these brains act by sampling).
``RandomMind`` is the random walker. Both are controls.
"""

from __future__ import annotations

import contextlib
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
import cadence
from cadence import Brain

from .genes import brain_genes
from .world import N_ACTIONS, N_INPUTS

AROUSAL = {
    "threshold": 0.2, "decay": 0.9, "tolerance": 2.0, "floor": 0.1, "fast": 0.05,
    "slow": 0.005, "heat": 1.0, "youth": 300, "value_surprise": 1.0, "need": 0.05,
}


def compose(g: dict[str, Any], seed: int = 0) -> Brain:
    """A newborn brain from the genes (anatomy and rates)."""
    width, depth = int(g["width"]), int(g["depth"])
    modules = (width,) if depth == 1 else (width, max(8, width // 2))
    arousal = {**AROUSAL, "threshold": g["threshold"], "tolerance": g["tolerance"],
               "need": g["need"], "heat": g["heat"]}
    extra: dict[str, Any] = {}
    if g["recall"]:
        # the recall memory with the same teaching point as a brain without it, so the gene
        # changes only the memory
        extra = {"teaching": "founder", "learning_surprise": False, "learning_fast_settle": False}
    eff = float(g.get("efference_amplitude", 0.0))
    return Brain.compose(
        N_INPUTS,
        N_ACTIONS,
        modules=modules,
        seed=seed,
        recall=bool(g["recall"]),
        episodic=True,
        consolidation=float(g["consolidation"]),
        memory_rate=float(g["memory_rate"]),
        working_memory_amplitude=float(g["trace_amplitude"]),
        working_memory_decay=0.1,
        efference_amplitude=eff,
        **({"efference_decay": 0.2} if eff > 0 else {}),
        lateral=-0.5,
        scales={"sensory": float(g["sensory_scale"]), "trace": 12.0},
        temperature=float(g["temperature"]),
        actor_eta=float(g["eta"]),
        actor_eta_bias=float(g["eta"]) / 10.0,
        actor_lam=float(g["lam"]),
        actor_gamma=float(g["gamma"]),
        actor_eta_critic=float(g["eta_critic"]),
        arousal=arousal,
        backend="cpu",
        **extra,
    )


def retune(brain: Brain, g: dict[str, Any]) -> None:
    """Give a brain raised under other genes this creature's rates and arousal."""
    b = brain_genes(g)
    brain.retune(
        temperature=float(b["temperature"]),
        actor_eta=float(b["eta"]), actor_eta_bias=float(b["eta"]) / 10.0,
        actor_lam=float(b["lam"]), actor_gamma=float(b["gamma"]),
        actor_eta_critic=float(b["eta_critic"]),
        consolidation=float(b["consolidation"]), memory_rate=float(b["memory_rate"]),
        arousal={"threshold": float(b["threshold"]), "tolerance": float(b["tolerance"]),
                 "need": float(b["need"]), "heat": float(b["heat"])},
    )


def activity(brain: Brain) -> dict[str, list[float]] | None:
    """The settled state the brain just acted from, per region, rounded for the page."""
    state = brain.basal_ganglia.state
    if state is None:
        return None
    act = np.asarray(state.activation)[0]
    c = brain.connectome
    out: dict[str, list[float]] = {}
    for name in ("sensory", "module_0", "association", "prefrontal", "motor", "recall", "next"):
        idx = c.populations.get(name)
        if idx is not None and len(idx):
            out[name] = [round(float(v), 3) for v in act[np.asarray(idx)]]
    return out


class LiveMind:
    """One creature's continuing life. ``moment`` takes the observation and the outcome of
    the previous action and returns the next action with the readings of the moment."""

    kind = "live"

    def __init__(self, brain: Brain) -> None:
        self.brain = brain
        self.owed = 0.0
        self.refusals = 0
        self.moments = 0
        self.sweeps_total = 0
        self.history: deque = deque(maxlen=200)  # its observations, for the recall view
        self.inspector = None

    def moment(self, observation: np.ndarray, reward: float | None, done: bool = False,
               detail: bool = False) -> dict[str, Any]:
        brain = self.brain
        began = time.perf_counter()
        feedback: dict[str, Any] = {}
        if reward is not None and brain.pending_feedback:
            feedback = {"reward": [float(reward) + self.owed], "done": [bool(done)]}
        elif reward is not None:
            self.owed += float(reward)
        action = None
        self.history.append(np.asarray(observation, dtype=float).copy())
        records: list = []
        before = None
        if detail:
            before = self._inspector().efficacy()
        recording = (cadence.record_settlements(records.append, label="inspect") if detail
                     else contextlib.nullcontext())
        with recording:
            try:
                action = brain.live(observation[None, :], **feedback)
                self.owed = 0.0
            except (RuntimeError, ValueError):
                self.refusals += 1
                if feedback and not brain.pending_feedback:
                    try:
                        action = brain.live(observation[None, :])
                        self.owed = 0.0
                    except (RuntimeError, ValueError):
                        pass
                elif feedback:
                    self.owed = float(feedback["reward"][0])
        self.moments += 1
        ms = (time.perf_counter() - began) * 1000.0
        if action is None:
            return {"action": int(np.random.default_rng(self.moments).integers(N_ACTIONS)),
                    "refused": True, "mode": "refused", "sweeps": 0, "learning_sweeps": 0,
                    "ms": ms}
        reading = brain.last_arousal or {}
        learning_sweeps = int(reading.get("learning_sweeps", 0))
        self.sweeps_total += learning_sweeps
        out = {
            "action": int(np.atleast_1d(action[0])[0]),
            "refused": False,
            "mode": reading.get("mode", "routine"),
            "sweeps": int(reading.get("sweeps", 0)),
            "learning_sweeps": learning_sweeps,
            "level": float(brain.arousal.level) if brain.arousal is not None else 0.0,
            "surprise": float(reading.get("surprise", 0.0) or 0.0),
            "want": float(reading.get("want", 0.0) or 0.0),
            "ms": ms,
        }
        ll = brain.last_learning or {}
        if reading.get("learned") and "dopamine" in ll:
            out["dopamine"] = round(float(ll["dopamine"]), 4)
        if detail:
            out["activity"] = activity(brain)
            settlement = brain.last_settlement or {}
            out["settle"] = {"steps": int(settlement.get("steps", 0)),
                             "residual": float(settlement.get("max_residual", 0.0))}
            out["brain"] = self._inspector().read(records, before)
        return out

    def _inspector(self):
        from .inspect import Inspector

        if self.inspector is None or self.inspector.brain is not self.brain:
            self.inspector = Inspector(self.brain)
            self.inspector.history = self.history
        return self.inspector

    def finish(self, reward: float) -> None:
        """A life that ended: the brain dies with the body, so nothing is learned from death."""

    def save(self, path: str | Path) -> Path:
        return self.brain.save(Path(path))


class FrozenMind:
    """The frozen twin: the same brain, sampling its policy as it stands, never learning."""

    kind = "frozen"

    def __init__(self, brain: Brain) -> None:
        self.brain = brain
        self.moments = 0
        self.refusals = 0
        self.sweeps_total = 0
        self.history: deque = deque(maxlen=200)
        self.inspector = None

    def moment(self, observation: np.ndarray, reward: float | None, done: bool = False,
               detail: bool = False) -> dict[str, Any]:
        began = time.perf_counter()
        self.moments += 1
        self.history.append(np.asarray(observation, dtype=float).copy())
        records: list = []
        recording = (cadence.record_settlements(records.append, label="inspect") if detail
                     else contextlib.nullcontext())
        try:
            with recording:
                action = self.brain.act(observation[None, :], greedy=False)
        except (RuntimeError, ValueError):
            self.refusals += 1
            return {"action": int(np.random.default_rng(self.moments).integers(N_ACTIONS)),
                    "refused": True, "mode": "refused", "sweeps": 0, "learning_sweeps": 0,
                    "ms": (time.perf_counter() - began) * 1000.0}
        settlement = self.brain.last_settlement or {}
        out = {"action": int(np.atleast_1d(action[0])[0]), "refused": False, "mode": "frozen",
               "sweeps": int(settlement.get("steps", 0)), "learning_sweeps": 0,
               "level": 0.0, "surprise": 0.0, "want": 0.0,
               "ms": (time.perf_counter() - began) * 1000.0}
        if detail:
            out["activity"] = activity(self.brain)
            out["settle"] = {"steps": int(settlement.get("steps", 0)),
                             "residual": float(settlement.get("max_residual", 0.0))}
            out["brain"] = self._inspector().read(records, None)
        return out

    def _inspector(self):
        from .inspect import Inspector

        if self.inspector is None:
            self.inspector = Inspector(self.brain)
            self.inspector.history = self.history
        return self.inspector

    def finish(self, reward: float) -> None:
        pass


class RandomMind:
    """The random walker: a uniform draw over the six actions every moment."""

    kind = "random"

    def __init__(self, seed: int = 0) -> None:
        self.rng = np.random.default_rng(seed)
        self.moments = 0
        self.refusals = 0
        self.sweeps_total = 0

    def moment(self, observation: np.ndarray, reward: float | None, done: bool = False,
               detail: bool = False) -> dict[str, Any]:
        self.moments += 1
        return {"action": int(self.rng.integers(N_ACTIONS)), "refused": False, "mode": "random",
                "sweeps": 0, "learning_sweeps": 0, "level": 0.0, "surprise": 0.0, "want": 0.0,
                "ms": 0.0}

    def finish(self, reward: float) -> None:
        pass


def load(path: str | Path) -> Brain:
    return Brain.load(Path(path), backend="cpu")
