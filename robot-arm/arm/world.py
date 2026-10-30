"""The cell: a four-joint arm with a gripper over a table, one block, two bins and two order lamps.

Units are metres, seconds and radians. x points to the right, y forward away from the base, z
up; the table top is z = 0. Every joint is a reflex joint: the motor pools set its rest angle
and a spring-damper drives the joint there. The reflex compensates the arm's own weight and
nothing else, so a load hung on the hand sags the arm. The brain never sees the physics. It
sees the retinas, the spindles and the skin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

TABLE_X = (-0.35, 0.35)
TABLE_Y = (0.10, 0.50)
BLOCK = 0.05  # cube side
BIN_SIDE = 0.13
BIN_HOME = {"A": (-0.20, 0.38), "B": (0.20, 0.38)}
LAMP = {"A": (-0.26, 0.54, 0.06), "B": (0.26, 0.54, 0.06)}
SPAWN_X = (-0.26, 0.26)
SPAWN_Y = (0.16, 0.32)
HOVER = 0.07  # the caregiver's hover height above the block top before lowering
LEVELS = (-2, -1, 0, 1, 2)  # a motor pool's commands: two steps down to two steps up, in units of the step
HOLD = 2  # the index of the level that holds
STEPS = LEVELS
JOINTS = ("yaw", "shoulder", "elbow", "wrist")


def steps_of(indices) -> np.ndarray:
    """Pool indices (one per joint) to steps in units of the step."""
    return np.array([LEVELS[int(i)] for i in indices], dtype=float)


def index_of(step: float) -> int:
    return LEVELS.index(int(round(step)))
SPINDLE_BINS = 7
BODY_SENSES = 4 * SPINDLE_BINS + 2
POSITION_BINS = 12
ORDERS = ("none", "A", "B")


@dataclass(frozen=True)
class ArmSpec:
    """Every designed constant of the body is a gene; these are the founder values."""

    base_height: float = 0.10
    links: tuple[float, float, float] = (0.26, 0.22, 0.08)
    masses: tuple[float, float, float] = (1.0, 0.6, 0.3)
    low: tuple[float, float, float, float] = (-1.3, 0.17, -2.4, -2.1)
    high: tuple[float, float, float, float] = (1.3, 1.92, -0.17, 0.5)
    home: tuple[float, float, float, float] = (0.0, 1.2, -1.6, -1.0)
    stiffness: float = 25.0  # N m per radian at every joint
    damping: float = 3.2  # N m s per radian
    inertia: float = 0.10  # kg m^2
    gravity: float = 9.81
    compensate: bool = True  # the reflex carries the arm's own links, not a load
    dt: float = 1.0 / 60.0
    frames_per_decision: int = 12
    step: float = 0.045  # radians of one fine motor command on a rest angle; a coarse command is two
    grasp_reach: float = 0.03  # the fingertip within this of the block centre, in the plane
    grasp_above: float = 0.025  # and no higher than this above the block top
    grasp_below: float = 0.01  # nor lower than this below the block top
    reward_placed: float = 1.0
    reward_wrong_bin: float = -0.25
    reward_dropped: float = -0.1


def forward(spec: ArmSpec, q: np.ndarray) -> np.ndarray:
    """Shoulder, elbow, wrist and fingertip positions (4, 3) for joint angles ``q`` (4,)."""
    yaw, a1, a2, a3 = (float(v) for v in q)
    l1, l2, l3 = spec.links
    t1, t2, t3 = a1, a1 + a2, a1 + a2 + a3
    r0, z0 = 0.0, spec.base_height
    r1, z1 = r0 + l1 * np.cos(t1), z0 + l1 * np.sin(t1)
    r2, z2 = r1 + l2 * np.cos(t2), z1 + l2 * np.sin(t2)
    r3, z3 = r2 + l3 * np.cos(t3), z2 + l3 * np.sin(t3)
    s, c = np.sin(yaw), np.cos(yaw)
    return np.array([[-r * s, r * c, z] for r, z in ((r0, z0), (r1, z1), (r2, z2), (r3, z3))])


def radial(points: np.ndarray) -> np.ndarray:
    """Distance from the base axis in the arm's plane, for points from ``forward``."""
    return np.hypot(points[:, 0], points[:, 1])


def gravity_torque(spec: ArmSpec, q: np.ndarray, load: float) -> np.ndarray:
    """Torque gravity puts on each joint; the reflex cancels the links' share when compensating."""
    points = forward(spec, q)
    r = radial(points)
    com = ((r[0] + r[1]) / 2, (r[1] + r[2]) / 2, (r[2] + r[3]) / 2)
    tau = np.zeros(4)
    for j in (1, 2, 3):
        pivot = r[j - 1]
        if not spec.compensate:
            tau[j] -= spec.gravity * sum(spec.masses[k] * (com[k] - pivot) for k in range(j - 1, 3))
        tau[j] -= spec.gravity * load * (r[3] - pivot)
    return tau


