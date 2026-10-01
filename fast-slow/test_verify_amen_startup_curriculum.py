"""Mutation tests for independent custody/gate checks; no training admissions."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location(
    "startup_verifier", HERE / "verify_amen_startup_curriculum.py"
)
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


def passing():
    report = {"status": "complete", "sources_unchanged": True, "wall_seconds": 899}
    derived = {
        "attempted_admissions": 128,
        "accepted_admissions": 128,
        "refused_calls": 0,
        "unknown_calls": 0,
        "initial_heldout": {"qualified": 128, "metrics": {"decoded_all_port_mae": 0.5}},
        "final_heldout": {"qualified": 128, "metrics": {"decoded_all_port_mae": 0.1}},
        "generation": {
            k: {"complete": True, "drum_fraction": 0.5, "bass_fraction": 0.25}
            for k in ("argmax-0", "sample-1", "sample-2", "sample-3", "sample-4")
        },
    }
    return report, derived, {"exit_code": 0}


def test_sampler_changes_are_detected():
    lengths = [1234, 2345, 1234]
    tapes = V.C.schedules(lengths, 1103)
    value = V.validate_schedule(tapes, lengths, 1103)
    assert value["uniform"]["presentations"] == 4096
    assert value["startup-balanced"]["prefix_rows"] >= 2048
    tapes["startup-balanced"][0][16] = 123
    with pytest.raises(ValueError, match="replacement"):
        V.validate_schedule(tapes, lengths, 1103)


def test_uniform_permutation_is_bound():
    lengths = [5000]
    tapes = V.C.schedules(lengths, 1109)
    tapes["uniform"][0].reverse()
    with pytest.raises(ValueError, match="uniform"):
        V.validate_schedule(tapes, lengths, 1109)


def test_original_quality_thresholds():
    r, d, o = passing()
    assert V.eligible(r, d, o) == (True, True)
    d["generation"]["argmax-0"]["bass_fraction"] = 0.24999
    assert V.eligible(r, d, o) == (True, False)
    d["generation"]["argmax-0"]["bass_fraction"] = 0.25
    d["final_heldout"]["metrics"]["decoded_all_port_mae"] = 0.491
    assert V.eligible(r, d, o) == (True, False)


@pytest.mark.parametrize(
    "change",
    [
        "timeout",
        "outer",
        "refusal",
        "unknown",
        "admissions",
        "heldout",
        "sample",
        "source",
    ],
)
def test_incomplete_cannot_promote(change):
    r, d, o = passing()
    if change == "timeout":
        r["wall_seconds"] = 900
    if change == "outer":
        o = {"status": "outer_timeout"}
    if change == "refusal":
        d["refused_calls"] = 1
    if change == "unknown":
        d["unknown_calls"] = 1
    if change == "admissions":
        d["accepted_admissions"] = 127
    if change == "heldout":
        d["initial_heldout"]["qualified"] = 127
    if change == "sample":
        del d["generation"]["sample-4"]
    if change == "source":
        r["sources_unchanged"] = False
    assert V.eligible(r, d, o) == (False, False)


def test_unknown_intent_includes_attempted_exposure_not_accepted():
    intent = {"id": 0, "kind": "admission"}
    result = V.counts([], intent)
    assert result["attempted_admissions"] == 1
    assert result["attempted_presentations"] == 32
    assert result["accepted_admissions"] == 0
    assert result["unknown_calls"] == 1
    recorded = {**intent, "status": "interrupted_or_error"}
    assert V.counts([recorded], intent) == result


def test_forged_exit_code_cannot_override_outer_timeout():
    r, d, o = passing()
    o["status"] = "outer_timeout"
    assert V.eligible(r, d, o) == (False, False)


def test_returned_refusal_work_is_not_discarded():
    row = {
        "id": 0,
        "kind": "admission",
        "status": "returned",
        "result": {"accepted": False, "qualified": False, "work": {"evaluations": 2}},
    }
    value = V.counts([row])
    assert value["refused_calls"] == 1 and value["accepted_presentations"] == 0
    assert value["attempted_presentations"] == 32 and value["work"]["admission"] == {
        "evaluations": 2
    }


def test_free_query_replay_rejects_mutated_output_and_preserves_brain(tmp_path):
    from cadence import Cortex

    cortex = Cortex(seed=3, device="python", state_prior=0.01)
    past = cortex.input("past", shape=504)
    heard = cortex.input("heard", shape=72)
    clock = cortex.input("clock", shape=8)
    wake = cortex.input("wake", shape=())
    p = cortex.column("playing", patches=71, inputs=(past, heard, clock, wake))
    cortex.output("event", shape=71, reads=p)
    brain = cortex.build()
    path = tmp_path / "brain.json"
    path.write_text(brain.snapshot())

    class Ref:
        @staticmethod
        def flat_check(brain, steps):
            assert steps == 8 and len(brain.weights) == 41535

    replay = V.Replay(path, Ref)
    inputs = {
        "past": [0.0] * 504,
        "heard": [0.0] * 72,
        "clock": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "wake": 1.0,
    }
    result = brain.settle(inputs)
    row = {
        "id": 0,
        "before_sha256": V.C.sha(path),
        "after_sha256": V.C.sha(path),
        "inputs_sha256": V.C.digest(inputs),
        "result": V.C.compact(result),
    }
    row = json.loads(json.dumps(row))
    replay.query(row, inputs)
    replay.finish()
    bad = copy.deepcopy(row)
    bad["result"]["outputs"]["event"][0] += 0.01
    with pytest.raises(ValueError, match="exact free replay"):
        replay.query(bad, inputs)
    assert replay.gap < 1e-6
    assert np.isfinite(replay.gap)
