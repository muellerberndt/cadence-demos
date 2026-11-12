"""The page's host for the what-where map, run natively on the pack's own wheel and map file:
the same files the worker runs in Pyodide.

    python -m pytest tests/test_map_host.py      # from out-of-sight/; node runs the page's rule for what the camera sees

The wheel named in ``site/pack/manifest.json`` is unpacked into a temporary folder and imported
from there, so the test reads the library the page runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
PACK = HERE / "site" / "pack"
MANIFEST = json.loads((PACK / "manifest.json").read_text())
_WHEEL = Path(tempfile.mkdtemp(prefix="oos-wheel-"))
with zipfile.ZipFile(PACK / MANIFEST["wheel"]) as archive:
    archive.extractall(_WHEEL)
sys.path.insert(0, str(_WHEEL))
sys.path.insert(0, str(PACK / "py"))
warnings.simplefilter("ignore")

from cadence.space.map import Map
from spacebrain.map_host import MapHost

MAP_FILE = PACK / "map" / MANIFEST["map"]["file"]
CONFIG = {"map": {"path": str(MAP_FILE), "kinds": MANIFEST["map"]["kinds"], "label": MANIFEST["map"]["label"]}}
SCENES = {"default": HERE / "tests" / "fixtures" / "promise-scene.json",
          "merged": HERE / "tests" / "fixtures" / "promise-merged-shadows-scene.json"}
HAND = MANIFEST["map"]["kinds"]["hand"]


def lit_cells(scene: Path, centers: np.ndarray) -> np.ndarray:
    """``(steps, cells)`` flags: the cells the camera sees, by the page's own rule (node)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(np.asarray(centers).tolist(), handle)
    text = subprocess.run(["node", str(HERE / "tests" / "lit_cells.mjs"), str(scene), handle.name],
                          check=True, capture_output=True, text=True).stdout
    return np.array([[c == "1" for c in line] for line in text.split()], dtype=bool)


