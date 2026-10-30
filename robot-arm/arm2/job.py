"""The job assay under contact physics, with stages from contacts and motion gates.

One fresh scene per trial (a random reachable posture, a fresh block of random size, mass and
friction from the physics set, the gripper open), the policy alone for up to ``cap`` decisions.
Stages: ``reached`` (tcp within 2.5 cm of the hover point before a grasp, or a grasp),
``reached_hover`` (the hover point alone), ``grasped`` (both fingers in contact with the block,
gripper closed), ``lifted`` (holding, the block's bottom 5 cm above the table), ``carried``
(lifted, the block within 3 cm of the ordered bin in the plane), ``right`` / ``wrong`` (the
released block at rest in a bin), ``dropped`` (a release or a slip that comes to rest outside
the bins).

Gates per trial at 100 Hz against the trial's waypoints (the block centre while the hand is
empty, the release point while it holds): ``oscillation_hz`` (velocity-component sign changes
per second within 1 cm; ``oscillation_near_hz`` within 3 cm), ``overshoot_cm``, ``settling_s``
(3 cm to the arrival or the act), ``effort_nms`` (the seven joint servos' |force| integrated,
``data.actuator_force``), ``effort_cmd`` (sum |ctrl - q| integrated, rad s), ``jerk`` (mean
|d^3 tcp / dt^3|, m/s^3), ``command_rad``, ``path_cm``. ``inspect`` reads every gate against the
teacher on the same trials, nominal and held-out physics apart.
"""

from __future__ import annotations

import itertools

import numpy as np

from arm1.job import DEAD_BAND, NEAR, OVERSHOOT_FRAMES, WITHIN

from . import teacher
from .actions import HOLD, execute, grip_index, hold_answer, motion, slots_of
from .scene import LIFT, RECORD_EVERY, PandaWorld
from .senses import blind, observe

STAGES = ("reached", "reached_hover", "grasped", "lifted", "carried", "right", "wrong", "dropped")
GATES = ("oscillation_hz", "oscillation_near_hz", "overshoot_cm", "settling_s", "effort_nms", "effort_cmd", "jerk",
         "command_rad", "path_cm")
SAMPLE_DT = 0.002 * RECORD_EVERY  # 100 Hz
OVERSHOOT_SAMPLES = OVERSHOOT_FRAMES * 100 // 60


def waypoint(world: PandaWorld) -> np.ndarray | None:
    return world.release_point() if world.holding else world.grasp_point()


class GateRecorder:
    def __init__(self, world: PandaWorld) -> None:
        self.world = world
        self.tips: list[np.ndarray] = []
        self.force: list[float] = []
        self.cmd: list[float] = []
        self.holding: list[bool] = []
        self.waypoints: list[np.ndarray | None] = []
        self.command = 0.0

    def sample(self, _index: int) -> None:
        w = self.world
        d = w.data
        self.tips.append(w.tip())
        self.force.append(float(np.abs(d.actuator_force[:7]).sum()))
        self.cmd.append(float(np.abs(d.ctrl[:7] - d.qpos[:7]).sum()))
        self.holding.append(bool(w.holding))
        self.waypoints.append(waypoint(w))

    def decision(self, before: np.ndarray, after: np.ndarray) -> None:
        self.command += float(np.abs(after - before).sum())

    def summary(self) -> dict:
        dt = SAMPLE_DT
        n = min(len(self.tips), len(self.holding), len(self.waypoints), len(self.force), len(self.cmd))  # a snapshot: the demo reads while sampling
        if n < 4:
            return dict.fromkeys(GATES, None) | {"unsettled": 0, "seconds": n * dt}
        tips = np.array(self.tips[:n])
        holding = np.array(self.holding[:n])
        force, cmd, waypoints = self.force[:n], self.cmd[:n], self.waypoints[:n]
        bounds = [0] + [i for i in range(1, n) if holding[i] != holding[i - 1]] + [n]
        changes = {WITHIN: 0, NEAR: 0}
        band_time = {WITHIN: 0.0, NEAR: 0.0}
        overshoots, settlings, unsettled = [], [], 0
        for a, b in itertools.pairwise(bounds):
            wp = waypoints[a]
            if wp is None or b - a < 3:
                continue
            dist = np.linalg.norm(tips[a:b] - wp, axis=1)
            v = np.diff(tips[a:b], axis=0) / dt
            sign = np.where(np.abs(v) < DEAD_BAND, 0.0, np.sign(v))
            flips = (sign[1:] * sign[:-1]) < 0
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
            window = dist[first:first + OVERSHOOT_SAMPLES]
            overshoots.append(float(window.max() - dist[first]) * 100)
            within = dist <= WITHIN
            acted = b < n
            if within.any():
                settlings.append((int(np.argmax(within)) - first) * dt)
            else:
                settlings.append((len(dist) - first) * dt)
                if not acted:
                    unsettled += 1
        velocity = np.diff(tips, axis=0) / dt
        jerk = np.diff(velocity, n=2, axis=0) / dt / dt
        return {
            "oscillation_hz": changes[WITHIN] / band_time[WITHIN] if band_time[WITHIN] else None,
            "oscillation_near_hz": changes[NEAR] / band_time[NEAR] if band_time[NEAR] else None,
            "overshoot_cm": max(overshoots) if overshoots else None,
            "settling_s": float(np.mean(settlings)) if settlings else None,
            "unsettled": unsettled,
            "effort_nms": float(np.sum(force)) * dt,
            "effort_cmd": float(np.sum(cmd)) * dt,
            "jerk": float(np.mean(np.linalg.norm(jerk, axis=1))),
            "command_rad": self.command,
            "path_cm": float(np.linalg.norm(np.diff(tips, axis=0), axis=1).sum()) * 100,
            "seconds": n * dt,
        }


