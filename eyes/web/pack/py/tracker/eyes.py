"""Eyes: retina windows that move over a surface of diverse shapes.

An eye sees a ``window``-square patch of the surface centred on its gaze and answers, through
the brain's two gaze slots, in which of ``bins`` × ``bins`` cells its object lies. Its object is
the object nearest the window centre, the only identity one frame can carry. With an odd number
of bins the window centre is the centre of the middle bin: an object inside the middle bin
leaves the eye still, and an answer off the middle bin moves the gaze by whole bins onto it.

``EyeWorld`` raises one eye. Open loop, the world places the eye near an object and then moves
it as a competent eye would; closed loop, the brain's own answers move it. ``Scene`` is the
many-object world of the page: shapes freeze, walk and dart on a large surface in world time,
every tracked object has an eye, all eyes settle together as one batch of streams, and each
eye moves by its own answer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from cadence import Brain

from .life import Life, Teaching
from .shapes import HELD_OUT, KINDS, ROTATES, TRAINED, Thing, render
from .world import Frame

__all__ = ["EyeConfig", "EyeWorld", "Eyes", "Retina", "Scene", "closed_eye", "glance", "scene_assay"]


@dataclass(frozen=True)
class EyeConfig:
    """One eye and the world it is raised in. Every designed constant is declared here."""

    window: int = 26
    bins: int = 13
    surface: int = 96
    kinds: tuple[str, ...] = TRAINED
    count: tuple[int, int] = (3, 12)
    sizes: tuple[float, float] = (6.0, 10.0)
    levels: tuple[float, float] = (0.4, 1.0)
    background: float = 0.1
    texture: float = 0.03
    placement: tuple[float, float] = (0.6, 0.3)  # shares placed within ``near`` and ``mid`` px
    near: float = 2.0
    mid: float = 6.0
    scene_ticks: tuple[int, int] = (8, 24)
    stay: float = 0.3
    step: float = 0.7
    dart: float = 0.05
    dart_px: tuple[float, float] = (3.0, 7.0)
    slip: float = 0.1  # open loop: the eye lands off its object again

    # The names the life, the runner and the baselines read.
    @property
    def size(self) -> int:
        return self.window

    @property
    def target_size(self) -> float:
        return sum(self.sizes) / 2

    def with_(self, **changes: Any) -> EyeConfig:
        return replace(self, **changes)


class Retina:
    """Window geometry shared by every eye: bins, centres, the middle bin and saccades."""

    def __init__(self, window: int, bins: int) -> None:
        if bins % 2 == 0 or window % bins:
            raise ValueError("an eye needs an odd number of bins of whole pixels")
        self.window, self.bins = window, bins
        self.cell = window // bins
        self.middle = bins // 2

    def bins_of(self, x: float, y: float) -> tuple[int, int]:
        b = self.bins
        return (min(max(int(x // self.cell), 0), b - 1), min(max(int(y // self.cell), 0), b - 1))

    def centre_of(self, bx: int, by: int) -> tuple[float, float]:
        return (bx + 0.5) * self.cell, (by + 0.5) * self.cell

    def origin(self, gx: int, gy: int) -> tuple[int, int]:
        return gx - self.window // 2, gy - self.window // 2

    def nearest(self, things: list[Thing], gx: int, gy: int) -> int | None:
        """Index of the thing nearest the window centre among those centred in the window."""
        ox, oy = self.origin(gx, gy)
        best, best_d = None, np.inf
        for k, t in enumerate(things):
            x, y = t.x - ox, t.y - oy
            if 0 <= x < self.window and 0 <= y < self.window:
                d = (x - self.window / 2) ** 2 + (y - self.window / 2) ** 2
                if d < best_d:
                    best, best_d = k, d
        return best

    def saccade(self, gx: int, gy: int, answer, width: int, height: int) -> tuple[int, int]:
        """Move the gaze by whole bins onto the answer; the window stays on the surface."""
        if answer is None:
            return gx, gy
        h = self.window // 2
        gx = int(np.clip(gx + self.cell * (int(answer[0]) - self.middle), h, width - h))
        gy = int(np.clip(gy + self.cell * (int(answer[1]) - self.middle), h, height - h))
        return gx, gy


def _sample_things(rng: np.random.Generator, cfg: EyeConfig, n: int, width: int, height: int,
                   kinds: tuple[str, ...]) -> list[Thing]:
    out: list[Thing] = []
    for _ in range(n):
        kind = kinds[int(rng.integers(len(kinds)))]
        size = float(rng.uniform(*cfg.sizes))
        x = y = 0.0
        for _ in range(60):
            x = float(rng.uniform(size / 2, width - size / 2))
            y = float(rng.uniform(size / 2, height - size / 2))
            if all(np.hypot(x - o.x, y - o.y) >= 0.6 * (size + o.size) for o in out):
                break
        angle = float(rng.uniform(0, 2 * np.pi)) if kind in ROTATES else 0.0
        out.append(Thing(kind, x, y, size, float(rng.uniform(*cfg.levels)), angle))
    return out


def _backdrop(rng: np.random.Generator, cfg: EyeConfig, height: int, width: int) -> np.ndarray:
    base = np.full((height, width), cfg.background)
    if cfg.texture:
        base = base + cfg.texture * rng.standard_normal(base.shape)
    return np.clip(base, 0.0, 1.0)


class EyeWorld:
    """One eye on a surface of shapes; ``step`` renders what the eye sees.

    Open loop (``closed`` false), the eye lands near an object (``placement``), follows it as
    a competent eye would and now and then lands off it again (``slip``). Closed loop, only the
    brain's answers move it (``look``); an eye with nothing in view is placed again. The
    witnessed target is the object nearest the window centre.
    """

    def __init__(self, config: EyeConfig, seed: int = 0, *, closed: bool = False) -> None:
        self.config = config
        self.retina = Retina(config.window, config.bins)
        self.rng = np.random.default_rng(seed)
        self.closed = closed
        self.things: list[Thing] = []
        self.backdrop = np.zeros((config.surface, config.surface))
        self.gx = self.gy = config.surface // 2
        self.left = 0
        self.ticks = 0
        self.mine: int | None = None
        self.last: tuple[float, float] | None = None
        self.counts = {"scenes": 0, "lost": 0, "switches": 0}

    # The scorer's geometry, in window coordinates.
    def cell(self) -> float:
        return float(self.retina.cell)

    def bins_of(self, x: float, y: float) -> tuple[int, int]:
        return self.retina.bins_of(x, y)

    def centre_of(self, bx: int, by: int) -> tuple[float, float]:
        return self.retina.centre_of(bx, by)

    # -- the scene

    def _scene(self) -> None:
        cfg, rng, s = self.config, self.rng, self.config.surface
        n = int(rng.integers(cfg.count[0], cfg.count[1] + 1))
        self.things = _sample_things(rng, cfg, n, s, s, cfg.kinds)
        self.backdrop = _backdrop(rng, cfg, s, s)
        self.left = int(rng.integers(cfg.scene_ticks[0], cfg.scene_ticks[1] + 1))
        self.mine = int(rng.integers(n))
        self.place(self.mine)
        self.last = None
        self.counts["scenes"] += 1

    def offset(self, bucket: str | None = None) -> tuple[float, float]:
        cfg, rng = self.config, self.rng
        if bucket is None:
            u = rng.random()
            near, mid = cfg.placement
            bucket = "near" if u < near else ("mid" if u < near + mid else "far")
        r = {"near": cfg.near, "mid": cfg.mid, "far": cfg.window / 2 - 1}[bucket]
        return float(rng.uniform(-r, r)), float(rng.uniform(-r, r))

    def place(self, k: int, bucket: str | None = None) -> None:
        """Land the eye near thing ``k``."""
        t, h, s = self.things[k], self.config.window // 2, self.config.surface
        dx, dy = self.offset(bucket)
        self.gx = int(np.clip(round(t.x - dx), h, s - h))
        self.gy = int(np.clip(round(t.y - dy), h, s - h))

    def _move(self) -> None:
        cfg, rng, s = self.config, self.rng, self.config.surface
        moved = []
        for t in self.things:
            u = rng.random()
            if u < cfg.stay:
                moved.append(t)
                continue
            if u < cfg.stay + cfg.dart:
                d, a = rng.uniform(*cfg.dart_px), rng.uniform(0, 2 * np.pi)
                dx, dy = d * np.cos(a), d * np.sin(a)
            else:
                dx, dy = cfg.step * rng.standard_normal(2)
            m = t.size / 2
            moved.append(replace(t, x=float(np.clip(t.x + dx, m, s - m)),
                                 y=float(np.clip(t.y + dy, m, s - m))))
        self.things = moved

    def look(self, answer) -> None:
        """Closed loop: the eye moves by the brain's answer."""
        s = self.config.surface
        self.gx, self.gy = self.retina.saccade(self.gx, self.gy, answer, s, s)

    def window(self) -> np.ndarray:
        w = self.config.window
        ox, oy = self.retina.origin(self.gx, self.gy)
        return render(w, w, self.things, self.backdrop[oy:oy + w, ox:ox + w], origin=(ox, oy))

    # -- one tick

    def step(self) -> Frame:
        cfg, rng = self.config, self.rng
        if self.left <= 0 or not self.things:
            self._scene()
            event = "jump"
        else:
            if not self.closed and self.mine is not None:
                ox, oy = self.retina.origin(self.gx, self.gy)
                t = self.things[self.mine]
                self.look(self.retina.bins_of(t.x - ox, t.y - oy))
            self._move()
            event = "step"
            if not self.closed and rng.random() < cfg.slip and self.mine is not None:
                self.place(self.mine)
                event = "slip"
        self.left -= 1
        self.ticks += 1
        k = self.retina.nearest(self.things, self.gx, self.gy)
        if k is None and self.closed:
            self.counts["lost"] += 1
            self.place(int(rng.integers(len(self.things))))
            k = self.retina.nearest(self.things, self.gx, self.gy)
            event = "lost"
        if k is not None and self.mine is not None and k != self.mine and event == "step":
            self.counts["switches"] += 1
        self.mine = k if k is not None else self.mine
        pixels = self.window()
        ox, oy = self.retina.origin(self.gx, self.gy)
        w = cfg.window
        if k is None:
            x = y = w / 2
            visible, kind = False, None
        else:
            t = self.things[k]
            x, y, visible, kind = t.x - ox, t.y - oy, True, t.kind
        displacement = 0.0 if self.last is None or event == "jump" else float(
            np.hypot(x - self.last[0], y - self.last[1]))
        self.last = (x, y)
        frame = Frame(pixels, x, y, visible, event, displacement, self.retina.bins_of(x, y))
        frame.kind = kind
        frame.offset_px = float(np.hypot(x - w / 2, y - w / 2))
        return frame


