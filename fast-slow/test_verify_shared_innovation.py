"""Mutations of prediction, qualification, censorship and paired selection."""

import copy

import pytest
import shared_innovation as producer
import verify_shared_innovation as verifier


def actual_query(teacher=False):
    model = producer.brain(2, "observer")
    row = producer.body(0.3, -0.2, 0.08, "mixed-test:0")
    targets = {"past": row["actual_x"]}
    if teacher:
        targets["future"] = row["actual_y"]
    r = model.settle(row["inputs"], targets=targets)
    q = {
        k: r[k]
        for k in (
            "qualified",
            "reason",
            "state",
            "errors",
            "predictions",
            "stationarity",
            "work",
            "sweeps",
        )
    }
    q.update(
        check="mixed128-teacher-diagnostic" if teacher else "mixed128-offset-observed",
        row=row["id"],
        teacher_clamped=teacher,
        observed=True,
        past_absolute_error=abs(r["state"][1] - row["actual_x"][0]),
        future_absolute_error=None
        if teacher
        else abs(r["state"][2] - row["actual_y"][0]),
        delta=row["delta"],
        offset_bin="medium",
        no_innovation_absolute_error=abs(producer.math.tanh(-0.2) - row["actual_y"][0]),
    )
    return model, row, q


@pytest.mark.parametrize("teacher", [False, True])
def test_actual_same_weight_queries_replay_purely(teacher):
    model, row, q = actual_query(teacher)
    before = model.snapshot()
    verifier.check_query(q, row)
    work = verifier.replay_queries(model, [q], {row["id"]: row})
    assert work == q["work"] and model.snapshot() == before


def test_teacher_future_cannot_be_counted_as_a_prediction():
    _, row, q = actual_query(True)
    q["future_absolute_error"] = 0.0
    with pytest.raises(ValueError, match="teacher scored"):
        verifier.check_query(q, row)


def test_forged_settled_output_is_rejected_by_fresh_query():
    model, row, q = actual_query()
    q["state"] = list(q["state"])
    q["state"][2] += 0.01
    q["future_absolute_error"] = abs(q["state"][2] - row["actual_y"][0])
    verifier.check_query(q, row)
    with pytest.raises(ValueError, match="fresh query state"):
        verifier.replay_queries(model, [q], {row["id"]: row})


def test_unqualified_state_cannot_be_promoted():
    _, row, q = actual_query()
    q["stationarity"] = 0.5
    with pytest.raises(ValueError, match="qualification"):
        verifier.check_query(q, row)


@pytest.fixture
def interrupted(tmp_path, monkeypatch):
    root = tmp_path / "run"
    producer.freeze(root)

    def interrupted_admission(model, *args, **kwargs):
        model._state = (0.8,) * 3
        raise TimeoutError("fixture interruption before any training")

    monkeypatch.setattr(producer.Brain, "observe_batch", interrupted_admission)
    assert producer.run(root, 2, "narrow", "ordinary") == 1
    return root


def verify_interrupted(root):
    data = producer.custody.read(root / "data.json")["narrow"]
    founder = producer.custody.read(root / "founders.json")["2"]["ordinary"]
    return verifier.verify_arm(
        root,
        2,
        "narrow",
        "ordinary",
        data,
        founder,
        {"status": "returned", "code": 1},
        False,
    )


def test_interruption_preserves_founder_missing_groups_and_unknown_work(interrupted):
    result = verify_interrupted(interrupted)
    assert result["status"] == "timeout" and not result["eligible"]
    assert result["accepted_updates"] == result["returned_calls"] == 0
    assert result["interrupted_work_unknown"]
    assert result["checkpoints_reloaded"] == 1
    assert len(result["groups"]) == 9 and all(
        g["completed"] == 0 for g in result["groups"]
    )


