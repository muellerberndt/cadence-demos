"""A ranked battle royale: every robot for itself until one is left or the clock runs out.

The ring closes over the fight, so hiding is paid for in hit points. Each robot's reward
per moment is the damage it dealt minus the damage it took (burn included), in units of
twenty hit points; the fight's end is a declared boundary of its continuing life, paid by
its placement (+1 for the winner down to -1 for the first eliminated) and delivered,
``done`` set, with the first observation of its next fight, as ``live`` defines terminal
outcomes. A robot that keeps one life keeps everything it learned: the brain that fights
the next royale is the brain that fought this one.

Readings per fighter: placement, damage dealt and taken, moments alive, the share of aroused
moments, learning sweeps and refusals. The replay records every moment for the viewer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .brain import hold_commands, motor_names
from .parts import Blueprint
from .pool import BrainPool
from .senses import input_names, observe
from .world import Arena, Robot

DAMAGE_SCALE = 20.0
APPROACH_PAY = 3.0  # reward per metre closed on the nearest rival
APPROACH_CAP = 0.3
MODE_CODES = {"routine": 0, "aroused": 1, "random": 2, "frozen": 3, "refused": 4}
DEAD = 9
REPLAY_FORMAT = "cadence-robot-arena/replay/2"


@dataclass
class Fighter:
    name: str
    blueprint: Blueprint
    policy: str = "brain"
    brain_path: Path | None = None
    owed: tuple[float, bool] | None = None  # the previous fight's end, not yet delivered
    need: float | None = None  # the ring stage's need; None keeps the brain's gene
    reset: bool = False  # forget what life used to pay on entering the ring
    stage: dict[str, Any] | None = None  # ring-stage genes (need, heat, temperature, eta, reset)
    stats: dict[str, Any] = field(default_factory=dict)


def place_score(place: int, n: int) -> float:
    """+1 for the winner, -1 for the first out, linear between."""
    if n <= 1:
        return 0.0
    return 1.0 - 2.0 * (place - 1) / (n - 1)


def run_royale(
    fighters: list[Fighter],
    *,
    seed: int = 0,
    duration: int = 1200,
    zone_moments: int = 1000,
    radius: float = 10.0,
    zone_end: float = 2.5,
    workers: int = 0,
    record: bool = True,
    save: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    if len(fighters) < 2:
        raise ValueError("a royale needs at least two fighters")
    robots = [Robot.build(i, f.blueprint) for i, f in enumerate(fighters)]
    arena = Arena(robots, radius=radius, zone_end=zone_end, zone_moments=zone_moments, seed=seed)
    n = len(fighters)
    frames: list[dict[str, Any]] = []
    acc = {
        f.name: {
            "moments": 0, "aroused": 0, "sweeps": 0, "learning_sweeps": 0, "refused": 0,
            "ms": 0.0, "dealt": 0.0, "taken": 0.0, "burn": 0.0, "hits": 0, "outside": 0,
            "travelled": 0.0, "closing": 0,
        }
        for f in fighters
    }
    last_readings: dict[str, dict] = {}
    last_rewards: dict[str, float] = {f.name: 0.0 for f in fighters}
    # feedback owed to each brain with its next observation: the previous fight's end first
    feedback: dict[str, tuple[float, bool] | None] = {f.name: f.owed for f in fighters}
    last_reward: dict[str, float] = {f.name: 0.0 for f in fighters}
    with BrainPool(workers) as pool:
        for f in fighters:
            pool.add(f.name, f.blueprint, f.policy, f.brain_path, need=f.need, reset=f.reset, stage=f.stage)
        if record:
            frames.append(_frame(arena, fighters, {}, {}))
        for t in range(duration):
            alive = arena.alive()
            if len(alive) <= 1:
                break
            rows = []
            for robot in alive:
                f = fighters[robot.rid]
                owed = feedback[f.name]
                rows.append((f.name, observe(robot, arena), None if owed is None else owed[0],
                             False if owed is None else owed[1]))
            readings = pool.moment(rows)
            last_readings = readings
            before = {robot.rid: (robot.x, robot.y) for robot in alive}
            gap_before = {robot.rid: _nearest_gap(robot, alive) for robot in alive}
            commands = {}
            for robot in alive:
                f = fighters[robot.rid]
                r = readings[f.name]
                commands[robot.rid] = r["commands"] if not r["refused"] else hold_commands(f.blueprint)
                a = acc[f.name]
                a["moments"] += 1
                a["aroused"] += int(r["aroused"])
                a["sweeps"] += r["sweeps"]
                a["learning_sweeps"] += r["learning_sweeps"]
                a["refused"] += int(r["refused"])
                a["ms"] += r["ms"]
            out = arena.step(commands)
            for robot in alive:
                f = fighters[robot.rid]
                o = out[robot.rid]
                reward = (o["dealt"] - o["taken"]) / DAMAGE_SCALE
                closed = gap_before[robot.rid] - _nearest_gap(robot, arena.alive())
                if math.isfinite(closed):
                    reward += float(np.clip(APPROACH_PAY * closed, -APPROACH_CAP, APPROACH_CAP))
                    acc[f.name]["closing"] += int(closed > 0.005)
                last_reward[f.name] = reward
                last_rewards[f.name] = reward
                feedback[f.name] = (reward, False)
                a = acc[f.name]
                a["dealt"] += o["dealt"]
                a["taken"] += o["taken"]
                a["burn"] += o["zone"]
                a["hits"] += len(robot.hits)
                a["outside"] += int(o["outside"])
                bx, by = before[robot.rid]
                a["travelled"] += math.hypot(robot.x - bx, robot.y - by)
            if record:
                frames.append(_frame(arena, fighters, readings, last_rewards))
            if verbose and (t + 1) % 200 == 0:
                standing = ", ".join(f"{fighters[r.rid].name} {r.hp:.0f}" for r in arena.alive())
                print(f"  moment {t + 1}: ring {arena.zone_radius():.1f} m; {standing}", flush=True)
        arena.finish()
        # the fight's end: placement paid as a terminal outcome, owed to the next fight
        results = []
        for robot in robots:
            f = fighters[robot.rid]
            assert robot.place is not None
            score = place_score(robot.place, n)
            f.owed = (last_reward[f.name] + score, True)
            a = acc[f.name]
            m = max(1, a["moments"])
            f.stats = {
                "place": robot.place,
                "score": round(score, 3),
                "alive": robot.alive,
                "hp": round(robot.hp, 1),
                "died_at": robot.died_at,
                "moments": a["moments"],
                "dealt": round(a["dealt"], 1),
                "taken": round(a["taken"], 1),
                "burn": round(a["burn"], 1),
                "hits": a["hits"],
                "moments_outside": a["outside"],
                "travelled_m": round(a["travelled"], 1),
                "closing_share": round(a["closing"] / m, 3),
                "aroused_share": round(a["aroused"] / m, 3),
                "sweeps_per_moment": round(a["sweeps"] / m, 1),
                "learning_sweeps": a["learning_sweeps"],
                "refused": a["refused"],
                "ms_per_moment": round(a["ms"] / m, 2),
            }
            results.append({"name": f.name, "policy": f.policy, **f.stats})
            if save and f.policy == "brain" and f.brain_path is not None:
                pool.save(f.name, f.brain_path)
        described = pool.describe()
    results.sort(key=lambda r: r["place"])
    replay = None
    if record:
        replay = {
            "format": REPLAY_FORMAT,
            "seed": seed,
            "radius": radius,
            "zone_end": zone_end,
            "zone_moments": zone_moments,
            "duration": duration,
            "moments": arena.t,
            "dt": 0.05,
            "robots": [
                {
                    "name": f.name,
                    "policy": f.policy,
                    "chassis": f.blueprint.chassis,
                    "radius": f.blueprint.radius,
                    "hp": f.blueprint.hp,
                    "parts": [p.to_dict() for p in f.blueprint.parts],
                    "place": f.stats["place"],
                    "inputs": input_names(f.blueprint),
                    "slots": f.blueprint.slots,
                    "motors": motor_names(f.blueprint),
                }
                for f in fighters
            ],
            "results": results,
            "frames": frames,
        }
    return {
        "seed": seed,
        "moments": arena.t,
        "results": results,
        "brains": {name: described.get(name, {}) for name in described},
        "replay": replay,
    }


def _nearest_gap(robot: Robot, others: list[Robot]) -> float:
    """Rim-to-rim distance to the nearest other living robot; infinite when alone."""
    best = math.inf
    for other in others:
        if other is robot or not other.alive:
            continue
        d = math.hypot(other.x - robot.x, other.y - robot.y) - robot.radius - other.radius
        best = min(best, d)
    return best


def _frame(
    arena: Arena, fighters: list[Fighter], readings: dict[str, dict], rewards: dict[str, float]
) -> dict[str, Any]:
    rows = []
    hits = []
    for robot in arena.robots:
        f = fighters[robot.rid]
        reading = readings.get(f.name) if robot.alive else None
        if not robot.alive:
            mode = DEAD
        else:
            mode = MODE_CODES.get(reading["mode"], 4) if reading else MODE_CODES.get(f.policy, 0)
        brain = None
        if reading and reading.get("activity"):
            act = reading["activity"]
            brain = [
                act["sensory"], act["association"], act["motor"],
                round(float(reading["level"]), 3), round(float(reading["want"]), 3),
                int(reading["sweeps"]), int(reading["learning_sweeps"]),
                round(float(rewards.get(f.name, 0.0)), 3),
            ]
        legs = [i for i, p in enumerate(f.blueprint.parts) if p.kind == "leg"]
        arms = [i for i, p in enumerate(f.blueprint.parts) if p.kind == "arm"]
        rows.append(
            [
                round(robot.x, 3),
                round(robot.y, 3),
                round(robot.heading, 3),
                round(robot.hp, 1),
                mode,
                [round(float(robot.stride[i]), 2) for i in legs],
                [int(robot.planted[i]) for i in legs],
                [round(float(robot.angle[i]), 2) for i in arms],
                [round(float(robot.spin[i]), 2) for i in arms],
                brain,
                list(reading["commands"]) if reading else None,
            ]
        )
        for x, y, damage in robot.hits:
            hits.append([round(x, 2), round(y, 2), round(damage, 1), robot.rid])
    return {"t": arena.t, "zone": round(arena.zone_radius(), 3), "robots": rows, "hits": hits}


def elo_update(ratings: dict[str, float], places: dict[str, int], k: float = 32.0) -> dict[str, float]:
    """Multiplayer Elo: every pair is one game decided by placement; K is shared by the pairs."""
    names = list(places)
    n = len(names)
    if n < 2:
        return {}
    delta = {name: 0.0 for name in names}
    for i in range(n):
        for j in range(i + 1, n):
            a, b = names[i], names[j]
            expected = 1.0 / (1.0 + 10 ** ((ratings[b] - ratings[a]) / 400.0))
            if places[a] == places[b]:
                actual = 0.5
            else:
                actual = 1.0 if places[a] < places[b] else 0.0
            change = k / (n - 1) * (actual - expected)
            delta[a] += change
            delta[b] -= change
    return delta
