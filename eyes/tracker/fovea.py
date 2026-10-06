"""A foveated eye: a fine centre, a coarse periphery, and a channel for change.

The window eye (``tracker.eyes``) sees a 26-pixel window at full resolution. A shape that jumps
farther than half the window between two frames leaves it, and the eye has nothing left to
look at. A primate retina is foveated instead: receptors sit one pixel apart at the centre and
spread out with eccentricity, each pooling the light of a growing patch, so the eye sees far
but coarsely. Its periphery is dominated by transient cells that answer change. The superior
colliculus maps the visual field the same way, fine for small saccades near the centre and
coarse for large ones.

``Fovea`` is that geometry: ``receptors`` per axis (odd, centred on the gaze), one pixel apart
out to ``inner`` pixels and geometrically spaced beyond, out to ``reach``. Every receptor
reports two channels: the mean brightness of its patch, and the mean absolute change of that
patch since the previous frame (computed on the surface, so the eye's own saccades do not count
as change). The answer bins follow the receptors: the middle bin covers the three central
receptors (an object within 1.5 px leaves the eye still); outward, each bin covers two
receptors and a saccade to it moves the gaze by its receptors' mean offset. The eye can look
anywhere on the surface; beyond the surface edge it sees the background level.

An eye follows its own shape. ``FovealWorld`` raises the eye on that identity: the label is
always the eye's own shape, also when another shape passes closer or its own shape darts away.
``FovealEyes`` is the pixels-only part the page runs; ``FovealScene`` the native many-eye world.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from cadence import Brain

from .life import Life, Teaching
from .shapes import KINDS, ROTATES, TRAINED, Thing, render
from .world import Frame

__all__ = ["FOVEA_KINDS", "Fovea", "FovealConfig", "FovealEyes", "FovealScene", "FovealWorld",
           "fovea_dart", "fovea_glance", "fovea_scene"]

FOVEA_KINDS = TRAINED + ("face",)


class Fovea:
    """Receptor positions, receptor patches, answer bins and saccades of one foveated eye."""

    def __init__(self, receptors: int = 25, inner: int = 6, reach: float = 40.0, bins: int = 13,
                 background: float = 0.1) -> None:
        half, half_bins = receptors // 2, bins // 2
        if receptors % 2 == 0 or bins % 2 == 0 or half <= inner:
            raise ValueError("a fovea needs odd receptor and bin counts and a periphery")
        if half_bins != int(np.ceil((half - 1) / 2)):
            raise ValueError("bins must group the receptors: three in the middle, then pairs")
        o = np.arange(half + 1, dtype=float)
        ratio = (reach / inner) ** (1.0 / (half - inner))
        o[inner + 1:] = inner * ratio ** np.arange(1, half - inner + 1)
        self.receptors, self.inner, self.reach, self.bins = receptors, inner, reach, bins
        self.half, self.middle = half, half_bins
        self.background = background
        self.offsets = np.concatenate([-o[:0:-1], o])
        # Patch of every receptor along one axis: from the midpoint to its inner neighbour to the
        # midpoint to its outer neighbour; the central receptor is one pixel.
        hi = np.empty(half + 1)
        hi[:-1] = (o[:-1] + o[1:]) / 2
        hi[0] = 0.5
        hi[-1] = o[-1] + (o[-1] - o[-2]) / 2
        lo = np.concatenate([[-0.5], hi[:-1]])
        lo_all = np.concatenate([-hi[:0:-1], lo])
        hi_all = np.concatenate([-lo[:0:-1], hi])
        self.lo = np.floor(lo_all + 0.5).astype(int)
        self.hi = np.floor(hi_all + 0.5).astype(int)
        self.hi = np.maximum(self.hi, self.lo + 1)
        self.pad = int(np.ceil(max(-self.lo.min(), self.hi.max()))) + 2
        # Bins: the three central receptors, then pairs outward, the last one alone if odd.
        k = np.arange(receptors) - half
        steps = np.where(np.abs(k) <= 1, 0, np.ceil((np.abs(k) - 1) / 2)).astype(int)
        self.bin_of_receptor = half_bins + np.sign(k) * steps
        self.bin_offset = np.array([self.offsets[self.bin_of_receptor == b].mean() for b in range(bins)])
        self.bin_lo = np.array([lo_all[self.bin_of_receptor == b].min() for b in range(bins)])
        self.bin_hi = np.array([hi_all[self.bin_of_receptor == b].max() for b in range(bins)])
        self.edges = np.concatenate([lo_all[:1], hi_all])  # receptor boundaries, px from the gaze

    # -- geometry

    def bin_of(self, d: float) -> int | None:
        """The bin of an offset in pixels from the gaze, or None beyond the periphery."""
        if not self.edges[0] <= d < self.edges[-1]:
            return None
        r = int(np.searchsorted(self.edges, d, side="right")) - 1
        return int(self.bin_of_receptor[min(max(r, 0), self.receptors - 1)])

    def bins_of(self, dx: float, dy: float) -> tuple[int, int] | None:
        bx, by = self.bin_of(dx), self.bin_of(dy)
        return None if bx is None or by is None else (bx, by)

    def centre_of(self, bx: int, by: int) -> tuple[float, float]:
        return float(self.bin_offset[bx]), float(self.bin_offset[by])

    def saccade(self, gx: int, gy: int, answer, width: int, height: int) -> tuple[int, int]:
        if answer is None:
            return gx, gy
        dx, dy = self.centre_of(int(answer[0]), int(answer[1]))
        return (int(np.clip(gx + round(dx), 0, width - 1)), int(np.clip(gy + round(dy), 0, height - 1)))

    # -- seeing

    def integral(self, surface: np.ndarray, fill: float | None = None) -> np.ndarray:
        """Summed-area table of the surface padded by the periphery's reach."""
        p = self.pad
        padded = np.pad(surface, p, constant_values=self.background if fill is None else fill)
        out = np.zeros((padded.shape[0] + 1, padded.shape[1] + 1))
        out[1:, 1:] = padded.cumsum(axis=0).cumsum(axis=1)
        return out

    def sample(self, table: np.ndarray, gx: int, gy: int) -> np.ndarray:
        """Mean of every receptor's patch, receptors × receptors, row = y."""
        p = self.pad
        x0, x1 = gx + p + self.lo, gx + p + self.hi
        y0, y1 = gy + p + self.lo, gy + p + self.hi
        total = (table[y1][:, x1] - table[y0][:, x1] - table[y1][:, x0] + table[y0][:, x0])
        area = np.outer(y1 - y0, x1 - x0)
        return total / area

    def see(self, bright: np.ndarray, change: np.ndarray, gx: int, gy: int) -> np.ndarray:
        """The eye's input: brightness then change, each receptors × receptors, flattened."""
        return np.concatenate([self.sample(bright, gx, gy).ravel(), self.sample(change, gx, gy).ravel()])


