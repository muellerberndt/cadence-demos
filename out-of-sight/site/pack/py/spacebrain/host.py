"""The page's brain host: one Cadence brain answering "where is the hand" at every moment.

The page owns the scene (``site/world.js``) and sends one message per moment of the scene: what
the camera reports of the hand (nothing while the hand is out of view), the arm's joint readings
and commands, and for every thing on the table what the camera reports of it or a heard cue. The
host answers with the brain's place for the hand, the spread of that answer, the place each
record holds for a thing, and everything the page draws of the brain: every neuron's activation,
the settle's sweeps and residual, the settle sweep by sweep, and the synapses a lesson changed.
The same class runs natively in the tests and in Pyodide in the page's worker.

Messages are JSON objects with a ``command``:

- ``describe``: the brain (kind, sizes, the call that composes it), its regions (which neurons
  hold what, and the anatomical role each plays on the page), the place answer's bins and the
  records' settings. Fills the buffers ``pre``, ``post``, ``weight`` and ``bias``.
- ``step``: one moment. ``{"hand": {"report": [x, y] | null}, "joints": [...], "commands":
  [...], "things": [{"name", "report": [x, y] | null, "cue": [direction, distance] | null}],
  "teach": bool, "wave": bool}``. A cue is what the ear hears of a thing that sounds: the
  direction to it and its distance from the ear. The brain acts on the moment (``Brain.act(x, greedy=True)``); where the hand
  is in view and ``teach`` is set, the place the camera reports is then taught as a lesson
  (``Brain.lesson``), so no lesson uses a position the camera did not give. A thing in view or
  heard writes its record; a thing out of view is read from its record.
- ``ask``: ``{"thing": name}``: reads the thing's record, crediting the read.
- ``reset``: the streams afresh (activity and working trace); weights and records stay.
- ``reborn``: a new brain and empty records.

This file's brain is the BASELINE: a plain composed brain (``Brain.compose``) whose inputs are
population codes (``PopulationCode``) of the camera's report, the joint readings and the arm's
commands, asked for the hand's place as two motor slots of bins (x and y), and raised on the page
from birth. It holds no place between moments beyond its working trace. The records are a
``LongTermMemory`` beside it, keyed by what a thing is, whose value is a population code of the
thing's place.
"""

from __future__ import annotations

import time
import zlib
from dataclasses import replace
from typing import Any

import numpy as np

import cadence
from cadence import Brain, LongTermMemory, PopulationCode

DEFAULTS: dict[str, Any] = {
    "plane": [-1.0, 1.0, -0.2, 1.4],  # x low, x high, y low, y high (metres)
    "limits": [[0.35, 2.79], [-2.6, -0.3]],  # the arm's joint limits (radians)
    "ear": [0.95, 1.35],  # where the ear stands: a cue is a direction and a distance from it
    "command": 0.25,  # the largest joint increment a step asks for (radians)
    "bins": 20,  # place bins per axis: the two motor slots
    "camera_per": 16,
    "joint_per": 12,
    "command_per": 9,
    "modules": [96],
    "temperature": 0.05,
    "seed": 0,
    "records": 12,  # slots of the records memory
    "record_per": 24,  # tuned units per axis of a record's place
    "key_width": 48,
}
TOP_CHANGES = 480  # the largest synaptic changes of a lesson that the page flashes
WAVE_FRAMES = 16
RECOGNISED = 0.9  # the cosine at which a read record is the thing asked for


def _copy_state(state: Any) -> Any:
    """An owned copy of a ``BrainState`` (None before the first act)."""
    if state is None:
        return None
    return replace(state, v=np.array(state.v), activation=np.array(state.activation),
                   adaptation=np.array(state.adaptation))