def visible(geometry: dict, points: np.ndarray, joints: list[float]) -> np.ndarray:
    """``visible`` of site/world.js for many places at once (not the arm's own end): whether the
    camera sees each place. Checked against the page's own rule at every cell of every step."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    cam = geometry["camera"]
    eye = np.asarray(cam["position"], dtype=np.float64)
    rel = pts - eye
    far = np.hypot(rel[:, 0], rel[:, 1])
    bearing = np.abs((np.arctan2(rel[:, 1], rel[:, 0]) - cam["heading"] + np.pi) % (2 * np.pi) - np.pi)
    x0, x1, y0, y1 = geometry["plane"]
    ok = (far <= cam["range"]) & (bearing <= cam["fov"] / 2) & (pts[:, 0] >= x0) & (pts[:, 0] <= x1) & (pts[:, 1] >= y0) & (pts[:, 1] <= y1)

    def to_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:  # p: (n, 2); a, b: (n, 2) or (2,)
        ab, ap = b - a, p - a
        t = np.clip((ap * ab).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-12), 0.0, 1.0)
        return np.hypot(*(p - (a + t[..., None] * ab)).T)

    for o in geometry["occluders"]:
        c = np.broadcast_to(np.asarray(o["center"], dtype=np.float64), pts.shape)
        ok &= to_segment(c, np.broadcast_to(eye, pts.shape), pts) > o["radius"]
    arm, angle, chain = geometry["arm"], 0.0, [np.asarray(geometry["arm"]["base"], dtype=np.float64)]
    for length, q in zip(arm["lengths"], joints, strict=False):
        angle += q
        chain.append(chain[-1] + length * np.array([np.cos(angle), np.sin(angle)]))
    e = np.broadcast_to(eye, pts.shape)
    cross = lambda u, v: u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]  # noqa: E731
    for a, b in zip(chain[:-1], chain[1:], strict=True):
        A, B = np.broadcast_to(a, pts.shape), np.broadcast_to(b, pts.shape)
        ends = np.minimum.reduce([to_segment(e, A, B), to_segment(pts, A, B), to_segment(A, e, pts), to_segment(B, e, pts)])
        s1, s2 = np.sign(cross(pts - e, A - e)), np.sign(cross(pts - e, B - e))
        s3, s4 = np.sign(cross(B - A, e - A)), np.sign(cross(B - A, pts - A))
        apart = np.where((s1 != s2) & (s3 != s4), 0.0, ends)
        ok &= apart > arm["width"] / 2
    return ok


def comparable(entries: list[dict]) -> list[tuple]:
    return sorted((int(e["kind"]), e["state"], e["since"], None if e["place"] is None else tuple(np.round(np.asarray(e["place"], dtype=float), 5)),
                   tuple(int(c) for c in e["cells"])) for e in entries)


@pytest.mark.parametrize("scene", sorted(SCENES))
def test_the_host_gives_the_inventory_the_map_gives_driven_directly(scene):
    data = json.loads(SCENES[scene].read_text())
    host = MapHost(CONFIG)
    host.handle({"command": "describe"})
    direct = Map.load(MAP_FILE)
    lit = lit_cells(SCENES[scene], direct.centers)
    assert lit.shape == (len(data["truth"]), direct.count)
    errors, last_seen, inside, last = [], [], [], None
    for t, (report, seen) in enumerate(zip(data["report"], data["in_view"], strict=True)):
        sees = lambda points, t=t: visible(data["geometry"], points, data["joints"][t])  # noqa: E731
        assert np.array_equal(sees(direct.centers), lit[t]), f"the port of the page's rule differs at moment {t}"
        host.looks = sees  # as the worker gives the page's rule for any place
        reports = [["hand", *report]] if seen else []
        reply = host.handle({"command": "step", "seen": reports, "lit": "".join("1" if v else "0" for v in lit[t]), "wave": t % 3 == 0})
        direct.moment(seen=[(HAND, np.asarray(report))] if seen else [], lit=sees)
        want = [{**e, "cells": np.asarray(e["cells"]).tolist()} for e in direct.things()]
        assert comparable(reply["things"]) == comparable(want), f"moment {t}"
        json.dumps(reply, allow_nan=False)  # the reply crosses to the page as JSON
        assert host.buffers["activation"].shape == (host.n,)
        if seen:
            last = np.asarray(report)
        else:
            hand = min((e for e in reply["things"] if e["kind"] == HAND), key=lambda e: e["since"])
            truth = np.asarray(data["truth"][t])
            errors.append(float(np.linalg.norm(np.asarray(hand["place"]) - truth)))
            last_seen.append(float(np.linalg.norm(last - truth)))
            cell = np.floor((truth - direct._low) / direct.size).astype(int)
            inside.append(int(cell[0] * direct.cells[1] + cell[1]) in hand["cells"])
    print(f"{scene}: hidden {100 * np.mean(errors):.1f} cm, last seen {100 * np.mean(last_seen):.1f} cm, cells hold {np.mean(inside):.2f}")
    assert np.mean(errors) <= np.mean(last_seen) and np.mean(inside) >= 0.85


def test_nothing_is_announced_and_a_thing_enters_when_first_sensed():
    host = MapHost(CONFIG)
    assert host.handle({"command": "things"})["things"] == []
    host.handle({"command": "step", "seen": [], "lit": None})
    assert host.handle({"command": "things"})["things"] == []
    reply = host.handle({"command": "step", "seen": [["apple", -0.05, 1.1]], "lit": None})
    (apple,) = reply["things"]
    assert apple["name"] == "apple" and apple["state"] == "seen" and np.allclose(apple["place"], [-0.05, 1.1], atol=1e-3)
    for _ in range(50):
        reply = host.handle({"command": "step", "seen": [], "lit": None})
    (apple,) = reply["things"]
    assert apple["state"] == "held" and apple["since"] == 50 and np.allclose(apple["place"], [-0.05, 1.1], atol=1e-3)


def test_a_sound_and_the_joint_readings_write_a_place():
    host = MapHost(CONFIG)
    reply = host.handle({"command": "step", "heard": [["bread", 0.4, 0.2]], "lit": None})
    assert [(e["name"], e["state"]) for e in reply["things"]] == [("bread", "heard")]
    for k in range(30):  # the arm's own hand, unseen, placed at every moment by its joint readings
        place = [-0.5 + 0.01 * k, 0.4]
        reply = host.handle({"command": "step", "felt": [["hand", *place]], "lit": np.zeros(832, dtype=bool).tolist()})
        hand = next(e for e in reply["things"] if e["name"] == "hand")
        assert hand["state"] == "felt" and np.linalg.norm(np.asarray(hand["place"]) - place) < 1e-3


def test_questions_both_ways_and_an_emptied_map():
    host = MapHost(CONFIG)
    host.handle({"command": "step", "seen": [["apple", -0.05, 1.1], ["bread", 0.82, 0.3]], "lit": None})
    where = host.handle({"command": "ask", "thing": "apple"})
    assert np.allclose(where["places"], [[-0.05, 1.1]], atol=1e-3) and where["wave"]["asked"] == "where_is"
    assert host.handle({"command": "what", "point": [0.82, 0.3]})["name"] == "bread"
    assert host.handle({"command": "what", "point": [0.5, 1.2]})["name"] is None
    assert host.handle({"command": "reset"})["things"] == []
    assert host.handle({"command": "things"})["things"] == []


def test_the_wave_is_the_maps_own_record_by_sweep():
    host = MapHost(CONFIG)
    d = host.handle({"command": "describe"})
    named = sorted(i for region in d["regions"] for i in region["neurons"])
    assert named == list(range(d["neurons"])) and len(host.buffers["pre"]) == d["synapses"]
    reply = host.handle({"command": "step", "seen": [["hand", -0.6, 1.0]], "lit": None, "wave": True})
    frames = host.buffers["wave_frames"].reshape(reply["wave"]["frames"], -1)
    assert np.allclose(frames[-1], host.buffers["activation"])
    sheet = host.populations["map"]
    assert frames[0][sheet].max() == 0.0 and frames[1][sheet].max() > 0.0  # the sheet settles in the first sweep


def test_learned_physics_is_taught_in_batches_and_states_what_it_learned():
    from cadence.space.map import Map as Wheel

    if "physics" not in Wheel.__init__.__code__.co_varnames:
        pytest.skip("the pack's wheel has no learned physics")
    from spacebrain.map_host import TEACH_EVERY

    host = MapHost({**CONFIG, "physics": True})
    d = host.handle({"command": "describe"})
    assert d["physics"]["lessons"] == 0 and len(d["physics"]["kernels"]["share"]) == len(d["physics"]["kernels"]["velocities"])
    errors = []
    for t in range(2 * TEACH_EVERY):
        reply = host.handle({"command": "step", "seen": [["hand", -0.6 + 0.012 * t, 0.9]], "lit": None})
        assert "physics" in reply
        if reply["physics"]["error"] is not None:
            errors.append(reply["physics"]["error"])
            assert reply["physics"]["kernels"]["lessons"] == reply["physics"]["lessons"]
    assert len(errors) == 2 and reply["physics"]["lessons"] > 0
    (hand,) = reply["things"]
    assert "moving" in hand
