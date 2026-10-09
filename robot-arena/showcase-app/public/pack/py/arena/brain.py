"""The robot's brain: one continuing ``Brain.live`` life wired to every motor.

``Brain.compose`` builds one neural graph: the senses drive a processing region, the
association region exchanges signals with the motor cortex, the working trace and the
efference copy feed the association region back its own recent state and command. The motor
cortex is grouped into one slot per motor (``Blueprint.slots``): the settled state of the
whole graph is read as one choice per slot, so every motor is commanded by the same
equilibrium, and lateral inhibition stays within a motor.

The founder genes are the arena nursery's operating point: a quiet working trace, no
efference copy, sensory projection scale 4, and actor eta 0.03 with a fast critic.
Episodic memory is disabled in this founder. ``preset: "chamber"`` keeps the earlier
library reward-chamber point (cadence 0.76/0.77), including efference amplitude 3 and
actor eta 0.1; ``preset: "compose"`` builds the library's composed defaults. Both are
controls for the arena point. Every value is a gene of the blueprint.

A robot lives through ``moment``: the observation of this moment and the outcome of its
previous command go in, one command per motor comes out. Calm, the brain answers from one
settled state and learns nothing; surprised or in want, it samples, learns and remembers.
A refused answer is handled as the library prescribes and reported, never hidden.
"""

from __future__ import annotations

import copy
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from cadence import ArousalConfig, Brain, Genome, Projection, Region, develop
from cadence.regions import motor_cortex, prefrontal_cortex

from .parts import Blueprint
from .senses import input_count

FOUNDER: dict[str, Any] = {
    # The operating point selected in the nursery grids of 2026-10-08 and 09 (STATUS.md):
    # two processing modules, no efference copy, the sensory projection at four times the
    # composed scale, the associative memory on, a small actor step, short eligibility, a
    # learner temperature of 0.3. Every value is a gene; ``preset: "chamber"`` builds the
    # library's reward-chamber point (the control that was observation-blind here) and
    # ``preset: "compose"`` the library's composed defaults.
    "preset": "founder",
    "modules": [48, 24],
    "observers": [],  # System 2 observer regions, expressed only on a developed two-module System 1
    "trace_amplitude": 0.3,
    "trace_decay": 0.1,
    "efference_amplitude": 0.0,
    "efference_decay": 0.0,
    "episodic": True,
    "consolidation": 0.05,
    "resting_bias": 0.0,
    "sensory_scale": 4.0,  # the sensory projection's scale; 1.0 is Brain.compose's own
    "temperature": 0.3,  # the learner's softmax temperature; 0.2 is the library default
    "eta": 0.03,
    "eta_bias": 0.003,
    "lam": 0.6,
    "gamma": 0.95,
    "eta_critic": 5.0,
    "arousal": {
        "threshold": 0.2,
        "decay": 0.9,
        "tolerance": 2.0,
        "floor": 0.1,
        "fast": 0.05,
        "slow": 0.005,
        "heat": 2.0,
        "youth": 300,
        "value_surprise": 1.0,
        "record_surprise": 0.0,
        "need": 0.05,
    },
}

PAGE_STAGE: dict[str, Any] = {
    # The ring stage of a life in the page and in the league's fights: no need and no heat
    # (calm unless surprised, no wider exploration), a sharp sampling temperature, the memory
    # of the nursery's income forgotten on entering the ring, and an actor step of 0.001, a
    # thirtieth of the nursery's: a fight refines a brain's policy instead of overwriting it.
    # Measured on six licensed brains over sixty fights: at 0.001 the driving-test mean held at
    # 0.49 of its 0.57 start with burn moments per fight between 14 and 31 and several winners;
    # at 0.003 it fell to 0.34 and the burn rose again in the third block; at the gene's 0.03
    # three fights turned approach into spinning. A threshold above the gene's 0.2 left the
    # brains calm throughout, the same winner twenty fights running.
    "need": 0.0, "heat": 0.0, "temperature": 0.2, "reset": True, "eta": 0.001,
}

CHAMBER_POINT: dict[str, Any] = {
    # The key-door nursery / reward-rhythm walker point of cadence 0.76-0.77: the control.
    "preset": "chamber",
    "efference_amplitude": 3.0,
    "efference_decay": 0.0,
    "sensory_scale": 1.0,
    "temperature": 0.2,
    "eta": 0.1,
    "eta_bias": 0.01,
    "lam": 0.95,
}