class Policy:
    def __init__(self, pools: str) -> None:
        self.pools = pools
        self.refused = 0

    def reset(self) -> None:
        pass

    def act(self, world: PandaWorld) -> np.ndarray | None:
        raise NotImplementedError


class TeacherPolicy(Policy):
    def __init__(self, pools: str, recover: bool = False) -> None:
        super().__init__(pools)
        self.recover = recover

    def act(self, world: PandaWorld) -> np.ndarray:
        return np.asarray(teacher.labels(world, self.pools, self.recover), dtype=np.int64)


class RandomPolicy(Policy):
    def __init__(self, pools: str, seed: int) -> None:
        super().__init__(pools)
        self.rng = np.random.default_rng(seed)

    def act(self, world: PandaWorld) -> np.ndarray:
        return np.array([self.rng.integers(0, s) for s in slots_of(self.pools)], dtype=np.int64)


class BrainPolicy(Policy):
    def __init__(self, brain, pools: str, blind: bool = False, velocity: bool = True, slip: bool = False) -> None:
        super().__init__(pools)
        self.brain, self.blind, self.velocity, self.slip = brain, blind, velocity, slip
        self.sweeps: list[int] = []
        self.activation: list[float] = []

    def reset(self) -> None:
        self.brain.reset()

    def act(self, world: PandaWorld) -> np.ndarray | None:
        x = observe(world, self.pools, self.velocity, self.slip)
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
            self.activation.append(float(np.max(np.atleast_2d(state.activation)[0][np.asarray(self.brain.motor_index)])))
        return answer.astype(np.int64)

    def readings(self) -> dict:
        return {"sweeps": float(np.mean(self.sweeps)) if self.sweeps else None,
                "activation_max": float(np.max(self.activation)) if self.activation else None}


class MLPPolicy(Policy):
    def __init__(self, model, pools: str, blind: bool = False, velocity: bool = True, slip: bool = False) -> None:
        super().__init__(pools)
        self.model, self.blind, self.velocity, self.slip = model, blind, velocity, slip

    def act(self, world: PandaWorld) -> np.ndarray:
        from arm1 import mlp

        x = observe(world, self.pools, self.velocity, self.slip)
        if self.blind:
            x = blind(x)
        return mlp.act(self.model, x[None])[0]


def prepare(world: PandaWorld) -> None:
    world.randomize()
    world.last_command = None


def run_trial(world: PandaWorld, policy: Policy, pools: str, cap: int, observer=None) -> dict:
    passed: set[str] = set()
    decisions = None
    holds = 0
    recorder = GateRecorder(world)
    if observer is not None:
        observer(0, world, None, "")
    d = 0
    for d in range(cap):
        tip = world.tip()
        if not world.holding and np.linalg.norm(tip - world.hover_point()) <= 0.025:
            passed.update(("reached", "reached_hover"))
        if world.holding:
            if world.block_pos()[2] - world.half >= 0.05:
                passed.add("lifted")
            ordered = world.ordered_bin()
            if "lifted" in passed and ordered is not None and np.hypot(tip[0] - ordered[0], tip[1] - ordered[1]) <= 0.03:
                passed.add("carried")
        answer = policy.act(world)
        if answer is None:
            answer = hold_answer(pools, world.closed)
        holds += int(np.all(answer[motion(pools)] == HOLD))
        before = world.rest()
        event = execute(world, answer, pools, recorder.sample)["event"] or ""
        recorder.decision(before, world.rest())
        if event == "grasped":
            passed.update(("reached", "grasped"))
        elif event in ("dropped", "slipped"):
            passed.add("dropped")
        elif event.startswith("placed"):
            passed.add("right" if event.endswith("right") else "wrong")
            if event.endswith("right"):
                decisions = d + 1
        if observer is not None:
            observer(d + 1, world, answer, event)
        if event.startswith("placed"):
            break
    return {"passed": passed, "decisions": decisions, "steps": d + 1, "holds": holds, "gates": recorder.summary(),
            "grip_index": grip_index(pools), "lift": LIFT}


def job_assay(policy: Policy, pools: str, trials: int, seed: int, cap: int = 80, physics: str = "nominal") -> dict:
    world = PandaWorld(seed, physics)
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
    out.update(trials=trials, success=out["right"], cap=cap, physics=physics,
               decisions_median=float(np.median(decisions)) if decisions else None,
               holds=round(holds / max(steps, 1), 3), decisions_total=steps, refused=policy.refused,
               gates={k: (round(float(np.mean(v)), 4) if v else None) for k, v in gates.items()} | {"unsettled": unsettled})
    if isinstance(policy, BrainPolicy):
        out.update(policy.readings())
    return out


def commands_at_starts(policy: Policy, pools: str, starts: int = 40, seed: int = 90_001, physics: str = "nominal") -> dict:
    world = PandaWorld(seed, physics)
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
