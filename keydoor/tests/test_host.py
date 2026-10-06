"""The creature host: one life, its ledger, its messages and its continuation."""

import copy
import json
import warnings

import pytest

from keydoor import world as w
from keydoor.host import Host, newborn


@pytest.fixture(autouse=True)
def quiet():
    warnings.simplefilter("ignore")


def test_a_newborn_lives_moments_and_reports_them():
    host = Host(None, 2, 0)
    describe = host.describe()
    assert describe["neurons"] > 6 and describe["synapses"] > 0 and describe["need"] == 0.03
    first = host.moment()
    assert first["refused"] is False and first["mode"] == "aroused"  # the youth
    assert first["kind"] == w.FLOOR and first["action"] in (0, 1) and first["want"] == 1.0  # never paid
    assert 0 <= first["p_interact"] <= 1 and 0 <= first["p_interact_policy"] <= 1
    result = host.run(trips=3)
    assert len(result["rows"]) == 3 and result["trips"] == 3
    assert all(r["cells"] <= w.LENGTH for r in result["rows"])
    status = host.status()
    assert status["moments"] == host.moments == result["lived"] + 1
    assert "cells" in first and len(first["cells"]) <= w.LENGTH
    assert status["work"]["aroused"] + status["work"]["routine"] == status["moments"]
    assert status["work"]["sweeps_aroused"] > 0


def test_messages_move_the_key_cut_a_trip_and_probe():
    host = Host(None, 2, 1)
    assert json.loads(host.handle_json(json.dumps({"op": "move_key"})))["keyed"] == w.LAMP
    assert json.loads(host.handle_json(json.dumps({"op": "cut"})))["cut"] is True
    out = json.loads(host.handle_json(json.dumps({"op": "run", "trips": 1})))
    assert out["rows"][0]["cut"] is True and out["rows"][0]["keyed"] == w.LAMP
    probe = json.loads(host.handle_json(json.dumps({"op": "probe"})))
    assert len(probe["greedy"]) == 2 and len(probe["p_interact"][0]) == 5
    with pytest.raises(ValueError):
        host.handle_json(json.dumps({"op": "fly"}))


def test_a_snapshot_mid_trip_continues_identically():
    """Saved between two cells with the preceding outcome pending, the restored twin takes
    the same actions for the rest of the trip and the next one."""
    host = Host(None, 5, 2)
    host.run(trips=4)
    for _ in range(6):  # into the fifth trip
        host.moment()
    data = host.snapshot()
    twin = Host(None, 5, 2)
    twin.restore(data)
    twin.world = copy.deepcopy(host.world)
    mine = [host.moment()["action"] for _ in range(30)]
    theirs = [twin.moment()["action"] for _ in range(30)]
    assert mine == theirs
    assert host.brain.arousal.to_dict() == twin.brain.arousal.to_dict()


def test_a_refused_answer_is_reported_and_keeps_the_outcome_for_a_retry():
    from dataclasses import replace

    host = Host(None, 2, 3)
    host.run(trips=1)
    learner = host.brain.learner
    strict = replace(learner.config, free_steps=8, tolerance=1e-15)
    learner.config = strict
    host.brain.basal_ganglia.learner.config = strict
    record = host.moment()
    assert record["refused"] and "settle" in record["error"] and record["sweeps"] == 8
    assert host.refusals == 1 and host.world.pending is None  # the brain holds the outcome
    learner.config = replace(strict, free_steps=1024, tolerance=0.003)
    host.brain.basal_ganglia.learner.config = learner.config
    again = host.moment()
    assert again["refused"] is False and again["kind"] == record["kind"]


def test_the_brain_is_the_protocols_live_arm():
    brain = newborn(0)
    cfg = brain.basal_ganglia.config
    assert (cfg.eta, cfg.eta_bias, cfg.lam, cfg.gamma, cfg.eta_critic) == (0.1, 0.01, 0.95, 0.95, 5.0)
    assert brain.arousal.config.need == 0.03 and brain.arousal.config.heat == 2.0
