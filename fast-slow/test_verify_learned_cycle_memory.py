"""Independent verifier mutations, scalar arithmetic and schedule; no training."""

import math

import pytest
import verify_learned_cycle_memory as verify
from cadence._repair import _evaluate_batch, settle


def test_schedule_keeps_every_free_step_and_only_declared_native_resets():
    for regime in range(3):
        plan = verify.schedule(verify.frozen.tape(), regime)
        assert len(plan) == len({r["identity"] for r in plan}) == 617
        assert sum(r["kind"] == "training" for r in plan) == 64
        assert sum(r["kind"] == "query" for r in plan) == 539
        assert sum(r["kind"] == "reset" for r in plan) == 14
        assert sum(r["kind"] == "query" and not r["scored"] for r in plan) == 2
        erasure = next(
            r for r in plan if r["identity"] == "erased-state-history-retained:-1"
        )
        assert erasure["cue"] == 0 and erasure["bit"] == 1
        reset = next(r for r in plan if r["identity"] == "full-reset-neutral:-1")
        assert reset["cue"] == reset["bit"] == reset["target"] == 0


def test_flat_and_native_cycle_have_no_external_memory_bit():
    for arm in ("flat", "cycle"):
        assert verify.inputs(arm, 0, -1) == verify.inputs(arm, 0, 1) == (0.0, 0.0)
    assert verify.inputs("history", 0, -1) != verify.inputs("history", 0, 1)


def queries():
    rows = []
    for op in verify.schedule(verify.frozen.tape(), 2):
        if op["kind"] == "query":
            rows.append(
                {
                    "identity": op["identity"],
                    "expected": op["target"],
                    "scored": op["scored"],
                    "state": math.copysign(0.3, op["target"]) if op["target"] else 0.0,
                }
            )
    return rows


def test_task_gate_rejects_qualified_lock_missing_data_and_cold_bias():
    good = queries()
    assert verify.bit_gate(good, True)
    assert not verify.bit_gate(good, False)
    assert not verify.bit_gate(good[:-1], True)
    locked = [dict(r) for r in good]
    next(r for r in locked if r["identity"] == "overwrite:1")["state"] = 1.0
    assert not verify.bit_gate(locked, True)
    biased = [dict(r) for r in good]
    biased[0]["state"] = 0.051
    assert not verify.bit_gate(biased, True)
    erased = [dict(r) for r in good]
    for r in erased:
        if not r["scored"]:
            r["state"] = -1.0
    assert verify.bit_gate(erased, True)


def test_projected_boundary_is_numerically_qualified_and_can_be_wrong():
    result = settle(
        verify.graph("cycle"), (-1.0, 1.0), (1.0,), (2.0, 3.0), (0.0,), **verify.CONFIG
    )
    assert result["qualified"] and result["state"] == (1.0,)
    assert (
        verify.scalar_audit("cycle", (-1.0, 1.0), (2.0, 3.0), (0.0,), result, False)
        < 2e-13
    )
    changed = {**result, "stationarity": 0.2}
    with pytest.raises(ValueError, match="projected derivative"):
        verify.scalar_audit("cycle", (-1.0, 1.0), (2.0, 3.0), (0.0,), changed, False)


@pytest.mark.parametrize("arm", verify.ARMS)
def test_parameter_anchor_count_checked_without_running_learning(arm):
    g = verify.graph(arm)
    rows = verify.frozen.tape()[0]
    values = tuple(v for r in rows for v in verify.inputs(arm, r["cue"], r["body_bit"]))
    states = tuple(
        r["body_bit"] * (0.98 if r["phase"] == "write" else 0.8) for r in rows
    )
    old_w, old_b = (0.03, -0.07), (0.02,)
    weights, biases = (0.2, 0.4), (0.05,)
    raw = _evaluate_batch(
        g, values, states, weights, biases, 0.01, old_w, old_b, 0.1, batch_size=16
    )
    result = {
        **raw,
        "state": states,
        "weights": weights,
        "biases": biases,
        "stationarity": max(
            abs(x) for x in (*raw["gradient_weights"], *raw["gradient_biases"])
        ),
    }
    assert verify.scalar_audit(arm, values, old_w, old_b, result, True) < 2e-13
    with pytest.raises(ValueError, match="energy"):
        verify.scalar_audit(
            arm,
            values,
            old_w,
            old_b,
            {**result, "energy": result["energy"] + 0.01},
            True,
        )


def test_a_censored_seed_cannot_be_dropped_from_regime_claim():
    cases = [
        {
            "seed": s,
            "regime": r,
            "arm": a,
            "complete": True,
            "bit_memory_gate": a != "flat",
        }
        for s in verify.SEEDS
        for r in range(3)
        for a in verify.ARMS
    ]
    assert all(c["cycle_and_history_all_five_pass"] for c in verify.conclusions(cases))
    cases[0]["complete"] = False
    result = verify.conclusions(cases)
    assert (
        not result[0]["eligible"] and not result[0]["cycle_and_history_all_five_pass"]
    )
    assert len(result) == 3
