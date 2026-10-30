"""The whole job: hover over the block, lower, grasp, lift, carry above the bin the lit lamp
names, release. The caregiver's plan (``arm.caregiver.plan``) names each phase's fingertip target
and the gripper; ``--teacher gradient`` turns the target into a direction for every joint
(``teacher.job_steps``).

The job assay runs one fresh scene per trial from a random posture with the gripper open, the
policy alone for up to ``cap`` decisions, and records the stages each trial passed: reached (the
fingertip within 2.5 cm of the hover point before a grasp), grasped (the gripper closed on the
block), lifted (holding, the fingertip within 3 cm of the carrying height), carried (holding,
lifted, the fingertip within 3 cm of the ordered bin in the plane), and the release: in the bin the
lamp names (the success), in the other bin, or dropped on the table at least once.

    python -m arm091.job --brain runs/c4_sur/brain_best.npz --trials 40
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from cadence import Brain

from arm import caregiver
from arm.anatomy import EYE_SLOTS
from arm.caregiver import LIFT
from arm.eyes import Eyes
from arm.nursery import answer_of, head_of
from arm.world import ArmSpec, World, index_of, steps_of

from . import teacher

POOLS = slice(len(EYE_SLOTS), len(EYE_SLOTS) + 4)
GRIP = len(EYE_SLOTS) + 4
STAGES = ("reached", "grasped", "lifted", "carried", "right", "wrong", "dropped")


def smooth_plan(world: World) -> tuple[np.ndarray, int, str]:
    """The caregiver's plan with its targets made continuous in the state. Before the grasp the
    target sits over the block at a height that falls with the fingertip's distance from the block
    in the plane (the hover height at 4 cm or more, the grasp point when centred), so the targets
    of nearby states are nearby; the gripper closes in the grasp window. Holding, the target rises
    to the carrying height and moves toward the ordered bin as the fingertip rises; above the bin
    within 2 cm the gripper opens."""
    tip = world.tip()
    if not world.holding:
        planar = float(np.hypot(tip[0] - world.block[0], tip[1] - world.block[1]))
        top = world.block_top()
        height = (top - 0.004) + (caregiver.HOVER + 0.004) * min(1.0, planar / 0.04)
        target = np.array([world.block[0], world.block[1], height])
        window = (planar <= world.spec.grasp_reach
                  and top - world.spec.grasp_below <= tip[2] <= top + world.spec.grasp_above - world.wear)
        return target, int(window), "grasp" if window else ("lower" if planar < 0.04 else "approach")
    ordered = world.ordered_bin()
    if ordered is None:
        return np.array([tip[0], tip[1], LIFT]), 1, "hold"
    raised = float(np.clip((tip[2] - (LIFT - 0.06)) / 0.04, 0.0, 1.0))
    x = tip[0] + (ordered[0] - tip[0]) * raised
    y = tip[1] + (ordered[1] - tip[1]) * raised
    planar = float(np.hypot(tip[0] - ordered[0], tip[1] - ordered[1]))
    if planar <= 0.02 and tip[2] >= LIFT - 0.04:
        return np.array([ordered[0], ordered[1], LIFT]), 0, "release"
    return np.array([x, y, LIFT]), 1, "carry" if raised >= 1.0 else "lift"


PLANS = {"steps": caregiver.plan, "smooth": smooth_plan}


def job_labels(world: World, eyes: Eyes, rule: str = "gradient", plan: str = "steps") -> list[int]:
    """Every slot: the eye's readouts, a level per joint toward the plan's target, the gripper."""
    target, close, phase = PLANS[plan](world)
    steps = teacher.job_steps(world, target, phase) if rule == "gradient" else caregiver.ideal_steps(world, target)
    return eyes.labels(world) + [index_of(s) for s in steps] + [int(close)]


def job_assay(brain: Brain | None, head, trials: int, seed: int, cap: int = 80, dark: bool = False,
              policy: str = "brain", rule: str = "gradient", plan: str = "steps") -> dict:
    """Stage rates over ``trials`` fresh scenes; ``policy`` is brain, caregiver or random."""
    world, eyes = World(ArmSpec(), seed), Eyes(head)
    world.rng = np.random.default_rng(seed)
    rng = np.random.default_rng(seed + 1)
    counts = dict.fromkeys(STAGES, 0)
    decisions = []
    for _ in range(trials):
        world.randomize(holding_rate=0.0)
        world.closed = False
        eyes.reset()
        if brain is not None:
            brain.reset()
        passed: set[str] = set()
        for d in range(cap):
            tip = world.tip()
            if not world.holding and np.linalg.norm(tip - caregiver.hover_point(world)) <= 0.025:
                passed.add("reached")
            if world.holding:
                if tip[2] >= LIFT - 0.03:
                    passed.add("lifted")
                ordered = world.ordered_bin()
                if "lifted" in passed and ordered is not None and np.hypot(tip[0] - ordered[0], tip[1] - ordered[1]) <= 0.03:
                    passed.add("carried")
            if policy == "caregiver":
                want = job_labels(world, eyes, rule, plan)
                steps, close = steps_of(want[POOLS]), want[GRIP]
            elif policy == "random":
                steps, close = rng.integers(-2, 3, size=4).astype(float), int(rng.random() < 0.5)
            else:
                x = eyes.inputs(world)[None]
                if dark:
                    x = x.copy()
                    x[:, : eyes.spec.retina] = 0.0
                answer = answer_of(brain, x)
                if answer is None:
                    steps, close = np.zeros(4), int(world.closed)
                else:
                    steps, close = steps_of(answer[POOLS]), int(answer[GRIP])
            event = world.decide(steps, close)["event"] or ""
            if event == "grasped":
                passed.update(("reached", "grasped"))  # a grasp is a reach, though the lowering may have begun short of the hover point
            elif event == "dropped":
                passed.add("dropped")
            elif event.startswith("placed"):
                passed.add("right" if event.endswith("right") else "wrong")
                if event.endswith("right"):
                    decisions.append(d + 1)
                break
        for stage in passed:
            counts[stage] += 1
    out = {stage: round(counts[stage] / trials, 3) for stage in STAGES}
    out.update(trials=trials, success=out["right"], cap=cap,
               decisions_median=float(np.median(decisions)) if decisions else None)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--brain", default=None, help="a brain; without one, the caregiver and random controls")
    p.add_argument("--run", default=None, help="a run folder whose run.json names the head (default: the brain's)")
    p.add_argument("--trials", type=int, default=40)
    p.add_argument("--cap", type=int, default=80)
    p.add_argument("--seed", type=int, default=60_001)
    p.add_argument("--teacher", choices=("gradient", "joint"), default="gradient")
    a = p.parse_args()
    folder = Path(a.run) if a.run else Path(a.brain).parent
    head = head_of(json.loads((folder / "run.json").read_text()))
    out = {
        "caregiver": job_assay(None, head, a.trials, a.seed, a.cap, policy="caregiver", rule=a.teacher),
        "random": job_assay(None, head, a.trials, a.seed, a.cap, policy="random"),
    }
    if a.brain:
        brain = Brain.load(a.brain)
        out["brain"] = job_assay(brain, head, a.trials, a.seed, a.cap)
        out["brain_dark"] = job_assay(brain, head, a.trials, a.seed, a.cap, dark=True)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
