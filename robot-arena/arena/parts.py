"""The parts catalogue and the blueprint of a robot.

A robot is a chassis with parts bolted to mount points around its rim. Every part that moves
has a motor, and every motor is one slot of the brain's motor cortex: three motor neurons for
a three-state motor (back, hold, forward), two for the spinner's on/off. ``Blueprint.slots``
is the exact slot layout the brain is composed with, so the one settled state of the brain
commands every motor at once.

Parts:

- ``wheel``   a driven wheel; reverse / brake / forward; thrust along the body's heading at
              the mount point, so wheels on one side turn the robot.
- ``leg``     a leg with a stride in [-1, 1]. Push forward / hold / push back: a planted foot
              drives the body until its stride is spent; then the stepping reflex lifts it and
              swings it to the other end, giving nothing for a while, and plants it again.
              Legs pushing in step move the body in lurches; legs out of phase walk smoothly,
              and legs on one side turn it: the gait is the brain's to find.
- ``arm``     a one-joint arm with a weapon at its tip; swing left / hold / swing right within
              a cone. Weapons: ``spike`` hurts a chassis it touches, more the faster it closes;
              ``hammer`` hurts on a swinging hit and needs a moment to be ready again;
              ``spinner`` has its own on/off motor, spins up over two seconds and hurts by its
              spin, kicking both robots back.

Masses add up; the heavier the robot, the slower it accelerates and the harder it rams.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CHASSIS: dict[str, dict[str, float]] = {
    #            footprint radius, mass, hit points, visual height, mount points
    "light": {"radius": 0.45, "mass": 18.0, "hp": 70.0, "height": 0.30, "mounts": 4},
    "medium": {"radius": 0.60, "mass": 30.0, "hp": 110.0, "height": 0.40, "mounts": 6},
    "heavy": {"radius": 0.80, "mass": 48.0, "hp": 160.0, "height": 0.50, "mounts": 8},
}

PART_MASS = {"wheel": 3.0, "leg": 4.0, "arm": 4.0}
WEAPON_MASS = {"spike": 2.0, "hammer": 6.0, "spinner": 7.0}
WEAPONS = tuple(WEAPON_MASS)
KINDS = ("wheel", "leg", "arm")

# motor constants of the body (world units: metres, seconds, newtons, hit points)
WHEEL_THRUST = 200.0  # N per wheel at full drive
LEG_THRUST = 160.0  # N per planted leg in its power stroke
LEG_RATE = 2.5  # stride units per second (a full stroke of 2 units takes 0.8 s)
LEG_RECOVER_RATE = 5.0  # stride units per second of the stepping reflex (0.4 s per swing)
ARM_RATE = 3.0  # rad/s of the arm joint
ARM_CONE = 1.2  # rad either side of the mount direction
ARM_LENGTH = 0.8  # m from the rim to the weapon
WEAPON_RADIUS = {"spike": 0.12, "hammer": 0.22, "spinner": 0.30}
SPINNER_SPINUP = 2.0  # s from rest to full spin
SPINNER_SPINDOWN = 3.0  # s from full spin to rest when off


@dataclass(frozen=True)
class Part:
    kind: str
    mount: float  # degrees from the heading, counter-clockwise (left is +90)
    weapon: str | None = None

    @property
    def mass(self) -> float:
        return PART_MASS[self.kind] + (WEAPON_MASS[self.weapon] if self.weapon else 0.0)

    @property
    def slots(self) -> list[int]:
        """The motor slots of this part: one three-state motor, plus the spinner's switch."""
        if self.kind == "arm" and self.weapon == "spinner":
            return [3, 2]
        return [3]

    @property
    def senses(self) -> int:
        """The proprioceptive inputs of this part (see ``senses.py``)."""
        if self.kind == "wheel":
            return 0
        if self.kind == "leg":
            return 2  # stride, foot planted
        return 3 if self.weapon == "spinner" else 2  # joint angle, weapon in reach, spin

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind, "mount": self.mount}
        if self.weapon:
            d["weapon"] = self.weapon
        return d


