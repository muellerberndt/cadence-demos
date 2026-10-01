"""Independent schedule, pure-query mutation and interrupted-custody tests."""

import copy
import math
import time

import pytest
import verify_cycle_write_confirmation as verify


def test_all_checkpoints_keep_same_trajectory_and_independent_free_resets():
    tape = verify.frozen.tape()
    plan = verify.schedule(tape, 2)
    assert len(plan) == len({r["identity"] for r in plan}) == 2641
    assert sum(r["kind"] == "training" for r in plan) == 1024
    for checkpoint in verify.CHECKS:
        queries = [r for r in plan if r["checkpoint"] == checkpoint]
        assert len(queries) == 539 and queries[0]["reset"] == "zero"
        assert sum(r["reset"] is not None for r in queries) == 13
        assert sum(not r["scored"] for r in queries) == 2
        first = plan.index(queries[0])
        assert plan[first - 1]["identity"] == f"batch{checkpoint}"
        assert not any(r.get("clamps") for r in queries)


def test_private_teacher_rows_never_initialize_native_memory():
    op = verify.schedule(verify.frozen.tape(), 2)[0]
    intent = verify.expected_intent(op, (0.01, 0.02, 0.03), 0.9999, {}, 2)
    assert intent["initial_state"] == (0.0,) * 16
    assert {abs(v) for v in intent["clamps"].values()} == {0.9999, 0.8}
    query = verify.query_plan(0.9999, 0.8)[0]
    query["checkpoint"] = 64
    intent = verify.expected_intent(query, (0.01, 0.02, 0.03), 0.9999, {}, 2)
    assert intent["initial_state"] == (0.0,) and intent["clamps"] == {}
    assert intent["inputs"] == (0.0, 0.0)


def receipt(intent):
    theta = intent["parameters_before"]
    r = verify.independent.settle(
        verify.independent.graph("cycle"),
        intent["inputs"],
        intent["initial_state"],
        theta[:2],
        theta[2:],
        **verify.CONFIG,
    )
    return {
        **intent,
        "status": "returned",
        "seconds": 0.01,
        "result": {k: v for k, v in r.items() if k != "energy_history"},
        "energy_history_sha256": verify.independent.digest(r["energy_history"]),
        "energy_history_length": len(r["energy_history"]),
    }


def test_pure_replay_rejects_future_clamps_teacher_initialization_and_false_work():
    intent = {
        "identity": "check64:overwrite:1",
        "checkpoint": 64,
        "learn": False,
        "inputs": (-1.0, 1.0),
        "initial_state": (1.0,),
        "parameters_before": (2.0, 3.0, 0.0),
        "clamps": {},
    }
    record = receipt(intent)
    r, gap = verify.replay_record(record, intent)
    assert r["qualified"] and r["state"] == (1.0,) and gap < 2e-13
    for field, value in (("clamps", {"0": -0.9999}), ("initial_state", [-0.9999])):
        mutated = {**record, field: value}
        with pytest.raises(ValueError, match="causal intent"):
            verify.replay_record(mutated, intent)
    mutated = copy.deepcopy(record)
    mutated["result"]["work"]["edge_visits"] += 1
    with pytest.raises(ValueError, match="numerical replay"):
        verify.replay_record(mutated, intent)


def test_all_five_and_all_fifteen_are_required_for_primary():
    cases = [
        {"seed": seed, "regime": regime, "complete": True, "primary_pass": True}
        for seed in verify.SEEDS
        for regime in range(3)
    ]
    assert all(c["all_five_primary_pass"] for c in verify.conclusions(cases))
    cases[0].update(complete=False, primary_pass=False)
    assert not verify.conclusions(cases)[0]["all_five_primary_pass"]
    with pytest.raises(ValueError, match="all15"):
        verify.conclusions(cases[1:])
    cases[-1] = cases[0]
    with pytest.raises(ValueError, match="all15"):
        verify.conclusions(cases)


def test_qualified_locked_overwrite_never_passes_memory_gate():
    rows = [
        {
            "identity": op["identity"],
            "expected": op["target"],
            "scored": op["scored"],
            "qualified": True,
            "state": math.copysign(0.3, op["target"]) if op["target"] else 0.0,
        }
        for op in verify.query_plan(0.9999, 0.8)
    ]
    assert verify.independent.bit_gate(rows, True)
    next(r for r in rows if r["identity"] == "overwrite:1")["state"] = 1.0
    assert not verify.independent.bit_gate(rows, True)
    assert not verify.independent.bit_gate(rows[:-1], True)


def interrupted_fixture(tmp_path):
    root = tmp_path / "run"
    folder = root / "regime0-seed179"
    folder.mkdir(parents=True)
    atomic = verify.frozen.custody.atomic
    atomic(root / "protocol.json", {"test": True})
    founder, tape = (0.01, 0.02, 0.03), verify.frozen.tape()
    op = verify.schedule(tape, 0)[0]
    current = {
        **verify.expected_intent(op, founder, 0.0, {}, 0),
        "status": "interrupted",
        "unknown_work": True,
    }
    atomic(folder / "current-call.json", current)
    atomic(
        folder / "last-completed.json",
        {"parameters": founder, "state": [0.0], "admissions": 0},
    )
    checks = [
        {
            "checkpoint": n,
            "status": "not_started",
            "queries": 0,
            "bit_memory_gate": False,
        }
        for n in verify.CHECKS
    ]
    atomic(folder / "checks.json", checks)
    report = {
        "seed": 179,
        "regime": 0,
        "status": "timeout",
        "complete": False,
        "primary_pass": False,
        "protocol_sha256": verify.sha(root / "protocol.json"),
        "journal": None,
        "checks": checks,
        "unknown_work": True,
        "accepted_admissions": 0,
        "returned_calls": 0,
        "training_work": {},
        "inference_work": {},
        "attempts": {"training": 1},
        "refusals": {},
        "sources_unchanged": True,
        "seconds": 0.02,
    }
    atomic(folder / "result.json", report)
    return root, folder, tape, founder, report


def test_interrupted_learning_has_no_commit_or_invented_work(tmp_path):
    root, folder, tape, founder, report = interrupted_fixture(tmp_path)
    result = verify.verify_arm(
        root, 179, 0, tape, founder, report, time.monotonic() + 2
    )
    assert not result["complete"] and result["unknown_work"]
    assert result["accepted_admissions"] == result["replayed_training_calls"] == 0
    verify.frozen.custody.atomic(
        folder / "last-completed.json",
        {"parameters": [3.0, 3.0, 2.0], "state": [0.0], "admissions": 0},
    )
    with pytest.raises(ValueError, match="final accepted parameters"):
        verify.verify_arm(root, 179, 0, tape, founder, report, time.monotonic() + 2)


def test_censor_cannot_be_promoted_or_hide_unknown_work(tmp_path):
    root, folder, tape, founder, report = interrupted_fixture(tmp_path)
    report["unknown_work"] = False
    verify.frozen.custody.atomic(folder / "result.json", report)
    with pytest.raises(ValueError, match="truthful call counts"):
        verify.verify_arm(root, 179, 0, tape, founder, report, time.monotonic() + 2)