# -- assays of one eye on frozen copies


def _chebyshev(a, b) -> int:
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def glance(path: str | Path, config: EyeConfig, trials: int, seed: int = 0,
           kinds: tuple[str, ...] | None = None) -> dict:
    """First glance at a fresh scene, answered from rest: pure visual localization.

    The eye lands near an object in each placement bucket in turn. The centre guess (always the
    middle bin) and uniform random are scored on the same frames. Each frame is then shown
    three more times: an unchanged frame should cost zero sweeps.
    """
    brain = Brain.load(path)
    cfg = config if kinds is None else config.with_(kinds=kinds)
    world = EyeWorld(cfg, seed)
    rng = np.random.default_rng(seed + 7)
    middle = cfg.bins // 2
    rows = []
    for k in range(trials):
        bucket = ("near", "mid", "far")[k % 3]
        world._scene()
        world.place(int(world.mine), bucket)
        kk = world.retina.nearest(world.things, world.gx, world.gy)
        if kk is None:
            continue
        ox, oy = world.retina.origin(world.gx, world.gy)
        t = world.things[kk]
        target = world.retina.bins_of(t.x - ox, t.y - oy)
        pixels = world.window()
        brain.reset()
        try:
            a = brain.act(pixels.reshape(1, -1), greedy=True)[0]
            d = _chebyshev(a, target)
            again = []
            for _ in range(3):
                brain.act(pixels.reshape(1, -1), greedy=True)
                again.append(int(brain.last_settlement["steps"]))
        except RuntimeError:
            d, again = cfg.bins, []
        guess = rng.integers(0, cfg.bins, size=2)
        rows.append({
            "bucket": bucket, "kind": t.kind, "hit": d <= 1, "exact": d == 0,
            "offset_px": float(np.hypot(t.x - ox - cfg.window / 2, t.y - oy - cfg.window / 2)),
            "centre_hit": _chebyshev((middle, middle), target) <= 1,
            "random_hit": _chebyshev(guess, target) <= 1, "still_sweeps": again,
        })

    def rate(sel, key):
        return None if not sel else round(float(np.mean([r[key] for r in sel])), 4)

    out: dict[str, Any] = {"trials": len(rows)}
    for name, sel in [("all", rows)] + [(b, [r for r in rows if r["bucket"] == b])
                                       for b in ("near", "mid", "far")]:
        out[name] = {"trials": len(sel), "hit": rate(sel, "hit"), "exact": rate(sel, "exact"),
                     "centre": rate(sel, "centre_hit"), "random": rate(sel, "random_hit")}
    out["off_middle"] = {
        "trials": sum(1 for r in rows if not r["centre_hit"]),
        "hit": rate([r for r in rows if not r["centre_hit"]], "hit"),
    }
    out["by_kind"] = {k: rate([r for r in rows if r["kind"] == k], "hit")
                      for k in sorted({r["kind"] for r in rows})}
    still = [s for r in rows for s in r["still_sweeps"]]
    out["still_zero_share"] = round(float(np.mean(np.array(still) == 0)), 4) if still else None
    return out


