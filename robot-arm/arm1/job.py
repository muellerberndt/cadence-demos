"""The job assay on true state, with the repaired reach criterion and motion gates.

One fresh scene per trial from a random posture with the gripper open, the policy alone for up
to ``cap`` decisions. Stages a trial passed:

- ``reached``: the fingertip within 2.5 cm of the hover point before a grasp, **or a grasp**
  (the smooth plan starts lowering 4 cm out and never passes the hover point);
- ``reached_hover``: the old criterion alone, the hover point within 2.5 cm, for comparison;
- ``grasped``, ``lifted`` (holding, within 3 cm of the carrying height), ``carried`` (holding,
  lifted, within 3 cm of the ordered bin in the plane), ``right``, ``wrong``, ``dropped``.

Motion gates per trial, read from every physics frame (60 Hz) against the trial's waypoints,
the grasp point while the hand is empty and the release point while it holds:

- ``oscillation_hz``: sign changes of the fingertip's velocity components (dead band 1 mm/s)
  in frames within ``WITHIN`` (1 cm) of the waypoint, per second spent within it;
  ``oscillation_near_hz`` the same within ``NEAR`` (3 cm), the band where the plan acts (a
  grasp needs 3 cm in the plane, a release 2 cm), so the teacher has a reading there too;
- ``overshoot_cm``: after the hand first comes within 3 cm, how far it moves away again in the
  next half second, the largest over the waypoints;
- ``settling_s``: from the first frame within 3 cm to the arrival, the first frame within 1 cm or
  the act that ends the phase (the grasp, release or drop), whichever comes first; a phase that
  runs out with the hand near the waypoint and no act counts the time to the end and ``unsettled``;
- ``effort_nms``: the actuator's torque integrated over the trial, sum over joints of
  |stiffness (rest - q) - damping dq| dt (the reflex's gravity share excluded);
- ``command_rad``: the rest angles' total commanded movement; ``path_cm``: the fingertip's path.

``inspect`` reads every gate against the teacher's value on the same trials.
"""

from __future__ import annotations

import itertools

import numpy as np

from arm import caregiver
from arm.caregiver import LIFT
from arm.world import ArmSpec, World

from . import teacher
from .actions import HOLD, execute, grip_index, hold_answer, motion, slots_of
from .senses import blind, observe

STAGES = ("reached", "reached_hover", "grasped", "lifted", "carried", "right", "wrong", "dropped")
GATES = ("oscillation_hz", "oscillation_near_hz", "overshoot_cm", "settling_s", "effort_nms", "command_rad", "path_cm")
WITHIN = 0.01
NEAR = 0.03
SETTLED_FRAMES = 12  # 0.2 s at 60 Hz
OVERSHOOT_FRAMES = 30  # 0.5 s
DEAD_BAND = 0.001  # m/s


def waypoint(world: World) -> np.ndarray | None:
    if not world.holding:
        return caregiver.grasp_point(world)
    ordered = world.ordered_bin()
    return None if ordered is None else np.array([ordered[0], ordered[1], LIFT])


