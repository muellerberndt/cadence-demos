"""Sampling, causal context, original gates, and interrupted-attempt custody."""

import copy
import os
import sys
from pathlib import Path

import amen_startup_curriculum as a
import numpy as np
import pytest


def test_schedules_preserve_exact_control_and_paired_half_exposure():
    lengths = [80] * 71
    for seed in a.SEEDS:
        result = a.schedules(lengths, seed)
        expected = (
            np.random.default_rng(seed)
            .permutation(sum(lengths))[:4096]
            .reshape(128, 32)
        )
        assert np.array_equal(result["uniform"], expected)
        balanced = np.asarray(result["startup-balanced"])
        assert np.array_equal(balanced[:, :16], expected[:, :16])
        _, pool = a.row_pools(lengths)
        extra = balanced[:, 16:].reshape(-1)
        assert len(pool) == 568 and np.isin(extra, pool).all()
        for start in range(0, len(extra) - len(pool) + 1, len(pool)):
            assert sorted(extra[start : start + len(pool)]) == sorted(pool)
        for rows in result.values():
            counts = a.exposure(rows, lengths)
            assert counts["presentations"] == 4096
            assert counts["prefix_rows"] + counts["other_rows"] == 4096
            assert counts["unique_rows"] + counts["repeated_presentations"] == 4096


def test_sampling_does_not_accept_or_depend_on_target_labels():
    lengths = [100] * 71
    before = a.schedules(lengths, 1103)
    arbitrary_targets = np.zeros((7100, 71))
    arbitrary_targets[:] = 1
    assert a.schedules(lengths, 1103) == before


def test_actual_prefix_features_match_generation_and_ignore_future():
    sys.path.insert(
        0,
        os.environ.get(
            "AMEN_APP", str(Path(__file__).resolve().parents[2] / "cadence-amen")
        ),
    )
    from drsn_amen import compose as C
    from drsn_amen import model as M
    from drsn_amen import stream as S

    events = np.zeros((12, 71))
    events[:, 0] = 1
    events[:, S.DRUM_ON] = 1
    events[:, S.DRUM_GAIN] = 0.8
    history, clock, wake, _ = S.stream(events, 8)
    for t in range(8):
        values = M.inputs_of(history[t], clock[t], wake[t], 8)
        assert values == C.senses(
            [S.COUNT_IN, *[S.executed(row) for row in events[:t]]], t, 8
        )
        future = events.copy()
        future[t:] = 0.777
        altered = S.stream(future, 8)
        assert values == M.inputs_of(altered[0][t], altered[1][t], altered[2][t], 8)
    assert wake[:, 0].tolist() == [1.0] + [0.0] * 11


def valid_report():
    free = {"complete": True, "drum_fraction": 0.5, "bass_fraction": 0.25}
    return {
        "status": "complete",
        "sources_unchanged": True,
        "accepted_admissions": 128,
        "refused_calls": 0,
        "unknown_calls": 0,
        "initial_heldout": {"qualified": 128},
        "final_heldout": {"qualified": 128},
        "heldout_mae_gain": 0.01,
        "generation": {
            "argmax-0": free,
            **{f"sample-{s}": {"complete": True} for s in (1, 2, 3, 4)},
        },
    }


@pytest.mark.parametrize(
    "failure",
    [
        "timeout",
        "admissions",
        "refusal",
        "unknown",
        "heldout",
        "mae",
        "drums",
        "bass",
        "sample",
        "source",
    ],
)
def test_original_gates_never_promote_failed_or_incomplete_arm(failure):
    r = copy.deepcopy(valid_report())
    assert a.gate(r)
    if failure == "timeout":
        r["status"] = "time_limit"
    elif failure == "admissions":
        r["accepted_admissions"] = 127
    elif failure == "refusal":
        r["refused_calls"] = 1
    elif failure == "unknown":
        r["unknown_calls"] = 1
    elif failure == "heldout":
        r["final_heldout"]["qualified"] = 127
    elif failure == "mae":
        r["heldout_mae_gain"] = 0.009
    elif failure == "drums":
        r["generation"]["argmax-0"]["drum_fraction"] = 0.49
    elif failure == "bass":
        r["generation"]["argmax-0"]["bass_fraction"] = 0.24
    elif failure == "sample":
        r["generation"]["sample-4"]["complete"] = False
    else:
        r["sources_unchanged"] = False
    assert not a.gate(r)


def test_interruption_retains_unknown_call_and_intent(tmp_path):
    class Brain:
        def snapshot(self):
            return "{}"

    calls = a.Calls(tmp_path, Brain())
    with pytest.raises(a.TimeCap):
        calls.call(
            {"kind": "admission", "update": 0, "indices": [1] * 32},
            lambda: (_ for _ in ()).throw(a.TimeCap()),
        )
    assert calls.rows[0]["unknown_solver_work"]
    assert a.read(tmp_path / "inflight.json")["indices"] == [1] * 32
    assert (tmp_path / "calls.jsonl").exists()


@pytest.mark.parametrize("changed", ["founder", "data"])
def test_bound_rejects_changed_frozen_founder_and_training_rows(
    tmp_path, monkeypatch, changed
):
    import torch

    (tmp_path / "founders").mkdir()
    (tmp_path / "data").mkdir()
    founder = tmp_path / "founders/seed1103.json"
    data = tmp_path / "data/history.npy"
    founder.write_text("{}")
    data.write_bytes(b"fixed rows")
    a.write(tmp_path / "schedules.json", {})
    a.write(tmp_path / "heldout.json", [])
    p = {
        "app": ".",
        "reference_helper": ".",
        "sources": {},
        "fixture_files": {},
        "runtime": {
            "python": sys.version,
            "numpy": np.__version__,
            "torch": torch.__version__,
            "cadence": a.cadence.__version__,
        },
        "founders": {"1103": a.sha(founder)},
        "data_files": {"history.npy": a.sha(data)},
        "schedules_sha256": a.sha(tmp_path / "schedules.json"),
        "heldout_sha256": a.sha(tmp_path / "heldout.json"),
    }
    a.write(tmp_path / "protocol.json", p)
    monkeypatch.setattr(a, "sources", lambda *_: {})
    assert a.bound(tmp_path) == p
    (founder if changed == "founder" else data).write_bytes(b"changed")
    with pytest.raises(ValueError, match="frozen"):
        a.bound(tmp_path)


def test_launch_error_retains_all_six_declared_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "bound", lambda _: {})

    def cannot_start(*args, **kwargs):
        raise OSError("fixture startup failure")

    monkeypatch.setattr(a.subprocess, "run", cannot_start)
    a.launch(tmp_path)
    result = a.read(tmp_path / "execution.json")
    assert [(r["seed"], r["arm"]) for r in result] == a.jobs()
    assert all(r["status"] == "launch_error" for r in result)
