"""No learned comparisons: algebra, pure queries and synthetic admission custody."""

import json
import math

import learned_cycle_memory as experiment
import pytest


@pytest.mark.parametrize("seed", experiment.SEEDS)
def test_matched_small_random_three_parameter_founders(seed):
    assert experiment.initial(seed) == experiment.initial(seed)
    assert len(experiment.initial(seed)) == 3
    assert all(abs(v) <= 0.1 for v in experiment.initial(seed))
    for arm in experiment.ARMS:
        g = experiment.graph(arm)
        assert g.n_patches == 1 and len(g.edges) + g.n_patches == 3
    assert experiment.graph("cycle").edges[1] == ("state", 0, 0)
    assert experiment.graph("flat").edges[1] == ("input", 1, 0)
    assert experiment.graph("history").edges[1] == ("input", 2, 0)


def test_analytic_stationarity_quadratic_and_numerical_saddle():
    result = experiment.threshold()
    assert 1.19 < result["gain"] < 1.191
    assert abs(result["audit"]["gradient"]) < 1e-10
    assert abs(result["audit"]["hessian"]) < 2e-7
    assert result["teacher_implications"][0]["zero_error_gain"] < result["gain"]
    assert result["teacher_implications"][2]["zero_error_gain"] > result["gain"]
    for g in (0.5, 1.1552453, 1.25, 1.5):
        for x in (0.1, 0.3, 0.6, 0.9):
            t = g * x
            p, d = math.tanh(t), 1 - math.tanh(t) ** 2
            quadratic = 1.01 - g * (d + p / t) + g * g * p * d / t
            assert experiment.scalar(0, x, 0, g, 0)["gradient"] / x == pytest.approx(
                quadratic, abs=1e-14
            )
    for control in result["teacher_implications"]:
        w, g = control["zero_error_cue_weight"], control["zero_error_gain"]
        assert math.tanh(w + g * control["write_target"]) == pytest.approx(
            control["write_target"]
        )
        assert math.tanh(g * control["hold_target"]) == pytest.approx(
            control["hold_target"]
        )


def test_body_history_provenance_balanced_and_not_future_labels():
    assert len(experiment.tape()) == 64
    for rows in experiment.tape():
        assert len(rows) == 16
        for cue, blank in zip(rows[::2], rows[1::2], strict=True):
            assert cue["episode"] == blank["episode"]
            assert cue["tick"] == 0 and blank["tick"] == 1
            assert blank["cue"] == 0 and blank["body_bit"] == cue["cue"]
        assert sum(r["body_bit"] for r in rows) == 0
    assert (
        experiment.inputs("cycle", 0, 1)
        == experiment.inputs("cycle", 0, -1)
        == (0.0, 0.0)
    )
    assert (
        experiment.inputs("flat", 0, 1)
        == experiment.inputs("flat", 0, -1)
        == (0.0, 0.0)
    )
    assert experiment.inputs("history", 0, 1) == (0.0, 0.0, 1.0)
    assert experiment.inputs("history", 0, -1) == (0.0, 0.0, -1.0)


def test_gate_rejects_locked_attractor_and_teacher_only_outputs():
    records = [{"state": 0.0, "expected": 0.0, "scored": True}]
    records.extend(
        {"state": 0.6 * sign, "expected": 0.6 * sign, "scored": True}
        for sign in (-1, 1)
        for _ in range(269)
    )
    assert experiment.bit_gate(records, True)
    locked = [dict(r) for r in records]
    locked[-1]["state"] = -0.6  # Old sign persists after a positive overwrite.
    assert not experiment.bit_gate(locked, True)
    assert not experiment.bit_gate(records, False)
    assert not experiment.bit_gate(records[:1], True)


def test_qualified_wrong_boundary_is_retained_as_task_failure():
    result = experiment.settle(
        experiment.graph("cycle"),
        (-1.0, 1.0),
        (1.0,),
        (2.0, 3.0),
        (0.0,),
        **experiment.CONFIG,
    )
    assert result["qualified"] and result["state"] == (1.0,)
    derivative = experiment.scalar(-1, 1, 2, 3, 0)["gradient"]
    assert abs(derivative) > experiment.CONFIG["tolerance"]
    assert experiment.projected_stationarity(1.0, derivative) == 0


def synthetic(kw, state, weights, biases, *, qualified=True):
    # A mock acceptance receipt, never an actual parameter-learning call.
    return {
        "state": tuple(kw["clamps"].values()),
        "weights": weights,
        "biases": biases,
        "predictions": state,
        "errors": state,
        "energy": 0.0,
        "stationarity": 0.0 if qualified else 1.0,
        "prediction_residual": 0.0,
        "qualified": qualified,
        "sweeps": 0,
        "reason": "synthetic",
        "energy_history": (0.0,),
        "work": {"edge_visits": 0},
    }


def test_zero_private_batch_state_and_free_chronological_queries(tmp_path, monkeypatch):
    root = tmp_path / "frozen"
    experiment.freeze(root)
    original = experiment.settle
    learned_states, free_states = [], []

    def mock_learning(g, values, state, weights, biases, **kw):
        if kw["learn"]:
            assert state == (0.0,) * 16
            learned_states.append(state)
            return synthetic(kw, state, weights, biases)
        assert not kw["clamps"]
        free_states.append(state)
        return original(g, values, state, weights, biases, **kw)

    monkeypatch.setattr(experiment, "settle", mock_learning)
    report = experiment.run_arm(root, 149, 0, "cycle")
    assert report["complete"] and report["queries"] == 539
    assert len(learned_states) == 64 and len(free_states) == 539
    assert free_states[0] == (0.0,)
    assert all(state[0] not in (0.9, -0.9, 0.6, -0.6) for state in free_states)
    assert report["initial_parameters"] == tuple(report["trained_parameters"])
    rows = [
        json.loads(line)
        for line in (root / "regime0-cycle-seed149" / "calls.jsonl")
        .read_text()
        .splitlines()
    ]
    free = [r for r in rows if r.get("learn") is False]
    assert all(not r["clamps"] for r in free)
    assert report["erasure_diagnostics"] and not report["bit_memory_gate"]


@pytest.mark.parametrize("outcome", ("refused", "interrupted"))
def test_custodian_never_commits_refused_or_interrupted_proposal(
    tmp_path, monkeypatch, outcome
):
    root = tmp_path / "frozen"
    experiment.freeze(root)

    def no_learning(g, values, state, weights, biases, **kw):
        if outcome == "interrupted":
            raise TimeoutError("synthetic interruption")
        return synthetic(kw, state, (3.0, 3.0), (2.0,), qualified=False)

    monkeypatch.setattr(experiment, "settle", no_learning)
    report = experiment.run_arm(root, 149, 0, "cycle")
    assert not report["complete"] and not report["bit_memory_gate"]
    assert report["accepted_admissions"] == 0
    saved = experiment.custody.read(
        root / "regime0-cycle-seed149" / "last-completed.json"
    )
    assert saved["weights"] + saved["biases"] == experiment.initial(149)
    assert saved["state"] == [0.0]
    assert report["unknown_work"] == (outcome == "interrupted")
