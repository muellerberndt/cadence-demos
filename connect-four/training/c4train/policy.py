"""The Cadence policy brain and its conventional control.

``CadencePolicy`` composes a one-region brain on the 84 stone readings with seven motor neurons,
no working trace and no associative store: a Connect Four position is fully observed, so the
answer is a function of the board. It reads the motor population of a memory-free settle and
takes the strongest legal column; it learns by ``lesson`` in batches of a fixed size.
``MLPPolicy`` is a network of the same input and output trained by backpropagation with Adam on
the same lessons, the competent control.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cadence import Brain

INPUTS, ACTIONS = 84, 7


class CadencePolicy:
    def __init__(self, modules=(512,), seed: int = 0, surprise: bool = True,
                 teaching: str = "normalized", apical_readout: bool = True,
                 nudged_fixed: bool = False, chain_scale: float = 1.0, skip: bool = False,
                 frozen_gain: bool = False, inputs: int = INPUTS, verdict: bool = False,
                 **options) -> None:
        import cadence.generic as generic

        if hasattr(generic, "_APICAL_READOUT"):  # the rule under comparison (branch depth-apical)
            generic._APICAL_READOUT = bool(apical_readout)
        connectome = None
        if skip and len(modules) > 1:
            # a one-way projection from the sensory region to every module above the first, beside
            # the chain: the deep brain contains the flat one's direct path
            from cadence.genome import Genome, Projection, develop

            genome = Genome.composed(inputs, ACTIONS, modules=tuple(modules), seed=seed)
            above = [f"module_{k}" for k in range(1, len(modules) - 1)] + ["association"]
            genome = Genome(genome.regions, tuple(genome.projections) + tuple(
                Projection("sensory", name, reciprocal=False) for name in above), label=genome.label)
            connectome = develop(genome, seed=seed)
        from cadence import LearnerConfig

        # 0.95: the nudged phases run their whole budget through LearnerConfig(nudged_fixed=True),
        # set after composing (the compose-time name was retired in 0.93.0)
        library_fixed = nudged_fixed and "nudged_fixed" in LearnerConfig.__dataclass_fields__
        if library_fixed:
            nudged_fixed = False
        # with ``verdict`` a second motor slot of three neurons judges the position for the mover
        # (loss, draw, win), taught beside the move: the brain's own sense of who is winning
        self.verdict_slot = bool(verdict)
        if verdict:
            options = {**options, "slots": (ACTIONS, 3)}
        self.brain = Brain.compose(
            inputs, ACTIONS + (3 if verdict else 0),
            **({"modules": tuple(modules)} if connectome is None else {"connectome": connectome}),
            seed=seed, teaching=teaching, learning_surprise=surprise, working_memory_amplitude=0.0,
            episodic=False, **options,
        )
        if library_fixed:
            from dataclasses import replace
            self.brain.retune(learning=replace(self.brain.learner.config, nudged_fixed=True))
        if chain_scale != 1.0:
            # every projection along sensory -> modules -> association -> motor (both halves of a
            # pair) multiplied at birth: activity passes the chain whole instead of at ~0.4x a region
            populations = self.brain.connectome.populations
            modules = sorted((n for n in populations if n.startswith("module_")), key=lambda n: int(n.split("_")[1]))
            chain = [n for n in ["sensory"] + modules + ["association", "motor"] if n in populations]
            region = -np.ones(self.brain.connectome.n, dtype=np.int64)
            for k, name in enumerate(chain):
                region[np.asarray(populations[name], dtype=np.int64)] = k
            pre, post = np.asarray(self.brain.connectome.pre), np.asarray(self.brain.connectome.post)
            between = (region[pre] >= 0) & (region[post] >= 0) & (np.abs(region[pre] - region[post]) == 1)
            graph = self.brain.learner.brain
            efficacy = np.array(graph.efficacy, copy=True)
            efficacy[between] *= chain_scale
            self.brain.learner.brain = graph.with_parameters(efficacy=efficacy)
        if nudged_fixed:
            # the nudged phases run their whole budget: no early stop at the free tolerance
            learner = self.brain.learner

            def fixed(drive, free_state, target, sign=1.0, weight=None, _learner=learner):
                cfg = _learner.config
                return _learner.brain.settle_batch(
                    drive, steps=cfg.nudged_steps, state=free_state,
                    nudge=_learner.nudge_for(target, sign * cfg.beta, weight), tolerance=None)

            learner.nudged = fixed
        if frozen_gain:  # installed after nudged_fixed, so it wraps the fixed-length phase
            from .frozen_gain import install  # noqa
            install(self.brain)
        self.lessons = 0
        self.refused = 0
        self.work = {"free_steps": 0.0, "exhausted": 0.0, "lessons": 0}

    def readout(self, x: np.ndarray) -> np.ndarray:
        """Every motor neuron's settled activation: the seven columns, then the verdict."""
        brain = self.brain
        x = np.asarray(x, float)
        rows = len(x)
        if rows < 16 and getattr(brain, "placement", {}).get("backend") == "torch":
            # the CUDA kernel of cadence-net 0.95.2 needs 16 rows: copies of the first row fill
            # the batch (rows settle independently; the copies change no answer)
            x = np.concatenate([x, np.repeat(x[:1], 16 - rows, axis=0)])
        state = brain.learner.free(brain.stimulus(x, memory=False))
        return np.asarray(state.activation)[:rows, brain.learner.output_index]

    def motor(self, x: np.ndarray) -> np.ndarray:
        return self.readout(x)[:, :ACTIONS]

    def verdict(self, x: np.ndarray) -> np.ndarray:
        """The brain's judgement of each position for the mover: softmax over (loss, draw, win)
        at the learner's temperature."""
        z = self.readout(x)[:, ACTIONS:] / float(self.brain.learner.config.temperature)
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    def choose_x(self, x: np.ndarray, legal: np.ndarray) -> np.ndarray:
        motor = np.where(legal, self.motor(x), -np.inf)
        return motor.argmax(axis=1)

    def choose(self, boards) -> np.ndarray:
        x = np.stack([b.encode() for b in boards])
        return self.choose_x(x, np.stack([b.legal() for b in boards]))

    def teach(self, x: np.ndarray, labels: np.ndarray, targets=None, weights=None) -> dict:
        try:
            extra = {}
            if weights is not None:
                extra["weights"] = np.asarray(weights, float)
            if targets is not None:
                report = self.brain.lesson(np.asarray(x, float), targets=np.asarray(targets, float), **extra)
            else:
                report = self.brain.lesson(np.asarray(x, float), np.asarray(labels), **extra)
            self.lessons += 1
            self.work["free_steps"] += float(report.get("free_steps", 0.0))
            self.work["exhausted"] += float(report.get("free_budget_exhausted", 0.0))
            self.work["lessons"] += 1
            return dict(report)
        except RuntimeError:
            self.refused += 1
            return {"refused": 1.0}

    def save(self, path: str | Path) -> None:
        self.brain.save(path)

    def size(self) -> dict:
        w = self.brain.brain.connectome
        apical = self.brain.brain.apical
        return {"neurons": int(w.n), "synapses": int(w.synapses),
                "apical": None if apical is None else apical.to_dict(),
                "dt": self.brain.brain.neuron_model.dt, "learning": self.brain.learner.config.to_dict()}

    def drain_work(self) -> dict:
        n = max(self.work["lessons"], 1)
        out = {"free_steps": self.work["free_steps"] / n, "exhausted": self.work["exhausted"] / n}
        self.work = {"free_steps": 0.0, "exhausted": 0.0, "lessons": 0}
        return out


