"""No training: exercise boundaries, public wiring and interrupted-run custody."""

import copy
import json

import pytest
import shared_innovation as pilot


@pytest.mark.parametrize("seed", pilot.SEEDS)
def test_matched_public_sources_and_initial_coefficients(seed):
    pair = pilot.founders(seed)
    for arm, snapshot in pair.items():
        model = pilot.Brain.from_snapshot(snapshot)
        assert len(model.weights) + len(model.biases) == 9
        assert model.graph.n_patches == 3
        for kind, source, target in model.graph.edges:
            if kind != "input":
                assert source < target
        assert sum(kind == "residual" for kind, _, _ in model.graph.edges) == (
            arm == "observer"
        )


@pytest.mark.parametrize("condition", pilot.CONDITIONS)
def test_balanced_shared_training_and_independent_continuous_test(condition):
    data = pilot.tape(condition)
    assert data == pilot.tape(condition)
    assert len(data["clean"]) == 1024 and len(data["mixed"]) == 2048
    for a, b in zip(data["mixed"][::2], data["mixed"][1::2], strict=True):
        assert a["inputs"] == b["inputs"] and a["delta"] == -b["delta"]
    trained = {
        (r["inputs"]["u"][0], r["inputs"]["v"][0])
        for phase in ("clean", "mixed")
        for r in data[phase]
    }
    tested = {
        (r["inputs"]["u"][0], r["inputs"]["v"][0])
        for phase in ("clean_test", "mixed_test")
        for r in data[phase]
    }
    assert not trained & tested


def test_future_or_offset_mutation_cannot_change_forecast_boundary():
    row = pilot.body(0.2, -0.1, 0.08, "test")
    changed = copy.deepcopy(row)
    changed["actual_y"], changed["delta"] = [-0.9], 900.0
    assert pilot.query(row) == pilot.query(changed)
    assert pilot.query(row)[1] == {"past": row["actual_x"]}
    assert pilot.query(row, observed=False)[1] is None
    assert pilot.witness(row) != pilot.witness(changed)


@pytest.mark.parametrize("input_only", (False, True))
def test_same_weight_teacher_probe_is_pure_and_input_only_residual_invariant(
    input_only,
):
    model = pilot.brain(2, "observer", input_only=input_only)
    before = model.snapshot()
    row = pilot.body(0.3, 0.2, 0.08, "test")
    inputs, past = pilot.query(row)
    _, full = pilot.witness(row)
    free = model.settle(inputs, targets=past)
    teacher = model.settle(inputs, targets=full)
    assert free["qualified"] and teacher["qualified"]
    assert model.snapshot() == before
    if input_only:
        assert len(model.weights) + len(model.biases) == 7
        assert free["errors"][0] == teacher["errors"][0]
    else:
        assert free["errors"][1] != teacher["errors"][1]


def test_timeout_discards_interrupted_call_and_retains_source_valid_founder(
    tmp_path, monkeypatch
):
    root = tmp_path / "pilot"
    pilot.freeze(root)

    def interrupt(*_args, **kwargs):
        assert kwargs["event_id"] == 0 and type(kwargs["event_id"]) is int
        assert kwargs["source"] == "witness"
        raise TimeoutError("synthetic call interruption; no training")

    monkeypatch.setattr(pilot.Brain, "observe_batch", interrupt)
    assert pilot.run(root, 2, "narrow", "ordinary") == 1
    out = root / "narrow-ordinary-seed2"
    result = json.loads((out / "result.json").read_text())
    assert result["status"] == "timeout" and result["accepted_updates"] == 0
    assert len(result["groups"]) == 9
    assert all(group["completed"] == 0 for group in result["groups"])
    interrupted = json.loads((out / "current-call.json").read_text())
    assert interrupted["unknown_work"] and interrupted["status"] == "interrupted"
    assert interrupted["before_sha256"] == interrupted["restored_sha256"]
    snapshot = json.loads((out / "last-completed.json").read_text())
    assert pilot.Brain.from_snapshot(snapshot).snapshot() == snapshot
    assert snapshot == pilot.custody.read(root / "founders.json")["2"]["ordinary"]
    assert result["sources_unchanged"]
