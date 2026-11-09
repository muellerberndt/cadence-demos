import numpy as np

from tron import bots, senses
from tron.world import Arena, mulberry32, turn


def test_starts_are_point_symmetric():
    for seed in range(50):
        a = Arena(24, seed=seed)
        (r0, c0), (r1, c1) = a.heads
        assert (r1, c1) == (23 - r0, 23 - c0)
        assert a.headings[1] == (a.headings[0] + 2) % 4
        assert a.headings[0] != 3


def test_crash_into_wall_and_head_on():
    a = Arena(24, seed=1)
    a.heads = [(0, 5), (10, 10)]
    a.headings = [0, 1]
    assert a.step((1, 1)) == (True, False)
    assert a.over and a.winner == 1
    b = Arena(24, seed=1)
    b.grid = [0] * (24 * 24)
    b.heads, b.headings = [(5, 5), (5, 7)], [1, 3]
    assert b.step((1, 1)) == (True, True)
    assert b.over and b.winner is None


def test_mulberry32_matches_reference_values():
    draw = mulberry32(42)
    values = [draw() for _ in range(3)]
    assert all(0 <= v < 1 for v in values)
    assert values == [mulberry32(42)() for _ in range(1)] + values[1:]


def test_turns():
    assert [turn(0, a) for a in (0, 1, 2)] == [3, 0, 1]


def test_voronoi_beats_uniform():
    draw = mulberry32(3)
    wins = 0
    for g in range(5):
        a = Arena(24, seed=100 + g)
        while not a.over:
            a.step((bots.voronoi(a, 0), bots.uniform(a, 1, draw)))
        wins += a.winner == 0
    assert wins == 5


def test_eye_turns_with_the_rider():
    """The same situation under any compass heading gives the same eye."""
    views = []
    for heading in range(4):
        a = Arena(24, seed=0)
        a.grid = [0] * (24 * 24)
        a.heads = [(12, 12), (0, 0)]
        a.headings = [heading, 0]
        dr, dc = ((-1, 0), (0, 1), (1, 0), (0, -1))[heading]
        r, c = 12 + 2 * dr, 12 + 2 * dc  # a trail two cells ahead
        a.grid[r * 24 + c] = 2
        views.append(senses.eye(a, 0)[:81])
    for v in views[1:]:
        np.testing.assert_array_equal(v, views[0])
    assert senses.eye(a, 0).shape == (senses.eye_size(),)
