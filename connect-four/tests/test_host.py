"""The host the page's worker runs: the brain's readout, the drawn settle, lessons, imagination.

These run against the brain packed in web/pack/ (run pack.py first); they hold for any brain of
this layout, trained or not.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from connect4.game import COLUMNS, replay
from connect4.host import Host, _strongest_legal

BRAIN = Path(__file__).resolve().parents[1] / "web" / "pack" / "brain.npz"
POSITIONS = [[], [3], [3, 3], [3, 2, 4, 4, 2, 3], [0, 6, 1, 5, 2, 4], [0, 0, 0, 1, 1, 1, 2, 2],
             [3, 3, 3, 3, 3, 3], [0, 1, 2, 3, 4, 5, 6, 0, 1, 2, 3, 4, 5, 6, 0, 1, 2, 3]]


@pytest.fixture(scope="module")
def host():
    if not BRAIN.exists():
        pytest.skip("run pack.py first")
    return Host(str(BRAIN))


def settle(host, moves):
    """The whole drawn settle: every chunk's frames and the final reading."""
    reply = host.handle({"command": "think", "payload": {"moves": moves}})
    frames, movement = [host.buffers["frames"]], list(reply["movement"])
    while not reply["done"]:
        reply = host.handle({"command": "more", "payload": {"id": reply["id"]}})
        frames.append(host.buffers["frames"])
        movement += reply["movement"]
    return reply, np.concatenate(frames), movement


