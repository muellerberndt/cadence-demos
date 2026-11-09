"""Shared pieces of training: the console as a body with savestates, the eye's carried state,
places and their tags on the route, the progress reading, frozen play and the memory-free
reading on held-out teacher states.

One emulator per process (``Body``): power-on games, saved practice states and frozen
evaluations all run in it.
"""
from __future__ import annotations

import copy
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from cadence import Brain  # noqa: E402

from simon.console import Console  # noqa: E402
from simon.eye import INPUTS, Eye  # noqa: E402
from simon.pad import ACTIONS, NOOP, SLOTS, readings, world_x  # noqa: E402,F401
from teacher import (BLOCK, BOSS_HP, OBJ_STATE, OBJ_X, OBJ_Y, bat_position,  # noqa: E402,F401
                     note_executed, teacher_action)

EYES = {"v2": INPUTS}
DEFAULT_EYE = "v2"


def library() -> dict:
    import cadence
    return {"cadence": cadence.__version__, "numpy": np.__version__, "python": sys.version.split()[0]}


def make_sensor(eye: str = DEFAULT_EYE) -> Eye:
    if eye != "v2":
        raise ValueError("this folder has one eye, v2 (827 inputs)")
    return Eye()


def eye_of_inputs(n: int) -> str:
    if n != INPUTS:
        raise ValueError(f"no eye has {n} inputs")
    return "v2"


def to_parts(labels) -> np.ndarray:
    """36-way action indices as the four slot choices."""
    return np.array([[h + 1, v + 1, w, j] for h, v, w, j in (ACTIONS[int(i)] for i in np.atleast_1d(labels))],
                    dtype=np.int64)


def from_parts(parts) -> np.ndarray:
    parts = np.asarray(parts).reshape(-1, 4)
    return np.array([ACTIONS.index((int(h) - 1, int(v) - 1, int(w), int(j))) for h, v, w, j in parts],
                    dtype=np.int64)


def choice(raw) -> int:
    return int(from_parts(raw)[0])


class Body:
    """The process's one console, with savestates."""

    def __init__(self) -> None:
        self.console = Console()

    def power_on(self, noops: int = 0):
        return self.console.power_on(noops)

    def step(self, action: int):
        return self.console.decide(int(action))

    def snapshot(self) -> bytes:
        return self.console.env.em.get_state()

    def restore(self, state: bytes):
        self.console.env.em.set_state(state)
        return self.console.env.get_ram().copy()

    def close(self) -> None:
        self.console.close()


def sensor_state(sensor, eye: str = DEFAULT_EYE) -> dict:
    return {"eye": eye,
            "previous": None if sensor.previous is None else sensor.previous.astype(np.float32),
            "facing": sensor.facing, "recent_whip": sensor.recent_whip,
            "recent_jump": sensor.recent_jump}


def sensor_from(state: dict):
    sensor = make_sensor(state.get("eye", DEFAULT_EYE))
    sensor.previous = None if state["previous"] is None else state["previous"].astype(float)
    sensor.facing, sensor.recent_whip = state["facing"], state["recent_whip"]
    sensor.recent_jump = state["recent_jump"]
    return sensor


def place(ram) -> dict:
    ram = np.asarray(ram).astype(int)
    r = readings(ram)
    return {"stage": r["stage"], "block": int(ram[BLOCK]), "wx": world_x(ram), "y": int(ram[OBJ_Y]),
            "sx": int(ram[OBJ_X]), "state": int(ram[OBJ_STATE]), "health": r["health"],
            "lives": r["lives"], "score": r["score"], "boss_hp": int(ram[BOSS_HP]),
            "bat": bat_position(ram) is not None}


def tags_of(p: dict, label: int) -> list[str]:
    """Critical places on the route (the practice draws weigh these more)."""
    s, b, wx, y = p["stage"], p["block"], p["wx"], p["y"]
    tags = []
    if s == 1 and 1150 <= wx <= 1420:
        tags.append("stairs1")  # the hall-end stairs: approach, window, climb, upper floor
    if s == 2 and b == 1 and wx < 300 and y >= 150:
        tags.append("stage2_left")
    if s == 2 and b == 0 and 180 <= wx <= 300:
        tags.append("water_jumps")
    if s == 2 and b == 0 and 380 <= wx <= 470:
        tags.append("under_stairs")
    if s == 2 and b == 1 and wx >= 360:
        tags.append("stage2_exit")
    if s >= 3 and s != 20:
        tags.append(f"stage{s}")
    if s == 3 and p.get("bat"):
        tags.append("bat")
    if ACTIONS[label][2]:
        tags.append("whip")
    if ACTIONS[label][3]:
        tags.append("jump")
    if ACTIONS[label][1]:
        tags.append("vertical")
    return tags


