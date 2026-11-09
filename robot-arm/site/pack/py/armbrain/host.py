"""The arm page's brain host: the trained Cadence brain, frozen, answering one observation at a time.

The page owns the cell (MuJoCo in WebAssembly, ``site/sim.js``) and sends the brain its 262-value
observation; this host answers with the brain's command and everything the page draws of the
brain. The same class runs natively in the tests and in Pyodide in the page's worker.

Messages are JSON objects with a ``command``:

- ``describe``: populations (name, first neuron, size), the motor slots, the sensory layout, the
  population pairs that synapses join (count, mean |efficacy|) and the strongest synapses.
- ``reset``: the brain's moment state (its working memory) back to rest; the weights stay.
- ``act``: ``{"x": [262 floats]}``. ``Brain.act(x, greedy=True)``, the call the brain was read
  with in every trial. The answer: the four slot indices (dx, dy, dz, grip), the settle's sweeps
  and residual, every neuron's activation, the policy's slot probabilities, the working-memory
  trace, the signal on each population pair (sum of |efficacy x presynaptic activation|) and on
  the strongest synapses, and the milliseconds. A refused settle answers ``refused`` and no
  command; the page then holds, as the training cell's policy did.

Pyodide's numpy is 32-bit; ``fit_32_bit_numpy`` adapts the library's index casts at import and
changes nothing on 64 bits.
"""

from __future__ import annotations

import json
import sys
import time
import types
from pathlib import Path
from typing import Any

import numpy as np

import cadence


def fit_32_bit_numpy() -> bool:
    """Pyodide's numpy is 32-bit: its index type is int32, and numpy refuses to cast int64
    counts and indices to it under the safe rule. Every module of the library gets a numpy whose
    ``repeat``, ``bincount`` and ufunc ``reduceat`` cast those indices to the index type; every
    other name is numpy's own and the library's files are unchanged. Nothing changes on 64 bits."""
    if np.dtype(np.intp).itemsize >= 8:
        return False
    import cadence.sparse  # noqa: F401  imported lazily by the transport; shimmed here as well

    def cast(a: Any) -> np.ndarray:
        return np.asarray(a).astype(np.intp)

    class Ufunc:
        def __init__(self, ufunc: Any) -> None:
            self._ufunc = ufunc

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            return self._ufunc(*args, **kwargs)

        def reduceat(self, array: Any, indices: Any, axis: int = 0, dtype: Any = None, out: Any = None) -> Any:
            return self._ufunc.reduceat(array, cast(indices), axis, dtype, out)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._ufunc, name)

    shim = types.ModuleType("numpy")
    shim.__dict__.update(np.__dict__)
    shim.repeat = lambda a, repeats, axis=None: np.repeat(a, cast(repeats), axis=axis)
    shim.bincount = lambda x, weights=None, minlength=0: np.bincount(cast(x), weights=weights, minlength=minlength)
    for name in ("add", "maximum", "minimum", "multiply"):
        setattr(shim, name, Ufunc(getattr(np, name)))
    for name, module in list(sys.modules.items()):
        if (name == "cadence" or name.startswith("cadence.")) and getattr(module, "np", None) is np:
            module.np = shim
    return True


SHIMMED = fit_32_bit_numpy()

from cadence import Brain  # noqa: E402

ORDER = ("sensory", "module_0", "module_1", "association", "prefrontal", "motor")
LABELS = {"sensory": "Senses", "module_0": "Layer 1", "module_1": "Layer 2", "association": "Layer 3",
          "prefrontal": "Working memory", "motor": "Motor"}
SLOT_NAMES = ("dx", "dy", "dz", "grip")
TOP_PER_PAIR = 60


def _copy_state(state):
    """An owned copy of a ``BrainState`` (None before the first act)."""
    if state is None:
        return None
    from dataclasses import replace

    return replace(state, v=np.array(state.v), activation=np.array(state.activation),
                   adaptation=np.array(state.adaptation))


def _r(values: Any, digits: int = 4) -> list:
    return [round(float(v), digits) for v in np.asarray(values).ravel()]


