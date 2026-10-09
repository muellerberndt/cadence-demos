import math

import numpy as np

from arena.nursery import DUMMY
from arena.parts import stock_designs
from arena.senses import EYES, input_count, observe
from arena.world import Arena, Robot

DESIGNS = {b.name: b for b in stock_designs()}


def test_direction_cells_point_at_the_target_and_stay_in_range():
    robot = Robot.build(0, DESIGNS["Crab"])
    target = Robot.build(1, DUMMY)
    arena = Arena([robot, target], spawn=False)
    robot.place_at(0.0, 0.0, 0.0)
    for cell, bearing in enumerate((0.0, 90.0, 180.0, -90.0)):
        a = math.radians(bearing)
        target.place_at(4.0 * math.cos(a), 4.0 * math.sin(a), 0.0)
        x = observe(robot, arena)[0]
        assert x.shape == (input_count(DESIGNS["Crab"]),)
        assert np.argmax(x[:EYES]) == cell
        assert np.count_nonzero(x[:EYES]) == 1
        assert (x >= 0).all() and (x <= 1).all()
    # the robot turns: the same target moves to another cell
    robot.place_at(0.0, 0.0, math.pi / 2)  # facing +y; the last target sits at (0, -4)
    x = observe(robot, arena)[0]
    assert np.argmax(x[:EYES]) == 2  # straight behind now
    robot.place_at(0.0, 0.0, math.pi)  # facing -x: the same target is on the left
    x = observe(robot, arena)[0]
    assert np.argmax(x[:EYES]) == 1
    assert x[-1] == 1.0  # the constant drive


def test_edge_cells_read_the_ring():
    robot = Robot.build(0, DESIGNS["Cart"])
    arena = Arena([robot], radius=10.0, zone_end=10.0, zone_moments=1, spawn=False)
    robot.place_at(7.5, 0.0, 0.0)
    x = observe(robot, arena)[0]
    assert x[EYES] > 0.3 and x[EYES + 2] == 0.0  # wall ahead, nothing behind
    robot.place_at(7.5, 0.0, math.pi)
    x = observe(robot, arena)[0]
    assert x[EYES + 2] > 0.3 and x[EYES] == 0.0
    burning = Arena([robot], radius=10.0, zone_end=3.0, zone_moments=1, spawn=False)
    burning.t = 1
    robot.place_at(6.0, 0.0, math.pi)  # outside, facing the centre
    x = observe(robot, burning)[0]
    assert x[EYES] == 0.0 and x[EYES + 2] == 1.0 and x[2 * EYES + 7] == 0.0
    burning.step({0: [1, 1, 1, 1]})
    x = observe(robot, burning)[0]
    assert x[2 * EYES + 7] == 1.0 and x[2 * EYES + 5] > 0.0  # outside, in pain
