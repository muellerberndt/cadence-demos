"""Mutations always give a valid blueprint, however they chain."""

import random

from arena.evolve import mutate
from arena.parts import CHASSIS, stock_designs


def test_chained_mutations_stay_valid():
    rng = random.Random(7)
    for design in stock_designs():
        current = design
        for k in range(400):
            current, _log = mutate(current, f"{design.name}-m{k}", seed=k, rng=rng)
            assert len(current.parts) <= int(CHASSIS[current.chassis]["mounts"])
            assert any(p.kind in ("wheel", "leg") for p in current.parts)
