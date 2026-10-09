"""The public 0.80 interface preserves the source-pinned 0.79 arena recipe.

The committed browser wrapper is an immutable control, not the current native adapter.
These short tapes check wiring, acquired state, stage changes and pending-outcome custody;
they do not establish new arena competence or general default quality.
"""

from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from cadence import Brain

from arena.brain import PAGE_STAGE, RobotBrain, compose, genes_of, set_need, set_stage
from arena.parts import stock_designs
from arena.senses import input_count


@pytest.fixture(scope="module")
def previous_interface():
    path = Path(__file__).resolve().parents[1] / "showcase-app/public/pack/py/arena/brain.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "8b53c9c26488d896f68162c5afdcd1f85e7fecce25d8a30ef39127c4f3ced3ca"
    )
    spec = importlib.util.spec_from_file_location("arena._interface_079_control", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def same_life(left, right, directory):
    """Compare every persisted numerical field, plus configs, RNG and arousal history."""
    left_path, right_path = left.save(directory / "left.npz"), right.save(directory / "right.npz")
    with np.load(left_path, allow_pickle=False) as a, np.load(right_path, allow_pickle=False) as b:
        assert set(a.files) == set(b.files)
        for name in a.files:
            if a[name].dtype.kind in "biufc":
                np.testing.assert_array_equal(a[name], b[name], err_msg=name)
    assert left.learner.config == right.learner.config
    assert left.basal_ganglia.config == right.basal_ganglia.config
    assert left.basal_ganglia.updates == right.basal_ganglia.updates
    assert left.basal_ganglia.b_critic == right.basal_ganglia.b_critic
    assert left.rng.bit_generator.state == right.rng.bit_generator.state
    assert left.basal_ganglia.rng.bit_generator.state == right.basal_ganglia.rng.bit_generator.state
    assert left.arousal.to_dict() == right.arousal.to_dict()
    assert left.pending_feedback == right.pending_feedback


@pytest.mark.parametrize("body", stock_designs(), ids=lambda body: body.name)
@pytest.mark.parametrize("preset", ["founder", "chamber", "compose"])
def test_public_compose_matches_previous_wiring_and_configs(body, preset, previous_interface, tmp_path):
    body = replace(body, genes={"preset": preset})
    same_life(compose(body), previous_interface.compose(body), tmp_path)


def test_optional_observers_and_efference_keep_the_previous_layout(previous_interface, tmp_path):
    body = stock_designs()[0]
    genes = {**genes_of(body), "observers": [8], "efference_amplitude": 0.3}
    same_life(compose(body, genes), previous_interface.compose(body, genes), tmp_path)


@pytest.mark.parametrize("reset", [False, True])
def test_stage_keeps_acquired_continuation_and_next_owed_outcome(previous_interface, tmp_path, reset):
    body = stock_designs()[0]
    current, previous = compose(body), previous_interface.compose(body)
    random = np.random.default_rng(21)
    observations = random.uniform(-0.1, 1.0, (12, 1, input_count(body)))
    for index, observation in enumerate(observations[:6]):
        feedback = {} if index == 0 else {"reward": [(-1.0, 0.25, 1.0)[index % 3]]}
        np.testing.assert_array_equal(current.live(observation, **feedback), previous.live(observation, **feedback))
    assert current.basal_ganglia.updates > 0 and current.pending_feedback
    same_life(current, previous, tmp_path)

    # Carry the acquired life and pending action across save/load before the stage.
    current = Brain.load(current.save(tmp_path / "acquired.npz"))
    previous = Brain.load(previous.save(tmp_path / "control.npz"))
    stage = {**PAGE_STAGE, "reset": reset}
    set_stage(current, stage)
    previous_interface.set_stage(previous, stage)
    assert current.pending_feedback
    same_life(current, previous, tmp_path)
    resumed = Brain.load(current.save(tmp_path / "retuned.npz"))
    same_life(current, resumed, tmp_path)

    for index, observation in enumerate(observations[6:]):
        feedback = {"reward": [(-0.5, 0.2, 0.8)[index % 3]], "done": [index == 0]}
        expected = previous.live(observation, **feedback)
        np.testing.assert_array_equal(current.live(observation, **feedback), expected)
        np.testing.assert_array_equal(resumed.live(observation, **feedback), expected)
        same_life(current, previous, tmp_path)
        same_life(current, resumed, tmp_path)


@pytest.mark.parametrize("need,reset", [(None, False), (None, True), (0.1, False), (0.0, True)])
def test_need_override_matches_previous_stage(previous_interface, tmp_path, need, reset):
    body = stock_designs()[0]
    current, previous = compose(body), previous_interface.compose(body)
    x = np.zeros((1, input_count(body)))
    for brain in (current, previous):
        brain.live(x)
        brain.live(x, reward=[0.5])
    set_need(current, need, reset)
    previous_interface.set_need(previous, need, reset)
    same_life(current, previous, tmp_path)


def test_wrapper_reads_public_feedback_custody():
    brain = SimpleNamespace(pending_feedback=False)
    life = RobotBrain(stock_designs()[0], brain)
    assert not life.has_pending()
    brain.pending_feedback = True
    assert life.has_pending()
