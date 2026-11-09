"""What the brain senses (2,000 numbers per decision) and the body that carries out its choice.

Eyes (1,664): the playfield below the score bar in grey, averaged in 8 x 8 px blocks to 26 x 32,
as distance from the frame's most common grey (the sky above ground, black underground and in
castles), for the present decision and the previous one.
Body (336): 42 readings repeated 8 times. 38 come from RAM and are Mario's own body only: x and y
speed (population codes), float state (ground, jumping, falling, pole), still rising, facing, power
(small, big, fire), hurt and star timers, time left. 4 are the buttons held during the last
decision (A, B, right, left). No enemy, tile or pit is read from RAM: the world comes from the eyes.

One decision holds one of 7 button combinations for 4 frames.
"""
from __future__ import annotations

import numpy as np

from .console import Console

FRAMES = 4
ACTIONS = [0x00, 0x80, 0x81, 0x82, 0x83, 0x01, 0x40]  # NES pad bits: right 0x80, left 0x40, B 0x02, A 0x01
ACTION_NAMES = ["none", "right", "right+jump", "run", "run+jump", "jump", "left"]
TOP, ROWS, COLS, BLOCK = 32, 26, 32, 8
HELD_BITS = (0x01, 0x02, 0x80, 0x40)  # A, B, right, left
COPIES = 8
N_EYES = 2 * ROWS * COLS
N_BODY = 38 + len(HELD_BITS)
N_INPUTS = N_EYES + N_BODY * COPIES  # 2,000


def background_grey(grey: np.ndarray) -> float:
    q = np.clip(np.round(grey * 255), 0, 255).astype(np.int64).reshape(-1)
    return float(np.bincount(q, minlength=256).argmax()) / 255.0


def eye(screen: np.ndarray) -> np.ndarray:
    """240 x 256 x 3 screen -> 832 block greys, as distance from the frame's background grey."""
    s = screen[TOP:TOP + ROWS * BLOCK].astype(np.float32)
    grey = (s[..., 0] * 0.299 + s[..., 1] * 0.587 + s[..., 2] * 0.114) / 255.0
    blocks = grey.reshape(ROWS, BLOCK, COLS, BLOCK).mean(axis=(1, 3))
    return np.abs(blocks - background_grey(grey)).reshape(-1)


def _pop(v: float, lo: float, hi: float, n: int) -> np.ndarray:
    """Population code: n bins over [lo, hi], a soft bump around v."""
    centres = np.linspace(lo, hi, n); w = (hi - lo) / (n - 1)
    return np.exp(-0.5 * ((np.clip(v, lo, hi) - centres) / (0.6 * w)) ** 2)


def body_sense(console: Console) -> np.ndarray:
    """Mario's own body from RAM (38 numbers)."""
    ram = console.ram
    xs = float(np.int8(np.uint8(ram[0x0057]))); ys = float(np.int8(np.uint8(ram[0x009F])))
    fl = int(ram[0x001D]); face = int(ram[0x0033]); pw = int(ram[0x0756])
    v = [_pop(xs, -40, 40, 9), _pop(ys, -5, 5, 9), np.eye(4)[min(fl, 3)], [1.0 if ys < 0 else 0.0],
         [1.0 if face == 1 else 0.0, 1.0 if face == 2 else 0.0], np.eye(3)[min(pw, 2)],
         [1.0 if ram[0x079E] > 0 else 0.0, 1.0 if ram[0x079F] > 0 else 0.0],
         _pop(float(console.time) / 400.0, 0, 1, 8)]
    return np.concatenate([np.asarray(a, dtype=np.float32) for a in v])


class Mario:
    """One attempt at one level: the console plus the brain's senses and Mario's progress.
    `idle` = frames the game runs on before the first decision (which changes where enemies are)."""

    def __init__(self, rom, world: int = 1, stage: int = 1, idle: int = 0, console: Console | None = None):
        self.console = console or Console(rom, world, stage)
        screen = self.console.reset()
        for _ in range(idle):
            screen, _, _, _ = self.console.step(0)
        self.cur = eye(screen)
        self.prev = self.cur.copy()
        self.screen = screen.copy()
        self.held = 0x00
        self.done = self.flag = False
        self.decisions = 0
        self.raw_x = self.console.x
        self.off = 0  # x carried across an area change (an exit pipe restarts x near 0)
        self.area = None
        self.x = self.max_x = self.raw_x
        self.stuck = 0  # decisions since the furthest x last grew

    def observation(self) -> np.ndarray:
        held = np.array([1.0 if self.held & b else 0.0 for b in HELD_BITS])
        body = np.concatenate([body_sense(self.console), held])
        return np.concatenate([self.cur, self.prev, np.tile(body, COPIES)])

    def step(self, action: int, frames: list | None = None) -> None:
        """Hold ACTIONS[action] for 4 frames (fewer if the attempt ends)."""
        screen = self.screen
        for _ in range(FRAMES):
            screen, _, done, info = self.console.step(ACTIONS[action])
            if frames is not None:
                frames.append(screen.copy())
            if done:
                self.done, self.flag = True, bool(info["flag_get"])
                break
        self.screen = screen.copy()
        self.prev, self.cur = self.cur, eye(screen)
        self.held = ACTIONS[action]
        raw = self.console.x
        if raw >= 0xF000:  # a loop castle's loop-back wraps the page byte
            raw -= 65536
        area = int(self.console.ram[0x0750])
        if raw < self.raw_x - 600 and not self.done and area != (area if self.area is None else self.area):
            self.off += self.raw_x + 16 - raw  # a new area (pipe), not a step back
        self.area, self.raw_x = area, raw
        self.x = raw + self.off
        if self.x > self.max_x:
            self.max_x, self.stuck = self.x, 0
        else:
            self.stuck += 1
        self.decisions += 1
