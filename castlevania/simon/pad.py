"""The pad, the RAM readings and the brain's four motor slots.

The brain answers in four slots (horizontal 3, vertical 3, whip 2, jump 2): 36 pad actions.
"""
from __future__ import annotations

from itertools import product

import numpy as np

BUTTONS = ("B", None, "SELECT", "START", "UP", "DOWN", "LEFT", "RIGHT", "A")
ACTIONS = tuple(product((-1, 0, 1), (-1, 0, 1), (0, 1), (0, 1)))  # (horizontal, vertical, whip, jump)
SLOTS = (3, 3, 2, 2)
NOOP = ACTIONS.index((0, 0, 0, 0))

# RAM addresses (NES Castlevania, PRG1)
STAGE, LIVES, HEALTH, BLOCK = 0x28, 0x2A, 0x44, 0x46
SCROLL_LO, SCROLL_HI = 0x2E, 0x2F
SX, SY, FACING, BODY_STATE = 0x38C, 0x354, 0x450, 0x46C
BOSS_HP = 0x1A9


def pad_action(index: int, buttons=BUTTONS) -> np.ndarray:
    horizontal, vertical, whip, jump = ACTIONS[int(index)]
    held = {"LEFT": horizontal == -1, "RIGHT": horizontal == 1, "UP": vertical == -1,
            "DOWN": vertical == 1, "B": whip == 1, "A": jump == 1}
    return np.array([int(held.get(name, False)) for name in buttons], dtype=np.uint8)


def from_slots(parts) -> int:
    """The pad action of one row of slot choices (as ``Brain.act`` answers)."""
    h, v, w, j = (int(p) for p in np.asarray(parts).reshape(4))
    return ACTIONS.index((h - 1, v - 1, w, j))


def buttons_of(index: int) -> list[str]:
    horizontal, vertical, whip, jump = ACTIONS[int(index)]
    out = []
    if horizontal:
        out.append("RIGHT" if horizontal > 0 else "LEFT")
    if vertical:
        out.append("DOWN" if vertical > 0 else "UP")
    if whip:
        out.append("B")
    if jump:
        out.append("A")
    return out


def world_x(ram) -> int:
    return int(ram[SCROLL_LO]) + 256 * int(ram[SCROLL_HI]) + int(ram[SX])


def readings(ram) -> dict[str, int]:
    ram = np.asarray(ram)
    score = 0
    for byte in reversed(ram[0x7FC:0x7FF]):
        score = 100 * score + 10 * (int(byte) >> 4) + (int(byte) & 0x0F)
    return {"stage": int(ram[STAGE]), "block": int(ram[BLOCK]), "lives": int(ram[LIVES]),
            "health": int(ram[HEALTH]), "x": int(ram[SX]), "y": int(ram[SY]),
            "world_x": world_x(ram), "score": score, "boss_hp": int(ram[BOSS_HP])}
