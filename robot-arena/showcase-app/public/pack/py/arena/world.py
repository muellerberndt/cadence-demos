"""The arena: a flat round floor, a ring that closes, and robots that push, swing and hit.

Top-down rigid bodies with a fixed moment of ``DT`` seconds; the brain issues one command per
motor per moment. Every force is local to a part: a wheel or a planted leg pushes along the
robot's heading at its mount point, so limbs on one side turn the body; a weapon hurts only
the chassis it touches. Nothing in here knows what a brain is: ``Arena.step`` takes the
commands of every robot and returns what each one dealt, took and did.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .parts import (
    ARM_CONE,
    ARM_LENGTH,
    ARM_RATE,
    LEG_RATE,
    LEG_RECOVER_RATE,
    LEG_THRUST,
    SPINNER_SPINDOWN,
    SPINNER_SPINUP,
    WEAPON_RADIUS,
    WHEEL_THRUST,
    Blueprint,
    Part,
)

DT = 0.05  # seconds per moment: 20 brain moments per simulated second

# ground
DRAG_ROLL = 4.0  # 1/s, speed-proportional longitudinal drag of wheels and planted legs (0.25 s response)
DRAG_BELLY = 8.0  # 1/s, a robot with no wheel and no planted foot sits on its belly
DRAG_BRAKE = 4.0  # 1/s added when every drive part brakes or holds
GRIP = 8.0  # 1/s, lateral grip of wheels and planted feet
SPIN_DRAG = 6.0  # 1/s, damping of the body's rotation

# weapons (hit points, seconds, metres)
SPIKE_RATE = 3.0  # hp/s while a spike rests against a chassis
SPIKE_SPEED = 6.0  # hp per (m/s) of closing speed, per second
HAMMER_DAMAGE = 18.0  # hp of a full-speed hammer blow
HAMMER_SPEED = 3.0  # m/s tip speed for a full blow
HAMMER_COOLDOWN = 0.8  # s before the hammer can hurt again
SPINNER_RATE = 50.0  # hp/s at full spin
SPINNER_KICK = 40.0  # N.s of knockback at full spin
SPINNER_LOSS = 0.15  # share of spin lost per moment of contact
RAM_FACTOR = 2.5  # hp per (m/s)^2 of closing speed, shared by mass
RAM_MIN_SPEED = 0.8  # m/s below which bumping does not hurt
RESTITUTION = 0.3

# the ring
ZONE_DAMAGE = 6.0  # hp/s outside the ring


@dataclass
class Robot:
    """One robot's body: pose, motion, hit points and the state of every part."""

    rid: int
    blueprint: Blueprint
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    omega: float = 0.0
    hp: float = 0.0
    alive: bool = True
    place: int | None = None  # final placement once eliminated (1 = winner)
    died_at: int | None = None
    # per part (indexed like blueprint.parts; unused entries stay zero)
    stride: np.ndarray = field(default_factory=lambda: np.zeros(0))
    planted: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    angle: np.ndarray = field(default_factory=lambda: np.zeros(0))
    spin: np.ndarray = field(default_factory=lambda: np.zeros(0))
    cooldown: np.ndarray = field(default_factory=lambda: np.zeros(0))
    recover: np.ndarray = field(default_factory=lambda: np.zeros(0))  # legs: the end a lifted foot swings to (0 = planted)
    tip: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    tip_vel: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    in_reach: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    commands: list[int] = field(default_factory=list)
    # readings of the last moment
    dealt: float = 0.0
    taken: float = 0.0
    zone_taken: float = 0.0
    outside: bool = False
    hits: list[tuple[float, float, float]] = field(default_factory=list)  # x, y, damage dealt

    @classmethod
    def build(cls, rid: int, blueprint: Blueprint) -> Robot:
        n = len(blueprint.parts)
        robot = cls(rid=rid, blueprint=blueprint, hp=blueprint.hp)
        robot.stride = np.ones(n)  # legs start swung forward, ready for a power stroke
        robot.recover = np.zeros(n)
        robot.planted = np.array([p.kind == "leg" for p in blueprint.parts])
        robot.angle = np.zeros(n)
        robot.spin = np.zeros(n)
        robot.cooldown = np.zeros(n)
        robot.recover = np.zeros(n)
        robot.tip = np.zeros((n, 2))
        robot.tip_vel = np.zeros((n, 2))
        robot.in_reach = np.zeros(n, bool)
        robot.commands = [1] * blueprint.motors
        return robot

    # -- geometry

    @property
    def mass(self) -> float:
        return self.blueprint.mass

    @property
    def radius(self) -> float:
        return self.blueprint.radius

    @property
    def inertia(self) -> float:
        return 0.5 * self.mass * self.radius**2

    @property
    def pos(self) -> np.ndarray:
        return np.array([self.x, self.y])

    @property
    def vel(self) -> np.ndarray:
        return np.array([self.vx, self.vy])

    @property
    def forward(self) -> np.ndarray:
        return np.array([math.cos(self.heading), math.sin(self.heading)])

    @property
    def left(self) -> np.ndarray:
        return np.array([-math.sin(self.heading), math.cos(self.heading)])

    def mount_point(self, i: int) -> np.ndarray:
        """World position of part ``i``'s mount on the rim."""
        phi = self.heading + math.radians(self.blueprint.parts[i].mount)
        return self.pos + self.radius * np.array([math.cos(phi), math.sin(phi)])

    def arm_tip(self, i: int) -> np.ndarray:
        phi = self.heading + math.radians(self.blueprint.parts[i].mount) + self.angle[i]
        return self.mount_point(i) + ARM_LENGTH * np.array([math.cos(phi), math.sin(phi)])

    def place_at(self, x: float, y: float, heading: float) -> None:
        self.x, self.y, self.heading = float(x), float(y), float(heading)
        self.vx = self.vy = self.omega = 0.0
        for i in self.blueprint.arms():
            self.tip[i] = self.arm_tip(i)
            self.tip_vel[i] = 0.0

    def motor_commands(self) -> list[tuple[Part, int, int | None]]:
        """(part, main command, spinner switch) per part from the flat command list."""
        out = []
        k = 0
        for p in self.blueprint.parts:
            main = self.commands[k]
            k += 1
            switch = None
            if p.kind == "arm" and p.weapon == "spinner":
                switch = self.commands[k]
                k += 1
            out.append((p, main, switch))
        return out


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class Arena:
    """A round floor of ``radius`` metres. The ring starts at the wall and closes to
    ``zone_end`` over ``zone_moments`` moments; a robot outside it burns. ``step`` advances one
    moment with the given commands (one int per motor slot per robot)."""

    def __init__(
        self,
        robots: list[Robot],
        *,
        radius: float = 10.0,
        zone_end: float = 2.5,
        zone_moments: int = 1000,
        seed: int = 0,
        spawn: bool = True,
    ) -> None:
        self.robots = robots
        self.radius = float(radius)
        self.zone_end = float(zone_end)
        self.zone_moments = int(zone_moments)
        self.t = 0
        self.rng = np.random.default_rng(seed)
        self.eliminated = 0
        if spawn:
            self.spawn_ring()

    # -- placement

    def spawn_ring(self, share: float = 0.65) -> None:
        """Robots evenly around a ring, facing the centre, with a random rotation."""
        n = len(self.robots)
        offset = float(self.rng.uniform(0, 2 * math.pi))
        for k, robot in enumerate(self.robots):
            a = offset + 2 * math.pi * k / max(1, n)
            r = share * self.radius
            robot.place_at(r * math.cos(a), r * math.sin(a), _wrap(a + math.pi))

    def zone_radius(self, t: int | None = None) -> float:
        t = self.t if t is None else t
        share = min(1.0, t / max(1, self.zone_moments))
        return self.radius + (self.zone_end - self.radius) * share

    def alive(self) -> list[Robot]:
        return [r for r in self.robots if r.alive]

    # -- one moment

    def step(self, commands: dict[int, list[int]]) -> dict[int, dict[str, Any]]:
        for robot in self.robots:
            robot.dealt = robot.taken = robot.zone_taken = 0.0
            robot.hits = []
            robot.outside = False
            if robot.rid in commands and robot.alive:
                cmd = list(commands[robot.rid])
                if len(cmd) != robot.blueprint.motors:
                    raise ValueError(
                        f"robot {robot.rid} has {robot.blueprint.motors} motors, got {len(cmd)}"
                    )
                robot.commands = [int(c) for c in cmd]
        for robot in self.alive():
            self._move(robot)
        self._collide()
        self._weapons()
        self._zone()
        self.t += 1
        out: dict[int, dict[str, Any]] = {}
        for robot in self.robots:
            if robot.alive and robot.hp <= 0.0:
                robot.alive = False
                robot.hp = 0.0
                robot.died_at = self.t
                robot.place = len(self.robots) - self.eliminated
                self.eliminated += 1
            out[robot.rid] = {
                "dealt": robot.dealt,
                "taken": robot.taken,
                "zone": robot.zone_taken,
                "outside": robot.outside,
                "alive": robot.alive,
                "hp": robot.hp,
            }
        return out

    def finish(self) -> None:
        """End of the fight: survivors are placed by remaining hit points."""
        survivors = sorted(self.alive(), key=lambda r: (-r.hp, r.rid))
        for k, robot in enumerate(survivors):
            robot.place = k + 1

    # -- body dynamics

    def _move(self, robot: Robot) -> None:
        bp = robot.blueprint
        f, l = robot.forward, robot.left
        thrust = 0.0  # along the heading
        torque = 0.0
        contacts = 0
        drive_parts = 0
        braking = 0
        for i, (part, cmd, switch) in enumerate(robot.motor_commands()):
            phi = math.radians(part.mount)
            r_left = bp.radius * math.sin(phi)  # lateral offset of the mount (left positive)
            if part.kind == "wheel":
                drive_parts += 1
                contacts += 1
                push = (cmd - 1) * WHEEL_THRUST
                if cmd == 1:
                    braking += 1
                thrust += push
                torque += -r_left * push
            elif part.kind == "leg":
                drive_parts += 1
                s = robot.stride[i]
                if robot.recover[i] != 0.0:
                    # the stepping reflex: a spent leg lifts and swings to the other end on
                    # its own, then plants again; commands are ignored while it swings
                    robot.planted[i] = False
                    target = robot.recover[i]
                    s = s + np.sign(target - s) * LEG_RECOVER_RATE * DT
                    if (target > 0 and s >= target) or (target < 0 and s <= target):
                        s, robot.recover[i], robot.planted[i] = target, 0.0, True
                    robot.stride[i] = float(s)
                elif cmd == 1:  # hold: the planted foot anchors the body
                    robot.planted[i] = True
                    braking += 1
                else:
                    # push: the planted foot drives the body forward (stride runs back) or
                    # backward (stride runs forward) until the stride is spent
                    direction = 1.0 if cmd == 0 else -1.0
                    robot.planted[i] = True
                    robot.stride[i] = float(np.clip(s - direction * LEG_RATE * DT, -1.0, 1.0))
                    thrust += direction * LEG_THRUST
                    torque += -r_left * direction * LEG_THRUST
                    if robot.stride[i] <= -1.0 or robot.stride[i] >= 1.0:
                        robot.recover[i] = -robot.stride[i]  # lift and swing to the other end
                if robot.planted[i]:
                    contacts += 1
            else:  # arm
                target = robot.angle[i] + (cmd - 1) * ARM_RATE * DT
                robot.angle[i] = float(np.clip(target, -ARM_CONE, ARM_CONE))
                if part.weapon == "spinner":
                    if switch == 1:
                        robot.spin[i] = min(1.0, robot.spin[i] + DT / SPINNER_SPINUP)
                    else:
                        robot.spin[i] = max(0.0, robot.spin[i] - DT / SPINNER_SPINDOWN)
                if robot.cooldown[i] > 0.0:
                    robot.cooldown[i] = max(0.0, robot.cooldown[i] - DT)
        m, inertia = robot.mass, robot.inertia
        v_fwd = robot.vx * f[0] + robot.vy * f[1]
        v_lat = robot.vx * l[0] + robot.vy * l[1]
        if contacts:
            drag = DRAG_ROLL + DRAG_BRAKE * braking / max(1, drive_parts)
            grip = GRIP
        else:
            drag = grip = DRAG_BELLY
        a_fwd = thrust / m - drag * v_fwd
        a_lat = -grip * v_lat
        alpha = torque / inertia - SPIN_DRAG * robot.omega
        v_fwd += a_fwd * DT
        v_lat += a_lat * DT
        robot.omega += alpha * DT
        robot.vx = v_fwd * f[0] + v_lat * l[0]
        robot.vy = v_fwd * f[1] + v_lat * l[1]
        robot.x += robot.vx * DT
        robot.y += robot.vy * DT
        robot.heading = _wrap(robot.heading + robot.omega * DT)
        # the wall
        d = math.hypot(robot.x, robot.y)
        limit = self.radius - robot.radius
        if d > limit and d > 0:
            nx, ny = robot.x / d, robot.y / d
            robot.x, robot.y = nx * limit, ny * limit
            vn = robot.vx * nx + robot.vy * ny
            if vn > 0:
                robot.vx -= (1 + 0.2) * vn * nx
                robot.vy -= (1 + 0.2) * vn * ny
        # weapon tips and their velocity, by finite difference
        for i in bp.arms():
            tip = robot.arm_tip(i)
            robot.tip_vel[i] = (tip - robot.tip[i]) / DT
            robot.tip[i] = tip

    def _collide(self) -> None:
        alive = self.alive()
        for a in range(len(alive)):
            for b in range(a + 1, len(alive)):
                A, B = alive[a], alive[b]
                dx, dy = B.x - A.x, B.y - A.y
                d = math.hypot(dx, dy)
                overlap = A.radius + B.radius - d
                if overlap <= 0.0:
                    continue
                if d < 1e-9:
                    dx, dy, d = 1.0, 0.0, 1.0
                nx, ny = dx / d, dy / d
                ma, mb = A.mass, B.mass
                # separate by inverse mass
                A.x -= nx * overlap * mb / (ma + mb)
                A.y -= ny * overlap * mb / (ma + mb)
                B.x += nx * overlap * ma / (ma + mb)
                B.y += ny * overlap * ma / (ma + mb)
                vrel = (B.vx - A.vx) * nx + (B.vy - A.vy) * ny
                if vrel >= 0.0:
                    continue  # already separating
                closing = -vrel
                j = (1 + RESTITUTION) * closing / (1 / ma + 1 / mb)
                A.vx -= j / ma * nx
                A.vy -= j / ma * ny
                B.vx += j / mb * nx
                B.vy += j / mb * ny
                if closing > RAM_MIN_SPEED:
                    energy = RAM_FACTOR * (closing - RAM_MIN_SPEED) ** 2
                    to_b = energy * ma / (ma + mb)  # the lighter one takes more
                    to_a = energy * mb / (ma + mb)
                    hx, hy = A.x + nx * A.radius, A.y + ny * A.radius
                    self._hurt(A, B, to_b, hx, hy)
                    self._hurt(B, A, to_a, hx, hy)

    def _hurt(self, attacker: Robot, victim: Robot, damage: float, x: float, y: float) -> None:
        if damage <= 0.0:
            return
        victim.hp -= damage
        victim.taken += damage
        attacker.dealt += damage
        attacker.hits.append((float(x), float(y), float(damage)))

    def _weapons(self) -> None:
        alive = self.alive()
        for A in alive:
            for i in A.blueprint.arms():
                # Collision separation moves the chassis after _move measured the
                # tip's physical velocity. Keep the weapon on that chassis without
                # turning this position correction into a strike next moment.
                A.tip[i] = A.arm_tip(i)
                A.in_reach[i] = False
                weapon = A.blueprint.parts[i].weapon
                assert weapon is not None
                reach = WEAPON_RADIUS[weapon]
                tip = A.tip[i]
                best: Robot | None = None
                best_d = math.inf
                for B in alive:
                    if B is A:
                        continue
                    d = float(np.hypot(*(B.pos - tip))) - B.radius
                    if d < best_d:
                        best, best_d = B, d
                if best is None:
                    continue
                A.in_reach[i] = best_d < reach + 0.35  # the sense: a chassis near the weapon
                if best_d >= reach:
                    continue
                B = best
                away = B.pos - tip
                dist = float(np.hypot(*away))
                n = away / dist if dist > 1e-9 else A.forward
                closing = float(np.dot(A.tip_vel[i] - B.vel, n))
                tip_speed = float(np.hypot(*(A.tip_vel[i] - B.vel)))
                if weapon == "spike":
                    damage = (SPIKE_RATE + SPIKE_SPEED * max(0.0, closing)) * DT
                    self._hurt(A, B, damage, *tip)
                elif weapon == "hammer":
                    if A.cooldown[i] <= 0.0 and tip_speed > 1.0:
                        damage = HAMMER_DAMAGE * min(1.0, tip_speed / HAMMER_SPEED)
                        self._hurt(A, B, damage, *tip)
                        A.cooldown[i] = HAMMER_COOLDOWN
                        kick = 0.4 * damage
                        B.vx += kick / B.mass * n[0]
                        B.vy += kick / B.mass * n[1]
                else:  # spinner
                    spin = float(A.spin[i])
                    if spin > 0.05:
                        damage = SPINNER_RATE * spin**2 * DT
                        self._hurt(A, B, damage, *tip)
                        kick = SPINNER_KICK * spin
                        B.vx += kick / B.mass * n[0]
                        B.vy += kick / B.mass * n[1]
                        A.vx -= 0.5 * kick / A.mass * n[0]
                        A.vy -= 0.5 * kick / A.mass * n[1]
                        A.spin[i] = spin * (1.0 - SPINNER_LOSS)

    def _zone(self) -> None:
        r = self.zone_radius()
        for robot in self.alive():
            if math.hypot(robot.x, robot.y) > r:
                robot.outside = True
                damage = ZONE_DAMAGE * DT
                robot.hp -= damage
                robot.taken += damage
                robot.zone_taken += damage
