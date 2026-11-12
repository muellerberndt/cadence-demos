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


def test_what_is_where_both_ways():
    host = Host()
    body = {"position": [0.45, 0.5], "heading": 3.0, "turn": 0.0}
    things = [{"name": "cup", "report": [-0.2, 0.32]}, {"name": "apple", "report": [-0.05, 1.1]}, {"name": "bread", "report": None}]
    host.handle({"command": "step", "hand": {"report": None}, "joints": JOINTS, "commands": REST, "things": things, "body": body})
    # asked for a kind, the record answers a place; a kind never seen has none
    apple = host.handle({"command": "ask", "thing": "apple"})
    assert np.allclose(apple["place"], [-0.05, 1.1], atol=1e-9) and apple["from"] == "seen" and apple["spread"] == 0.01
    assert host.handle({"command": "ask", "thing": "bread"})["place"] is None
    # asked for a direction from the body, the record whose place lies that way answers its kind
    origin = np.array(body["position"])
    toward = lambda p: float(np.arctan2(p[1] - origin[1], p[0] - origin[0]))  # noqa: E731
    assert host.handle({"command": "what", "origin": body["position"], "direction": toward([-0.05, 1.1]) + 0.1})["name"] == "apple"
    assert host.handle({"command": "what", "origin": body["position"], "direction": toward([-0.2, 0.32])})["name"] == "cup"
    assert host.handle({"command": "what", "origin": body["position"], "direction": toward([0.82, 0.3])})["name"] is None
    # a cue is read from the ear at the body, and its record's spread is the cue's own error
    cue = [toward([0.82, 0.3]), float(np.hypot(0.82 - 0.45, 0.3 - 0.5))]
    things[2] = {"name": "bread", "report": None, "cue": cue}
    host.handle({"command": "step", "hand": {"report": None}, "joints": JOINTS, "commands": REST, "things": things, "body": body})
    bread = host.handle({"command": "what", "origin": body["position"], "direction": cue[0]})
    assert bread["name"] == "bread" and bread["from"] == "heard" and np.allclose(bread["place"], [0.82, 0.3], atol=1e-9)
    assert np.isclose(bread["spread"], cue[1] * np.hypot(0.04, 0.08))


def test_reborn_takes_another_plane_and_starts_empty():
    host = Host()
    step(host, [0.2, 0.5], [{"name": "cup", "report": [0.3, 0.4]}])
    d = host.handle({"command": "reborn", "config": {"plane": [0.0, 2.0, 0.0, 1.0]}})
    assert d["place"]["plane"] == [0.0, 2.0, 0.0, 1.0] and d["records"]["held"] == 0 and d["lessons"] == 0
    reply = step(host, [1.5, 0.5])
    assert 0.0 <= reply["place"][0] <= 2.0


def test_a_pack_that_names_a_module_the_library_does_not_hold_is_refused():
    # a wheel without the module system refuses by that; one with it, by the module's name
    from spacebrain.host import make

    with pytest.raises((RuntimeError, ValueError)):
        make({"module": {"name": "no-such-module", "path": None}})
    assert isinstance(make({}), Host)


