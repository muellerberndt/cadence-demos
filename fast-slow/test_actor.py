import threading
import time

import numpy as np

from actor import FastSlowActor
from train import build


def test_fast_settles_while_recursive_worker_is_blocked():
    started, release = threading.Event(), threading.Event()
    slow = build(2, 1, seed=3, slow=True, device="python")

    class Blocked:
        def settle(self, inputs):
            started.set()
            assert release.wait(2)
            return slow.settle(inputs)

    actor = FastSlowActor(build(2, 1, seed=2, device="python"), Blocked(), 1, period=2)
    try:
        actor.step([0.1, 0.2])
        assert started.wait(2)
        rows = [actor.step([0.2, 0.1]) for _ in range(6)]
        assert all(r["qualified"] and r["feedback_source_tick"] == -1 for r in rows)
    finally:
        release.set()
        trace = actor.close()
    assert not trace["runtime"]["worker_alive"]


def test_learned_feedback_delayed_and_expired():
    fast = build(2, 1, seed=2, device="python")
    slow = build(2, 1, seed=3, slow=True, device="python")
    clock = [0.0]
    actor = FastSlowActor(fast, slow, 1, period=3, max_age=2.0, clock=lambda: clock[0])
    try:
        actor.step([0.1, 0.2])
        deadline = time.monotonic() + 2
        while (
            actor.controller.inspect()["completed"] < 1 and time.monotonic() < deadline
        ):
            time.sleep(0.001)
        assert actor.controller.inspect()["completed"] == 1
        assert actor.step([0.1, 0.2])["feedback_source_tick"] == -1
        assert actor.step([0.1, 0.2])["feedback_source_tick"] == -1
        assert actor.step([0.1, 0.2])["feedback_source_tick"] == 0
        clock[0] = 3.0
        assert actor.step([0.1, 0.2])["feedback_source_tick"] == -1
    finally:
        actor.close()


def test_refused_fast_state_never_becomes_action_or_readback():
    class Refused:
        def settle(self, inputs):
            return {
                "qualified": False,
                "outputs": {"answer": [0.9]},
                "sweeps": 1,
                "work": {},
            }

    actor = FastSlowActor(Refused(), build(2, 1, seed=2, slow=True, device="python"), 1)
    row = actor.step(np.zeros(2))
    trace = actor.close()
    assert row["output"] is None
    assert trace["runtime"]["submitted"] == 0
