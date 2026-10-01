"""Verifier mutations; no learning or comparative campaign."""

import copy

import delayed_bandit as collector
import pytest
import verify_delayed_bandit as verifier


def episode(delay=2):
    row = collector.tape()["mixed"][0]
    model_id = "original-model"
    owner = collector.Ledger()
    inputs, actual_x = collector.observation(row)
    decision = owner.issue(
        inputs=inputs,
        actual_x=actual_x,
        forecasts=[-0.1, 0.2],
        model_id=model_id,
        event_id=0,
        tick=0,
        row=row["id"],
    )
    execution = owner.execute(1, 0, 0, delay)
    outcome = owner.outcome(
        decision_id=1,
        executed_action=0,
        reward=collector.terminal_reward(row, 0),
        tick=delay,
    )
    call = {"event_id": 0, "before_sha256": model_id, "check": "training"}
    return decision, execution, outcome, row, call


def test_actual_action_and_original_forecast_are_independently_checked():
    args = episode()
    verifier.check_outcome(*args, 0, 2)
    assert args[0]["proposed_action"] == 1
    assert args[1]["executed_action"] == 0
    assert set(verifier.witnesses([args[2]])[0][1]) == {"past", "q_minus"}


@pytest.mark.parametrize(
    "mutation", ["early", "action", "reward", "surprise", "context", "future", "model"]
)
def test_changed_or_premature_evidence_is_rejected(mutation):
    args = copy.deepcopy(episode())
    decision, execution, outcome, _, _ = args
    if mutation == "early":
        outcome["outcome_tick"] = 1
    elif mutation == "action":
        execution["executed_action"] = 1
    elif mutation == "reward":
        outcome["reward"] += 0.01
    elif mutation == "surprise":
        outcome["original_surprise"] += 0.01
    elif mutation == "context":
        decision["inputs"]["u"][0] += 0.01
    elif mutation == "future":
        decision["reward"] = outcome["reward"]
    else:
        decision["model_id"] = "later-model"
    with pytest.raises(ValueError):
        verifier.check_outcome(*args, 0, 2)


def test_delay_normalization_preserves_work_and_values():
    a, b = episode(0), episode(4)
    for i in range(3):
        assert verifier.fingerprint(a[i]) == verifier.fingerprint(b[i])
    b[0]["original_forecasts"][0] += 0.01
    assert verifier.fingerprint(a[0]) != verifier.fingerprint(b[0])
    assert verifier.fingerprint(
        {"work": {"edges": 1}, "seconds": 1}
    ) != verifier.fingerprint({"work": {"edges": 2}, "seconds": 9})


def test_complete_schedule_and_no_false_clean_gate():
    plan = verifier.call_plan(collector.tape())
    assert len(plan) == 3840
    assert sum(r["kind"] == "forecast" for r in plan) == 3456
    assert sum(r["kind"] == "admission" for r in plan) == 192
    assert sum(r["kind"] == "post-update-forecast" for r in plan) == 192
    assert verifier.groups([])[0]["clean_gate"] is False
    rows = [
        {
            "check": "clean-gate",
            "executed_action": i % 2,
            "past_absolute_error": 0.0,
            "prediction_absolute_error": 0.0,
            "reward": 0.0,
            "oracle_regret": 0.0,
        }
        for i in range(64)
    ]
    assert verifier.groups(rows)[0]["clean_gate"] is True
    assert verifier.groups(rows[:-1])[0]["clean_gate"] is False


def test_censor_cannot_promote_architecture_comparison():
    cases = []
    for seed in verifier.SEEDS:
        for arm in verifier.ARMS:
            cases.append(
                {
                    "seed": seed,
                    "arm": arm,
                    "delay": 0,
                    "eligible": True,
                    "groups": [
                        {
                            "check": "policy-final",
                            "completed": 128,
                            "means": {
                                "oracle_regret": 0.02 if arm == "ordinary" else 0.01
                            },
                        }
                    ],
                }
            )
    assert verifier.comparison(cases)["criterion_met"]
    cases[0]["eligible"] = False
    assert not verifier.comparison(cases)["criterion_met"]
    assert len(verifier.comparison(cases)["pairs"]) == 5


def test_interrupted_admission_custody_is_verifiable_without_learning(
    tmp_path, monkeypatch
):
    root = tmp_path / "run"
    collector.freeze(root)

    def stop(self, examples, *, event_id, source):
        raise TimeoutError("synthetic verifier fixture; no learning")

    monkeypatch.setattr(collector.Brain, "observe_batch", stop)
    assert collector.run(root, 41, "ordinary", 2) == 1
    founder = collector.custody.read(root / "founders.json")["41"]["ordinary"]
    result, _ = verifier.verify_arm(
        root,
        41,
        "ordinary",
        2,
        collector.tape(),
        founder,
        {"status": "returned", "code": 1},
        True,
    )
    assert result["status"] == "timeout" and result["unknown_inflight_work"]
    assert result["outcomes"] == 16 and result["admitted_batches"] == 0
    assert not result["eligible"]
    folder = root / "ordinary-seed41-delay2"
    report = collector.custody.read(folder / "result.json")
    report["primary_learning_gate"] = True
    collector.custody.atomic(folder / "result.json", report)
    with pytest.raises(ValueError, match="learning gate promotion"):
        verifier.verify_arm(
            root,
            41,
            "ordinary",
            2,
            collector.tape(),
            founder,
            {"status": "returned", "code": 1},
            False,
        )
