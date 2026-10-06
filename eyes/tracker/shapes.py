"""Diverse shapes for the many-object world, and their renderer.

A shape is a list of parts in units of the object's size: ellipses and polygons, drawn in order
at the object's brightness. A part marked as a hole shows the background beneath. Polygons
turn with the object's angle. Every pixel is supersampled 4×4 as in ``world.draw``, so a
sub-pixel move changes a few pixels a little and a jump changes many pixels a lot.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .world import SUPERSAMPLE, FaceShape

__all__ = ["HELD_OUT", "KINDS", "ROTATES", "TRAINED", "Thing", "render"]


def _rect(cx: float, cy: float, a: float, b: float) -> tuple[tuple[float, float], ...]:
    return ((cx - a, cy - b), (cx + a, cy - b), (cx + a, cy + b), (cx - a, cy + b))


def _star(points: int = 5, outer: float = 0.5, inner: float = 0.21) -> tuple[tuple[float, float], ...]:
    angles = -np.pi / 2 + np.arange(2 * points) * np.pi / points
    radii = np.where(np.arange(2 * points) % 2 == 0, outer, inner)
    return tuple((float(r * np.cos(t)), float(r * np.sin(t))) for r, t in zip(radii, angles, strict=True))


def _face() -> list[tuple]:
    f = FaceShape()
    return [
        ("ellipse", 0.0, 0.0, 0.5, f.head_ry, False),
        ("ellipse", -f.eye_dx, -f.eye_dy, f.eye_r, f.eye_r, True),
        ("ellipse", f.eye_dx, -f.eye_dy, f.eye_r, f.eye_r, True),
        ("poly", _rect(0.0, f.mouth_dy, f.mouth_w / 2, f.mouth_h / 2), True),
    ]


# A part is ("ellipse", cx, cy, a, b, hole) or ("poly", vertices, hole), in units of the size.
PARTS: dict[str, list[tuple]] = {
    "disc": [("ellipse", 0.0, 0.0, 0.5, 0.5, False)],
    "ring": [("ellipse", 0.0, 0.0, 0.5, 0.5, False), ("ellipse", 0.0, 0.0, 0.26, 0.26, True)],
    "square": [("poly", _rect(0.0, 0.0, 0.42, 0.42), False)],
    "frame": [("poly", _rect(0.0, 0.0, 0.46, 0.46), False),
              ("poly", _rect(0.0, 0.0, 0.24, 0.24), True)],
    "triangle": [("poly", ((0.0, -0.5), (0.5, 0.4), (-0.5, 0.4)), False)],
    "diamond": [("poly", ((0.0, -0.5), (0.36, 0.0), (0.0, 0.5), (-0.36, 0.0)), False)],
    "cross": [("poly", _rect(0.0, 0.0, 0.5, 0.14), False),
              ("poly", _rect(0.0, 0.0, 0.14, 0.5), False)],
    "bar": [("poly", _rect(0.0, 0.0, 0.5, 0.15), False)],
    "star": [("poly", _star(), False)],
    "tee": [("poly", _rect(0.0, -0.36, 0.5, 0.14), False),
            ("poly", _rect(0.0, 0.14, 0.14, 0.36), False)],
    "ell": [("poly", _rect(-0.3, 0.0, 0.14, 0.5), False),
            ("poly", _rect(0.02, 0.36, 0.46, 0.14), False)],
    "face": _face(),
}
TRAINED = ("disc", "ring", "square", "frame", "triangle", "diamond", "cross", "bar")
HELD_OUT = ("star", "tee", "ell", "face")
KINDS = TRAINED + HELD_OUT
ROTATES = frozenset({"square", "frame", "triangle", "diamond", "cross", "bar", "star", "tee", "ell"})


@dataclass(frozen=True)
class Thing:
    """One object: kind, centre and size in pixels, brightness, angle in radians."""

    kind: str
    x: float
    y: float
    size: float
    level: float = 0.8
    angle: float = 0.0


def _inside_polygon(px: np.ndarray, py: np.ndarray, vx: np.ndarray, vy: np.ndarray) -> np.ndarray:
    """Even-odd rule on a grid of points."""
    inside = np.zeros(np.broadcast(px, py).shape, dtype=bool)
    j = len(vx) - 1
    for i in range(len(vx)):
        crosses = (vy[i] > py) != (vy[j] > py)
        dy = vy[j] - vy[i]
        safe = np.where(dy == 0.0, 1.0, dy)
        x_cross = vx[i] + (py - vy[i]) * (vx[j] - vx[i]) / safe
        inside ^= crosses & (px < x_cross)
        j = i
    return inside


def render(height: int, width: int, things: list[Thing], background: np.ndarray | float,
           origin: tuple[int, int] = (0, 0)) -> np.ndarray:
    """Render ``things`` (surface coordinates) into a window whose top-left pixel is ``origin``.

    ``background`` is the window's own background (an array of the window's shape) or a level.
    Later things occlude earlier ones; a hole shows the background.
    """
    s = SUPERSAMPLE
    if np.isscalar(background):
        background = np.full((height, width), float(background))
    base = np.repeat(np.repeat(np.asarray(background, float), s, axis=0), s, axis=1)
    canvas = base.copy()
    ys = (np.arange(height * s) + 0.5) / s
    xs = (np.arange(width * s) + 0.5) / s
    ox, oy = origin
    for t in things:
        cx, cy = t.x - ox, t.y - oy
        reach = 0.75 * t.size + 0.5
        y0 = max(int(np.floor((cy - reach) * s)), 0)
        y1 = min(int(np.ceil((cy + reach) * s)) + 1, height * s)
        x0 = max(int(np.floor((cx - reach) * s)), 0)
        x1 = min(int(np.ceil((cx + reach) * s)) + 1, width * s)
        if y0 >= y1 or x0 >= x1:
            continue
        gy = ys[y0:y1, None]
        gx = xs[None, x0:x1]
        angle = t.angle if t.kind in ROTATES else 0.0
        c, sn = np.cos(angle), np.sin(angle)
        region = canvas[y0:y1, x0:x1]
        under = base[y0:y1, x0:x1]
        for part in PARTS[t.kind]:
            if part[0] == "ellipse":
                _, ex, ey, a, b, hole = part
                px = cx + (ex * c - ey * sn) * t.size
                py = cy + (ex * sn + ey * c) * t.size
                ra, rb = max(a * t.size, 0.35), max(b * t.size, 0.35)
                u = ((gx - px) * c + (gy - py) * sn) / ra
                v = (-(gx - px) * sn + (gy - py) * c) / rb
                inside = u * u + v * v <= 1.0
            else:
                _, vertices, hole = part
                v = np.asarray(vertices, float) * t.size
                vx = cx + v[:, 0] * c - v[:, 1] * sn
                vy = cy + v[:, 0] * sn + v[:, 1] * c
                inside = _inside_polygon(gx, gy, vx, vy)
            if hole:
                region[inside] = under[inside]
            else:
                region[inside] = t.level
    return canvas.reshape(height, s, width, s).mean(axis=(1, 3))