class MLPPolicy:
    def __init__(self, hidden=(512,), seed: int = 0, rate: float = 1e-3) -> None:
        rng = np.random.default_rng(seed)
        sizes = (INPUTS, *hidden, ACTIONS)
        self.weights = [rng.normal(0.0, np.sqrt(1.0 / a), size=(a, b)) for a, b in zip(sizes, sizes[1:])]
        self.biases = [np.zeros(b) for b in sizes[1:]]
        self.m = [np.zeros_like(p) for p in self.weights + self.biases]
        self.v = [np.zeros_like(p) for p in self.weights + self.biases]
        self.rate, self.steps, self.lessons, self.refused = rate, 0, 0, 0

    def _layers(self, x):
        layers = [np.asarray(x, float)]
        for k, (w, b) in enumerate(zip(self.weights, self.biases)):
            z = layers[-1] @ w + b
            layers.append(np.tanh(z) if k < len(self.weights) - 1 else z)
        return layers

    def motor(self, x):
        return self._layers(x)[-1]

    def choose_x(self, x, legal):
        return np.where(legal, self.motor(x), -np.inf).argmax(axis=1)

    def choose(self, boards):
        x = np.stack([b.encode() for b in boards])
        return self.choose_x(x, np.stack([b.legal() for b in boards]))

    def teach(self, x, labels) -> dict:
        layers = self._layers(x)
        logits = layers[-1] - layers[-1].max(axis=1, keepdims=True)
        p = np.exp(logits)
        p /= p.sum(axis=1, keepdims=True)
        delta = p.copy()
        delta[np.arange(len(labels)), labels] -= 1.0
        delta /= len(labels)
        grads_w, grads_b = [], []
        for k in range(len(self.weights) - 1, -1, -1):
            grads_w.insert(0, layers[k].T @ delta)
            grads_b.insert(0, delta.sum(axis=0))
            if k:
                delta = (delta @ self.weights[k].T) * (1.0 - layers[k] ** 2)
        self.steps += 1
        for p_, g, m, v in zip(self.weights + self.biases, grads_w + grads_b, self.m, self.v):
            m *= 0.9
            m += 0.1 * g
            v *= 0.999
            v += 0.001 * g * g
            p_ -= self.rate * (m / (1 - 0.9 ** self.steps)) / (np.sqrt(v / (1 - 0.999 ** self.steps)) + 1e-8)
        self.lessons += 1
        return {}

    def save(self, path) -> None:
        arrays = {f"w{k}": w for k, w in enumerate(self.weights)} | {f"b{k}": b for k, b in enumerate(self.biases)}
        np.savez(path, **arrays)

    def size(self) -> dict:
        return {"parameters": int(sum(p.size for p in self.weights + self.biases))}


