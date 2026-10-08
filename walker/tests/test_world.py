"""The world's rule, the moments and the track; the chamber's own code when a checkout is at hand."""

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from walker import world as w  # noqa: E402


def test_moments_are_the_frozen_input_module_s_events():
    drive = w.observation(w.KIND_DRIVE)
    assert drive.shape == (1, w.INPUTS) and drive[0, w.DRIVE] == 1.0 and drive.sum() == 1.0
    assert not w.observation(w.KIND_PAUSE).any()
    flash = w.observation(w.KIND_DISTRACTOR)
    assert flash[0, w.DISTRACTOR] == 1.0 and flash.sum() == 1.0
    with pytest.raises(ValueError):
        w.observation(7)


def test_the_world_pays_a_changed_step_and_nothing_else():
    assert w.pay(None, 0) == w.REPEAT
    assert w.pay(0, 1) == w.ALTERNATE
    assert w.pay(1, 1) == w.REPEAT
    assert w.beat([0, 1, 0, 1]) == 1.0 and w.beat([0, 0, 0]) == 0.0 and w.beat([1]) == 0.0


def test_the_track_moves_on_changed_steps_only():
    track = w.Track()
    first = track.step(0)
    assert first["changed"] is False and first["reward"] == 0.0 and track.position == 0
    second = track.step(1)
    assert second["changed"] is True and second["reward"] == 1.0 and second["foot"] == "R"
    track.step(1)
    assert track.position == 1 and track.recent_beat(3) == 0.5 and track.income(3) == pytest.approx(1 / 3)


@pytest.mark.skipif(not os.environ.get("CADENCE_REPO"), reason="set CADENCE_REPO to a cadence checkout")
def test_the_rule_and_the_events_are_the_chamber_s():
    repo = Path(os.environ["CADENCE_REPO"])
    sys.path.insert(0, str(repo / "benchmarks" / "rhythm"))
    spec = importlib.util.spec_from_file_location("reward_rhythm", repo / "benchmarks/rhythm/reward_rhythm.py")
    chamber = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chamber)
    protocol, _ = chamber.load_protocol(repo / "benchmarks/rhythm/protocol-reward-2.json")
    rule = protocol["world"]["reward"]
    for previous in (None, 0, 1):
        for action in (0, 1):
            assert w.pay(previous, action) == chamber.pay(previous, action, rule)
    for kind in (w.KIND_DRIVE, w.KIND_PAUSE, w.KIND_DISTRACTOR):
        np.testing.assert_array_equal(w.observation(kind), chamber.observation(kind))
