"""The page's host: one cell, one head with its eyes, the scripted caregiver and, when the pack
carries one, the brain. The same class runs natively in the tests and in Pyodide in the page's
worker; the page sees nothing but this host's JSON answers.

Messages are JSON objects with an ``op``, one at a time:

- ``describe``: the brain's populations and slot layout, the head, the world's constants.
- ``moment``: one decision, ``{"driver": "caregiver" | "brain" | "shown" | "corrected" |
  "alone"}``. With a brain in the pack, every driver but ``caregiver`` runs one moment of
  ``arm.life.Life`` (``brain`` is ``alone``); without one, the caregiver drives. The answer
  carries the outcome, the executed commands, the caregiver's labels, the phase, the sweeps
  and milliseconds, and every physics frame of the decision for the page's animation.
- ``frames``: ``n`` physics frames without a decision, one frame payload each.
- ``retinas``: both eyes' current images, base64 uint8 of size by size.
- ``activity``: the brain's last settled state per population, base64 uint8, and the motor
  slots' probabilities under the policy.
- the visitor's changes: ``move_block``, ``move_bin``, ``set_load``, ``set_wear``, ``order``,
  ``erase_memory``, ``reset``; and ``snapshot`` / ``restore`` of the world.

A failed request answers ``{"error": ...}``. Pyodide's numpy is 32-bit; ``fit_32_bit_numpy``
below adapts the library's index casts at import and changes nothing on 64 bits.
"""

from __future__ import annotations

import base64
import json
import sys
import time
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

import cadence


def fit_32_bit_numpy() -> bool:
    """Pyodide's numpy is 32-bit: its index type is int32, and numpy refuses to cast int64
    counts and indices to it under the safe rule. The library sets up a learner with several
    slots by ``np.repeat(..., slot_sizes)`` on int64 sizes, sums the messages into neurons by
    ``np.add.reduceat`` on int64 segment starts, and counts tie-group members and synapses per
    neuron by ``np.bincount`` on int64 groups. Every module of the library gets a numpy whose
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

from . import caregiver  # noqa: E402
from .anatomy import EYE_SLOTS, MOTOR_SLOTS  # noqa: E402
from .eyes import BRIGHT, HAND_HALF, LAMP_RADIUS, LINK_RADIUS, Eyes, HeadSpec, render  # noqa: E402
from .life import Life  # noqa: E402
from .nursery import SLOT_NAMES  # noqa: E402
from .world import (  # noqa: E402
    BIN_HOME, BIN_SIDE, BLOCK, BODY_SENSES, HOVER, JOINTS, LAMP, ORDERS, POSITION_BINS, SPAWN_X, SPAWN_Y,
    TABLE_X, TABLE_Y, ArmSpec, World,
    steps_of,
)

DRIVERS = ("caregiver", "brain", "shown", "corrected", "alone")
MODES = {"brain": "alone", "shown": "shown", "corrected": "corrected", "alone": "alone"}
MAX_FRAMES = 600
LOG_KEPT = 100


def head_of(run: dict[str, Any] | None) -> HeadSpec:
    """The head the brain was raised with, from a run's ``run.json``; the founder head without."""
    h = (run or {}).get("head")
    if not h:
        return HeadSpec()
    bright = dict(BRIGHT)
    bright.update(h.get("bright") or {})
    return HeadSpec(size=int(h["size"]), eyes=int(h["eyes"]), baseline=float(h["baseline"]),
                    position=tuple(float(v) for v in h["position"]), target=tuple(float(v) for v in h["target"]),
                    fov=float(h["fov"]), change=bool(h.get("change", False)), colour=bool(h.get("colour", False)),
                    bright=bright)


def _round(values: Any, digits: int = 4) -> Any:
    a = np.asarray(values, dtype=float)
    if a.ndim == 0:
        return round(float(a), digits)
    return [_round(v, digits) for v in a]


def frame_of(world: World) -> dict[str, Any]:
    """One physics frame as the page draws it: angles, the links' points, the block, the bins,
    the lamps' order, the gripper and the counters."""
    points = world.points()
    return {
        "t": round(float(world.t), 4), "q": _round(world.q), "rest": _round(world.rest),
        "points": _round(points), "tip": _round(points[3]), "block": _round(world.block),
        "bins": {k: _round(v) for k, v in world.bins.items()}, "order": int(world.order),
        "closed": bool(world.closed), "holding": bool(world.holding),
        "load": float(world.load), "wear": float(world.wear),
        "decisions": int(world.decisions), "placed": int(world.placed), "wrong": int(world.wrong),
        "dropped": int(world.dropped),
    }