def closed_eye(path: str | Path, config: EyeConfig, ticks: int, seed: int = 0,
               teaching: str = "never") -> dict:
    """One eye in closed loop on moving shapes: its answers move it; nothing else does."""
    brain = Brain.load(path)
    brain.reset()
    world = EyeWorld(config, seed, closed=True)
    life = Life(brain, world, teaching=Teaching(teaching), seed=seed)
    rows = []
    for _ in range(ticks):
        frame = world.step()
        row = life.see(frame, "closed")
        row["offset_px"] = round(frame.offset_px, 3)
        rows.append(row)
        world.look(None if row["refused"] else (row["ax"], row["ay"]))
    steps = [r for r in rows if r["event"] == "step"]
    sweeps = np.array([r["sweeps"] for r in steps]) if steps else np.zeros(1)
    return {
        "ticks": ticks, "scenes": world.counts["scenes"],
        "hit": round(float(np.mean([r["hit"] for r in rows if r["visible"]])), 4),
        "lost_per_100": round(100 * world.counts["lost"] / ticks, 2),
        "switches_per_100": round(100 * world.counts["switches"] / ticks, 2),
        "offset_px_median": round(float(np.median([r["offset_px"] for r in rows])), 2),
        "still_zero_share": round(float(np.mean([r["sweeps"] == 0 for r in steps
                                                 if r["displacement"] == 0.0] or [np.nan])), 4),
        "sweeps_mean": round(float(sweeps.mean()), 2),
        "lessons": int(sum(r["lesson"] for r in rows)),
    }


