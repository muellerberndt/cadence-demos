"""The page's host for the trained place module: ``cadence.space.Space`` behind the page's messages.

The page speaks to one host through ``handle`` (``describe``, ``step``, ``ask``, ``what``,
``reset``, ``reborn``; see ``host.py``). This host answers the same messages with a space of a
trained module (``cadence.load_module(path)`` or ``cadence.modules.load(name)``), and its replies
hold the same fields, so the page draws either brain.

What holds what, as the module is built:

- The space, a program beside the brain, holds each thing's place between moments: one row a
  thing. A camera's report of a thing writes its row. With no report, the row moves by what the
  brain answers.
- The brain answers three things for a row: how far its place moves in this step (``shift``),
  how far off the place may be (``spread``), and the place a cue or the joint readings name
  (``found``). It is asked only for the rows that hold information at a step.
- Reports and cues reach the space without names, as rows of a position (or a direction and a
  distance) and what the thing looks like: the hand 0, the kinds 1 and up. The space gives each
  to the nearest row of its look (``assign``, ``hear``).
- The sight evidence, where the library's space takes it (``observe(in_sight=)``). The page
  knows the camera, the pillar and the arm as they stand at each step. Where the space takes a
  function, the page gives one (``looks``: places in, one flag a place out: would the camera see
  a thing there?), and the space looks ahead with it: a thing that goes out of view while moving
  is carried no farther than the middle of its hidden stretch and waits there. Where the space
  takes flags alone, a step is taken in two halves: ``predict`` gives where every row is
  predicted to be, the page says for every row whether the camera would see a thing there, and
  ``observe`` is given that; a row predicted in sight for three steps in a row with no report
  is put halfway between where it was last seen and where it was before those steps, and rests.
  Where the space has the rule, a thing at rest whose own place is in sight with no report from
  there is marked gone (``state()["gone"]``): it is not where the map holds it, and the page
  says the brain does not know where it is. The space clears the mark when the thing is seen; a
  cue that names a place for it after the mark is shown as the heard place.

The module's ear stands where its interface says. A cue heard at the page's body is given to the
space as the direction and distance of the same point from the module's own ear.

This adapter is written against the first module system and place package and is expected to
change with them: every call into the space is made in one place below.
"""

from __future__ import annotations

import inspect
import time
from typing import Any

import numpy as np

import cadence

RATE = 0.9
AREA = float(np.sqrt(-2.0 * np.log(1.0 - RATE)))  # the radius of the area at RATE, in standard deviations
TOP_CHANGES = 480
WAVE_FRAMES = 12
# What the module was trained within; the page keeps a visitor's input inside it.
LIMITS = {"speed": 0.7, "command": 0.1, "unseen_moving": 100}
# The chamber's Kalman filter, fitted on a person's hand.
KALMAN = {"q": 3.16e-7, "r": 0.02}

# Where each region of the place brain sits in the page's drawing of a brain seen from the side,
# and the role it plays there. Seats are in the drawing's own units: the centre (u, v) and the
# half size (w, h) of the region's box. The roles are provisional until the module's own
# description of its regions replaces them.
SEATS: dict[str, dict[str, Any]] = {
    "place": {"role": "place", "label": "the held place, as the brain is given it", "seat": [0.66, 0.2, 0.095, 0.12]},
    "moved": {"role": "motor", "label": "the arm's command, as a copy", "seat": [0.35, 0.34, 0.035, 0.26]},
    "motion": {"role": "visual", "label": "the last seen movement", "seat": [0.865, 0.49, 0.07, 0.19]},
    "unseen": {"role": "timer", "label": "the moments since it was seen", "seat": [0.8, 0.9, 0.07, 0.03]},
    "heard": {"role": "auditory", "label": "a cue: its direction and distance", "seat": [0.73, 0.745, 0.06, 0.04]},
    "felt": {"role": "somatosensory", "label": "the arm's joint readings", "seat": [0.47, 0.34, 0.04, 0.26]},
    "hidden": {"role": "association", "label": "the hidden region", "seat": [0.655, 0.52, 0.085, 0.12]},
    "shift": {"role": "shift", "label": "how far the place moves in this step", "seat": [0.52, 0.2, 0.035, 0.12]},
    "spread": {"role": "doubt", "label": "how far off the place may be", "seat": [0.165, 0.43, 0.07, 0.12]},
    "found": {"role": "found", "label": "the place another sense names", "seat": [0.8, 0.2, 0.035, 0.12]},
    "keep": {"role": "keep", "label": "how much of its seen movement a thing keeps", "seat": [0.25, 0.2, 0.05, 0.035]},
}


