"""Structural, causal and failure-custody tests; no learning admissions."""

import copy
import math

import pytest
import residual_reuse as experiment


@pytest.mark.parametrize("seed", experiment.SEEDS)
@pytest.mark.parametrize("layout", experiment.LAYOUTS)
def test_all_shared_and_replacement_initial_coefficients_match(seed, layout):
    snapshots = experiment.founders(seed, layout)
    a, b = (experiment.Brain.from_snapshot(snapshots[arm]) for arm in experiment.ARMS)
    assert a.weights == b.weights and a.biases == b.biases
    assert len(a.weights) + len(a.biases) == experiment.LAYOUTS[layout]
    assert a.graph.n_patches == (2 if layout == "input_only" else 3)
    p = a.graph.n_patches - 2
    expected = {("input", 0, p)}
    if layout == "coupled":
        expected.add(("state", 0, p))
    assert {edge for edge in b.graph.edges if edge[2] == p} == expected


def test_body_targets_are_external_and_tape_is_balanced_disjoint_bounded():
    data = experiment.tape()
    assert data == experiment.tape()
    assert {k: len(v) for k, v in data.items()} == {
        "clean": 1024,
        "mixed": 2048,
        "clean_test": 32,
        "mixed_test": 64,
    }
    for phase, rows in data.items():
        for row in rows:
            u, v = row["inputs"]["u"][0], row["inputs"]["v"][0]
            assert row["actual_x"][0] - math.tanh(u) == pytest.approx(row["delta"])
            assert math.atanh(row["actual_y"][0]) - v == pytest.approx(row["delta"])
            assert abs(row["actual_x"][0]) < 1
            assert abs(u) <= 1.2 and abs(v) <= 0.4
            assert (
                row["delta"] == 0
                if phase.startswith("clean")
                else 0.03 <= abs(row["delta"]) <= 0.12
            )
    for phase in ("mixed", "mixed_test"):
        for index in range(0, len(data[phase]), 2):
            a, b = data[phase][index : index + 2]
            assert a["inputs"] == b["inputs"] and a["delta"] == -b["delta"]
        for index in range(0, len(data[phase]), 16):
            assert sum(r["delta"] for r in data[phase][index : index + 16]) == 0
    training = {
        tuple(tuple(v) for v in r["inputs"].values())
        for phase in ("clean", "mixed")
        for r in data[phase]
    }
    heldout = {
        tuple(tuple(v) for v in r["inputs"].values())
        for phase in ("clean_test", "mixed_test")
        for r in data[phase]
    }
    assert not training & heldout


@pytest.mark.parametrize("layout", experiment.LAYOUTS)
@pytest.mark.parametrize("arm", experiment.ARMS)
def test_only_actual_p_crosses_observed_query_boundary(layout, arm):
    model = experiment.brain(107, layout, arm)
    row = experiment.tape()["mixed_test"][0]
    changed = copy.deepcopy(row)
    changed["actual_y"] = [-0.99]
    changed["delta"] = -999
    assert experiment.query(row) == experiment.query(changed)
    assert set(experiment.query(row)[0]) == {"u", "v"}
    p = model.graph.n_patches - 2
    assert set(model._arguments(*experiment.query(row))[1]) == {p}
    assert model._arguments(*experiment.query(row, observed=False))[1] == {}
    assert set(model._arguments(*experiment.witness(row))[1]) == {p, p + 1}


@pytest.mark.parametrize("arm", experiment.ARMS)
def test_input_only_residual_invariance_and_scalar_free_head_solution(arm):
    model = experiment.brain(107, "input_only", arm)
    row = experiment.tape()["mixed_test"][0]
    before = model.snapshot()
    free = model.settle(row["inputs"], targets={"past": row["actual_x"]})
    teacher = model.settle(
        row["inputs"], targets={"past": row["actual_x"], "future": row["actual_y"]}
    )
    assert free["qualified"] and teacher["qualified"]
    assert model.snapshot() == before
    assert free["predictions"][0] == teacher["predictions"][0]
    assert free["errors"][0] == teacher["errors"][0]
    # Once actual P is clamped, the remaining H objective is a scalar quadratic.
    assert free["state"][1] == pytest.approx(free["predictions"][1] / 1.01, abs=1.1e-6)


