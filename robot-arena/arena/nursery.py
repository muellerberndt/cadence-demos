"""The nursery: an accelerated, lonely arena where a newborn robot learns to move and hit.

A training dummy stands somewhere in the ring; it never moves and never strikes back, but
ramming it hurts both. The world pays progress toward the dummy, damage dealt, and one unit
when the dummy is destroyed; damage taken is suffering. A dummy that is destroyed, or that
has stood for ``relocate`` moments, reappears somewhere else, so approaching is a repeated
problem and not a one-off. The ring stands still at ``RING`` metres: the strip along the wall
burns, as the closing ring will in a fight, so pressing against the wall is never free. The
pupil cannot die here: every pain is felt and paid, but its hit points are restored each
moment, so a life of learning is not cut short by a ram or a stay in the burn.

The nursery runs headless as fast as the brain settles: ``moments per second`` against the
body's twenty moments per second says how accelerated it is. The same life continues into
the fights: the checkpoint written here is the brain that fights.

Readings per block of moments, all counts a robot cannot fake: metres of progress toward
the dummy, dummies destroyed, damage dealt and taken, the share of aroused moments, sweeps
per moment and milliseconds per moment. The uniform-random policy with the same body is the
baseline; a frozen newborn (greedy, never learning) is the control for learning.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

from .brain import RobotBrain, make_policy
from .parts import Blueprint, Part
from .senses import observe
from .world import Arena, Robot

DUMMY = Blueprint("Dummy", "medium", (Part("leg", 180.0),), seed=0, policy="random")
DUMMY_HP = 60.0
RING = 8.5  # m, the nursery's standing ring; outside it burns
PROGRESS_PAY = 10.0  # reward per metre of approach (0.5 per moment at 1 m/s)
PROGRESS_CAP = 0.5
DAMAGE_SCALE = 20.0  # hit points that pay or cost one unit
KILL_PAY = 1.0


def _place_dummy(arena: Arena, robot: Robot, dummy: Robot, rng: np.random.Generator) -> None:
    for _ in range(100):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(4.0, 7.0)
        x, y = robot.x + d * math.cos(a), robot.y + d * math.sin(a)
        if math.hypot(x, y) < arena.zone_radius() - dummy.radius - 0.5:
            break
    dummy.place_at(x, y, rng.uniform(-math.pi, math.pi))
    dummy.hp = DUMMY_HP
    dummy.alive = True
    dummy.place = dummy.died_at = None


def run_nursery(
    blueprint: Blueprint,
    *,
    moments: int = 6000,
    seed: int = 0,
    policy: str = "brain",
    brain_path: str | Path | None = None,
    owed: tuple[float, bool] | None = None,
    block: int = 500,
    relocate: int = 400,
    save_to: str | Path | None = None,
    verbose: bool = False,
    probe_every: int = 0,
) -> dict[str, Any]:
    """Run one physical nursery episode without resetting its brain.

    ``owed`` is the preceding episode's outcome, delivered with the first observation.
    Save the returned ``owed`` beside the brain checkpoint and pass it to the next
    nursery or fight: the final executed command's real outcome is still pending.
    Ending this physical world is a declared terminal boundary, as for a royale.
    """
    rng = np.random.default_rng(seed)
    probes: list[dict[str, Any]] = []
    robot = Robot.build(0, blueprint)
    dummy = Robot.build(1, DUMMY)
    arena = Arena([robot, dummy], radius=10.0, zone_end=RING, zone_moments=1, seed=seed, spawn=False)
    arena.t = 1  # the ring stands at RING from the first moment
    robot.place_at(0.0, 0.0, rng.uniform(-math.pi, math.pi))
    _place_dummy(arena, robot, dummy, rng)
    agent = make_policy(blueprint, policy, brain_path)
    reward, done = (None, False) if owed is None else owed
    stood = 0
    blocks: list[dict[str, Any]] = []
    acc = _fresh_block()
    began = time.perf_counter()
    travelled = 0.0
    for t in range(moments):
        x = observe(robot, arena)
        reading = agent.moment(x, reward, done)
        if not (isinstance(agent, RobotBrain) and reading["refused"] and agent.has_pending()):
            done = False  # a refused forecast still owes the same terminal outcome
        before = math.hypot(dummy.x - robot.x, dummy.y - robot.y)
        px, py = robot.x, robot.y
        out = arena.step({0: reading["commands"], 1: [1]})
        robot.hp = blueprint.hp  # immortal in the nursery: the pain stays, the life goes on
        travelled += math.hypot(robot.x - px, robot.y - py)
        after = math.hypot(dummy.x - robot.x, dummy.y - robot.y)
        progress = before - after
        pay = float(np.clip(PROGRESS_PAY * progress, -PROGRESS_CAP, PROGRESS_CAP))
        pay += (out[0]["dealt"] - out[0]["taken"]) / DAMAGE_SCALE
        killed = not dummy.alive  # the dummy stands inside the ring, so only the robot kills it
        if killed:
            pay += KILL_PAY
        reward = pay
        acc["progress"] += progress
        acc["dealt"] += out[0]["dealt"]
        acc["taken"] += out[0]["taken"]
        acc["kills"] += int(killed)
        acc["burn"] += out[0]["zone"]
        acc["outside"] += int(out[0]["outside"])
        acc["reward"] += pay
        acc["aroused"] += int(reading["aroused"])
        acc["sweeps"] += reading["sweeps"]
        acc["learning_sweeps"] += reading["learning_sweeps"]
        acc["refused"] += int(reading["refused"])
        acc["ms"] += reading["ms"]
        acc["moments"] += 1
        stood += 1
        if killed or stood >= relocate:
            _place_dummy(arena, robot, dummy, rng)
            stood = 0
        if probe_every and (t + 1) % probe_every == 0 and isinstance(agent, RobotBrain):
            probes.append({"moment": t + 1, **_probe(agent, blueprint)})
        if (t + 1) % block == 0:
            blocks.append(_close_block(acc))
            if verbose:
                b = blocks[-1]
                print(
                    f"  [{blueprint.name} {policy}] moments {t + 1}: progress {b['progress_m']:.1f} m, "
                    f"kills {b['kills']}, dealt {b['dealt']:.0f}, taken {b['taken']:.0f}, reward/moment "
                    f"{b['reward_per_moment']:.3f}, aroused {b['aroused_share']:.2f}, "
                    f"{b['ms_per_moment']:.1f} ms/moment",
                    flush=True,
                )
            acc = _fresh_block()
    elapsed = time.perf_counter() - began
    # No extra command is issued just to flush feedback. Carry the actual final
    # reward, including feedback held across a refusal, into the next episode.
    pending = None
    if isinstance(agent, RobotBrain) and reward is not None:
        pending = [float(reward) + agent.owed, True]
    if save_to is not None and isinstance(agent, RobotBrain):
        agent.save(save_to)
    total = {
        "progress_m": sum(b["progress_m"] for b in blocks),
        "kills": sum(b["kills"] for b in blocks),
        "dealt": sum(b["dealt"] for b in blocks),
        "taken": sum(b["taken"] for b in blocks),
        "reward": sum(b["reward"] for b in blocks),
        "refused": sum(b["refused"] for b in blocks),
        "travelled_m": travelled,
    }
    half = len(blocks) // 2
    return {
        "robot": blueprint.name,
        "policy": policy,
        "seed": seed,
        "moments": moments,
        "block": block,
        "blocks": blocks,
        "total": total,
        "first_half": _sum_blocks(blocks[:half]),
        "second_half": _sum_blocks(blocks[half:]),
        "seconds": elapsed,
        "moments_per_second": moments / elapsed if elapsed else 0.0,
        "acceleration": (moments / elapsed) / 20.0 if elapsed else 0.0,
        "brain": agent.describe(),
        "owed": pending,
        "probes": probes,
    }


def _probe(agent: RobotBrain, blueprint: Blueprint) -> dict[str, Any]:
    """The fingerprint of the living brain's current policy, read from a saved copy."""
    import tempfile

    from .probe import fingerprint

    with tempfile.TemporaryDirectory() as folder:
        path = agent.save(Path(folder) / "probe.npz")
        report = fingerprint(blueprint, path)
    return {"distinct": report["distinct_answers"], "rows": [r.get("commands") for r in report["rows"]]}


