"""The look-ahead without a ROM: a toy console (savestates, one enemy that hurts Simon every
decision until a whip removes it) stands in for the emulator. The brain's move is played where
no enemy is near; next to the enemy, walking on into it is overruled by a whip."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simon.lookahead import Lookahead  # noqa: E402
from simon.pad import ACTIONS  # noqa: E402

TYPE, X, Y, HEALTH = 0x434, 0x38C, 0x354, 0x44
ENEMY = 4  # the first object slot after Simon's whip and weapon


class ToyConsole:
    def __init__(self, enemy: bool) -> None:
        self.ram = np.zeros(2048, np.uint8)
        self.ram[0x28], self.ram[0x2A], self.ram[HEALTH] = 1, 3, 64  # stage 1, three lives, full health
        self.ram[X], self.ram[Y] = 120, 150
        if enemy:
            self.ram[TYPE + ENEMY], self.ram[X + ENEMY], self.ram[Y + ENEMY] = 5, 140, 150

    def snapshot(self) -> bytes:
        return self.ram.tobytes()

    def restore(self, state: bytes) -> np.ndarray:
        self.ram = np.frombuffer(state, np.uint8).copy()
        return self.ram.copy()

    def step(self, action: int):
        if ACTIONS[action][2]:
            self.ram[TYPE + ENEMY] = 0  # the whip lands
        elif self.ram[TYPE + ENEMY]:
            self.ram[HEALTH] = max(0, int(self.ram[HEALTH]) - 4)
        return None, self.ram.copy(), False


WALK_RIGHT = ACTIONS.index((1, 0, 0, 0))


def test_brain_plays_alone_without_enemies():
    console, look = ToyConsole(enemy=False), Lookahead()
    act, info = look.decide(console, console.ram, WALK_RIGHT)
    assert act == WALK_RIGHT and not info["checked"] and not info["overruled"]


def test_overruled_next_to_an_enemy():
    console, look = ToyConsole(enemy=True), Lookahead()
    before = console.snapshot()
    act, info = look.decide(console, console.ram, WALK_RIGHT)
    assert info["checked"] and info["overruled"] and ACTIONS[act][2] == 1  # a whip instead
    assert console.snapshot() == before  # the look-ahead restored the console
    assert look.counts == {"decisions": 1, "checked": 1, "brain": 0, "overruled": 1, "recovery": 0}
