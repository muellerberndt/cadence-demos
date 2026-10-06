"""The corridor world: its trips, its outcomes, its exactly-once feedback, and its agreement
with the chamber in the Cadence repository when a checkout is at hand (``CADENCE_REPO``)."""

import importlib.util
import os
from pathlib import Path

import numpy as np
import pytest

from keydoor import world as w


def test_every_trip_has_the_declared_length_and_order():
    rng = np.random.default_rng(0)
    for delay in (2, 5, 10):
        for _ in range(20):
            cells = w.corridor(delay, w.LENGTH, w.JITTER, rng)
            assert len(cells) == w.LENGTH
            levers = cells.count(w.LEVER)
            assert abs(levers - delay) <= w.JITTER
            floors = cells.count(w.FLOOR)
            assert cells == [w.FLOOR] * floors + [w.CHEST, w.LAMP] + [w.LEVER] * levers + [w.DOOR]
    x = w.observe(w.LAMP, True)
    assert x.shape == (1, 6) and x[0, w.LAMP] == 1.0 and x[0, 5] == 1.0


def test_the_world_pays_the_door_with_the_key_and_costs_wrong_interactions():
    world = w.World(2, 0, truncation=0.0)
    paid = []
    for _ in range(5):  # always interact: the key is taken, levers and the lamp cost, the door pays
        while True:
            kind, holding = world.face()
            record = world.act(w.INTERACT)
            paid.append((kind, holding, record["event"], record["outcome"], record["done"]))
            if record["done"]:
                break
    events = {(k, h): e for k, h, e, _, _ in paid}
    assert events[(w.CHEST, False)] == "key" and events[(w.DOOR, True)] == "food"
    assert events[(w.LAMP, True)] == "wrong" and events[(w.LEVER, True)] == "wrong"
    assert events[(w.FLOOR, False)] == "nothing"
    assert sum(1 for *_, d in paid if d) == 5 and world.recent()["fed"] == 1.0
    assert world.recent()["wrong"] > 0
    # feedback is delivered once
    reward, done = world.feedback()
    assert reward == 1.0 and done is True
    assert world.feedback() == (None, False)


def test_moving_the_key_and_cutting_a_trip():
    world = w.World(2, 1, truncation=0.0)
    assert world.move_key() == w.LAMP
    kind, holding = world.face()
    while kind != w.CHEST:
        world.act(w.PASS)
        kind, holding = world.face()
    assert world.act(w.INTERACT)["event"] == "wrong"  # the chest holds nothing under rule B
    kind, _ = world.face()
    assert kind == w.LAMP and world.act(w.INTERACT)["event"] == "key"
    world.cut_next()
    record = world.act(w.PASS)
    assert record["cut"] and not record["done"] and world.trip.over
    assert world.cuts == 1 and world.recent()["trips"] == 0
    reward, done = world.feedback()
    assert reward == 0.0 and done is False  # a cut trip carries its forecast over


def test_a_share_of_trips_is_cut_by_chance():
    world = w.World(5, 3)
    for _ in range(400 * 14):
        world.face()
        world.act(w.PASS)
    begun = world.trips - (0 if world.trip is None or world.trip.over else 1)
    assert 5 <= world.cuts <= 50 and world.recent()["trips"] + world.cuts == begun


@pytest.mark.skipif(not os.environ.get("CADENCE_REPO"), reason="needs a Cadence checkout")
def test_the_world_is_the_chambers():
    """Against ``benchmarks/keydoor/key_door.py`` of the Cadence checkout: the same corridor
    sequence per seed and the same constants as the frozen protocol."""
    import json

    repo = Path(os.environ["CADENCE_REPO"])
    spec = importlib.util.spec_from_file_location("key_door", repo / "benchmarks/keydoor/key_door.py")
    chamber = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chamber)
    protocol = json.loads((repo / "benchmarks/keydoor/protocol.json").read_text())
    assert (protocol["length"], protocol["jitter"]) == (w.LENGTH, w.JITTER)
    assert (protocol["cost"], protocol["food"], protocol["truncation"]) == (w.COST, w.FOOD, w.TRUNCATION)
    assert protocol["corridor_seed"] == w.CORRIDOR_SEED
    for delay in protocol["delays"]:
        ours = np.random.default_rng(w.CORRIDOR_SEED + 7)
        theirs = np.random.default_rng(protocol["corridor_seed"] + 7)
        for _ in range(50):
            assert w.corridor(delay, w.LENGTH, w.JITTER, ours) == chamber.corridor(
                delay, protocol["length"], protocol["jitter"], theirs)
    assert np.array_equal(w.observe(w.LAMP, True), chamber.observe(chamber.LAMP, True, True))
    from keydoor.host import NEED, POINT

    assert protocol["operating_point"] == POINT and protocol["arousal"]["need"] == NEED
