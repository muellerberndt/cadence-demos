"""Ownership, boundary and construction tests; no comparative training."""

import copy
import json

import delayed_bandit as experiment
import pytest


@pytest.mark.parametrize("seed", experiment.SEEDS)
def test_public_pair_has_exact_same_fourteen_initial_coefficients(seed):
    models = experiment.founders(seed)
    a, b = (experiment.Brain.from_snapshot(models[arm]) for arm in experiment.ARMS)
    assert a.weights == b.weights and a.biases == b.biases
    assert len(a.weights) + len(a.biases) == 14
    assert a.graph.n_patches == b.graph.n_patches == 4


def issued(ledger):
    return ledger.issue(
        inputs={"u": [0.2], "v": [-0.1]},
        actual_x=0.15,
        forecasts=[-0.2, 0.1],
        model_id="original-model",
        event_id=0,
        tick=10,
        row="actual-body-row",
    )


@pytest.mark.parametrize("delay", experiment.DELAYS)
def test_executed_action_owns_original_forecast_and_only_its_target(delay):
    ledger = experiment.Ledger()
    proposal = issued(ledger)
    assert proposal["proposed_action"] == 1
    proposal["original_forecasts"][0] = 0.99
    ledger.execute(1, 0, 10, delay)  # Body overrides the proposed action.
    if delay:
        with pytest.raises(ValueError, match="Premature"):
            ledger.outcome(decision_id=1, executed_action=0, reward=0.4, tick=10)
    receipt = ledger.outcome(
        decision_id=1, executed_action=0, reward=0.4, tick=10 + delay
    )
    assert receipt["original_forecasts"] == [-0.2, 0.1]
    assert receipt["original_surprise"] == pytest.approx(0.6)
    assert receipt["model_id"] == "original-model"
    assert experiment.witness(receipt) == (
        {"u": [0.2], "v": [-0.1]},
        {"past": [0.15], "q_minus": [0.4]},
    )
    for reward in (0.4, 0.5):
        with pytest.raises(ValueError):
            ledger.outcome(decision_id=1, executed_action=0, reward=reward, tick=14)
    next_proposal = issued(ledger)
    assert next_proposal["decision_id"] == 2
    with pytest.raises(ValueError):
        ledger.outcome(decision_id=1, executed_action=0, reward=0.4, tick=14)
    assert ledger.pending["decision_id"] == 2


def test_cancelled_unexecuted_changed_and_unknown_receipts_cannot_teach():
    ledger = experiment.Ledger()
    issued(ledger)
    with pytest.raises(ValueError):
        issued(ledger)
    with pytest.raises(ValueError):
        ledger.outcome(decision_id=1, executed_action=1, reward=0.4, tick=14)
    ledger.execute(1, 1, 10, 2)
    before = copy.deepcopy(ledger.pending)
    for update in (
        {"decision_id": True},
        {"decision_id": 2},
        {"executed_action": 0},
        {"executed_action": True},
        {"reward": float("nan")},
        {"reward": 2},
        {"tick": 11},
    ):
        with pytest.raises(ValueError):
            ledger.outcome(
                **{
                    "decision_id": 1,
                    "executed_action": 1,
                    "reward": 0.1,
                    "tick": 12,
                    **update,
                }
            )
        assert ledger.pending == before
    cancelled = ledger.cancel()
    assert cancelled["cancelled"]
    with pytest.raises(ValueError):
        ledger.outcome(decision_id=1, executed_action=1, reward=0.4, tick=14)


def test_future_fields_never_enter_forecast_and_only_selected_reward_is_clamped():
    row = experiment.tape()["mixed"][0]
    mutated = {**row, "eventual_reward": 0.95, "future_action": 1, "due_tick": 10**6}
    assert experiment.observation(row) == experiment.observation(mutated)
    inputs, actual_x = experiment.observation(row)
    model = experiment.brain(41, "observer")
    _, clamps = model._arguments(inputs, {"past": [actual_x]})
    assert set(clamps) == {1}
    assert model._arguments(inputs)[1] == {}
    for action in (0, 1):
        record = {
            "inputs": inputs,
            "actual_x": actual_x,
            "executed_action": action,
            "reward": experiment.terminal_reward(row, action),
            "delta": row["delta"],
        }
        _, clamps = model._arguments(*experiment.witness(record))
        assert set(clamps) == {1, action + 2}


def test_common_tape_is_balanced_disjoint_and_independent_of_model_or_delay():
    data = experiment.tape()
    assert data == experiment.tape()
    for phase in ("clean", "mixed"):
        assert len(data[phase]) == experiment.UPDATES[phase] * experiment.BATCH
        for offset in range(0, len(data[phase]), 2):
            a, b = data[phase][offset : offset + 2]
            assert (a["u"], a["v"], a["delta"]) == (b["u"], b["v"], b["delta"])
            assert (a["executed_action"], b["executed_action"]) == (0, 1)
    train = {(r["u"], r["v"]) for phase in ("clean", "mixed") for r in data[phase]}
    assert not train & {
        (r["u"], r["v"]) for phase in ("clean_test", "policy_test") for r in data[phase]
    }
    witnesses = []
    for delay in experiment.DELAYS:
        ledger = experiment.Ledger()
        issued(ledger)
        ledger.execute(1, 0, 10, delay)
        witnesses.append(
            experiment.witness(
                ledger.outcome(
                    decision_id=1, executed_action=0, reward=-0.3, tick=10 + delay
                )
            )
        )
    assert witnesses[0] == witnesses[1] == witnesses[2]


def test_pure_forecast_and_interrupted_admission_preserve_evidence(
    tmp_path, monkeypatch
):
    root = tmp_path / "frozen"
    experiment.freeze(root)

    def interrupted(self, examples, *, event_id, source):
        assert event_id == 0 and source == "witness"
        assert len(examples) == 16
        assert all(len(targets) == 2 and "past" in targets for _, targets in examples)
        raise TimeoutError("synthetic interruption; no learning")

    monkeypatch.setattr(experiment.Brain, "observe_batch", interrupted)
    assert experiment.run(root, 41, "ordinary", 4) == 1
    out = root / "ordinary-seed41-delay4"
    result = experiment.custody.read(out / "result.json")
    assert result["status"] == "timeout" and result["completed_updates"] == 0
    assert result["admission_counts"] == {
        "started": 1,
        "returned": 0,
        "accepted": 0,
        "refused": 0,
        "interrupted_unknown_work": 1,
    }
    assert not result["primary_learning_gate"]
    assert result["issued_decisions"] == 16
    assert len(result["groups"]) == 4 and all(
        g["completed"] == 0 for g in result["groups"]
    )
    outcomes = [
        json.loads(line) for line in (out / "outcomes.jsonl").read_text().splitlines()
    ]
    assert len(outcomes) == 16
    assert all(r["outcome_tick"] - r["executed_tick"] == 4 for r in outcomes)
    current = experiment.custody.read(out / "current-call.json")
    assert current["status"] == "interrupted" and current["unknown_work"]
    assert current["before_sha256"] == current["restored_sha256"]
    saved = experiment.custody.read(out / "last-completed.json")
    assert experiment.Brain.from_snapshot(saved).snapshot() == saved
    assert saved == experiment.custody.read(root / "founders.json")["41"]["ordinary"]
