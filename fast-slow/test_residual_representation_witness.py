import math
import random

import pytest
import residual_representation_witness as witness


def test_functional_annihilates_arbitrary_ordinary_heads():
    certificate = witness.certificate()
    rng = random.Random(239)
    for _ in range(100):
        a, b, c, d = (rng.uniform(-4, 4) for _ in range(4))
        values = [
            a * row["v"] + b * row["x"] + c * row["u"] + d
            for row in certificate["rows"]
        ]
        assert (
            abs(sum(x * y for x, y in zip(certificate["coefficients"], values))) < 1e-13
        )


def test_inverse_derivative_bound_covers_entire_output_error_band():
    certificate = witness.certificate()
    epsilon = certificate["effective_output_error_allowance"]
    derivative_bound = certificate["inverse_derivative_bound"]
    for row in certificate["rows"]:
        expected = math.atanh((1 + witness.ALPHA) * row["y"])
        for i in range(101):
            error = epsilon * (2 * i / 100 - 1)
            actual = math.atanh((1 + witness.ALPHA) * (row["y"] + error))
            assert abs(actual - expected) <= derivative_bound * abs(error) + 1e-15


def test_larger_tolerance_cannot_silently_claim_same_obstruction(monkeypatch):
    monkeypatch.setattr(witness, "EPSILON", 0.04)
    with pytest.raises(AssertionError):
        witness.certificate()


def test_constructive_observer_qualifies_without_parameter_admission():
    certificate = witness.certificate()
    observer, ordinary = witness.public_graph(True), witness.public_graph(False)
    assert observer.edges[:-1] == ordinary.edges[:-1]
    for row in certificate["rows"]:
        result = witness.engineered_query(
            observer, certificate["observer_error_weight"], row
        )
        assert result["qualified"]
        assert result["state"][0] == row["x"]
        assert result["state"][1] == pytest.approx(row["y"], abs=1e-12)
        assert result["errors"][0] == pytest.approx(row["delta"], abs=1e-15)
