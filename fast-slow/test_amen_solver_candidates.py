"""Independent equations and custody checks; no application training/admission."""

from types import SimpleNamespace
import json

import numpy as np
import pytest
from cadence import Cortex

import amen_solver_candidates as S


def test_numpy_scalar_receipts_roundtrip_without_changing_solver_values(tmp_path):
    record = {
        "qualified": np.bool_(True),
        "count": np.int64(3),
        "energy": np.float64(1.25),
        "values": np.array([1.0, 2.0]),
        "nested": (np.bool_(False),),
    }
    S.write(tmp_path / "report.json", record)
    assert json.loads((tmp_path / "report.json").read_text()) == {
        "qualified": True,
        "count": 3,
        "energy": 1.25,
        "values": [1.0, 2.0],
        "nested": [False],
    }
    assert type(record["qualified"]) is np.bool_


def fixture():
    c = Cortex(seed=13, state_prior=0.01, parameter_prior=0.4)
    u = c.input("u", shape=2)
    hidden = c.column("hidden", patches=2, inputs=u)
    output = c.column("output", patches=1, inputs=(u, hidden))
    c.output("y", shape=1, reads=output)
    b = c.build()
    return b, [({"u": [0.3, -0.2]}, {"y": [0.4]}), ({"u": [-0.1, 0.5]}, {"y": [-0.2]})]


def test_analytic_gradient_adjoint_fd_and_public_qualification_at_four_points():
    brain, rows = fixture()
    before = brain.snapshot()
    e = S.Energy(brain, rows)
    result = S.checks(e, e.initial.copy())
    assert [r["point"] for r in result] == [
        "initial",
        "public_baseline",
        "seeded_interior",
        "active_bounds",
    ]
    assert max(r["gradient_max_difference"] for r in result) < 1e-12
    assert brain.snapshot() == before
    assert brain.inspect()["admissions"] == 0


def test_gn_diagonal_is_column_norms_and_clamps_have_zero_jacobian_columns():
    brain, rows = fixture()
    e = S.Energy(brain, rows)
    _f, _g, aux = e.evaluate(e.initial)
    diagonal = e.diagonal(aux)
    for k in range(len(e.initial)):
        v = np.eye(1, len(e.initial), k).ravel()
        actual = e.jv(v, aux)
        expected = 0 if k in e.fixed else diagonal[k]
        assert float(actual @ actual) == pytest.approx(expected, abs=1e-12)


def test_row_duplication_preserves_energy_parameter_gradient_and_per_row_residual():
    brain, rows = fixture()
    a, b = S.Energy(brain, rows), S.Energy(brain, rows * 3)
    fa, ga, _ = a.evaluate(a.initial)
    fb, gb, _ = b.evaluate(b.initial)
    assert fa == pytest.approx(fb, abs=1e-15)
    np.testing.assert_allclose(ga[a.B * a.N :], gb[b.B * b.N :], atol=1e-15)
    assert a.stationarity(a.initial, ga) == pytest.approx(
        b.stationarity(b.initial, gb), abs=1e-15
    )
    # Mean gradient alone would divide private-row qualification by batch size.
    assert np.max(np.abs(ga[: a.B * a.N])) * a.B == pytest.approx(
        np.max(np.abs(gb[: b.B * b.N])) * b.B
    )


def test_energy_has_one_parameter_anchor_and_full_state_prior():
    brain, rows = fixture()
    e = S.Energy(brain, rows)
    x = e.initial.copy()
    x[-1] += 0.2
    f, _, a = e.evaluate(x)
    z, w, bias, _, _, _, errors, _ = a
    expected = sum(v * v for v in errors.flat) / (2 * len(rows))
    expected += 0.01 * sum(v * v for v in z.flat) / (2 * len(rows))
    expected += (
        0.4
        * (
            sum((v - u) ** 2 for v, u in zip(w, brain.weights))
            + sum((v - u) ** 2 for v, u in zip(bias, brain.biases))
        )
        / 2
    )
    assert f == pytest.approx(expected, abs=1e-15)


@pytest.mark.parametrize("method", S.METHODS)
def test_tiny_candidate_qualifies_without_public_admission_and_keeps_true_clamps(
    tmp_path, method
):
    brain, rows = fixture()
    before = brain.snapshot()
    e = S.Energy(brain, rows)
    trace = []
    x, status = S.solve(e, method, tmp_path, trace)
    reference, _, stationarity = e.reference(x)
    assert status == "dense_stationary" and stationarity <= 1e-6
    assert all(x[k] == v for k, v in e.fixed.items())
    assert reference["energy"] < e.evaluate(e.initial)[0]
    assert all(b["energy"] <= a["energy"] + 1e-14 for a, b in zip(trace, trace[1:]))
    assert brain.snapshot() == before


def test_matrix_kernel_refuses_duplicate_and_residual_contacts():
    brain, rows = fixture()
    fake = SimpleNamespace(
        graph=SimpleNamespace(
            n_patches=brain.graph.n_patches,
            n_inputs=brain.graph.n_inputs,
            edges=brain.graph.edges + (brain.graph.edges[0],),
        ),
        weights=brain.weights + (brain.weights[0],),
        config=brain.config,
        _arguments=brain._arguments,
    )
    with pytest.raises(ValueError, match="parallel"):
        S.Energy(fake, rows)
    c = Cortex()
    u = c.input("u", shape=2)
    m = c.column("m", patches=1, inputs=u)
    h = c.observer("h", patches=1, inputs=m, observes=m)
    c.output("y", shape=1, reads=h)
    with pytest.raises(ValueError, match="ordinary"):
        S.Energy(c.build(), rows)


def test_frozen_artifact_mutation_rejected(tmp_path):
    artifact = tmp_path / "founder.json"
    artifact.write_text("{}")
    S.A.write(
        tmp_path / "protocol.json",
        {
            "artifacts": {str(artifact): S.A.sha(artifact)},
            "sources": {},
            "numpy": np.__version__,
            "methods": list(S.METHODS),
        },
    )
    S.bound(tmp_path, tmp_path)
    artifact.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="artifact drift"):
        S.bound(tmp_path, tmp_path)
