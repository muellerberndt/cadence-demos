"""The arcade's brain on the released library: the recipe, a watched-then-rewarded tape that
continues across save and load, the browser's brain side through a takeover, and the pack."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from cadence import Brain

import arcade_brain
import server

HERE = Path(__file__).resolve().parents[1]


def screen(t, n):
    rng = np.random.default_rng(t)
    return ((rng.random(n) - 0.5) * 0.4).reshape(1, n)


def test_recipe_on_the_screen():
    brain = server.build_brain(3)
    assert len(brain.sensory_index) == 7056
    assert len(brain.motor_index) == 3
    assert "recall" not in brain.connectome.populations  # off unless ARCADE_RECALL=1
    config = brain.learner.config
    assert (config.eta, config.nudged_steps, config.normalize) == (0.003, 12, 0.99)
    assert brain.placement["backend"] == "cpu"


@pytest.mark.parametrize("actions", [3, 4])
def test_watched_rewarded_and_saved_tape_continues(actions, tmp_path):
    brain = arcade_brain.build_brain(actions, n_screen=12)
    for t in range(3):
        x = screen(t, 12)
        drive = brain.stimulus(x)
        brain.act(x, greedy=True)
        brain.learner.step(drive, np.array([(2 * t + 1) % actions]))
    for t in range(3, 7):
        feedback = {} if t == 3 else {"reward": [(-1.0, 0.0, 1.0)[t % 3]], "done": [t == 5]}
        brain.step(screen(t, 12), **feedback)
    assert brain.pending_feedback
    restored = Brain.load(brain.save(tmp_path / "acquired.npz"))
    for t in range(7, 10):
        x, reward = screen(t, 12), [float(t % 2)]
        np.testing.assert_array_equal(restored.step(x, reward=reward), brain.step(x, reward=reward))


def test_brain_side_takes_over_from_the_teacher(monkeypatch):
    monkeypatch.setattr(arcade_brain, "MIN_LESSONS", 20)
    monkeypatch.setattr(arcade_brain, "AGREE_WINDOW", 10)
    side = arcade_brain.BrainSide("Freeway", ["NOOP", "UP", "DOWN"], seed=0)
    drive = screen(0, 7056)[0]
    out = {}
    for _ in range(arcade_brain.MAX_LESSONS):
        out = side.iterate(drive, 1, 0.0, False, 1)
        if out.get("takeover"):
            break
    assert side.phase == "playing" and side.faults == 0
    assert side.takeover["lessons"] >= 20
    for k in range(6):
        out = side.iterate(drive, 1, float(k % 2), False, 1)
        assert out.get("consumed") and "fault" not in out
    assert side.decisions == 6 and side.outcomes == 5
    state = side.state()
    assert state["life"]["decisions"] == 6
    assert side.viz and len(side.viz["state"]) == sum(p["count"] for p in side.populations())
    assert len(side.graph_sample()) > 0


def test_pack_matches_its_sources():
    pack = HERE / "web" / "pack"
    manifest = json.loads((pack / "manifest.json").read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert manifest["cadence"] == "0.95.2"
    assert sha(pack / manifest["wheel"]) == manifest["wheel_sha256"]
    for name in manifest["sources"]:
        assert sha(pack / "py" / name) == manifest["sources_sha256"][name]
        assert (pack / "py" / name).read_bytes() == (HERE / name).read_bytes()
