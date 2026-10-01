"""Algebra, pure activity and synthetic custody; no parameter-learning calls."""

import json
import math

import cycle_write_confirmation as experiment
import pytest
from test_learned_cycle_memory import synthetic


def frozen(tmp_path):
    historical = tmp_path / "historical"
    historical.mkdir()
    for name in ("protocol.json", "verification.json"):
        experiment.custody.atomic(historical / name, {"synthetic_test_reference": True})
    root = tmp_path / "new"
    experiment.freeze(root, historical)
    return root


def test_fresh_freeze_no_old_law_mutation(tmp_path):
    root = frozen(tmp_path)
    protocol = experiment.validate(root)
    assert experiment.base.CONFIG["tolerance"] == 1e-10
    assert protocol["config"]["tolerance"] == 1e-6
    assert protocol["checks"] == [64, 256, 1024]
    assert protocol["primary_checkpoint"] == 1024
    assert not set(experiment.SEEDS) & set(experiment.base.SEEDS)
    assert protocol["regimes"] == [[0.98, 0.8], [0.999, 0.8], [0.9999, 0.8]]
    assert protocol["limits"]["planned_arms"] == 15
    (root / "data.json").write_text("[]")
    with pytest.raises(AssertionError):
        experiment.validate(root)


def test_balanced_causal_body_witnesses_and_hidden_bit_not_input():
    batches = experiment.tape()
    assert len(batches) == 1024
    identities = set()
    for rows in batches:
        assert len(rows) == 16 and sum(r["body_bit"] for r in rows) == 0
        for write, hold in zip(rows[::2], rows[1::2], strict=True):
            assert write["episode"] == hold["episode"] not in identities
            identities.add(write["episode"])
            assert write["tick"] == 0 and hold["tick"] == 1
            assert write["cue"] == write["body_bit"] == hold["body_bit"]
            assert hold["cue"] == 0
    assert experiment.base.inputs("cycle", 0, 1) == experiment.base.inputs(
        "cycle", 0, -1
    )


@pytest.mark.parametrize("gain", (1.1, 1.373265360835137, 2.0, 3.0))
def test_sufficient_cue_bound_independent_gradient_direction(gain):
    for bias in (-0.04, 0.0, 0.04):
        weight = experiment.cue_bound(gain, bias) + 1e-4
        for sign in (-1, 1):
            for step in range(101):
                state = -sign * step / 100
                p = math.tanh(sign * weight + gain * state + bias)
                gradient = (state - p) * (1 - gain * (1 - p * p)) + 0.01 * state
                assert p * sign > 0 and gradient * sign < 0
    assert experiment.cue_bound(1) is None


def test_teacher_fit_is_not_switching_guarantee():
    gain = math.atanh(0.8) / 0.8
    weights = [math.atanh(w) - w * gain for w, _ in experiment.REGIMES]
    assert weights[0] < experiment.cue_bound(gain) < weights[1] < weights[2] < 4
    for (target, _), weight in zip(experiment.REGIMES, weights, strict=True):
        assert math.tanh(weight + gain * target) == pytest.approx(target)


def test_qualified_wrong_boundary_stays_task_failure():
    theta = (2.0, 3.0, 0.0)
    rows = []

    def call(values, state, parameters, **_):
        return experiment.base.settle(
            experiment.base.graph("cycle"),
            values,
            state,
            parameters[:2],
            parameters[2:],
            **experiment.CONFIG,
        )

    experiment.evaluate(call, theta, 0.999, 0.8, 64, rows)
    assert len(rows) == 539 and all(r["qualified"] for r in rows)
    overwrite = [r for r in rows if r["identity"].startswith("overwrite:")]
    assert any(r["state"] * r["expected"] < 0 for r in overwrite)
    assert not experiment.base.bit_gate(rows, True)