def test_freeze_pins_all_twenty_jobs_and_shared_data_without_training(tmp_path):
    root = tmp_path / "frozen"
    experiment.freeze(root)
    protocol = experiment.validate(root)
    assert len(protocol["jobs"]) == 20
    assert protocol["seeds"] == [107, 109, 113, 127, 131]
    assert protocol["data_seed"] == 20261008
    assert protocol["layouts"] == {"input_only": 6, "coupled": 9}
    assert protocol["sources"] == experiment.sources()
    assert len({tuple(job) for job in protocol["jobs"]}) == 20
    assert not (root / "execution.json").exists()
    with pytest.raises(FileExistsError):
        experiment.freeze(root)


def test_interrupted_admission_retains_founder_and_unknown_work(tmp_path, monkeypatch):
    root = tmp_path / "frozen"
    experiment.freeze(root)

    def interrupted(self, examples, *, event_id, source):
        assert len(examples) == 16 and event_id == 0 and source == "witness"
        assert all(set(targets) == {"past", "future"} for _, targets in examples)
        raise TimeoutError("Synthetic interruption; no admission")

    monkeypatch.setattr(experiment.Brain, "observe_batch", interrupted)
    assert experiment.run(root, 107, "input_only", "ordinary") == 1
    folder = root / "input_only-ordinary-seed107"
    result = experiment.custody.read(folder / "result.json")
    assert result["status"] == "timeout"
    assert result["accepted_updates"] == result["completed_queries"] == 0
    assert result["call_counts"]["started"] == 1
    assert result["call_counts"]["returned"] == 0
    assert result["call_counts"]["interrupted_unknown_work"] == 1
    assert result["attempted_training_presentations"] == 16
    assert result["admitted_training_presentations"] == 0
    assert all(group["completed"] == 0 for group in result["groups"])
    assert all(
        not group["clean_gate"]
        for group in result["groups"]
        if group["check"].endswith("clean-free")
    )
    saved = experiment.custody.read(folder / "last-completed.json")
    assert (
        saved
        == experiment.custody.read(root / "founders.json")["input_only"]["107"][
            "ordinary"
        ]
    )
    current = experiment.custody.read(folder / "current-call.json")
    assert (
        current["unknown_work"]
        and current["before_sha256"] == current["restored_sha256"]
    )


def test_campaign_requires_all_twenty_arms_and_uses_final_endpoint(tmp_path):
    root = tmp_path / "frozen"
    experiment.freeze(root)
    execution = []
    for seed, layout, arm in experiment.jobs():
        folder = root / f"{layout}-{arm}-seed{seed}"
        folder.mkdir()
        experiment.custody.atomic(
            folder / "result.json",
            {
                "seed": seed,
                "layout": layout,
                "arm": arm,
                "status": "complete",
                "eligible": True,
                "groups": [
                    {
                        "check": "mixed32-offset-observed",
                        "qualified": 64,
                        "completed": 64,
                        "qualified_only_mae": {
                            "future": 0.1 if arm == "ordinary" else 0.01
                        },
                    },
                    {
                        "check": "mixed128-offset-observed",
                        "qualified": 64,
                        "completed": 64,
                        "qualified_only_mae": {
                            "future": 0.03 if arm == "ordinary" else 0.029
                        },
                    },
                ],
            },
        )
        execution.append({"job": [seed, layout, arm], "status": "returned", "code": 0})
    experiment.custody.atomic(root / "execution.json", execution)
    result = experiment.campaign_summary(root)
    assert result["all_twenty_arms_eligible"]
    assert all(
        c["mean_mae_reduction"] == pytest.approx(0.001) for c in result["comparisons"]
    )
    assert not any(c["criterion_met"] for c in result["comparisons"])
    # A late censor is retained and vetoes either layout's primary comparison.
    path = root / "coupled-observer-seed131" / "result.json"
    censored = experiment.custody.read(path)
    censored.update(status="timeout", eligible=False)
    experiment.custody.atomic(path, censored)
    result = experiment.campaign_summary(root)
    assert len(result["outcomes"]) == 20
    assert not result["all_twenty_arms_eligible"]
    assert all(
        not c["eligible"] and not c["criterion_met"] for c in result["comparisons"]
    )
    execution.reverse()
    experiment.custody.atomic(root / "execution.json", execution)
    with pytest.raises(AssertionError, match="Execution identity"):
        experiment.campaign_summary(root)