def test_the_place_modules_host_answers_the_pages_messages(tmp_path):
    """The adapter, on a module made here in a few lessons: the replies hold what the page
    reads. It says nothing of how well a trained module answers."""
    space = pytest.importorskip("cadence.space")
    from spacebrain.host import make

    interface = space.Interface(plane=(-1.0, 1.0, -0.2, 1.4), limits=((0.35, 2.79), (-2.6, -0.3)), hidden=32)
    donor = space.Space(interface, seed=0)
    donor.begin(np.array([[-0.5, 0.6]]))
    for t in range(40):
        donor.advance(np.array([True]), np.array([[-0.5 + 0.01 * t, 0.6]]), learn=True)
    path = donor.save(tmp_path / "place.npz")
    host = make({"module": {"name": "place", "path": str(path)}})
    d = host.handle({"command": "describe"})
    assert d["brain"]["kind"] == "place" and d["brain"]["trained"] is True
    named = [i for region in d["regions"] for i in region["neurons"]]
    assert sorted(named) == list(range(d["neurons"])) and all(len(r["seat"]) == 4 for r in d["regions"])
    assert host.buffers["weight"].shape == (d["synapses"],)
    body = {"position": [0.45, 0.5], "heading": 3.0, "turn": 0.0}

    def moment(report, cup=None, cue=None, teach=True):
        things = [{"name": "cup", "report": cup, "cue": cue}, {"name": "apple", "report": None, "cue": None}]
        return host.handle({"command": "step", "hand": {"report": report}, "joints": JOINTS, "commands": REST,
                            "things": things, "body": body, "teach": teach})

    for t in range(30):  # the hand in view, moving; the cup at rest in view
        reply = moment([-0.5 + 0.01 * t, 0.6], cup=[-0.2, 0.32])
    assert reply["seen"] and np.allclose(reply["place"], [-0.21, 0.6], atol=0.03)
    assert host.buffers["activation"].shape == (d["neurons"],) and np.isclose(host.buffers["px"].sum(), 1.0, atol=1e-5)
    cup, apple = reply["things"]
    assert np.allclose(cup["place"], [-0.2, 0.32], atol=0.02) and cup["from"] == "seen" and cup["spread"] > 0
    assert apple["place"] is None  # never seen: no place is claimed for it
    # out of view: the space holds the rows. A lesson is made of six reports in a row and lands
    # up to five moments after the last of them; from the sixth unseen moment on none is taken.
    for _ in range(6):
        reply = moment(None)
    lessons = reply["lessons"]
    for _ in range(14):
        reply = moment(None)
    assert not reply["seen"] and reply["since"] == 20 and reply["lesson"] is None and reply["lessons"] == lessons
    assert reply["radius"] > 0 and np.isfinite(reply["place"]).all()
    assert np.allclose(reply["things"][0]["place"], [-0.2, 0.32], atol=0.02) and reply["things"][0]["unseen"] == 20
    # a cue heard at the body reaches the space from the module's own ear: the same point
    point = np.array([-0.4, 0.2])
    offset = point - np.array(body["position"])
    again = host._cue([float(np.arctan2(offset[1], offset[0])), float(np.linalg.norm(offset))], np.array(body["position"]))
    ear = np.array(host.interface.ear)
    assert np.allclose(ear + again[1] * np.array([np.cos(again[0]), np.sin(again[0])]), point, atol=1e-12)
    heard = moment(None, cue=[float(np.arctan2(offset[1], offset[0])), float(np.linalg.norm(offset))])
    assert heard["things"][0]["source"] == "heard" and heard["things"][0]["from"] == "heard"
    # what is where, both ways
    assert host.handle({"command": "ask", "thing": "apple"})["place"] is None
    where = host.handle({"command": "ask", "thing": "cup"})
    assert where["place"] is not None
    toward = float(np.arctan2(where["place"][1] - 0.5, where["place"][0] - 0.45))
    assert host.handle({"command": "what", "origin": body["position"], "direction": toward})["name"] == "cup"
    assert host.handle({"command": "what", "origin": body["position"], "direction": toward + 2.0, "point": where["place"]})["by"] == "place"
    assert host.handle({"command": "what", "origin": body["position"], "direction": toward + 2.0})["name"] is None


def test_the_sight_evidence_holds_back_a_place_that_did_not_come_out(tmp_path):
    """A moment in two halves, on a module made here: the host predicts, the caller says which
    predicted places the camera would see, and a place predicted in sight for three moments
    with no report is put halfway along its hidden path. It says nothing of a trained module."""
    import inspect

    space = pytest.importorskip("cadence.space")
    if "in_sight" not in inspect.signature(space.Space.observe).parameters:
        pytest.skip("this library's space takes no sight evidence")
    from spacebrain.host import make

    interface = space.Interface(plane=(-1.0, 1.0, -0.2, 1.4), limits=((0.35, 2.79), (-2.6, -0.3)), hidden=32)
    donor = space.Space(interface, seed=0)
    donor.begin(np.array([[-0.5, 0.6]]))
    for t in range(40):
        donor.advance(np.array([True]), np.array([[-0.5 + 0.01 * t, 0.6]]), learn=True)
    host = make({"module": {"name": "place", "path": str(donor.save(tmp_path / "place.npz"))}})
    assert host.handle({"command": "describe"})["sight"] is True

    def halves(report, in_sight):
        moment = {"hand": {"report": report}, "joints": JOINTS, "commands": REST, "things": [], "teach": False}
        first = host.handle({"command": "predict", **moment})
        assert len(first["predicted"]) == 1 and first["names"] == ["hand"]
        return host.handle({"command": "observe", "in_sight": in_sight})

    for t in range(20):  # in view, moving right at 2 cm a moment
        reply = halves([-0.5 + 0.02 * t, 0.6], [True])
    last = np.array(reply["place"])
    for _ in range(8):  # hidden, its predicted place out of sight: moved by the brain's answer
        reply = halves(None, [False])
        assert reply["sight"]["given"] and not reply["held_back"]
    before = np.array(reply["place"])
    for _ in range(3):  # the camera would see it where it is predicted, and no report comes
        reply = halves(None, [True])
    assert reply["held_back"] and reply["sight"]["held_back"] == [True]
    assert np.allclose(reply["place"], (last + before) / 2.0, atol=1e-9)  # halfway along the hidden path
    assert reply["radius"] >= np.linalg.norm(before - last) / 2.0         # the circle reaches both ends
    rests = halves(None, [True])
    assert rests["held_back"] and not rests["asked"] and np.allclose(rests["place"], reply["place"])
    assert not halves([0.1, 0.6], [True])["held_back"]  # a report takes the place back
    # one message a moment, without the evidence: nothing is held back
    plain = host.handle({"command": "step", "hand": {"report": None}, "joints": JOINTS, "commands": REST, "things": [], "teach": False})
    assert plain["sight"]["given"] is False and not plain["held_back"]
    with pytest.raises(RuntimeError):
        host.handle({"command": "observe", "in_sight": [True]})  # no moment is open
