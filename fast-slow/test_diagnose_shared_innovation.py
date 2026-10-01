import copy
import math

import pytest
from diagnose_shared_innovation import decomposition, equation_checks


def fixture():
    row = {
        "inputs": {"u": [0.0], "v": [0.0]},
        "actual_x": [0.1],
        "actual_y": [math.tanh(0.1)],
        "delta": 0.1,
    }

    def result(states, predictions):
        return {
            "qualified": True,
            "state": states,
            "predictions": predictions,
            "errors": [s - p for s, p in zip(states, predictions, strict=True)],
        }

    prior = result([0.03, 0.02, 0.01], [0.025, 0.019, 0.009])
    observed = result([0.09, 0.1, 0.08], [0.025, 0.075, 0.079])
    teacher = result([0.10, 0.1, math.tanh(0.1)], [0.025, 0.08, 0.099])
    return row, prior, observed, teacher


def test_counterfactual_innovation_is_distinct_from_posterior_residual():
    measurements = decomposition(*fixture())
    assert measurements["counterfactual_prior_innovation"] == pytest.approx(0.08)
    assert measurements["posterior_p_residual"] == pytest.approx(0.025)
    assert measurements["posterior_prediction_minus_prior_forecast"] == pytest.approx(
        0.055
    )
    assert measurements["teacher_p_residual_change"] == pytest.approx(-0.005)
    assert measurements["prior_baseline_error"] == pytest.approx(0.02)


def test_wrong_body_innovation_rejected():
    row, *_ = fixture()
    row["delta"] = 0.2
    with pytest.raises(AssertionError):
        equation_checks(row)


def test_wrong_returned_error_rejected():
    rows = list(fixture())
    rows[2] = copy.deepcopy(rows[2])
    rows[2]["errors"][1] = 0.1
    with pytest.raises(AssertionError):
        decomposition(*rows)


def test_unqualified_query_cannot_enter_diagnostic():
    rows = list(fixture())
    rows[1]["qualified"] = False
    with pytest.raises(AssertionError):
        decomposition(*rows)


def test_teacher_future_must_be_actual_witness():
    rows = list(fixture())
    rows[3]["state"][2] += 0.03
    rows[3]["errors"][2] += 0.03
    with pytest.raises(AssertionError):
        decomposition(*rows)
