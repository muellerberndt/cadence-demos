import numpy as np

from arena.brain import FrozenPolicy, RandomPolicy, RobotBrain, compose, genes_of, hold_commands
from arena.nursery import DUMMY, run_nursery
from arena.parts import stock_designs
from arena.senses import input_count, observe
from arena.world import Arena, Robot

DESIGNS = {b.name: b for b in stock_designs()}


def test_every_motor_is_a_slot_of_the_one_brain():
    bp = DESIGNS["Hexapod"]
    brain = compose(bp)
    assert list(brain.learner.slot_sizes) == bp.slots
    assert len(brain.motor_index) == bp.motor_neurons
    assert len(brain.sensory_index) == input_count(bp)
    assert brain.efference is None and brain.arousal is not None  # the founder carries no copy
    with_copy = compose(bp, {**genes_of(bp), "efference_amplitude": 3.0})
    assert len(with_copy.connectome.populations["efference"]) == bp.motor_neurons


def test_genes_merge_over_the_founder():
    bp = DESIGNS["Tumbler"]
    assert genes_of(bp)["lam"] == 0.6 and genes_of(bp)["efference_amplitude"] == 0.0
    from dataclasses import replace

    g = genes_of(replace(bp, genes={"lam": 0.5, "arousal": {"need": 0.3}}))
    assert g["lam"] == 0.5 and g["arousal"]["need"] == 0.3 and g["arousal"]["youth"] == 300
    chamber = genes_of(replace(bp, genes={"preset": "chamber"}))
    assert chamber["efference_amplitude"] == 3.0 and chamber["eta"] == 0.1


def test_a_life_continues_identically_from_a_checkpoint(tmp_path):
    bp = DESIGNS["Tumbler"]
    robot, target = Robot.build(0, bp), Robot.build(1, DUMMY)
    arena = Arena([robot, target], spawn=False)
    robot.place_at(0.0, 0.0, 0.0)
    target.place_at(3.0, 1.0, 0.0)
    life = RobotBrain.newborn(bp)
    reward = None
    for _ in range(12):
        reading = life.moment(observe(robot, arena), reward)
        assert len(reading["commands"]) == bp.motors
        out = arena.step({0: reading["commands"], 1: [1]})
        reward = out[0]["dealt"] / 20.0
    path = life.save(tmp_path / "life.npz")
    twin = RobotBrain.load(bp, path)
    for _ in range(6):
        x = observe(robot, arena)
        a = life.moment(x, reward)
        b = twin.moment(x, reward)
        assert a["commands"] == b["commands"]
        out = arena.step({0: a["commands"], 1: [1]})
        reward = (out[0]["dealt"] - out[0]["taken"]) / 20.0
    assert life.refusals == 0
    assert life.describe()["age"] == 18


def test_baselines_answer_with_one_command_per_motor():
    bp = DESIGNS["Mantis"]
    x = np.zeros((1, input_count(bp)))
    assert len(RandomPolicy(bp).moment(x, None)["commands"]) == bp.motors
    frozen = FrozenPolicy(bp, compose(bp))
    for reward in (None, 1.0, -1.0):
        reading = frozen.moment(x, reward)
        assert all(0 <= c < size for c, size in zip(reading["commands"], bp.slots, strict=True))
        assert reading["learning_sweeps"] == 0 and reading["mode"] == "frozen"
    assert frozen.brain.arousal.learning_sweeps == 0  # a frozen brain never learns
    assert hold_commands(bp) == [1, 1, 1, 1, 1]


def test_a_short_nursery_runs_and_reports():
    report = run_nursery(DESIGNS["Cart"], moments=120, seed=3, block=60)
    assert report["moments"] == 120 and len(report["blocks"]) == 2
    assert report["brain"]["age"] == 120
    assert report["total"]["refused"] == 0
    random = run_nursery(DESIGNS["Cart"], moments=120, seed=3, policy="random", block=60)
    assert random["policy"] == "random"