# -- many eyes on one surface


class Eyes:
    """Eyes over a surface of pixels, each eye one stream of the one brain.

    ``see`` cuts every eye's window out of the surface, lets all eyes settle together, each
    from its own previous equilibrium, and moves each eye by whole bins onto its answer. The
    eyes receive nothing but pixels; where to open an eye is the only thing they are told.
    Opening or closing an eye changes the streams and starts every stream afresh.
    """

    def __init__(self, brain: Brain, window: int, bins: int, width: int, height: int) -> None:
        self.brain = brain
        self.retina = Retina(window, bins)
        self.width, self.height = width, height
        self.gaze: dict[int, tuple[int, int]] = {}
        self.answers: dict[int, tuple[int, int] | None] = {}
        self.streams: list[int] = []

    def open(self, eid: int, x: float, y: float) -> None:
        h = self.retina.window // 2
        self.gaze[eid] = (int(np.clip(round(x), h, self.width - h)),
                          int(np.clip(round(y), h, self.height - h)))

    def close(self, eid: int) -> None:
        self.gaze.pop(eid, None)
        self.answers.pop(eid, None)

    def window(self, surface: np.ndarray, gx: int, gy: int) -> np.ndarray:
        w = self.retina.window
        ox, oy = self.retina.origin(gx, gy)
        return surface[oy:oy + w, ox:ox + w]

    def see(self, surface: np.ndarray) -> dict[str, Any]:
        """One frame for every eye: answers, saccades, the settlement's work."""
        ids = list(self.gaze)
        if ids != self.streams:
            self.brain.reset()
            self.streams = ids
        out: dict[str, Any] = {"eyes": [], "sweeps": 0, "ms": 0.0, "x": None, "state": None}
        if not ids:
            return out
        inputs = np.stack([self.window(surface, *self.gaze[i]) for i in ids])
        x = inputs.reshape(len(ids), -1)
        start = time.perf_counter()
        try:
            answers = [(int(a[0]), int(a[1])) for a in self.brain.act(x, greedy=True)]
        except RuntimeError:
            answers = [None] * len(ids)
        ms = (time.perf_counter() - start) * 1000
        rep = self.brain.last_settlement or {}
        for eid, a in zip(ids, answers, strict=True):
            gx, gy = self.gaze[eid]
            self.answers[eid] = a
            self.gaze[eid] = self.retina.saccade(gx, gy, a, self.width, self.height)
            out["eyes"].append({"id": eid, "gaze": [gx, gy], "answer": a,
                                "next": list(self.gaze[eid])})
        out.update(sweeps=int(rep.get("steps", 0)), ms=round(ms, 2), x=x, inputs=inputs,
                   state=self.brain.basal_ganglia.state)
        return out