@dataclass(frozen=True)
class FovealConfig:
    """The foveated eye and the world it is raised in. Every designed constant is declared here."""

    receptors: int = 25
    inner: int = 6
    reach: float = 40.0
    bins: int = 13
    surface: int = 128
    kinds: tuple[str, ...] = FOVEA_KINDS
    count: tuple[int, int] = (3, 12)
    sizes: tuple[float, float] = (6.0, 10.0)
    levels: tuple[float, float] = (0.4, 1.0)
    background: float = 0.1
    texture: float = 0.03
    change_gain: float = 1.0
    placement: tuple[float, float] = (0.2, 0.3)  # shares landing within ``near`` and ``mid`` px
    near: float = 3.0
    mid: float = 12.0
    far: float = 34.0
    scene_ticks: tuple[int, int] = (10, 30)
    stay: float = 0.3
    step: float = 0.7
    dart: float = 0.06  # per shape and tick: a fast move of ``dart_px`` over one to three ticks
    own_dart: float = 0.1  # the same for the eye's own shape
    dart_px: tuple[float, float] = (8.0, 34.0)
    slip: float = 0.3

    # The names the life and the runner read.
    @property
    def size(self) -> int:
        return self.receptors

    @property
    def target_size(self) -> float:
        return sum(self.sizes) / 2

    def fovea(self) -> Fovea:
        return Fovea(self.receptors, self.inner, self.reach, self.bins, self.background)

    def with_(self, **changes: Any) -> FovealConfig:
        return replace(self, **changes)


