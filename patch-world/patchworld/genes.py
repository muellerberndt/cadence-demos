"""A creature's genes: the shape and rates of its brain, its arousal, and its body.

Every gene is paid for. The brain costs energy per moment in proportion to its neurons (and a
recall memory costs more), every learning sweep of an aroused moment costs energy, a wider
sense range, a faster gait and a larger body burn more. Selection sees only who eats, drinks,
escapes and lives long enough to bear young.
"""

from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np

from .world import Body

WIDTHS = (16, 24, 32, 48)
DEPTHS = (1, 2)

# continuous genes: (low, high, log scale)
RANGES: dict[str, tuple[float, float, bool]] = {
    "eta": (0.002, 0.2, True),  # actor step
    "eta_critic": (0.1, 10.0, True),
    "temperature": (0.1, 0.6, False),
    "lam": (0.3, 0.95, False),
    "gamma": (0.6, 0.98, False),
    "sensory_scale": (1.0, 6.0, False),
    "trace_amplitude": (0.0, 1.0, False),
    "efference_amplitude": (0.0, 2.0, False),
    "consolidation": (0.01, 0.4, True),
    "memory_rate": (0.05, 0.6, True),
    "threshold": (0.05, 0.6, True),  # arousal
    "tolerance": (0.5, 4.0, True),
    "need": (0.0, 0.3, False),
    "heat": (0.0, 3.0, False),
    "birth": (0.55, 0.95, False),  # share of capacity at which it bears a child
}

FOUNDER: dict[str, Any] = {
    "width": 32,
    "depth": 1,
    "recall": False,
    "eta": 0.03,
    "eta_critic": 3.0,
    "temperature": 0.3,
    "lam": 0.6,
    "gamma": 0.9,
    "sensory_scale": 4.0,
    "trace_amplitude": 0.3,
    "efference_amplitude": 0.0,
    "consolidation": 0.05,
    "memory_rate": 0.2,
    "threshold": 0.2,
    "tolerance": 2.0,
    "need": 0.05,
    "heat": 1.0,
    "birth": 0.8,
    "sense": 4,
    "speed": 1,
    "size": 1.0,
}

# what the brain and the body cost, in energy per moment
NEURON_COST = 0.0003  # per association neuron
RECALL_COST = 0.008  # a recall memory's upkeep
SWEEP_COST = 0.00004  # per learning sweep of an aroused moment


def structure(g: dict[str, Any]) -> str:
    """The name of the brain's anatomy: the genes that decide its neurons."""
    return f"w{int(g['width'])}d{int(g['depth'])}{'r' if g['recall'] else ''}"


def body_of(g: dict[str, Any]) -> Body:
    return Body(sense=int(g["sense"]), speed=int(g["speed"]), size=float(g["size"]))


def brain_cost(g: dict[str, Any]) -> float:
    return NEURON_COST * int(g["width"]) * int(g["depth"]) + (RECALL_COST if g["recall"] else 0.0)


def mutate(g: dict[str, Any], rng: np.random.Generator, rate: float = 0.25,
           structural: float = 0.08, structures: list[str] | None = None) -> dict[str, Any]:
    """A child's genes: each continuous gene moves with chance ``rate``, the anatomy with
    chance ``structural`` (only to anatomies in ``structures`` when given)."""
    c = copy.deepcopy(g)
    for name, (lo, hi, log) in RANGES.items():
        if rng.random() < rate:
            if log:
                v = math.exp(math.log(max(c[name], lo)) + rng.normal(0, 0.35))
            else:
                v = c[name] + rng.normal(0, 0.12 * (hi - lo))
            c[name] = float(min(hi, max(lo, v)))
    if rng.random() < rate:
        c["sense"] = int(min(6, max(2, c["sense"] + rng.choice([-1, 1]))))
    if rng.random() < rate / 2:
        c["speed"] = int(3 - c["speed"])  # 1 <-> 2
    if rng.random() < rate:
        c["size"] = float(min(1.5, max(0.7, c["size"] + rng.normal(0, 0.1))))
    if rng.random() < structural:
        options = []
        for w in WIDTHS:
            for d in DEPTHS:
                for r in (False, True):
                    cand = {**c, "width": w, "depth": d, "recall": r}
                    if structures is None or structure(cand) in structures:
                        # one step at a time: a neighbouring width, depth or recall
                        steps = (abs(WIDTHS.index(w) - WIDTHS.index(c["width"]))
                                 + abs(d - c["depth"]) + int(r != c["recall"]))
                        if steps == 1:
                            options.append((w, d, r))
        if options:
            w, d, r = options[int(rng.integers(len(options)))]
            c.update(width=w, depth=d, recall=r)
    return c


def random_genes(rng: np.random.Generator) -> dict[str, Any]:
    g = copy.deepcopy(FOUNDER)
    for _ in range(4):
        g = mutate(g, rng, rate=0.5, structural=0.5)
    return g


def brain_genes(g: dict[str, Any]) -> dict[str, Any]:
    """The genes a living brain can take by ``retune`` (everything but its anatomy)."""
    keys = ("eta", "eta_critic", "temperature", "lam", "gamma", "consolidation", "memory_rate",
            "threshold", "tolerance", "need", "heat")
    return {k: g[k] for k in keys}
