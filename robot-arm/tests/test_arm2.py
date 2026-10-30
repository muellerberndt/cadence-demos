import numpy as np

from arm2 import brains, teacher
from arm2.actions import CARTESIAN_SLOTS, JOINT_SLOTS, execute
from arm2.job import STAGES, TeacherPolicy, job_assay
from arm2.scene import HOME_Q, R_DOWN, PandaWorld
from arm2.senses import OBJECT, blind, inputs, observe


def test_scene_builds_and_home_hand_points_down():
    w = PandaWorld(seed=0)
    tip = w.tip()
    assert 0.4 < tip[0] < 0.7 and abs(tip[1]) < 0.02 and 0.4 < tip[2] < 0.6
    assert np.abs(w.tip_rotation() - R_DOWN).max() < 0.02
    assert w.block_pos()[2] > 0 and not w.holding


def test_randomize_draws_physics_and_a_reachable_posture():
    w = PandaWorld(seed=3, physics="heldout")
    w.randomize()
    assert 0.015 <= w.half <= 0.03
    assert 0.15 <= w.model.body_mass[w.block_body] <= 0.25
    assert 0.1 < w.tip()[2] < 0.4 and 0.3 < w.tip()[0] < 0.65


def test_observation_layout_and_blind_twin():
    w = PandaWorld(seed=1)
    w.randomize()
    x = observe(w, "cartesian")
    assert x.shape == (inputs("cartesian"),) and inputs("cartesian") == 262
    assert x.min() >= 0.0 and x.max() <= 1.0 + 1e-12
    assert blind(x)[OBJECT].max() == 0.0
    assert observe(w, "cartesian", velocity=False).shape == x.shape
    assert observe(w, "joint").shape == (inputs("joint"),)


def test_reflex_moves_the_tcp_the_commanded_way():
    w = PandaWorld(seed=0)
    w.set_posture(HOME_Q)
    for _ in range(3):
        execute(w, [2, 2, 2, 0], "cartesian")  # settle under gravity
    for answer in ([4, 2, 2, 0], [2, 0, 2, 0], [2, 2, 0, 0]):
        before = w.tip()
        for _ in range(3):
            execute(w, answer, "cartesian")
        moved = w.tip() - before
        wanted = (np.array(answer[:3]) - 2) * 0.01 * 3
        axis = int(np.argmax(np.abs(wanted)))
        assert np.sign(moved[axis]) == np.sign(wanted[axis]) and abs(moved[axis]) > 0.4 * abs(wanted[axis])
        assert np.abs(w.tip_rotation() - R_DOWN).max() < 0.1


def test_teacher_labels_and_completes_jobs():
    w = PandaWorld(seed=2)
    w.randomize()
    labels = teacher.cartesian_labels(w)
    assert len(labels) == 4 and all(0 <= v <= 4 for v in labels[:3])
    assert len(teacher.joint_labels(w)) == 8
    r = job_assay(TeacherPolicy("cartesian"), "cartesian", trials=3, seed=321, cap=80)
    assert set(STAGES) <= set(r) and r["grasped"] >= 0.6 and r["right"] >= 0.6  # the ceiling itself: arm2.teacher --trials 100
    assert r["gates"]["jerk"] is not None and r["gates"]["effort_nms"] > 0


def test_arms_compose_on_the_contact_observation():
    for arm in ("D1", "D1nv", "D2", "D4"):
        pools = brains.DEFAULT_POOLS[arm]
        b = brains.compose(arm, pools, seed=0)
        sizes = CARTESIAN_SLOTS if pools == "cartesian" else JOINT_SLOTS
        assert len(b.motor_index) == sum(sizes) and len(b.sensory_index) == inputs(pools)
