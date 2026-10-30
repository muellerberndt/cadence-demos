import numpy as np

from arm import caregiver
from arm.world import BLOCK, BODY_SENSES, ArmSpec, World, forward, in_bin


def test_home_posture_is_above_the_table():
    w = World(ArmSpec(), seed=0)
    tip = w.tip()
    assert 0.1 < tip[2] < 0.3 and 0.15 < tip[1] < 0.45 and abs(tip[0]) < 0.01


def test_reflex_holds_the_rest_posture_and_a_load_sags_it():
    w = World(ArmSpec(), seed=0)
    for _ in range(300):
        w.frame()
    assert np.abs(w.q - w.rest).max() < 0.01
    w.set_load(1.0)
    for _ in range(300):
        w.frame()
    assert w.q[1] < w.rest[1] - 0.03  # the shoulder sags under the hand's load


def test_body_senses_shape_and_range():
    w = World(ArmSpec(), seed=0)
    b = w.body()
    assert b.shape == (BODY_SENSES,) and b.min() >= 0.0 and b.max() <= 1.0


def test_caregiver_picks_places_and_is_paid():
    w = World(ArmSpec(), seed=3)
    rewards = []
    events = []
    for _ in range(400):
        target, close, phase = caregiver.plan(w)
        steps = caregiver.ideal_steps(w, target)
        out = w.decide(steps, close)
        events.append(out["event"])
        rewards.append(out["reward"])
        if w.placed >= 2:
            break
    assert w.placed >= 2, (events[-20:], w.snapshot())
    assert max(rewards) == 1.0 and w.wrong == 0


def test_wear_makes_the_usual_grasp_height_fail():
    w = World(ArmSpec(), seed=5)
    w.spec = ArmSpec()
    top = w.block_top()
    # place the fingertip right above the block at the usual height by setting the posture
    for _ in range(60):
        target = np.array([w.block[0], w.block[1], top + 0.02])
        w.decide(caregiver.ideal_steps(w, target), 0)
    assert np.linalg.norm(w.tip() - np.array([w.block[0], w.block[1], top + 0.02])) < 0.02
    w.set_wear(0.02)
    out = w.decide(np.zeros(4), 1)
    assert out["event"] == "missed" and not w.holding


def test_random_scenes_keep_the_hand_over_the_table():
    w = World(ArmSpec(), seed=1)
    for _ in range(50):
        w.randomize()
        tip = w.tip()
        assert tip[2] > 0.03 and -0.35 < tip[0] < 0.35 and 0.10 < tip[1] < 0.50
        if w.holding:
            assert np.allclose(w.block, tip - [0, 0, BLOCK / 2])
    assert in_bin(*w.bins["A"], w.bins) == "A"


def test_snapshot_round_trip():
    w = World(ArmSpec(), seed=2)
    w.randomize()
    s = w.snapshot()
    v = World(ArmSpec(), seed=9)
    v.restore(s)
    assert np.allclose(v.q, w.q) and v.order == w.order and np.allclose(v.block, w.block)