def _things(rng, cfg: FovealConfig, n: int, width: int, height: int, kinds) -> list[Thing]:
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


class FovealWorld:
    """One foveated eye on a surface of moving shapes; its own shape is its identity.

    Open loop, the eye lands near its shape and then moves as a competent eye would (by the
    true bin of its shape), now and then landing off it again. Closed loop, only the brain's
    answers move it, and an eye whose shape is beyond its periphery is placed again. Shapes
    walk, stay, or dart: a fast move of 8 to 34 px over one to three ticks.
    """

    def __init__(self, config: FovealConfig, seed: int = 0, *, closed: bool = False) -> None:
        self.config = config
        self.fovea = config.fovea()
        self.rng = np.random.default_rng(seed)
        self.closed = closed
        s = config.surface
        self.things: list[Thing] = []
        self.velocity: list[tuple[float, float, int]] = []
        self.texture = np.zeros((s, s))
        self.previous: np.ndarray | None = None
        self.gx = self.gy = s // 2
        self.mine = 0
        self.left = 0
        self.ticks = 0
        self.last: tuple[float, float] | None = None
        self.counts = {"scenes": 0, "lost": 0, "darts": 0}

    # The scorer's geometry: offsets from the gaze, in pixels.
    def cell(self) -> float:
        return 1.0

    def bins_of(self, dx: float, dy: float):
        return self.fovea.bins_of(dx, dy)

    def centre_of(self, bx: int, by: int) -> tuple[float, float]:
        return self.fovea.centre_of(bx, by)

    def _scene(self) -> None:
        cfg, rng, s = self.config, self.rng, self.config.surface
        n = int(rng.integers(cfg.count[0], cfg.count[1] + 1))
        self.things = _things(rng, cfg, n, s, s, cfg.kinds)
        self.velocity = [(0.0, 0.0, 0)] * n
        base = np.full((s, s), cfg.background)
        self.texture = np.clip(base + cfg.texture * rng.standard_normal((s, s)), 0, 1)
        self.left = int(rng.integers(cfg.scene_ticks[0], cfg.scene_ticks[1] + 1))
        self.mine = int(rng.integers(n))
        self.place()
        self.previous = None
        self.last = None
        self.counts["scenes"] += 1

    def offset(self, bucket: str | None = None) -> tuple[float, float]:
        cfg, rng = self.config, self.rng
        if bucket is None:
            u = rng.random()
            near, mid = cfg.placement
            bucket = "near" if u < near else ("mid" if u < near + mid else "far")
        r = {"near": cfg.near, "mid": cfg.mid, "far": cfg.far}[bucket]
        return float(rng.uniform(-r, r)), float(rng.uniform(-r, r))

    def place(self, bucket: str | None = None) -> None:
        """Land the eye near its shape, so that its own shape is the nearest one: a still frame
        can tell which shape is the eye's own only by where it is."""
        t, s = self.things[self.mine], self.config.surface
        for _ in range(30):
            dx, dy = self.offset(bucket)
            gx, gy = int(np.clip(round(t.x - dx), 0, s - 1)), int(np.clip(round(t.y - dy), 0, s - 1))
            d = np.hypot(t.x - gx, t.y - gy)
            if all(np.hypot(o.x - gx, o.y - gy) > d for k, o in enumerate(self.things) if k != self.mine):
                break
        self.gx, self.gy = gx, gy

    def _move(self) -> None:
        cfg, rng, s = self.config, self.rng, self.config.surface
        things, velocity = [], []
        for k, (t, (vx, vy, left)) in enumerate(zip(self.things, self.velocity, strict=True)):
            if left <= 0:
                u = rng.random()
                if u < (cfg.own_dart if k == self.mine else cfg.dart):
                    ticks = int(rng.integers(1, 4))
                    d, a = rng.uniform(*cfg.dart_px), rng.uniform(0, 2 * np.pi)
                    vx, vy, left = d * np.cos(a) / ticks, d * np.sin(a) / ticks, ticks
                elif u < (cfg.own_dart if k == self.mine else cfg.dart) + cfg.stay:
                    vx = vy = 0.0
                    left = 1
                else:
                    vx, vy = cfg.step * rng.standard_normal(2)
                    left = 1
            m = t.size / 2
            x, y = t.x + vx, t.y + vy
            if not m <= x <= s - m:
                vx = -vx
            if not m <= y <= s - m:
                vy = -vy
            things.append(replace(t, x=float(np.clip(x, m, s - m)), y=float(np.clip(y, m, s - m))))
            velocity.append((vx, vy, left - 1))
        self.things, self.velocity = things, velocity

    def look(self, answer) -> None:
        s = self.config.surface
        self.gx, self.gy = self.fovea.saccade(self.gx, self.gy, answer, s, s)

    def surface(self) -> np.ndarray:
        s = self.config.surface
        return render(s, s, self.things, self.texture)

    def step(self) -> Frame:
        cfg, rng, fv = self.config, self.rng, self.fovea
        event = "step"
        if self.left <= 0 or not self.things:
            self._scene()
            event = "jump"
        else:
            if not self.closed:
                t = self.things[self.mine]
                truth = fv.bins_of(t.x - self.gx, t.y - self.gy)
                self.look(truth)
            before = self.things[self.mine]
            self._move()
            after = self.things[self.mine]
            if np.hypot(after.x - before.x, after.y - before.y) > 4.0:
                event = "dart"
                self.counts["darts"] += 1
            if not self.closed and rng.random() < cfg.slip:
                self.place()
                event = "slip"
        self.left -= 1
        self.ticks += 1
        t = self.things[self.mine]
        if self.closed and fv.bins_of(t.x - self.gx, t.y - self.gy) is None:
            self.counts["lost"] += 1
            self.place()
            event = "lost"
        surface = self.surface()
        change = np.zeros_like(surface) if self.previous is None else np.abs(surface - self.previous)
        if event in ("jump",):
            change = np.zeros_like(surface)
        self.previous = surface
        pixels = fv.see(fv.integral(surface), fv.integral(cfg.change_gain * change, 0.0), self.gx, self.gy)
        dx, dy = t.x - self.gx, t.y - self.gy
        target = fv.bins_of(dx, dy)
        visible = target is not None
        displacement = 0.0 if self.last is None or event == "jump" else float(
            np.hypot(dx - self.last[0], dy - self.last[1]))
        self.last = (dx, dy)
        frame = Frame(pixels, dx, dy, visible, event, displacement, target if visible else (fv.middle, fv.middle))
        frame.kind = t.kind
        frame.offset_px = float(np.hypot(dx, dy))
        return frame