def _fresh_block() -> dict[str, float]:
    return {
        "progress": 0.0, "dealt": 0.0, "taken": 0.0, "kills": 0, "reward": 0.0, "burn": 0.0,
        "outside": 0, "aroused": 0, "sweeps": 0, "learning_sweeps": 0, "refused": 0, "ms": 0.0,
        "moments": 0,
    }


def _close_block(acc: dict[str, float]) -> dict[str, Any]:
    n = max(1, int(acc["moments"]))
    return {
        "moments": n,
        "progress_m": round(acc["progress"], 3),
        "kills": int(acc["kills"]),
        "dealt": round(acc["dealt"], 2),
        "taken": round(acc["taken"], 2),
        "burn": round(acc["burn"], 2),
        "outside_share": round(acc["outside"] / n, 3),
        "reward": round(acc["reward"], 3),
        "reward_per_moment": round(acc["reward"] / n, 4),
        "aroused_share": round(acc["aroused"] / n, 3),
        "sweeps_per_moment": round(acc["sweeps"] / n, 1),
        "learning_sweeps": int(acc["learning_sweeps"]),
        "refused": int(acc["refused"]),
        "ms_per_moment": round(acc["ms"] / n, 2),
    }


def _sum_blocks(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    if not blocks:
        return {}
    n = sum(b["moments"] for b in blocks)
    return {
        "moments": n,
        "progress_m": round(sum(b["progress_m"] for b in blocks), 2),
        "kills": sum(b["kills"] for b in blocks),
        "dealt": round(sum(b["dealt"] for b in blocks), 1),
        "taken": round(sum(b["taken"] for b in blocks), 1),
        "reward_per_moment": round(sum(b["reward"] for b in blocks) / n, 4),
        "aroused_share": round(sum(b["aroused_share"] * b["moments"] for b in blocks) / n, 3),
    }


def save_report(report: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1) + "\n")
    return path