class GateRecorder:
    """Frame-level record of one trial, summarized into the motion gates."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.tips: list[np.ndarray] = []
        self.torque: list[float] = []
        self.holding: list[bool] = []
        self.waypoints: list[np.ndarray | None] = []
        self.command = 0.0

    def frame(self, _index: int) -> None:
        w, s = self.world, self.world.spec
        tau = s.stiffness * (w.rest - w.q) - s.damping * w.dq
        self.tips.append(w.tip())
        self.torque.append(float(np.abs(tau).sum()))
        self.holding.append(bool(w.holding))
        self.waypoints.append(waypoint(w))

    def decision(self, before: np.ndarray, after: np.ndarray) -> None:
        self.command += float(np.abs(after - before).sum())

    def summary(self) -> dict:
        dt = self.world.spec.dt
        n = len(self.tips)
        if n < 2:
            return dict.fromkeys(GATES, None) | {"unsettled": 0, "seconds": n * dt}
        tips = np.array(self.tips)
        holding = np.array(self.holding)
        bounds = [0] + [i for i in range(1, n) if holding[i] != holding[i - 1]] + [n]
        changes = {WITHIN: 0, NEAR: 0}
        band_time = {WITHIN: 0.0, NEAR: 0.0}
        overshoots, settlings, unsettled = [], [], 0
        for a, b in itertools.pairwise(bounds):
            wp = self.waypoints[a]
            if wp is None or b - a < 2:
                continue
            dist = np.linalg.norm(tips[a:b] - wp, axis=1)
            v = np.diff(tips[a:b], axis=0) / dt
            sign = np.where(np.abs(v) < DEAD_BAND, 0.0, np.sign(v))
            flips = (sign[1:] * sign[:-1]) < 0  # (m - 2, 3): a reversal between frames t and t + 1
            for band in (WITHIN, NEAR):
                inside = dist <= band
                if inside.any():
                    both = inside[1:-1] & inside[2:]
                    changes[band] += int((flips & both[:, None]).sum())
                    band_time[band] += float(inside.sum()) * dt
            near = dist <= NEAR
            if not near.any():
                continue
            first = int(np.argmax(near))
            window = dist[first:first + OVERSHOOT_FRAMES]
            overshoots.append(float(window.max() - dist[first]) * 100)
            within = dist <= WITHIN
            acted = b < n  # the phase ended with the act that flips ``holding`` (a grasp, a release, a drop)
            if within.any():
                settlings.append((int(np.argmax(within)) - first) * dt)
            elif acted:
                settlings.append((len(dist) - first) * dt)
            else:  # the trial ran out with the hand near the waypoint and never acting
                settlings.append((len(dist) - first) * dt)
                unsettled += 1
        return {
            "oscillation_hz": changes[WITHIN] / band_time[WITHIN] if band_time[WITHIN] else None,
            "oscillation_near_hz": changes[NEAR] / band_time[NEAR] if band_time[NEAR] else None,
            "overshoot_cm": max(overshoots) if overshoots else None,
            "settling_s": float(np.mean(settlings)) if settlings else None,
            "unsettled": unsettled,
            "effort_nms": float(np.sum(self.torque)) * dt,
            "command_rad": self.command,
            "path_cm": float(np.linalg.norm(np.diff(tips, axis=0), axis=1).sum()) * 100,
            "seconds": n * dt,
        }


class Policy:
    """A decision from the world's state: slot indices, or None for a refused decision."""

    def __init__(self, pools: str) -> None:
        self.pools = pools
        self.refused = 0

    def reset(self) -> None:
        pass

    def act(self, world: World) -> np.ndarray | None:
        raise NotImplementedError


class TeacherPolicy(Policy):
    def act(self, world: World) -> np.ndarray:
        return np.asarray(teacher.labels(world, self.pools), dtype=np.int64)


class RandomPolicy(Policy):
    def __init__(self, pools: str, seed: int) -> None:
        super().__init__(pools)
        self.rng = np.random.default_rng(seed)

    def act(self, world: World) -> np.ndarray:
        sizes = slots_of(self.pools)
        return np.array([self.rng.integers(0, s) for s in sizes], dtype=np.int64)


class BrainPolicy(Policy):
    """A frozen brain, one row; ``blind`` zeroes the object terms (the blind twin)."""

    def __init__(self, brain, pools: str, blind: bool = False) -> None:
        super().__init__(pools)
        self.brain = brain
        self.blind = blind
        self.sweeps: list[int] = []
        self.activation: list[float] = []

    def reset(self) -> None:
        self.brain.reset()

    def act(self, world: World) -> np.ndarray | None:
        x = observe(world)
        if self.blind:
            x = blind(x)
        try:
            answer = np.asarray(self.brain.act(x[None], greedy=True))[0]
        except RuntimeError:
            self.refused += 1
            return None
        self.sweeps.append(int((self.brain.last_settlement or {}).get("steps", 0)))
        state = self.brain.basal_ganglia.state
        if state is not None:
            motor = np.atleast_2d(state.activation)[0][np.asarray(self.brain.motor_index)]
            self.activation.append(float(np.max(motor)))
        return answer.astype(np.int64)

    def readings(self) -> dict:
        return {"sweeps": float(np.mean(self.sweeps)) if self.sweeps else None,
                "activation_max": float(np.max(self.activation)) if self.activation else None}


class MLPPolicy(Policy):
    def __init__(self, model, pools: str, blind: bool = False) -> None:
        super().__init__(pools)
        self.model = model
        self.blind = blind

    def act(self, world: World) -> np.ndarray:
        from . import mlp

        x = observe(world)
        if self.blind:
            x = blind(x)
        return mlp.act(self.model, x[None])[0]


