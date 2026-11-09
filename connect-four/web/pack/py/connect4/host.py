"""The host the page's worker runs in Pyodide; the tests run the same file natively.

The brain's move on a board is its contract readout: the board encoded from the side to
move (its 42 stones, the opponent's 42 and the 42 playable cells), one memory-free settle of
the whole brain,

    state = brain.learner.free(brain.stimulus(x, memory=False))

and the strongest of the seven column neurons among the columns that still have room. A brain
with a verdict slot has three more motor neurons after the columns, its judgement of the
position for the side to move (loss, draw, win); the host reads them beside the move. The host runs that
same settle (the call ``Learner.free`` makes for this brain's configuration, from rest, at
the learner's sweep budget and tolerance) in chunks with its trajectory recorded, so the page
can draw every sweep while the next chunk is computed. Splitting the run into chunks changes
nothing: each chunk continues the previous chunk's potentials, and the stop rule (no
activation moved by the tolerance or more in a sweep) is checked on every sweep exactly as
in one call. ``check`` reads the contract itself with ``Learner.free`` for comparison.

Arrays for the page are kept in ``buffers`` (float32 or int32); every reply names the
buffers it filled so the worker can hand them over without a JSON detour.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import cadence
from cadence import Brain

from .game import COLUMNS, replay

FULL_BLOCK = 150_000  # a block with more synapses is drawn by its strongest few per neuron
SAMPLED_PER_NEURON = 8
TOP_CHANGES = 600  # the largest synaptic changes of a lesson that the page flashes
PAGE_ETA = 0.0033  # the step of a visitor's lesson (the bias steps a tenth of it)


def fit_32_bit_numpy() -> bool:
    """Adapt NumPy ``repeat``'s count dtype on 32-bit WASM; no model arithmetic changes.

    Pyodide's NumPy has a 32-bit ``intp``; a library call of ``np.repeat`` with int64 counts
    can refuse the cast there. The library's files stay unchanged: its learning module gets a
    NumPy whose ``repeat`` casts the counts. Nothing happens on a 64-bit NumPy.
    """
    if np.dtype(np.intp).itemsize >= 8:
        return False
    import types

    import cadence.learning as learning

    shim = types.ModuleType("numpy")
    shim.__dict__.update(np.__dict__)
    shim.repeat = lambda a, repeats, axis=None: np.repeat(
        a, np.asarray(repeats).astype(np.intp), axis=axis
    )
    learning.np = shim
    return True


def _round(values: Any, digits: int = 6) -> list:
    return [float(v) for v in np.round(np.asarray(values, dtype=float).ravel(), digits)]


def _strongest_legal(motor: np.ndarray, legal: np.ndarray) -> int:
    return int(np.argmax(np.where(legal, motor[:COLUMNS], -np.inf)))


def _verdict(motor: np.ndarray, temperature: float) -> list | None:
    """The verdict slot (the motor neurons after the seven columns) as a distribution over
    (loss, draw, win) for the side to move, at the learner's temperature; None without it."""
    if len(motor) < COLUMNS + 3:
        return None
    z = np.asarray(motor[COLUMNS:COLUMNS + 3], float) / float(temperature)
    p = np.exp(z - z.max())
    return _round(p / p.sum())


