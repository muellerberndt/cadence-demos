"""The shipped brain loads and acts on the released library, without a ROM: a synthetic frame
and RAM go through the eye, the brain answers four slots, and the player's snapshot has what
the page draws."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simon.eye import INPUTS, SLICES, Eye  # noqa: E402
from simon.pad import ACTIONS, SLOTS, from_slots, pad_action  # noqa: E402
from simon.player import BRAIN, Player, load_brain, populations  # noqa: E402


def synthetic(seed: int = 0):
    rng = np.random.default_rng(seed)
    frame = rng.integers(0, 256, size=(240, 256, 3), dtype=np.uint8)
    ram = np.zeros(2048, np.uint8)
    ram[0x28], ram[0x2A], ram[0x44] = 1, 3, 64      # stage 1, three lives, full health
    ram[0x38C], ram[0x354], ram[0x46C] = 120, 150, 0  # Simon's screen x and y, on the ground
    return frame, ram


def test_eye_layout():
    frame, ram = synthetic()
    x = Eye().observe(frame, ram)
    assert x.shape == (INPUTS,) == (827,)
    assert np.all(np.abs(x) <= 1.2 + 1e-9)
    assert SLICES["floor"][1] == INPUTS
    assert x[SLICES["stage"][0] + 1] == 0.6  # one-hot stage 1


def test_pad():
    assert len(ACTIONS) == 36 and sum(SLOTS) == 10
    right_whip = from_slots([2, 1, 1, 0])
    assert ACTIONS[right_whip] == (1, 0, 1, 0)
    pad = pad_action(right_whip)
    assert pad.tolist() == [1, 0, 0, 0, 0, 0, 0, 1, 0]  # B and RIGHT


def test_brain_acts():
    brain = load_brain(BRAIN)
    assert len(brain.sensory_index) == INPUTS
    player = Player(brain, populations(BRAIN))
    player.new_game()
    eye_frames = [synthetic(s) for s in range(3)]
    for frame, ram in eye_frames:
        action = player.decide(frame, ram)
        assert 0 <= action < 36
    snap = player.snapshot()
    assert snap["decisions"] == 3
    assert [len(s) for s in snap["slots"]] == list(SLOTS)
    assert {"module_0", "association", "motor"} <= set(snap["regions"])
    assert snap["qualified"] is not False
    json.dumps(snap)  # the page receives it as JSON


def test_receipt_names_the_brain():
    receipt = json.loads((ROOT / "evidence" / "receipt.json").read_text())
    import hashlib
    assert receipt["brain"]["sha256"] == hashlib.sha256(BRAIN.read_bytes()).hexdigest()