class Scene:
    """A large surface with diverse shapes; every tracked shape has an eye.

    The shapes and their motion are the world; the eyes see only the rendered pixels. Shapes
    freeze, walk and dart in world time when ``animate`` is on, and can be dragged.
    """

    def __init__(self, brain: Brain, config: EyeConfig = EyeConfig(), *, width: int = 160,
                 height: int = 100, fps: float = 20.0, seed: int = 0) -> None:
        self.brain = brain
        self.config = config
        self.retina = Retina(config.window, config.bins)
        self.eyes = Eyes(brain, config.window, config.bins, width, height)
        self.width, self.height, self.fps = width, height, float(fps)
        self.rng = np.random.default_rng(seed)
        self.backdrop = _backdrop(self.rng, config, height, width)
        self.things: dict[int, Thing] = {}
        self.order: list[int] = []
        self.motion: dict[int, dict] = {}
        self.animate = False
        self.learn = False
        self.next_id = 1
        self.ticks = 0
        self.lessons = 0
        self.clock = 0.0  # world time in seconds

    # -- objects

    def add(self, kind: str, x: float | None = None, y: float | None = None, *,
            size: float | None = None, level: float | None = None, angle: float | None = None,
            tracked: bool = True) -> int:
        cfg, rng = self.config, self.rng
        if kind not in KINDS:
            raise ValueError(f"unknown shape {kind!r}")
        size = float(rng.uniform(*cfg.sizes)) if size is None else float(size)
        m = size / 2
        x = float(rng.uniform(m, self.width - m)) if x is None else float(np.clip(x, m, self.width - m))
        y = float(rng.uniform(m, self.height - m)) if y is None else float(np.clip(y, m, self.height - m))
        level = float(rng.uniform(*cfg.levels)) if level is None else float(level)
        if angle is None:
            angle = float(rng.uniform(0, 2 * np.pi)) if kind in ROTATES else 0.0
        oid = self.next_id
        self.next_id += 1
        self.things[oid] = Thing(kind, x, y, size, level, float(angle))
        self.order.append(oid)
        if tracked:
            self.track(oid, True)
        return oid

    def move(self, oid: int, x: float, y: float, hold: float = 0.6) -> None:
        t = self.things.get(oid)
        if t is None:
            return
        m = t.size / 2
        self.things[oid] = replace(t, x=float(np.clip(x, m, self.width - m)),
                                   y=float(np.clip(y, m, self.height - m)))
        if oid in self.motion:
            self.motion[oid]["held"] = self.clock + hold

    def remove(self, oid: int) -> None:
        self.things.pop(oid, None)
        self.order = [i for i in self.order if i != oid]
        self.eyes.close(oid)
        self.motion.pop(oid, None)

    def track(self, oid: int, on: bool) -> None:
        if oid not in self.things:
            return
        if on:
            t = self.things[oid]
            self.eyes.open(oid, t.x, t.y)
        else:
            self.eyes.close(oid)

    def populate(self, count: int, kinds: tuple[str, ...] = TRAINED, tracked: int | None = None) -> None:
        """A fresh surface of ``count`` shapes, the first ``tracked`` of them with eyes."""
        for oid in list(self.order):
            self.remove(oid)
        things = _sample_things(self.rng, self.config, count, self.width, self.height, kinds)
        for k, t in enumerate(things):
            self.add(t.kind, t.x, t.y, size=t.size, level=t.level, angle=t.angle,
                     tracked=tracked is None or k < tracked)

    # -- the world

    def wander(self) -> None:
        """Shapes freeze, walk and dart on their own; a shape just dragged waits."""
        dt = 1.0 / self.fps
        rng = self.rng
        for oid in self.order:
            st = self.motion.get(oid)
            if st is None or st["left"] <= 0:
                mode = rng.choice(["freeze", "walk", "dart"], p=[0.35, 0.5, 0.15])
                speed = {"freeze": 0.0, "walk": 6.0, "dart": 30.0}[mode]
                low, high = {"freeze": (0.6, 1.8), "walk": (0.6, 2.0), "dart": (0.15, 0.3)}[mode]
                a = rng.uniform(0, 2 * np.pi)
                st = {"vx": speed * np.cos(a), "vy": speed * np.sin(a),
                      "left": float(rng.uniform(low, high)), "held": st["held"] if st else 0.0}
                self.motion[oid] = st
            st["left"] -= dt
            if self.clock < st["held"]:
                continue
            t = self.things[oid]
            m = t.size / 2
            x, y = t.x + st["vx"] * dt, t.y + st["vy"] * dt
            if not m <= x <= self.width - m:
                st["vx"] = -st["vx"]
            if not m <= y <= self.height - m:
                st["vy"] = -st["vy"]
            self.things[oid] = replace(t, x=float(np.clip(x, m, self.width - m)),
                                       y=float(np.clip(y, m, self.height - m)))

    def surface(self) -> np.ndarray:
        return render(self.height, self.width, [self.things[i] for i in self.order], self.backdrop)

    def score(self, eid: int, gaze, answer) -> dict[str, Any]:
        """What the world knows about one eye's answer: on its own shape, which shape is nearest."""
        gx, gy = gaze
        ox, oy = self.retina.origin(gx, gy)
        listed = [self.things[i] for i in self.order]
        near = self.retina.nearest(listed, gx, gy)
        t = self.things[eid]
        w = self.config.window
        in_view = 0 <= t.x - ox < w and 0 <= t.y - oy < w
        own_bins = self.retina.bins_of(t.x - ox, t.y - oy) if in_view else None
        label = None
        if near is not None:
            n = listed[near]
            label = self.retina.bins_of(n.x - ox, n.y - oy)
        centred = own_bins is not None and _chebyshev(own_bins, (self.retina.middle, self.retina.middle)) <= 1
        return {"own": near is not None and self.order[near] == eid, "in_view": bool(in_view),
                "hit": answer is not None and own_bins is not None and _chebyshev(answer, own_bins) <= 1,
                "centred": bool(centred), "label": label}

    # -- one frame

    def step(self) -> dict[str, Any]:
        """Advance one frame: move the world, render it, let every eye see and move."""
        if self.animate:
            self.wander()
        self.clock += 1.0 / self.fps
        self.ticks += 1
        pix = self.surface()
        seen = self.eyes.see(pix)
        lesson_rows, labels = [], []
        for k, e in enumerate(seen["eyes"]):
            e.update(self.score(e["id"], e["gaze"], e["answer"]))
            if self.learn and e["label"] is not None and e["answer"] is not None \
                    and _chebyshev(e["answer"], e["label"]) > 1:
                lesson_rows.append(k)
                labels.append(e["label"])
        state = seen["state"]
        if lesson_rows and state is not None:
            drive = self.brain.stimulus(seen["x"][lesson_rows])
            warm = replace(state, v=state.v[lesson_rows], activation=state.activation[lesson_rows],
                           adaptation=state.adaptation[lesson_rows],
                           activity_change=state.activity_change[lesson_rows])
            self.brain.learner.step(drive, np.array(labels, dtype=np.int64), warm=warm)
            self.lessons += len(lesson_rows)
        seen["surface"] = pix
        seen["tick"] = self.ticks
        return seen