@pytest.mark.parametrize("mutation", ["gate", "count", "complete"])
def test_report_promotion_after_censor_is_rejected(interrupted, mutation):
    path = interrupted / "narrow-ordinary-seed2/result.json"
    report = producer.custody.read(path)
    if mutation == "gate":
        report["groups"][0]["clean_gate"] = True
    elif mutation == "count":
        report["accepted_updates"] = 192
    else:
        report["status"] = "complete"
    producer.custody.atomic(path, report)
    with pytest.raises(ValueError):
        verify_interrupted(interrupted)


def successful_cases(reduction=0.01):
    return [
        {
            "seed": seed,
            "condition": "wide",
            "arm": arm,
            "eligible": True,
            "groups": [
                {
                    "check": "mixed128-offset-observed",
                    "completed": 64,
                    "qualified": 64,
                    "qualified_only_mae": {
                        "future": 0.02 if arm == "ordinary" else 0.02 - reduction
                    },
                }
            ],
        }
        for seed in verifier.SEEDS
        for arm in verifier.ARMS
    ]


@pytest.mark.parametrize(
    "mutation", ["ineligible", "missing_rows", "one_losing_pair", "too_small"]
)
def test_advantage_requires_every_pair_and_predeclared_effect_size(mutation):
    cases = successful_cases()
    assert verifier.comparison(cases, "wide")["predeclared_accuracy_criterion_met"]
    changed = copy.deepcopy(cases)
    if mutation == "ineligible":
        changed[0]["eligible"] = False
    elif mutation == "missing_rows":
        changed[0]["eligible"] = False
        changed[0]["groups"][0]["completed"] = 63
    elif mutation == "one_losing_pair":
        changed[1]["groups"][0]["qualified_only_mae"]["future"] = 0.03
    else:
        changed = successful_cases(reduction=0.001)
    comparison = verifier.comparison(changed, "wide")
    assert not comparison["predeclared_accuracy_criterion_met"]
    assert len(comparison["pairs"]) == 5


def test_development_primary_endpoint_cannot_be_relabelled_as_confirmation():
    original = {"seeds": list(verifier.SEEDS)}
    assert verifier.design(original)["primary_checkpoint"] == 128
    original["primary_checkpoint"] = 32
    with pytest.raises(ValueError, match="original endpoint cannot be edited"):
        verifier.design(original)


def test_confirmation_mode_requires_exact_wrapper_new_seeds_and_all_clean_checks():
    protocol = {
        "schema": "shared-innovation-confirmation/1",
        "confirmation_source_sha256": verifier.CONFIRMATION_PIN,
        "seeds": [61, 67, 71, 73, 79],
        "data_seed": 20261006,
        "primary_condition": "narrow",
        "primary_checkpoint": 32,
        "required_clean_checks": [0, 32, 128],
    }
    assert verifier.design(protocol)["global_veto"]
    changed = copy.deepcopy(protocol)
    changed["required_clean_checks"] = [0, 128]
    with pytest.raises(ValueError, match="clean gates"):
        verifier.design(changed)
    changed = copy.deepcopy(protocol)
    changed["seeds"] = list(verifier.SEEDS)
    with pytest.raises(ValueError, match="seed grid"):
        verifier.design(changed)


def test_confirmation_secondary_failure_vetoes_otherwise_successful_primary():
    wide = successful_cases()
    narrow = copy.deepcopy(wide)
    for case in narrow:
        case["condition"] = "narrow"
    cases = narrow + wide
    for case in cases:
        case["groups"][0]["check"] = "mixed32-offset-observed"
    assert verifier.comparison(cases, "narrow", checkpoint=32, global_veto=True)[
        "predeclared_accuracy_criterion_met"
    ]
    cases[-1]["eligible"] = False
    result = verifier.comparison(cases, "narrow", checkpoint=32, global_veto=True)
    assert (
        result["all_five_pairs_eligible"] and not result["global_twenty_arms_eligible"]
    )
    assert (
        not result["predeclared_accuracy_criterion_met"]
        and result["verdict"] == "inconclusive"
    )
    secondary = verifier.comparison(
        cases, "wide", checkpoint=32, global_veto=True, primary=False
    )
    assert secondary["predeclared_accuracy_criterion_met"] is None
    assert secondary["verdict"] == "descriptive_secondary"
