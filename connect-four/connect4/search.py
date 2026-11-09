"""The brain plus a search: the brain proposes, a look-ahead vets.

The brain settles once on the board, as when it plays alone. Its seven column neurons, read
as a softmax at the learner's temperature, are the search's priors. A negamax search with
alpha-beta pruning then reads ahead over the game's rules (bitboards, a transposition table,
iterative deepening within a budget of nodes), and scores the positions at its horizon with a
threat count: the cells where a stone would complete four for either side, weighted by the
row parity that lets the side make use of them. Wins and losses inside the horizon are exact.

The move: a win the search proves is played (the fastest); columns the search proves lost are
dropped while any other remains; among the rest the brain's own preference decides, unless the
search scores another column clearly higher (by more than ``MARGIN``), when the search's column
is played. The brain's verdict slot is read at the root and reported; it does not enter the
search, whose leaves are far too many to settle the brain on in a browser.

Nothing here learns, and the brain is not changed. The search knows the rules of the game, not
the solver's scores.
"""

from __future__ import annotations

import time

import numpy as np

from .game import COLUMNS, ROWS, Board

H = ROWS + 1  # bits per column: six cells and a sentinel
BOTTOM = sum(1 << (c * H) for c in range(COLUMNS))
BOARD = BOTTOM * ((1 << ROWS) - 1)
ORDER = (3, 2, 4, 1, 5, 0, 6)
WIN = 1000.0
MARGIN = 0.25  # how much higher the search must score a column to overrule the brain
NODES = 120_000  # the search's budget: positions visited per move (deterministic on any machine)


def bits(board: Board) -> tuple[int, int, int]:
    """(stones of the side to move, all stones, stones on the board) as Pons-style bitboards."""
    position = mask = 0
    for r in range(ROWS):
        for c in range(COLUMNS):
            bit = 1 << (c * H + r)
            if board.mine[r, c]:
                position |= bit
                mask |= bit
            elif board.theirs[r, c]:
                mask |= bit
    return position, mask, int(board.stones)


def _wins(p: int, mask: int) -> int:
    """The empty cells where a stone of ``p`` would complete four."""
    r = (p << 1) & (p << 2) & (p << 3)
    for s in (H, H - 1, H + 1):
        q = (p << s) & (p << 2 * s)
        r |= q & (p << 3 * s)
        r |= q & (p >> s)
        q = (p >> s) & (p >> 2 * s)
        r |= q & (p << s)
        r |= q & (p >> 3 * s)
    return r & (BOARD ^ mask)


def _popcount(x: int) -> int:
    return bin(x).count("1")


ODD_ROWS = sum(1 << (c * H + r) for c in range(COLUMNS) for r in (0, 2, 4))  # rows 1, 3, 5


def _leaf(position: int, mask: int, stones: int) -> float:
    """The threat count from the side to move, in (-1, 1). The side that moved first can use
    threats on rows 1, 3 and 5 (counted from the bottom); the other side those on 2, 4 and 6."""
    opponent = position ^ mask
    mine, theirs = _wins(position, mask), _wins(opponent, mask)
    first = stones % 2 == 0  # the side to move moved first
    good_mine = ODD_ROWS if first else BOARD ^ ODD_ROWS
    good_theirs = BOARD ^ good_mine
    score = (_popcount(mine) + _popcount(mine & good_mine)) - (_popcount(theirs) + _popcount(theirs & good_theirs))
    centre = (0b111111 << (3 * H))
    score += 0.25 * (_popcount(position & centre) - _popcount(opponent & centre))
    return float(np.tanh(0.2 * score)) * 0.9


class _Timeout(Exception):
    pass


