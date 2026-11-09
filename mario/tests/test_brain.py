"""The shipped brain loads and answers on the released library, without a ROM: a synthetic screen
and RAM go through the eye, and 32 recorded observations from the gauntlet get the answers the
brain gave when it played it (on cadence-net 0.91.1, the gauntlet's library line)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smb.console import area_of  # noqa: E402
from smb.eye import ACTIONS, N_INPUTS, body_sense, eye  # noqa: E402
from smb.player import FRESH, HELD, TRAIN_POOL  # noqa: E402

BRAIN = ROOT / "brain" / "brain.npz"


class FakeConsole:
    """What body_sense reads: RAM and the level timer."""
    def __init__(self):
        self.ram = np.zeros(2048, np.uint8)
        self.ram[0x0057], self.ram[0x009F], self.ram[0x0033] = 24, 0xFC, 1  # running right, rising, facing right
        self.time = 380


def test_eye_layout():
    rng = np.random.default_rng(0)
    screen = rng.integers(0, 256, size=(240, 256, 3), dtype=np.uint8)
    e = eye(screen)
    assert e.shape == (832,) and np.all((e >= 0) & (e <= 1))
    b = body_sense(FakeConsole())
    assert b.shape == (38,) and np.all((b >= 0) & (b <= 1))
    assert N_INPUTS == 2 * 832 + (38 + 4) * 8 == 2000
    assert len(ACTIONS) == 7


def test_levels_and_starts():
    assert [area_of(1, s) for s in (1, 2, 3, 4)] == [1, 3, 4, 5]
    assert [area_of(3, s) for s in (1, 2, 3, 4)] == [1, 2, 3, 4]
    assert len(HELD) == len(FRESH) == 50
    assert not set(HELD) & set(TRAIN_POOL) and not set(FRESH) & (set(TRAIN_POOL) | set(HELD))


def test_brain_answers_as_it_played():
    from cadence import Brain
    brain = Brain.load(str(BRAIN), backend="cpu")
    layout = brain.describe()["layout"]
    assert layout["inputs"] == N_INPUTS and layout["actions"] == 7 and layout["modules"] == [256]
    rec = np.load(ROOT / "tests" / "answers.npz")
    got = [int(np.asarray(brain.predict(o.astype(np.float64)[None])).reshape(-1)[0]) for o in rec["obs"]]
    assert got == rec["actions"].tolist()
    # predict carries no state between calls: the same answers in reversed order
    back = [int(np.asarray(brain.predict(o.astype(np.float64)[None])).reshape(-1)[0]) for o in rec["obs"][::-1]]
    assert back[::-1] == got


def test_brain_view():
    """The view settles an observation under the recorder, agrees with the played answer and draws."""
    from cadence import Brain
    from smb.view import H, W, BrainView
    brain = Brain.load(str(BRAIN), backend="cpu")
    rec = np.load(ROOT / "tests" / "answers.npz")
    view = BrainView(brain)
    for o, a in zip(rec["obs"][:4], rec["actions"][:4]):
        s = view.settle(o.astype(np.float64), int(a))
        assert s["final"].shape == (2519,) and s["steps"] > 0
    assert view.agree == view.decisions == 4
    assert view.draw(s).size == (W, H)
