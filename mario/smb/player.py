"""The brain playing: one attempt, and the five-life gauntlet.

An attempt ends at the flag, at a death, after 40 decisions without a new furthest x ("stands
still"), or at 900 decisions. The brain plays frozen and greedy: `Brain.predict` on the present
observation, nothing learned while it plays.
"""
from __future__ import annotations

import numpy as np

from .console import Console
from .eye import ACTION_NAMES, Mario

STUCK, CAP = 40, 900
RETRY_IDLE = (0, 37, 83, 110, 131)  # idle frames before try 1..5 of a level: the emulator is
# deterministic, so an identical restart would replay the identical death
ORDER = [f"{w}-{s}" for w in range(1, 9) for s in range(1, 5)]
# Start sets: idle frames before the first decision.
TRAIN_POOL = tuple(s for s in range(80) if not 32 <= s <= 41)  # the training and selection starts
HELD = tuple(range(32, 42)) + tuple(range(80, 100)) + tuple(range(100, 140, 2))  # 50: W1b was picked on these
FRESH = tuple(range(140, 190))  # 50: never seen in training or selection, read once for the card


def choose(brain, obs: np.ndarray) -> int:
    return int(np.asarray(brain.predict(obs[None])).reshape(-1)[0])


def attempt(brain, rom, level: str, idle: int, console: Console | None = None, on_frame=None,
            trace: bool = False) -> dict:
    """One attempt at `level` ("1-3") after `idle` idle frames. on_frame(screen, action) is called for
    every emulator frame (for a window or a video)."""
    w, s = (int(v) for v in level.split("-"))
    m = Mario(rom, w, s, idle, console)
    acts = []
    while not m.done and m.decisions < CAP and m.stuck < STUCK:
        a = choose(brain, m.observation())
        frames = [] if on_frame else None
        m.step(a, frames)
        acts.append(a)
        for f in frames or ():
            on_frame(f, a)
    end = "flag" if m.flag else ("died" if m.done else ("stood still" if m.stuck >= STUCK else "cap"))
    out = dict(level=level, idle=idle, end=end, x=int(m.max_x), decisions=m.decisions)
    if trace:
        out["actions"] = [ACTION_NAMES[a] for a in acts]
    return out


def gauntlet(brain, rom, lives: int = 5, on_frame=None, on_attempt=None) -> list[dict]:
    """The real start of 1-1 and five lives. A flag moves on to the next level; a death or standing
    still costs a life and restarts the current level (later idle frames, small Mario)."""
    log, li = [], 0
    while lives > 0 and li < len(ORDER):
        level = ORDER[li]
        tries = sum(1 for e in log if e["level"] == level)
        if on_attempt:
            on_attempt(level, tries + 1, lives)
        r = attempt(brain, rom, level, RETRY_IDLE[min(tries, len(RETRY_IDLE) - 1)], on_frame=on_frame, trace=True)
        r["lives_before"] = lives
        log.append(r)
        if r["end"] == "flag":
            li += 1
        else:
            lives -= 1
    return log