def decode(code: PopulationCode, response: np.ndarray) -> np.ndarray:
    """The readings a population code's response holds, one per reading: from the two most
    driven neighbouring units of each reading, whose log ratio is linear in the value. An empty
    response decodes to NaN."""
    rows = np.asarray(response, dtype=np.float64).reshape(len(code.ranges), code.per)
    out = np.full(len(code.ranges), np.nan)
    for r, row in enumerate(rows):
        i = int(np.argmax(row))
        if row[i] <= 0.0:
            continue
        left = row[i - 1] if i > 0 else 0.0
        right = row[i + 1] if i + 1 < code.per else 0.0
        j = i + 1 if right >= left else i - 1
        if not 0 <= j < code.per or row[j] <= 0.0:
            out[r] = code.preferred[r, i]
            continue
        s, pi, pj = code.spacing[r], code.preferred[r, i], code.preferred[r, j]
        # log r_i - log r_j = ((v - p_j)^2 - (v - p_i)^2) / (2 s^2)
        out[r] = (2.0 * s * s * (np.log(row[i]) - np.log(row[j])) + pi * pi - pj * pj) / (2.0 * (pi - pj))
    return out


class Host:
    """One brain and its records, answering the page's requests."""

    kind = "baseline"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = {**DEFAULTS, **(config or {})}
        self.buffers: dict[str, np.ndarray] = {}
        self._build()

    # -- the brain

    def _build(self) -> None:
        cfg = self.config
        x0, x1, y0, y1 = (float(v) for v in cfg["plane"])
        self.plane = (x0, x1, y0, y1)
        k = self.bins = int(cfg["bins"])
        self.centres = np.stack([np.linspace(x0, x1, k), np.linspace(y0, y1, k)])
        self.cell_area = ((x1 - x0) / (k - 1)) * ((y1 - y0) / (k - 1))
        self.camera = PopulationCode([(x0, x1), (y0, y1)], per=int(cfg["camera_per"]))
        limits = [(float(lo), float(hi)) for lo, hi in cfg["limits"]]
        self.joints = PopulationCode(limits, per=int(cfg["joint_per"]))
        c = float(cfg["command"])
        self.commands = PopulationCode([(-c, c)] * len(limits), per=int(cfg["command_per"]))
        self.layout: dict[str, tuple[int, int]] = {}
        at = 0
        for name, size in (("camera", self.camera.inputs), ("seen", 1), ("joints", self.joints.inputs),
                           ("commands", self.commands.inputs)):
            self.layout[name] = (at, size)
            at += size
        self.inputs = at
        began = time.perf_counter()
        self.brain = Brain.compose(
            inputs=self.inputs, actions=2 * k, slots=2, modules=tuple(int(m) for m in cfg["modules"]),
            seed=int(cfg["seed"]), backend="cpu", recall=False, temperature=float(cfg["temperature"]),
        )
        self.compose_call = (
            f"Brain.compose(inputs={self.inputs}, actions={2 * k}, slots=2, "
            f"modules={tuple(int(m) for m in cfg['modules'])!r}, seed={int(cfg['seed'])}, "
            f"recall=False, temperature={float(cfg['temperature'])})"
        )
        self.compose_ms = (time.perf_counter() - began) * 1000.0
        self.record_code = PopulationCode([(x0, x1), (y0, y1)], per=int(cfg["record_per"]))
        self.records = LongTermMemory(
            width=int(cfg["key_width"]), value_width=self.record_code.inputs,
            capacity=int(cfg["records"]), cosine=True, revise=RECOGNISED, seed=int(cfg["seed"]),
        )
        self.record_meta: dict[int, dict[str, Any]] = {}  # slot -> what it stored and when
        self.keys: dict[str, np.ndarray] = {}
        self.moments = 0
        self.lessons = 0
        self.changed_total = 0
        self.refused = 0
        self.agreed = 0
        g = self.brain.brain
        c = g.connectome
        self.n = int(c.n)
        self.pre = np.asarray(c.pre).astype(np.int64)
        self.post = np.asarray(c.post).astype(np.int64)
        self.sensory = np.asarray(self.brain.sensory_index).astype(np.int64)
        self.motor = np.asarray(self.brain.learner.output_index).astype(np.int64)

    def _weights(self) -> np.ndarray:
        return np.asarray(self.brain.brain.weights, dtype=np.float64)

    def _regions(self) -> list[dict[str, Any]]:
        """Which neurons hold what. ``role`` names the part of an animal's brain whose role the
        region plays on the page; it claims nothing about what the neurons are."""
        c = self.brain.brain.connectome
        x0, x1, y0, y1 = self.plane
        k = self.bins
        out: list[dict[str, Any]] = []

        def sensory(name: str, role: str, label: str, holds: str, layout: dict[str, Any]) -> None:
            start, size = self.layout[name]
            out.append({"name": name, "role": role, "label": label, "holds": holds, "layout": layout,
                        "neurons": [int(i) for i in self.sensory[start:start + size]]})

        sensory("camera", "visual", "the camera's report",
                "Where the camera sees the hand: 16 tuned inputs for x and 16 for y. Dark while the hand is out of view.",
                {"kind": "axes", "per": self.camera.per, "ranges": [[x0, x1], [y0, y1]]})
        sensory("seen", "visual", "in view",
                "One input: on while the camera sees the hand.", {"kind": "point"})
        sensory("joints", "somatosensory", "the arm's joint readings",
                "The arm's own joint angles, 12 tuned inputs a joint.",
                {"kind": "axes", "per": self.joints.per, "ranges": [list(r) for r in self.joints.ranges]})
        sensory("commands", "motor", "the arm's commands, as a copy",
                "The joint increments asked of the arm at this moment, 9 tuned inputs a joint: the copy of the command the brain is given.",
                {"kind": "axes", "per": self.commands.per, "ranges": [list(r) for r in self.commands.ranges]})
        for name, role, label, holds in (
            ("association", "association", "association",
             "Reciprocal with the place answer: where the settle agrees on a place."),
            ("prefrontal", "prefrontal", "working trace",
             "The trace of the last moment's interpretation, carried into this one."),
        ):
            members = c.populations.get(name)
            if members:
                out.append({"name": name, "role": role, "label": label, "holds": holds,
                            "layout": {"kind": "field"}, "neurons": [int(i) for i in members]})
        out.append({"name": "place", "role": "place", "label": "the place answer",
                    "holds": f"Where the brain says the hand is: {k} neurons for x and {k} for y, each axis read as one softmax.",
                    "layout": {"kind": "axes", "per": k, "ranges": [[x0, x1], [y0, y1]]},
                    "neurons": [int(i) for i in self.motor]})
        return out

    def describe(self) -> dict[str, Any]:
        b = self.brain
        g = b.brain
        c = g.connectome
        cfg = b.learner.config
        self.buffers["pre"] = self.pre.astype(np.int32)
        self.buffers["post"] = self.post.astype(np.int32)
        self.buffers["weight"] = self._weights().astype(np.float32)
        self.buffers["bias"] = np.asarray(g.bias, dtype=np.float32)
        return {
            "cadence": cadence.__version__,
            "brain": {
                "kind": self.kind, "trained": False,
                "label": "Untrained baseline",
                "note": "A plain composed brain, raised on this page from birth. It reads the camera, the "
                        "arm's joints and commands, and is asked for the hand's place. It holds no place "
                        "map between moments beyond its working trace.",
                "compose": self.compose_call,
            },
            "neurons": self.n,
            "synapses": int(c.synapses),
            "populations": {name: len(members) for name, members in c.populations.items() if members},
            "regions": self._regions(),
            "place": {"kind": "axes", "bins": self.bins, "plane": list(self.plane),
                      "centres": [self.centres[0].tolist(), self.centres[1].tolist()],
                      "rate": 0.9},
            "records": {"capacity": int(self.records.capacity), "role": "hippocampus",
                        "key_width": int(self.config["key_width"]),
                        "value": {"per": self.record_code.per, "plane": list(self.plane)},
                        "revise": RECOGNISED, "held": int(self.records.count)},
            "learning": {"free_steps": int(cfg.free_steps), "nudged_steps": int(cfg.nudged_steps),
                         "tolerance": None if cfg.tolerance is None else float(cfg.tolerance),
                         "surprise": bool(cfg.surprise), "eta": float(cfg.eta),
                         "temperature": float(cfg.temperature)},
            "compose_ms": round(self.compose_ms, 1),
            "moments": self.moments, "lessons": self.lessons,
            "index_bits": int(np.dtype(np.intp).itemsize * 8),
        }

    # -- one moment

    def observation(self, report: Any, joints: Any, commands: Any) -> np.ndarray:
        x = np.zeros((1, self.inputs))
        if report is not None:
            start, size = self.layout["camera"]
            x[0, start:start + size] = self.camera(np.asarray(report, dtype=np.float64))[0]
            x[0, self.layout["seen"][0]] = 1.0
        start, size = self.layout["joints"]
        x[0, start:start + size] = self.joints(np.asarray(joints, dtype=np.float64))[0]
        start, size = self.layout["commands"]
        if commands is None:
            commands = np.zeros(len(self.commands.ranges))
        x[0, start:start + size] = self.commands(np.asarray(commands, dtype=np.float64))[0]
        return x

    def label(self, report: Any) -> np.ndarray:
        p = np.asarray(report, dtype=np.float64)
        return np.array([[int(np.abs(self.centres[a] - p[a]).argmin()) for a in range(2)]])

    def step(self, m: dict[str, Any]) -> dict[str, Any]:
        hand = m.get("hand") or {}
        report = hand.get("report")
        x = self.observation(report, m["joints"], m.get("commands"))
        b = self.brain
        want_wave = bool(m.get("wave"))
        before = _copy_state(b.basal_ganglia.state) if want_wave else None
        drive = np.array(b.stimulus(x)) if before is not None else None
        began = time.perf_counter()
        self.moments += 1
        out: dict[str, Any] = {"moment": self.moments, "seen": report is not None}
        try:
            b.act(x, greedy=True)
        except RuntimeError as error:
            # a settle that finds no qualified state gives no answer: counted and shown
            self.refused += 1
            out.update({"refused": True, "reason": str(error)[:200], "refusals": self.refused,
                        "ms": round((time.perf_counter() - began) * 1000.0, 2)})
            out["things"] = self._things(m.get("things") or [])
            return out
        act_ms = (time.perf_counter() - began) * 1000.0
        settle = b.last_settlement or {}
        state = b.basal_ganglia.state
        a = np.asarray(state.activation, dtype=np.float64)
        a = a[0] if a.ndim == 2 else a
        p = np.asarray(b.basal_ganglia.probabilities(state), dtype=np.float64)
        p = p[0] if p.ndim == 3 else p
        mean = (p * self.centres).sum(axis=1)
        sd = np.sqrt((p * (self.centres - mean[:, None]) ** 2).sum(axis=1))
        # the area that holds the stated rate: the most likely cells of the x-by-y answer
        joint = np.sort(np.outer(p[1], p[0]).ravel())[::-1]
        cells = int(np.searchsorted(np.cumsum(joint), 0.9) + 1)
        self.buffers["activation"] = a.astype(np.float32)
        self.buffers["px"] = p[0].astype(np.float32)
        self.buffers["py"] = p[1].astype(np.float32)
        out.update({
            "place": [float(mean[0]), float(mean[1])], "sd": [float(sd[0]), float(sd[1])],
            "area": float(cells * self.cell_area), "cells": cells,
            "sweeps": int(settle.get("steps", 0)),
            "residual": float(settle.get("max_residual") or 0.0),
            "tolerance": float(settle.get("tolerance") or 0.0),
            "qualified": bool(settle.get("qualified", True)),
            "refusals": self.refused,
        })
        if before is not None:
            wave_began = time.perf_counter()
            wave = self._wave(drive, before, settle, a)
            if wave is not None:
                wave["ms"] = round((time.perf_counter() - wave_began) * 1000.0, 2)
            out["wave"] = wave
        # the lesson: only at a moment the camera gives the place
        out["lesson"] = None
        lesson_ms = 0.0
        if report is not None and m.get("teach", True):
            lesson_began = time.perf_counter()
            out["lesson"] = self._lesson(x, report, mean)
            lesson_ms = (time.perf_counter() - lesson_began) * 1000.0
        out["things"] = self._things(m.get("things") or [])
        out["lessons"] = self.lessons
        out["changed_total"] = self.changed_total
        out["act_ms"] = round(act_ms, 2)
        out["lesson_ms"] = round(lesson_ms, 2)
        out["ms"] = round((time.perf_counter() - began) * 1000.0, 2)
        return out

    def _lesson(self, x: np.ndarray, report: Any, answered: np.ndarray) -> dict[str, Any]:
        """Teach the place the camera reports; return what the lesson changed."""
        b = self.brain
        w0 = self._weights().copy()
        mismatch = float(np.linalg.norm(answered - np.asarray(report, dtype=np.float64)))
        try:
            report_ = b.lesson(x, self.label(report))
        except (RuntimeError, ValueError) as error:  # a refused phase leaves the brain as it was
            return {"refused": True, "reason": str(error)[:200], "changed": 0, "mismatch": mismatch}
        delta = self._weights() - w0
        changed = np.flatnonzero(delta)
        taught = len(changed) > 0
        if taught:
            self.lessons += 1
            self.changed_total += int(len(changed))
            top = changed[np.argsort(-np.abs(delta[changed]))[:TOP_CHANGES]]
            self.buffers["flash_index"] = top.astype(np.int32)
            self.buffers["flash_delta"] = delta[top].astype(np.float32)
            self.buffers["weight"] = self._weights().astype(np.float32)
        else:
            self.agreed += 1
        return {"changed": int(len(changed)), "taught": taught, "mismatch": mismatch,
                "largest": float(np.abs(delta).max()) if taught else 0.0,
                "agreed": int(report_.get("agreed_presentations", 0)) if isinstance(report_, dict) else 0}

    def _wave(self, drive: Any, before: Any, settle: dict[str, Any], final: np.ndarray) -> dict[str, Any] | None:
        """The moment's settle, sweep by sweep: the brain settled again from the state the act
        started from, under the same drive, for exactly the sweeps the act ran, every sweep
        recorded. The last sweep is the state the answer was read from (checked; nothing is sent
        when it differs or when the act's solve halved its step). Up to 16 sweeps are sent, with
        the largest change of any neuron at every sweep."""
        steps = int(settle.get("steps", 0))
        if steps <= 0 or settle.get("damping_halvings") or settle.get("rescue_steps"):
            return None
        solved = self.brain.brain.settle_batch(drive, steps=steps, state=before, tolerance=None, trajectory=True)
        traj = np.asarray(solved.trajectory)[:, 0]
        if np.abs(traj[-1] - final).max() > 1e-9:
            return None
        keep = np.unique(np.linspace(0, steps - 1, min(WAVE_FRAMES, steps)).round().astype(int))
        start = np.asarray(before.activation)[0]
        move = np.abs(np.diff(np.vstack([start, traj]), axis=0)).max(axis=1)
        self.buffers["wave_frames"] = np.ascontiguousarray(traj[keep], dtype=np.float32).ravel()
        self.buffers["wave_move"] = move.astype(np.float32)
        return {"sweeps": [int(v) + 1 for v in keep], "of": steps, "frames": int(len(keep))}

    # -- the records: where each thing was last seen or heard

    def key(self, name: str) -> np.ndarray:
        """A thing's identity as a fixed unit key, drawn once from its name."""
        if name not in self.keys:
            rng = np.random.default_rng(zlib.crc32(name.encode("utf-8")))
            key = rng.standard_normal(int(self.config["key_width"]))
            self.keys[name] = key / np.linalg.norm(key)
        return self.keys[name]

    def heard(self, cue: Any) -> np.ndarray:
        """The point a cue names: its distance from the ear along its direction."""
        direction, distance = (float(v) for v in cue)
        ear = np.asarray(self.config["ear"], dtype=np.float64)
        return ear + distance * np.array([np.cos(direction), np.sin(direction)])

    def _held(self, name: str, credit: bool) -> tuple[int, np.ndarray | None, float]:
        """The slot and the place a thing's record holds (-1 and None where no record is it)."""
        if self.records.count == 0:
            return -1, None, 0.0
        key = self.key(name)
        read = self.records.read(key, credit=credit)
        slot = int(read.first())
        if slot < 0:
            return -1, None, 0.0
        held = np.asarray(self.records.keys[slot], dtype=np.float64)
        cosine = float(held @ key / max(np.linalg.norm(held), 1e-12))
        if cosine < RECOGNISED:
            return -1, None, cosine
        return slot, decode(self.record_code, np.asarray(self.records.value(read))), cosine

    def _things(self, things: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for thing in things:
            name = str(thing["name"])
            report, cue = thing.get("report"), thing.get("cue")
            entry: dict[str, Any] = {"name": name}
            if report is not None or cue is not None:
                source = "seen" if report is not None else "heard"
                given = (np.asarray(report, dtype=np.float64) if report is not None
                         else self.heard(cue))
                slot, revised = self.records.write(self.key(name), self.record_code(given)[0])
                slot = int(slot)
                previous = self.record_meta.get(slot, {})
                moved = (not previous or previous.get("name") != name
                         or float(np.hypot(*(np.asarray(previous["given"]) - given))) > 0.03)
                if moved:
                    self.record_meta[slot] = {"name": name, "moment": self.moments, "source": source,
                                              "given": [float(given[0]), float(given[1])]}
                else:
                    previous["latest"] = self.moments
                    previous["source"] = source
                place = decode(self.record_code, np.asarray(self.records.values[slot]))
                entry.update({"slot": slot, "source": source, "write": True, "revised": bool(revised),
                              "place": [float(place[0]), float(place[1])]})
            else:
                slot, place, cosine = self._held(name, credit=False)
                entry.update({"slot": slot, "source": "held", "write": False,
                              "place": None if place is None else [float(place[0]), float(place[1])]})
            meta = self.record_meta.get(entry["slot"]) if entry["slot"] >= 0 else None
            if meta is not None and meta.get("name") == name:
                entry["stored"] = meta["moment"]
                entry["unseen"] = self.moments - int(meta.get("latest", meta["moment"]))
                entry["from"] = meta["source"]
            out.append(entry)
        self.records.moment()
        return out

    def ask(self, name: str) -> dict[str, Any]:
        slot, place, cosine = self._held(name, credit=True)
        return {"name": name, "slot": slot, "cosine": round(cosine, 4),
                "place": None if place is None else [float(place[0]), float(place[1])],
                "stored": self.record_meta.get(slot)}

    # -- requests

    def reset(self) -> dict[str, Any]:
        self.brain.reset()
        return {"reset": True, "moments": self.moments}

    def reborn(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        if config:
            self.config.update(config)
        self._build()
        return self.describe()

    def handle(self, m: dict[str, Any]) -> dict[str, Any]:
        self.buffers = {}
        command = m.get("command")
        if command == "describe":
            reply = self.describe()
        elif command == "step":
            reply = self.step(m)
        elif command == "ask":
            reply = self.ask(str(m.get("thing")))
        elif command == "reset":
            reply = self.reset()
        elif command == "reborn":
            reply = self.reborn(m.get("config"))
        else:
            reply = {"error": f"unknown command {command!r}"}
        reply["buffers"] = sorted(self.buffers)
        return reply