def test_zero_training_states_frozen_free_checks_and_projection(tmp_path, monkeypatch):
    root = frozen(tmp_path)
    original = experiment.base.settle
    training_states, query_states = [], []

    def mock_learning(g, values, state, weights, biases, **kw):
        if kw["learn"]:
            training_states.append(state)
            assert state == (0.0,) * 16
            return synthetic(kw, state, weights, biases)
        assert kw["clamps"] is None
        query_states.append(state)
        return original(g, values, state, weights, biases, **kw)

    monkeypatch.setattr(experiment.base, "settle", mock_learning)
    report = experiment.run_arm(root, 179, 0)
    assert report["complete"] and not report["primary_pass"]
    assert report["accepted_admissions"] == 1024
    assert report["returned_calls"] == 2641
    assert report["attempts"] == {"training": 1024, "inference": 1617}
    assert report["refusals"] == {} and not report["unknown_work"]
    assert len(training_states) == 1024 and len(query_states) == 1617
    out = root / "regime0-seed179"
    for n in experiment.CHECKS:
        checkpoint = experiment.custody.read(out / f"checkpoint{n}.json")
        assert checkpoint["parameters"] == experiment.base.initial(179)
        assert checkpoint["state"] == [0.0] and checkpoint["admissions"] == n
        assert len(experiment.custody.read(out / f"queries{n}.json")) == 539
    assert query_states[0] == query_states[539] == query_states[1078] == (0.0,)
    calls = [
        json.loads(line) for line in (out / "calls.jsonl").read_text().splitlines()
    ]
    assert len(calls) == 2641
    assert all(r["parameters_before"] == experiment.base.initial(179) for r in calls)
    arm_bytes = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    fixed_bytes = sum(p.stat().st_size for p in root.iterdir() if p.is_file())
    # Synthetic learning has no trajectory/outcome meaning; this checks receipt volume.
    assert arm_bytes * 15 + fixed_bytes < 100_000_000


@pytest.mark.parametrize("outcome", ("refused", "interrupted"))
def test_no_commit_on_failed_training_attempt(tmp_path, monkeypatch, outcome):
    root = frozen(tmp_path)

    def fail(g, values, state, weights, biases, **kw):
        if outcome == "interrupted":
            raise TimeoutError("synthetic interruption")
        return synthetic(kw, state, (3.0, 3.0), (2.0,), qualified=False)

    monkeypatch.setattr(experiment.base, "settle", fail)
    report = experiment.run_arm(root, 179, 0)
    assert not report["complete"] and not report["primary_pass"]
    assert report["accepted_admissions"] == 0
    assert report["attempts"] == {"training": 1}
    assert report["refusals"] == ({"training": 1} if outcome == "refused" else {})
    assert report["unknown_work"] == (outcome == "interrupted")
    last = experiment.custody.read(root / "regime0-seed179" / "last-completed.json")
    assert last["parameters"] == experiment.base.initial(179) and last["state"] == [0.0]
    assert all(check["status"] == "not_started" for check in report["checks"])


def test_partial_evaluation_keeps_rows_journal_and_checkpoint(tmp_path, monkeypatch):
    root = frozen(tmp_path)
    original = experiment.base.settle
    query_count = 0

    def interrupt(g, values, state, weights, biases, **kw):
        nonlocal query_count
        if kw["learn"]:
            return synthetic(kw, state, weights, biases)
        query_count += 1
        if query_count == 3:
            raise TimeoutError("interrupted free query")
        return original(g, values, state, weights, biases, **kw)

    monkeypatch.setattr(experiment.base, "settle", interrupt)
    report = experiment.run_arm(root, 179, 0)
    out = root / "regime0-seed179"
    assert report["status"] == "timeout" and report["unknown_work"]
    assert report["accepted_admissions"] == 64 and report["returned_calls"] == 66
    assert report["attempts"] == {"training": 64, "inference": 3}
    assert not report["complete"] and not report["primary_pass"]
    assert len(experiment.custody.read(out / "queries64.json")) == 2
    assert report["checks"] == [
        {"checkpoint": 64, "status": "started", "queries": 2, "bit_memory_gate": False},
        {
            "checkpoint": 256,
            "status": "not_started",
            "queries": 0,
            "bit_memory_gate": False,
        },
        {
            "checkpoint": 1024,
            "status": "not_started",
            "queries": 0,
            "bit_memory_gate": False,
        },
    ]
    assert len((out / "calls.jsonl").read_text().splitlines()) == 66
    assert experiment.custody.read(out / "current-call.json")["status"] == "interrupted"
    assert experiment.custody.read(out / "checkpoint64.json")["admissions"] == 64


def test_campaign_retains_all_fifteen_not_started(tmp_path, monkeypatch):
    root = frozen(tmp_path)
    monkeypatch.setattr(experiment, "START_WINDOW", 0)
    monkeypatch.setattr(experiment, "run_arm", lambda *_: pytest.fail("must not start"))
    experiment.run(root)
    execution = experiment.custody.read(root / "execution.json")
    assert len(execution) == 15
    assert {(r["seed"], r["regime"]) for r in execution} == {
        (s, r) for s in experiment.SEEDS for r in range(3)
    }
    assert all(r["status"] == "not_started_deadline" for r in execution)
    assert all(
        not r["all_five_primary_pass"]
        for r in experiment.custody.read(root / "summary.json")["conclusions"]
    )