def b64(array: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(array).tobytes()).decode()


def grey8(image: np.ndarray) -> np.ndarray:
    return (np.clip(image, 0.0, 1.0) * 255).astype(np.uint8)


def activation8(a: np.ndarray) -> np.ndarray:
    """Activations in [-0.1, 1] as bytes, the Eyes demo's scale."""
    return np.clip(np.round((np.clip(a, -0.1, 1.0) + 0.1) / 1.1 * 255), 0, 255).astype(np.uint8)


@dataclass
class RecordingLife(Life):
    """A life whose decisions also record every physics frame, for the page's animation."""

    frames: list[dict[str, Any]] = field(default_factory=list)

    def _wait_frames(self):
        inner = super()._wait_frames()
        world, frames = self.world, self.frames

        def hook(frame_index: int) -> None:
            frames.append(frame_of(world))
            if inner is not None:
                inner(frame_index)

        return hook


class Host:
    def __init__(self, brain: str | Path | None = None, run: dict[str, Any] | None = None, seed: int = 0,
                 waits: int = 0) -> None:
        self.run = dict(run or {})
        self.head = head_of(self.run)
        self.seed = int(seed)
        self.waits = int(waits)
        self.world = World(ArmSpec(), self.seed)
        self.eyes = Eyes(self.head)
        self.brain: Brain | None = None if brain is None else Brain.load(brain)
        if self.brain is not None:
            self.brain.reset()
        self.life = self._life()
        self.last: dict[str, Any] | None = None
        self.moments = 0

    def _life(self) -> RecordingLife | None:
        if self.brain is None:
            return None
        return RecordingLife(self.brain, self.world, self.eyes, waits=self.waits)

    # -- what the page needs to know once

    def describe(self) -> dict[str, Any]:
        spec = self.world.spec
        head = self.head
        centre = self.eyes.cameras[0] if head.eyes == 1 else None
        cameras = [_round(c.eye) for c in self.eyes.cameras]
        out: dict[str, Any] = {
            "has_brain": self.brain is not None, "shimmed": SHIMMED, "cadence": cadence.__version__,
            "numpy": np.__version__, "drivers": list(DRIVERS),
            "head": {
                "size": head.size, "eyes": head.eyes, "baseline": head.baseline, "position": list(head.position),
                "target": list(head.target), "fov": head.fov, "change": head.change, "channels": head.channels,
                "cameras": cameras, "centre": _round(centre.eye) if centre is not None else _round(head.position),
            },
            "world": {
                "table_x": list(TABLE_X), "table_y": list(TABLE_Y), "block": BLOCK, "bin_side": BIN_SIDE,
                "bin_home": {k: list(v) for k, v in BIN_HOME.items()}, "lamp": {k: list(v) for k, v in LAMP.items()},
                "lamp_radius": LAMP_RADIUS, "spawn_x": list(SPAWN_X), "spawn_y": list(SPAWN_Y), "hover": HOVER,
                "joints": list(JOINTS), "orders": list(ORDERS), "position_bins": POSITION_BINS,
                "base_height": spec.base_height, "links": list(spec.links), "link_radius": list(LINK_RADIUS),
                "hand_half": HAND_HALF, "home": list(spec.home), "low": list(spec.low), "high": list(spec.high),
                "frames_per_decision": spec.frames_per_decision, "dt": spec.dt, "step": spec.step,
                "grasp_reach": spec.grasp_reach, "grasp_above": spec.grasp_above, "grasp_below": spec.grasp_below,
                "lift": caregiver.LIFT, "body_senses": BODY_SENSES,
            },
            "brain": None,
            "frame": frame_of(self.world),
        }
        if self.brain is not None:
            c = self.brain.connectome
            populations = {k: len(v) for k, v in c.populations.items()}
            sizes = [int(s) for s in self.brain.learner.slot_sizes]
            out["brain"] = {
                "neurons": int(c.n), "synapses": int(c.synapses), "populations": populations,
                "slots": sizes, "slot_names": list(SLOT_NAMES[:len(sizes)]),
                "eye_slots": len(EYE_SLOTS), "motor_slots": len(MOTOR_SLOTS),
                "memory": self.brain.hippocampus is not None, "arousal": self.brain.arousal is not None,
                "working_memory": self.brain.working_memory is not None,
                "layout": self._layout(populations),
                "run": {k: self.run.get(k) for k in ("seed", "lessons", "cadence") if k in self.run},
            }
        return out

    def _layout(self, populations: dict[str, int]) -> dict[str, Any]:
        """How the page tiles each population: the retinas and the body, V1's feature maps,
        the map's sheet, the dense regions. From the run's anatomy, checked against the sizes."""
        a = self.run.get("anatomy") or {}
        size, channels = int(a.get("size", self.head.size)), int(a.get("channels", self.head.channels))
        stages = a.get("stages") or [{"features": 8, "field": 5, "stride": 2}]
        side, v1 = size, None
        for st in stages:
            side = (side - int(st["field"])) // int(st["stride"]) + 1
            v1 = {"features": int(st["features"]), "side": side}
        sheet = int(a.get("sheet", 0) or 0)
        body = int(a.get("body", BODY_SENSES))
        if populations.get("sensory") != channels * size * size + body:
            size = channels = 0
        if v1 is not None and populations.get("visual/v1") != v1["features"] * v1["side"] ** 2:
            v1 = None
        if populations.get("visual/map") != sheet * sheet:
            sheet = 0
        return {"retina": {"channels": channels, "size": size}, "body": body, "v1": v1,
                "map": {"side": sheet} if sheet else None}

    # -- a decision and the frames between decisions

    def moment(self, driver: str = "caregiver") -> dict[str, Any]:
        if driver not in DRIVERS:
            raise ValueError(f"driver is one of {DRIVERS}, not {driver!r}")
        used = driver if (driver == "caregiver" or self.life is not None) else "caregiver"
        world = self.world
        target, _, phase = caregiver.plan(world)
        eye_labels = world.labels()
        start = time.perf_counter()
        if used == "caregiver":
            labels = caregiver.labels(world)
            frames: list[dict[str, Any]] = []
            outcome = world.decide_frames(steps_of(labels[:4]), labels[4],
                                          lambda _i: frames.append(frame_of(world)))
            row = {"mode": "caregiver", "taught": False, "refused": False, "own": None, "want": labels,
                   "disagreed": False, "event": outcome["event"], "reward": outcome["reward"],
                   "done": outcome["done"], "sweeps": 0, "ms": 0.0, "aroused": None}
            executed = labels
        else:
            assert self.life is not None
            mode = MODES[used]
            self.life.frames = frames = []
            row = self.life.moment(mode)
            del self.life.log[:-LOG_KEPT]
            executed = row["want"] if (mode == "shown" or row["own"] is None) else row["own"]
        if frames:
            frames[-1] = frame_of(world)  # the counters after the decision
        self.moments += 1
        self.last = {
            "driver": driver, "used": used, "mode": row["mode"], "phase": phase, "target": _round(target),
            "labels": [int(v) for v in row["want"]], "eye_labels": [int(v) for v in eye_labels],
            "commands": [int(steps_of([v])[0]) for v in executed[:4]] + [int(executed[4])],
            "own": None if row["own"] is None else [int(v) for v in row["own"]],
            "disagreed": bool(row["disagreed"]), "taught": bool(row["taught"]), "refused": bool(row["refused"]),
            "event": row["event"], "reward": float(row["reward"]), "done": bool(row["done"]),
            "sweeps": int(row["sweeps"]), "ms": float(row["ms"]), "aroused": row["aroused"],
            "host_ms": round((time.perf_counter() - start) * 1000, 1),
            "moments": self.moments, "frames": frames, "frame": frame_of(world),
        }
        return self.last

    def frames(self, n: int = 1) -> dict[str, Any]:
        n = int(np.clip(int(n), 1, MAX_FRAMES))
        out = []
        for _ in range(n):
            self.world.frame()
            out.append(frame_of(self.world))
        return {"n": n, "frames": out, "frame": out[-1]}

    # -- what the eyes and the brain hold

    def retinas(self) -> dict[str, Any]:
        images = [render(self.world, cam, self.head.bright) for cam in self.eyes.cameras]
        return {"size": self.head.size, "eyes": [b64(grey8(image)) for image in images],
                "labels": [int(v) for v in self.world.labels()]}

    def activity(self) -> dict[str, Any]:
        if self.brain is None:
            return {"populations": None, "motor": None, "note": "no brain in this pack"}
        state = self.brain.basal_ganglia.state
        if state is None:
            return {"populations": None, "motor": None, "note": "no settled state yet"}
        act = np.asarray(state.activation)
        act = act[0] if act.ndim == 2 else act
        populations = {name: b64(activation8(act[np.asarray(members)]))
                       for name, members in self.brain.connectome.populations.items()}
        sizes = [int(s) for s in self.brain.learner.slot_sizes]
        probabilities: list[list[float]] | None
        try:
            p = np.asarray(self.brain.basal_ganglia.probabilities(state))
            p = p[0] if p.ndim == 3 else p
            probabilities = [[round(float(v), 4) for v in p[j, :size]] for j, size in enumerate(sizes)]
        except (ValueError, RuntimeError, IndexError):
            probabilities = None
        last = self.last or {}
        labels = None
        if last.get("eye_labels") is not None and last.get("labels") is not None:
            labels = list(last["eye_labels"]) + list(last["labels"])
        return {
            "populations": populations,
            "motor": {"slots": sizes, "names": list(SLOT_NAMES[:len(sizes)]), "probabilities": probabilities,
                      "commands": last.get("commands"), "own": last.get("own"), "labels": labels,
                      "eye_slots": len(EYE_SLOTS)},
            "sweeps": last.get("sweeps"), "aroused": last.get("aroused"),
        }

    # -- the visitor's changes

    def erase_memory(self) -> dict[str, Any]:
        erased = False
        if self.brain is not None:
            for store in (self.brain.hippocampus, self.brain.context_memory):
                clear = getattr(store, "clear", None)
                if clear is not None:
                    clear()
                    erased = True
        return {"erased": erased, "frame": frame_of(self.world)}

    def reset(self, seed: int | None = None) -> dict[str, Any]:
        if seed is not None:
            self.seed = int(seed)
        self.world = World(ArmSpec(), self.seed)
        self.eyes.reset()
        if self.brain is not None:
            self.brain.reset()
        self.life = self._life()
        self.last = None
        self.moments = 0
        return {"frame": frame_of(self.world)}

    def _on_table(self, x: float, y: float) -> tuple[float, float]:
        return (float(np.clip(x, *TABLE_X)), float(np.clip(y, *TABLE_Y)))

    # -- the page's protocol

    def handle(self, m: dict[str, Any]) -> dict[str, Any]:
        op = m.get("op")
        world = self.world
        if op == "describe":
            return self.describe()
        if op == "moment":
            return self.moment(str(m.get("driver", "caregiver")))
        if op == "frames":
            return self.frames(int(m.get("n", 1)))
        if op == "frame":
            return {"frame": frame_of(world)}
        if op == "retinas":
            return self.retinas()
        if op == "activity":
            return self.activity()
        if op == "move_block":
            world.move_block(*self._on_table(float(m["x"]), float(m["y"])))
        elif op == "move_bin":
            name = str(m["name"])
            if name not in world.bins:
                raise ValueError(f"no bin {name!r}")
            world.move_bin(name, *self._on_table(float(m["x"]), float(m["y"])))
        elif op == "set_load":
            world.set_load(max(0.0, float(m.get("kg", 0.0))))
        elif op == "set_wear":
            world.set_wear(max(0.0, float(m.get("metres", 0.0))))
        elif op == "order":
            value = m.get("order", "new")
            if value == "new":
                world.new_order()
            elif value == "toggle":
                world.order = 2 if world.order == 1 else 1
            else:
                order = int(value)
                if order not in range(len(ORDERS)):
                    raise ValueError(f"order is 0, 1 or 2, not {order}")
                world.order = order
        elif op == "erase_memory":
            return self.erase_memory()
        elif op == "reset":
            return self.reset(m.get("seed"))
        elif op == "snapshot":
            return {"snapshot": world.snapshot()}
        elif op == "restore":
            world.restore(m["snapshot"])
            self.eyes.reset()
        else:
            raise ValueError(f"unknown op {op!r}")
        return {"ok": True, "frame": frame_of(world)}

    def handle_json(self, text: str) -> str:
        try:
            return json.dumps(self.handle(json.loads(text)))
        except Exception as error:  # noqa: BLE001  the page shows the message
            return json.dumps({"error": f"{type(error).__name__}: {error}"})
