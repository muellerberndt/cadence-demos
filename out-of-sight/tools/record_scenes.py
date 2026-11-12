"""Record steps and scenes with the tracking chamber's Python world, for the page and its parity test.

    python tools/record_scenes.py --world <cadence>/benchmarks/tracking --source "<branch> <commit>"

Writes, from the world's own ``step``, scripts and scene file format (``cadence-tracking-scene/1``):

- ``tests/fixtures/steps.json``: scripted runs of the world, one ``step`` call a step, with every
  step's command, moves, sounds and standard normal draws and the record the step returned;
  samples of the geometry helpers; the camera's view over the whole plane; and scene files beside
  what the world's own reader makes of them. ``tests/parity.mjs`` gives ``site/world.js`` the same
  inputs and compares every number.
- ``site/pack/reaches.json``: the recorded scenes the page plays: a person's hand that crosses
  the blind spot (one per kind: straight, slow, stop, turn), a sweep of the arm's own hand, and
  the room scene with a thing heard moving out of view.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]


def load_world(folder: Path):
    path = folder / "world.py"
    spec = importlib.util.spec_from_file_location("tracking_world", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["tracking_world"] = module
    spec.loader.exec_module(module)
    return module, hashlib.sha256(path.read_bytes()).hexdigest()


def nulls(rows: np.ndarray) -> list:
    """Rows of numbers with None in place of a row of NaN."""
    return [None if np.isnan(row).any() else [float(v) for v in row] for row in rows]


def run(W, world, commands, moves, sounds, rng, name: str) -> dict:
    """One scripted run, one ``step`` call a step, every input and record kept."""
    start = {"joints": world.joints.tolist(), "things": world.things.tolist(), "own": bool(world.own)}
    steps = []
    for t in range(len(commands)):
        noise = W.draws(rng, world)
        row = W.step(world, commands[t], moves[t], sounds[t], noise)
        steps.append({
            "command": commands[t].tolist(), "moves": moves[t].tolist(), "sounds": [bool(v) for v in sounds[t]],
            "noise": {k: v.tolist() for k, v in noise.items()},
            "record": {"truth": row["truth"].tolist(), "in_view": [bool(v) for v in row["in_view"]],
                       "report": nulls(row["report"]), "cue": nulls(row["cue"]),
                       "joints": row["joints"].tolist(), "commands": row["commands"].tolist()},
        })
    return {"name": name, "geometry": world.geometry.to_dict(), "start": start,
            "noise": {"camera": world.camera_noise, "motor": world.motor_noise, "encoder": world.encoder_noise,
                      "cue": list(world.cue_noise)}, "steps": steps}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--world", required=True, help="the folder that holds the chamber's world.py")
    p.add_argument("--source", default="", help="what to name as the world's source (branch and commit)")
    p.add_argument("--seed", type=int, default=320)
    a = p.parse_args()
    W, digest = load_world(Path(a.world))
    rng = np.random.default_rng(a.seed)
    g = W.Geometry()
    dt = 1.0 / 30.0

    runs = []
    # the arm's own hand on a sweep, two things at rest that sound at times
    for k in range(1):
        origin = np.array(W.OWN_STARTS[2][k])
        things = np.array([W.hand(g, origin), [0.5, 0.36], [-0.5, 1.0]])
        steps = 100
        commands = W.sweep(rng, g, origin, steps)
        moves = np.zeros((steps, 3, 2))
        sounds = rng.random((steps, 3)) < 0.05
        runs.append(run(W, W.World(g, origin.copy(), things, own=True), commands, moves, sounds, rng, f"own-sweep-{k}"))
    # a person's hand of every kind, the arm holding a pose and then moving once
    for k, kind in enumerate(("straight", "slow", "stop", "turn")):
        pose = np.array(W.POSES[2][k])
        start = np.array(W.OTHER_STARTS[k + 1])
        steps = 60
        hand_moves, _ = W.reach(rng, g, start, steps, kind, dt)
        moves = np.zeros((steps, 3, 2))
        moves[:, 0] = hand_moves
        moves[20:35, 2] = [0.004, -0.003]  # a thing carried a little way
        commands = np.zeros((steps, 2))
        commands[40:60] = (np.array(W.POSES[2][(k + 1) % 4]) - pose) / 20.0
        sounds = rng.random((steps, 3)) < 0.05
        things = np.array([start, [0.5, 0.36], [-0.5, 1.0]])
        runs.append(run(W, W.World(g, pose.copy(), things), commands, moves, sounds, rng, f"other-{kind}"))

    f = np.linspace(-0.2, 1.2, 57)
    pts = rng.uniform(-1.5, 1.5, (200, 4, 2))
    cues = np.stack([rng.uniform(-np.pi, np.pi, 100), rng.uniform(0.0, 2.5, 100)], axis=1)
    helpers = {
        "smooth": {"fraction": f.tolist(), "value": W._smooth(f).tolist()},
        "point_segment": {"points": pts[:, :3].tolist(),
                          "value": W._point_segment(pts[:, 0], pts[:, 1], pts[:, 2]).tolist()},
        "segments": {"points": pts.tolist(),
                     "value": W._segments(pts[:, 0], pts[:, 1], pts[:, 2], pts[:, 3]).tolist()},
        "polar": {"points": pts[:, 0].tolist(), "value": W.polar(g, pts[:, 0]).tolist()},
        "cartesian": {"cues": cues.tolist(), "value": W.cartesian(g, cues).tolist()},
    }
    # the camera's view over the whole plane, for three poses of the arm
    grid = np.stack(np.meshgrid(np.linspace(-1.05, 1.05, 43), np.linspace(-0.25, 1.45, 35)), -1).reshape(-1, 2)
    views = []
    for pose in W.POSES[2][:3]:
        views.append({"pose": list(pose), "visible": W.visible(g, grid, np.array(pose)).tolist()})
    helpers["view"] = {"geometry": g.to_dict(), "points": grid.tolist(), "views": views}
    # scene files as the world writes them, beside what its own reader makes of them
    def read(data: dict) -> dict:
        scene = W.from_dict(json.loads(json.dumps(data)))
        return {"steps": scene.steps, "things": scene.things, "case": scene.case, "dt": scene.dt,
                "kind": scene.kind, "event": scene.event,
                "truth": scene.truth.tolist(), "in_view": scene.in_view.tolist(),
                "report": [nulls(row) for row in scene.report], "cue": [nulls(row) for row in scene.cue],
                "commands": scene.commands.tolist(), "joints": scene.joints.tolist(),
                "start": scene.start.tolist(), "what": scene.what.tolist(),
                "unseen": scene.unseen().tolist(), "geometry": scene.geometry.to_dict()}

    files = []
    example = Path(a.world) / "scenes" / "example.json"
    if example.exists():
        files.append(("the chamber's example file", json.loads(example.read_text())))
    one = W.scenes("other", a.seed + 3, 1, steps=40)[0]
    files.append(("a person's hand", W.to_dict(one)))
    least = {k: v for k, v in W.to_dict(one).items() if k in ("format", "case", "report", "in_view", "truth")}
    files.append(("the least a file holds", least))
    files.append(("the arm's own hand", W.to_dict(W.scenes("own", a.seed + 4, 1, steps=40)[0])))
    files.append(("a room of several things", W.to_dict(W.room_scene(np.random.default_rng(a.seed + 5), kind="demo", steps=60))))
    files = [{"name": name, "file": data, "read": read(data)} for name, data in files]
    # the controls that learn nothing, on scenes of one thing
    sys.path.insert(0, str(Path(a.world).resolve()))
    import tracking as T  # the chamber itself: its controls and their settings

    controls = []
    settings = {"q": 1e-5, "r": 0.01}
    for scene in W.scenes("other", a.seed + 6, 3, steps=90):
        last, _ = T.follow(scene, T.Still)
        kalman, radius = T.follow(scene, T.ConstantVelocity, settings)
        controls.append({"file": W.to_dict(scene), "settings": settings, "rate": T.RATE,
                         "last_seen": last[:, 0].tolist(), "kalman": kalman[:, 0].tolist(),
                         "kalman_radius": radius[:, 0].tolist()})
    out = {"format": "cadence-out-of-sight-parity/3", "world_sha256": digest, "source": a.source,
           "scene_format": W.FORMAT, "runs": runs, "helpers": helpers, "files": files,
           "controls": controls}
    path = HERE / "tests" / "fixtures" / "steps.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out) + "\n")
    print("wrote", path, f"{path.stat().st_size / 1024:.0f} KB", len(runs), "runs")

    # -- the scenes the page plays
    reaches = []
    want = ["straight", "slow", "stop", "turn"]
    seed = a.seed
    while want and seed < a.seed + 400:
        seed += 1
        for scene in W.scenes("other", seed, 4, steps=180):
            kind = W.panel(scene)
            seen = scene.in_view[:, 0]
            hidden = int((~seen).sum())
            if kind in want and 25 <= hidden <= 90 and bool(seen[-10:].all()) and bool(seen[:15].all()):
                want.remove(kind)
                scene.name = f"a person's hand, {kind}"
                reaches.append(W.to_dict(scene))
    for scene in W.scenes("own", a.seed + 7, 12, steps=240):
        seen = scene.in_view[:, 0]
        hidden = int((~seen).sum())
        if 40 <= hidden <= 140 and bool(seen[:10].all()):
            scene.name = "the arm's own hand, a sweep"
            reaches.append(W.to_dict(scene))
            break
    try:
        room = W.room_scene(np.random.default_rng(a.seed + 11), kind="demo", steps=240)
        room.name = "the room: a hand, and a thing heard moving out of view"
        reaches.append(W.to_dict(room))
    except Exception as error:  # the room scene is the newest part of the world
        print("no room scene:", error)
    order = ["straight", "slow", "stop", "turn", "sweep", "demo"]
    reaches.sort(key=lambda r: order.index(r["kind"]) if r["kind"] in order else 99)
    out = {"format": "cadence-out-of-sight-reaches/1", "world_sha256": digest, "source": a.source,
           "scene_format": W.FORMAT, "reaches": reaches}
    path = HERE / "site" / "pack" / "reaches.json"
    path.write_text(json.dumps(out) + "\n")
    print("wrote", path, f"{path.stat().st_size / 1024:.0f} KB",
          [(r["name"], len(r["truth"])) for r in reaches])


if __name__ == "__main__":
    main()