def scene_assay(path: str | Path, config: EyeConfig, *, objects: int, frames: int, seed: int = 0,
                width: int = 160, height: int = 100, fps: float = 20.0,
                kinds: tuple[str, ...] = TRAINED, policy: str = "brain") -> dict:
    """Every shape followed by its own eye while all of them move on their own.

    ``policy`` "brain" moves the eyes by the brain's answers; "fixed" never moves them;
    "oracle" by the true bins of the shape nearest the window centre (the bound set by the
    window and the nearest-shape rule); "random" by uniform random answers.
    """
    brain = Brain.load(path)
    scene = Scene(brain, config, width=width, height=height, fps=fps, seed=seed)
    scene.populate(objects, kinds)
    scene.animate = True
    rng = np.random.default_rng(seed + 1)
    own, hit, in_view, centred, losses, still, moving = [], [], [], [], 0, [], []
    previous_own: dict[int, bool] = {}
    last_xy = None
    for _ in range(frames):
        if policy == "brain":
            f = scene.step()
            eyes, sweeps = f["eyes"], f["sweeps"]
        else:
            scene.wander()
            scene.clock += 1.0 / scene.fps
            eyes, sweeps = [], 0
            for eid in list(scene.eyes.gaze):
                gaze = scene.eyes.gaze[eid]
                truth = scene.score(eid, gaze, None)
                a = {"oracle": truth["label"], "fixed": None,
                     "random": tuple(int(v) for v in rng.integers(0, config.bins, 2))}[policy]
                e = scene.score(eid, gaze, a)
                e["id"] = eid
                eyes.append(e)
                scene.eyes.gaze[eid] = scene.retina.saccade(*gaze, a, scene.width, scene.height)
        xy = [(scene.things[i].x, scene.things[i].y) for i in scene.order]
        (still if xy == last_xy else moving).append(sweeps)
        last_xy = xy
        for e in eyes:
            own.append(e["own"])
            hit.append(e["hit"])
            in_view.append(e["in_view"])
            centred.append(e["centred"])
            if previous_own.get(e["id"], True) and not e["own"]:
                losses += 1
            previous_own[e["id"]] = e["own"]
    minutes = frames / fps / 60
    return {
        "policy": policy, "objects": objects, "frames": frames,
        "own": round(float(np.mean(own)), 4), "hit": round(float(np.mean(hit)), 4),
        "on_own_shape": round(float(np.mean(centred)), 4),
        "in_view": round(float(np.mean(in_view)), 4),
        "losses_per_eye_minute": round(losses / objects / minutes, 2),
        "still_frames": len(still),
        "still_zero_share": round(float(np.mean(np.array(still) == 0)), 4) if still else None,
        "sweeps_per_moving_frame": round(float(np.mean(moving)), 2) if moving else None,
    }


