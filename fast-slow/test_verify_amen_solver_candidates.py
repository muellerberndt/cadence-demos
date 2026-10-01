"""Adversarial qualification/custody checks without optimization or admission."""

import numpy as np
import pytest
import amen_solver_candidates as S
import verify_amen_solver_candidates as V
from test_amen_solver_candidates import fixture


def test_projected_residual_respects_active_bounds_and_free_mask():
    assert V.projected([1, -1, 0.2], [-4, 8, 9], 1, {2}) == 0
    assert V.projected([1, -1, 0.2], [0.1, -0.3, 9], 1, {2}) == pytest.approx(0.3)
    assert V.projected([0.0], [0.01], 1) == 0.01


def test_requalification_uses_original_anchor_and_rejects_changed_clamp():
    brain, rows = fixture()
    before = brain.snapshot()
    e = S.Energy(brain, rows)
    result = V.qualify(brain, rows, e.initial)
    native, _, stationarity = e.reference(e.initial)
    assert result["energy"] == native["energy"]
    assert result["stationarity"] == pytest.approx(stationarity, abs=1e-15)
    forged = e.initial.copy()
    forged[next(iter(e.fixed))] += 0.01
    with pytest.raises(ValueError, match="changed actual clamp"):
        V.qualify(brain, rows, forged)
    assert brain.snapshot() == before


def test_invalid_box_nonfinite_and_duplicate_inventory_cannot_pass():
    brain, rows = fixture()
    e = S.Energy(brain, rows)
    forged = e.initial.copy()
    forged[-1] = 4.1
    with pytest.raises(ValueError, match="parameter outside"):
        V.qualify(brain, rows, forged)
    forged[-1] = np.nan
    with pytest.raises(ValueError, match="nonfinite"):
        V.qualify(brain, rows, forged)
    with pytest.raises(ValueError, match="inventory"):
        V.inventory([{"method": "diagonal_spectral"}] * 2)
    with pytest.raises(ValueError, match="two candidate"):
        V.inventory([{"method": "diagonal_spectral"}])
