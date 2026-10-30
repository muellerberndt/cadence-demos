import numpy as np

from arm.world import ArmSpec, World, forward
from arm1 import brains, teacher
from arm1.actions import CARTESIAN_SLOTS, HOLD, JOINT_SLOTS, delta_of, execute, ik_steps, jacobian
from arm1.job import STAGES, RandomPolicy, TeacherPolicy, commands_at_starts, job_assay
from arm1.senses import INPUTS, OBJECT, blind, observe


def test_observation_shape_range_and_blind_twin():
    w = World(ArmSpec(), seed=3)
    x = observe(w)
    assert x.shape == (INPUTS,) and x.min() >= 0.0 and x.max() <= 1.0 + 1e-12
    assert x[OBJECT].max() > 0.5  # the object terms carry a bump
    b = blind(x)
    assert b[OBJECT].max() == 0.0 and np.array_equal(b[: OBJECT.start], x[: OBJECT.start])


def test_jacobian_matches_finite_differences():
    spec = ArmSpec()
    rng = np.random.default_rng(0)
    for _ in range(5):
        q = rng.uniform(spec.low, spec.high)
        j = jacobian(spec, q)
        eps = 1e-6
        fd = np.zeros((3, 4))
        for k in range(4):
            dq = np.zeros(4)
            dq[k] = eps
            fd[:, k] = (forward(spec, q + dq)[3] - forward(spec, q - dq)[3]) / (2 * eps)
        assert np.abs(j - fd).max() < 1e-5


def test_reflex_moves_the_fingertip_the_commanded_way():
    w = World(ArmSpec(), seed=0)
    for _ in range(120):
        w.frame()
    for answer in ([4, 2, 2, 0], [2, 0, 2, 0], [2, 2, 4, 0], [2, 2, 0, 0]):
        before = w.tip().copy()
        steps = ik_steps(w, delta_of(answer))
        assert np.abs(steps).max() <= 2.0
        for _ in range(3):  # three decisions of the same command, settled
            execute(w, answer, "cartesian")
        moved = w.tip() - before
        wanted = delta_of(answer) * 3
        axis = int(np.argmax(np.abs(wanted)))
        assert np.sign(moved[axis]) == np.sign(wanted[axis])
        assert abs(moved[axis]) > 0.5 * abs(wanted[axis])
        off = np.delete(moved, axis)
        assert np.abs(off).max() < 0.5 * abs(wanted[axis])


def test_cartesian_labels_point_at_the_plan_and_hold_near_it():
    w = World(ArmSpec(), seed=1)
    labels = teacher.cartesian_labels(w)
    assert len(labels) == 4 and all(0 <= v <= 4 for v in labels[:3]) and labels[3] in (0, 1)
    assert len(teacher.joint_labels(w)) == 5


def test_teacher_completes_jobs_through_the_reflex():
    r = job_assay(TeacherPolicy("cartesian"), "cartesian", trials=8, seed=123, cap=80)
    assert set(STAGES) <= set(r) and "reached_hover" in r
    assert r["right"] == 1.0 and r["grasped"] == 1.0 and r["wrong"] == 0.0
    assert r["gates"]["effort_nms"] > 0 and r["gates"]["path_cm"] > 0


def test_random_policy_is_the_floor_and_starts_count_commands():
    r = job_assay(RandomPolicy("cartesian", 5), "cartesian", trials=4, seed=321, cap=20)
    assert r["right"] == 0.0
    s = commands_at_starts(TeacherPolicy("cartesian"), "cartesian", starts=10, seed=9)
    assert s["distinct"] >= 3 and 0.0 <= s["holds"] <= 1.0
    s = commands_at_starts(TeacherPolicy("joint"), "joint", starts=4, seed=9)
    assert len(s["most_common"]) == len(JOINT_SLOTS)


def test_every_arm_composes_on_its_pools():
    for arm in brains.ARMS:
        pools = brains.DEFAULT_POOLS[arm]
        b = brains.compose(arm, pools, seed=0)
        sizes = CARTESIAN_SLOTS if pools == "cartesian" else JOINT_SLOTS
        assert len(b.motor_index) == sum(sizes) and b.learner.config.surprise is True
        x = np.zeros((2, INPUTS))
        x[:, 0] = 1.0
        answer = b.act(x, greedy=True)
        assert answer.shape == (2, len(sizes))
        if arm == "D4":
            assert b.recall is not None and b.recall.acted.shape == (2, sum(sizes))
    steps = brains.set_steps(brains.compose("D1", "cartesian", 0), 0.03)
    assert abs(steps["eta"] - 0.03) < 1e-12 and abs(steps["eta_bias"] - 0.003) < 1e-12
    assert HOLD == 2
