"""a brain-guided Monte Carlo tree search player.

A round is my move, then the opponent's reply knowing it (the convention of `absearch` and
`bots.voronoi2`). Each state of the tree is a node for my move; each of my moves leads to a node
for the opponent's reply; each reply leads to the next state (or a finished game: 1 a win, 0 a
loss, 0.5 a draw, from my side). Selection is PUCT: at my node the move maximizing
Q + c P sqrt(N) / (1 + n), at the opponent's node the reply maximizing (1 - Q) + c P' sqrt(N) /
(1 + n), Q my value.

A new state is evaluated by the brain, settled from rest on two rows: the state seen from my seat
and from the opponent's. The priors P (mine) and P' (the opponent's, the same brain in the other
seat) are the softmax of the settled motor activations at the brain's temperature. The leaf value
blends a value readout of my settled state (`value`: a logistic readout, `scripts/value_readout.py`)
with the Voronoi territory of the position (`fastbots._leaf`, squashed by a logistic of scale
`terr_scale` cells): v = lam * readout + (1 - lam) * territory; without a readout, territory only.

`batch` leaves are selected per brain call with a virtual loss, so one settle evaluates up to
2 x `batch` rows. The move is the root's most visited; `visits` returns the visit shares (the
AlphaZero policy target).

The settled state is read through `Brain._activity().activation` (cadence-net 0.95, a read-only
view of the stream's state after `act`; equal to the last state `record_settlements` reports).
"""

from __future__ import annotations

import math

import numpy as np

from . import absearch, fastbots
from .field import make_sense3
from .world import Arena

SEE = make_sense3("field")[0]


def clone(a: Arena) -> Arena:
    return Arena(a.size, a.seed, list(a.grid), list(a.heads), list(a.headings), list(a.alive), a.tick, a.over, a.winner)


class Evaluator:
    def __init__(self, brain_path: str, value: str | None = None, lam: float = 0.5, terr_scale: float = 20.0,
                 backend: str = "cpu"):
        from cadence import Brain
        self.brain = Brain.load(brain_path, backend=backend)
        self.backend = backend
        self.motor = np.asarray(self.brain.motor_index)
        self.temp = float(self.brain.learner.config.temperature)
        self.lam, self.terr_scale = lam, terr_scale
        self.readout = None
        if value:
            z = np.load(value)
            self.readout = (np.asarray(z["w"]), float(z["b"]), np.asarray(z["idx"]))
        n = 24 * 24
        self._a, self._b, self._q = np.empty(n, np.int64), np.empty(n, np.int64), np.empty(n, np.int64)
        self.calls = 0

    def territory(self, arena: Arena, seat: int) -> float:
        g, h, _ = absearch._state(arena)
        t = fastbots._leaf(g, arena.size, h, seat, self._a, self._b, self._q)
        return 1.0 / (1.0 + math.exp(-t / self.terr_scale))

    def __call__(self, arenas: list[Arena]):
        """Per state: (my prior, the opponent's prior, my value)."""
        x = np.stack([SEE(a, s) for a in arenas for s in (0, 1)]).astype(np.float64)
        self.brain.reset()
        self.brain.act(x, greedy=True)
        act = self.brain._activity().activation
        if hasattr(act, "detach"):  # torch backend
            act = act.detach().cpu().numpy()
        act = np.asarray(act).reshape(len(x), -1)
        self.calls += 1
        if self.backend == "torch" and self.calls % 200 == 0:
            import torch
            torch.cuda.empty_cache()  # the cache otherwise grows
        m = act[:, self.motor] / self.temp
        p = np.exp(m - m.max(1, keepdims=True))
        p /= p.sum(1, keepdims=True)
        out = []
        for i, a in enumerate(arenas):
            v = self.territory(a, 0)
            if self.readout is not None:
                w, b, idx = self.readout
                vr = 1.0 / (1.0 + math.exp(-(float(act[2 * i, idx] @ w) + b)))
                v = self.lam * vr + (1 - self.lam) * v
            out.append((p[2 * i], p[2 * i + 1], v))
        return out


