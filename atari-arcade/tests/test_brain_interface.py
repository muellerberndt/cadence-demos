"""The current native factory keeps the archived explicit recipe on Cadence 0.80.

The old Python recipe is evaluated on the candidate runtime. This does not rewrite
the browser's 0.70 fixture or establish numerical parity with older runtimes.
"""

import hashlib
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from cadence import Brain

import server


@pytest.fixture(scope="module")
def previous_recipe():
    path = Path(__file__).resolve().parents[1] / "web/tools/make_parity_fixture.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "46b266194bc8a88f42f816a13373f2fb68f891e428473862dc933948f1b7345e"
    )
    spec = importlib.util.spec_from_file_location("arcade_previous_recipe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def same_checkpoint(left, right, directory):
    with (
        np.load(left.save(directory / "left.npz"), allow_pickle=False) as a,
        np.load(right.save(directory / "right.npz"), allow_pickle=False) as b,
    ):
        assert set(a.files) == set(b.files)
        for name in a.files:
            np.testing.assert_array_equal(a[name], b[name], err_msg=name)


@pytest.mark.parametrize("actions", [3, 4])
def test_pixel_sized_factory_keeps_explicit_recipe(previous_recipe, actions):
    before, after = previous_recipe.compose(server.N_SCREEN, actions), server.build_brain(actions)
    assert before.learner.config == after.learner.config
    assert before.basal_ganglia.config == after.basal_ganglia.config
    for name in ("pre", "post", "count", "sign"):
        np.testing.assert_array_equal(getattr(before.connectome, name), getattr(after.connectome, name))
    np.testing.assert_array_equal(before.brain.efficacy, after.brain.efficacy)
    assert len(after.sensory_index) == 7056


@pytest.mark.parametrize("actions", [3, 4])
def test_watched_rewarded_and_saved_tape_keeps_owned_continuation(
    previous_recipe, actions, monkeypatch, tmp_path
):
    monkeypatch.setattr(server, "N_SCREEN", 12)
    before, after = previous_recipe.compose(12, actions), server.build_brain(actions)
    for t in range(3):
        screen, label = previous_recipe.screen(t, 12), np.array([(2 * t + 1) % actions])
        own = []
        for brain in (before, after):
            drive = brain.stimulus(screen)
            own.append(brain.act(screen, greedy=True))
            brain.learner.step(drive, label)
        np.testing.assert_array_equal(*own)
    for t in range(3, 7):
        screen = previous_recipe.screen(t, 12)
        feedback = {} if t == 3 else {"reward": [(-1.0, 0.0, 1.0)[t % 3]], "done": [t == 5]}
        np.testing.assert_array_equal(before.step(screen, **feedback), after.step(screen, **feedback))
    assert after.pending_feedback and after.basal_ganglia.updates == 3
    same_checkpoint(before, after, tmp_path)

    restored = Brain.load(after.save(tmp_path / "acquired.npz"))
    for t in range(7, 10):
        screen, reward = previous_recipe.screen(t, 12), [float(t % 2)]
        expected = before.step(screen, reward=reward)
        np.testing.assert_array_equal(after.step(screen, reward=reward), expected)
        np.testing.assert_array_equal(restored.step(screen, reward=reward), expected)
    same_checkpoint(before, after, tmp_path)
    same_checkpoint(after, restored, tmp_path)
