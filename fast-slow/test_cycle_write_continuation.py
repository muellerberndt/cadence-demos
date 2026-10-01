"""Causal continuation custody with synthetic admissions; no actual training."""

import json
import shutil

import cycle_write_continuation as experiment
import pytest
from test_learned_cycle_memory import synthetic


def parent_fixture(tmp_path):
    root = tmp_path / "parent"
    root.mkdir()
    c = experiment.custody
    c.atomic(root / "protocol.json", {"sources": experiment.parent.sources()})
    cases = []
    for seed in experiment.SEEDS:
        for regime in range(3):
            # Distinct, deliberately untrained synthetic parameter arrays.
            theta = [0.02 + regime * 0.01, 0.03, -0.01 + seed * 1e-6]
            checkpoint = {
                "parameters": theta,
                "state": [0.0],
                "admissions": 1024,
                "training_work": {"edge_visits": 123},
                "protocol_sha256": c.sha(root / "protocol.json"),
            }
            folder = root / f"regime{regime}-seed{seed}"
            folder.mkdir()
            c.atomic(folder / "checkpoint1024.json", checkpoint)
            cases.append(
                {
                    "seed": seed,
                    "regime": regime,
                    "complete": True,
                    "accepted_admissions": 1024,
                    "primary_pass": False,
                    "checks": [{"checkpoint": 1024, "parameters": theta}],
                }
            )
    c.atomic(
        root / "verification.json",
        {
            "valid": True,
            "full_training_and_query_replay": True,
            "collector_sha256": experiment.PARENT_PIN,
            "protocol_sha256": c.sha(root / "protocol.json"),
            "cases": cases,
        },
    )
    return root


def frozen(tmp_path):
    prior = parent_fixture(tmp_path)
    root = tmp_path / "continuation"
    experiment.freeze(root, prior)
    return root, prior


def test_self_contained_parent_custody_and_no_founder_restart(tmp_path):
    root, prior = frozen(tmp_path)
    protocol = experiment.validate(root)
    assert protocol["checks"] == [1536, 2048]
    assert protocol["starting_admissions"] == 1024
    assert protocol["primary_checkpoint"] == 2048
    assert len(protocol["parent"]["files"]) == 17
    before = experiment.custody.read(root / "parent" / "regime2-seed179.json")
    assert before["parameters"] != experiment.base.initial(179)
    shutil.rmtree(prior)
    assert experiment.validate(root) == protocol
    (root / "parent" / "regime2-seed179.json").write_text("{}")
    with pytest.raises(AssertionError):
        experiment.validate(root)


@pytest.mark.parametrize("mutation", ("array", "missing", "unverified", "count"))
def test_freeze_rejects_unverified_selected_or_changed_parents(tmp_path, mutation):
    prior = parent_fixture(tmp_path)
    path = prior / "verification.json"
    receipt = experiment.custody.read(path)
    if mutation == "array":
        receipt["cases"][0]["checks"][-1]["parameters"][0] += 0.01
    elif mutation == "missing":
        receipt["cases"].pop()
    elif mutation == "unverified":
        receipt["valid"] = False
    else:
        receipt["cases"][0]["accepted_admissions"] = 64
    experiment.custody.atomic(path, receipt)
    with pytest.raises(AssertionError):
        experiment.freeze(tmp_path / "new", prior)
    assert not (tmp_path / "new").exists()


def test_new_causal_tape_has_exact_1024_balanced_actual_witness_batches():
    tape = experiment.tape()
    assert len(tape) == 1024
    for event, rows in enumerate(tape, start=1025):
        assert len(rows) == 16 and sum(r["body_bit"] for r in rows) == 0
        for i, (cue, blank) in enumerate(zip(rows[::2], rows[1::2], strict=True)):
            assert cue["episode"] == blank["episode"] == f"{event}:{i}"
            assert cue["cue"] == cue["body_bit"] == blank["body_bit"]
            assert cue["tick"] == 0 and blank["tick"] == 1 and blank["cue"] == 0