class Progress:
    """100000 * stage + world x, counted on stable frames (same stage, alive, a plausible move);
    the stage-clear transition (stage 20) counts for nothing. Also the furthest stage, the first
    decision of each stage, lives lost, deaths per stage (health to 0, counted once), the world x
    reached per stage, and the bat health taken (stage 3)."""

    def __init__(self) -> None:
        self.best, self.previous, self.furthest, self.lives_lost = 0, None, 0, 0
        self.first_stage: dict[int, int] = {}
        self.deaths_by_stage: dict[str, int] = {}
        self.world_x: dict[str, int] = {}
        self.bat_hp_min, self.bat_seen = 64, False

    def update(self, before, after, ram, step: int) -> None:
        ram = np.asarray(ram)
        where = world_x(ram)
        stage = after["stage"]
        if stage == 20:
            self.previous = None
            return
        if (stage == before["stage"] and after["lives"] == before["lives"]
                and after["health"] > 0 and self.previous is not None
                and abs(where - self.previous) <= 64):
            self.best = max(self.best, 100_000 * stage + where)
            key = str(stage)
            self.world_x[key] = max(self.world_x.get(key, 0), where)
        self.previous = where if stage == before["stage"] else None
        self.furthest = max(self.furthest, stage)
        self.first_stage.setdefault(stage, step)
        self.lives_lost += int(after["lives"] < before["lives"])
        if after["health"] == 0 and before["health"] > 0:
            key = str(before["stage"])
            self.deaths_by_stage[key] = self.deaths_by_stage.get(key, 0) + 1
        if stage == 3:
            self.bat_seen = self.bat_seen or bat_position(ram) is not None
            if self.bat_seen:
                self.bat_hp_min = min(self.bat_hp_min, int(ram[BOSS_HP]))

    @property
    def bat_hp_dealt(self) -> int:
        return 64 - self.bat_hp_min


def frozen_play(brain: Brain, body: Body, noops: int, decisions: int, *, eye: str = DEFAULT_EYE,
                greedy: bool = True) -> dict:
    """One game of the brain alone from power-on (acts only; pass a deep copy)."""
    brain.reset()
    frame, ram = body.power_on(noops)
    sensor, progress = make_sensor(eye), Progress()
    step = 0
    for step in range(decisions):
        x = sensor.observe(frame, ram)[None, :]
        try:
            action = choice(brain.act(x, greedy=greedy))
        except RuntimeError:
            break
        sensor.executed(action)
        before = readings(ram)
        frame, ram, done = body.step(action)
        progress.update(before, readings(ram), ram, step)
        if done:
            break
    return {"noops": noops, "decisions": step + 1, "progress": progress.best,
            "furthest_stage": progress.furthest, "lives_lost": progress.lives_lost,
            "score": readings(ram)["score"], "first_stage": progress.first_stage,
            "world_x": progress.world_x, "deaths_by_stage": progress.deaths_by_stage,
            "bat_hp_dealt": progress.bat_hp_dealt, "passed_stairs": progress.furthest >= 2}


def frozen_evaluation(brain: Brain, body: Body, starts, decisions: int, *, eye: str = DEFAULT_EYE) -> dict:
    frozen = copy.deepcopy(brain)
    return {"greedy": [frozen_play(frozen, body, n, decisions, eye=eye) for n in starts]}


def summarize(evaluation: dict) -> dict:
    games = evaluation["greedy"]
    deaths: dict[str, int] = {}
    for g in games:
        for k, v in g["deaths_by_stage"].items():
            deaths[k] = deaths.get(k, 0) + v
    return {"progress": [g["progress"] for g in games], "stage": [g["furthest_stage"] for g in games],
            "past_stairs": int(sum(g["furthest_stage"] >= 2 for g in games)),
            "stage3": int(sum(g["furthest_stage"] >= 3 for g in games)),
            "stage4": int(sum(g["furthest_stage"] >= 4 for g in games)),
            "world_x": [g["world_x"] for g in games], "bat_hp_dealt": [g["bat_hp_dealt"] for g in games],
            "deaths_by_stage": deaths, "lives_lost": [g["lives_lost"] for g in games]}


def predict_reading(brain: Brain, validation: dict, batch: int = 256) -> dict:
    """``Brain.predict`` (no live memory read or changed) on held-out teacher states: agreement
    with the teacher whole and per slot."""
    x, y = validation["x"], validation["y"]
    predicted = np.full(len(y), -1, dtype=np.int64)
    for start in range(0, len(y), batch):
        try:
            predicted[start:start + batch] = from_parts(brain.predict(x[start:start + batch]))
        except RuntimeError:
            pass
    mine = np.array([ACTIONS[int(a)] if a >= 0 else (9, 9, 9, 9) for a in predicted])
    theirs = np.array([ACTIONS[int(a)] for a in y])
    return {"rows": int(len(y)), "refused": int((predicted < 0).sum()),
            "agreement": float(np.mean(predicted == y)),
            "slots": [float(np.mean(mine[:, k] == theirs[:, k])) for k in range(4)]}


def load_practice(path: Path) -> list[dict]:
    with open(path, "rb") as handle:
        return pickle.load(handle)


def load_validation(path: Path) -> dict:
    data = np.load(path, allow_pickle=True)
    tags = {k[4:]: data[k] for k in data.files if k.startswith("tag_")}
    return {"x": data["x"].astype(float), "y": data["y"].astype(np.int64), "tags": tags}
