"""The two packed brains: the manifest's hashes hold, the brain loads on the pinned cadence-net,
and the page's host answers a legal move every tick of a game, as the worker runs it."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "web" / "pack"
sys.path.insert(0, str(ROOT))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module", params=["flat", "deep"])
def slot(request):
    return request.param


def manifest(slot: str) -> dict:
    return json.loads((PACK / slot / "manifest.json").read_text())


def test_manifest_hashes(slot):
    m = manifest(slot)
    base = PACK / slot
    assert sha(base / m["wheel"]) == m["wheel_sha256"]
    for name in m["sources"]:
        assert sha(base / "py" / "tron" / name) == m["sources_sha256"][name]
        assert (base / "py" / "tron" / name).read_bytes() == (ROOT / "tron" / name).read_bytes(), name
    for key in ("file", "meta", "introspect"):
        if key in m["brain"]:
            assert sha(base / m["brain"][key]) == m["brain"][f"{key}_sha256" if key != "file" else "sha256"]


def test_pinned_version(slot):
    import cadence

    m = manifest(slot)
    assert m["cadence"] == cadence.__version__ == "0.95.2"
    meta = json.loads((PACK / slot / m["brain"]["meta"]).read_text())
    assert meta["cadence"] == m["cadence"]


def test_host_plays_legal_moves(slot):
    """A whole game against `voronoi` riding the player's seat, through the page's JSON ops."""
    from tron import bots
    from tron.fieldhost import FieldHost

    m = manifest(slot)
    base = PACK / slot
    meta = json.loads((base / m["brain"]["meta"]).read_text())
    host = FieldHost((base / m["brain"]["file"]).read_bytes(), meta)
    described = json.loads(host.handle_json('{"op": "describe"}'))
    assert described
    state = json.loads(host.handle_json(json.dumps({"op": "begin", "seed": 12345})))
    ticks = 0
    while not state["over"]:
        assert state["brain"]["choice"] in (0, 1, 2)
        move = bots.voronoi(host.arena, 1)
        state = json.loads(host.handle_json(json.dumps({"op": "tick", "move": move})))
        ticks += 1
        assert ticks < 24 * 24
    assert state["result"] in ("win", "loss", "draw")


def test_layouts(slot):
    from cadence import Brain

    m = manifest(slot)
    brain = Brain.load(str(PACK / slot / m["brain"]["file"]), backend="cpu")
    modules = brain.describe()["layout"]["modules"]
    assert list(modules) == ([256] if slot == "flat" else [256, 128, 32])
    assert len(brain.sensory_index) == 2470 and len(brain.learner.output_index) == 3
