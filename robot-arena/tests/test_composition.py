"""The arena's brain on the pinned cadence-net: what the founder composes, and how a ring
stage changes a living brain without losing what it acquired or the outcome it is owed."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from cadence import Brain

from arena.brain import PAGE_STAGE, RobotBrain, compose, genes_of, set_need, set_stage
from arena.parts import stock_designs
from arena.senses import input_count


def same_life(left, right, directory):
    """Two brains whose checkpoints hold the same arrays."""
    left_path, right_path = left.save(directory / "left.npz"), right.save(directory / "right.npz")
    with np.load(left_path, allow_pickle=False) as a, np.load(right_path, allow_pickle=False) as b:
        assert set(a.files) == set(b.files)
        for key in a.files:
            np.testing.assert_array_equal(a[key], b[key], err_msg=key)


@pytest.mark.parametrize("body", stock_designs(), ids=lambda body: body.name)
def test_the_founder_composes_without_the_recall_memory(body):
    brain = compose(body)
    memories = brain.describe().get("memories", {})
    assert "recall" not in memories and "working_memory" in memories
    assert len(brain.motor_index) == sum(body.slots)
    assert len(brain.sensory_index) == input_count(body)


def test_a_blueprint_can_turn_the_recall_memory_on():
    body = replace(stock_designs()[0], genes={"recall": True})
    assert genes_of(body)["recall"] is True
    assert "recall" in compose(body).describe().get("memories", {})


@pytest.mark.parametrize("preset", ["chamber", "compose"])
def test_the_controls_compose(preset):
    body = replace(stock_designs()[0], genes={"preset": preset})
    assert compose(body).arousal is not None


@pytest.mark.parametrize("reset", [False, True])
def test_stage_keeps_acquired_continuation_and_next_owed_outcome(tmp_path, reset):
    body = stock_designs()[0]
    brain = compose(body)
    random = np.random.default_rng(21)
    observations = random.uniform(-0.1, 1.0, (12, 1, input_count(body)))
    for index, observation in enumerate(observations[:6]):
        feedback = {} if index == 0 else {"reward": [(-1.0, 0.25, 1.0)[index % 3]]}
        brain.live(observation, **feedback)
    assert brain.basal_ganglia.updates > 0 and brain.pending_feedback
    before = np.array(brain.learner.brain.weights, copy=True)

    # Carry the acquired life and the pending action across save/load, then enter the ring.
    brain = Brain.load(brain.save(tmp_path / "acquired.npz"))
    set_stage(brain, {**PAGE_STAGE, "reset": reset})
    assert brain.pending_feedback
    np.testing.assert_array_equal(np.asarray(brain.learner.brain.weights), before)
    resumed = Brain.load(brain.save(tmp_path / "retuned.npz"))
    same_life(brain, resumed, tmp_path)

    for index, observation in enumerate(observations[6:]):
        feedback = {"reward": [(-0.5, 0.2, 0.8)[index % 3]], "done": [index == 0]}
        np.testing.assert_array_equal(brain.live(observation, **feedback), resumed.live(observation, **feedback))


@pytest.mark.parametrize("reset", [False, True])
def test_need_override_keeps_the_life(tmp_path, reset):
    body = stock_designs()[0]
    brain = compose(body)
    observation = np.zeros((1, input_count(body)))
    brain.live(observation)
    assert brain.arousal.config.need == pytest.approx(0.05)
    set_need(brain, 0.0, reset)
    assert brain.arousal.config.need == 0.0
    assert brain.pending_feedback


def test_wrapper_reads_public_feedback_custody():
    brain = SimpleNamespace(pending_feedback=False)
    life = RobotBrain(stock_designs()[0], brain)
    assert not life.has_pending()
    brain.pending_feedback = True
    assert life.has_pending()