# -- many foveated eyes on one surface


class FovealEyes:
    """Foveated eyes over a surface of pixels, each eye one stream of the one brain.

    ``see`` takes the page's pixels, computes the change since the previous frame, lets every
    eye read its receptors and all eyes settle together, each from its own previous equilibrium,
    and moves every eye by its answer. Nothing else reaches the brain: where to open an eye is
    the only thing the eyes are told.
    """

    def __init__(self, brain: Brain, fovea: Fovea, width: int, height: int, change_gain: float = 1.0) -> None:
        self.brain = brain
        self.fovea = fovea
        self.width, self.height = width, height
        self.change_gain = change_gain
        self.gaze: dict[int, tuple[int, int]] = {}
        self.answers: dict[int, tuple[int, int] | None] = {}
        self.streams: list[int] = []
        self.previous: np.ndarray | None = None
        self.inputs: dict[int, np.ndarray] = {}

    def open(self, eid: int, x: float, y: float) -> None:
        self.gaze[eid] = (int(np.clip(round(x), 0, self.width - 1)), int(np.clip(round(y), 0, self.height - 1)))

    def close(self, eid: int) -> None:
        self.gaze.pop(eid, None)
        self.answers.pop(eid, None)
        self.inputs.pop(eid, None)

    def see(self, surface: np.ndarray) -> dict[str, Any]:
        ids = list(self.gaze)
        change = np.zeros_like(surface) if self.previous is None or self.previous.shape != surface.shape \
            else np.abs(surface - self.previous)
        self.previous = surface.copy()
        if ids != self.streams:
            self.brain.reset()
            self.streams = ids
        out: dict[str, Any] = {"eyes": [], "sweeps": 0, "ms": 0.0, "x": None, "state": None}
        if not ids:
            return out
        fv = self.fovea
        bright, moved = fv.integral(surface), fv.integral(self.change_gain * change, 0.0)
        x = np.stack([fv.see(bright, moved, *self.gaze[i]) for i in ids])
        start = time.perf_counter()
        try:
            answers = [(int(a[0]), int(a[1])) for a in self.brain.act(x, greedy=True)]
        except RuntimeError:
            answers = [None] * len(ids)
        ms = (time.perf_counter() - start) * 1000
        rep = self.brain.last_settlement or {}
        for k, (eid, a) in enumerate(zip(ids, answers, strict=True)):
            gx, gy = self.gaze[eid]
            self.answers[eid] = a
            self.inputs[eid] = x[k]
            self.gaze[eid] = fv.saccade(gx, gy, a, self.width, self.height)
            out["eyes"].append({"id": eid, "gaze": [gx, gy], "answer": a, "next": list(self.gaze[eid])})
        out.update(sweeps=int(rep.get("steps", 0)), ms=round(ms, 2), x=x,
                   state=self.brain.basal_ganglia.state)
        return out


