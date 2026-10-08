"""The walker host: one life, its readings, its messages, its continuation and its parity with
the chamber's brains."""

import copy
import importlib.util
import json
import os
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from walker import world as w  # noqa: E402
from walker.host import AROUSAL, POINT, Host  # noqa: E402


@pytest.fixture(autouse=True)
def quiet():
    warnings.simplefilter("ignore")


def test_a_newborn_lives_moments_and_reports_them():
    host = Host(0)
    describe = host.describe()
    assert describe["copy"] is True and describe["neurons"] > 40 and describe["synapses"] > 0
    first = host.moment()
    assert first["refused"] is False and first["mode"] == "aroused"  # the youth
    assert first["foot"] in ("L", "R") and first["changed"] is False and first["reward"] == 0.0
    assert first["belief"] is None and len(first["copy"]) == 2 and len(first["motor"]) == 2
    assert first["copy"][first["action"]] == 1.0  # the copy holds the command just issued
    second = host.moment()
    assert 0.0 <= second["belief"] <= 1.0 and second["copy"][second["action"]] == 1.0
    status = host.status()
    assert status["moments"] == 2 == status["work"]["routine"] + status["work"]["aroused"]
    assert status["work"]["sweeps_aroused"] > 0 and status["position"] == int(second["changed"])


def test_the_walker_with_the_copy_learns_the_beat_and_the_one_without_does_not():
    # seed 3 is the example's founder; the chamber's receipts give the five fresh seeds
    walker, bare = Host(3, copy=True), Host(3, copy=False)
    out, control = walker.run(300), bare.run(300)
    assert out["beat50"] >= 0.9 and out["found"] is not None and out["work"]["aroused_recent"] <= 0.1
    assert control["beat50"] < 0.75 and control["found"] is None
    assert bare.brain.efference is None and walker.brain.efference is not None


def test_forgetting_erases_the_copy_and_the_walker_resumes():
    host = Host(3)
    host.run(300)
    assert host.forget() == {"forgot": True}
    assert not host.brain.efference.trace.any() and host.brain.efference.cold.all()
    feet = [host.moment()["action"] for _ in range(21)]
    assert w.beat(feet) >= 0.9
    assert Host(3, copy=False).forget() == {"forgot": False}


def test_frozen_floor_and_a_flash_are_moments_of_the_life():
    host = Host(3)
    host.run(200)
    before = host.moments
    paused = [host.moment(w.KIND_PAUSE) for _ in range(3)]
    flashed = host.moment(w.KIND_DISTRACTOR)
    assert [p["kind"] for p in paused] == ["pause"] * 3 and flashed["kind"] == "distractor"
    assert host.moments == before + 4


def test_messages_run_forget_describe_and_refuse_unknown_ops():
    host = Host(1)
    out = json.loads(host.handle_json(json.dumps({"op": "run", "moments": 5})))
    assert len(out["feet"]) == 5 and out["moments"] == 5
    assert json.loads(host.handle_json(json.dumps({"op": "describe"})))["point"] == POINT
    assert json.loads(host.handle_json(json.dumps({"op": "forget"})))["forgot"] is True
    with pytest.raises(ValueError):
        host.handle_json(json.dumps({"op": "fly"}))


def test_a_snapshot_mid_life_continues_identically():
    host = Host(2)
    host.run(150)
    data = host.snapshot()
    twin = Host(2)
    twin.restore(data)
    twin.track = copy.deepcopy(host.track)
    twin.pending = host.pending
    mine = [host.moment()["action"] for _ in range(40)]
    theirs = [twin.moment()["action"] for _ in range(40)]
    assert mine == theirs


@pytest.mark.skipif(not os.environ.get("CADENCE_REPO"), reason="set CADENCE_REPO to a cadence checkout")
def test_the_host_runs_the_chamber_s_brains_action_for_action():
    repo = Path(os.environ["CADENCE_REPO"])
    sys.path.insert(0, str(repo / "benchmarks" / "rhythm"))
    spec = importlib.util.spec_from_file_location("reward_rhythm", repo / "benchmarks/rhythm/reward_rhythm.py")
    chamber = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chamber)
    protocol, _ = chamber.load_protocol(repo / "benchmarks/rhythm/protocol-reward-2.json")
    point = protocol["operating_point"]
    assert all(POINT[k] == point[k] for k in POINT)
    assert AROUSAL == {k: v for k, v in protocol["arousal"].items() if k != "note"}
    import tempfile

    directory = Path(tempfile.mkdtemp())
    for arm, copied in (("live", True), ("nocopy", False)):
        brain = chamber.make_brain(401, protocol, arm)
        life = chamber.live_life(brain, arm, protocol, 401, directory / arm, moments=200, probe_at=150)
        host = Host(401, copy=copied)
        assert [host.moment()["action"] for _ in range(200)] == life["actions"]
