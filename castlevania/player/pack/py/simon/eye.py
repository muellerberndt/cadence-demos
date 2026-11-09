"""What the brain sees: 827 numbers per decision, from the screen and a few RAM readings.

| Slice | Count | Content |
| --- | --- | --- |
| `[0:192]` | 192 | scene: the gray frame, rows 40-231, pooled to 12 x 16 cells of 16 px, as 1.2 v - 0.6 |
| `[192:384]` | 192 | motion: the scene minus the previous decision's scene, times 1.2 |
| `[384:576]` | 192 | fovea ahead: a 64 x 48 px window on Simon, 16 px behind him and 48 px ahead (mirrored when he faces left, so ahead is always on the right), pooled 4 x 4 to 12 x 16 cells |
| `[576:588]` | 12 | body: screen x and y, scroll, world x, health, lives, stage, facing, the last command's facing, whip and jump, each in [-0.6, 0.6] |
| `[588:780]` | 192 | fovea behind: the same window mirrored about Simon, 48 px behind and 16 ahead |
| `[780:798]` | 18 | one-hot stage |
| `[798:802]` | 4 | one-hot block of the stage |
| `[802:812]` | 10 | one-hot body state: ground, jump, whip, crouch, stairs, knocked back, stepping onto stairs, falling, other, recovering |
| `[812:827]` | 15 | one-hot floor: Simon's y in rows of 16 px |

Positions come from RAM (Simon's object slot, `0x38C`/`0x354`, facing `0x450`); everything
else in the window is pixels.
"""
from __future__ import annotations

import numpy as np

from .pad import (ACTIONS, BLOCK, BODY_STATE, FACING, HEALTH, LIVES, SCROLL_HI, SCROLL_LO, STAGE,
                  SX, SY, world_x)

BEHIND, AHEAD, ABOVE, BELOW, CELL = 16, 48, 24, 24, 4
FOVEA_W, FOVEA_H = (BEHIND + AHEAD) // CELL, (ABOVE + BELOW) // CELL  # 16 x 12 cells
PAD = 64
STAGES, BLOCKS, STATES, FLOORS = 18, 4, 10, 15
INPUTS = 192 + 192 + FOVEA_W * FOVEA_H + 12 + FOVEA_W * FOVEA_H + STAGES + BLOCKS + STATES + FLOORS  # 827
SLICES = {"scene": (0, 192), "motion": (192, 384), "ahead": (384, 576), "body": (576, 588),
          "behind": (588, 780), "stage": (780, 798), "block": (798, 802), "state": (802, 812),
          "floor": (812, 827)}


def fovea_window(ram) -> tuple[int, int, int, int, int]:
    """The ahead window's screen rectangle (left, top, right, bottom) and the facing."""
    x, y = int(ram[SX]), int(ram[SY])
    facing = -1 if int(ram[FACING]) else 1
    left, right = (x - BEHIND, x + AHEAD) if facing > 0 else (x - AHEAD, x + BEHIND)
    return left, y - ABOVE, right, y + BELOW, facing


def one_hot(index: int, size: int) -> np.ndarray:
    out = np.full(size, -0.6)
    if 0 <= index < size:
        out[index] = 0.6
    return out


class Eye:
    """The eye of one game: it keeps the previous scene and the last executed command."""

    inputs = INPUTS

    def __init__(self) -> None:
        self.previous = None
        self.facing = 1
        self.recent_whip = self.recent_jump = False

    def executed(self, index: int) -> None:
        horizontal, _, whip, jump = ACTIONS[int(index)]
        if horizontal:
            self.facing = horizontal
        self.recent_whip, self.recent_jump = bool(whip), bool(jump)

    def observe(self, frame, ram) -> np.ndarray:
        frame, ram = np.asarray(frame), np.asarray(ram)
        if frame.shape != (240, 256, 3):
            raise ValueError("expected a 240 x 256 RGB frame")
        gray = frame.astype(float) @ np.array([0.299, 0.587, 0.114]) / 255.0
        scene = gray[40:232].reshape(12, 16, 16, 16).mean(axis=(1, 3))
        motion = np.zeros_like(scene) if self.previous is None else scene - self.previous
        left, top, right, bottom, facing = fovea_window(ram)
        padded = np.pad(gray, PAD, mode="edge")
        window = padded[top + PAD:bottom + PAD, left + PAD:right + PAD]
        if facing < 0:
            window = window[:, ::-1]
        ahead = window.reshape(FOVEA_H, CELL, FOVEA_W, CELL).mean(axis=(1, 3))
        x = int(ram[SX])
        bleft, bright = (x - AHEAD, x + BEHIND) if facing > 0 else (x - BEHIND, x + AHEAD)
        back = padded[top + PAD:bottom + PAD, bleft + PAD:bright + PAD]
        if facing > 0:
            back = back[:, ::-1]
        behind = back.reshape(FOVEA_H, CELL, FOVEA_W, CELL).mean(axis=(1, 3))
        body = np.array([
            0.6 * (2 * int(ram[SX]) / 255 - 1), 0.6 * (2 * int(ram[SY]) / 239 - 1),
            0.6 * (2 * int(ram[SCROLL_LO]) / 255 - 1),
            0.6 * (2 * min(int(ram[SCROLL_HI]), 40) / 40 - 1),
            0.6 * (2 * min(world_x(ram), 2047) / 2047 - 1),
            0.6 * (2 * int(ram[HEALTH]) / 64 - 1),
            0.6 * (2 * min(int(ram[LIVES]), 5) / 5 - 1),
            0.6 * (2 * min(int(ram[STAGE]), 18) / 18 - 1),
            0.6 * facing, 0.6 * self.facing,
            0.6 if self.recent_whip else -0.6, 0.6 if self.recent_jump else -0.6,
        ])
        state = int(ram[BODY_STATE])
        output = np.concatenate((
            1.2 * scene.ravel() - 0.6, 1.2 * motion.ravel(), 1.2 * ahead.ravel() - 0.6, body,
            1.2 * behind.ravel() - 0.6, one_hot(int(ram[STAGE]), STAGES), one_hot(int(ram[BLOCK]), BLOCKS),
            one_hot(state if state < 8 else (8 if state != 9 else 9), STATES),
            one_hot(int(ram[SY]) // 16, FLOORS)))
        if output.shape != (INPUTS,) or not np.isfinite(output).all():
            raise ValueError("invalid eye reading")
        self.previous = scene.copy()
        return output