class _Me:
    __slots__ = ("arena", "P", "Q0", "N", "W", "opp")

    def __init__(self, arena, P, Popp, v):
        self.arena, self.P, self.Q0 = arena, P, v
        self.N, self.W = np.zeros(3), np.zeros(3)
        self.opp = [_Opp(Popp) for _ in range(3)]


class _Opp:
    __slots__ = ("P", "N", "W", "kids")

    def __init__(self, P):
        self.P = P
        self.N, self.W = np.zeros(3), np.zeros(3)
        self.kids = [None, None, None]  # a _Me, or a float for a finished game


def search(arena: Arena, seat: int, ev: Evaluator, sims: int = 200, c: float = 1.5, batch: int = 8,
           noise: float = 0.0, alpha: float = 0.3, rng=None):
    """The move for `seat` and the root's visit shares. `noise` > 0 mixes Dirichlet(`alpha`)
    noise into the root prior (self-play exploration, AlphaZero)."""
    root_arena = clone(arena)
    if seat == 1:  # the tree is built from the side to move: mirror the seats
        root_arena = _swap(root_arena)
    (P, Popp, v), = ev([root_arena])
    if noise > 0:
        rng = rng or np.random.default_rng()
        P = (1 - noise) * P + noise * rng.dirichlet([alpha] * 3)
    root = _Me(root_arena, P, Popp, v)
    done = 0
    while done < sims:
        leaves, paths = [], []
        for _ in range(min(batch, sims - done)):
            path, node = [], root
            while True:
                tot = node.N.sum()
                q = np.where(node.N > 0, node.W / np.maximum(node.N, 1), node.Q0)
                a = int(np.argmax(q + c * node.P * math.sqrt(tot + 1) / (1 + node.N)))
                o = node.opp[a]
                tot2 = o.N.sum()
                q2 = np.where(o.N > 0, o.W / np.maximum(o.N, 1), node.Q0)
                b = int(np.argmax((1 - q2) + c * o.P * math.sqrt(tot2 + 1) / (1 + o.N)))
                path.append((node, a, o, b))
                # virtual loss: my visit counts as a loss, the opponent's as a loss for it
                node.N[a] += 1
                o.N[b] += 1
                o.W[b] += 1.0
                kid = o.kids[b]
                if kid is None:
                    nxt = clone(node.arena)
                    nxt.step((a, b))
                    if nxt.over:
                        o.kids[b] = 1.0 if nxt.winner == 0 else 0.5 if nxt.winner is None else 0.0
                        leaves.append(("end", o.kids[b]))
                    else:
                        leaves.append(("new", nxt))
                    break
                if isinstance(kid, float):
                    leaves.append(("end", kid))
                    break
                node = kid
            paths.append(path)
        new = [i for i, (k, _) in enumerate(leaves) if k == "new"]
        vals = {}
        if new:
            evs = ev([leaves[i][1] for i in new])
            for i, (P1, P2, v1) in zip(new, evs):
                node, a, o, b = paths[i][-1]
                if o.kids[b] is None:
                    o.kids[b] = _Me(leaves[i][1], P1, P2, v1)
                vals[i] = v1
        for i, path in enumerate(paths):
            v = vals[i] if i in vals else leaves[i][1]
            for node, a, o, b in path:
                node.W[a] += v
                o.W[b] += v - 1.0  # remove the virtual loss, add the value
        done += len(paths)
    visits = root.N / max(root.N.sum(), 1)
    return int(np.argmax(root.N)), visits


def _swap(a: Arena) -> Arena:
    """The same position with the seats exchanged (my cycle in seat 0)."""
    n = a.size
    grid = [0 if v == 0 else (2 if v == 1 else 1) for v in a.grid]
    w = None if a.winner is None else 1 - a.winner
    return Arena(n, a.seed, grid, [a.heads[1], a.heads[0]], [a.headings[1], a.headings[0]],
                 [a.alive[1], a.alive[0]], a.tick, a.over, w)


def player(ev: Evaluator, sims: int = 200, c: float = 1.5, batch: int = 8):
    def play(arena, seat):
        return search(arena, seat, ev, sims, c, batch)[0]
    return play