def playable(x: np.ndarray) -> np.ndarray:
    """The cells where a stone would land, one per column with room (42 inputs): empty, and on
    the bottom row or above a stone. An observation of the board, as the stones are."""
    cells = np.asarray(x).reshape(-1, 2, 6, 7) > 0.5
    occupied = cells.any(axis=1)
    below = np.concatenate([np.ones((len(occupied), 1, 7), dtype=bool), occupied[:, :-1, :]], axis=1)
    return (~occupied & below).reshape(-1, 42).astype(float)


class Planes:
    """A policy that sees a third plane, the playable cells, beside the two stone planes."""

    def __init__(self, inner) -> None:
        self.inner = inner

    @staticmethod
    def expand(x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, float)
        return np.concatenate([x, playable(x)], axis=1)

    def teach(self, x, labels, targets=None, weights=None):
        return self.inner.teach(self.expand(x), labels, targets=targets, weights=weights)

    def readout(self, x):
        return self.inner.readout(self.expand(x))

    def motor(self, x):
        return self.inner.motor(self.expand(x))

    def verdict(self, x):
        return self.inner.verdict(self.expand(x))

    def choose_x(self, x, legal):
        return self.inner.choose_x(self.expand(x), legal)

    def choose(self, boards):
        x = np.stack([b.encode() for b in boards])
        return self.choose_x(x, np.stack([b.legal() for b in boards]))

    def __getattr__(self, name):
        return getattr(self.inner, name)
