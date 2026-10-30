"""Four fixed trials of a frozen checkpoint as frames, from the offscreen renderer or a replay.

    python -m arm2.render --checkpoint runs/x/brain.npz --out runs/x/frames/ep100
    python -m arm2.render --replay runs/x/frames/ep100/trial0.json --out /tmp/replay   # frames from a saved trajectory

Every trial always writes ``trial<k>.json`` with the full state per decision (qpos, ctrl, the
block's half side, order, command, event), so frames can be made anywhere from the trajectory.
PNG frames (320 x 240 RGB, a fixed camera over the table) are written when ``mujoco.Renderer``
can open a GL context; on a headless Linux machine try ``MUJOCO_GL=egl`` (mesa EGL) and
otherwise replay the trajectories where a display is available.
"""

from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path

import mujoco
import numpy as np

from .inspect import load_policy
from .job import prepare, run_trial
from .scene import ORDERS, PandaWorld

WIDTH, HEIGHT = 320, 240


def save_rgb_png(image: np.ndarray, path: Path) -> None:
    a = np.ascontiguousarray(image, dtype=np.uint8)
    h, w, _ = a.shape
    raw = b"".join(b"\x00" + a[y].tobytes() for y in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    Path(path).write_bytes(png)


class Painter:
    """The offscreen renderer with a fixed camera, or None when no GL context opens."""

    def __init__(self, model: mujoco.MjModel) -> None:
        self.renderer = mujoco.Renderer(model, HEIGHT, WIDTH)
        self.camera = mujoco.MjvCamera()
        self.camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.camera.lookat[:] = (0.52, 0.0, 0.08)
        self.camera.distance = 1.25
        self.camera.azimuth = 150.0
        self.camera.elevation = -32.0

    @classmethod
    def open(cls, model: mujoco.MjModel):
        try:
            return cls(model)
        except Exception as error:
            print(json.dumps({"renderer": "unavailable", "error": repr(error)[:200]}), flush=True)
            return None

    def frame(self, world: PandaWorld) -> np.ndarray:
        self.renderer.update_scene(world.data, self.camera)
        return self.renderer.render()


def record(world: PandaWorld, answer, event: str, d: int) -> dict:
    return {"decision": d, "qpos": np.round(world.data.qpos, 5).tolist(), "ctrl": np.round(world.data.ctrl, 5).tolist(),
            "half": world.half, "order": world.order, "lamp": ORDERS[world.order], "tip": np.round(world.tip(), 4).tolist(),
            "block": np.round(world.block_pos(), 4).tolist(), "holding": world.holding, "closed": world.closed,
            "command": None if answer is None else [int(v) for v in answer], "event": event}


def render_trials(checkpoint: str | Path, out: str | Path, *, pools: str, trials: int = 4, seed: int = 70_001, cap: int = 80,
                  velocity: bool = True, physics: str = "nominal", slip: bool = False) -> list[dict]:
    out = Path(out)
    policy = load_policy(checkpoint, pools, velocity=velocity, slip=slip)
    world = PandaWorld(seed, physics)
    painter = Painter.open(world.model)
    results = []
    for k in range(trials):
        folder = out / f"trial{k}"
        folder.mkdir(parents=True, exist_ok=True)
        prepare(world)
        policy.reset()
        trajectory: list[dict] = []

        def observer(d: int, w: PandaWorld, answer, event: str, folder=folder, trajectory=trajectory) -> None:
            trajectory.append(record(w, answer, event, d))
            if painter is not None:
                save_rgb_png(painter.frame(w), folder / f"{d:03d}.png")

        r = run_trial(world, policy, pools, cap, observer)
        rec = {"trial": k, "seed": seed, "physics": physics, "passed": sorted(r["passed"]), "decisions": r["decisions"],
               "steps": r["steps"], "gates": r["gates"], "frames": painter is not None, "trajectory": trajectory}
        (out / f"trial{k}.json").write_text(json.dumps(rec, indent=1))
        results.append({k2: v for k2, v in rec.items() if k2 != "trajectory"})
    return results


def replay(path: str | Path, out: str | Path) -> int:
    """Frames from a saved trajectory: the world set to each decision's state and painted."""
    rec = json.loads(Path(path).read_text())
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    world = PandaWorld(0, rec.get("physics", "nominal"))
    painter = Painter.open(world.model)
    if painter is None:
        raise RuntimeError("no GL context here either")
    for moment in rec["trajectory"]:
        world.model.geom_size[world.block_geom] = (moment["half"],) * 3
        world.order = moment["order"]
        world.new_order()
        world.data.qpos[:] = moment["qpos"]
        world.data.ctrl[:] = moment["ctrl"]
        mujoco.mj_forward(world.model, world.data)
        save_rgb_png(painter.frame(world), out / f"{moment['decision']:03d}.png")
    return len(rec["trajectory"])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--checkpoint", default=None)
    p.add_argument("--replay", default=None, help="a trial<k>.json to paint instead of running a checkpoint")
    p.add_argument("--out", required=True)
    p.add_argument("--pools", choices=("cartesian", "joint"), default="cartesian")
    p.add_argument("--trials", type=int, default=4)
    p.add_argument("--seed", type=int, default=70_001)
    p.add_argument("--cap", type=int, default=80)
    p.add_argument("--no-velocity", dest="no_velocity", action="store_true")
    p.add_argument("--physics", choices=("nominal", "heldout", "wide", "heldout2"), default="nominal")
    p.add_argument("--senses", choices=("basic", "slip"), default="basic")
    a = p.parse_args()
    if a.replay:
        print(json.dumps({"frames": replay(a.replay, a.out)}))
        return
    if not a.checkpoint:
        p.error("--checkpoint or --replay")
    print(json.dumps(render_trials(a.checkpoint, a.out, pools=a.pools, trials=a.trials, seed=a.seed, cap=a.cap,
                                   velocity=not a.no_velocity, physics=a.physics, slip=a.senses == "slip"), indent=1))


if __name__ == "__main__":
    main()