class Host:
    def __init__(self, brain: str | Path, run: str | Path | None = None) -> None:
        self.brain = Brain.load(str(brain))
        self.run = json.loads(Path(run).read_text()) if run else {}
        c = self.brain.connectome
        self.populations = []
        for name in ORDER:
            members = np.asarray(c.populations[name])
            self.populations.append({"name": name, "label": LABELS[name], "start": int(members.min()), "size": int(len(members))})
        self.n = int(c.n)
        owner = np.empty(self.n, dtype=np.int64)
        for k, p in enumerate(self.populations):
            owner[p["start"]:p["start"] + p["size"]] = k
        self.pre = np.asarray(c.pre).astype(np.int64)
        self.post = np.asarray(c.post).astype(np.int64)
        self.efficacy = np.asarray(self.brain.basal_ganglia._free_brain.efficacy, dtype=float)
        pair = owner[self.pre] * len(ORDER) + owner[self.post]
        self.pairs = []
        self.pair_of = np.full(len(pair), -1, dtype=np.int64)
        top = []
        for code in np.unique(pair):
            idx = np.nonzero(pair == code)[0]
            k = len(self.pairs)
            self.pair_of[idx] = k
            src, dst = divmod(int(code), len(ORDER))
            self.pairs.append({"from": ORDER[src], "to": ORDER[dst], "synapses": int(len(idx)),
                               "mean_abs": round(float(np.abs(self.efficacy[idx]).mean()), 5)})
            strongest = idx[np.argsort(-np.abs(self.efficacy[idx]))[:TOP_PER_PAIR]]
            top.extend(int(i) for i in strongest)
        self.top = np.asarray(top, dtype=np.int64)
        self.slots = [int(s) for s in self.brain.learner.slot_sizes]
        self.decisions = 0

    def describe(self) -> dict[str, Any]:
        return {
            "cadence": cadence.__version__, "neurons": self.n, "synapses": int(len(self.pre)),
            "populations": self.populations, "slots": self.slots, "slot_names": list(SLOT_NAMES),
            "layout": self.run.get("layout"), "recipe": self.run.get("recipe"), "arm": self.run.get("arm"),
            "pairs": self.pairs,
            "top": {"pre": self.pre[self.top].tolist(), "post": self.post[self.top].tolist(), "efficacy": _r(self.efficacy[self.top], 5)},
            "shimmed_numpy": SHIMMED,
        }

    def reset(self) -> dict[str, Any]:
        self.brain.reset()
        self.decisions = 0
        return {"reset": True}

    def act(self, x: list[float], wave: bool = False) -> dict[str, Any]:
        """``Brain.act(x, greedy=True)``; with ``wave`` the reply also carries this decision's
        settle sweep by sweep (``_wave``), outside the measured ``ms``."""
        obs = np.asarray(x, dtype=float)[None]
        before = _copy_state(self.brain.basal_ganglia.state) if wave else None
        drive = self.brain.stimulus(obs) if before is not None else None
        began = time.perf_counter()
        try:
            answer = np.asarray(self.brain.act(obs, greedy=True))[0]
        except RuntimeError as error:
            return {"refused": True, "reason": str(error)[:160], "ms": round((time.perf_counter() - began) * 1000, 1)}
        ms = (time.perf_counter() - began) * 1000
        self.decisions += 1
        settle = self.brain.last_settlement or {}
        state = self.brain.basal_ganglia.state
        a = np.asarray(state.activation)
        a = a[0] if a.ndim == 2 else a
        try:
            p = np.asarray(self.brain.basal_ganglia.probabilities(state))
            p = p[0] if p.ndim == 3 else p
            probabilities = [_r(p[j, :size], 4) for j, size in enumerate(self.slots)]
        except (ValueError, RuntimeError, IndexError):
            probabilities = None
        message = np.abs(self.efficacy * a[self.pre])
        flows = np.bincount(self.pair_of, weights=message, minlength=len(self.pairs))
        trace = self.brain.working_memory.trace
        trace = None if trace is None else np.asarray(trace)
        trace = None if trace is None else (trace[0] if trace.ndim == 2 else trace)
        out_wave = None
        if before is not None:
            began = time.perf_counter()
            out_wave = self._wave(drive, before, settle, a)
            if out_wave is not None:
                out_wave["ms"] = round((time.perf_counter() - began) * 1000, 1)
        return {
            "wave": out_wave,
            "answer": [int(v) for v in answer], "ms": round(ms, 1), "decision": self.decisions,
            "sweeps": int(settle.get("steps", 0)), "residual": float(settle.get("max_residual") or 0.0),
            "activation": _r(a, 3), "probabilities": probabilities,
            "trace": None if trace is None else _r(trace, 3),
            "flows": _r(flows, 3), "top_messages": _r(self.efficacy[self.top] * a[self.pre[self.top]], 4),
        }

    def _wave(self, drive, before, settle, final) -> dict[str, Any] | None:
        """The decision's settle, sweep by sweep: the brain settled again from the state the act
        started from, under the same drive, for exactly the sweeps the act ran, every sweep
        recorded. The last sweep is the state the answer was read from (checked; nothing is sent
        when it differs or when the act's solve halved its step). Up to 16 sweeps are sent, with
        the largest change of any neuron at every sweep."""
        steps = int(settle.get("steps", 0))
        if steps <= 0 or settle.get("damping_halvings") or settle.get("rescue_steps"):
            return None
        traj = np.asarray(self.brain.brain.settle_batch(drive, steps=steps, state=before, tolerance=None,
                                                         trajectory=True).trajectory)[:, 0]
        if np.abs(traj[-1] - final).max() > 1e-9:
            return None
        keep = np.unique(np.linspace(0, steps - 1, min(16, steps)).round().astype(int))
        start = np.asarray(before.activation)[0]
        move = np.abs(np.diff(np.vstack([start, traj]), axis=0)).max(axis=1)
        return {"sweeps": [int(k) + 1 for k in keep], "of": steps, "move": _r(move, 5),
                "frames": [_r(traj[k], 3) for k in keep]}

    def handle(self, m: dict[str, Any]) -> dict[str, Any]:
        command = m.get("command")
        if command == "describe":
            return self.describe()
        if command == "reset":
            return self.reset()
        if command == "act":
            return self.act(m["x"], bool(m.get("wave", False)))
        return {"error": f"unknown command {command!r}"}
