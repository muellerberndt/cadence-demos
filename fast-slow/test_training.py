"""Check temporal custody and the actual current patch law before training."""

import numpy as np
from cadence import Brain

from data import load, save
from train import build, slow_examples, delayed_cues


def test_future_outcomes_change_only_the_slow_target():
    sequence = {"name": "a", "split": 0, "x": np.zeros((16, 3)), "y": np.zeros((16, 2))}
    readings = [(np.zeros((16, 2)), np.zeros((16, 2)))]
    before = slow_examples([sequence], readings, 4)
    sequence["y"][4:8] = 0.6
    after = slow_examples([sequence], readings, 4)
    assert before[0][0] == after[0][0]
    assert after[0][1]["answer"] == [0.3, 0.3]
    assert before[0][1]["answer"] == [0, 0]


def test_corrections_cannot_arrive_before_their_delivery_block():
    class Slow:
        def settle(self, inputs):
            return {
                "qualified": True,
                "outputs": {"answer": [0.25]},
                "sweeps": 2,
                "work": {},
            }

    sequences = [{"name": "a", "x": np.zeros((12, 2)), "y": np.zeros((12, 1))}]
    cues, records = delayed_cues(
        Slow(), sequences, [(np.zeros((12, 1)), np.zeros((12, 1)))], 4
    )
    assert np.all(cues[0][:4] == 0)
    assert np.all(cues[0][4:] == 0.25)
    assert [r["source_tick"] for r in records] == [0, 4]


def test_validation_cannot_change_normalization(tmp_path):
    train = {
        "name": "train",
        "split": 0,
        "x": np.array([[0.0], [1.0]]),
        "y": np.zeros((2, 1)),
    }
    valid = {
        "name": "valid",
        "split": 1,
        "x": np.array([[1000.0]]),
        "y": np.zeros((1, 1)),
    }
    save(tmp_path / "rows.npz", [train, valid], {"domain": "fixture"})
    sequences, _, mean, scale = load(tmp_path / "rows.npz")
    assert mean.tolist() == [0.5]
    assert scale.tolist() == [0.5]
    assert sequences[1]["x"][0, 0] == 0.6 or np.isclose(sequences[1]["x"][0, 0], 0.6)


def test_small_actual_fast_and_recursive_brains_admit_and_restore():
    for recursive in (False, True):
        brain = build(2, 1, seed=2, slow=recursive, device="python")
        inputs = {
            "features": [0.2, -0.3],
            "readback" if recursive else "feedback": [0.0, 0.0] if recursive else [0.0],
        }
        result = brain.observe_batch(
            [(inputs, {"answer": [0.2]})], source="estimate", budget=8192
        )
        assert result["accepted"]
        restored = Brain.from_snapshot(brain.snapshot())
        assert restored.predict(inputs) == brain.predict(inputs)