def window_dart(path: str | Path, config: EyeConfig, trials: int, seed: int = 0, *,
                jumps=(10.0, 20.0, 30.0), others: int = 4, distractor: bool = False) -> dict:
    """The dart test of ``tracker.fovea.fovea_dart`` for the window eye: its shape (or another
    shape) jumps while everything else stays still; is the eye back on its own shape, within one
    bin of its middle bin, after one, two and three frames?"""
    brain = Brain.load(path)
    rng = np.random.default_rng(seed)
    r = Retina(config.window, config.bins)
    out = {}
    for jump in jumps:
        on: dict[int, list[bool]] = {1: [], 2: [], 3: []}
        for _ in range(trials):
            scene = Scene(brain, config, seed=int(rng.integers(1 << 30)))
            scene.populate(others + 1, config.kinds, tracked=1)
            mine = scene.order[0]
            for _ in range(4):
                scene.step()
            mover = scene.order[1] if distractor else mine
            t = scene.things[mover]
            nx, ny = t.x, t.y
            for _ in range(20):
                a = rng.uniform(0, 2 * np.pi)
                nx, ny = t.x + jump * np.cos(a), t.y + jump * np.sin(a)
                if t.size / 2 <= nx <= scene.width - t.size / 2 and t.size / 2 <= ny <= scene.height - t.size / 2:
                    break
            scene.move(mover, nx, ny, hold=0.0)
            for k in (1, 2, 3):
                scene.step()
                gx, gy = scene.eyes.gaze[mine]
                ox, oy = r.origin(gx, gy)
                own = scene.things[mine]
                x, y = own.x - ox, own.y - oy
                inside = 0 <= x < config.window and 0 <= y < config.window
                b = r.bins_of(x, y)
                on[k].append(inside and max(abs(b[0] - r.middle), abs(b[1] - r.middle)) <= 1)
        out[str(jump)] = {str(k): round(float(np.mean(v)), 4) for k, v in on.items()}
    return out
