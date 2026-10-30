"""Two eyes in a head above the base, looking at the table: pinhole cameras and a rasterizer.

Each eye is a small grey retina. The scene is drawn from the world's own geometry: the table,
the bins, the block, the lamps, the arm's links and the bright hand, painted far to near. The
retinas are the only sight the brain has; the arm's own links are in the picture like anything
else. A second channel per eye can carry change, the difference to the previous frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .world import BIN_SIDE, BLOCK, LAMP, ORDERS, POSITION_BINS, TABLE_X, TABLE_Y, World

BRIGHT = dict(table=0.22, bin=0.04, block=0.65, link=0.42, hand=1.0, lamp_on=0.95, lamp_off=0.25, background=0.0)
# Cone channels beside brightness: the block is red, the hand green, the lamps blue (brighter when
# lit); everything else is grey and shows in no cone channel.
RED = dict(table=0.0, bin=0.0, block=1.0, link=0.0, hand=0.0, lamp_on=0.0, lamp_off=0.0, background=0.0)
GREEN = dict(table=0.0, bin=0.0, block=0.0, link=0.0, hand=1.0, lamp_on=0.0, lamp_off=0.0, background=0.0)
BLUE = dict(table=0.0, bin=0.0, block=0.0, link=0.0, hand=0.0, lamp_on=1.0, lamp_off=0.25, background=0.0)
CONES = (RED, GREEN, BLUE)
LINK_RADIUS = (0.030, 0.024, 0.016)
LAMP_RADIUS = 0.04
HAND_HALF = 0.035


@dataclass(frozen=True)
class HeadSpec:
    size: int = 40  # retina side in pixels
    eyes: int = 2
    baseline: float = 0.10  # metres between the eyes, along the head's right
    position: tuple[float, float, float] = (-0.34, -0.10, 0.58)  # a mast beside the base
    target: tuple[float, float, float] = (0.02, 0.31, 0.0)
    fov: float = 50.0  # degrees
    change: bool = False
    colour: bool = False  # three cone channels per eye beside brightness: red, green, blue
    bright: dict = field(default_factory=lambda: dict(BRIGHT))

    @property
    def kinds(self) -> int:
        """Channels per eye: brightness, the cones, the change."""
        return 1 + (3 if self.colour else 0) + int(self.change)

    @property
    def channels(self) -> int:
        return self.eyes * self.kinds

    @property
    def retina(self) -> int:
        return self.channels * self.size * self.size


class Camera:
    """A pinhole camera at ``eye`` looking at ``target``; rows go down the image."""

    def __init__(self, eye, target, fov: float, size: int) -> None:
        self.eye = np.asarray(eye, dtype=float)
        f = np.asarray(target, dtype=float) - self.eye
        self.f = f / np.linalg.norm(f)
        up = np.array([0.0, 0.0, 1.0])
        if abs(float(self.f @ up)) > 0.999:  # looking straight down: the image's up is forward
            up = np.array([0.0, 1.0, 0.0])
        r = np.cross(self.f, up)
        self.r = r / np.linalg.norm(r)
        self.u = np.cross(self.r, self.f)
        self.size = size
        self.focal = (size / 2) / np.tan(np.radians(fov) / 2)

    def project(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Pixel coordinates (k, 2) as (column, row) and depths (k,) of world points (k, 3)."""
        d = np.atleast_2d(points) - self.eye
        z = d @ self.f
        z = np.maximum(z, 1e-3)
        x = d @ self.r
        y = d @ self.u
        col = self.size / 2 + self.focal * x / z
        row = self.size / 2 - self.focal * y / z
        return np.stack([col, row], axis=1), z

    def radius_px(self, radius: float, depth: float) -> float:
        return float(self.focal * radius / max(depth, 1e-3))


def fill_convex(image: np.ndarray, polygon: np.ndarray, value: float) -> None:
    """Paint the convex polygon (k, 2) in pixel coordinates onto ``image`` in place."""
    size = image.shape[0]
    lo = np.floor(polygon.min(axis=0)).astype(int) - 1
    hi = np.ceil(polygon.max(axis=0)).astype(int) + 1
    c0, r0 = max(lo[0], 0), max(lo[1], 0)
    c1, r1 = min(hi[0], size - 1), min(hi[1], size - 1)
    if c1 < c0 or r1 < r0:
        return
    cols, rows = np.meshgrid(np.arange(c0, c1 + 1) + 0.5, np.arange(r0, r1 + 1) + 0.5)
    inside = np.ones(cols.shape, dtype=bool)
    sign = 0.0
    k = len(polygon)
    for i in range(k):
        a, b = polygon[i], polygon[(i + 1) % k]
        cross = (b[0] - a[0]) * (rows - a[1]) - (b[1] - a[1]) * (cols - a[0])
        if sign == 0.0:
            area = 0.0
            for j in range(k):
                p, q = polygon[j], polygon[(j + 1) % k]
                area += p[0] * q[1] - q[0] * p[1]
            sign = 1.0 if area >= 0 else -1.0
        inside &= sign * cross >= -1e-9
    image[r0:r1 + 1, c0:c1 + 1][inside] = value


def disc(centre: np.ndarray, radius: float, sides: int = 10) -> np.ndarray:
    angles = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    return centre + radius * np.stack([np.cos(angles), np.sin(angles)], axis=1)


def thick_segment(a: np.ndarray, b: np.ndarray, radius: float) -> np.ndarray:
    d = b - a
    n = np.linalg.norm(d)
    if n < 1e-9:
        return disc(a, radius)
    normal = np.array([-d[1], d[0]]) / n * radius
    return np.array([a + normal, b + normal, b - normal, a - normal])


