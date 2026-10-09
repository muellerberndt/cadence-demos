"""What a robot senses: the observation row its brain settles under, every value in [0, 1].

Direction is coded the way bilateral animals do it, by broadly tuned cells rather than a
compass: four cells prefer ahead, left, behind and right, and each responds to the nearest
other robot by its proximity times the cosine of the bearing to its preferred direction
(zero when the target is more than a quarter turn away). The same four cells code the ring's
edge: how close the burn is in each direction; outside the ring, the directions that lead
back in read zero and the rest read one. Then the body: forward and backward speed, turning
left and right, hit points, the pain of the last moment, the damage it dealt, whether it is
outside the ring. Then each part's proprioception: a leg's stride and whether its foot is
planted; an arm's joint angle, whether a chassis is within its weapon's reach and, for a
spinner, its spin. A wheel has no sense of its own; the efference copy carries what it was
told. One constant input closes the row, the drive that is the same every moment.
"""

from __future__ import annotations

import math

import numpy as np

from .parts import ARM_CONE, Blueprint
from .world import Arena, Robot

EYES = 4  # ahead, left, behind, right
SIGHT = 8.0  # m at which another robot's proximity reads zero
EDGE_SIGHT = 4.0  # m at which the ring's edge reads zero
SPEED_SCALE = 3.0  # m/s that reads one
TURN_SCALE = 3.0  # rad/s that reads one
PAIN_SCALE = 20.0  # hit points per moment that read one
CLOSING_SCALE = 3.0  # m/s of closing speed that reads one
THREAT_REACH = 0.5  # m from this hull at which another robot's weapon reads as a threat
BODY_INPUTS = 2 * EYES + 3 + 2 + 2 + 4
_PREFERRED = [2 * math.pi * k / EYES for k in range(EYES)]


def input_count(blueprint: Blueprint) -> int:
    return BODY_INPUTS + sum(p.senses for p in blueprint.parts) + 1


def input_names(blueprint: Blueprint) -> list[str]:
    where = ["ahead", "left", "behind", "right"]
    names = [f"robot {w}" for w in where] + [f"edge {w}" for w in where]
    names += ["robot closing", "robot receding", "weapon threat"]
    names += ["speed forward", "speed backward", "turning left", "turning right"]
    names += ["hit points", "pain", "damage dealt", "outside the ring"]
    for i, p in enumerate(blueprint.parts):
        if p.kind == "leg":
            names += [f"leg {i} stride", f"leg {i} planted"]
        elif p.kind == "arm":
            names += [f"arm {i} angle", f"arm {i} in reach"]
            if p.weapon == "spinner":
                names.append(f"arm {i} spin")
    names.append("drive")
    return names


def tuning(rel: float) -> list[float]:
    """The response of the four direction cells to a bearing ``rel`` (radians, left +)."""
    cells = [math.cos(rel - pref) for pref in _PREFERRED]
    return [c if c > 1e-9 else 0.0 for c in cells]


def observe(robot: Robot, arena: Arena) -> np.ndarray:
    """The ``(1, inputs)`` observation of ``robot`` in ``arena`` at this moment."""
    bp = robot.blueprint
    x = np.zeros(input_count(bp))
    # the nearest other robot, by direction cells
    nearest: Robot | None = None
    nearest_d = math.inf
    for other in arena.robots:
        if other is robot or not other.alive:
            continue
        d = math.hypot(other.x - robot.x, other.y - robot.y) - robot.radius - other.radius
        if d < nearest_d:
            nearest, nearest_d = other, d
    if nearest is not None:
        prox = max(0.0, 1.0 - nearest_d / SIGHT)
        rel = math.atan2(nearest.y - robot.y, nearest.x - robot.x) - robot.heading
        for k, cell in enumerate(tuning(rel)):
            x[k] = prox * cell
    # the ring's edge, by direction cells
    r = arena.zone_radius()
    p = robot.pos
    inside = math.hypot(robot.x, robot.y) <= r
    for k in range(EYES):
        a = robot.heading + _PREFERRED[k]
        u = np.array([math.cos(a), math.sin(a)])
        pu = float(np.dot(p, u))
        disc = pu * pu - (float(np.dot(p, p)) - r * r)
        if inside:
            t = -pu + math.sqrt(max(0.0, disc))  # distance to the edge along u
            x[EYES + k] = max(0.0, 1.0 - t / EDGE_SIGHT)
        else:
            enters = disc > 0.0 and (-pu - math.sqrt(disc)) > 0.0
            x[EYES + k] = 0.0 if enters else 1.0
    # the nearest robot closing or receding, and any weapon near this hull
    base = 2 * EYES
    if nearest is not None:
        dx, dy = nearest.x - robot.x, nearest.y - robot.y
        dist = math.hypot(dx, dy) or 1e-9
        rel = ((nearest.vx - robot.vx) * dx + (nearest.vy - robot.vy) * dy) / dist  # + when drawing away
        x[base + 0] = min(1.0, max(0.0, -rel / CLOSING_SCALE))
        x[base + 1] = min(1.0, max(0.0, rel / CLOSING_SCALE))
    threat = 0.0
    for other in arena.robots:
        if other is robot or not other.alive:
            continue
        for i in other.blueprint.arms():
            d = math.hypot(other.tip[i][0] - robot.x, other.tip[i][1] - robot.y) - robot.radius
            threat = max(threat, 1.0 - d / THREAT_REACH)
    x[base + 2] = min(1.0, max(0.0, threat))
    # the body
    base = 2 * EYES + 3
    v_fwd = float(np.dot(robot.vel, robot.forward)) / SPEED_SCALE
    x[base + 0] = min(1.0, max(0.0, v_fwd))
    x[base + 1] = min(1.0, max(0.0, -v_fwd))
    turn = robot.omega / TURN_SCALE
    x[base + 2] = min(1.0, max(0.0, turn))
    x[base + 3] = min(1.0, max(0.0, -turn))
    x[base + 4] = max(0.0, robot.hp / bp.hp)
    x[base + 5] = min(1.0, robot.taken / PAIN_SCALE)
    x[base + 6] = min(1.0, robot.dealt / PAIN_SCALE)
    x[base + 7] = 1.0 if robot.outside else 0.0
    # proprioception
    j = BODY_INPUTS
    for i, part in enumerate(bp.parts):
        if part.kind == "leg":
            x[j] = (robot.stride[i] + 1.0) / 2.0
            x[j + 1] = 1.0 if robot.planted[i] else 0.0
            j += 2
        elif part.kind == "arm":
            x[j] = (robot.angle[i] / ARM_CONE + 1.0) / 2.0
            x[j + 1] = 1.0 if robot.in_reach[i] else 0.0
            j += 2
            if part.weapon == "spinner":
                x[j] = robot.spin[i]
                j += 1
    x[j] = 1.0
    assert j + 1 == len(x)
    return x[None, :]
