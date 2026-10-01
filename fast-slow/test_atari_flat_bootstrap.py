"""Causal and qualification gates for the bounded native Freeway collector."""

import copy
import json

import atari_flat_bootstrap as a
import numpy as np
import pytest

from cadence import Brain


def test_pixels_and_executed_action_are_the_only_feature_sources():
    image = np.full((210, 160, 3), 255, np.uint8)
    x, pooled = a.features(image, None, 2, 3)
    assert x.shape == (843,)
    assert np.allclose(x[:420], 1)
    assert np.all(x[420:840] == 0)
    assert x[840:].tolist() == [0, 0, 1]
    next_x, _ = a.features(np.zeros_like(image), pooled, 1, 3)
    assert np.allclose(next_x[420:840], -1)
    assert next_x[840:].tolist() == [0, 1, 0]


def test_schedule_is_one_complete_shared_training_permutation():
    rows = a.schedule()
    assert len(rows) == 64 and all(len(row) == 16 for row in rows)
    assert sorted(i for row in rows for i in row) == list(range(1024))
    assert rows == a.schedule()
    assert len({*a.TRAIN_SEEDS, a.HELD_SEED, *a.PLAY_SEEDS}) == 6


def test_exact_flat_graph_and_real_common_rule_learning():
    brain = a.make_brain(211, device="python")
    assert brain.graph.n_patches == 3 and brain.graph.n_inputs == 843
    assert len(brain.weights) + len(brain.biases) == 2532
    assert all(k == "input" for k, _, _ in brain.graph.edges)
    inputs = {"visible": [0.0] * 843}
    before = brain.settle(inputs)
    r = a.admit(brain, [(inputs, {"motor": a.action_targets(1, 3)})], 0)
    assert r["accepted"] and r["qualified"]
    assert r["event_id"] == 1 and r["source"] == "witness"
    after = brain.settle(inputs)
    assert after["qualified"]
    target = np.asarray(a.action_targets(1, 3))
    assert (
        np.abs(np.asarray(after["outputs"]["motor"]) - target).mean()
        < np.abs(np.asarray(before["outputs"]["motor"]) - target).mean()
    )
    snapshot = brain.snapshot()
    restored = Brain.from_snapshot(snapshot)
    assert restored.settle(inputs) == after
    assert restored.snapshot() == snapshot


class Body:
    def __init__(self):
        self.actions = []

    def reset(self, seed):
        self.actions.clear()
        return np.zeros((210, 160, 3), np.uint8), {}

    def step(self, action):
        self.actions.append(action)
        return (
            np.full((210, 160, 3), len(self.actions), np.uint8),
            float(action == 1),
            len(self.actions) >= 3,
            False,
            {},
        )


class StubBrain:
    def __init__(self, qualified):
        self.qualified = qualified

    def snapshot(self):
        return '{"fixed": true}'

    def settle(self, inputs):
        return {
            "qualified": self.qualified,
            "outputs": {"motor": [0, 0.5, -0.1]},
            "work": {},
        }


def test_native_refusal_never_executes_fallback_or_fabricates_outcome(tmp_path):
    body = Body()
    journal = a.Journal(tmp_path)
    result = a.native_episode(
        body,
        0,
        brain=StubBrain(False),
        mean=np.zeros(843),
        scale=np.ones(843),
        journal=journal,
    )
    assert body.actions == [0]  # Declared reset start only.
    assert result["refused"] and result["decisions"] == 0 and result["actions"] == []
    assert not (tmp_path / "transitions.jsonl").exists()


def test_serial_actions_have_actual_observation_reward_custody(tmp_path):
    body = Body()
    journal = a.Journal(tmp_path)
    result = a.native_episode(
        body,
        0,
        brain=StubBrain(True),
        mean=np.zeros(843),
        scale=np.ones(843),
        journal=journal,
    )
    assert body.actions == [0, 1, 1]
    assert result["terminated"] and not result["censored"] and result["return"] == 2
    rows = [
        json.loads(line)
        for line in (tmp_path / "transitions.jsonl").read_text().splitlines()
    ]
    assert rows == result["actions"]
    assert rows[0]["next_observation_sha256"] == rows[1]["observation_sha256"]
    assert not (tmp_path / "body-inflight.json").exists()
    assert len(journal.rows) == 2


def good_report():
    base = [
        {
            "seed": s,
            "baseline": "teacher",
            "return": 10,
            "terminated": True,
            "truncated": False,
        }
        for s in a.PLAY_SEEDS
    ]
    report = {
        "status": "complete",
        "sources_unchanged": True,
        "accepted_updates": 64,
        "refused_calls": 0,
        "unknown_calls": 0,
        "final_heldout": {"qualified": 512, "agreement": 1.0},
        "episodes": [
            {
                "seed": s,
                "return": 8,
                "terminated": True,
                "truncated": False,
                "refused": False,
            }
            for s in a.PLAY_SEEDS
        ],
    }
    return report, base


@pytest.mark.parametrize(
    "failure",
    [
        "refused",
        "censored",
        "missing",
        "accuracy",
        "return",
        "source",
        "unknown",
        "truncated",
    ],
)
def test_gates_cannot_promote_failed_or_missing_cases(failure):
    report, base = good_report()
    assert a.gates(report, base)
    report = copy.deepcopy(report)
    if failure == "refused":
        report["refused_calls"] = 1
    elif failure == "censored":
        report["episodes"][0]["terminated"] = False
    elif failure == "missing":
        report["episodes"].pop()
    elif failure == "accuracy":
        report["final_heldout"]["agreement"] = 0.94
    elif failure == "return":
        report["episodes"][0]["return"] = 7
    elif failure == "source":
        report["sources_unchanged"] = False
    elif failure == "truncated":
        report["episodes"][0]["truncated"] = True
    else:
        report["unknown_calls"] = 1
    assert not a.gates(report, base)


def test_failed_call_preserves_attempt_and_unknown_work(tmp_path):
    journal = a.Journal(tmp_path)
    with pytest.raises(a.TimeCap):
        journal.call(
            StubBrain(True),
            {"kind": "admission"},
            lambda: (_ for _ in ()).throw(a.TimeCap()),
        )
    assert journal.rows[0]["unknown_solver_work"]
    assert (tmp_path / "inflight.json").exists()


def test_latency_counts_all_calls_and_deadline_misses():
    values = a.latency([0.01, 0.08, 0.1])
    assert values["calls"] == 3 and values["misses_15hz"] == 2
    assert values["seconds"] == pytest.approx(0.19)


def test_compact_receipt_preserves_every_nonparameter_field_and_parameter_identity():
    full = {
        "weights": (1.0, 2.0),
        "biases": (0.1,),
        "state": (0.2,),
        "qualified": True,
        "work": {"evaluations": 3},
    }
    compact = a.compact_result(full)
    assert compact == {
        "parameters_sha256": a.digest({"weights": [1.0, 2.0], "biases": [0.1]}),
        "state": (0.2,),
        "qualified": True,
        "work": {"evaluations": 3},
    }
    assert full["weights"] == (1.0, 2.0)
