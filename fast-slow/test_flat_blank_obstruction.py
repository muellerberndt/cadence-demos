"""Independent arithmetic and pure queries; no parameter-learning calls."""

import math

import flat_blank_obstruction as proof
import learned_cycle_memory as core
import pytest


def test_qualified_band_cannot_separate_opposed_bits():
    receipt = proof.witness()
    assert receipt["qualified_band_width_upper_bound"] == pytest.approx(
        1.9801980198019803e-6
    )
    assert receipt["required_opposed_response_separation"] == 0.5
    assert receipt["opposed_qualified_bit_responses_impossible"]
    assert not receipt["training_performed"]
    # The inequality must not be asserted when a deliberately loose gate permits it.
    assert not proof.witness(tolerance=0.5)[
        "opposed_qualified_bit_responses_impossible"
    ]


def test_clipping_cannot_hide_a_qualified_alternative():
    for alpha in (0.01, 0.5, 2, 10):
        for p in (-1, -0.9, 0, 0.9, 1):
            for i in range(201):
                x = -1 + i / 100
                gradient = (1 + alpha) * x - p
                unprojected = x - gradient
                residual = proof.projected(x, gradient)
                if abs(unprojected) > 1:
                    assert residual > 1
                else:
                    assert residual == pytest.approx(
                        (1 + alpha) * abs(x - p / (1 + alpha)), abs=3e-15
                    )


@pytest.mark.parametrize("bias", (-4.0, -1.0, 0.0, 1.0, 4.0))
def test_pure_flat_blank_recall_is_independent_of_native_history(bias):
    expected = math.tanh(bias) / 1.01
    outputs = []
    for initial in (-1.0, 0.0, 1.0):
        r = core.settle(
            core.graph("flat"),
            (0.0, 0.0),
            (initial,),
            (0.7, -0.3),
            (bias,),
            **{**core.CONFIG, "tolerance": 1e-6},
        )
        assert r["qualified"]
        assert abs(r["state"][0] - expected) <= 1e-6 / 1.01 + 1e-14
        outputs.append(r["state"][0])
    assert max(outputs) - min(outputs) <= 2e-6 / 1.01 + 1e-14


@pytest.mark.parametrize(
    "args", ({"alpha": 0}, {"tolerance": 1}, {"bit_threshold": 0}, {"alpha": math.inf})
)
def test_invalid_mathematical_hypotheses_are_rejected(args):
    with pytest.raises(ValueError):
        proof.witness(**args)
