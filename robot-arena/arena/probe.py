"""Fingerprint a robot's policy: what it does in declared situations, read from a copy.

Each situation places a target robot at a bearing and distance, or the ring's edge near,
and reads the greedy command per motor and the base policy's probabilities from a fresh
copy of the saved brain (the living brain is never touched). A policy that gives the same
commands in every situation is observation-blind; the share of distinct answers across the
situations is the first count to check before any claim about learning.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from cadence import Brain

from .parts import Blueprint
from .senses import input_names, observe
from .world import Arena, Robot
from .nursery import DUMMY


def situations(blueprint: Blueprint) -> list[tuple[str, np.ndarray]]:
    robot = Robot.build(0, blueprint)
    target = Robot.build(1, DUMMY)
    arena = Arena([robot, target], radius=10.0, zone_end=10.0, zone_moments=1, spawn=False)
    rows = []
    robot.place_at(0.0, 0.0, 0.0)
    for label, bearing in (("ahead", 0.0), ("left", 90.0), ("behind", 180.0), ("right", -90.0)):
        a = math.radians(bearing)
        target.place_at(4.0 * math.cos(a), 4.0 * math.sin(a), 0.0)
        rows.append((f"target {label} 4 m", observe(robot, arena)))
    target.place_at(1.6, 0.0, 0.0)
    rows.append(("target ahead, touching", observe(robot, arena)))
    target.place_at(50.0, 50.0, 0.0)  # out of sight
    rows.append(("nothing in sight", observe(robot, arena)))
    arena2 = Arena([robot], radius=10.0, zone_end=4.0, zone_moments=1, spawn=False)
    arena2.t = 1
    robot.place_at(3.0, 0.0, 0.0)
    rows.append(("edge ahead 1 m", observe(robot, arena2)))
    robot.place_at(5.0, 0.0, 0.0)
    rows.append(("outside the ring, centre behind", observe(robot, arena2)))
    return rows


def fingerprint(blueprint: Blueprint, brain_path: str | Path) -> dict[str, Any]:
    rows = []
    answers = []
    tables = []
    for label, x in situations(blueprint):
        copy = Brain.load(Path(brain_path))
        try:
            action = copy.act(x, greedy=True)
        except RuntimeError as error:
            rows.append({"situation": label, "refused": str(error)[:80]})
            continue
        state = copy.basal_ganglia.state
        probs = np.asarray(copy.basal_ganglia.probabilities(state))
        commands = [int(c) for c in np.atleast_1d(action[0])]
        answers.append(tuple(commands))
        # per-slot probabilities of the chosen command: probabilities are (1, slots, max size)
        table = np.atleast_3d(probs) if probs.ndim == 3 else probs[None, None, :]
        confidence = [round(float(table[0, k, c]), 2) for k, c in enumerate(commands)]
        tables.append(np.asarray(table[0], dtype=float))
        rows.append({"situation": label, "commands": commands, "confidence": confidence})
    sensitivity = 0.0
    if tables:
        stack = np.stack(tables)  # situations x slots x max size
        sensitivity = float(np.mean(stack.max(axis=0) - stack.min(axis=0)))
    return {
        "robot": blueprint.name,
        "inputs": input_names(blueprint),
        "rows": rows,
        "distinct_answers": len(set(answers)),
        "situations": len(rows),
        "sensitivity": round(sensitivity, 3),
    }


def fingerprint_text(report: dict[str, Any]) -> str:
    lines = [f"{report['robot']}: {report['distinct_answers']} distinct greedy answers in {report['situations']} situations; "
             f"policy sensitivity {report.get('sensitivity', 0):.3f} (mean range of a command's probability across the situations)"]
    for row in report["rows"]:
        if "refused" in row:
            lines.append(f"  {row['situation']:32} refused: {row['refused']}")
        else:
            lines.append(f"  {row['situation']:32} commands {row['commands']}  p {row['confidence']}")
    return "\n".join(lines)
