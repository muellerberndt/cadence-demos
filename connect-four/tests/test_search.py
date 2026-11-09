"""The search that vets the brain's proposal: wins it must take, blocks it must make, cells it must
not open, and the brain's preference where the search sees no difference."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from connect4.game import COLUMNS, replay
from connect4.search import WIN, Searcher, bits, choose, priors

FLAT = np.zeros(COLUMNS)


def test_bitboards_count_the_stones():
    board = replay([3, 3, 2]).board
    position, mask, stones = bits(board)
    assert stones == 3 and bin(mask).count("1") == 3 and bin(position).count("1") == 1


def test_takes_an_immediate_win_whatever_the_brain_prefers():
    board = replay([0, 6, 1, 6, 2, 5]).board  # the mover has 0, 1, 2 on the bottom row
    motor = np.full(COLUMNS, -0.1)
    motor[6] = 1.0  # the brain wants column 7
    r = choose(board, motor, 0.2, nodes=5_000)
    assert r["column"] == 3 and r["reason"] == "win"


def test_blocks_a_win_next_move():
    board = replay([0, 6, 1, 6, 2]).board  # the opponent threatens column 4 on the bottom row
    motor = np.full(COLUMNS, -0.1)
    motor[5] = 1.0
    r = choose(board, motor, 0.2, nodes=20_000)
    assert r["column"] == 3


def test_does_not_open_the_cell_under_a_threat():
    # the opponent holds row 2 at columns 2, 3 and 4 over a filled row 1; columns 1 and 5 are
    # empty, so a stone there lets the opponent complete four on row 2
    board = replay([1, 1, 3, 3, 6, 2, 6, 2]).board
    s = Searcher(20_000).root(board)
    assert s["values"][0] <= -(WIN - 50) and s["values"][4] <= -(WIN - 50)
    assert max(s["values"].values()) > -(WIN - 50)


def test_keeps_the_brains_column_when_the_search_sees_no_difference():
    board = replay([]).board
    motor = np.full(COLUMNS, -0.1)
    motor[2] = 1.0
    r = choose(board, motor, 0.2, nodes=2_000)
    assert r["column"] == 2 and r["reason"] == "brain"


def test_priors_are_a_distribution_over_legal_columns():
    legal = np.array([True, True, False, True, True, True, True])
    p = priors(np.arange(COLUMNS, dtype=float), legal, 0.2)
    assert p[2] == 0 and abs(p.sum() - 1) < 1e-12 and np.argmax(p) == 6


BRAIN = Path(__file__).resolve().parents[1] / "web" / "pack" / "brain.npz"


def test_host_think_with_search_plays_a_legal_vetted_column():
    if not BRAIN.exists():
        pytest.skip("run pack.py first")
    from connect4.host import Host

    h = Host(str(BRAIN))
    moves = [0, 6, 1, 6, 2]
    reply = h.handle({"command": "think", "payload": {"moves": moves, "search": True}})
    while not reply["done"]:
        reply = h.handle({"command": "more", "payload": {"id": reply["id"]}})
    final = reply["final"]
    assert final["search"] is not None and final["column"] == 3  # the block
    assert final["legal"][final["column"]] and 0 <= final["brain_column"] < COLUMNS
    assert final["after"]["moves"] == moves + [3]
