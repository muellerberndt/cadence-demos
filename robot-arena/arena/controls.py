"""The matched-information conventional control: a linear softmax policy per motor with
eligibility traces and a linear TD critic, on the same inputs and the same reward as the
brain. It is the control the library's chambers run beside every brain (the tabular
Q(lambda) of the key-door nursery): it shows whether the problem is learnable at all with
the information and the moments given, and it is never the answer."""

from __future__ import annotations

from typing import Any

import numpy as np

from .parts import Blueprint
from .senses import input_count


class LinearPolicy:
    policy = "linear"

    def __init__(
        self,
        blueprint: Blueprint,
        *,
        alpha: float = 0.05,
        alpha_critic: float = 0.1,
        gamma: float = 0.95,
        lam: float = 0.6,
        temperature: float = 0.5,
        seed: int | None = None,
    ) -> None:
        self.blueprint = blueprint
        self.slots = blueprint.slots
        n = input_count(blueprint) + 1  # bias
        self.n = n
        self.w = [np.zeros((size, n)) for size in self.slots]
        self.v = np.zeros(n)
        self.e_w = [np.zeros_like(w) for w in self.w]
        self.e_v = np.zeros(n)
        self.alpha, self.alpha_critic, self.gamma, self.lam = alpha, alpha_critic, gamma, lam
        self.temperature = temperature
        self.rng = np.random.default_rng(blueprint.seed if seed is None else seed)
        self.last: tuple[np.ndarray, list[int]] | None = None
        self.moments = 0
        self.refusals = 0

    def _features(self, observation: np.ndarray) -> np.ndarray:
        x = np.asarray(observation, dtype=float).reshape(-1)
        return np.concatenate([x, [1.0]])

    def _probs(self, phi: np.ndarray, k: int) -> np.ndarray:
        z = self.w[k] @ phi / self.temperature
        z -= z.max()
        p = np.exp(z)
        return p / p.sum()

    def moment(self, observation: np.ndarray, reward: float | None, done: bool = False) -> dict[str, Any]:
        phi = self._features(observation)
        if reward is not None and self.last is not None:
            phi0, acts = self.last
            v0 = float(self.v @ phi0)
            v1 = 0.0 if done else float(self.v @ phi)
            delta = float(reward) + self.gamma * v1 - v0
            # critic TD(lambda)
            self.e_v = self.gamma * self.lam * self.e_v + phi0
            self.v += self.alpha_critic * delta * self.e_v
            # actor: eligibility of the log-policy gradient per slot
            for k, a in enumerate(acts):
                p = self._probs(phi0, k)
                grad = -np.outer(p, phi0)
                grad[a] += phi0
                self.e_w[k] = self.gamma * self.lam * self.e_w[k] + grad / self.temperature
                self.w[k] += self.alpha * delta * self.e_w[k]
            if done:
                self.e_v[:] = 0.0
                for e in self.e_w:
                    e[:] = 0.0
        acts = []
        for k in range(len(self.slots)):
            p = self._probs(phi, k)
            acts.append(int(self.rng.choice(len(p), p=p)))
        self.last = (phi, acts)
        self.moments += 1
        return {
            "commands": acts, "refused": False, "mode": "linear", "aroused": True, "sweeps": 0,
            "learning_sweeps": 0, "want": 0.0, "level": 0.0, "ms": 0.0,
        }

    def greedy(self, observation: np.ndarray) -> list[int]:
        phi = self._features(observation)
        return [int(np.argmax(self.w[k] @ phi)) for k in range(len(self.slots))]

    def save(self, path: Any) -> None:
        return None

    def describe(self) -> dict[str, Any]:
        return {"policy": "linear", "moments": self.moments, "weight_norm": float(sum(np.abs(w).sum() for w in self.w))}
