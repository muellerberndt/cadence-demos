import hashlib
import json
from pathlib import Path

import numpy as np

from tracker.eye_host import Host
from tracker.eyes import EyeConfig, window_dart
from tracker.shapes import Thing, render

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "web" / "pack"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_pack_carries_these_sources_and_its_manifest_holds():
    manifest = json.loads((PACK / "manifest.json").read_text())
    for name in manifest["sources"]:
        packed = PACK / "py" / "tracker" / name
        assert packed.read_bytes() == (ROOT / "tracker" / name).read_bytes(), name
        assert sha(packed) == manifest["sources_sha256"][name]
    assert sha(PACK / manifest["wheel"]) == manifest["wheel_sha256"]
    assert sha(PACK / manifest["brain"]) == manifest["brain_sha256"]
    assert manifest["eye"] == "fovea" and manifest["cadence"] == "0.74.0"


def test_the_packed_eye_follows_a_shape_from_pixels(tmp_path):
    manifest = json.loads((PACK / "manifest.json").read_text())
    host = Host(str(PACK / manifest["brain"]), 0, manifest["bins"], manifest["width"],
                manifest["height"], eye="fovea", fovea=manifest["fovea"])
    assert host.brain.learner.config.tolerance == manifest["tolerance"]
    host.handle_json(json.dumps({"op": "open", "id": 1, "x": 60, "y": 40}))
    shape = Thing("disc", 66.0, 44.0, 8, 0.9)
    for _ in range(4):
        out = json.loads(host.see(render(100, 160, [shape], 0.1).astype(np.float32)))
    gx, gy = out["eyes"][0]["next"]
    assert abs(gx - shape.x) <= 2 and abs(gy - shape.y) <= 2
    assert json.loads(host.see(render(100, 160, [shape], 0.1).astype(np.float32)))["sweeps"] == 0


def test_the_window_eye_control_loads_and_runs():
    out = window_dart(ROOT / "controls" / "window-eye.npz", EyeConfig(), 2, seed=3, jumps=(10.0,), others=2)
    assert set(out["10.0"]) == {"1", "2", "3"}
