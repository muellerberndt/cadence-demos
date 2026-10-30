"""Pictures without any image library: grey PNGs of what the eyes see and a top view.

    python -m arm.view --out runs/view --seed 3
"""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

import numpy as np

from .eyes import Camera, Eyes, HeadSpec, render
from .world import ArmSpec, World


def save_png(image: np.ndarray, path: Path, scale: int = 1) -> None:
    """Write a grey image in [0, 1] as an 8-bit PNG, enlarged ``scale`` times."""
    a = (np.clip(image, 0, 1) * 255).astype(np.uint8)
    if scale > 1:
        a = np.repeat(np.repeat(a, scale, axis=0), scale, axis=1)
    h, w = a.shape
    raw = b"".join(b"\x00" + a[y].tobytes() for y in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    Path(path).write_bytes(png)


def top_view(world: World, size: int = 128) -> np.ndarray:
    cam = Camera((0.0, 0.30, 1.2), (0.0, 0.30, 0.0), 40.0, size)
    return render(world, cam)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--scenes", type=int, default=4)
    p.add_argument("--size", type=int, default=32)
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    world, eyes = World(ArmSpec(), a.seed), Eyes(HeadSpec(size=a.size))
    for k in range(a.scenes):
        if k:
            world.randomize()
        frames = eyes.see(world)
        save_png(frames[0], out / f"scene{k}_left.png", 8)
        save_png(frames[1], out / f"scene{k}_right.png", 8)
        save_png(top_view(world), out / f"scene{k}_top.png", 3)
        print(k, "tip", np.round(world.tip(), 3), "block", np.round(world.block, 3), "order", world.order, "holding", world.holding)


if __name__ == "__main__":
    main()
