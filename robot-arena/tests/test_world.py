import math

import numpy as np

from arena.nursery import DUMMY
from arena.parts import Blueprint, Part
from arena.world import DT, Arena, Robot

TUMBLER = Blueprint("T", "light", (Part("wheel", 90), Part("wheel", -90), Part("arm", 0, "spike")))
MANTIS = Blueprint(
    "M", "medium",
    (Part("leg", 50), Part("leg", -50), Part("leg", 130), Part("leg", -130), Part("arm", 0, "hammer")),
)


def drive(bp, commands, moments):
    robot = Robot.build(0, bp)
    arena = Arena([robot], seed=1, spawn=False)
    robot.place_at(0.0, 0.0, 0.0)
    for t in range(moments):
        arena.step({0: commands(t, robot)})
    return robot


def test_wheels_drive_forward_and_one_wheel_turns_the_robot():
    robot = drive(TUMBLER, lambda t, r: [2, 2, 1], 60)
    assert robot.x > 3.0 and abs(robot.y) < 1e-6 and abs(robot.heading) < 1e-6
    robot = drive(TUMBLER, lambda t, r: [2, 1, 1], 6)
    assert robot.omega < 0  # the left wheel alone turns the body to the right
    robot = drive(TUMBLER, lambda t, r: [1, 2, 1], 6)
    assert robot.omega > 0


