"""The page's host for the what-where map: ``cadence.space.map.Map`` behind the page's messages.

The map is the brain's own state: a sheet of cells by code units whose settled activity is
carried from moment to moment. No list of things is given to it and none is kept here. A thing
enters the map at the moment a sense first reports it; the inventory is read off the map.

The page speaks to the host through ``handle``. Messages (JSON objects with a ``command``):

- ``describe``: the map's graph (its regions, which neurons hold what, the seat and the role
  each plays in the page's drawing of a brain), its cells and its kinds. Fills the buffers
  ``pre``, ``post``, ``weight``, ``bias`` and ``centers``.
- ``step``: one moment. ``{"seen": [[name, x, y], ...], "heard": [...], "felt": [...],
  "lit": "0101..." | [flag a cell] | null, "wave": bool, "learn": bool}``: what the camera reports this moment (nothing for
  a thing it does not see), the place a sound names, the place the arm's joint readings name
  (the page works it out from the readings: a program's step, not the brain's), and which of
  the map's cells the camera sees (the page's own rule for what the camera sees, at each cell's
  middle). Gives the inventory and fills ``activation`` (every neuron) and, with ``wave``, the
  settle sweep by sweep (``wave_frames``, ``wave_move``).
- ``things``: the inventory as it stands, with no moment.
- ``ask``: ``{"thing": name}``: where is it? ``Map.where_is``, a settle with the kind as cue.
- ``what``: ``{"point": [x, y]}``: what is there? ``Map.what_is_at``, a settle with the place as
  cue.
- ``reset``: the map emptied (``Map.reset``): it holds no thing.

Every call into the map is made in the methods of the first block below.
"""

from __future__ import annotations

import time
from typing import Any

import cadence
import numpy as np

KINDS = {"hand": 0, "own": 1, "apple": 2, "bread": 3}
TEACH_EVERY = 15  # with learned physics: the moments whose lessons are taught as one batch

# Where each region sits in the page's drawing of a brain seen from the side (front to the
# left), and the role it plays there: the centre (u, v) and the half size (w, h) of its box, in
# the drawing's own units. The page names the role; it claims nothing about what the neurons are.
SEATS: dict[str, dict[str, Any]] = {
    "map": {"role": "map", "label": "the map", "seat": [0.655, 0.27, 0.15, 0.19]},
    "reference": {"role": "attention", "label": "a question's kind", "seat": [0.835, 0.27, 0.012, 0.14]},
    "held": {"role": "recall", "label": "the map replayed for a question", "seat": [0.885, 0.55, 0.05, 0.075]},
    "doubt": {"role": "doubt", "label": "the cells of doubt", "seat": [0.66, 0.565, 0.075, 0.058]},
    "where": {"role": "placecells", "label": "where", "seat": [0.6, 0.72, 0.09, 0.055]},
    "what": {"role": "objects", "label": "what", "seat": [0.8, 0.705, 0.06, 0.012]},
    "clock": {"role": "timer", "label": "the moments since a sense wrote a cell", "seat": [0.80, 0.905, 0.075, 0.045]},
    "lost": {"role": "lost", "label": "a kind known with no place", "seat": [0.25, 0.66, 0.06, 0.012]},
}


