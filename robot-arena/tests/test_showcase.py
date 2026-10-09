"""A browser pack must carry the outcome owed to each saved continuing brain."""

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from arena import nursery
from arena.brain import RobotBrain
from arena.league import League
from arena.parts import stock_designs


def load_script(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=[0, 300], ids=["calm", "aroused"])
def packed_lives(tmp_path, monkeypatch, request):
    root = Path(__file__).resolve().parents[1]
    pack = load_script(root / "showcase-app/pack.py")
    host = load_script(root / "showcase-app/py/host.py")
    blueprints = [
        replace(body, name=f"{tmp_path.name}-{index}", genes={"arousal": {
            "youth": request.param, "need": 0.0, "value_surprise": 0.0,
        }})
        for index, body in enumerate(stock_designs()[:2])
    ]
    league = League(tmp_path / "league")
    league.create(blueprints)
    step = nursery.Arena.step

    def known_outcome(world, commands):
        outcomes = step(world, commands)
        outcomes[0]["dealt"], outcomes[0]["taken"] = 0.123456789, 0.0
        return outcomes

    with monkeypatch.context() as patch:
        patch.setattr(nursery.Arena, "step", known_outcome)
        patch.setattr(nursery, "PROGRESS_PAY", 0.0)
        patch.setattr(nursery, "DAMAGE_SCALE", 1.0)
        league.nursery(moments=2, seed=8)

    output = tmp_path / "pack"

    def download(command, *, check):
        # Exercise the complete builder without depending on network availability.
        assert check and f"cadence-net=={pack.CADENCE}" in command
        destination = Path(command[command.index("-d") + 1])
        (destination / f"cadence_net-{pack.CADENCE}-py3-none-any.whl").write_bytes(b"wheel")

    with monkeypatch.context() as patch:
        patch.setattr(pack.subprocess, "run", download)
        patch.setattr(sys, "argv", [
            "pack.py", "--league", str(league.root), "--robots", "2", "--out", str(output),
        ])
        pack.main()
    manifest = json.loads((output / "manifest.json").read_text())
    for entry in manifest["roster"]:
        assert entry["owed"] == league.data["robots"][entry["name"]]["owed"]
        assert entry["owed"] == [0.123456789, True]
        assert (output / "brains" / f"{entry['name']}.npz").read_bytes() == (
            league.brain_path(entry["name"]).read_bytes()
        )
    return host.Host, manifest, output / "brains"


def observe_feedback(monkeypatch):
    delivered = []
    moment = RobotBrain.moment

    def record(life, observation, reward, done=False):
        before = life.brain.arousal.rewards
        reading = moment(life, observation, reward, done)
        assert not reading["refused"]
        delivered.append((life.blueprint.name, reward, done, before, life.brain.arousal.rewards))
        return reading

    monkeypatch.setattr(RobotBrain, "moment", record)
    return delivered


def test_packed_nursery_outcome_reaches_first_browser_feedback_once(packed_lives, monkeypatch):
    Host, manifest, brains = packed_lives
    page = Host(manifest["roster"], str(brains), manifest["stage"])
    expected = {entry["name"]: tuple(entry["owed"]) for entry in manifest["roster"]}
    assert page.owed == expected
    assert all(life.has_pending() for life in page.brains.values())
    delivered = observe_feedback(monkeypatch)
    page.new_fight(list(expected), seed=91, duration=4, zone_moments=40)
    page.step(2)
    for name, owed in expected.items():
        rows = [row[1:] for row in delivered if row[0] == name]
        assert rows[0] == (*owed, 0, 1)
        assert rows[1][1:] == (False, 1, 2)

    # The explicit page reset reloads both the original brain and its original outcome.
    page.reset()
    assert page.owed == expected
    delivered.clear()
    page.new_fight(list(expected), seed=92, duration=4, zone_moments=40)
    page.step(1)
    assert {name: (reward, done, before, after) for name, reward, done, before, after in delivered} == {
        name: (*owed, 0, 1) for name, owed in expected.items()
    }


def test_browser_restore_uses_its_saved_debt_not_the_pack_debt(packed_lives, monkeypatch):
    Host, manifest, brains = packed_lives
    page = Host(manifest["roster"], str(brains), manifest["stage"])
    names = list(page.brains)
    page.new_fight(names, seed=91, duration=1, zone_moments=40)
    assert page.step(1)["done"]
    saved = page.save()
    assert all(saved["owed"][entry["name"]] != entry["owed"] for entry in manifest["roster"])

    restored = Host(manifest["roster"], str(brains), manifest["stage"])
    restored.restore(saved["brains"], saved["owed"])
    assert restored.owed == {name: tuple(owed) for name, owed in saved["owed"].items()}
    delivered = observe_feedback(monkeypatch)
    restored.new_fight(names, seed=92, duration=4, zone_moments=40)
    restored.step(2)
    for name in names:
        rows = [row[1:] for row in delivered if row[0] == name]
        assert rows[0] == (*saved["owed"][name], 1, 2)
        assert rows[1][1:] == (False, 2, 3)

    # Legacy browser saves with no outcome must not inherit an unrelated pack's debt.
    legacy = Host(manifest["roster"], str(brains), manifest["stage"])
    legacy.restore(saved["brains"])
    assert legacy.owed == dict.fromkeys(names)
    old_roster = [{key: value for key, value in entry.items() if key != "owed"}
                  for entry in manifest["roster"]]
    assert Host(old_roster, str(brains), manifest["stage"]).owed == dict.fromkeys(names)