class FovealScene:
    """The many-shape world with foveated eyes: shapes freeze, walk and dart in world time."""

    def __init__(self, brain: Brain, config: FovealConfig = FovealConfig(), *, width: int = 160,
                 height: int = 100, fps: float = 20.0, seed: int = 0) -> None:
        self.config = config
        self.fovea = config.fovea()
        self.eyes = FovealEyes(brain, self.fovea, width, height, config.change_gain)
        self.width, self.height, self.fps = width, height, float(fps)
        self.rng = np.random.default_rng(seed)
        self.texture = np.clip(config.background + config.texture * self.rng.standard_normal((height, width)), 0, 1)
        self.things: dict[int, Thing] = {}
        self.order: list[int] = []
        self.motion: dict[int, dict] = {}
        self.animate = False
        self.clock = 0.0
        self.next_id = 1

    def add(self, t: Thing, tracked: bool = True) -> int:
        oid = self.next_id
        self.next_id += 1
        self.things[oid] = t
        self.order.append(oid)
        if tracked:
            self.eyes.open(oid, t.x, t.y)
        return oid

    def populate(self, count: int, kinds=FOVEA_KINDS, tracked: int | None = None) -> None:
        for k, t in enumerate(_things(self.rng, self.config, count, self.width, self.height, kinds)):
            self.add(t, tracked is None or k < tracked)

    def move(self, oid: int, x: float, y: float) -> None:
        t = self.things[oid]
        m = t.size / 2
        self.things[oid] = replace(t, x=float(np.clip(x, m, self.width - m)), y=float(np.clip(y, m, self.height - m)))

    def wander(self) -> None:
        dt = 1.0 / self.fps
        rng = self.rng
        for oid in self.order:
            st = self.motion.get(oid)
            if st is None or st["left"] <= 0:
                mode = rng.choice(["freeze", "walk", "dart"], p=[0.35, 0.5, 0.15])
                speed = {"freeze": 0.0, "walk": 6.0, "dart": 30.0}[mode]
                low, high = {"freeze": (0.6, 1.8), "walk": (0.6, 2.0), "dart": (0.15, 0.3)}[mode]
                a = rng.uniform(0, 2 * np.pi)
                st = {"vx": speed * np.cos(a), "vy": speed * np.sin(a), "left": float(rng.uniform(low, high))}
                self.motion[oid] = st
            st["left"] -= dt
            t = self.things[oid]
            m = t.size / 2
            x, y = t.x + st["vx"] * dt, t.y + st["vy"] * dt
            if not m <= x <= self.width - m:
                st["vx"] = -st["vx"]
            if not m <= y <= self.height - m:
                st["vy"] = -st["vy"]
            self.things[oid] = replace(t, x=float(np.clip(x, m, self.width - m)), y=float(np.clip(y, m, self.height - m)))

    def surface(self) -> np.ndarray:
        return render(self.height, self.width, [self.things[i] for i in self.order], self.texture)

    def score(self, eid: int, gaze, answer) -> dict[str, Any]:
        """On its own shape: the eye's answer lands within one bin of its own shape."""
        t = self.things[eid]
        truth = self.fovea.bins_of(t.x - gaze[0], t.y - gaze[1])
        hit = answer is not None and truth is not None and max(
            abs(answer[0] - truth[0]), abs(answer[1] - truth[1])) <= 1
        centred = truth is not None and max(abs(truth[0] - self.fovea.middle), abs(truth[1] - self.fovea.middle)) <= 1
        return {"hit": bool(hit), "in_reach": truth is not None, "centred": bool(centred), "truth": truth}

    def step(self) -> dict[str, Any]:
        if self.animate:
            self.wander()
        self.clock += 1.0 / self.fps
        seen = self.eyes.see(self.surface())
        for e in seen["eyes"]:
            e.update(self.score(e["id"], e["gaze"], e["answer"]))
        return seen


