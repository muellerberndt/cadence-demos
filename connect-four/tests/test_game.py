"""The rules and the encoding the brain reads: two stone planes and the playable cells."""
from __future__ import annotations

import numpy as np
import pytest

from connect4.game import CELLS, COLUMNS, LINES, Board, replay


def test_lines_are_every_four_in_a_row():
    assert LINES.shape == (69, 4)
    assert len({tuple(sorted(line)) for line in LINES.tolist()}) == 69


def test_encoding_is_mover_first_row_major_from_bottom_left():
    # player 0 drops in column 3; player 1 is to move and reads it as the opponent's stone
    x = replay([3]).board.encode(planes=2)
    assert x.shape == (84,) and set(np.unique(x)) <= {0.0, 1.0}
    assert x[:42].sum() == 0 and x[42 + 3] == 1 and x.sum() == 1
    # player 1 answers in column 3: the stone lands in row 1, cell 7 + 3; player 0 to move
    x = replay([3, 3]).board.encode(planes=2)
    assert x[3] == 1 and x[42 + 10] == 1 and x.sum() == 2
    x = replay([3, 3, 0]).board.encode(planes=2)  # player 1 to move: its stone at 10, the opponent's at 0 and 3
    assert x[10] == 1 and x[42 + 0] == 1 and x[42 + 3] == 1 and x.sum() == 3


def test_third_plane_is_where_a_stone_would_land():
    board = replay([3, 3, 0]).board
    x = board.encode()
    assert x.shape == (126,) and np.array_equal(x[:84], board.encode(planes=2))
    playable = x[84:].reshape(6, 7)
    # one landing cell per column with room: row 2 in column 3, row 1 in column 0, else row 0
    assert playable.sum() == 7 and playable[2, 3] == 1 and playable[1, 0] == 1 and playable[0, 6] == 1
    full = replay([0] * 6).board.encode()[84:].reshape(6, 7)
    assert full[:, 0].sum() == 0 and full.sum() == 6
    with pytest.raises(ValueError):
        board.encode(planes=4)


def test_cells_record_who_played_where():
    g = replay([3, 3, 2])
    assert g.cells[3] == 1 and g.cells[10] == 2 and g.cells[2] == 1
    assert sum(1 for v in g.cells if v) == 3 and g.to_move == 1


def test_full_column_is_illegal_and_refused():
    g = replay([0] * 6)
    assert g.board.legal().tolist() == [False] + [True] * 6
    assert g.summary()["legal"][0] is False
    with pytest.raises(ValueError):
        replay([0] * 7)
    with pytest.raises(ValueError):
        replay([7])
    with pytest.raises(ValueError):
        Board.empty().play(-1)


@pytest.mark.parametrize("moves, line", [
    ([0, 0, 1, 1, 2, 2, 3], [0, 1, 2, 3]),                    # horizontal
    ([0, 1, 0, 1, 0, 1, 0], [0, 7, 14, 21]),                  # vertical
    ([0, 1, 1, 2, 2, 3, 2, 3, 3, 6, 3], [0, 8, 16, 24]),      # diagonal up to the right
    ([6, 5, 5, 4, 4, 3, 4, 3, 3, 0, 3], [6, 12, 18, 24]),     # diagonal up to the left
])
def test_four_in_a_row_ends_the_game(moves, line):
    g = replay(moves)
    assert g.winner == 0 and g.over and g.line == tuple(line)
    assert g.summary()["legal"] == []
    with pytest.raises(ValueError):
        replay(moves + [5])


def test_draw_on_a_full_board_without_four():
    # column pairs filled in a pattern that never makes four, the last column alone
    columns = [0, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 2, 3, 2, 3, 2, 3, 3, 2, 3, 2, 3, 2,
               4, 5, 4, 5, 4, 5, 5, 4, 5, 4, 5, 4, 6, 6, 6, 6, 6, 6]
    g = replay(columns)
    assert len(g.moves) == CELLS and g.winner is None and g.board.full()
    assert g.summary()["draw"] is True and g.over


def test_winning_predicts_the_four():
    board = replay([0, 0, 1, 1, 2, 2]).board
    assert board.winning(3) and not board.winning(4)
    assert all(not board.winning(c) for c in range(COLUMNS) if c != 3)
