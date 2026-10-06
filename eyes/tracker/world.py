"""The world: a grey surface with a target object, distractors, motion and occlusion.

The world renders pixels and knows where the target is. It never supplies an answer to the
brain; the brain reports a position and the world then reveals where the target was. Objects
are drawn with sub-pixel anti-aliasing, so a small movement changes a few pixels a little and
a jump changes many pixels a lot.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

__all__ = [
    "FaceShape",
    "Frame",
    "Placed",
    "World",
    "WorldConfig",
    "draw",
    "primitives",
]

SUPERSAMPLE = 4


@dataclass(frozen=True)
class FaceShape:
    """One face identity, in units of the head width."""

    eye_dx: float = 0.21
    eye_dy: float = 0.14
    eye_r: float = 0.10
    mouth_w: float = 0.40
    mouth_dy: float = 0.27
    mouth_h: float = 0.10
    head_ry: float = 0.60
    skin: float = 0.80
    dark: float = 0.08

    @staticmethod
    def sample(rng: np.random.Generator) -> FaceShape:
        return FaceShape(
            eye_dx=float(rng.uniform(0.17, 0.25)),
            eye_dy=float(rng.uniform(0.10, 0.18)),
            eye_r=float(rng.uniform(0.08, 0.12)),
            mouth_w=float(rng.uniform(0.30, 0.50)),
            mouth_dy=float(rng.uniform(0.22, 0.31)),
            head_ry=float(rng.uniform(0.52, 0.66)),
            skin=float(rng.uniform(0.65, 0.90)),
        )


# A primitive is (kind, cx, cy, a, b, level) in units of the object size, drawn in order.
Primitive = tuple[str, float, float, float, float, float]


def primitives(kind: str, face: FaceShape = FaceShape()) -> list[Primitive]:
    """The drawing of one object kind, centred at the origin, in units of its size."""
    f = face
    head = ("ellipse", 0.0, 0.0, 0.5, f.head_ry, f.skin)
    eyes = [
        ("ellipse", -f.eye_dx, -f.eye_dy, f.eye_r, f.eye_r, f.dark),
        ("ellipse", f.eye_dx, -f.eye_dy, f.eye_r, f.eye_r, f.dark),
    ]
    mouth = ("rect", 0.0, f.mouth_dy, f.mouth_w / 2, f.mouth_h / 2, f.dark)
    if kind == "dot":
        return [("ellipse", 0.0, 0.0, 0.5, 0.5, 1.0)]
    if kind == "face":
        return [head, *eyes, mouth]
    if kind == "inverted":
        return [head] + [(k, x, -y, a, b, v) for k, x, y, a, b, v in (*eyes, mouth)]
    if kind == "scrambled":
        # The same parts with the configuration broken: the mouth stands upright on one side,
        # one eye sits low on the other side, the other eye sits in the middle.
        return [
            head,
            ("ellipse", 0.0, 0.0, f.eye_r, f.eye_r, f.dark),
            ("ellipse", f.eye_dx + 0.04, f.mouth_dy - 0.02, f.eye_r, f.eye_r, f.dark),
            ("rect", -f.eye_dx - 0.04, -0.05, f.mouth_h / 2, f.mouth_w / 2, f.dark),
        ]
    if kind == "blank":
        return [head]
    if kind == "ring":
        return [
            ("ellipse", 0.0, 0.0, 0.5, f.head_ry, f.skin),
            ("ellipse", 0.0, 0.0, 0.28, f.head_ry - 0.22, f.dark),
        ]
    if kind == "square":
        return [("rect", 0.0, 0.0, 0.45, 0.45, f.skin), ("rect", 0.0, 0.0, 0.12, 0.12, f.dark)]
    if kind == "cross":
        return [("rect", 0.0, 0.0, 0.5, 0.13, f.skin), ("rect", 0.0, 0.0, 0.13, 0.5, f.skin)]
    if kind == "cover":
        # An occluder at the background level: whatever lies under it is hidden.
        return [("rect", 0.0, 0.0, 0.62, 0.62, 0.1)]
    raise ValueError(f"unknown object kind {kind!r}")


@dataclass(frozen=True)
class Placed:
    """An object instance on the surface: kind, centre in pixels, size in pixels, identity."""

    kind: str
    x: float
    y: float
    size: float
    face: FaceShape = FaceShape()


def draw(height: int, width: int, objects: list[Placed], background: np.ndarray) -> np.ndarray:
    """Render objects over a background with sub-pixel anti-aliasing; later objects occlude."""
    s = SUPERSAMPLE
    ys = (np.arange(height * s) + 0.5) / s
    xs = (np.arange(width * s) + 0.5) / s
    canvas = np.repeat(np.repeat(background, s, axis=0), s, axis=1).astype(float)
    for obj in objects:
        for kind, cx, cy, a, b, level in primitives(obj.kind, obj.face):
            px, py = obj.x + cx * obj.size, obj.y + cy * obj.size
            ra, rb = max(a * obj.size, 0.35), max(b * obj.size, 0.35)
            y0 = max(int(np.floor((py - rb) * s)), 0)
            y1 = min(int(np.ceil((py + rb) * s)) + 1, height * s)
            x0 = max(int(np.floor((px - ra) * s)), 0)
            x1 = min(int(np.ceil((px + ra) * s)) + 1, width * s)
            if y0 >= y1 or x0 >= x1:
                continue
            dy = (ys[y0:y1, None] - py) / rb
            dx = (xs[None, x0:x1] - px) / ra
            if kind == "ellipse":
                inside = dx * dx + dy * dy <= 1.0
            else:
                inside = (np.abs(dx) <= 1.0) & (np.abs(dy) <= 1.0)
            region = canvas[y0:y1, x0:x1]
            region[inside] = level
    return canvas.reshape(height, s, width, s).mean(axis=(1, 3))


@dataclass(frozen=True)
class WorldConfig:
    """The surface, the target, its motion and its company."""

    size: int = 16
    bins: int = 8
    target: str = "dot"
    target_size: float = 3.6
    distractors: tuple[str, ...] = ()
    count: int = 0
    distractor_size: float | None = None
    stay: float = 0.2
    jump: float = 0.1
    step: float = 0.7
    momentum: float = 0.0
    occlusion: float = 0.0
    occlusion_ticks: tuple[int, int] = (2, 6)
    background: float = 0.1
    texture: float = 0.0
    flicker: float = 0.0
    identities: int = 1

    @property
    def margin(self) -> float:
        return max(self.target_size, self.distractor_size or self.target_size) / 2 + 0.5

    def with_(self, **changes: object) -> WorldConfig:
        return replace(self, **changes)


@dataclass
class Frame:
    """One tick of the world: pixels and the truth about the target."""

    pixels: np.ndarray
    x: float
    y: float
    visible: bool
    event: str
    displacement: float
    target: tuple[int, int]
    objects: list[Placed] = field(default_factory=list)


class World:
    """A continuing scene. ``step`` advances the target and renders the next frame."""

    def __init__(self, config: WorldConfig, seed: int = 0) -> None:
        self.config = config
        self.rng = np.random.default_rng(seed)
        self.faces = [FaceShape()] + [
            FaceShape.sample(self.rng) for _ in range(max(config.identities, 1) - 1)
        ]
        self.face = self.faces[0]
        self.backdrop = self._backdrop()
        self.x, self.y = self._anywhere()
        self.vx = self.vy = 0.0
        self.hidden_for = 0
        self.others = self._distractors()
        self.ticks = 0

    # -- geometry

    def cell(self) -> float:
        return self.config.size / self.config.bins

    def bins_of(self, x: float, y: float) -> tuple[int, int]:
        c, b = self.cell(), self.config.bins
        return min(max(int(x / c), 0), b - 1), min(max(int(y / c), 0), b - 1)

    def centre_of(self, bx: int, by: int) -> tuple[float, float]:
        c = self.cell()
        return (bx + 0.5) * c, (by + 0.5) * c

    def _anywhere(self) -> tuple[float, float]:
        m, s = self.config.margin, self.config.size
        return float(self.rng.uniform(m, s - m)), float(self.rng.uniform(m, s - m))

    def _backdrop(self) -> np.ndarray:
        cfg = self.config
        base = np.full((cfg.size, cfg.size), cfg.background)
        if cfg.texture:
            base = base + cfg.texture * self.rng.standard_normal(base.shape)
        return np.clip(base, 0.0, 1.0)

    def _distractors(self) -> list[Placed]:
        cfg = self.config
        out: list[Placed] = []
        size = cfg.distractor_size or cfg.target_size
        for k in range(cfg.count):
            kind = cfg.distractors[k % len(cfg.distractors)]
            for _ in range(50):
                x, y = self._anywhere()
                far = np.hypot(x - self.x, y - self.y) >= 0.9 * (size + cfg.target_size) / 2
                if far and all(np.hypot(x - o.x, y - o.y) >= size for o in out):
                    break
            out.append(Placed(kind, x, y, size, self.face))
        return out

    # -- dynamics

    def place(self, x: float, y: float) -> None:
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0

    def change(self, **changes: object) -> None:
        """A disturbance: a new configuration in the same continuing scene."""
        self.config = replace(self.config, **changes)
        if "texture" in changes or "background" in changes:
            self.backdrop = self._backdrop()
        if "count" in changes or "distractors" in changes or "distractor_size" in changes:
            self.others = self._distractors()

    def wear(self, identity: int) -> None:
        self.face = self.faces[identity % len(self.faces)]
        self.others = [replace(o, face=self.face) for o in self.others]

    def _move(self) -> str:
        cfg = self.config
        u = self.rng.random()
        if u < cfg.jump:
            self.place(*self._anywhere())
            self.others = self._distractors()
            return "jump"
        if u < cfg.jump + cfg.stay:
            self.vx = self.vy = 0.0
            return "stay"
        m, s = cfg.margin, cfg.size
        self.vx = cfg.momentum * self.vx + cfg.step * float(self.rng.standard_normal())
        self.vy = cfg.momentum * self.vy + cfg.step * float(self.rng.standard_normal())
        x, y = self.x + self.vx, self.y + self.vy
        if not m <= x <= s - m:
            self.vx = -self.vx
            x = float(np.clip(x, m, s - m))
        if not m <= y <= s - m:
            self.vy = -self.vy
            y = float(np.clip(y, m, s - m))
        self.x, self.y = x, y
        return "step"

    def render(self, objects: list[Placed]) -> np.ndarray:
        cfg = self.config
        pixels = draw(cfg.size, cfg.size, objects, self.backdrop)
        if cfg.flicker:
            pixels = pixels + cfg.flicker * self.rng.standard_normal(pixels.shape)
        return np.clip(pixels, 0.0, 1.0)

    def target(self) -> Placed:
        return Placed(self.config.target, self.x, self.y, self.config.target_size, self.face)

    def frame(self, event: str = "stay", displacement: float = 0.0) -> Frame:
        visible = self.hidden_for == 0
        objects = list(self.others) + ([self.target()] if visible else [])
        return Frame(
            self.render(objects), self.x, self.y, visible, event, displacement,
            self.bins_of(self.x, self.y), objects,
        )

    def step(self) -> Frame:
        """Advance one tick and render it."""
        x0, y0 = self.x, self.y
        event = self._move() if self.ticks else "start"
        self.ticks += 1
        if self.hidden_for:
            self.hidden_for -= 1
        elif self.config.occlusion and self.rng.random() < self.config.occlusion:
            low, high = self.config.occlusion_ticks
            self.hidden_for = int(self.rng.integers(low, high + 1))
        return self.frame(event, float(np.hypot(self.x - x0, self.y - y0)))