def contract(brain, moves):
    """The readout the brain was evaluated with: learner.free on the memory-free stimulus."""
    x = replay(moves).board.encode(len(brain.sensory_index) // 42)[None, :]
    state = brain.learner.free(brain.stimulus(x, memory=False))
    return np.asarray(state.activation)[0], int(state.steps)


def test_strongest_legal_masks_full_columns():
    motor = np.array([0.1, 0.2, 0.3, 0.9, 0.3, 0.2, 0.1])
    legal = np.array([True, True, True, False, True, True, True])
    assert _strongest_legal(motor, legal) in (2, 4)
    assert _strongest_legal(motor, np.ones(7, bool)) == 3


@pytest.mark.parametrize("moves", POSITIONS)
def test_drawn_settle_is_the_contract_readout(host, moves):
    reply, frames, movement = settle(host, moves)
    final = reply["final"]
    activation, steps = contract(host.brain, moves)
    # the chunked settle is the same run as one Learner.free call, sweep for sweep
    assert final["sweeps"] == steps == len(frames) == len(movement)
    np.testing.assert_allclose(frames[-1], activation, atol=1e-6)  # float32 frames
    motor = activation[host.brain.learner.output_index][:COLUMNS]
    np.testing.assert_allclose(final["motor"], motor, atol=1e-6)
    if host.verdict_slot:
        assert len(final["verdict"]) == 3 and abs(sum(final["verdict"]) - 1) < 1e-5
    legal = replay(moves).board.legal()
    assert final["column"] == int(np.argmax(np.where(legal, motor, -np.inf)))
    assert final["legal"][final["column"]]
    # the stop rule: the last sweep moved no activation by the tolerance or more
    tolerance = host.brain.learner.config.tolerance
    if final["settled"]:
        assert movement[-1] <= tolerance and all(m >= tolerance - 1e-6 for m in movement[:-1])
    assert reply["final"]["after"]["moves"] == list(moves) + [final["column"]]


def test_full_column_is_never_played(host):
    moves = [3, 3, 3, 3, 3, 3]  # column 3 is full
    reply, _, _ = settle(host, moves)
    assert reply["final"]["column"] != 3 and reply["final"]["legal"][3] is False


def test_check_command_agrees_with_the_drawn_settle(host):
    for moves in POSITIONS[:4]:
        reply, _, _ = settle(host, moves)
        checked = host.handle({"command": "check", "payload": {"moves": moves}})
        assert checked["column"] == reply["final"]["column"]
        assert checked["sweeps"] == reply["final"]["sweeps"]


def test_frames_start_from_rest_and_movement_is_measured(host):
    reply, frames, movement = settle(host, [3, 2])
    np.testing.assert_allclose(movement[0], np.abs(frames[0]).max(), rtol=1e-5, atol=1e-6)
    for t in range(1, len(frames)):
        assert movement[t] == pytest.approx(float(np.abs(frames[t] - frames[t - 1]).max()), abs=2e-6)


def test_layout_names_populations_and_draws_active_pathways(host):
    reply = host.handle({"command": "init"})
    brain = reply["brain"]
    names = [p["name"] for p in brain["populations"]]
    assert {"sensory", "association", "motor"} <= set(names)
    motor = next(p for p in brain["populations"] if p["name"] == "motor")
    assert "motor/actions" in motor["aliases"] and motor["size"] == len(brain["motor"])
    assert len(brain["sensory"]) == 42 * brain["planes"] and brain["planes"] in (2, 3)
    assert len(brain["motor"]) == COLUMNS + (3 if brain["verdict"] else 0)
    assert sum(p["size"] for p in brain["populations"]) == brain["neurons"]
    assert sum(b["synapses"] for b in brain["blocks"]) == brain["synapses"]
    for block in brain["blocks"]:
        if not block["silent"] and block["synapses"] <= 150_000:
            assert block["drawn"] == block["synapses"]  # every synapse of an active pathway
    pre, post, weight = (host.buffers[k] for k in ("pre", "post", "weight"))
    assert pre.dtype == np.int32 and weight.dtype == np.float32 and len(pre) == len(post) == brain["drawn"]
    c = host.brain.brain.connectome
    np.testing.assert_array_equal(pre, c.pre[host.drawn])
    np.testing.assert_allclose(weight, np.asarray(host.brain.brain.weights)[host.drawn], rtol=1e-6)
    assert brain["compose"].startswith(f"Brain.compose({len(brain['sensory'])}, {len(brain['motor'])}, modules=(")
    json.dumps(reply, allow_nan=False)


def test_silent_population_stays_at_rest(host):
    _, frames, _ = settle(host, [3, 2, 4])
    for name in host.silent:
        members = next(p["members"] for p in host.populations if p["name"] == name)
        assert np.all(frames[:, list(members)] == 0.0)


def test_imagine_changes_nothing(host):
    w0 = np.asarray(host.brain.brain.weights).copy()
    before = host.handle({"command": "check", "payload": {"moves": [3, 3]}})
    reply = host.handle({"command": "imagine", "payload": {"moves": [3, 3]}})
    columns = [c["column"] for c in reply["candidates"]]
    assert columns == [c for c in range(COLUMNS) if replay([3, 3]).board.legal()[c]]
    for c in reply["candidates"]:
        if "reply" in c:
            assert replay([3, 3, c["column"]]).board.legal()[c["reply"]]
    np.testing.assert_array_equal(np.asarray(host.brain.brain.weights), w0)
    assert host.handle({"command": "check", "payload": {"moves": [3, 3]}})["motor"] == before["motor"]
    json.dumps(reply, allow_nan=False)


def test_lesson_changes_the_brain_and_reset_restores_it():
    if not BRAIN.exists():
        pytest.skip("run pack.py first")
    h = Host(str(BRAIN))
    moves = [3, 2]
    w0 = np.asarray(h.brain.brain.weights).copy()
    choice = h.handle({"command": "check", "payload": {"moves": moves}})["column"]
    other = next(c for c in (0, 6, 1, 5) if c != choice)
    reply = h.handle({"command": "lesson", "payload": {"moves": moves, "column": other}})
    assert reply["accepted"] and reply["changed"] > 0 and reply["lessons"] == 1
    w1 = np.asarray(h.brain.brain.weights)
    assert np.count_nonzero(w1 - w0) == reply["changed"]
    assert reply["after"][other] != reply["before"][other]
    assert len(h.buffers["changed"]) == len(h.buffers["delta"]) > 0
    np.testing.assert_allclose(h.buffers["weight"], w1[h.drawn], rtol=1e-6)
    json.dumps(reply, allow_nan=False)
    # a lesson on the brain's own answer is no surprise: nothing changes
    own = h.handle({"command": "check", "payload": {"moves": [0]}})["column"]
    w2 = np.asarray(h.brain.brain.weights).copy()
    reply = h.handle({"command": "lesson", "payload": {"moves": [0], "column": own}})
    assert not reply["accepted"] and reply["changed"] == 0
    np.testing.assert_array_equal(np.asarray(h.brain.brain.weights), w2)
    with pytest.raises(ValueError):
        h.handle({"command": "lesson", "payload": {"moves": [3] * 6, "column": 3}})
    h.handle({"command": "reset_brain"})
    np.testing.assert_array_equal(np.asarray(h.brain.brain.weights), w0)
    assert h.lessons == 0


def test_requests_after_the_end_are_refused(host):
    over = [0, 1, 0, 1, 0, 1, 0]
    for command in ("think", "imagine", "check"):
        with pytest.raises(ValueError):
            host.handle({"command": command, "payload": {"moves": over}})
    assert host.handle({"command": "position", "payload": {"moves": over}})["game"]["winner"] == 0