@dataclass(frozen=True)
class Blueprint:
    name: str
    chassis: str
    parts: tuple[Part, ...]
    seed: int = 0
    genes: dict[str, Any] = field(default_factory=dict)
    policy: str = "brain"  # "brain" | "random" (the uniform-random baseline with the same body)

    def __post_init__(self) -> None:
        if self.chassis not in CHASSIS:
            raise ValueError(f"unknown chassis {self.chassis!r}; one of {tuple(CHASSIS)}")
        if not self.parts:
            raise ValueError("a robot needs at least one part")
        if len(self.parts) > int(CHASSIS[self.chassis]["mounts"]):
            raise ValueError(
                f"a {self.chassis} chassis has {int(CHASSIS[self.chassis]['mounts'])} mount points"
            )
        if not any(p.kind in ("wheel", "leg") for p in self.parts):
            raise ValueError("a robot needs at least one wheel or leg")
        for p in self.parts:
            if p.kind not in KINDS:
                raise ValueError(f"unknown part kind {p.kind!r}")
            if p.kind == "arm" and p.weapon not in WEAPONS:
                raise ValueError(f"an arm needs a weapon, one of {WEAPONS}")
            if p.kind != "arm" and p.weapon is not None:
                raise ValueError(f"a {p.kind} carries no weapon")
            if not -180.0 <= float(p.mount) <= 180.0:
                raise ValueError("mount angles are degrees in [-180, 180]")
        if self.policy not in ("brain", "random"):
            raise ValueError("policy is 'brain' or 'random'")

    # -- derived

    @property
    def mass(self) -> float:
        return CHASSIS[self.chassis]["mass"] + sum(p.mass for p in self.parts)

    @property
    def hp(self) -> float:
        return CHASSIS[self.chassis]["hp"]

    @property
    def radius(self) -> float:
        return CHASSIS[self.chassis]["radius"]

    @property
    def slots(self) -> list[int]:
        """The brain's motor slot layout: every motor of every part, in part order."""
        return [s for p in self.parts for s in p.slots]

    @property
    def motors(self) -> int:
        return len(self.slots)

    @property
    def motor_neurons(self) -> int:
        return sum(self.slots)

    def wheels(self) -> list[int]:
        return [i for i, p in enumerate(self.parts) if p.kind == "wheel"]

    def legs(self) -> list[int]:
        return [i for i, p in enumerate(self.parts) if p.kind == "leg"]

    def arms(self) -> list[int]:
        return [i for i, p in enumerate(self.parts) if p.kind == "arm"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "chassis": self.chassis,
            "parts": [p.to_dict() for p in self.parts],
            "seed": self.seed,
            "genes": dict(self.genes),
            "policy": self.policy,
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(json.dumps(self.to_dict(), indent=1) + "\n")
        return path


def blueprint_from_dict(d: dict[str, Any]) -> Blueprint:
    parts = tuple(
        Part(kind=p["kind"], mount=float(p["mount"]), weapon=p.get("weapon")) for p in d["parts"]
    )
    return Blueprint(
        name=str(d["name"]),
        chassis=str(d["chassis"]),
        parts=parts,
        seed=int(d.get("seed", 0)),
        genes=dict(d.get("genes", {})),
        policy=str(d.get("policy", "brain")),
    )


def load_blueprint(path: str | Path) -> Blueprint:
    return blueprint_from_dict(json.loads(Path(path).read_text()))


def stock_designs() -> list[Blueprint]:
    """Eight robots that cover the catalogue: wheels and legs, two to six limbs, every weapon."""
    W, L, A = "wheel", "leg", "arm"
    return [
        Blueprint("Tumbler", "light", (Part(W, 90), Part(W, -90), Part(A, 0, "spike")), seed=11),
        Blueprint(
            "Mantis",
            "medium",
            (Part(L, 50), Part(L, -50), Part(L, 130), Part(L, -130), Part(A, 0, "hammer")),
            seed=12,
        ),
        Blueprint(
            "Hexapod",
            "heavy",
            (
                Part(L, 40), Part(L, -40), Part(L, 90), Part(L, -90), Part(L, 140), Part(L, -140),
                Part(A, 0, "spinner"),
            ),
            seed=13,
        ),
        Blueprint(
            "Cart",
            "medium",
            (Part(W, 100), Part(W, -100), Part(A, 25, "spike"), Part(A, -25, "spike")),
            seed=14,
        ),
        Blueprint(
            "Crab",
            "medium",
            (Part(L, 60), Part(L, -60), Part(L, 120), Part(L, -120), Part(A, 20, "hammer"),
             Part(A, -20, "spike")),
            seed=15,
        ),
        Blueprint(
            "Roller",
            "heavy",
            (Part(W, 60), Part(W, -60), Part(W, 120), Part(W, -120), Part(A, 0, "spinner")),
            seed=16,
        ),
        Blueprint(
            "Scorpion",
            "medium",
            (Part(L, 45), Part(L, -45), Part(L, 135), Part(L, -135), Part(A, 180, "spinner")),
            seed=17,
        ),
        Blueprint(
            "Dozer",
            "heavy",
            (Part(W, 70), Part(W, -70), Part(W, 110), Part(W, -110), Part(A, 15, "spike"),
             Part(A, -15, "spike"), Part(A, 0, "hammer")),
            seed=18,
        ),
    ]