def test_legs_push_both_ways_and_the_reflex_swings_a_spent_leg():
    forward = drive(MANTIS, lambda t, r: [0, 0, 0, 0, 1], 100)
    assert forward.x > 3.0 and abs(forward.heading) < 0.3
    backward = drive(MANTIS, lambda t, r: [2, 2, 2, 2, 1], 100)
    assert backward.x < -3.0
    # one side pushing turns the body: left legs (mounts +50, +130) alone turn it right
    turned = drive(MANTIS, lambda t, r: [0, 1, 0, 1, 1], 30)
    assert turned.omega < 0
    # a leg that spends its stride lifts (unplanted) and swings to the other end on its own
    robot = Robot.build(0, MANTIS)
    arena = Arena([robot], seed=1, spawn=False)
    robot.place_at(0.0, 0.0, 0.0)
    lifted = False
    for _ in range(25):  # 16 moments of stroke, 8 of reflex swing, one more stroke
        arena.step({0: [0, 1, 1, 1, 1]})
        lifted = lifted or not robot.planted[0]
    assert lifted and robot.planted[0] and robot.stride[0] > 0.8

    # diagonal pairs out of phase walk smoother than all legs in step
    def trot(t, r):
        a = (t // 16) % 2 == 0
        return [0 if a else 1, 1 if a else 0, 1 if a else 0, 0 if a else 1, 1]

    def speeds(fn):
        robot = Robot.build(0, MANTIS)
        arena = Arena([robot], seed=1, spawn=False)
        robot.place_at(-8.0, 0.0, 0.0)
        out = []
        for t in range(120):
            arena.step({0: fn(t, robot)})
            out.append(math.hypot(robot.vx, robot.vy))
        return np.array(out[40:])

    assert speeds(trot).std() < speeds(lambda t, r: [0, 0, 0, 0, 1]).std()


def test_spike_and_ram_hurt_a_dummy_and_the_ring_burns_outside():
    attacker = Robot.build(0, TUMBLER)
    dummy = Robot.build(1, DUMMY)
    arena = Arena([attacker, dummy], seed=1, spawn=False)
    attacker.place_at(-2.5, 0.0, 0.0)
    dummy.place_at(0.0, 0.0, 0.0)
    dealt = 0.0
    for _ in range(100):
        out = arena.step({0: [2, 2, 1], 1: [1]})
        dealt += out[0]["dealt"]
    assert dealt > 5.0
    assert dummy.hp < DUMMY.hp
    assert attacker.hp < TUMBLER.hp  # ramming hurts the rammer too, the lighter one more
    assert attacker.hp > dummy.hp - 100  # sanity: nobody is dead

    parked = Robot.build(0, TUMBLER)
    ring = Arena([parked], seed=1, zone_moments=50, spawn=False)
    parked.place_at(8.0, 0.0, 0.0)
    for _ in range(100):
        ring.step({0: [1, 1, 1]})
    assert parked.outside and parked.hp < TUMBLER.hp
    assert ring.zone_radius() == 2.5


def test_elimination_and_placement():
    a, b = Robot.build(0, TUMBLER), Robot.build(1, TUMBLER)
    arena = Arena([a, b], seed=1, spawn=False)
    a.place_at(0.0, 0.0, 0.0)
    b.place_at(5.0, 0.0, 0.0)
    b.hp = 0.5
    out = arena.step({0: [1, 1, 1], 1: [1, 1, 1]})
    assert out[1]["alive"] and b.place is None
    b.hp = -1.0
    arena.step({0: [1, 1, 1], 1: [1, 1, 1]})
    assert not b.alive and b.place == 2 and b.died_at == 2
    arena.finish()
    assert a.place == 1


def test_commands_must_match_the_motors():
    robot = Robot.build(0, TUMBLER)
    arena = Arena([robot], seed=1)
    try:
        arena.step({0: [1, 1]})
    except ValueError as error:
        assert "motors" in str(error)
    else:
        raise AssertionError("a short command list was accepted")


def test_collision_separation_keeps_weapons_attached_without_inventing_a_strike():
    hammer = Blueprint(
        "Hammer", "light",
        (Part("wheel", 90), Part("wheel", -90), Part("arm", 0, "hammer")),
    )
    attacker, dummy = Robot.build(0, hammer), Robot.build(1, DUMMY)
    arena = Arena([attacker, dummy], spawn=False, zone_end=10.0)
    attacker.place_at(0.0, 0.0, 0.0)
    dummy.place_at(0.8, 0.0, 0.0)  # the solver must separate this stationary overlap
    for _ in range(3):
        outcome = arena.step({0: [1, 1, 1], 1: [1]})
        np.testing.assert_allclose(attacker.tip[2], attacker.arm_tip(2), atol=1e-15)
        np.testing.assert_array_equal(attacker.tip_vel[2], [0.0, 0.0])
        assert outcome[0]["dealt"] == 0.0
        assert outcome[1]["taken"] == 0.0
    assert attacker.x < 0.0 and dummy.x > 0.8  # separation really happened

    # Genuine joint motion still produces a blow with the same contact geometry.
    outcome = arena.step({0: [1, 1, 2], 1: [1]})
    assert np.linalg.norm(attacker.tip_vel[2]) > 1.0
    assert outcome[0]["dealt"] > 0.0
    assert outcome[1]["taken"] == outcome[0]["dealt"]


def test_the_finishing_blow_is_credited_as_a_kill_and_a_burn_death_is_not():
    attacker = Robot.build(0, TUMBLER)
    dummy = Robot.build(1, DUMMY)
    arena = Arena([attacker, dummy], seed=1, spawn=False)
    attacker.place_at(-2.5, 0.0, 0.0)
    dummy.place_at(0.0, 0.0, 0.0)
    dummy.hp = 1.0
    kills = 0
    for _ in range(100):
        out = arena.step({0: [2, 2, 1], 1: [1]})
        kills += out[0]["kills"]
        if not dummy.alive:
            break
    assert not dummy.alive and kills == 1
    assert sum(arena.step({0: [1, 1, 1], 1: [1]})[0]["kills"] for _ in range(3)) == 0  # credited once

    burner, bystander = Robot.build(0, TUMBLER), Robot.build(1, TUMBLER)
    ring = Arena([burner, bystander], seed=1, zone_moments=50, spawn=False)
    burner.place_at(8.0, 0.0, 0.0)
    bystander.place_at(0.0, 0.0, 0.0)
    burner.hp = 0.5
    credited = 0
    for _ in range(100):
        out = ring.step({0: [1, 1, 1], 1: [1, 1, 1]})
        credited += out[1]["kills"]
        if not burner.alive:
            break
    assert not burner.alive and credited == 0