def render(world: World, camera: Camera, bright: dict | None = None) -> np.ndarray:
    """One retina image (size, size) of the cell as the camera sees it, far to near."""
    b = BRIGHT if bright is None else bright
    image = np.full((camera.size, camera.size), b["background"])
    floor: list[tuple[float, np.ndarray, float]] = []  # the table and the bins, in that order
    items: list[tuple[float, np.ndarray, float]] = []

    def quad(corners, value, flat=False):
        px, z = camera.project(np.asarray(corners, dtype=float))
        (floor if flat else items).append((float(z.mean()), px, value))

    x0, x1 = TABLE_X
    y0, y1 = TABLE_Y
    quad([(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)], b["table"], flat=True)
    half = BIN_SIDE / 2
    for bx, by in world.bins.values():
        quad([(bx - half, by - half, 0.001), (bx + half, by - half, 0.001), (bx + half, by + half, 0.001), (bx - half, by + half, 0.001)], b["bin"], flat=True)
    for name, pos in LAMP.items():
        px, z = camera.project(np.array([pos]))
        on = ORDERS[world.order] == name
        items.append((float(z[0]), disc(px[0], camera.radius_px(LAMP_RADIUS, float(z[0]))), b["lamp_on"] if on else b["lamp_off"]))
    cx, cy, cz = world.block
    h = BLOCK / 2
    corners = np.array([[cx + sx * h, cy + sy * h, cz + sz * h] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    faces = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    for face in faces:
        quad(corners[list(face)], b["block"])
    pts = world.points()
    px, z = camera.project(pts)
    for i in range(3):
        depth = float((z[i] + z[i + 1]) / 2)
        items.append((depth, thick_segment(px[i], px[i + 1], camera.radius_px(LINK_RADIUS[i], depth)), b["link"]))
    hand_px, hand_z = px[3], float(z[3])
    r = camera.radius_px(HAND_HALF, hand_z)
    items.append((hand_z - 1e-3, np.array([hand_px + (-r, -r), hand_px + (r, -r), hand_px + (r, r), hand_px + (-r, r)]), b["hand"]))
    for _, polygon, value in floor + sorted(items, key=lambda item: -item[0]):
        fill_convex(image, polygon, value)
    return np.clip(image, 0.0, 1.0)


class Eyes:
    """The head's eyes: see the world, carry the previous frame for the change channel."""

    def __init__(self, spec: HeadSpec = HeadSpec()) -> None:
        self.spec = spec
        centre = Camera(spec.position, spec.target, spec.fov, spec.size)
        offsets = [0.0] if spec.eyes == 1 else [-spec.baseline / 2, spec.baseline / 2]
        self.cameras = [Camera(centre.eye + d * centre.r, spec.target, spec.fov, spec.size) for d in offsets]
        self.previous: list[np.ndarray | None] = [None] * len(self.cameras)

    def reset(self) -> None:
        self.previous = [None] * len(self.cameras)

    def see(self, world: World) -> np.ndarray:
        """Retina channels (channels, size, size): brightness per eye, then change if declared."""
        frames = [render(world, cam, self.spec.bright) for cam in self.cameras]
        channels = list(frames)
        if self.spec.colour:
            for cone in CONES:
                channels += [render(world, cam, cone) for cam in self.cameras]
        if self.spec.change:
            for i, frame in enumerate(frames):
                prev = self.previous[i]
                channels.append(np.zeros_like(frame) if prev is None else np.abs(frame - prev))
        self.previous = [f.copy() for f in frames]
        return np.stack(channels)

    def inputs(self, world: World) -> np.ndarray:
        """Everything the brain senses this moment: the retinas, then the body."""
        return np.concatenate([self.see(world).ravel(), world.body()])

    def pixel_bins(self, point: np.ndarray, bins: int = POSITION_BINS) -> tuple[int, int]:
        """Where a world point falls in the first eye's image: (column bin, row bin)."""
        px, _ = self.cameras[0].project(np.asarray(point, dtype=float)[None])
        size = self.spec.size
        col = int(np.clip(np.floor(px[0, 0] / size * bins), 0, bins - 1))
        row = int(np.clip(np.floor(px[0, 1] / size * bins), 0, bins - 1))
        return col, row

    def labels(self, world: World) -> list[int]:
        """What the eye is taught to read, in its own coordinates: the block's and the hand's
        column and row in the first eye, whether the block is held, and which lamp is on."""
        bc, br = self.pixel_bins(world.block)
        hc, hr = self.pixel_bins(world.tip())
        return [bc, br, hc, hr, int(world.holding), int(world.order)]

    def map_labels(self, world: World, sheet: int) -> list[int]:
        """The first eye's map cell under the block, the fingertip and the lit lamp (the first
        lamp when none is lit), for teaching the maps directly."""
        from .anatomy import map_label  # local import: anatomy imports this module

        cam, size = self.cameras[0], self.spec.size
        lamp = LAMP[ORDERS[world.order]] if world.order else LAMP["A"]
        out = []
        for point in (world.block, world.tip(), np.asarray(lamp, dtype=float)):
            px, _ = cam.project(np.asarray(point, dtype=float)[None])
            out.append(map_label(float(px[0, 0]), float(px[0, 1]), size, sheet))
        return out

    def block_visible(self, world: World, frames: np.ndarray | None = None, pixels: int = 2) -> bool:
        """Whether the first eye sees at least ``pixels`` of the block this moment."""
        frame = render(world, self.cameras[0], self.spec.bright) if frames is None else frames[0]
        return int((frame == self.spec.bright["block"]).sum()) >= pixels