class Searcher:
    def __init__(self, nodes: int = NODES, max_depth: int = 42) -> None:
        self.limit = int(nodes)
        self.max_depth = max_depth
        self.table: dict[tuple[int, int], tuple[int, float, int, int]] = {}
        self.nodes = 0

    def _negamax(self, position: int, mask: int, stones: int, depth: int, alpha: float, beta: float, ply: int) -> float:
        self.nodes += 1
        if self.nodes > self.limit:
            raise _Timeout
        possible = (mask + BOTTOM) & BOARD
        mine = _wins(position, mask)
        if mine & possible:
            return WIN - ply - 1
        if stones >= ROWS * COLUMNS - 1:
            return 0.0
        opponent = position ^ mask
        theirs = _wins(opponent, mask)
        forced = possible & theirs
        if forced:
            if forced & (forced - 1):  # two threats at once: lost
                return -(WIN - ply - 2)
            possible = forced
        possible &= ~(theirs >> 1)  # never play under the opponent's winning cell
        if not possible:
            return -(WIN - ply - 2)
        if depth == 0:
            return _leaf(position, mask, stones)
        key = (position, mask)
        hit = self.table.get(key)
        first = None
        if hit is not None:
            h_depth, h_value, h_flag, h_move = hit
            first = h_move
            if h_depth >= depth:
                if h_flag == 0:
                    return h_value
                if h_flag == 1 and h_value >= beta:
                    return h_value
                if h_flag == -1 and h_value <= alpha:
                    return h_value
        order = ([first] if first is not None else []) + [c for c in ORDER if c != first]
        best, best_move, start_alpha = -2 * WIN, None, alpha
        for c in order:
            col = possible & (((1 << ROWS) - 1) << (c * H))
            if not col:
                continue
            new_mask = mask | col
            value = -self._negamax(position ^ mask, new_mask, stones + 1, depth - 1, -beta, -alpha, ply + 1)
            if value > best:
                best, best_move = value, c
            if value > alpha:
                alpha = value
            if alpha >= beta:
                break
        flag = 0 if start_alpha < best < beta else (1 if best >= beta else -1)
        self.table[key] = (depth, best, flag, best_move)
        return best

    def root(self, board: Board) -> dict:
        """Every legal column's value from the side to move, at the deepest finished depth."""
        position, mask, stones = bits(board)
        began = time.perf_counter()
        self.nodes = 0
        legal = [c for c in range(COLUMNS) if board.legal()[c]]
        values: dict[int, float] = {}
        depth_done = 0
        immediate = [c for c in legal if board.winning(c)]
        if immediate:
            values = {c: (WIN - 1 if c in immediate else -2 * WIN) for c in legal}
            return {"values": values, "depth": 0, "nodes": 0, "ms": 0.0, "immediate": True}
        try:
            for depth in range(1, min(self.max_depth, ROWS * COLUMNS - stones) + 1):
                found = {}
                for c in legal:
                    col = ((mask + BOTTOM) & BOARD) & (((1 << ROWS) - 1) << (c * H))
                    found[c] = -self._negamax(position ^ mask, mask | col, stones + 1, depth - 1,
                                              -2 * WIN, 2 * WIN, 1)
                values, depth_done = found, depth
                if all(abs(v) >= WIN - 50 for v in found.values()) or max(found.values()) >= WIN - 50:
                    break  # every column decided, or a win proven
        except _Timeout:
            pass
        return {"values": values, "depth": depth_done, "nodes": self.nodes,
                "ms": round((time.perf_counter() - began) * 1000.0, 1), "immediate": False}


def priors(motor: np.ndarray, legal: np.ndarray, temperature: float) -> np.ndarray:
    """The brain's column neurons as a distribution over the legal columns."""
    z = np.where(legal, np.asarray(motor[:COLUMNS], float) / float(temperature), -np.inf)
    z = z - z[legal].max()
    p = np.exp(z)
    return p / p.sum()


def choose(board: Board, motor: np.ndarray, temperature: float, nodes: int = NODES) -> dict:
    """The brain-plus-search move on ``board`` given the brain's settled motor activations."""
    legal = board.legal()
    p = priors(motor, legal, temperature)
    brain = int(np.argmax(np.where(legal, motor[:COLUMNS], -np.inf)))
    s = Searcher(nodes).root(board)
    values = s["values"]
    if not values:  # the budget did not cover depth 1: the brain's move
        return {"column": brain, "brain": brain, "reason": "brain", "priors": p.tolist(), **s}
    best = max(values.values())
    if best >= WIN - 50:
        column = max((c for c in values if values[c] == best), key=lambda c: p[c])
        reason = "win"
    else:
        alive = [c for c in values if values[c] > -(WIN - 50)] or list(values)
        top = max(values[c] for c in alive)
        if brain in alive and values[brain] >= top - MARGIN:
            column, reason = brain, "brain"
        else:
            near = [c for c in alive if values[c] >= top - MARGIN]
            column = max(near, key=lambda c: p[c])
            reason = "search" if column != brain else "brain"
    return {"column": int(column), "brain": brain, "reason": reason, "priors": [round(float(v), 6) for v in p],
            "values": {int(c): round(float(v), 4) for c, v in values.items()},
            **{k: s[k] for k in ("depth", "nodes", "ms", "immediate")}}