def load_module(spec: dict[str, Any]) -> Any:
    """The module the pack names: from its file where the pack ships one, else by name from the
    wheel. A wheel without the module system is refused by name."""
    if spec.get("path"):
        loader = getattr(cadence, "load_module", None)
        if loader is None:
            raise RuntimeError(f"cadence {cadence.__version__} has no load_module; the pack ships a module file")
        return loader(spec["path"])
    modules = getattr(cadence, "modules", None)
    if modules is None:
        try:
            import cadence.modules as modules  # noqa: PLC0415  opt-in, imported by name
        except ImportError:
            modules = None
    if modules is None or not hasattr(modules, "load"):
        raise RuntimeError(f"cadence {cadence.__version__} has no modules.load; the pack names the module {spec.get('name')!r}")
    return modules.load(spec["name"])


class PlaceHost:
    """A space of a trained place module, answering the page's requests."""

    kind = "place"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})
        self.buffers: dict[str, np.ndarray] = {}
        self.module = load_module(self.config["module"])
        self._build()

    # -- every call into the space is made in the methods of this block

    def _build(self) -> None:
        from cadence.space import Space  # opt-in, imported by name

        began = time.perf_counter()
        slots = int(self.config.get("records", 12))
        # the page teaches as the space teaches itself, with no span of reports left unread; the
        # pack may state further settings of the space this module is run with (``space``).
        # ``joints`` among them says the module was raised with the arm's joint readings given,
        # as the chamber's setting of that name does: without it they are not passed.
        self.settings = dict(self.config["module"].get("space") or {})
        self.felt = bool(self.settings.pop("joints", False))
        self.space = Space.load(self.module, **{"track": True, "records": slots, "practice": 0.0, **self.settings})
        self.label = str(self.config["module"].get("label") or f"The {self.module.name} module")
        self.interface = self.space.interface
        self.brain = self.space.brain
        self.load_ms = (time.perf_counter() - began) * 1000.0
        # whether this library's space takes the caller's sight evidence (observe(in_sight=)),
        # and in which form: a function of places (the library took it in the commit that gave
        # ``advance`` the same argument), flags for the predicted places, or not at all
        takes = "in_sight" in inspect.signature(Space.observe).parameters
        self.sight: str | bool = False if not takes else (
            "function" if "in_sight" in inspect.signature(Space.advance).parameters else "flags")
        self.looks: Any = getattr(self, "looks", None)  # the page's function: places -> flags
        self.held: list[bool] = []  # the row was held back and rests on its hidden path
        self.was_live: list[bool] = []
        self.gone: list[bool] = []  # the row is not where the map holds it: its place is in sight, with no report
        self.named: list[bool] = []  # a cue named a place for the row after it was marked gone
        self.rules_gone = False  # the space states which rows are gone
        self._open: dict[str, Any] | None = None  # a step begun (predict) and not ended (observe)
        self.names: list[str] = []  # the page's name of each row; row 0 is the hand
        self.ever: list[bool] = []  # the row was seen or heard at least once
        self.source: list[str] = []
        self.latest: list[int] = []
        self.own = False
        self.moments = self.lessons = self.changed_total = self.refused = 0
        c = self.brain.brain.connectome
        self.n = int(c.n)
        self.pre = np.asarray(c.pre).astype(np.int64)
        self.post = np.asarray(c.post).astype(np.int64)

    def _begin(self, names: list[str], starts: np.ndarray, own: bool) -> None:
        looks = np.arange(len(names))
        self.space.begin(starts, own=np.array([own] + [False] * (len(names) - 1)), looks=looks)
        self.names, self.own = list(names), own
        self.ever = [bool(np.isfinite(p).all()) for p in starts]
        self.source = ["seen" if e else "" for e in self.ever]
        self.latest = [self.moments] * len(names)
        self.held = [False] * len(names)
        self.was_live = [False] * len(names)
        self.gone = [False] * len(names)
        self.named = [False] * len(names)

    def _predict(self, cue_rows: list[list[float]], commands: Any, joints: Any, learn: bool,
                 wave: bool = False) -> dict[str, Any]:
        """The first half of a step of the space: the cues to their rows and the brain's
        answers. Gives where every row is predicted to be, what the brain was given, its
        activation as it stood after its answers (one row a row it was asked for; a lesson that
        follows begins from rest and leaves none) and that settle's report. The activation may
        be of an earlier step where the brain was not asked at this one: ``state()['live']``
        says which rows it was asked for."""
        space = self.space
        cues = space.hear(np.array(cue_rows, dtype=np.float64)) if cue_rows else None
        given = np.array(space.sense(commands, cues, joints))
        predicted = np.asarray(space.predict(commands, cues, joints, learn=learn), dtype=np.float64)
        held = self.brain.basal_ganglia.state
        answered = None if held is None else np.array(held.activation, dtype=np.float64)
        settle = dict(self.brain.last_settlement or {})
        # the wave is replayed here, before a lesson of this step moves a synapse
        replay = self._wave(given, int(settle.get("steps", 0)), answered[0]) if wave and answered is not None and answered.ndim == 2 else None
        return {"cues": cues, "predicted": predicted, "given": given, "answered": answered, "settle": settle, "wave": replay}

    def _observe(self, half: dict[str, Any], report_rows: list[list[float]], learn: bool,
                 in_sight: Any = None) -> dict[str, Any]:
        """The second half: the reports to their rows and the places written. ``in_sight`` is
        the sight evidence of this step: True for the page's function (``looks``), or one flag
        a row for the predicted places; it is passed in the form the library's space takes.
        Gives which rows were seen and heard, how the evidence was given, and the flags of the
        predicted places."""
        space, cues = self.space, half["cues"]
        seen, z = space.assign(np.array(report_rows, dtype=np.float64).reshape(-1, 3))
        given: str | bool = False
        flags = None
        if self.sight == "function" and in_sight is True and self.looks is not None:
            looks = lambda points: np.asarray(self.looks(np.asarray(points, dtype=np.float64).reshape(-1, 2)), dtype=bool)  # noqa: E731
            flags = looks(half["predicted"])
            space.observe(seen, z, learn=learn, in_sight=looks)
            given = "function"
        elif self.sight and in_sight is not None and in_sight is not True and in_sight is not False:
            flags = np.asarray(in_sight, dtype=bool).reshape(space.rows)
            space.observe(seen, z, learn=learn, in_sight=flags)
            given = "flags"
        else:
            space.observe(seen, z, learn=learn)
        heard = np.zeros(space.rows, dtype=bool) if cues is None else np.isfinite(cues).all(axis=1)
        return {**half, "seen": np.asarray(seen, dtype=bool), "reports": np.asarray(z), "heard": heard, "sight": given, "flags": flags}

    def _wave(self, given: np.ndarray, steps: int, final: np.ndarray) -> dict[str, Any] | None:
        """The hand's answer, sweep by sweep: the brain settled again from rest under the same
        drive for the sweeps the answer took, every sweep kept. Nothing is sent where the last
        sweep is not the state the answer was read from."""
        if steps <= 0:
            return None
        drive = self.brain.stimulus(given[:1], memory=False)
        traj = np.asarray(self.brain.brain.settle_batch(drive, steps=steps, trajectory=True).trajectory)[:, 0]
        if np.abs(traj[-1] - final).max() > 1e-6:
            return None
        move = np.abs(np.diff(np.vstack([np.zeros_like(traj[0]), traj]), axis=0)).max(axis=1)
        # the sweeps in which a neuron moved, up to WAVE_FRAMES of them, and the last one
        moving = np.flatnonzero(move > 1e-7)
        if len(moving) > WAVE_FRAMES:
            moving = moving[np.unique(np.linspace(0, len(moving) - 1, WAVE_FRAMES).round().astype(int))]
        keep = np.unique(np.append(moving, steps - 1))
        self.buffers["wave_frames"] = np.ascontiguousarray(traj[keep], dtype=np.float32).ravel()
        self.buffers["wave_move"] = move.astype(np.float32)
        return {"sweeps": [int(v) + 1 for v in keep], "of": steps, "frames": int(len(keep))}

    def _where_is(self, row: int) -> tuple[np.ndarray, float] | None:
        """Where a kind of thing is, by the space's own answer for what the row looks like."""
        rows, places, radii = self.space.where_is(int(self.space.looks[row]))
        return (places[0], float(radii[0])) if len(rows) else None

    def _what_is_at(self, point: Any) -> int | None:
        """The row whose place holds a point, by the space's own answer."""
        found = self.space.what_is_at(np.asarray(point, dtype=np.float64))
        return None if found is None else int(found[0])

    def _where(self) -> tuple[np.ndarray, np.ndarray]:
        return self.space.where()

    def _cells(self) -> tuple[np.ndarray, list[float]] | None:
        """The hand's belief over the plane as a sheet of cells, where the space states one:
        ``(ny, nx)`` shares that sum to one, the first row the lowest y and each row from the
        lowest x, and the plane they cover. The page then draws the stated area as the cells
        that hold ``RATE`` of the belief, in place of a circle (``site/region.js``). The space
        of this module states a place and a circle and gives no sheet: this is the seam for a
        space that does, and the call into it comes with that space."""
        return None

    def _weights(self) -> np.ndarray:
        return np.asarray(self.brain.brain.efficacy, dtype=np.float64)

    # -- the page's messages

    def describe(self) -> dict[str, Any]:
        f, c = self.interface, self.brain.brain.connectome
        populations = c.populations
        x0, x1, y0, y1 = f.plane
        regions = []
        for name, size in f.regions.items():
            seat = SEATS[name]
            layout: dict[str, Any] = {"kind": "field"}
            if name == "place":
                layout = {"kind": "axes", "per": f.place, "ranges": [[x0, x1], [y0, y1]]}
            elif name in ("shift",):
                layout = {"kind": "axes", "per": f.shift, "ranges": [[-f.reach, f.reach]] * 2}
            elif name == "found":
                layout = {"kind": "axes", "per": f.found, "ranges": [[x0, x1], [y0, y1]]}
            elif name == "keep":
                layout = {"kind": "axes", "per": f.keep, "ranges": [[0.0, 1.0]]}
            elif name == "moved":
                layout = {"kind": "axes", "per": f.moved, "ranges": [[-f.command, f.command]] * f.joints}
            elif name == "heard":
                layout = {"kind": "grid", "width": f.heard[1], "height": f.heard[0]}
            elif name == "felt" and f.joints == 2:
                layout = {"kind": "grid", "width": f.felt, "height": f.felt}
            regions.append({"name": name, "role": seat["role"], "label": seat["label"], "holds": seat["label"],
                            "layout": layout, "seat": seat["seat"], "provisional": True,
                            "neurons": [int(i) for i in populations[name]]})
        self.buffers["pre"] = self.pre.astype(np.int32)
        self.buffers["post"] = self.post.astype(np.int32)
        self.buffers["weight"] = self._weights().astype(np.float32)
        self.buffers["bias"] = np.asarray(self.brain.brain.bias, dtype=np.float32)
        card = self.module.card
        centres = [np.linspace(x0, x1, f.place).tolist(), np.linspace(y0, y1, f.place).tolist()]
        return {
            "cadence": cadence.__version__,
            "brain": {"kind": self.kind, "trained": True, "label": self.label, "badge": self.config["module"].get("label"),
                      "note": str(self.config["module"].get("note") or card.get("note", "")), "module": self.module.name,
                      "library": self.module.record.get("library"), "card": card},
            "neurons": self.n, "synapses": int(len(self.pre)),
            "populations": {name: int(size) for name, size in f.regions.items()},
            "regions": regions,
            "place": {"kind": "axes", "bins": f.place, "plane": [x0, x1, y0, y1], "centres": centres, "rate": RATE},
            "records": {"capacity": int(self.space.records.capacity) if self.space.records is not None else 0,
                        "role": "hippocampus", "held": int(self.space.records.count) if self.space.records is not None else 0},
            "learning": {"temperature": float(f.temperature)},
            "ear": [float(v) for v in f.ear], "limits": dict(LIMITS), "controls": {"kalman": dict(KALMAN)},
            "sight": self.sight, "space": {**self.settings, **({"joints": True} if self.felt else {})},
            "compose_ms": round(self.load_ms, 1), "moments": self.moments, "lessons": self.lessons,
            "index_bits": int(np.dtype(np.intp).itemsize * 8),
        }

    def _cue(self, cue: Any, ear: np.ndarray) -> list[float]:
        """A cue heard at ``ear`` as the direction and distance of the same point from the
        module's own ear."""
        direction, distance = (float(v) for v in cue)
        point = ear + distance * np.array([np.cos(direction), np.sin(direction)])
        offset = point - np.asarray(self.interface.ear, dtype=np.float64)
        return [float(np.arctan2(offset[1], offset[0])), float(np.linalg.norm(offset))]

    def step(self, m: dict[str, Any]) -> dict[str, Any]:
        """One moment in one message: both halves, with the sight evidence the message holds
        (``in_sight``: True for the page's function, one flag a row, or none)."""
        self.begin(m)
        return self.end(m.get("in_sight"))

    def begin(self, m: dict[str, Any]) -> dict[str, Any]:
        """The first half of a moment: the cues and the brain's answers. Gives the predicted
        place of every row (the hand first, then the things in the message's order), for the
        page to say which of them the camera would see."""
        hand = (m.get("hand") or {}).get("report")
        things = m.get("things") or []
        names = ["hand", *[str(t["name"]) for t in things]]
        own = bool(m.get("own", False))
        given = [hand, *[t.get("report") for t in things]]
        if names != self.names or own != self.own:
            # new things, or another hand: the rows begin where the camera reports them; a row
            # with no report begins where its record holds it
            starts = np.array([[np.nan, np.nan] if p is None else p for p in given], dtype=np.float64)
            if self.names == names:  # the same things: every row keeps the place it holds
                held, _ = self._where()
                starts = np.where(np.isfinite(starts), starts, held)
                ever = list(self.ever)
                self._begin(names, starts, own)
                self.ever = ever
            else:
                self._begin(names, starts, own)
        body = m.get("body") or {}
        ear = np.asarray(body.get("position") or self.interface.ear, dtype=np.float64)
        report_rows = [[float(p[0]), float(p[1]), float(k)] for k, p in enumerate(given) if p is not None]
        cue_rows = [[*self._cue(t["cue"], ear), float(k)] for k, t in enumerate(things, start=1) if t.get("cue") is not None]
        learn = bool(m.get("teach", True))
        taught_before = self.space.work["lesson_row_sweeps"]
        began = time.perf_counter()
        self.moments += 1
        half = self._predict(cue_rows, m.get("commands") if own else None, m.get("joints") if own and self.felt else None,
                             learn, bool(m.get("wave")))
        self._open = {"half": half, "reports": report_rows, "learn": learn, "taught_before": taught_before,
                      "ms": (time.perf_counter() - began) * 1000.0}
        return {"moment": self.moments, "predicted": [[float(p[0]), float(p[1])] for p in half["predicted"]],
                "names": list(self.names), "own": own, "sight": self.sight}

    def end(self, in_sight: Any = None) -> dict[str, Any]:
        """The second half of the moment begun: the reports, the sight evidence and the places
        written. Gives the page's reply for the moment."""
        if self._open is None:
            raise RuntimeError("observe follows predict: no moment is open")
        opened, self._open = self._open, None
        learn, taught_before, rows = opened["learn"], opened["taught_before"], len(self.names)
        began = time.perf_counter()
        step = self._observe(opened["half"], opened["reports"], learn, in_sight)
        ms = opened["ms"] + (time.perf_counter() - began) * 1000.0
        seen, reports, cues, answered, settle = step["seen"], step["reports"], step["heard"], step["answered"], step["settle"]
        at, radius = self._where()
        state = self.space.state()
        live = np.asarray(state.get("live", np.zeros(rows, dtype=bool)))
        refused = np.asarray(state.get("refused", np.zeros(rows, dtype=bool)), dtype=bool)
        # a row that waits at the middle of its hidden stretch: the space keeps where the
        # stretch ends and that the row moves no more (its own notes, read here where it has them)
        ends, moving = getattr(self.space, "_exit", None), getattr(self.space, "_moving", None)
        waits = np.zeros(rows, dtype=bool) if ends is None or moving is None else (
            np.isfinite(np.asarray(ends)).all(axis=1) & ~np.asarray(moving, dtype=bool))
        for k in range(rows):
            if seen[k] or cues[k]:
                self.ever[k], self.latest[k] = True, self.moments
                self.source[k] = "seen" if seen[k] else "heard"
                self.held[k] = False
            elif refused[k] or (step["sight"] and (waits[k] or (self.was_live[k] and not live[k]))):
                # with the evidence given, a row that was moved while unseen and was put to
                # rest by it: it rests on its hidden path until it is seen or heard
                self.held[k] = True
            self.was_live[k] = bool(live[k]) and not (seen[k] or cues[k])
        # the rows the space marks gone: at rest, their own place in the camera's sight, no report
        # from there. The space clears the mark at a report; a cue after the mark names a place,
        # which the page shows as heard.
        self.rules_gone = "gone" in state
        marked = np.asarray(state.get("gone", np.zeros(rows, dtype=bool)), dtype=bool)
        for k in range(rows):
            self.named[k] = bool(marked[k]) and (self.named[k] or bool(cues[k]))
            self.gone[k] = bool(marked[k]) and not self.named[k]
        # the hand's row: its place, the radius of its area, and the brain as it was asked
        sd = float(radius[0]) / AREA
        activation = np.zeros(self.n)
        sweeps, residual, asked = 0, 0.0, bool(live[0]) if len(live) else False
        wave: dict[str, Any] | None = None
        index = {name: np.asarray(self.brain.brain.connectome.populations[name], dtype=np.int64) for name in self.interface.regions}
        for name in ("place", "moved", "motion", "unseen", "heard", "felt"):
            if name in state:
                activation[index[name]] = np.asarray(state[name])[0]
        if asked and answered is not None and answered.ndim == 2 and len(answered) == int(live.sum()):
            # the hand's row is the first of the rows the brain was asked for
            sweeps, residual = int(settle.get("steps", 0)), float(settle.get("max_residual") or 0.0)
            activation = answered[0].copy()
            wave = step["wave"]
        else:
            asked = False
        peak = np.asarray(state["place"])[0].reshape(2, self.interface.place) if "place" in state else np.zeros((2, self.interface.place))
        shares = peak / np.maximum(peak.sum(axis=1, keepdims=True), 1e-12)
        self.buffers["activation"] = activation.astype(np.float32)
        self.buffers["px"] = shares[0].astype(np.float32)
        self.buffers["py"] = shares[1].astype(np.float32)
        out: dict[str, Any] = {
            "moment": self.moments, "seen": bool(seen[0]), "asked": asked,
            "place": [float(at[0, 0]), float(at[0, 1])], "sd": [sd, sd], "radius": float(radius[0]),
            "area": float(np.pi * radius[0] ** 2), "since": int(np.asarray(state["since"])[0]),
            "sweeps": sweeps, "residual": residual, "tolerance": 0.0, "qualified": True, "refusals": self.refused,
            "wave": wave, "lesson": None, "held_back": bool(self.held[0]), "gone": bool(self.gone[0]),
            # the sight evidence of this moment: whether it was given, which predicted places the
            # camera would see, and which rows were held back at this moment
            "sight": {"given": step["sight"], "in_sight": None if step["flags"] is None else [bool(v) for v in step["flags"]],
                      "held_back": [bool(v) for v in self.held], "gone": list(self.gone) if self.rules_gone else None},
        }
        cells = self._cells()
        if cells is not None:
            sheet, plane = cells
            self.buffers["cells"] = np.ascontiguousarray(sheet, dtype=np.float32).ravel()
            out["cells"] = {"nx": int(sheet.shape[1]), "ny": int(sheet.shape[0]), "plane": [float(v) for v in plane], "rate": RATE}
        if learn and self.space.work["lesson_row_sweeps"] != taught_before and len(self.space.changed):
            delta, where = np.asarray(self.space.changes, dtype=np.float64), np.asarray(self.space.changed, dtype=np.int64)
            top = np.argsort(-np.abs(delta))[:TOP_CHANGES]
            self.lessons += 1
            self.changed_total += int(len(where))
            self.buffers["flash_index"] = where[top].astype(np.int32)
            self.buffers["flash_delta"] = delta[top].astype(np.float32)
            self.buffers["weight"] = self._weights().astype(np.float32)
            out["lesson"] = {"taught": True, "changed": int(len(where)), "largest": float(np.abs(delta).max()),
                             "mismatch": float(np.linalg.norm(at[0] - reports[0])) if seen[0] else 0.0}
        out["things"] = [self._thing(k, at, radius, bool(seen[k]), bool(cues[k])) for k in range(1, rows)]
        out.update({"lessons": self.lessons, "changed_total": self.changed_total, "act_ms": round(ms, 2),
                    "lesson_ms": 0.0, "ms": round(ms, 2)})
        return out

    def _thing(self, k: int, at: np.ndarray, radius: np.ndarray, seen: bool, heard: bool) -> dict[str, Any]:
        name = self.names[k]
        if not self.ever[k]:
            return {"name": name, "slot": -1, "source": "held", "write": False, "place": None}
        return {"name": name, "slot": k - 1, "source": "seen" if seen else "heard" if heard else "held",
                "write": bool(seen or heard), "revised": bool(seen or heard),
                "place": [float(at[k, 0]), float(at[k, 1])], "spread": float(radius[k]) / AREA,
                "from": self.source[k], "unseen": self.moments - self.latest[k], "stored": self.latest[k],
                "held_back": bool(self.held[k]), "gone": bool(self.gone[k])}

    def ask(self, name: str) -> dict[str, Any]:
        """Where is this kind of thing? The space's own answer for what it looks like."""
        if name not in self.names or not self.ever[self.names.index(name)]:
            return {"name": name, "slot": -1, "place": None, "asked": "where"}
        k = self.names.index(name)
        at, radius = self._where()
        held = self._where_is(k)
        if held is not None:
            at[k], radius[k] = held
        return {**self._thing(k, at, radius, False, False), "asked": "where"}

    def what(self, origin: Any, direction: float, tolerance: float = 0.45, point: Any = None) -> dict[str, Any]:
        """What is there? Given a point, the space's own answer for it. Else, or where it holds
        nothing there, the thing whose held place lies nearest the direction from the origin,
        within the tolerance."""
        origin = np.asarray(origin, dtype=np.float64)
        at, radius = self._where()
        if point is not None:
            row = self._what_is_at(point)
            if row is not None and row >= 1 and self.ever[row] and not self.gone[row]:
                return {**self._thing(row, at, radius, False, False), "gap": 0.0, "asked": "what", "by": "place"}
        best: tuple[float, int] | None = None
        for k in range(1, len(self.names)):
            if not self.ever[k] or self.gone[k]:  # a thing marked gone lies no way the brain knows
                continue
            offset = at[k] - origin
            turn = float(np.arctan2(offset[1], offset[0])) - float(direction)
            gap = abs(float(np.arctan2(np.sin(turn), np.cos(turn))))
            if gap <= tolerance and (best is None or gap < best[0]):
                best = (gap, k)
        if best is None:
            return {"name": None, "slot": -1, "place": None, "asked": "what"}
        return {**self._thing(best[1], at, radius, False, False), "gap": round(best[0], 4), "asked": "what", "by": "direction"}

    def reset(self) -> dict[str, Any]:
        self.names = []  # the next moment begins the rows anew
        self._open = None
        return {"reset": True, "moments": self.moments}

    def reborn(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        # the module as its file holds it: read again, since a loaded module keeps the brain it
        # made, and lessons on the page have moved that brain's synapses
        self.module = load_module(self.config["module"])
        self._build()
        return self.describe()

    def handle(self, m: dict[str, Any]) -> dict[str, Any]:
        command = m.get("command")
        if command != "observe":  # the second half of a moment keeps the first half's arrays (the wave)
            self.buffers = {}
        if command == "describe":
            reply = self.describe()
        elif command == "step":
            reply = self.step(m)
        elif command == "predict":
            reply = self.begin(m)
        elif command == "observe":
            reply = self.end(m.get("in_sight"))
        elif command == "ask":
            reply = self.ask(str(m.get("thing")))
        elif command == "what":
            reply = self.what(m["origin"], float(m["direction"]), float(m.get("tolerance", 0.45)), m.get("point"))
        elif command == "reset":
            reply = self.reset()
        elif command == "reborn":
            reply = self.reborn(m.get("config"))
        else:
            reply = {"error": f"unknown command {command!r}"}
        reply["buffers"] = sorted(self.buffers)
        return reply
