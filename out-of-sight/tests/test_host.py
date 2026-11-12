"""The page's brain host, run natively: the same file the worker runs in Pyodide.

    PYTHONPATH=<cadence>/src python -m pytest tests/test_host.py     # or with cadence-net installed
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site" / "pack" / "py"))
warnings.simplefilter("ignore")

from cadence import PopulationCode  # noqa: E402
from spacebrain.host import Host, decode  # noqa: E402

JOINTS, REST = [1.3, -1.1], [0.0, 0.0]


def step(host: Host, report, things=(), **more):
    return host.handle({"command": "step", "hand": {"report": report}, "joints": JOINTS, "commands": REST,
                        "things": list(things), **more})


def test_a_population_code_decodes_to_the_value_it_was_given():
    code = PopulationCode([(-1.0, 1.0), (-0.2, 1.4)], per=24)
    points = np.random.default_rng(0).uniform([-1.0, -0.2], [1.0, 1.4], (500, 2))
    read = np.array([decode(code, code(p)[0]) for p in points])
    assert np.abs(read - points).max() < 1e-12


def test_describe_names_every_neuron_once_and_every_region_with_a_role():
    host = Host()
    d = host.handle({"command": "describe"})
    named = [i for region in d["regions"] for i in region["neurons"]]
    assert sorted(named) == list(range(d["neurons"]))
    assert {r["role"] for r in d["regions"]} == {"visual", "somatosensory", "motor", "association", "prefrontal", "place"}
    assert d["brain"]["trained"] is False and d["brain"]["kind"] == "baseline"
    assert host.buffers["pre"].shape == host.buffers["post"].shape == host.buffers["weight"].shape == (d["synapses"],)


def test_a_lesson_follows_only_a_moment_the_camera_reports():
    host = Host()
    seen = step(host, [0.2, 0.5], teach=True)
    assert seen["lesson"] and seen["lesson"]["taught"] and seen["lesson"]["changed"] > 0
    assert "flash_index" in seen["buffers"] and "weight" in seen["buffers"]
    weights = host._weights().copy()
    hidden = step(host, None, teach=True)
    assert hidden["lesson"] is None and hidden["seen"] is False
    assert np.array_equal(weights, host._weights())
    off = step(host, [0.2, 0.5], teach=False)
    assert off["lesson"] is None and np.array_equal(weights, host._weights())


def test_the_answer_is_a_place_with_a_spread_and_an_area():
    host = Host()
    reply = step(host, [0.2, 0.5])
    x0, x1, y0, y1 = host.plane
    assert x0 <= reply["place"][0] <= x1 and y0 <= reply["place"][1] <= y1
    assert reply["sd"][0] > 0 and reply["sd"][1] > 0 and reply["area"] > 0
    assert np.isclose(host.buffers["px"].sum(), 1.0, atol=1e-5) and np.isclose(host.buffers["py"].sum(), 1.0, atol=1e-5)
    assert host.buffers["activation"].shape == (host.n,)


def test_the_wave_is_the_settle_the_answer_was_read_from():
    host = Host()
    step(host, [0.2, 0.5])
    reply = step(host, [-0.4, 0.9], wave=True)
    assert reply["wave"] is not None and reply["wave"]["of"] == reply["sweeps"] > 0
    frames = host.buffers["wave_frames"].reshape(reply["wave"]["frames"], host.n)
    assert np.abs(frames[-1] - host.buffers["activation"]).max() < 1e-6
    assert host.buffers["wave_move"].shape == (reply["wave"]["of"],)
    assert reply["wave"]["sweeps"][-1] == reply["wave"]["of"]


def test_a_record_keeps_its_place_until_the_thing_is_seen_or_heard():
    host = Host()
    cup = lambda **given: {"name": "cup", "report": None, "cue": None, **given}  # noqa: E731
    first = step(host, None, [cup(report=[0.3, 0.4])])["things"][0]
    assert first["write"] and first["source"] == "seen" and np.allclose(first["place"], [0.3, 0.4], atol=1e-9)
    for _ in range(50):  # out of view: read, never moved
        held = step(host, None, [cup()])["things"][0]
    assert not held["write"] and held["source"] == "held" and np.allclose(held["place"], [0.3, 0.4], atol=1e-9)
    assert held["unseen"] == 50 and held["from"] == "seen"
    # a sound: its direction and distance from the ear name a point, and the record moves there
    ear = np.asarray(host.config["ear"])
    point = np.array([-0.2, 0.6])
    offset = point - ear
    cue = [float(np.arctan2(offset[1], offset[0])), float(np.linalg.norm(offset))]
    heard = step(host, None, [cup(cue=cue)])["things"][0]
    assert heard["write"] and heard["source"] == "heard" and heard["revised"]
    assert np.allclose(heard["place"], point, atol=1e-9)
    after = step(host, None, [cup()])["things"][0]
    assert after["from"] == "heard" and np.allclose(after["place"], point, atol=1e-9)
    # seen again: the camera's report takes the record back
    again = step(host, None, [cup(report=[0.1, 0.1])])["things"][0]
    assert again["source"] == "seen" and np.allclose(again["place"], [0.1, 0.1], atol=1e-9)
    assert host.records.count == 1


def test_things_keep_their_own_records_and_a_thing_never_seen_has_none():
    host = Host()
    things = [{"name": "cup", "report": [0.3, 0.4]}, {"name": "wrench", "report": [-0.5, 1.0]}, {"name": "box", "report": None}]
    out = step(host, None, things)["things"]
    assert [t["slot"] for t in out[:2]] == [0, 1] and out[2]["slot"] == -1 and out[2]["place"] is None
    quiet = [{"name": t["name"], "report": None} for t in things]
    out = step(host, None, quiet)["things"]
    assert np.allclose(out[0]["place"], [0.3, 0.4], atol=1e-9) and np.allclose(out[1]["place"], [-0.5, 1.0], atol=1e-9)
    assert host.handle({"command": "ask", "thing": "box"})["place"] is None
    assert np.allclose(host.handle({"command": "ask", "thing": "wrench"})["place"], [-0.5, 1.0], atol=1e-9)


def test_reborn_takes_another_plane_and_starts_empty():
    host = Host()
    step(host, [0.2, 0.5], [{"name": "cup", "report": [0.3, 0.4]}])
    d = host.handle({"command": "reborn", "config": {"plane": [0.0, 2.0, 0.0, 1.0]}})
    assert d["place"]["plane"] == [0.0, 2.0, 0.0, 1.0] and d["records"]["held"] == 0 and d["lessons"] == 0
    reply = step(host, [1.5, 0.5])
    assert 0.0 <= reply["place"][0] <= 2.0


def test_a_pack_that_names_a_module_is_refused_by_a_wheel_without_one():
    with pytest.raises(RuntimeError):
        Host({"module": {"name": "place", "path": None}})