class MapHost:
    """The what-where map, answering the page's requests."""

    kind = "map"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})
        self.buffers: dict[str, np.ndarray] = {}
        spec = self.config.get("map") or {}
        self.kinds = {str(k): int(v) for k, v in (spec.get("kinds") or KINDS).items()}
        self.names = {v: k for k, v in self.kinds.items()}
        self.label = str(spec.get("label") or "The what-where map")
        self.note = str(spec.get("note") or "")
        self.moments = 0
        # learned physics: the pack's settings, or the page's request (``physics``), where the
        # wheel has it; a map file that holds taught kernels brings them
        self.physics_settings = self.config.get("physics", spec.get("physics"))
        self.errors: list[float] = []  # each lesson batch's error, in order
        self._gathered = 0  # moments since the last batch of lessons was taught
        self._build(spec.get("path"))

    # -- every call into the map is made in the methods of this block

    def _build(self, path: str | None) -> None:
        from cadence.space.map import Map  # opt-in, imported by name

        began = time.perf_counter()
        # trace: a settle kept by sweep, for the brain view's wave; switched on for the moments
        # the page asks a wave of (a traced settle takes two sweeps in place of one)
        more = {"physics": self.physics_settings} if self.physics_settings else {}
        self.map = Map.load(path, trace=False, **more) if path else Map((-1.0, 1.0, -0.2, 1.4), trace=False, **more)
        self._traced = False
        self.load_ms = (time.perf_counter() - began) * 1000.0
        self.n = int(self.map.connectome.n)
        self.pre = np.asarray(self.map.connectome.pre, dtype=np.int64)
        self.post = np.asarray(self.map.connectome.post, dtype=np.int64)
        self.populations = {name: np.asarray(ids, dtype=np.int64) for name, ids in self.map.connectome.populations.items()}
        # Every neuron's settled potential, where the map's settle hands it back: the regions the
        # settle's record by sweep leaves out (clock, doubt, lost, held, reference) are drawn from it.
        self._v: np.ndarray | None = None
        settle = getattr(self.map, "_settle", None)
        if callable(settle):
            def watched(*args: Any, **kwargs: Any) -> Any:
                v = settle(*args, **kwargs)
                if np.ndim(v) == 1 and len(v) == self.n:
                    self._v = np.asarray(v, dtype=np.float64).copy()
                return v
            self.map._settle = watched

    def _moment(self, seen: list, heard: list, felt: list, lit: Any, trace: bool, learn: bool) -> float | None:
        """One moment. With learned physics and ``learn`` the moment gathers its lessons (a thing
        seen at this moment and at the one before), and every ``TEACH_EVERY`` moments the
        lessons gathered are taught as one batch, whose error is returned."""
        self.map.trace = self._traced = bool(trace)
        if self.physics is None:
            self.map.moment(seen=seen, heard=heard, felt=felt, lit=lit)
            return None
        self.map.moment(seen=seen, heard=heard, felt=felt, lit=lit, learn=learn)
        self._gathered += 1
        if not learn or self._gathered < TEACH_EVERY:
            return None
        self._gathered = 0
        before = int(self.physics.lessons)
        error = float(self.map.teach())
        return error if int(self.physics.lessons) > before else None

    @property
    def physics(self) -> Any:
        return getattr(self.map, "physics", None)

    def _motion(self) -> tuple[np.ndarray, np.ndarray] | None:
        """Each cell's velocity (metres a moment) and the share of its mass that moves."""
        if self.physics is None:
            return None
        velocity, share = self.map.motion()
        return np.asarray(velocity, dtype=np.float64).reshape(-1, 2), np.asarray(share, dtype=np.float64).ravel()

    def _kernels(self) -> dict[str, Any] | None:
        """What the physics learned: each velocity's kernel, the share of its mass that goes to
        each of the nine cells around (``OFFSETS``' order), and the velocities themselves."""
        physics = self.physics
        if physics is None:
            return None
        from cadence.space.physics import OFFSETS, PASS
        return {"velocities": np.asarray(physics.velocities, dtype=float).round(5).tolist(), "per": int(physics.per),
                "offsets": [list(o) for o in OFFSETS], "share": (np.asarray(physics.kernel) / PASS).round(4).tolist(),
                "lessons": int(physics.lessons)}

    def _things(self) -> list[dict[str, Any]]:
        return list(self.map.things())

    def _where_is(self, kind: int) -> np.ndarray:
        return np.asarray(self.map.where_is(kind), dtype=np.float64).reshape(-1, 2)

    def _what_is_at(self, point: Any) -> int | None:
        found = self.map.what_is_at(np.asarray(point, dtype=np.float64))
        return None if found is None else int(found)

    def _sheet(self, kind: int) -> np.ndarray:
        return np.asarray(self.map.sheet(kind), dtype=np.float64).ravel()

    def _reset(self) -> None:
        self.map.reset()
        self._v = None
        self._traced = False

    # -- what the page is given

    def _activity(self) -> np.ndarray:
        """Every neuron's activity above rest after the latest settle; the map's own record by
        sweep where it holds a region, the settled potentials for the rest."""
        out = np.zeros(self.n)
        if self._v is not None:
            out = np.maximum(np.tanh(self._v / 2.0), 0.0)
        trace = (getattr(self.map, "trajectory", None) or {}) if self._traced else {}
        for name in ("map", "where", "what"):
            if name in trace and name in self.populations:
                out[self.populations[name]] = np.asarray(trace[name])[-1].reshape(-1)
        return out

    def _wave(self, final: np.ndarray) -> dict[str, Any] | None:
        """The latest settle sweep by sweep, from the map's own record: the regions it keeps by
        sweep (``map``, ``where``, ``what``) at each sweep, the rest as they settled."""
        trace = (getattr(self.map, "trajectory", None) or {}) if self._traced else {}
        names = [name for name in ("map", "where", "what") if name in trace and name in self.populations]
        if not names:
            return None
        rows = int(np.asarray(trace[names[0]]).shape[0])
        frames = np.repeat(final[None], rows, axis=0)
        for name in names:
            frames[:, self.populations[name]] = np.asarray(trace[name]).reshape(rows, -1)
        if np.abs(frames[-1] - final).max() > 1e-9:
            return None
        move = np.abs(np.diff(frames, axis=0)).max(axis=1)
        self.buffers["wave_frames"] = np.ascontiguousarray(frames, dtype=np.float32).ravel()
        self.buffers["wave_move"] = move.astype(np.float32)
        return {"frames": rows, "sweeps": list(range(rows)), "of": rows - 1, "asked": trace.get("asked")}

    def _entry(self, e: dict[str, Any], sheets: dict[int, np.ndarray], motion: Any) -> dict[str, Any]:
        """One thing on the map, in few numbers: its name, place, cells with each one's activity
        (relative to the thing's most active cell, to four places), the sizes of its pieces
        where it lies in several, the moments since a sense wrote it and its state; with
        physics, the velocity its moving mass carries and the share of its mass that moves."""
        kind = int(e["kind"])
        cells = np.asarray(e.get("cells", []), dtype=np.int64)
        if kind not in sheets:
            sheets[kind] = self._sheet(kind)
        share = sheets[kind][cells]
        top = float(share.max()) if len(share) else 0.0
        out: dict[str, Any] = {"name": self.names.get(kind, f"kind {kind}"), "kind": kind,
                               "place": None if e.get("place") is None else [round(float(v), 5) for v in e["place"]],
                               "cells": cells.tolist(), "shares": (share / top).round(4).tolist() if top > 0 else [],
                               "since": None if e.get("since") is None else int(e["since"]), "state": str(e["state"])}
        pieces = e.get("pieces") or []
        if len(pieces) > 1:
            out["pieces"] = [len(p) for p in pieces]
        if motion is not None and len(cells):
            velocity, moving = motion
            weight = np.maximum(share, 0.0) * moving[cells]
            if weight.sum() > 0:  # the moving mass's velocity, over the thing's cells
                out["velocity"] = [round(float(v), 6) for v in (weight @ velocity[cells]) / weight.sum()]
            out["moving"] = round(float((np.maximum(share, 0.0) @ moving[cells]) / max(float(np.maximum(share, 0.0).sum()), 1e-300)), 4)
            units = np.flatnonzero(np.asarray(self.map.codes)[kind])
            mass = np.maximum(np.asarray(self.physics.mass)[cells][:, units, :], 0.0).sum(axis=(0, 1))
            if mass.sum() > 0:  # its moving mass by velocity, as shares
                out["by_velocity"] = (mass / mass.sum()).round(3).tolist()
        return out

    def inventory(self) -> list[dict[str, Any]]:
        sheets: dict[int, np.ndarray] = {}
        motion = self._motion()
        return [self._entry(e, sheets, motion) for e in self._things()]

    def _reports(self, rows: Any) -> list[tuple[int, np.ndarray]]:
        out = []
        for row in rows or []:
            name, x, y = row
            if str(name) in self.kinds:
                out.append((self.kinds[str(name)], np.array([float(x), float(y)])))
        return out

    # -- the page's messages

    def describe(self) -> dict[str, Any]:
        m = self.map
        nx, ny = (int(v) for v in m.cells)
        regions = []
        for name, ids in self.populations.items():
            seat = SEATS.get(name, {"role": "other", "label": name, "seat": [0.5, 0.5, 0.05, 0.05]})
            units = m.units if name in ("map", "held") else 1
            layout = ({"kind": "cells", "nx": nx, "ny": ny, "units": units} if len(ids) in (nx * ny, nx * ny * m.units)
                      else {"kind": "row", "units": len(ids)})
            regions.append({"name": name, "role": seat["role"], "label": seat["label"], "holds": seat["label"],
                            "layout": layout, "seat": seat["seat"], "neurons": ids.tolist()})
        self.buffers["pre"] = self.pre.astype(np.int32)
        self.buffers["post"] = self.post.astype(np.int32)
        self.buffers["weight"] = np.asarray(m.graph.efficacy, dtype=np.float32)
        self.buffers["bias"] = np.asarray(getattr(m.graph, "bias", np.zeros(self.n)), dtype=np.float32)
        self.buffers["centers"] = np.asarray(m.centers, dtype=np.float32).ravel()
        codes = np.asarray(m.codes)
        return {
            "cadence": cadence.__version__,
            "brain": {"kind": self.kind, "trained": False, "label": self.label, "note": self.note},
            "neurons": self.n, "synapses": len(self.pre), "regions": regions,
            "plane": [float(v) for v in m.plane], "cells": [nx, ny], "cell": [float(v) for v in m.size], "units": int(m.units),
            "kinds": self.kinds, "codes": {name: np.flatnonzero(codes[k]).tolist() for name, k in self.kinds.items() if k < len(codes)},
            "settings": {k: v for k, v in m.settings.items() if k != "physics"}, "load_ms": round(self.load_ms, 1), "moments": self.moments,
            "physics": None if self.physics is None else {**self.physics.settings(), "kernels": self._kernels()},
        }

    def step(self, msg: dict[str, Any]) -> dict[str, Any]:
        lit = msg.get("lit")  # one flag a cell: a string of 0s and 1s, or a list of flags
        if isinstance(lit, str):
            lit = np.frombuffer(lit.encode("ascii"), dtype=np.uint8) == ord("1")
        elif lit is not None:
            lit = np.asarray(lit, dtype=bool)
        began = time.perf_counter()
        wave = bool(msg.get("wave"))
        error = self._moment(self._reports(msg.get("seen")), self._reports(msg.get("heard")), self._reports(msg.get("felt")), lit,
                             trace=wave, learn=bool(msg.get("learn", True)))
        settle_ms = (time.perf_counter() - began) * 1000.0
        self.moments += 1
        things = self.inventory()
        final = self._activity()
        self.buffers["activation"] = final.astype(np.float32)
        out: dict[str, Any] = {"moment": self.moments, "things": things, "wave": self._wave(final) if wave else None,
                               "settle_ms": round(settle_ms, 2)}
        if self.physics is not None:
            if error is not None:
                self.errors.append(error)
            out["physics"] = {"lessons": int(self.physics.lessons), "error": None if error is None else round(error, 5),
                              "taught": error is not None}
            if error is not None and (len(self.errors) < 20 or len(self.errors) % 15 == 0):
                out["physics"]["kernels"] = self._kernels()
        out["ms"] = round((time.perf_counter() - began) * 1000.0, 2)
        return out

    def ask(self, name: str) -> dict[str, Any]:
        if name not in self.kinds:
            return {"name": name, "places": [], "asked": "where"}
        self.map.trace = self._traced = True  # a question is shown sweep by sweep
        places = self._where_is(self.kinds[name])
        final = self._activity()
        self.buffers["activation"] = final.astype(np.float32)
        return {"name": name, "places": places.tolist(), "asked": "where", "wave": self._wave(final),
                "entries": [e for e in self.inventory() if e["name"] == name]}

    def what(self, point: Any) -> dict[str, Any]:
        self.map.trace = self._traced = True
        kind = self._what_is_at(point)
        final = self._activity()
        self.buffers["activation"] = final.astype(np.float32)
        name = None if kind is None else self.names.get(kind, f"kind {kind}")
        return {"name": name, "point": [float(v) for v in point], "asked": "what", "wave": self._wave(final)}

    def reset(self) -> dict[str, Any]:
        self._reset()
        return {"reset": True, "things": self.inventory(), "moments": self.moments}

    def handle(self, msg: dict[str, Any]) -> dict[str, Any]:
        self.buffers = {}
        command = msg.get("command")
        if command == "describe":
            reply = self.describe()
        elif command == "step":
            reply = self.step(msg)
        elif command == "things":
            reply = {"things": self.inventory()}
        elif command == "ask":
            reply = self.ask(str(msg.get("thing")))
        elif command == "what":
            reply = self.what(msg["point"])
        elif command == "reset":
            reply = self.reset()
        else:
            reply = {"error": f"unknown command {command!r}"}
        reply["buffers"] = sorted(self.buffers)
        return reply