def bin_of(value: float, span: tuple[float, float], bins: int = POSITION_BINS) -> int:
    width = (span[1] - span[0]) / bins
    return int(np.clip(np.floor((value - span[0]) / width), 0, bins - 1))


def in_bin(x: float, y: float, bins: dict[str, tuple[float, float]]) -> str | None:
    for name, (bx, by) in bins.items():
        if abs(x - bx) <= BIN_SIDE / 2 and abs(y - by) <= BIN_SIDE / 2:
            return name
    return None


class World:
    """One cell with one arm, one block and two bins; a continuing life of decisions."""

    def __init__(self, spec: ArmSpec = ArmSpec(), seed: int = 0) -> None:
        self.spec = spec
        self.rng = np.random.default_rng(seed)
        self.low, self.high = np.array(spec.low), np.array(spec.high)
        self.bins = {k: tuple(v) for k, v in BIN_HOME.items()}
        self.load = 0.0  # kg hung on the hand
        self.wear = 0.0  # metres the grasp window has shrunk from above
        self.t = 0.0
        self.decisions = 0
        self.placed = 0
        self.wrong = 0
        self.dropped = 0
        self.home()
        self.spawn_block()
        self.order = 1

    # --- state -------------------------------------------------------------------------------
    def home(self) -> None:
        self.q = np.array(self.spec.home, dtype=float)
        self.rest = self.q.copy()
        self.dq = np.zeros(4)
        self.closed = False
        self.holding = False

    def spawn_block(self) -> None:
        for _ in range(100):
            x = self.rng.uniform(*SPAWN_X)
            y = self.rng.uniform(*SPAWN_Y)
            if in_bin(x, y, self.bins) is None:
                break
        self.block = np.array([x, y, BLOCK / 2])

    def new_order(self) -> None:
        self.order = int(self.rng.integers(1, 3))

    def points(self) -> np.ndarray:
        return forward(self.spec, self.q)

    def tip(self) -> np.ndarray:
        return self.points()[3]

    def block_top(self) -> float:
        return float(self.block[2] + BLOCK / 2)

    def ordered_bin(self) -> tuple[float, float] | None:
        return None if self.order == 0 else self.bins[ORDERS[self.order]]

    # --- physics -----------------------------------------------------------------------------
    def frame(self) -> None:
        s = self.spec
        tau = s.stiffness * (self.rest - self.q) - s.damping * self.dq + gravity_torque(s, self.q, self.load)
        dq = self.dq + tau / s.inertia * s.dt
        q = self.q + dq * s.dt
        hit = (q < self.low) | (q > self.high)
        q = np.clip(q, self.low, self.high)
        dq[hit] = 0.0
        if forward(s, q)[3][2] < 0.0:  # the fingertip presses on the table
            dq[:] = 0.0
            q = self.q
        self.q, self.dq = q, dq
        if self.holding:
            self.block = self.tip() - np.array([0.0, 0.0, BLOCK / 2])
        self.t += s.dt

    def decide(self, steps: Any, close: int) -> dict[str, Any]:
        """One decision: joint steps in {-1, 0, 1} per joint and the gripper (1 closed, 0 open),
        then the frames of one decision. Returns the outcome of this decision."""
        s = self.spec
        steps = np.asarray(steps, dtype=float)
        if steps.shape != (4,) or (np.abs(steps) > 2).any():
            raise ValueError("steps are four values in -2..2")
        self.rest = np.clip(self.rest + steps * s.step, self.low, self.high)
        outcome: dict[str, Any] = {"reward": 0.0, "event": None, "done": False}
        if close and not self.closed:
            self.closed = True
            self._grasp(outcome)
        elif not close and self.closed:
            self.closed = False
            self._release(outcome)
        for _ in range(s.frames_per_decision):
            self.frame()
        self.decisions += 1
        return outcome

    def decide_frames(self, steps: Any, close: int, hook=None) -> dict[str, Any]:
        """``decide`` with a callback after each frame (``hook(frame_index)``), for waits."""
        if hook is None:
            return self.decide(steps, close)
        s = self.spec
        saved = s.frames_per_decision
        object.__setattr__(self, "spec", s)
        steps = np.asarray(steps, dtype=float)
        self.rest = np.clip(self.rest + steps * s.step, self.low, self.high)
        outcome: dict[str, Any] = {"reward": 0.0, "event": None, "done": False}
        if close and not self.closed:
            self.closed = True
            self._grasp(outcome)
        elif not close and self.closed:
            self.closed = False
            self._release(outcome)
        for i in range(saved):
            self.frame()
            hook(i + 1)
        self.decisions += 1
        return outcome

    def _grasp(self, outcome: dict[str, Any]) -> None:
        tip = self.tip()
        if self.holding:
            return
        near = np.hypot(tip[0] - self.block[0], tip[1] - self.block[1]) <= self.spec.grasp_reach
        top = self.block_top()
        window = top - self.spec.grasp_below <= tip[2] <= top + self.spec.grasp_above - self.wear
        if near and window:
            self.holding = True
            outcome["event"] = "grasped"
        else:
            outcome["event"] = "missed"

    def _release(self, outcome: dict[str, Any]) -> None:
        if not self.holding:
            return
        self.holding = False
        x, y = float(self.block[0]), float(self.block[1])
        name = in_bin(x, y, self.bins)
        if name is not None:
            right = ORDERS[self.order] == name
            outcome["reward"] = self.spec.reward_placed if right else self.spec.reward_wrong_bin
            outcome["event"] = f"placed:{name}:{'right' if right else 'wrong'}"
            outcome["done"] = True
            self.placed += int(right)
            self.wrong += int(not right)
            self.spawn_block()
            self.new_order()
        else:
            self.block = np.array([x, y, BLOCK / 2])
            outcome["reward"] = self.spec.reward_dropped
            outcome["event"] = "dropped"
            self.dropped += 1

    # --- senses and labels -------------------------------------------------------------------
    def body(self) -> np.ndarray:
        """Spindles as a population code per joint, then the skin: gripper closed, holding."""
        code = []
        for j in range(4):
            centres = np.linspace(self.low[j], self.high[j], SPINDLE_BINS)
            sigma = (self.high[j] - self.low[j]) / (SPINDLE_BINS - 1) * 0.75
            code.append(np.exp(-0.5 * ((self.q[j] - centres) / sigma) ** 2))
        return np.concatenate(code + [[float(self.closed)], [float(self.holding)]])

    def labels(self) -> list[int]:
        """What the eyes are taught to read: block x, y; hand x, y; held; the order."""
        tip = self.tip()
        return [
            bin_of(float(self.block[0]), TABLE_X), bin_of(float(self.block[1]), TABLE_Y),
            bin_of(float(tip[0]), TABLE_X), bin_of(float(tip[1]), TABLE_Y),
            int(self.holding), int(self.order),
        ]

    # --- the visitor's changes ---------------------------------------------------------------
    def move_block(self, x: float, y: float) -> None:
        if self.holding:
            raise ValueError("the block is in the hand")
        self.block = np.array([x, y, BLOCK / 2])

    def move_bin(self, name: str, x: float, y: float) -> None:
        self.bins[name] = (x, y)

    def set_load(self, kg: float) -> None:
        self.load = float(kg)

    def set_wear(self, metres: float) -> None:
        self.wear = float(metres)

    # --- scenes for the nursery --------------------------------------------------------------
    def randomize(self, holding_rate: float = 0.3) -> None:
        """A random posture over the table, a random block, order and gripper state."""
        for _ in range(200):
            q = self.rng.uniform(self.low, self.high)
            tip = forward(self.spec, q)[3]
            if tip[2] > 0.03 and TABLE_X[0] < tip[0] < TABLE_X[1] and TABLE_Y[0] < tip[1] < TABLE_Y[1]:
                break
        self.q, self.rest, self.dq = q, q.copy(), np.zeros(4)
        self.spawn_block()
        self.new_order()
        self.closed = bool(self.rng.random() < 0.5)
        self.holding = bool(self.closed and self.rng.random() < holding_rate)
        if self.holding:
            self.block = self.tip() - np.array([0.0, 0.0, BLOCK / 2])

    def snapshot(self) -> dict[str, Any]:
        return {
            "q": self.q.tolist(), "rest": self.rest.tolist(), "dq": self.dq.tolist(),
            "closed": self.closed, "holding": self.holding, "block": self.block.tolist(),
            "bins": {k: list(v) for k, v in self.bins.items()}, "order": self.order,
            "load": self.load, "wear": self.wear, "t": self.t, "decisions": self.decisions,
            "placed": self.placed, "wrong": self.wrong, "dropped": self.dropped,
        }

    def restore(self, s: dict[str, Any]) -> None:
        self.q, self.rest, self.dq = (np.array(s[k], dtype=float) for k in ("q", "rest", "dq"))
        self.closed, self.holding = bool(s["closed"]), bool(s["holding"])
        self.block = np.array(s["block"], dtype=float)
        self.bins = {k: tuple(v) for k, v in s["bins"].items()}
        self.order, self.load, self.wear, self.t = int(s["order"]), float(s["load"]), float(s["wear"]), float(s["t"])
        self.decisions, self.placed, self.wrong, self.dropped = (int(s[k]) for k in ("decisions", "placed", "wrong", "dropped"))