# -- assays on frozen copies


def fovea_glance(path: str | Path, config: FovealConfig, trials: int, seed: int = 0,
                 kinds: tuple[str, ...] | None = None) -> dict:
    """First glance at a fresh scene from rest, no change channel: where is my shape?"""
    brain = Brain.load(path)
    cfg = config if kinds is None else config.with_(kinds=kinds)
    world = FovealWorld(cfg, seed)
    fv = world.fovea
    rng = np.random.default_rng(seed + 7)
    rows = []
    for k in range(trials):
        bucket = ("near", "mid", "far")[k % 3]
        world._scene()
        world.place(bucket)
        t = world.things[world.mine]
        target = fv.bins_of(t.x - world.gx, t.y - world.gy)
        if target is None:
            continue
        surface = world.surface()
        x = fv.see(fv.integral(surface), fv.integral(np.zeros_like(surface), 0.0), world.gx, world.gy)
        brain.reset()
        try:
            a = brain.act(x.reshape(1, -1), greedy=True)[0]
            d = max(abs(int(a[0]) - target[0]), abs(int(a[1]) - target[1]))
            ax, ay = fv.centre_of(int(a[0]), int(a[1]))
            err = float(np.hypot(ax - (t.x - world.gx), ay - (t.y - world.gy)))
            again = []
            for _ in range(2):
                brain.act(x.reshape(1, -1), greedy=True)
                again.append(int(brain.last_settlement["steps"]))
        except RuntimeError:
            d, err, again = cfg.bins, float("nan"), []
        guess = rng.integers(0, cfg.bins, size=2)
        rows.append({"bucket": bucket, "kind": t.kind, "hit": d <= 1, "exact": d == 0, "err_px": err,
                     "centre_hit": max(abs(fv.middle - target[0]), abs(fv.middle - target[1])) <= 1,
                     "random_hit": max(abs(int(guess[0]) - target[0]), abs(int(guess[1]) - target[1])) <= 1,
                     "still": again})

    def rate(sel, key):
        return None if not sel else round(float(np.mean([r[key] for r in sel])), 4)

    out: dict[str, Any] = {"trials": len(rows)}
    for name, sel in [("all", rows)] + [(b, [r for r in rows if r["bucket"] == b]) for b in ("near", "mid", "far")]:
        out[name] = {"trials": len(sel), "hit": rate(sel, "hit"), "exact": rate(sel, "exact"),
                     "err_px_median": round(float(np.nanmedian([r["err_px"] for r in sel])), 2) if sel else None,
                     "centre": rate(sel, "centre_hit"), "random": rate(sel, "random_hit")}
    out["by_kind"] = {k: rate([r for r in rows if r["kind"] == k], "hit") for k in sorted({r["kind"] for r in rows})}
    still = [s for r in rows for s in r["still"]]
    out["still_zero_share"] = round(float(np.mean(np.array(still) == 0)), 4) if still else None
    return out


