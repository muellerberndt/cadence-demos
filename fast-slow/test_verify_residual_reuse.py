"""Arithmetic, mutation and censor tests without any learning admissions."""

import copy
import math

import pytest
import residual_reuse as collector
import verify_residual_reuse as verifier


def query_record(model, row, kind="offset-observed"):
    observed, teacher = kind != "clean-free", kind == "teacher-diagnostic"
    targets = {"past": row["actual_x"]} if observed else None
    if teacher:
        targets["future"] = row["actual_y"]
    q = model.settle(row["inputs"], targets=targets)
    return {
        **q,
        "check": f"mixed128-{kind}",
        "row": row["id"],
        "observed": observed,
        "teacher_clamped": teacher,
        "model_sha256": collector.custody.digest(model.snapshot()),
        "past_absolute_error": abs(q["outputs"]["past"][0] - row["actual_x"][0]),
        "future_absolute_error": None
        if teacher
        else abs(q["outputs"]["future"][0] - row["actual_y"][0]),
        "delta": row["delta"],
        "offset_bin": "small"
        if abs(row["delta"]) < 0.06
        else "medium"
        if abs(row["delta"]) < 0.09
        else "large",
        "no_innovation_absolute_error": abs(
            math.tanh(row["inputs"]["v"][0]) - row["actual_y"][0]
        ),
    }


@pytest.mark.parametrize("layout", collector.LAYOUTS)
def test_actual_clamps_arithmetic_and_exact_pure_replay(layout):
    model = collector.brain(107, layout, "observer")
    row = collector.tape()["mixed_test"][0]
    queries = [query_record(model, row, kind) for kind in verifier.KINDS]
    for q in queries:
        verifier.check_query(q, row, model.graph.n_patches)
    before = model.snapshot()
    verifier.replay_queries(model, queries, {row["id"]: row})
    assert model.snapshot() == before


@pytest.mark.parametrize("mutation", ("error", "clamp", "prediction", "qualification"))
def test_mutated_forecast_rejected(mutation):
    model = collector.brain(107, "input_only", "observer")
    row = collector.tape()["mixed_test"][0]
    q = query_record(model, row)
    if mutation == "error":
        q["future_absolute_error"] = 0
    elif mutation == "clamp":
        q["state"] = (-0.9, q["state"][1])
    elif mutation == "prediction":
        q["errors"] = (0.99, q["errors"][1])
    else:
        q["qualified"] = False
    with pytest.raises(ValueError):
        verifier.check_query(q, row, 2)


def test_teacher_value_is_never_a_forecast_score():
    model = collector.brain(107, "input_only", "observer")
    row = collector.tape()["mixed_test"][0]
    q = query_record(model, row, "teacher-diagnostic")
    q["future_absolute_error"] = 0
    with pytest.raises(ValueError, match="teacher scored"):
        verifier.check_query(q, row, 2)


def test_exact_input_only_invariance_checked_on_all_paired_rows():
    model = collector.brain(107, "input_only", "observer")
    rows = collector.tape()["mixed_test"]
    queries = [
        query_record(model, row, kind)
        for kind in ("offset-observed", "teacher-diagnostic")
        for row in rows
    ]
    diagnostics = verifier.diagnostics_from_queries(queries, "input_only")
    assert len(diagnostics) == 1 and diagnostics[0]["matched_rows"] == 64
    assert diagnostics[0]["p_predictions_exactly_invariant"]
    assert diagnostics[0]["p_error_shift_rms"] == 0
    queries[-1]["model_sha256"] = "changed-parameters"
    with pytest.raises(ValueError, match="same-weight"):
        verifier.diagnostics_from_queries(queries, "input_only")


def test_comparison_keeps_failed_comparator_and_never_changes_endpoint():
    cases = [
        {
            "seed": s,
            "layout": l,
            "arm": a,
            "eligible": True,
            "groups": [
                {
                    "check": "mixed128-offset-observed",
                    "completed": 64,
                    "qualified": 64,
                    "qualified_only_mae": {
                        "future": 0.04 if a == "ordinary" else 0.002
                    },
                }
            ],
        }
        for s, l, a in verifier.jobs()
    ]
    assert all(c["criterion_met"] for c in verifier.comparisons(cases))
    failed = copy.deepcopy(cases)
    failed[0]["eligible"] = False
    comparisons = verifier.comparisons(failed)
    assert all(not c["eligible"] and not c["criterion_met"] for c in comparisons)
    assert all(c["mean_mae_reduction"] == pytest.approx(0.038) for c in comparisons)
    failed[0]["groups"] = []
    assert verifier.comparisons(failed)[0]["mean_mae_reduction"] is None


def test_missing_arm_is_preserved_not_promoted(tmp_path):
    founder = collector.brain(107, "input_only", "ordinary").snapshot()
    result = verifier.verify_arm(
        tmp_path, 107, "input_only", "ordinary", collector.tape(), founder, None, True
    )
    assert result["status"] == "missing" and not result["eligible"]


def test_interrupted_first_admission_remains_valid_censored_evidence(
    tmp_path, monkeypatch
):
    root = tmp_path / "frozen"
    collector.freeze(root)

    def stop(self, *args, **kwargs):
        raise TimeoutError("synthetic interruption, no learning")

    monkeypatch.setattr(collector.Brain, "observe_batch", stop)
    assert collector.run(root, 107, "input_only", "ordinary") == 1
    founder = collector.custody.read(root / "founders.json")["input_only"]["107"][
        "ordinary"
    ]
    result = verifier.verify_arm(
        root,
        107,
        "input_only",
        "ordinary",
        collector.tape(),
        founder,
        {"status": "returned", "code": 1},
        True,
    )
    assert result["status"] == "timeout" and not result["eligible"]
    assert result["accepted_updates"] == 0 and result["interrupted_work_unknown"]
