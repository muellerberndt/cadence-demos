"""Causal timing, matched capacity and custody checks for the small predictor."""

import copy
import json
import signal
import time
from collections import Counter

import pytest
import self_correction as experiment


def test_independent_body_arithmetic_and_first_informed_query():
    tape = experiment.make_tape()
    assert len(tape["train"]) == 512 and len(tape["test"]) == 128
    for phase, rows in tape.items():
        for record in rows:
            old, executed = record["inputs"]["previous"]
            present, candidate = record["inputs"]["present"]
            history_gain = (present - 0.8 * old) / executed
            assert 0.25 <= abs(executed) <= 0.5
            assert 0.25 <= abs(candidate) <= 0.5
            assert present == pytest.approx(
                0.8 * old + record["audit"]["past_gain"] * executed
            )
            assert history_gain == pytest.approx(record["audit"]["past_gain"])
            actual = 0.8 * present + record["audit"]["future_gain"] * candidate
            assert record["past"] == [present, present - old]
            assert record["future"] == [actual, actual - present]
            causal = 0.8 * present + history_gain * candidate
            if record["audit"]["switch"]:
                assert abs(actual - causal) == pytest.approx(0.6 * abs(candidate))
            else:
                assert causal == pytest.approx(actual, abs=1e-15)
        if phase != "gate":
            for previous, following in zip(rows, rows[1:], strict=False):
                assert previous["future"][0] == following["inputs"]["present"][0]
                assert (
                    previous["audit"]["future_gain"] == following["audit"]["past_gain"]
                )
    assert [r["index"] for r in tape["test"] if r["audit"]["switch"]] == list(
        experiment.SWITCHES
    )
    for index in experiment.SWITCHES:
        assert tape["test"][index]["audit"]["causal_absolute_error"] >= 0.15 - 1e-14
        assert tape["test"][index + 1]["audit"]["causal_absolute_error"] < 1e-14


def test_unobserved_future_and_gain_do_not_enter_current_query():
    original = experiment.make_tape()["test"][23]
    forged = copy.deepcopy(original)
    forged["future"] = [-0.9, 0.9]
    forged["audit"] = {"future_gain": 700, "switch": False}
    assert experiment.known_query(original) == experiment.known_query(forged)
    inputs, targets = experiment.known_query(original)
    assert set(inputs) == {"previous", "present"}
    assert set(targets) == {"past"}
    assert set(experiment.witness(original)[1]) == {"past", "future"}


def test_gate_covers_both_rules_and_every_action_sign_pair_without_switches():
    gate = experiment.make_tape()["gate"]
    cells = Counter(
        (
            r["audit"]["future_gain"],
            r["inputs"]["previous"][1] > 0,
            r["inputs"]["present"][1] > 0,
        )
        for r in gate
    )
    assert len(gate) == 16 and len(cells) == 8 and set(cells.values()) == {2}
    assert not any(r["audit"]["switch"] for r in gate)


@pytest.mark.parametrize("seed", experiment.SEEDS)
def test_initial_capacity_and_every_shared_coefficient_are_exactly_matched(seed):
    left = experiment.make_brain(seed, "ordinary")
    right = experiment.make_brain(seed, "observer")
    match = experiment.matched_founders(left, right)
    assert match["shared_edges"] == 24
    assert len(left.weights) + len(left.biases) == 34
    assert len(right.weights) + len(right.biases) == 34
    assert sum(kind == "residual" for kind, _, _ in right.graph.edges) == 4
    assert not any(kind == "residual" for kind, _, _ in left.graph.edges)


@pytest.mark.parametrize("arm", experiment.ARMS)
def test_known_past_query_is_pure_and_future_head_is_unclamped(arm, monkeypatch):
    brain = experiment.make_brain(2, arm)
    record = experiment.make_tape()["test"][24]
    before = brain.snapshot()
    solve = brain._solve
    captured = []

    def checked(inputs, clamps, **options):
        captured.append(clamps)
        assert set(clamps) == {2, 3} and options["learn"] is False
        return solve(inputs, clamps, **options)

    monkeypatch.setattr(brain, "_solve", checked)
    inputs, targets = experiment.known_query(record)
    result = brain.settle(inputs, targets=targets)
    assert captured and result["qualified"]
    assert result["stationarity"] <= brain.config["tolerance"]
    assert result["outputs"]["past"] == tuple(record["past"])
    assert brain.snapshot() == before


