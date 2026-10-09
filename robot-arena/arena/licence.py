"""The driving test: what a robot's greedy policy does in declared situations, without learning.

Four tests on fresh copies of the saved brain, acting greedily (the calm policy a watcher
sees in the ring), each a count a robot cannot fake:

- ``approach``: a dummy 5 m away at eight bearings; the share of the distance closed in 300
  moments (negative when it drives away), and dummies destroyed.
- ``escape``: outside a 5-metre ring, 7 m from its centre, facing away, left, right and
  toward it; the share of starts that get back inside within 300 moments and how long it took.
- ``engage``: the nursery's sparring partner (a wheeled spike) hunts the robot for 400 moments;
  the damage dealt and the damage taken.
- ``closing``: the robot starts 6 m out while the ring closes from 10 m to 3 m over 600
  moments; the share of moments it spends outside the ring.
- ``chase``: a target that drives away at walking pace (1 m/s) for 400 moments; the share of the gap closed.
- ``facing``: in the engage trial, the share of moments with the partner inside the front
  cone (45 degrees either side) within 3 m.
- ``spin``: the share of moments in the approach trials with the body turning fast and going
  nowhere (above 1.5 rad/s, under 0.3 m/s); ``stall``: the share standing still (under 0.1 m/s,
  not turning) with the target in sight and out of contact.

Each part has a pass mark (``PASS``); ``passed`` lists them and ``all_passed`` is the gate a
robot must clear to be shown. The licence score weighs the parts into one number (about -1
to 1) for ranking; uniform random with the same body gives the baseline for every part.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .brain import make_policy
from .nursery import DUMMY, DUMMY_HP, SPAR, SPAR_HP, spar_commands
from .parts import Blueprint
from .senses import observe
from .world import Arena, Robot

APPROACH_MOMENTS = 300
ESCAPE_MOMENTS = 300
ENGAGE_MOMENTS = 400
CLOSING_MOMENTS = 600
CHASE_MOMENTS = 400
PASS = {"approach": 0.6, "escape": 0.75, "closing_outside": 0.1, "engage_dealt": 100.0, "engage_ratio": 1.0,
        "chase": 0.3, "facing": 0.5, "spin": 0.1, "stall": 0.2}


def _policy(blueprint: Blueprint, brain_path: str | Path | None, policy: str):
    return make_policy(blueprint, "frozen" if policy == "brain" else policy, brain_path)


def approach_trials(blueprint: Blueprint, brain_path: str | Path | None, policy: str = "brain", moments: int = APPROACH_MOMENTS) -> dict[str, Any]:
    closed, kills, spin_moments, stall_moments, total = [], 0, 0, 0, 0
    for k in range(8):
        agent = _policy(blueprint, brain_path, policy)
        robot, dummy = Robot.build(0, blueprint), Robot.build(1, DUMMY)
        arena = Arena([robot, dummy], radius=10.0, zone_end=10.0, zone_moments=1, spawn=False)
        robot.place_at(0.0, 0.0, 0.0)
        a = 2 * math.pi * k / 8
        dummy.place_at(5.0 * math.cos(a), 5.0 * math.sin(a), 0.0)
        dummy.hp = DUMMY_HP
        start = math.hypot(dummy.x, dummy.y)
        reward = None
        for _ in range(moments):
            reading = agent.moment(observe(robot, arena), reward)
            out = arena.step({0: reading["commands"], 1: [1]})
            robot.hp = blueprint.hp
            reward = 0.0
            total += 1
            speed = math.hypot(robot.vx, robot.vy)
            if abs(robot.omega) > 1.5 and speed < 0.3:
                spin_moments += 1
            gap = math.hypot(dummy.x - robot.x, dummy.y - robot.y) - robot.radius - dummy.radius
            if speed < 0.1 and abs(robot.omega) < 0.3 and gap > 0.4:
                stall_moments += 1
            if not dummy.alive:
                kills += 1
                break
        gap = math.hypot(dummy.x - robot.x, dummy.y - robot.y)
        closed.append(max(-1.0, min(1.0, (start - gap) / start)) if dummy.alive else 1.0)
    return {"approach": round(sum(closed) / len(closed), 3), "approach_by_bearing": [round(c, 2) for c in closed],
            "kills": kills, "spin": round(spin_moments / max(1, total), 3), "stall": round(stall_moments / max(1, total), 3)}


def escape_trials(blueprint: Blueprint, brain_path: str | Path | None, policy: str = "brain", moments: int = ESCAPE_MOMENTS) -> dict[str, Any]:
    back, times = 0, []
    for k, facing in enumerate(("away", "left", "right", "toward")):
        agent = _policy(blueprint, brain_path, policy)
        robot = Robot.build(0, blueprint)
        arena = Arena([robot], radius=10.0, zone_end=5.0, zone_moments=1, spawn=False)
        arena.t = 1
        heading = {"away": 0.0, "left": math.pi / 2, "right": -math.pi / 2, "toward": math.pi}[facing]
        robot.place_at(7.0, 0.0, heading)
        reward = None
        entered = None
        for t in range(moments):
            reading = agent.moment(observe(robot, arena), reward)
            arena.step({0: reading["commands"]})
            robot.hp = blueprint.hp
            reward = 0.0
            if math.hypot(robot.x, robot.y) + robot.radius < 5.0:
                entered = t + 1
                break
        if entered is not None:
            back += 1
            times.append(entered)
    return {"escape": round(back / 4, 3), "escape_moments": round(sum(times) / len(times), 1) if times else None}


def engage_trial(blueprint: Blueprint, brain_path: str | Path | None, policy: str = "brain", moments: int = ENGAGE_MOMENTS) -> dict[str, Any]:
    agent = _policy(blueprint, brain_path, policy)
    robot, spar = Robot.build(0, blueprint), Robot.build(1, SPAR)
    arena = Arena([robot, spar], radius=10.0, zone_end=10.0, zone_moments=1, spawn=False)
    robot.place_at(0.0, 0.0, 0.0)
    spar.place_at(4.0, 2.0, math.pi)
    spar.hp = SPAR_HP
    dealt = taken = 0.0
    kills = facing = near = 0
    reward = None
    for _ in range(moments):
        reading = agent.moment(observe(robot, arena), reward)
        out = arena.step({0: reading["commands"], 1: spar_commands(spar, robot) if spar.alive else [1, 1, 1]})
        robot.hp = blueprint.hp
        reward = 0.0
        dealt += out[0]["dealt"]
        taken += out[0]["taken"]
        if spar.alive:
            gap = math.hypot(spar.x - robot.x, spar.y - robot.y) - robot.radius - spar.radius
            if gap < 3.0:
                near += 1
                bearing = math.atan2(spar.y - robot.y, spar.x - robot.x) - robot.heading
                bearing = (bearing + math.pi) % (2 * math.pi) - math.pi
                if abs(bearing) < math.pi / 4:
                    facing += 1
        if not spar.alive:
            kills += 1
            spar.alive = True
            spar.hp = SPAR_HP
            spar.place_at(-4.0, -2.0, 0.0)
    return {"engage_dealt": round(dealt, 1), "engage_taken": round(taken, 1), "engage_kills": kills,
            "engage_ratio": round(dealt / max(1.0, taken), 2), "facing": round(facing / max(1, near), 3) if near else 0.0}


def closing_trial(blueprint: Blueprint, brain_path: str | Path | None, policy: str = "brain", moments: int = CLOSING_MOMENTS) -> dict[str, Any]:
    """The ring closes from 10 m to 3 m over the trial; the robot starts 6 m out."""
    agent = _policy(blueprint, brain_path, policy)
    robot = Robot.build(0, blueprint)
    arena = Arena([robot], radius=10.0, zone_end=3.0, zone_moments=moments, spawn=False)
    robot.place_at(6.0, 0.0, 0.0)
    outside = 0
    reward = None
    for _ in range(moments):
        reading = agent.moment(observe(robot, arena), reward)
        out = arena.step({0: reading["commands"]})
        robot.hp = blueprint.hp
        reward = 0.0
        outside += int(out[0]["outside"])
    return {"closing_outside": round(outside / moments, 3)}


def chase_trial(blueprint: Blueprint, brain_path: str | Path | None, policy: str = "brain", moments: int = CHASE_MOMENTS) -> dict[str, Any]:
    """A target that drives away at walking pace; the share of the starting gap the robot closed."""
    agent = _policy(blueprint, brain_path, policy)
    robot, prey = Robot.build(0, blueprint), Robot.build(1, SPAR)
    arena = Arena([robot, prey], radius=10.0, zone_end=10.0, zone_moments=1, spawn=False)
    robot.place_at(-6.0, 0.0, 0.0)
    prey.place_at(-2.0, 0.0, 0.0)
    prey.hp = SPAR_HP
    start = math.hypot(prey.x - robot.x, prey.y - robot.y)
    reward = None
    for _ in range(moments):
        reading = agent.moment(observe(robot, arena), reward)
        # the prey flees along a circle of radius 6 m at half speed, spinner off
        bearing = math.atan2(-prey.y, -prey.x) - prey.heading
        bearing = (bearing + math.pi) % (2 * math.pi) - math.pi
        tangent = bearing + math.pi / 2  # keep the centre on the left: circle
        tangent = (tangent + math.pi) % (2 * math.pi) - math.pi
        if tangent > 0.3:
            cmd = [0, 2, 1]
        elif tangent < -0.3:
            cmd = [2, 0, 1]
        else:
            cmd = [2, 2, 1] if math.hypot(prey.vx, prey.vy) < 1.0 else [1, 1, 1]
        arena.step({0: reading["commands"], 1: cmd if prey.alive else [1, 1, 1]})
        robot.hp = blueprint.hp
        prey.hp = SPAR_HP  # the prey is a target, not a kill
        reward = 0.0
    gap = math.hypot(prey.x - robot.x, prey.y - robot.y)
    return {"chase": round(max(-1.0, min(1.0, (start - gap) / start)), 3)}


def licence(blueprint: Blueprint, brain_path: str | Path | None, policy: str = "brain", scale: float = 1.0) -> dict[str, Any]:
    """The four tests and the one score. ``scale`` shortens every test (for quick checks)."""
    a = approach_trials(blueprint, brain_path, policy, max(20, int(APPROACH_MOMENTS * scale)))
    e = escape_trials(blueprint, brain_path, policy, max(20, int(ESCAPE_MOMENTS * scale)))
    g = engage_trial(blueprint, brain_path, policy, max(20, int(ENGAGE_MOMENTS * scale)))
    c = closing_trial(blueprint, brain_path, policy, max(20, int(CLOSING_MOMENTS * scale)))
    h = chase_trial(blueprint, brain_path, policy, max(20, int(CHASE_MOMENTS * scale)))
    parts = {**a, **e, **g, **c, **h}
    score = (0.25 * parts["approach"] + 0.15 * parts["escape"] + 0.15 * (1.0 - parts["closing_outside"])
             + 0.15 * min(1.0, parts["engage_dealt"] / 150.0) - 0.1 * min(1.0, parts["engage_taken"] / 150.0)
             + 0.1 * parts["chase"] + 0.1 * parts["facing"] - 0.3 * parts["spin"] - 0.2 * parts["stall"])
    passed = {
        "approach": parts["approach"] >= PASS["approach"],
        "escape": parts["escape"] >= PASS["escape"],
        "closing": parts["closing_outside"] <= PASS["closing_outside"],
        "engage": parts["engage_dealt"] >= PASS["engage_dealt"] and parts["engage_ratio"] >= PASS["engage_ratio"],
        "chase": parts["chase"] >= PASS["chase"],
        "facing": parts["facing"] >= PASS["facing"],
        "spin": parts["spin"] <= PASS["spin"],
        "stall": parts["stall"] <= PASS["stall"],
    }
    return {"robot": blueprint.name, "policy": policy, "licence": round(score, 3), **parts, "passed": passed,
            "all_passed": all(passed.values()), "passes": sum(passed.values())}


def licence_text(r: dict[str, Any]) -> str:
    marks = "".join("+" if v else "-" for v in r["passed"].values())
    return (f"{r['robot']:14} {r['policy']:7} licence {r['licence']:+.2f} passes {r['passes']}/{len(r['passed'])} [{marks}] | "
            f"approach {r['approach']:+.2f} (kills {r['kills']}) escape {r['escape']:.2f} closing-out {r['closing_outside']:.2f} "
            f"engage {r['engage_dealt']:.0f}/{r['engage_taken']:.0f} facing {r['facing']:.2f} chase {r['chase']:+.2f} "
            f"spin {r['spin']:.2f} stall {r['stall']:.2f}")