def test_full_mock_continuation_preserves_parent_parameters_and_query_isolation(
    tmp_path, monkeypatch
):
    root, _ = frozen(tmp_path)
    theta = experiment.custody.read(root / "parent" / "regime2-seed179.json")[
        "parameters"
    ]
    original = experiment.base.settle
    learned, queries = [], []

    def mock(g, values, state, weights, biases, **kw):
        assert [*weights, *biases] == theta
        if kw["learn"]:
            assert state == (0.0,) * 16
            learned.append(state)
            return synthetic(kw, state, weights, biases)
        assert kw["clamps"] is None
        queries.append(state)
        return original(g, values, state, weights, biases, **kw)

    monkeypatch.setattr(experiment.base, "settle", mock)
    report = experiment.run_arm(root, 179, 2)
    assert report["complete"] and not report["primary_pass"]
    assert report["accepted_admissions"] == 2048
    assert report["new_accepted_admissions"] == 1024
    assert report["returned_calls"] == 2102
    assert report["attempts"] == {"training": 1024, "inference": 1078}
    assert report["refusals"] == {} and not report["unknown_work"]
    assert len(learned) == 1024 and len(queries) == 1078
    assert queries[0] == queries[539] == (0.0,)
    out = root / "regime2-seed179"
    calls = [
        json.loads(line) for line in (out / "calls.jsonl").read_text().splitlines()
    ]
    assert calls[0]["identity"] == "batch1025"
    assert [r["identity"] for r in calls if r["learn"]][-1] == "batch2048"
    for n in experiment.CHECKS:
        cp = experiment.custody.read(out / f"checkpoint{n}.json")
        assert (
            cp["parameters"] == theta and cp["admissions"] == n and cp["state"] == [0.0]
        )
        assert len(experiment.custody.read(out / f"queries{n}.json")) == 539
    assert report["parent_checkpoint_sha256"] == experiment.custody.sha(
        root / "parent" / "regime2-seed179.json"
    )
    arm_bytes = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    assert arm_bytes * 15 < 100_000_000


@pytest.mark.parametrize("outcome", ("refused", "interrupted"))
def test_failure_preserves_exact_parent_and_counts_only_new_attempt(
    tmp_path, monkeypatch, outcome
):
    root, _ = frozen(tmp_path)

    def fail(g, values, state, weights, biases, **kw):
        if outcome == "interrupted":
            raise TimeoutError("synthetic timeout")
        return synthetic(kw, state, (3.0, 3.0), (2.0,), qualified=False)

    monkeypatch.setattr(experiment.base, "settle", fail)
    report = experiment.run_arm(root, 179, 0)
    assert not report["complete"] and not report["primary_pass"]
    assert (
        report["accepted_admissions"] == 1024 and report["new_accepted_admissions"] == 0
    )
    assert report["attempts"] == {"training": 1}
    assert report["unknown_work"] == (outcome == "interrupted")
    out = root / "regime0-seed179"
    parent = experiment.custody.read(root / "parent" / "regime0-seed179.json")
    saved = experiment.custody.read(out / "last-completed.json")
    assert saved == {
        "parameters": parent["parameters"],
        "state": [0.0],
        "admissions": 1024,
    }
    assert all(c["status"] == "not_started" for c in report["checks"])


def test_partial_evaluation_retained_after_admission1536(tmp_path, monkeypatch):
    root, _ = frozen(tmp_path)
    original = experiment.base.settle
    count = 0

    def stop(g, values, state, weights, biases, **kw):
        nonlocal count
        if kw["learn"]:
            return synthetic(kw, state, weights, biases)
        count += 1
        if count == 3:
            raise TimeoutError("synthetic query stop")
        return original(g, values, state, weights, biases, **kw)

    monkeypatch.setattr(experiment.base, "settle", stop)
    report = experiment.run_arm(root, 179, 0)
    assert (
        report["accepted_admissions"] == 1536
        and report["new_accepted_admissions"] == 512
    )
    assert report["returned_calls"] == 514 and report["unknown_work"]
    assert not report["complete"] and not report["primary_pass"]
    assert report["checks"][0]["status"] == "started"
    assert report["checks"][0]["queries"] == 2
    assert report["checks"][1]["status"] == "not_started"
    assert (
        len(experiment.custody.read(root / "regime0-seed179" / "queries1536.json")) == 2
    )


def test_all_fifteen_unstarted_outcomes_remain(tmp_path, monkeypatch):
    root, _ = frozen(tmp_path)
    monkeypatch.setattr(experiment, "START_WINDOW", 0)
    monkeypatch.setattr(experiment, "run_arm", lambda *_: pytest.fail("must not start"))
    experiment.run(root)
    execution = experiment.custody.read(root / "execution.json")
    assert len(execution) == len({(r["seed"], r["regime"]) for r in execution}) == 15
    assert all(r["status"] == "not_started_deadline" for r in execution)
    assert all(
        not r["all_five_primary_pass"]
        for r in experiment.custody.read(root / "summary.json")["conclusions"]
    )