def test_recovery_excludes_unavoidable_first_error_and_refusals():
    calls = []
    for index in range(128):
        calls.append(
            {
                "ordinal": len(calls),
                "kind": "forecast",
                "phase": "test",
                "index": index,
                "status": "returned",
                "seconds": 0,
                "position_error": 0.5 if index in experiment.SWITCHES else 0.01,
                "result": {"qualified": True, "work": {"evaluations": 1}},
            }
        )
    metrics = experiment.recovery_metrics(calls)
    for record in metrics:
        assert record["unavoidable_first_error"]["position_error"] == 0.5
        assert record["windows"]["1"]["position_mae"] == 0.01
        assert record["recovered"]["confirmed_at"] == record["switch"] + 3
    calls[24]["position_error"] = None
    calls[24]["result"]["qualified"] = False
    metrics = experiment.recovery_metrics(calls)
    assert metrics[0]["windows"]["1"]["complete"] is False
    assert metrics[0]["recovered"]["confirmed_at"] == 27
    assert experiment.work_summary(calls)["refusals"] == 1


def test_freeze_rejects_tape_and_founder_tampering(tmp_path):
    experiment.freeze(tmp_path, 2)
    original = (tmp_path / "tape.json").read_text()
    tape = json.loads(original)
    tape["test"][23]["future"][0] += 0.1
    experiment.atomic(tmp_path / "tape.json", tape)
    with pytest.raises(ValueError, match="tape differs"):
        experiment.freeze(tmp_path, 2)
    (tmp_path / "tape.json").write_text(original)
    (tmp_path / "founder-observer.json").write_text("{}")
    with pytest.raises(ValueError, match="founder differs"):
        experiment.freeze(tmp_path, 2)


@pytest.mark.parametrize(
    "error", [experiment.ArmTimeout("fixture cap"), RuntimeError("fixture error")]
)
def test_interrupted_call_restores_prior_state_and_preserves_last_checkpoint(
    tmp_path, monkeypatch, error
):
    protocol = experiment.freeze(tmp_path, 2)
    founder = (tmp_path / "founder-ordinary.json").read_text()

    def interrupted(brain, *args, **kwargs):
        brain._state = (0.8,) * 6
        raise error

    monkeypatch.setattr(experiment.Brain, "settle", interrupted)
    report = experiment.run_arm(
        tmp_path,
        "ordinary",
        protocol,
        experiment.make_tape(),
        {"train": [[0]], "gate": [], "test": []},
    )
    assert report["status"] in {"censored", "error"} and not report["gate"]["passed"]
    assert report["groups"]["all"]["unknown_work_calls"] == 1
    latest = experiment.read(tmp_path / "ordinary/latest.json")
    assert latest["brain"] == founder and latest["admissions"] == 0
    ledger = json.loads((tmp_path / "ordinary/calls.jsonl").read_text())
    assert ledger["before_brain_sha256"] == ledger["after_brain_sha256"]
    assert ledger["unknown_solver_work"] and "result" not in ledger


def test_real_timer_restores_prior_handler():
    before = signal.getsignal(signal.SIGALRM)
    with pytest.raises(experiment.ArmTimeout):
        experiment.limited_call(lambda: time.sleep(0.1), 0.005)
    assert signal.getsignal(signal.SIGALRM) == before
    assert signal.getitimer(signal.ITIMER_REAL) == (0, 0)


def test_real_witness_admissions_and_probe_precede_no_future_clamped_queries(tmp_path):
    protocol = experiment.freeze(tmp_path, 2)
    report = experiment.run_arm(
        tmp_path,
        "ordinary",
        protocol,
        experiment.make_tape(),
        {"train": [[0]], "gate": [], "test": [23, 24]},
    )
    assert report["status"] == "complete"
    calls = [
        json.loads(line)
        for line in (tmp_path / "ordinary/calls.jsonl").read_text().splitlines()
    ]
    assert [(c["kind"], c["phase"], c["index"]) for c in calls] == [
        ("forecast", "train", 0),
        ("admission", "train", 0),
        ("forecast", "test", 23),
        ("forecast", "probe", 24),
        ("admission", "test", 23),
        ("forecast", "test", 24),
        ("admission", "test", 24),
    ]
    for call in calls:
        assert call["result"]["qualified"]
        if call["kind"] == "admission":
            assert call["result"]["accepted"] and call["result"]["source"] == "witness"
        else:
            assert call["before_brain_sha256"] == call["after_brain_sha256"]
    assert report["groups"]["all"]["admissions"] == 3
    assert experiment.read(tmp_path / "ordinary/latest.json")["admissions"] == 3
