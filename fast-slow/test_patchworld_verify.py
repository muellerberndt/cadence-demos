"""Adversarial promotion, replay and split checks; no learning required."""

import copy

import patchworld_bootstrap as p
import patchworld_verify as v
import pytest


def test_incomplete_or_unqualified_cannot_pass():
    after, native = {"qualified": 48, "agreement": 1.0}, {"refused": 0}
    assert v.acquisition_gate("complete", 120, after, native)
    assert not v.acquisition_gate("timeout", 120, after, native)
    assert not v.acquisition_gate("complete", 119, after, native)
    assert not v.acquisition_gate("complete", 120, {**after, "qualified": 47}, native)
    assert not v.acquisition_gate("complete", 120, after, {"refused": 1})


def test_source_bound_pure_replay_rejects_forged_prediction_or_custody():
    brain = p.make("flat", 211)
    inputs = {"food": [0.1] * 9}
    snapshot = brain.snapshot()
    row = {
        "inputs": inputs,
        "result": brain.settle(inputs),
        "before_sha256": v.digest(snapshot),
        "after_sha256": v.digest(snapshot),
    }
    v.replay_query(brain, row)
    forged = copy.deepcopy(row)
    forged["result"]["outputs"]["action"] = list(forged["result"]["outputs"]["action"])
    forged["result"]["outputs"]["action"][0] += 0.01
    with pytest.raises(ValueError, match="replayed query"):
        v.replay_query(brain, forged)
    with pytest.raises(ValueError, match="custody"):
        v.replay_query(brain, {**row, "before_sha256": "x"})


def test_independent_tape_and_frozen_overlap_are_retained():
    train, held = v.tape(96, 641), v.tape(48, 647)
    assert train == p.examples(96, 641) and held == p.examples(48, 647)
    seen = {tuple(row[0]["food"]) for row in train}
    assert sum(tuple(row[0]["food"]) in seen for row in held) == 8


def test_metric_reconstruction_rejects_wrong_qualified_flag():
    brain = p.make("flat", 211)
    examples = v.tape(2, 647)
    rows = [
        {"inputs": inputs, "result": brain.settle(inputs)} for inputs, _ in examples
    ]
    truth = v.metrics(rows, examples)
    assert truth["qualified"] == 2
    rows[0]["result"]["qualified"] = False
    changed = v.metrics(rows, examples)
    assert changed["qualified"] == 1
    with pytest.raises(ValueError):
        v.same(changed, truth)
