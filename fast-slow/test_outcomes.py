import pytest

from outcomes import OutcomeLedger


def test_later_outcome_keeps_original_goal_and_inputs():
    ledger = OutcomeLedger("episode-a")
    ledger.observe("episode-a", 0, [0])
    inputs = {"features": [0.2], "goal": [0.4]}
    identity = ledger.forecast(
        goal="door-a",
        horizon=2,
        inputs=inputs,
        prediction=[0.3],
        model_sha256="frozen-model",
        qualified=True,
    )
    inputs["goal"][0] = -0.9
    assert ledger.observe("episode-a", 1, [0.1]) == []
    matched = ledger.observe("episode-a", 2, [0.8])[0]
    assert matched["id"] == identity
    assert matched["inputs"]["goal"] == [0.4]
    assert matched["actual"] == [0.8]
    assert matched["residual"] == [0.5]


def test_crossed_episode_and_missing_outcomes_cannot_be_teaching_rows():
    ledger = OutcomeLedger("a")
    ledger.observe("a", 0, [0])
    ledger.forecast(
        goal="exit",
        horizon=3,
        inputs={},
        prediction=[0.2],
        model_sha256="model",
        qualified=True,
    )
    with pytest.raises(ValueError):
        ledger.observe("b", 1, [1])
    with pytest.raises(ValueError):
        ledger.observe("a", 3, [1])
    assert ledger.end("episode terminated")[0]["status"] == "censored"
    assert "actual" not in ledger.records[0]
