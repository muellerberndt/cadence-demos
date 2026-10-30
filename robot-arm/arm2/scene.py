"""The contact-physics cell: a Franka Panda over a table with one block, two bins and two lamps.

The Panda comes from MuJoCo Menagerie (``menagerie/franka_emika_panda/panda.xml``, bytes
unchanged); ``build`` loads it through ``mujoco.MjSpec`` and adds the table (top at z = 0, the
robot's mounting plane), a free block, two open bins, two lamps and a ``tcp`` site 0.1034 m
down the hand's axis, between the fingertip pads. Units are metres, seconds, radians; x points
away from the robot across the table, y to its left, z up.

Physics runs at the model's 500 Hz; one decision is ``STEPS_PER_DECISION`` = 100 steps (0.2 s,
the cell's 12-frame decision at 60 Hz). The seven joint actuators are the Menagerie position
servos (``kp`` 4500 / 3500 / 2000, no gravity compensation), so ``data.ctrl[:7]`` is the
equilibrium posture; ``ctrl[7]`` drives the finger tendon (255 open, 0 closed). The block's
half side, mass, friction and contact time constant are drawn per job from the ``PHYSICS``
set in use; ``heldout`` draws from ranges ``nominal`` never uses.

Holding is read from contacts: the block touching a geom of each finger while the gripper is
commanded closed. A grasp is the moment holding begins; a slip is holding ending with the
gripper still closed; a release is holding ending after an open command, judged once the block
rests (in the bin the lamp names: placed right; in the other: wrong; elsewhere: dropped).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

PANDA = Path(__file__).resolve().parent / "menagerie" / "franka_emika_panda" / "panda.xml"
TABLE_X = (0.25, 0.85)
TABLE_Y = (-0.42, 0.42)
SPAWN_X = (0.36, 0.54)
SPAWN_Y = (-0.24, 0.24)
BIN_HOME = {"A": (0.62, -0.22), "B": (0.62, 0.22)}
BIN_SIDE = 0.13  # inner side
BIN_WALL = 0.005
BIN_HEIGHT = 0.04
LAMP = {"A": (0.80, -0.30, 0.05), "B": (0.80, 0.30, 0.05)}
ORDERS = ("none", "A", "B")
LIFT = 0.15  # carrying height of the tcp above the table
HOVER = 0.08  # the teacher's hover height above the block centre before lowering
STEPS_PER_DECISION = 100
RECORD_EVERY = 5  # the gates sample the physics at 100 Hz
HOME_Q = np.array([0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853])
R_DOWN = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])  # the hand's rotation at home: fingers down
ARM = slice(0, 7)
PHYSICS = {
    "nominal": {"half": (0.015, 0.030), "mass": (0.03, 0.12), "friction": (0.7, 1.2), "solref": [(0.02, 0.02)]},
    "heldout": {"half": (0.015, 0.030), "mass": (0.13, 0.18), "friction": (0.45, 0.60), "solref": [(0.008, 0.012), (0.03, 0.04)]},
    # stage 2b: training spans today's held-out range; the new held-out set lies beyond it. Contact
    # time constants stay at 0.015 s or more (the stage-2 held-out band 0.008-0.012 s is unstable
    # at the 0.002 s step under the squeeze: the block leaves the world); the damping ratio
    # ("dampratio", second solref value, 1 = critical) varies instead.
    "wide": {"half": (0.015, 0.030), "mass": (0.03, 0.18), "friction": (0.45, 1.20), "solref": [(0.015, 0.040)], "dampratio": (0.6, 1.0)},
    "heldout2": {"half": (0.015, 0.030), "mass": (0.18, 0.22), "friction": (0.38, 0.45), "solref": [(0.040, 0.048)], "dampratio": (0.5, 0.6)},
}
GRIP_STIFFNESS = 1000.0  # N/m of the finger tendon servo at load time (Menagerie's file: 100)
GRASP_PLANAR = 0.012
GRASP_HEIGHT = 0.012
SETTLE_SPEED = 0.03
RELEASE_WAIT = 6  # decisions a release may take to settle before it is judged

_MODEL: mujoco.MjModel | None = None


def in_bin(x: float, y: float, bins: dict[str, tuple[float, float]] = BIN_HOME, margin: float = 0.0) -> str | None:
    for name, (bx, by) in bins.items():
        if abs(x - bx) <= BIN_SIDE / 2 + margin and abs(y - by) <= BIN_SIDE / 2 + margin:
            return name
    return None


def build() -> mujoco.MjModel:
    """The compiled cell, built once per process; worlds take a copy each."""
    global _MODEL
    if _MODEL is not None:
        return copy.copy(_MODEL)
    spec = mujoco.MjSpec.from_file(str(PANDA))
    spec.body("hand").add_site(name="tcp", pos=[0.0, 0.0, 0.1034], size=[0.004, 0.004, 0.004], rgba=[0, 1, 0, 0.5])
    # The one change to the Menagerie model, applied here and not in its files: the finger tendon
    # servo at GRIP_STIFFNESS N/m in place of 100 N/m, so a 3 to 6 cm block is squeezed with 10 to
    # 25 N (the real gripper holds 70 N continuous); ctrl 255 still opens to 4 cm, 0 closes.
    grip = spec.actuator("actuator8")
    grip.gainprm[0] = 0.04 * GRIP_STIFFNESS / 255.0
    grip.biasprm[1] = -GRIP_STIFFNESS
    grip.biasprm[2] = -GRIP_STIFFNESS / 10.0
    w = spec.worldbody
    box = mujoco.mjtGeom.mjGEOM_BOX
    cx, cy = (TABLE_X[0] + TABLE_X[1]) / 2, (TABLE_Y[0] + TABLE_Y[1]) / 2
    w.add_geom(name="table", type=box, size=[(TABLE_X[1] - TABLE_X[0]) / 2, (TABLE_Y[1] - TABLE_Y[0]) / 2, 0.02],
               pos=[cx, cy, -0.02], rgba=[0.55, 0.45, 0.35, 1], friction=[1.0, 0.005, 0.0001])
    block = w.add_body(name="block", pos=[0.45, 0.0, 0.03])
    block.add_freejoint(name="block")
    block.add_geom(name="block", type=box, size=[0.03, 0.03, 0.03], rgba=[0.85, 0.15, 0.1, 1], mass=0.1)
    half, wall, height = BIN_SIDE / 2, BIN_WALL, BIN_HEIGHT
    for name, (bx, by) in BIN_HOME.items():
        w.add_geom(name=f"bin_{name}_floor", type=box, size=[half + wall, half + wall, 0.002], pos=[bx, by, 0.002],
                   rgba=[0.2, 0.2, 0.25, 1])
        for k, (dx, dy, sx, sy) in enumerate(((half + wall / 2, 0, wall / 2, half + wall), (-(half + wall / 2), 0, wall / 2, half + wall),
                                              (0, half + wall / 2, half + wall, wall / 2), (0, -(half + wall / 2), half + wall, wall / 2))):
            w.add_geom(name=f"bin_{name}_wall{k}", type=box, size=[sx, sy, height / 2], pos=[bx + dx, by + dy, height / 2],
                       rgba=[0.2, 0.2, 0.25, 1])
    for name, (lx, ly, lz) in LAMP.items():
        w.add_geom(name=f"lamp_{name}", type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[0.03, 0, 0], pos=[lx, ly, lz],
                   rgba=[0.3, 0.3, 0.3, 1], contype=0, conaffinity=0)
    _MODEL = spec.compile()  # the Panda's own light lights the scene
    return copy.copy(_MODEL)


class PandaWorld:
    """One cell with one Panda, one block and two bins; a continuing life of decisions."""

    def __init__(self, seed: int = 0, physics: str = "nominal") -> None:
        self.model = build()
        self.data = mujoco.MjData(self.model)
        self.scratch = mujoco.MjData(self.model)
        self.rng = np.random.default_rng(seed)
        self.physics = physics
        m = self.model
        self.tcp = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "tcp")
        self.block_body = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "block")
        self.block_geom = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "block")
        joint = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "block")
        self.block_qpos, self.block_qvel = int(m.jnt_qposadr[joint]), int(m.jnt_dofadr[joint])
        self.fingers = tuple(mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, n) for n in ("left_finger", "right_finger"))
        self.lamps = {k: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, f"lamp_{k}") for k in BIN_HOME}
        self.key = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_KEY, "home")
        self.low, self.high = m.jnt_range[:7, 0].copy(), m.jnt_range[:7, 1].copy()
        self.bins = {k: tuple(v) for k, v in BIN_HOME.items()}
        self._jacp, self._jacr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        self.decisions = self.placed = self.wrong = self.dropped = self.slipped = 0
        self.closed = False
        self.closed_for = 0
        self.releasing = 0
        self.holding = False
        self.lifted_once = False
        self.grasp_offset = 0.0
        self.last_command: np.ndarray | None = None
        self.half = 0.025
        self.order = 1
        self.home()
        self.spawn_block()

    # --- state ---------------------------------------------------------------------------------
    def home(self) -> None:
        mujoco.mj_resetDataKeyframe(self.model, self.data, self.key)
        self.data.ctrl[ARM] = HOME_Q
        self.data.ctrl[7] = 255.0
        self.closed, self.closed_for, self.releasing, self.holding = False, 0, 0, False
        mujoco.mj_forward(self.model, self.data)

    def set_posture(self, q: np.ndarray) -> None:
        self.data.qpos[ARM] = q
        self.data.qvel[:] = 0.0
        self.data.ctrl[ARM] = q
        self.data.qpos[7:9] = 0.04
        self.data.ctrl[7] = 255.0
        self.closed, self.closed_for, self.releasing, self.holding = False, 0, 0, False
        mujoco.mj_forward(self.model, self.data)

    def randomize_block(self) -> dict:
        """The block's half side, mass, friction and contact time constant from the physics set."""
        p = PHYSICS[self.physics]
        half = float(self.rng.uniform(*p["half"]))
        mass = float(self.rng.uniform(*p["mass"]))
        friction = float(self.rng.uniform(*p["friction"]))
        lo, hi = p["solref"][int(self.rng.integers(len(p["solref"])))]
        timeconst = float(self.rng.uniform(lo, hi))
        dampratio = float(self.rng.uniform(*p["dampratio"])) if "dampratio" in p else 1.0
        m = self.model
        m.geom_size[self.block_geom] = (half, half, half)
        m.geom_friction[self.block_geom, 0] = friction
        m.geom_solref[self.block_geom] = (timeconst, dampratio)
        m.body_mass[self.block_body] = mass
        m.body_inertia[self.block_body] = mass * (2 * half) ** 2 / 6.0  # a uniform cube
        self.half = half
        return {"half": half, "mass": mass, "friction": friction, "solref_timeconst": timeconst}

    def spawn_block(self) -> dict:
        drawn = self.randomize_block()
        for _ in range(100):
            x = float(self.rng.uniform(*SPAWN_X))
            y = float(self.rng.uniform(*SPAWN_Y))
            if in_bin(x, y, self.bins, margin=0.04) is None:
                break
        q = self.block_qpos
        self.data.qpos[q:q + 7] = (x, y, self.half, 1.0, 0.0, 0.0, 0.0)
        self.data.qvel[self.block_qvel:self.block_qvel + 6] = 0.0
        self.lifted_once = False
        mujoco.mj_forward(self.model, self.data)
        return drawn

    def new_order(self) -> None:
        self.order = int(self.rng.integers(1, 3))
        for k, gid in self.lamps.items():
            lit = ORDERS[self.order] == k
            self.model.geom_rgba[gid] = (1.0, 0.95, 0.4, 1.0) if lit else (0.3, 0.3, 0.3, 1.0)

    def randomize(self) -> None:
        """A fresh job: a random reachable posture above the table (through the reflex's own
        IK from home), a fresh block and order, the gripper open."""
        for _ in range(20):
            target = np.array([self.rng.uniform(0.34, 0.60), self.rng.uniform(-0.26, 0.26), self.rng.uniform(0.12, 0.35)])
            q = self.solve_ik(HOME_Q, target, iterations=40, bound=None)
            self.set_posture(q)
            if np.linalg.norm(self.tip() - target) < 0.03:
                break
        self.spawn_block()
        self.new_order()
        self.decisions_since_spawn = 0

    # --- kinematics ----------------------------------------------------------------------------
    def tip(self) -> np.ndarray:
        return self.data.site_xpos[self.tcp].copy()

    def tip_rotation(self) -> np.ndarray:
        return self.data.site_xmat[self.tcp].reshape(3, 3).copy()

    def block_pos(self) -> np.ndarray:
        return self.data.xpos[self.block_body].copy()

    def block_speed(self) -> float:
        return float(np.linalg.norm(self.data.qvel[self.block_qvel:self.block_qvel + 3]))

    def block_top(self) -> float:
        return float(self.block_pos()[2] + self.half)

    def joints(self) -> np.ndarray:
        return self.data.qpos[ARM].copy()

    def velocities(self) -> np.ndarray:
        return self.data.qvel[ARM].copy()

    def opening(self) -> float:
        return float(self.data.qpos[7])

    def rest(self) -> np.ndarray:
        return self.data.ctrl[ARM].copy()

    def ordered_bin(self) -> tuple[float, float] | None:
        return None if self.order == 0 else self.bins[ORDERS[self.order]]

    def release_point(self) -> np.ndarray | None:
        b = self.ordered_bin()
        return None if b is None else np.array([b[0], b[1], LIFT])

    def hover_point(self) -> np.ndarray:
        return self.block_pos() + np.array([0.0, 0.0, HOVER])

    def grasp_point(self) -> np.ndarray:
        return self.block_pos()

    def jacobian(self, data: mujoco.MjData | None = None) -> tuple[np.ndarray, np.ndarray]:
        mujoco.mj_jacSite(self.model, self.data if data is None else data, self._jacp, self._jacr, self.tcp)
        return self._jacp[:, ARM].copy(), self._jacr[:, ARM].copy()

    def solve_ik(self, q0: np.ndarray, target: np.ndarray, rotation: np.ndarray = R_DOWN, *, iterations: int = 3,
                 damping: float = 0.05, posture: float = 0.05, rot_weight: float = 0.5, bound: float | None = 0.15) -> np.ndarray:
        """Damped least squares on the tcp site, position and orientation (the hand kept pointing
        down), with a null-space bias toward the home posture; the change from ``q0`` clipped to
        ``bound`` radians per joint when given."""
        q = np.asarray(q0, dtype=float).copy()
        s = self.scratch
        eye6, eye7 = np.eye(6), np.eye(7)
        for _ in range(iterations):
            s.qpos[ARM] = q
            mujoco.mj_kinematics(self.model, s)
            mujoco.mj_comPos(self.model, s)
            pos = s.site_xpos[self.tcp]
            rot = s.site_xmat[self.tcp].reshape(3, 3)
            jp, jr = self.jacobian(s)
            j = np.vstack([jp, rot_weight * jr])
            rot_err = 0.5 * sum(np.cross(rot[:, i], rotation[:, i]) for i in range(3))
            err = np.concatenate([target - pos, rot_weight * rot_err])
            inverse = j.T @ np.linalg.inv(j @ j.T + damping * damping * eye6)
            dq = inverse @ err + (eye7 - inverse @ j) @ (posture * (HOME_Q - q))
            q = np.clip(q + dq, self.low, self.high)
        if bound is not None:
            q = np.clip(q, np.asarray(q0) - bound, np.asarray(q0) + bound)
        return np.clip(q, self.low, self.high)

    # --- contacts ------------------------------------------------------------------------------
    def finger_contacts(self) -> tuple[bool, bool]:
        """Whether the block touches a geom of the left and of the right finger."""
        touched = [False, False]
        m, d = self.model, self.data
        for i in range(d.ncon):
            c = d.contact[i]
            g1, g2 = int(c.geom1), int(c.geom2)
            if g1 != self.block_geom and g2 != self.block_geom:
                continue
            other = g2 if g1 == self.block_geom else g1
            body = int(m.geom_bodyid[other])
            for k, finger in enumerate(self.fingers):
                if body == finger:
                    touched[k] = True
        return bool(touched[0]), bool(touched[1])

    # --- slip senses (stage 2b) ------------------------------------------------------------------
    def tip_velocity(self) -> np.ndarray:
        v = np.zeros(6)
        mujoco.mj_objectVelocity(self.model, self.data, mujoco.mjtObj.mjOBJ_SITE, self.tcp, v, 0)
        return v[3:6].copy()  # linear, world frame

    def relative_velocity(self) -> np.ndarray:
        """The block's velocity relative to the fingertips (m/s): nonzero while it slips."""
        return self.data.qvel[self.block_qvel:self.block_qvel + 3] - self.tip_velocity()

    def contact_force(self) -> float:
        """The normal force the fingers put on the block (N), summed over their contacts."""
        m, d = self.model, self.data
        total = 0.0
        f = np.zeros(6)
        for i in range(d.ncon):
            c = d.contact[i]
            g1, g2 = int(c.geom1), int(c.geom2)
            if g1 != self.block_geom and g2 != self.block_geom:
                continue
            other = g2 if g1 == self.block_geom else g1
            if int(m.geom_bodyid[other]) in self.fingers:
                mujoco.mj_contactForce(m, d, i, f)
                total += abs(float(f[0]))
        return total

    # --- physics -------------------------------------------------------------------------------
    def decide(self, q_target: np.ndarray, close: int, hook=None) -> dict[str, Any]:
        """One decision: the equilibrium posture and the gripper, then 100 physics steps.
        ``hook(sample_index)`` runs every ``RECORD_EVERY`` steps. Returns the outcome."""
        d = self.data
        d.ctrl[ARM] = np.clip(np.asarray(q_target, dtype=float), self.low, self.high)
        close = bool(close)
        if close != self.closed:
            self.closed_for = 0
            if self.closed and self.holding:  # an open command while holding: a release begins
                self.releasing = 1
        self.closed = close
        d.ctrl[7] = 0.0 if close else 255.0
        outcome: dict[str, Any] = {"reward": 0.0, "event": None, "done": False}
        was_holding = self.holding
        for i in range(STEPS_PER_DECISION):
            mujoco.mj_step(self.model, d)
            if hook is not None and (i + 1) % RECORD_EVERY == 0:
                hook((i + 1) // RECORD_EVERY)
        block_z = float(self.block_pos()[2])
        if not np.isfinite(self.data.qvel).all() or not np.isfinite(self.data.qpos).all() or abs(block_z) > 1.0:
            # the contact solver blew the block out of the world (seen with contact time
            # constants under 0.015 s): the block is lost, counted as dropped, and respawned
            self.data.qvel[:] = 0.0
            self.data.qpos[ARM] = np.clip(np.nan_to_num(self.data.qpos[ARM]), self.low, self.high)
            self.data.qpos[7:9] = np.clip(np.nan_to_num(self.data.qpos[7:9]), 0.0, 0.04)
            self.holding, self.releasing = False, 0
            self.dropped += 1
            self.spawn_block()
            self.decisions += 1
            outcome.update(reward=-0.1, event="dropped")
            return outcome
        left, right = self.finger_contacts()
        self.holding = bool(self.closed and left and right)
        if self.closed and not self.holding:
            self.closed_for += 1
        if self.holding and not was_holding:
            outcome["event"] = "grasped"
            self.releasing = 0
            self.grasp_offset = float(self.tip()[2] - block_z)  # where the block sits in the fingers; sag shows a slip
        elif was_holding and not self.holding and self.closed:
            outcome["event"] = "slipped"
            self.slipped += 1
            self.releasing = 1  # judged like a release: where the block comes to rest
        if self.holding and self.block_pos()[2] - self.half >= 0.05:
            self.lifted_once = True
        if self.releasing and not self.holding:
            settled = self.block_speed() < SETTLE_SPEED and self.block_pos()[2] < BIN_HEIGHT + 2 * self.half
            if settled or self.releasing > RELEASE_WAIT:
                x, y, _ = self.block_pos()
                name = in_bin(x, y, self.bins)
                if name is not None and self.block_pos()[2] < BIN_HEIGHT + self.half + 0.01:
                    right_bin = ORDERS[self.order] == name
                    outcome["reward"] = 1.0 if right_bin else -0.25
                    outcome["event"] = f"placed:{name}:{'right' if right_bin else 'wrong'}"
                    outcome["done"] = True
                    self.placed += int(right_bin)
                    self.wrong += int(not right_bin)
                    self.spawn_block()
                    self.new_order()
                else:
                    outcome["reward"] = -0.1
                    outcome["event"] = "dropped" if outcome["event"] is None else outcome["event"]
                    self.dropped += 1
                self.releasing = 0
            else:
                self.releasing += 1
        self.decisions += 1
        return outcome

    def snapshot(self) -> dict[str, Any]:
        return {"qpos": self.data.qpos.tolist(), "ctrl": self.data.ctrl.tolist(), "half": self.half, "order": self.order,
                "closed": self.closed, "holding": self.holding, "block": self.block_pos().tolist(), "tip": self.tip().tolist(),
                "physics": self.physics}