def prepare(world: World) -> None:
    """A fresh job: a random posture, a fresh block and order, the gripper open."""
    world.randomize(holding_rate=0.0)
    world.closed = False


def run_trial(world: World, policy: Policy, pools: str, cap: int, observer=None) -> dict:
    """One job from a prepared world. ``observer(decision, world, answer, event)`` is called
    before the first decision (with None, "") and after each one."""
    passed: set[str] = set()
    decisions = None
    holds = 0
    recorder = GateRecorder(world)
    if observer is not None:
        observer(0, world, None, "")
    d = 0
    for d in range(cap):
        tip = world.tip()
        if not world.holding and np.linalg.norm(tip - caregiver.hover_point(world)) <= 0.025:
            passed.update(("reached", "reached_hover"))
        if world.holding:
            if tip[2] >= LIFT - 0.03:
                passed.add("lifted")
            ordered = world.ordered_bin()
            if "lifted" in passed and ordered is not None and np.hypot(tip[0] - ordered[0], tip[1] - ordered[1]) <= 0.03:
                passed.add("carried")
        answer = policy.act(world)
        if answer is None:
            answer = hold_answer(pools, world.closed)
        holds += int(np.all(answer[motion(pools)] == HOLD))
        before = world.rest.copy()
        event = execute(world, answer, pools, recorder.frame)["event"] or ""
        recorder.decision(before, world.rest)
        if event == "grasped":
            passed.update(("reached", "grasped"))
        elif event == "dropped":
            passed.add("dropped")
        elif event.startswith("placed"):
            passed.add("right" if event.endswith("right") else "wrong")
            if event.endswith("right"):
                decisions = d + 1
        if observer is not None:
            observer(d + 1, world, answer, event)
        if event.startswith("placed"):
            break
    return {"passed": passed, "decisions": decisions, "steps": d + 1, "holds": holds, "gates": recorder.summary()}


def job_assay(policy: Policy, pools: str, trials: int, seed: int, cap: int = 80) -> dict:
    """Stage rates, decisions and gates over ``trials`` fresh scenes drawn from ``seed``."""
    world = World(ArmSpec(), seed)
    world.rng = np.random.default_rng(seed)
    counts = dict.fromkeys(STAGES, 0)
    decisions, gates, holds, steps, unsettled = [], {k: [] for k in GATES}, 0, 0, 0
    for _ in range(trials):
        prepare(world)
        policy.reset()
        r = run_trial(world, policy, pools, cap)
        for stage in r["passed"]:
            counts[stage] += 1
        if r["decisions"] is not None:
            decisions.append(r["decisions"])
        holds += r["holds"]
        steps += r["steps"]
        unsettled += r["gates"]["unsettled"]
        for k in GATES:
            if r["gates"][k] is not None:
                gates[k].append(r["gates"][k])
    out = {stage: round(counts[stage] / trials, 3) for stage in STAGES}
    out.update(trials=trials, success=out["right"], cap=cap,
               decisions_median=float(np.median(decisions)) if decisions else None,
               holds=round(holds / max(steps, 1), 3), decisions_total=steps, refused=policy.refused,
               gates={k: (round(float(np.mean(v)), 4) if v else None) for k, v in gates.items()} | {"unsettled": unsettled})
    if isinstance(policy, BrainPolicy):
        out.update(policy.readings())
    return out


def commands_at_starts(policy: Policy, pools: str, starts: int = 40, seed: int = 90_001) -> dict:
    """The policy's first decision at ``starts`` fixed fresh scenes: how many distinct commands
    it gives (a collapsed policy gives one or two), the share that hold, and for a brain the
    largest motor activation and the sweeps per settle."""
    world = World(ArmSpec(), seed)
    world.rng = np.random.default_rng(seed)
    commands = []
    for _ in range(starts):
        prepare(world)
        policy.reset()
        answer = policy.act(world)
        commands.append(tuple(int(v) for v in (hold_answer(pools, world.closed) if answer is None else answer)))
    arr = np.array(commands)
    out = {"starts": starts, "distinct": len(set(commands)),
           "holds": round(float(np.mean(np.all(arr[:, motion(pools)] == HOLD, axis=1))), 3),
           "closed": round(float(np.mean(arr[:, grip_index(pools)] == 1)), 3),
           "most_common": max(set(commands), key=commands.count)}
    if isinstance(policy, BrainPolicy):
        out.update(policy.readings())
    return out
