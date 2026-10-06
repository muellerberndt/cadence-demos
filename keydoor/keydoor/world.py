"""The key-door corridor, as the frozen protocol of Cadence's ``benchmarks/keydoor`` defines it.

One trip is a corridor of ``LENGTH`` cells met in order: empty floor, a chest, a lamp, ``D``
levers (``D`` varying by ``JITTER`` from trip to trip) and a door. At every cell the creature
passes or interacts. The key sits in the chest under rule A and in the lamp under rule B.
Interacting at the door with the key pays ``FOOD_REWARD`` and ends the trip; interacting with
the chest, the lamp or a lever when it holds no key costs ``COST``; the floor has nothing to
interact with; taking the key pays nothing by itself. One trip in twenty is cut short before
the door at a random cell, the key lost with it. The creature sees the one-hot kind of the
cell it faces and, through the pouch sense, whether it holds the key.

The constants here are the frozen protocol's (`protocol.json`, schema ``key-door/1``); the
test ``tests/test_world.py`` compares this module against the chamber's own code when a
Cadence checkout is at hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

PASS, INTERACT = 0, 1
FLOOR, CHEST, LAMP, LEVER, DOOR = range(5)
KINDS = ("floor", "chest", "lamp", "lever", "door")
LENGTH = 14
JITTER = 1
COST = 0.25
FOOD_REWARD = 1.0
FOOD = 1.0  # the chance that the door pays, given the key
TRUNCATION = 0.05  # the share of trips cut before the door
CORRIDOR_SEED = 2000  # the chamber's; a seed's corridors are ``default_rng(CORRIDOR_SEED + seed)``
LUCK_OFFSET = 7919


def corridor(delay: int, length: int, jitter: int, rng: np.random.Generator) -> list[int]:
    """The cells of one trip: floor, chest, lamp, the levers and the door, ``length`` in all."""
    levers = max(0, delay + (int(rng.integers(-jitter, jitter + 1)) if jitter else 0))
    floors = max(0, length - 3 - levers)
    return [*([FLOOR] * floors), CHEST, LAMP, *([LEVER] * levers), DOOR]


def observe(kind: int, holding: bool) -> np.ndarray:
    x = np.zeros((1, 6))
    x[0, kind] = 1.0
    x[0, 5] = float(holding)
    return x


@dataclass
class Trip:
    """One trip in progress."""

    cells: list[int]
    cut: bool
    index: int = 0
    holding: bool = False
    got: int = 0
    took: int = 0
    wrongs: int = 0
    log: list[dict] = field(default_factory=list)

    @property
    def kind(self) -> int:
        return self.cells[self.index]

    @property
    def over(self) -> bool:
        return self.index >= len(self.cells)


class World:
    """The corridor world of one creature: trips, outcomes and the exactly-once delivery of
    the preceding action's outcome with the next observation.

    ``keyed`` names the cell that holds the key; ``move_key`` moves it between the chest and
    the lamp; ``cut_next`` ends the current trip before the door at the next cell (``done``
    clear), as the world does by chance one trip in twenty.
    """

    def __init__(self, delay: int, seed: int, *, keyed: int = CHEST, truncation: float = TRUNCATION,
                 food: float = FOOD, cost: float = COST) -> None:
        self.delay = int(delay)
        self.keyed = int(keyed)
        self.truncation = float(truncation)
        self.food = float(food)
        self.cost = float(cost)
        self.cells_rng = np.random.default_rng(CORRIDOR_SEED + seed)
        self.luck = np.random.default_rng(CORRIDOR_SEED + LUCK_OFFSET + seed)
        self.pending: tuple[float, bool] | None = None  # the preceding action's outcome
        self.trip: Trip | None = None
        self.trips = 0  # trips begun
        self.fed: list[int] = []  # per trip that reached the door
        self.wrong: list[int] = []
        self.took: list[int] = []
        self.cuts = 0
        self.force_cut = False

    def move_key(self) -> int:
        self.keyed = LAMP if self.keyed == CHEST else CHEST
        return self.keyed

    def cut_next(self) -> None:
        self.force_cut = True

    def begin(self) -> Trip:
        cells = corridor(self.delay, LENGTH, JITTER, self.cells_rng)
        cut = bool(self.luck.random() < self.truncation)
        if cut:
            cells = cells[: int(self.luck.integers(1, len(cells) - 1))]
        self.trip = Trip(cells, cut)
        self.trips += 1
        return self.trip

    def face(self) -> tuple[int, bool]:
        """The cell faced now and the pouch; begins a trip when none is in progress."""
        if self.trip is None or self.trip.over:
            self.begin()
        assert self.trip is not None
        return self.trip.kind, self.trip.holding

    def act(self, action: int) -> dict:
        """Apply the action at the faced cell; the outcome becomes the pending feedback that
        the next observation delivers. Returns what happened at this cell."""
        trip = self.trip
        assert trip is not None and not trip.over
        kind, holding = trip.kind, trip.holding
        outcome = 0.0
        event = "pass"
        if action == INTERACT:
            if kind == self.keyed and not holding:
                trip.holding, trip.took, event = True, 1, "key"
            elif kind == DOOR:
                if holding and self.luck.random() < self.food:
                    outcome, trip.got, event = FOOD_REWARD, 1, "food"
                else:
                    outcome, event = -self.cost, "wrong"
                    trip.wrongs += 1
            elif kind != FLOOR:
                outcome, event = -self.cost, "wrong"
                trip.wrongs += 1
            else:
                event = "nothing"
        if self.force_cut and kind != DOOR:
            trip.cut = True
            trip.cells = trip.cells[: trip.index + 1]
            self.force_cut = False
        last = trip.index == len(trip.cells) - 1
        done = last and not trip.cut
        self.pending = (outcome, done)
        record = {
            "trip": self.trips,
            "index": trip.index,
            "kind": kind,
            "holding": holding,
            "action": int(action),
            "event": event,
            "outcome": outcome,
            "done": done,
            "cut": bool(trip.cut and last),
            "holding_after": trip.holding,
        }
        trip.index += 1
        if last:
            if trip.cut:
                self.cuts += 1
            else:
                self.fed.append(trip.got)
                self.wrong.append(trip.wrongs)
                self.took.append(trip.took)
        return record

    def feedback(self) -> tuple[float | None, bool]:
        """The outcome to deliver with the next observation, once."""
        if self.pending is None:
            return None, False
        reward, done = self.pending
        self.pending = None
        return reward, done

    def recent(self, n: int = 20) -> dict:
        fed = self.fed[-n:]
        return {
            "fed": float(np.mean(fed)) if fed else 0.0,
            "wrong": float(np.mean(self.wrong[-n:])) if self.wrong else 0.0,
            "took": float(np.mean(self.took[-n:])) if self.took else 0.0,
            "trips": len(self.fed),
            "cuts": self.cuts,
        }
