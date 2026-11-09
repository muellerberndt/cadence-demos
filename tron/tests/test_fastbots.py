"""The Numba look-ahead bots return the Python bots' moves."""
import random

from tron import bots, fastbots, school
from tron.world import Arena, mulberry32




def test_same_moves():
    rng = random.Random(1)
    n = 0
    for g in range(40):
        s = 3_000_000 + g
        arena, draw = Arena(24, seed=s), mulberry32(s)
        while not arena.over:
            if rng.random() < 0.15:
                for seat in (0, 1):
                    assert fastbots.voronoi2(arena, seat) == bots.voronoi2(arena, seat)
                    assert fastbots.voronoi3(arena, seat) == bots.voronoi3(arena, seat)
                    n += 1
            arena.step((school.POOL["voronoi20"](arena, 0, draw), school.POOL["safe"](arena, 1, draw)))
    assert n > 200