def genes_of(blueprint: Blueprint) -> dict[str, Any]:
    """The blueprint's genes over the founder values (``preset: compose`` keeps only the
    arousal genes and the module widths, leaving every other value to the library)."""
    genes = copy.deepcopy(FOUNDER)
    own = dict(blueprint.genes)
    if own.get("preset") == "chamber":
        genes.update(CHAMBER_POINT)
    arousal = own.pop("arousal", {})
    genes.update(own)
    genes["arousal"] = {**genes["arousal"], **arousal}
    return genes


def composed_genome(
    inputs: int,
    actions: int,
    *,
    modules: tuple[int, ...],
    slots: list[int],
    sensory_scale: float,
    efference: bool,
    observers: tuple[int, ...] = (),
) -> Genome:
    """``Brain.compose``'s own layout, region for region and projection for projection, with
    one difference offered as a gene: the scale of the sensory projection. At scale 1.0 the
    genome is the composed one and develops the same connectome from the same seed."""
    lateral = -0.5 if max(slots) <= 8 else 0.0  # the library's default motor inhibition
    names = [f"module_{index}" for index in range(len(modules) - 1)] + ["association"]
    regions = [Region("sensory", inputs)]
    regions.extend(Region(name, width) for name, width in zip(names, modules, strict=True))
    regions.extend((prefrontal_cortex(modules[-1]), motor_cortex(actions, lateral=lateral, slots=slots)))
    projections = [Projection("sensory", names[0], reciprocal=False, scale=sensory_scale)]
    projections.extend(Projection(left, right) for left, right in zip(names, names[1:], strict=False))
    projections.extend(
        (
            Projection("association", "motor"),
            Projection("prefrontal", "association", scale=12.0, reciprocal=False),
        )
    )
    observed = [*names, "motor"]
    for index, width in enumerate(observers):
        name = f"observer_{index}"
        regions.append(Region(name, width))
        projections.extend(Projection(source, name) for source in observed)
        observed.append(name)
    if efference:
        regions.append(Region("efference", actions))
        projections.append(Projection("efference", "association", scale=12.0, reciprocal=False))
    return Genome(tuple(regions), tuple(projections), label="composed-brain")


def compose(blueprint: Blueprint, genes: dict[str, Any] | None = None) -> Brain:
    """A newborn brain for this body: every motor a slot, every sense an input."""
    g = genes_of(blueprint) if genes is None else genes
    arousal = ArousalConfig(**g["arousal"])
    inputs, slots = input_count(blueprint), blueprint.slots
    if g.get("preset") == "compose":
        return Brain.compose(
            inputs,
            sum(slots),
            modules=tuple(g["modules"]),
            slots=slots,
            seed=blueprint.seed,
            arousal=arousal,
        )
    options: dict[str, Any] = dict(
        episodic=bool(g["episodic"]),
        consolidation=float(g["consolidation"]),
        working_memory_amplitude=float(g["trace_amplitude"]),
        working_memory_decay=float(g["trace_decay"]),
        efference_amplitude=float(g["efference_amplitude"]),
        efference_decay=float(g["efference_decay"]),
        resting_bias=float(g["resting_bias"]),
        arousal=arousal,
    )
    observers = tuple(int(w) for w in g.get("observers", ()) or ())
    if float(g.get("sensory_scale", 1.0)) == 1.0:
        brain = Brain.compose(
            inputs, sum(slots), modules=tuple(g["modules"]), observers=observers, slots=slots, seed=blueprint.seed, **options
        )
    else:
        genome = composed_genome(
            inputs,
            sum(slots),
            modules=tuple(g["modules"]),
            slots=slots,
            sensory_scale=float(g["sensory_scale"]),
            efference=float(g["efference_amplitude"]) > 0.0,
            observers=observers,
        )
        brain = Brain(develop(genome, seed=blueprint.seed), seed=blueprint.seed, slots=slots, **options)
    if float(g.get("temperature", 0.2)) != 0.2:
        brain.learner.config = replace(brain.learner.config, temperature=float(g["temperature"]))
    brain.basal_ganglia.config = replace(
        brain.basal_ganglia.config,
        eta=float(g["eta"]),
        eta_bias=float(g["eta_bias"]),
        lam=float(g["lam"]),
        gamma=float(g["gamma"]),
        eta_critic=float(g["eta_critic"]),
    )
    return brain


def activity(brain: Brain) -> dict[str, list[float]] | None:
    """The settled state the brain just acted from: its sensory, association and motor
    activations, rounded for the replay."""
    state = brain.basal_ganglia.state
    if state is None:
        return None
    act = np.asarray(state.activation)[0]
    return {
        "sensory": [round(float(v), 2) for v in act[brain.sensory_index]],
        "association": [round(float(v), 2) for v in act[brain.association_index]],
        "motor": [round(float(v), 2) for v in act[brain.motor_index]],
    }


