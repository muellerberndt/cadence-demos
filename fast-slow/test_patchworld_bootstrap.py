"""Public topology, unchanged native physics and causal body ownership tests."""

from pathlib import Path

import patchworld_bootstrap as p
import pytest

CORE = Path(__file__).resolve().parents[1] / "patch-world" / "core.js"


def test_flat_and_shallow_graphs_use_only_public_population_rule():
    for arm, size, edges in (("flat", 6, 54), ("composed", 8, 84), ("observer", 8, 96)):
        brain = p.make(arm, 211)
        assert brain.graph.n_patches == size and len(brain.graph.edges) == edges
        assert brain.inspect()["output_connected_patches"] == size
        if arm == "flat":
            assert all(edge[0] == "input" for edge in brain.graph.edges)
        assert brain.settle({"food": [0.0] * 9})["qualified"]


def test_curriculum_source_and_split_are_explicit():
    a, b, c = p.examples(96, 641), p.examples(24, 643), p.examples(48, 647)
    assert a != b and b != c
    for inputs, targets in [*a, *b, *c]:
        assert targets["action"] == p.teacher(inputs["food"])
        assert all(0 <= x <= 1 for x in inputs["food"])
        assert len(targets["action"]) == 6


def test_frozen_data_cannot_change_before_run(tmp_path):
    root = tmp_path / "run"
    p.freeze(root, CORE)
    p.bound_inputs(root, CORE)
    data = p.read(root / "data.json")
    data["train"][0][0]["food"][0] += 0.1
    p.write(root / "data.json", data)
    with pytest.raises(AssertionError, match="data pin"):
        p.bound_inputs(root, CORE)


def test_original_body_mass_and_deterministic_action_replay():
    pin = p.sha(CORE)
    brain = p.make("flat", 211)
    bodies = [p.Body(CORE, 1211, brain), p.Body(CORE, 1211, brain)]
    try:
        assert bodies[0].initial == bodies[1].initial
        for action in (0, 1, 2, 3, 4, 5):
            observations = [b.request({"op": "sense"}) for b in bodies]
            assert observations[0] == observations[1]
            assert len(observations[0]["food"]) == 9
            rows = [
                b.request(
                    {
                        "op": "step",
                        "tick": observations[0]["tick"],
                        "action": action,
                        "qualified": True,
                        "sweeps": 2,
                    }
                )
                for b in bodies
            ]
            assert rows[0] == rows[1]
            assert (
                rows[0]["before"]["mass"]
                == rows[0]["after"]["mass"]
                == bodies[0].initial["initial_mass"]
            )
            assert rows[0]["births"] == 0
    finally:
        for body in bodies:
            body.close()
    assert p.sha(CORE) == pin


def test_body_rejects_unqualified_motor_action_and_stale_tick():
    body = p.Body(CORE, 1211, p.make("flat", 211))
    try:
        observation = body.request({"op": "sense"})
        with pytest.raises(ValueError, match="Unqualified"):
            body.request(
                {
                    "op": "step",
                    "tick": observation["tick"],
                    "action": 4,
                    "qualified": False,
                    "sweeps": 0,
                }
            )
        with pytest.raises(ValueError, match="current observation"):
            body.request(
                {
                    "op": "step",
                    "tick": observation["tick"] - 1,
                    "action": 5,
                    "qualified": False,
                    "sweeps": 0,
                }
            )
        row = body.request(
            {
                "op": "step",
                "tick": observation["tick"],
                "action": 5,
                "qualified": False,
                "sweeps": 0,
            }
        )
        assert row["action"] == 5 and not row["qualified"]
    finally:
        body.close()
