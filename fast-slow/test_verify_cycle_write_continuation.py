"""Continuation custody/censor mutations; no new parameter learning."""

import copy
import time

import pytest
import verify_cycle_write_continuation as verify


def test_no_restart_and_no_1536_endpoint_selection():
    plan = verify.schedule(verify.frozen.tape(), 1)
    assert len(plan) == len({r["identity"] for r in plan}) == 2102
    assert plan[0]["identity"] == "batch1025"
    assert sum(r["kind"] == "training" for r in plan) == 1024
    assert {r["checkpoint"] for r in plan} == {None, 1536, 2048}
    for checkpoint in verify.CHECKS:
        queries = [r for r in plan if r["checkpoint"] == checkpoint]
        assert len(queries) == 539 and queries[0]["reset"] == "zero"
        assert plan[plan.index(queries[0]) - 1]["identity"] == f"batch{checkpoint}"
    assert plan[-1]["identity"] == "check2048:full-reset-neutral:1"


def parent_fixture(tmp_path, monkeypatch):
    root, folder = tmp_path / "run", tmp_path / "run" / "parent"
    folder.mkdir(parents=True)
    atomic = verify.frozen.custody.atomic
    p = {"sources": verify.frozen.parent.sources(), "config": verify.CONFIG}
    atomic(folder / "protocol.json", p)
    protocol_pin = verify.sha(folder / "protocol.json")
    monkeypatch.setattr(verify, "PARENT_PROTOCOL_PIN", protocol_pin)
    cases = []
    for seed in verify.SEEDS:
        for regime in range(3):
            cp = {
                "parameters": [0.01 * regime, 0.001 * seed, 0.0],
                "state": [0.0],
                "admissions": 1024,
                "protocol_sha256": protocol_pin,
                "training_work": {"edge_visits": seed + regime},
            }
            atomic(folder / f"regime{regime}-seed{seed}.json", cp)
            cases.append(
                {
                    "seed": seed,
                    "regime": regime,
                    "complete": True,
                    "accepted_admissions": 1024,
                    "primary_pass": False,
                    "checks": [
                        {
                            "checkpoint": 1024,
                            "parameters": cp["parameters"],
                            "training_work": cp["training_work"],
                        }
                    ],
                }
            )
    receipt = {
        "valid": True,
        "full_training_and_query_replay": True,
        "collector_sha256": verify.prior.PIN,
        "verifier_sha256": verify.PRIOR_VERIFIER_PIN,
        "protocol_sha256": protocol_pin,
        "cases": cases,
        "conclusions": [
            {"regime": r, "all_five_complete": True, "all_five_primary_pass": False}
            for r in range(3)
        ],
    }
    atomic(folder / "verification.json", receipt)
    monkeypatch.setattr(
        verify, "PARENT_RECEIPT_PIN", verify.sha(folder / "verification.json")
    )
    protocol = {
        "parent": {
            "collector_sha256": verify.prior.PIN,
            "files": {p.name: verify.sha(p) for p in folder.iterdir()},
        }
    }
    return root, protocol


def test_copied_parent_requires_all_fifteen_verified_parameter_arrays(
    tmp_path, monkeypatch
):
    root, protocol = parent_fixture(tmp_path, monkeypatch)
    assert len(verify.parent_checkpoints(root, protocol)) == 15
    name = "regime2-seed197.json"
    path = root / "parent" / name
    cp = verify.read(path)
    cp["parameters"][0] += 0.01
    verify.frozen.custody.atomic(path, cp)
    protocol["parent"]["files"][name] = verify.sha(path)
    with pytest.raises(ValueError, match="verified learned parent parameters"):
        verify.parent_checkpoints(root, protocol)


def test_parent_receipt_cannot_be_replaced_to_erase_failure(tmp_path, monkeypatch):
    root, protocol = parent_fixture(tmp_path, monkeypatch)
    path = root / "parent" / "verification.json"
    receipt = verify.read(path)
    receipt["conclusions"][0]["all_five_primary_pass"] = True
    verify.frozen.custody.atomic(path, receipt)
    protocol["parent"]["files"][path.name] = verify.sha(path)
    with pytest.raises(ValueError, match="immutable failed1024 parent identity"):
        verify.parent_checkpoints(root, protocol)


def interrupted_fixture(tmp_path):
    root, folder = tmp_path / "run", tmp_path / "run" / "regime0-seed179"
    folder.mkdir(parents=True)
    (root / "parent").mkdir()
    atomic = verify.frozen.custody.atomic
    atomic(root / "protocol.json", {"synthetic": True})
    theta, tape = (0.95, 1.37, 0.0), verify.frozen.tape()
    parent_path = root / "parent" / "regime0-seed179.json"
    atomic(parent_path, {"parameters": theta, "admissions": 1024})
    op = verify.schedule(tape, 0)[0]
    atomic(
        folder / "current-call.json",
        {
            **verify.expected_intent(op, theta, 0.0, {}, 0),
            "status": "interrupted",
            "unknown_work": True,
        },
    )
    atomic(
        folder / "last-completed.json",
        {"parameters": theta, "state": [0.0], "admissions": 1024},
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
        "parent_checkpoint_sha256": verify.sha(parent_path),
        "journal": None,
        "checks": checks,
        "unknown_work": True,
        "accepted_admissions": 1024,
        "new_accepted_admissions": 0,
        "returned_calls": 0,
        "training_work": {},
        "inference_work": {},
        "attempts": {"training": 1},
        "refusals": {},
        "sources_unchanged": True,
        "seconds": 0.01,
    }
    atomic(folder / "result.json", report)
    return root, folder, tape, theta, report


def test_interruption_retains_parent_without_inventing_new_admissions(tmp_path):
    root, folder, tape, theta, report = interrupted_fixture(tmp_path)
    result = verify.verify_arm(root, 179, 0, tape, theta, report, time.monotonic() + 2)
    assert (
        result["accepted_admissions"] == 1024 and result["new_accepted_admissions"] == 0
    )
    assert result["replayed_training_calls"] == 0 and not result["primary_pass"]
    forged = copy.deepcopy(report)
    forged["new_accepted_admissions"] = 1024
    verify.frozen.custody.atomic(folder / "result.json", forged)
    with pytest.raises(ValueError, match="new versus inherited admissions"):
        verify.verify_arm(root, 179, 0, tape, theta, forged, time.monotonic() + 2)


def test_restarted_parameters_fail_parent_custody(tmp_path):
    root, folder, tape, theta, report = interrupted_fixture(tmp_path)
    current = verify.read(folder / "current-call.json")
    current["parameters_before"] = [0.01, 0.02, 0.03]
    verify.frozen.custody.atomic(folder / "current-call.json", current)
    with pytest.raises(ValueError, match="pending intent parameters_before"):
        verify.verify_arm(root, 179, 0, tape, theta, report, time.monotonic() + 2)