def motor_names(blueprint: Blueprint) -> list[dict[str, str]]:
    """One label per motor slot, in slot order."""
    names = []
    for p in blueprint.parts:
        side = f"{p.mount:+.0f}°"
        if p.kind == "arm":
            names.append({"kind": "arm", "label": f"{p.weapon} arm {side}"})
            if p.weapon == "spinner":
                names.append({"kind": "switch", "label": "spinner"})
        else:
            names.append({"kind": p.kind, "label": f"{p.kind} {side}"})
    return names


def hold_commands(blueprint: Blueprint) -> list[int]:
    """Every motor at rest: wheels brake, legs hold, arms hold, spinners off."""
    return [1 if size == 3 else 0 for size in blueprint.slots]


class RobotBrain:
    """One robot's continuing life. ``moment`` delivers the previous command's outcome and
    returns this moment's commands; ``save``/``load`` carry the whole life, including an
    outcome still owed."""

    policy = "brain"

    def __init__(self, blueprint: Blueprint, brain: Brain) -> None:
        self.blueprint = blueprint
        self.brain = brain
        self.owed: float = 0.0  # reward not yet delivered after a refusal
        self.refusals = 0
        self.moments = 0
        self.last_error: str | None = None

    @classmethod
    def newborn(cls, blueprint: Blueprint) -> RobotBrain:
        return cls(blueprint, compose(blueprint))

    @classmethod
    def load(cls, blueprint: Blueprint, path: str | Path) -> RobotBrain:
        return cls(blueprint, Brain.load(Path(path)))

    def save(self, path: str | Path) -> Path:
        return self.brain.save(Path(path))

    def has_pending(self) -> bool:
        """Whether an issued command still awaits its outcome."""
        return self.brain.basal_ganglia._pending is not None or self.brain._lived is not None

    def moment(
        self, observation: np.ndarray, reward: float | None, done: bool = False
    ) -> dict[str, Any]:
        brain = self.brain
        began = time.perf_counter()
        feedback: dict[str, Any] = {}
        if reward is not None and self.has_pending():
            feedback = {"reward": [float(reward) + self.owed], "done": [bool(done)]}
        elif reward is not None:
            self.owed += float(reward)  # nothing to credit yet; keep it for the next command
        action = None
        try:
            action = brain.live(observation, **feedback)
            self.owed = 0.0
        except (RuntimeError, ValueError) as error:
            self.refusals += 1
            self.last_error = f"{type(error).__name__}: {error}"[:200]
            if feedback and not self.has_pending():
                # the outcome was taken; only the answer refused: retry without it
                try:
                    action = brain.live(observation)
                    self.owed = 0.0
                except (RuntimeError, ValueError) as again:
                    self.last_error = f"{type(again).__name__}: {again}"[:200]
            elif feedback:
                self.owed = float(feedback["reward"][0])  # still owed to the same command
        elapsed = (time.perf_counter() - began) * 1000.0
        self.moments += 1
        if action is None:
            return {
                "commands": hold_commands(self.blueprint),
                "refused": True,
                "mode": "refused",
                "aroused": False,
                "sweeps": 0,
                "learning_sweeps": 0,
                "want": 0.0,
                "level": 0.0,
                "ms": elapsed,
            }
        reading = brain.last_arousal or {}
        arousal = brain.arousal
        assert arousal is not None
        return {
            "commands": [int(c) for c in np.atleast_1d(action[0])],
            "refused": False,
            "mode": reading.get("mode", arousal.mode),
            "aroused": reading.get("mode", arousal.mode) == "aroused",
            "sweeps": int(reading.get("sweeps", 0)),
            "learning_sweeps": int(reading.get("learning_sweeps", 0)),
            "want": float(arousal.want),
            "level": float(arousal.level),
            "ms": elapsed,
            "activity": activity(brain),
        }

    def describe(self) -> dict[str, Any]:
        arousal = self.brain.arousal
        assert arousal is not None
        return {
            "neurons": int(self.brain.connectome.n),
            "parameters": int(self.brain.parameters()),
            "age": int(arousal.age),
            "moments": {k: int(v) for k, v in arousal.moments.items()},
            "sweeps": {k: int(v) for k, v in arousal.sweeps.items()},
            "learning_sweeps": int(arousal.learning_sweeps),
            "refusals": self.refusals,
        }


