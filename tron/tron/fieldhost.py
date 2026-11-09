"""One brain in the page: the full-field sense, cadence-net 0.95.2, played frozen.

The page's worker runs this host for brains whose meta names ``"sense": "field"``. It plays
exactly as the readings measure a brain (`tron.r3.policy`): the brain is reset at the start of every
game and each move is ``brain.act(field(arena, seat)[None, :], greedy=True)``. Nothing is
learned while you play, so a game is fully determined by the arena seed and your moves, and the
moves are the ones the checkpoint reports were scored with.

The brain rides seat 0, the player seat 1, as in `tron.host`. Each settle is recorded
(`record_settlements`) and sent to the page sweep by sweep: the observation (the 2,470 inputs),
the state of every non-sensory neuron after each sweep, the largest potential repair per sweep
and the final equation residual.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import time
from typing import Any

import numpy as np

from .field import FOVEA, field, field_size
from .world import Arena

MAX_FRAMES = 128  # sweeps sent per settle (subsampled beyond this; the last is always sent)
EDGES = 2400


def game_seed(name: str, index: int) -> int:
    digest = hashlib.sha256(f"{name}:{index}".encode()).digest()
    return int.from_bytes(digest[:4], "little")


def _load(data: bytes):
    from cadence import Brain

    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "brain.npz")
        with open(path, "wb") as handle:
            handle.write(data)
        return Brain.load(path, backend="cpu")  # the page runs NumPy on the CPU; so do the readings


def retina(n: int) -> list[dict[str, Any]]:
    """Where each input lives, in `tron.field.field` order."""
    p = n * n
    f = FOVEA * FOVEA
    return [
        {"key": "blocked", "label": "blocked", "start": 0, "rows": n, "cols": n},
        {"key": "trail", "label": "your trail", "start": p, "rows": n, "cols": n},
        {"key": "self", "label": "its head", "start": 2 * p, "rows": n, "cols": n},
        {"key": "you", "label": "your head", "start": 3 * p, "rows": n, "cols": n},
        {"key": "fovea", "label": "fovea · blocked", "start": 4 * p, "rows": FOVEA, "cols": FOVEA, "head": [5, 4]},
        {"key": "fovea_you", "label": "fovea · your head", "start": 4 * p + f, "rows": FOVEA, "cols": FOVEA, "head": [5, 4]},
        {"key": "heading", "label": "your heading", "start": 4 * p + 2 * f, "rows": 1, "cols": 4,
         "names": ["same", "right", "opposite", "left"]},
    ]


class FieldHost:
    def __init__(self, data: bytes, meta: dict[str, Any]) -> None:
        self.meta = meta
        self.name = meta["name"]
        self.size = int(meta.get("size", 24))
        self.brain = _load(data)
        self.n_in = field_size(self.size)
        pops = self.brain.connectome.populations
        if len(pops["sensory"]) != self.n_in:
            raise ValueError(f"the brain has {len(pops['sensory'])} inputs, the field sense {self.n_in}")
        self.n = int(self.brain.connectome.n)
        self.shimmed = False
        self.refused = 0
        self.games = int(meta.get("games", 0))
        self.arena: Arena | None = None
        self.pending: int | None = None
        self.moved: list[int] | None = None  # [brain, player] of the last tick
        self.last: dict[str, Any] = {}
        self.settle: dict[str, Any] = {}
        # Search mode (op "mode"): the brain's settle is the prior and the leaf evaluator of a
        # brain-guided tree search (tron/mcts.py) that picks the move; 0 plays the brain alone.
        self.sims = int(meta.get("sims", 0))
        self._evaluator = None

    # ---- the move -----------------------------------------------------------------------------
    def _act(self) -> int:
        from cadence import record_settlements

        x = field(self.arena, 0)
        records = []
        refused = False
        t0 = time.perf_counter()
        if self.meta.get("settle_from_rest"):
            # every move settles from rest, as the brain was taught and measured.
            self.brain.reset()
        with record_settlements(records.append):
            try:
                action = int(self.brain.act(x[None, :], greedy=True)[0])
            except RuntimeError:
                # A settle that does not qualify is refused: the cycle rides straight on.
                action, refused = 1, True
                self.refused += 1
        act_ms = 1e3 * (time.perf_counter() - t0)
        search = None
        if self.sims > 0 and not refused:
            from . import mcts

            if self._evaluator is None:
                self._evaluator = mcts.Evaluator(self.brain)
            t2 = time.perf_counter()
            brain_move = action
            action, visits = mcts.search(self.arena, 0, self._evaluator, sims=self.sims)
            search = {"sims": self.sims, "visits": [round(float(v), 3) for v in visits], "brain_move": brain_move,
                      "ms": round(1e3 * (time.perf_counter() - t2), 1)}
        t1 = time.perf_counter()
        free = [r for r in records if r.nudge is None and r.steps > 0]
        lo = self.n_in
        if free:
            states = [free[0].activation[:, 0, lo:]] + [r.activation[1:, 0, lo:] for r in free[1:]]
            acts = np.concatenate(states, axis=0)
            pots = np.concatenate([free[0].potential[:, 0, :]] + [r.potential[1:, 0, :] for r in free[1:]], axis=0)
            repair = np.abs(np.diff(pots, axis=0)).max(axis=1)
        else:
            acts = np.zeros((1, self.n - lo))
            repair = np.zeros(0)
        sweeps = int(sum(r.steps for r in free))
        residual = self._residual(free[-1]) if free else None
        pick = np.arange(len(acts))
        if len(acts) > MAX_FRAMES:
            pick = np.unique(np.linspace(0, len(acts) - 1, MAX_FRAMES).round().astype(int))
        frames = acts[pick].astype(np.float32)
        motor = self.brain.connectome.populations["motor"]
        self.settle = {
            "obs": base64.b64encode(np.asarray(x).astype(np.uint8).tobytes()).decode(),
            "frames": base64.b64encode(frames.tobytes()).decode(),
            "nframes": int(len(frames)),
            "frame_sweeps": pick.tolist(),
            "offset": lo,
            "repair": [float(f"{v:.3g}") for v in repair],
            "motor": np.round(acts[:, np.asarray(motor) - lo], 4).tolist(),
        }
        self.last = {
            "mode": "frozen" if search is None else "search",
            "choice": action,
            "search": search,
            "sweeps": sweeps,
            "settles": len(records),
            "residual": residual,
            "tolerance": float(self.brain.learner.config.tolerance),
            "refused": refused,
            "learned": False,
            "act_ms": round(act_ms, 2),
            "pack_ms": round(1e3 * (time.perf_counter() - t1), 2),
        }
        return action

    def _residual(self, record) -> float | None:
        """The fixed-point residual of the settled state the move was read from."""
        try:
            from cadence.brain import BrainState

            state = BrainState(record.potential[-1], record.activation[-1], record.adaptation[-1], record.steps)
            return float(np.max(self.brain.brain.residual(record.drive, state, mask=record.mask)))
        except Exception:
            return None

    # ---- the game -------------------------------------------------------------------------------
    def begin(self, seed: int | None = None) -> dict[str, Any]:
        self.arena = Arena(self.size, seed=game_seed(self.name, self.games) if seed is None else int(seed))
        self.brain.reset()
        self.moved = None
        self.proposed = None
        self.pending = self._act()
        return self.state(full=True)

    def tick(self, player: int, decided: int | None = None) -> dict[str, Any]:
        """One round. `decided`: the move the page's player chose for the brain's cycle (the
        look-ahead over the rules, seeded with the brain's pick); None plays the brain's pick."""
        if self.arena is None or self.arena.over:
            raise RuntimeError("no game in progress")
        player = int(player)
        if player not in (0, 1, 2):
            raise ValueError("a move is 0 (left), 1 (straight) or 2 (right)")
        mine = self.pending if decided is None else int(decided)
        if mine not in (0, 1, 2):
            raise ValueError("a decided move is 0, 1 or 2")
        self.moved = [mine, player]
        self.proposed = self.pending
        self.arena.step((mine, player))
        if self.arena.over:
            self.games += 1
            self.pending = None
            self.settle = {}
            return self.state()
        self.pending = self._act()
        return self.state()

    def result(self) -> str:
        a = self.arena
        return "win" if a.winner == 0 else "loss" if a.winner == 1 else "draw"

    # ---- what the page sees ----------------------------------------------------------------------
    def state(self, full: bool = False) -> dict[str, Any]:
        a = self.arena
        out: dict[str, Any] = {
            "format": "field",
            "game": self.games if not a.over else self.games - 1,
            "tick": a.tick,
            "heads": [list(h) for h in a.heads],
            "headings": list(a.headings),
            "alive": list(a.alive),
            "over": a.over,
            "result": self.result() if a.over else None,
            "lessons": 0,
            "moved": self.moved,
            "proposed": getattr(self, "proposed", None),
            "grid": list(a.grid),
            "brain": self.last if not a.over else {**self.last, "choice": None},
            "nframes": 0,
            "frames": "",
        }
        out.update(self.settle)
        if full:
            out.update({"size": a.size, "seed": a.seed})
        return out

    def describe(self) -> dict[str, Any]:
        b = self.brain
        c = b.connectome
        pops = {k: [int(v[0]), len(v)] for k, v in c.populations.items() if "/" not in k}
        pre = np.asarray(c.pre)
        post = np.asarray(c.post)
        w = np.asarray(b.brain.weights, dtype=float)
        # Population of each neuron, to keep every pathway in the drawing: each population pair
        # gets its strongest synapses up to an even share, the rest go to the strongest overall.
        owner = np.empty(c.n, dtype=np.int32)
        names = sorted(pops, key=lambda k: pops[k][0])
        for i, k in enumerate(names):
            owner[pops[k][0]:pops[k][0] + pops[k][1]] = i
        pair = owner[pre] * len(names) + owner[post]
        mag = np.abs(w)
        kinds = np.unique(pair)
        share = EDGES // (2 * len(kinds))
        chosen = []
        pathways = []
        for k in kinds:
            idx = np.flatnonzero(pair == k)
            top = idx[np.argsort(-mag[idx])[:share]]
            chosen.append(top)
            pathways.append({"from": names[k // len(names)], "to": names[k % len(names)], "synapses": int(len(idx)),
                             "mean_abs": float(mag[idx].mean()), "max_abs": float(mag[idx].max())})
        chosen = np.concatenate(chosen)
        rest = np.setdiff1d(np.argpartition(-mag, EDGES)[:EDGES], chosen)
        rest = rest[np.argsort(-mag[rest])][: EDGES - len(chosen)]
        order = np.concatenate([chosen, rest])
        order = order[np.argsort(-mag[order])]
        # How strongly each input is wired in: summed |weight| of its outgoing synapses.
        sensory = np.asarray(c.populations["sensory"])
        reach = np.zeros(c.n)
        np.add.at(reach, pre, mag)
        reach = reach[sensory]
        reach = (255 * reach / max(reach.max(), 1e-12)).astype(np.uint8)
        d = b.describe()
        genes = d.get("genes", {})
        return {
            "format": "field",
            "name": self.name,
            "meta": self.meta,
            "neurons": int(c.n),
            "synapses": int(len(w)),
            "populations": pops,
            "layout": d["layout"],
            "retina": retina(self.size),
            "reach": base64.b64encode(reach.tobytes()).decode(),
            "pathways": pathways,
            "play": {"greedy": True, "learning": False, "reset": "every game",
                     "free_steps": genes.get("learning_free_steps"), "tolerance": genes.get("learning_tolerance"),
                     "temperature": genes.get("temperature"),
                     "working_memory_amplitude": genes.get("working_memory_amplitude")},
            "edges": {"pre": pre[order].tolist(), "post": post[order].tolist(), "w": np.round(w[order], 4).tolist()},
            "games": self.games,
        }

    def snapshot(self) -> dict[str, Any]:
        # Frozen: the brain is the shipped one; only the count of games lived is kept.
        if self.arena is not None and not self.arena.over:
            raise RuntimeError("snapshot between games only")
        return {"brain": None, "meta": {**self.meta, "games": self.games}}

    def handle_json(self, text: str) -> str:
        msg = json.loads(text)
        op = msg["op"]
        if op == "begin":
            return json.dumps(self.begin(msg.get("seed")))
        if op == "tick":
            return json.dumps(self.tick(msg["move"], msg.get("decided")))
        if op == "mode":
            self.sims = max(0, int(msg.get("sims", 0)))
            return json.dumps({"sims": self.sims})
        if op == "describe":
            return json.dumps(self.describe())
        if op == "snapshot":
            return json.dumps(self.snapshot())
        raise ValueError(f"unknown op {op}")