class Host:
    """One brain, loaded from its checkpoint, answering the page's requests."""

    def __init__(self, checkpoint: str, *, chunk: int = 12) -> None:
        self.checkpoint = str(checkpoint)
        self.chunk = int(chunk)
        self.shimmed = fit_32_bit_numpy()
        self.buffers: dict[str, np.ndarray] = {}
        self._load()

    # -- the brain

    def _load(self) -> None:
        began = time.perf_counter()
        self.brain = Brain.load(self.checkpoint, backend="cpu", precision="float64")
        # The visitor's lessons: only a column the brain does not already play is taught (the
        # surprise rule), at PAGE_ETA, so one lesson shows on the motor bars and a second
        # usually changes the move. The brain's own moves do not depend on either setting.
        from dataclasses import replace
        config = self.brain.learner.config
        self.trained_eta = float(config.eta)
        self.brain.retune(learning=replace(config, surprise=True, eta=PAGE_ETA, eta_bias=PAGE_ETA / 10))
        self.load_ms = (time.perf_counter() - began) * 1000.0
        self.planes = len(self.brain.sensory_index) // 42
        self.verdict_slot = len(self.brain.learner.output_index) >= COLUMNS + 3
        self.lessons = 0
        self.taught_changes = 0
        self.settle: dict[str, Any] | None = None
        self.settle_id = 0
        self._layout()
        # One settle on the empty board builds the graph's transport caches while the page is
        # loading, so the first move costs what every later move costs. It changes nothing.
        began = time.perf_counter()
        self.check([])
        self.warm_ms = (time.perf_counter() - began) * 1000.0

    def _layout(self) -> None:
        """Populations, synapse blocks and the synapses the page draws."""
        b = self.brain
        g = b.brain
        c = g.connectome
        grouped: dict[tuple[int, ...], list[str]] = {}
        for name, members in c.populations.items():
            if members:  # one set may carry two names, such as "motor" and "motor/actions"
                grouped.setdefault(tuple(members), []).append(name)
        populations = []
        for key, group in grouped.items():
            name = min(group, key=len)
            populations.append({"name": name, "aliases": [n for n in group if n != name],
                                "members": key})
        populations.sort(key=lambda p: p["members"][0])
        label = np.full(c.n, -1, dtype=np.int64)
        for k, p in enumerate(populations):
            label[list(p["members"])] = k
        self.populations = populations
        pre_pop, post_pop = label[c.pre], label[c.post]
        weights = np.asarray(g.weights)
        # A population that hears no synapse and holds no sensory neuron gets no drive in a
        # memory-free settle: it stays at rest and its synapses carry nothing (here the
        # prefrontal region, the working trace's target). Its blocks are drawn by their
        # strongest few synapses per neuron, like any block too large to draw whole.
        heard = set(post_pop.tolist())
        sensory = set(np.asarray(b.sensory_index).tolist())
        silent = {k for k, p in enumerate(populations)
                  if k not in heard and not sensory.intersection(p["members"])}
        self.silent = sorted(populations[k]["name"] for k in silent)
        blocks, drawn = [], []
        for a, z in sorted(set(zip(pre_pop.tolist(), post_pop.tolist()))):
            index = np.flatnonzero((pre_pop == a) & (post_pop == z))
            w = weights[index]
            if len(index) <= FULL_BLOCK and a not in silent:
                keep = index
            else:  # the strongest few inbound synapses of every postsynaptic neuron
                order = np.lexsort((-np.abs(w), c.post[index]))
                ranked = index[order]
                posts = c.post[ranked]
                starts = np.flatnonzero(np.r_[True, posts[1:] != posts[:-1]])
                counts = np.diff(np.r_[starts, len(ranked)]).astype(np.intp)  # 32-bit WASM
                rank = np.arange(len(ranked)) - np.repeat(starts, counts)
                keep = np.sort(ranked[rank < SAMPLED_PER_NEURON])
            drawn.append(keep)
            blocks.append({
                "pre": populations[a]["name"] if a >= 0 else "unnamed",
                "post": populations[z]["name"] if z >= 0 else "unnamed",
                "synapses": int(len(index)),
                "drawn": int(len(keep)),
                "sampled": bool(len(keep) < len(index)),
                "silent": bool(a in silent),
                "excitatory": int((w > 0).sum()),
                "inhibitory": int((w < 0).sum()),
                "mean_abs": float(np.abs(w).mean()) if len(w) else 0.0,
                "max_abs": float(np.abs(w).max()) if len(w) else 0.0,
            })
        self.blocks = blocks
        self.drawn = np.concatenate(drawn) if drawn else np.zeros(0, dtype=np.int64)
        position = np.full(c.synapses, -1, dtype=np.int64)
        position[self.drawn] = np.arange(len(self.drawn))
        self.drawn_position = position

    def describe(self) -> dict[str, Any]:
        b = self.brain
        g = b.brain
        c = g.connectome
        cfg = b.learner.config
        info = b.describe()
        memories = info.get("memories", {})
        genes = info.get("genes", {})
        self.buffers["pre"] = np.asarray(c.pre[self.drawn], dtype=np.int32)
        self.buffers["post"] = np.asarray(c.post[self.drawn], dtype=np.int32)
        self.buffers["weight"] = np.asarray(np.asarray(g.weights)[self.drawn], dtype=np.float32)
        self.buffers["bias"] = np.asarray(g.bias, dtype=np.float32)
        return {
            "cadence": cadence.__version__,
            "neurons": int(c.n),
            "synapses": int(c.synapses),
            "populations": [
                {"name": p["name"], "aliases": p["aliases"], "start": int(p["members"][0]),
                 "size": len(p["members"]),
                 "contiguous": p["members"][-1] - p["members"][0] + 1 == len(p["members"])}
                for p in self.populations
            ],
            "sensory": [int(i) for i in b.sensory_index],
            "motor": [int(i) for i in b.learner.output_index],
            "planes": self.planes,
            "verdict": self.verdict_slot,
            "temperature": float(cfg.temperature),
            "blocks": self.blocks,
            "drawn": int(len(self.drawn)),
            "silent": self.silent,
            "free_steps": int(cfg.free_steps),
            "tolerance": None if cfg.tolerance is None else float(cfg.tolerance),
            "surprise": bool(cfg.surprise),
            "page_eta": PAGE_ETA,
            "trained_eta": self.trained_eta,
            "neuron_model": g.neuron_model.to_dict(),
            "working_memory": memories.get("working_memory"),
            "working_memory_amplitude": genes.get("working_memory_amplitude"),
            "modules": info.get("layout", {}).get("modules"),
            "compose": self.compose_call(info),
            "load_ms": round(self.load_ms, 1),
            "warm_ms": round(self.warm_ms, 1),
            "lessons": self.lessons,
            "shimmed": self.shimmed,
        }

    @staticmethod
    def compose_call(info: dict[str, Any]) -> str:
        """The ``Brain.compose`` call this checkpoint's layout and genes describe."""
        layout = info.get("layout", {})
        composition = layout.get("composition", {})
        genes = info.get("genes", {})
        modules = tuple(layout.get("modules") or composition.get("modules") or ())
        parts = [str(layout.get("inputs", composition.get("inputs"))),
                 str(layout.get("actions", composition.get("actions"))),
                 f"modules={modules!r}"]
        actions = layout.get("actions", composition.get("actions"))
        if actions and int(actions) == COLUMNS + 3:
            parts.append("slots=(7, 3)")
        if genes.get("apical"):
            parts.append(f"apical={genes['apical']}")
        if "seed" in composition:
            parts.append(f"seed={composition['seed']}")
        if genes.get("teaching") not in (None, "custom"):
            parts.append(f"teaching={genes['teaching']!r}".replace("'", '"'))
        if "working_memory_amplitude" in genes:
            parts.append(f"working_memory_amplitude={genes['working_memory_amplitude']}")
        parts.append(f"episodic={'episodic' in info.get('memories', {})}")
        return f"Brain.compose({', '.join(parts)})"

    # -- requests

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        self.buffers = {}
        command = message.get("command")
        payload = message.get("payload") or {}
        if command == "init":
            reply = {"brain": self.describe(), "game": replay([]).summary()}
        elif command == "position":
            reply = {"game": replay(payload.get("moves", [])).summary()}
        elif command == "think":
            reply = self.think(payload.get("moves", []))
        elif command == "more":
            reply = self.more(payload.get("id"))
        elif command == "check":
            reply = self.check(payload.get("moves", []))
        elif command == "imagine":
            reply = self.imagine(payload.get("moves", []))
        elif command == "lesson":
            reply = self.lesson(payload.get("moves", []), payload.get("column"))
        elif command == "reset_brain":
            self._load()
            reply = {"brain": self.describe()}
        else:
            raise ValueError(f"unknown command {command!r}")
        reply["buffers"] = {name: {"dtype": "i4" if a.dtype == np.int32 else "f4",
                                   "shape": list(a.shape)} for name, a in self.buffers.items()}
        return reply

    # -- the brain's move, sweep by sweep

    def think(self, moves: list[int]) -> dict[str, Any]:
        game = replay(moves)
        if game.over:
            raise ValueError("the game is over")
        b = self.brain
        x = game.board.encode(self.planes)[None, :]
        drive = b.stimulus(x, memory=False)
        n = b.brain.connectome.n
        self.settle_id += 1
        self.settle = {
            "id": self.settle_id, "game": game, "drive": drive, "state": None, "sweeps": 0,
            "last": np.asarray(b.brain.neuron_model.activation(np.zeros((1, n))))[0],
            "movement": [], "compute": 0.0,
        }
        return self._advance()

    def more(self, settle_id: Any = None) -> dict[str, Any]:
        if self.settle is None or (settle_id is not None and settle_id != self.settle["id"]):
            raise ValueError("no settle is in progress")
        return self._advance()

    def _advance(self) -> dict[str, Any]:
        s = self.settle
        assert s is not None
        b = self.brain
        g = b.brain
        cfg = b.learner.config
        began = time.perf_counter()
        steps = min(self.chunk, cfg.free_steps - s["sweeps"])
        out = g.settle_batch(s["drive"], steps=steps, state=s["state"],
                             tolerance=cfg.tolerance, trajectory=True)
        frames = np.asarray(out.trajectory)[:, 0, :]
        movement, previous = [], s["last"]
        for frame in frames:
            movement.append(float(np.abs(frame - previous).max()))
            previous = frame
        s["last"], s["state"] = previous, out
        first = s["sweeps"]
        s["sweeps"] += int(out.steps)
        s["movement"] += movement
        s["compute"] += time.perf_counter() - began
        quiet = cfg.tolerance is not None and bool(movement) and movement[-1] < cfg.tolerance
        done = quiet or s["sweeps"] >= cfg.free_steps or int(out.steps) < steps
        self.buffers["frames"] = np.asarray(frames, dtype=np.float32)
        reply: dict[str, Any] = {
            "id": s["id"], "first": first, "sweeps": s["sweeps"], "done": done,
            "movement": _round(movement, 7), "ms": round(s["compute"] * 1000.0, 2),
        }
        if done:
            game = s["game"]
            outputs = s["last"][b.learner.output_index]
            motor = outputs[:COLUMNS]
            legal = game.board.legal()
            column = _strongest_legal(motor, legal)
            began = time.perf_counter()
            residual = float(np.asarray(g.residual(s["drive"], s["state"]))[0])
            s["compute"] += time.perf_counter() - began
            reply["final"] = {
                "column": column,
                "motor": _round(motor),
                "verdict": _verdict(outputs, cfg.temperature),
                "legal": [bool(v) for v in legal],
                "settled": quiet,
                "residual": round(residual, 7),
                "tolerance": cfg.tolerance,
                "budget": int(cfg.free_steps),
                "sweeps": s["sweeps"],
                "ms": round(s["compute"] * 1000.0, 2),
                "after": replay(list(game.moves) + [column]).summary(),
            }
            self.settle = None
        return reply

    def check(self, moves: list[int]) -> dict[str, Any]:
        """The contract readout on this position, read with ``Learner.free`` itself."""
        game = replay(moves)
        if game.over:
            raise ValueError("the game is over")
        b = self.brain
        began = time.perf_counter()
        state = b.learner.free(b.stimulus(game.board.encode(self.planes)[None, :], memory=False))
        outputs = np.asarray(state.activation)[0, b.learner.output_index]
        motor = outputs[:COLUMNS]
        return {"column": _strongest_legal(motor, game.board.legal()), "motor": _round(motor),
                "verdict": _verdict(outputs, b.learner.config.temperature),
                "sweeps": int(state.steps), "ms": round((time.perf_counter() - began) * 1000.0, 2)}

    # -- private imagination

    def imagine(self, moves: list[int]) -> dict[str, Any]:
        """Each candidate column's board, read from the opponent's seat, settled privately by
        ``Brain.imagine``: the reply the brain would make there. Nothing in the brain changes,
        and the brain's own move does not read these replies."""
        game = replay(moves)
        if game.over:
            raise ValueError("the game is over")
        b = self.brain
        cfg = b.learner.config
        candidates: list[dict[str, Any]] = []
        boards = []
        for column in np.flatnonzero(game.board.legal()).tolist():
            if game.board.winning(column):
                candidates.append({"column": column, "wins": True})
                continue
            after = game.board.play(column)
            if after.full():
                candidates.append({"column": column, "draw": True})
                continue
            boards.append((column, after))
        began = time.perf_counter()
        sweeps = 0
        if boards:
            # each phase settles to the learner's tolerance within the brain's sweep budget
            phases = b.imagine([np.stack([after.encode(self.planes) for _, after in boards])],
                               budget=int(cfg.free_steps))
            phase = phases[0]
            sweeps = int(phase.steps)
            outputs = np.asarray(phase.state.activation)[:, b.motor_index]
            for i, (column, after) in enumerate(boards):
                reply = _strongest_legal(outputs[i], after.legal())
                candidates.append({"column": column, "reply": reply, "motor": _round(outputs[i][:COLUMNS]),
                                   # the brain's verdict on that board, from the opponent's seat
                                   "verdict": _verdict(outputs[i], cfg.temperature),
                                   "qualified": bool(phase.qualified[i]),
                                   "reply_wins": bool(after.winning(reply))})
        candidates.sort(key=lambda item: item["column"])
        return {"candidates": candidates, "sweeps": sweeps,
                "ms": round((time.perf_counter() - began) * 1000.0, 2)}

    # -- a lesson from the visitor

    def lesson(self, moves: list[int], column: Any) -> dict[str, Any]:
        """One ``brain.lesson`` on the position with the visitor's column as its label."""
        game = replay(moves)
        if game.over:
            raise ValueError("the game is over")
        if column is None or not 0 <= int(column) < COLUMNS or not game.board.legal()[int(column)]:
            raise ValueError("a lesson needs a column with room")
        column = int(column)
        b = self.brain
        x = game.board.encode(self.planes)[None, :]
        legal = game.board.legal()
        before = self._motor(x)
        label = np.array([column])
        if self.verdict_slot:
            # the lesson names the column; the verdict slot is taught the judgement it holds now
            outputs = self._outputs(x)
            label = np.array([[column, int(np.argmax(outputs[COLUMNS:COLUMNS + 3]))]])
        g0 = b.brain
        w0, bias0 = np.asarray(g0.weights).copy(), np.asarray(g0.bias).copy()
        began = time.perf_counter()
        try:
            report = b.lesson(x, label)
        except (RuntimeError, cadence.LearningPhaseError) as error:
            return {"refused": str(error), "column": column, "lessons": self.lessons}
        ms = (time.perf_counter() - began) * 1000.0
        g1 = b.brain
        dw = np.asarray(g1.weights) - w0
        changed = np.flatnonzero(dw)
        accepted = float(report.get("accepted_presentations", 0.0)) > 0
        if accepted:
            self.lessons += 1
            self.taught_changes += int(len(changed))
        after = self._motor(x)
        top = changed[np.argsort(-np.abs(dw[changed]), kind="stable")]
        top = top[self.drawn_position[top] >= 0][:TOP_CHANGES]
        self.buffers["weight"] = np.asarray(np.asarray(g1.weights)[self.drawn], dtype=np.float32)
        self.buffers["bias"] = np.asarray(g1.bias, dtype=np.float32)
        self.buffers["changed"] = np.asarray(self.drawn_position[top], dtype=np.int32)
        self.buffers["delta"] = np.asarray(dw[top], dtype=np.float32)
        return {
            "column": column,
            "accepted": accepted,
            "changed": int(len(changed)),
            "max_change": float(np.abs(dw).max()) if len(dw) else 0.0,
            "bias_changed": int(np.count_nonzero(np.asarray(g1.bias) - bias0)),
            "before": _round(before),
            "after": _round(after),
            "choice_before": _strongest_legal(before, legal),
            "choice_after": _strongest_legal(after, legal),
            "sweeps": float(report.get("total_steps", 0.0)),
            "ms": round(ms, 2),
            "lessons": self.lessons,
        }

    def _outputs(self, x: np.ndarray) -> np.ndarray:
        b = self.brain
        state = b.learner.free(b.stimulus(x, memory=False))
        return np.asarray(state.activation)[0, b.learner.output_index]

    def _motor(self, x: np.ndarray) -> np.ndarray:
        return self._outputs(x)[:COLUMNS]