class RandomPolicy:
    """The uniform-random baseline with the same body: one draw per motor, every moment."""

    policy = "random"

    def __init__(self, blueprint: Blueprint, seed: int | None = None) -> None:
        self.blueprint = blueprint
        self.rng = np.random.default_rng(blueprint.seed if seed is None else seed)
        self.moments = 0
        self.refusals = 0

    def moment(
        self, observation: np.ndarray, reward: float | None, done: bool = False
    ) -> dict[str, Any]:
        self.moments += 1
        return {
            "commands": [int(self.rng.integers(size)) for size in self.blueprint.slots],
            "refused": False,
            "mode": "random",
            "aroused": False,
            "sweeps": 0,
            "learning_sweeps": 0,
            "want": 0.0,
            "level": 0.0,
            "ms": 0.0,
        }

    def save(self, path: str | Path) -> Path | None:
        return None

    def describe(self) -> dict[str, Any]:
        return {"policy": "random", "moments": self.moments}


class FrozenPolicy:
    """A brain that answers greedily and never learns: the control for 'kept learning'."""

    policy = "frozen"

    def __init__(self, blueprint: Blueprint, brain: Brain) -> None:
        self.blueprint = blueprint
        self.brain = brain
        self.moments = 0
        self.refusals = 0

    def moment(
        self, observation: np.ndarray, reward: float | None, done: bool = False
    ) -> dict[str, Any]:
        self.moments += 1
        began = time.perf_counter()
        try:
            action = self.brain.act(observation, greedy=True)
        except (RuntimeError, ValueError):
            self.refusals += 1
            return {
                "commands": hold_commands(self.blueprint),
                "refused": True,
                "mode": "refused",
                "aroused": False,
                "sweeps": 0,
                "learning_sweeps": 0,
                "want": 0.0,
                "level": 0.0,
                "ms": (time.perf_counter() - began) * 1000.0,
            }
        settlement = self.brain.last_settlement or {}
        return {
            "commands": [int(c) for c in np.atleast_1d(action[0])],
            "refused": False,
            "mode": "frozen",
            "aroused": False,
            "sweeps": int(settlement.get("steps", 0)),
            "learning_sweeps": 0,
            "want": 0.0,
            "level": 0.0,
            "ms": (time.perf_counter() - began) * 1000.0,
            "activity": activity(self.brain),
        }

    def save(self, path: str | Path) -> Path | None:
        return None

    def describe(self) -> dict[str, Any]:
        return {"policy": "frozen", "moments": self.moments, "refusals": self.refusals}


def set_stage(brain: Brain, stage: dict[str, Any] | None) -> None:
    """The ring stage's genes: ``need``, ``heat``, ``threshold``, ``decay``, ``tolerance`` (arousal),
    ``temperature`` (the learner's sampling temperature), ``eta`` (the actor) and ``reset`` (forget
    what life used to pay). None or {} keeps the brain as it is."""
    if not stage or brain.arousal is None:
        return
    arousal = {k: stage[k] for k in ("need", "heat", "threshold", "decay", "tolerance") if k in stage}
    if arousal:
        brain.arousal.config = replace(brain.arousal.config, **arousal)
    if "temperature" in stage:
        brain.learner.config = replace(brain.learner.config, temperature=float(stage["temperature"]))
    if "eta" in stage:
        brain.basal_ganglia.config = replace(brain.basal_ganglia.config, eta=float(stage["eta"]), eta_bias=float(stage["eta"]) / 10.0)
    if stage.get("reset"):
        brain.arousal.reset()


def set_need(brain: Brain, need: float | None, reset: bool = False) -> None:
    """The ring stage of a life: another need than the nursery's (None keeps the gene) and,
    with ``reset``, the arousal's memory of what life used to pay forgotten (``Arousal.reset``:
    the stream begins calm; age, work and every learned parameter stay). A brain raised on the
    nursery's income otherwise wants forever in a ring that pays less."""
    if brain.arousal is None:
        return
    if need is not None:
        brain.arousal.config = replace(brain.arousal.config, need=float(need))
    if reset:
        brain.arousal.reset()


def make_policy(
    blueprint: Blueprint, policy: str = "brain", brain_path: str | Path | None = None,
    need: float | None = None, reset: bool = False, stage: dict[str, Any] | None = None,
):
    if policy == "random":
        return RandomPolicy(blueprint)
    if policy == "linear":
        from .controls import LinearPolicy

        return LinearPolicy(blueprint)
    brain = Brain.load(Path(brain_path)) if brain_path else compose(blueprint)
    set_need(brain, need, reset)
    set_stage(brain, stage)
    if policy == "frozen":
        return FrozenPolicy(blueprint, brain)
    if policy == "brain":
        return RobotBrain(blueprint, brain)
    raise ValueError(f"unknown policy {policy!r}")