def fovea_dart(path: str | Path, config: FovealConfig, trials: int, seed: int = 0, *,
               jumps=(10.0, 20.0, 30.0), others: int = 4, distractor: bool = False) -> dict:
    """The player drags a shape fast: it jumps while everything else stays still.

    The eye first settles on its own shape. Then its shape jumps by the given distance in a
    random direction (or, with ``distractor``, another shape jumps and the eye's own stays).
    The eye moves by its own answers; the count is whether it is back on its own shape (the
    shape within its middle bins) after one, two and three frames.
    """
    brain = Brain.load(path)
    fv = config.fovea()
    rng = np.random.default_rng(seed)
    out = {}
    for jump in jumps:
        on = {1: [], 2: [], 3: []}
        for _ in range(trials):
            scene = FovealScene(brain, config, seed=int(rng.integers(1 << 30)))
            scene.populate(others + 1, config.kinds, tracked=0)
            mine = scene.order[0]
            scene.eyes.open(mine, scene.things[mine].x, scene.things[mine].y)
            brain.reset()
            scene.eyes.streams = []
            for _ in range(4):
                scene.step()
            mover = scene.order[1] if distractor else mine
            t = scene.things[mover]
            for _ in range(20):
                a = rng.uniform(0, 2 * np.pi)
                nx, ny = t.x + jump * np.cos(a), t.y + jump * np.sin(a)
                if t.size / 2 <= nx <= scene.width - t.size / 2 and t.size / 2 <= ny <= scene.height - t.size / 2:
                    break
            scene.move(mover, nx, ny)
            for k in (1, 2, 3):
                scene.step()
                gaze = scene.eyes.gaze[mine]
                own = scene.things[mine]
                truth = fv.bins_of(own.x - gaze[0], own.y - gaze[1])
                on[k].append(truth is not None and max(abs(truth[0] - fv.middle), abs(truth[1] - fv.middle)) <= 1)
        out[str(jump)] = {str(k): round(float(np.mean(v)), 4) for k, v in on.items()}
    return out


def fovea_scene(path: str | Path, config: FovealConfig, *, objects: int, frames: int, seed: int = 0,
                kinds=FOVEA_KINDS, width: int = 160, height: int = 100) -> dict:
    """Every shape followed by its own foveated eye while all of them move on their own."""
    brain = Brain.load(path)
    scene = FovealScene(brain, config, width=width, height=height, seed=seed)
    scene.populate(objects, kinds)
    scene.animate = True
    centred, hit, in_reach, losses, sweeps = [], [], [], 0, []
    previous: dict[int, bool] = {}
    for _ in range(frames):
        f = scene.step()
        sweeps.append(f["sweeps"])
        for e in f["eyes"]:
            centred.append(e["centred"])
            hit.append(e["hit"])
            in_reach.append(e["in_reach"])
            if previous.get(e["id"], True) and not e["centred"]:
                losses += 1
            previous[e["id"]] = e["centred"]
    minutes = frames / scene.fps / 60
    return {"objects": objects, "frames": frames, "on_own_shape": round(float(np.mean(centred)), 4),
            "hit": round(float(np.mean(hit)), 4), "in_reach": round(float(np.mean(in_reach)), 4),
            "losses_per_eye_minute": round(losses / objects / minutes, 2),
            "sweeps_mean": round(float(np.mean(sweeps)), 2)}
