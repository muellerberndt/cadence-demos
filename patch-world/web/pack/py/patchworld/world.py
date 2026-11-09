"""The world of Patch World: a torus of ground, water, plants and hidden caches under a day and
a season, with predators.

Everything here is NumPy and seeded, so the same world runs on the laptop, on a training box
and in the browser (Pyodide). One call to ``step`` is one moment: every creature's action is
executed, the plants grow, the predators move, and each creature receives the outcome of its
action as a reward together with its next observation.

The season is not in the senses. A berry nourishes in summer and sickens in winter, and
nothing a creature sees says which season it is: the only way to know is to have eaten a berry
recently, so a policy that does not learn within its life cannot follow the season.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

# cell contents (food layer)
NONE, BERRY, ROOT, LEAF = 0, 1, 2, 3
FOOD_NAMES = ("none", "berry", "root", "leaf")
# terrain
GROUND, WATER, BUSH, MEADOW = 0, 1, 2, 3

ACTIONS = ("north", "east", "south", "west", "eat", "drink")
MOVES = ((0, -1), (1, 0), (0, 1), (-1, 0))
N_ACTIONS = len(ACTIONS)

# sensed kinds per direction
DIR_KINDS = ("berry", "root", "leaf", "water", "predator", "creature")
DIRECTIONS = ("north", "east", "south", "west")


def input_names() -> list[str]:
    names = [f"{d}:{k}" for d in DIRECTIONS for k in DIR_KINDS]
    names += ["here:berry", "here:root", "here:leaf", "here:cache", "here:water"]
    names += ["energy", "thirst", "light", "nausea", "cold"]
    names += ["place:x-sin", "place:x-cos", "place:y-sin", "place:y-cos"]
    return names


N_INPUTS = len(input_names())


@dataclass
class Rules:
    """The world's constants. Every value is declared here and saved with a run."""

    width: int = 48
    height: int = 32
    day: int = 240  # moments in a day; the second half is night
    season: int = 1500  # moments in a season; summer and winter alternate
    berry_summer: float = 5.0  # energy of a berry in summer
    berry_winter: float = -6.0  # energy of a berry in winter (poison)
    sick_moments: int = 20  # a poisoned creature burns extra energy for this long
    sick_burn: float = 0.15
    root: float = 2.5
    leaf: float = 0.8
    nut: float = 6.0  # one nut from a cache
    berry_regrow: float = 0.02  # chance per empty bush cell per moment
    leaf_regrow: float = 0.004  # per empty meadow cell
    root_regrow: float = 0.00015  # per empty ground cell
    cache_count: int = 4
    cache_capacity: int = 3
    cache_refill: int = 120  # one nut back per this many moments
    thirst_rate: float = 1.0 / 200.0  # thirst gained per moment
    drink_value: float = 2.0  # reward per unit of thirst quenched
    dry_burn: float = 0.05  # extra burn per moment at full thirst
    metabolism: float = 0.005  # base burn per moment
    wasted_act: float = 0.1  # cost of eating or drinking with nothing there
    predators: int = 1
    predator_sense: int = 7
    predator_bite: float = 7.0
    predator_rest: int = 40  # moments a predator rests after a bite
    predator_pace: int = 2  # a predator moves every this many moments
    max_age: int = 8000
    nausea_sense: bool = True  # a poisoned creature feels sick while it lasts
    temperature_sense: bool = True  # it feels the cold; the air turns slowly after the season
    temperature_lag: float = 250.0  # moments for the air to cover two thirds of a turn
    immortal: bool = False  # the nursery: energy never falls below 1, no old age


@dataclass
class Body:
    """What a creature's genes build besides its brain."""

    sense: int = 4  # cells it senses in daylight; half at night
    speed: int = 1  # cells per move
    size: float = 1.0  # energy store and armour; burns with size

    def capacity(self) -> float:
        return 20.0 * self.size

    def burn(self) -> float:
        # sensing, moving and carrying a body cost energy every moment
        return 0.003 * self.sense + 0.02 * (self.speed - 1) + 0.03 * (self.size - 1.0)


@dataclass
class Creature:
    id: int
    x: int
    y: int
    body: Body
    energy: float
    brain_cost: float = 0.0  # energy per moment the brain costs (set by the brain's owner)
    learn_cost: float = 0.0  # energy per learning sweep (charged by the owner)
    thirst: float = 0.0
    sick: int = 0
    age: int = 0
    kind: str = "live"  # live, frozen or random: what drives it
    lineage: int = 0
    generation: int = 0
    alive: bool = True
    cause: str = ""
    last_food: str = ""
    stats: dict[str, float] = field(default_factory=dict)


def _stats() -> dict[str, float]:
    return {k: 0.0 for k in (
        "berry_summer", "berry_winter", "poisoned", "root", "leaf", "nut", "drink", "bitten",
        "eaten", "gained", "wasted", "refused_berry", "over_berry", "moves")}


class World:
    def __init__(self, seed: int = 0, rules: Rules | None = None) -> None:
        self.rules = rules or Rules()
        self.seed = int(seed)
        self.rng = np.random.default_rng(seed)
        self._sense_rng = np.random.default_rng(seed + 1)
        r = self.rules
        self.t = 0
        self.season_flips = 0  # visitor flips shift the season phase
        self._season_offset = 0
        self.terrain = np.zeros((r.height, r.width), dtype=np.int8)
        self.food = np.zeros((r.height, r.width), dtype=np.int8)
        self._make_terrain()
        self.cache_pos = self._place_caches()
        self.cache_nuts = np.full(len(self.cache_pos), r.cache_capacity, dtype=np.int32)
        self.creatures: dict[int, Creature] = {}
        self.predators: list[dict[str, int]] = []
        for _ in range(r.predators):
            self.add_predator()
        self.next_id = 1
        self.temperature = 1.0  # 1 summer air, 0 winter air
        self._offsets: dict[int, tuple[np.ndarray, ...]] = {}
        # seed the plants at their steady state
        for _ in range(400):
            self._grow()

    # -- construction

    def _blob(self, cx: float, cy: float, rx: float, ry: float) -> np.ndarray:
        r = self.rules
        ys, xs = np.mgrid[0:r.height, 0:r.width]
        dx = (xs - cx + r.width / 2) % r.width - r.width / 2
        dy = (ys - cy + r.height / 2) % r.height - r.height / 2
        noise = self.rng.normal(0, 0.18, size=xs.shape)
        return (dx / rx) ** 2 + (dy / ry) ** 2 + noise < 1.0

    def _make_terrain(self) -> None:
        r = self.rules
        rng = self.rng
        area = r.width * r.height / (48 * 32)
        for _ in range(max(1, round(3 * area))):  # ponds
            self.terrain[self._blob(rng.uniform(0, r.width), rng.uniform(0, r.height),
                                    rng.uniform(2.0, 3.5), rng.uniform(1.5, 3.0))] = WATER
        for _ in range(max(1, round(5 * area))):  # meadows
            m = self._blob(rng.uniform(0, r.width), rng.uniform(0, r.height),
                           rng.uniform(3, 6), rng.uniform(3, 5)) & (self.terrain == GROUND)
            self.terrain[m] = MEADOW
        for _ in range(max(1, round(6 * area))):  # berry thickets
            b = self._blob(rng.uniform(0, r.width), rng.uniform(0, r.height),
                           rng.uniform(1.5, 2.8), rng.uniform(1.5, 2.5)) & (self.terrain != WATER)
            self.terrain[b] = BUSH

    def _place_caches(self) -> np.ndarray:
        r = self.rules
        spots = np.argwhere(self.terrain == GROUND)
        pick = self.rng.choice(len(spots), size=r.cache_count, replace=False)
        return spots[pick][:, ::-1].astype(np.int32)  # (x, y)

    def free_cell(self) -> tuple[int, int]:
        r = self.rules
        while True:
            x, y = int(self.rng.integers(r.width)), int(self.rng.integers(r.height))
            if self.terrain[y, x] != WATER:
                return x, y

    def add_creature(self, body: Body, kind: str = "live", energy: float | None = None,
                     at: tuple[int, int] | None = None, lineage: int = 0,
                     generation: int = 0, cid: int | None = None) -> Creature:
        x, y = at if at is not None else self.free_cell()
        cid = self.next_id if cid is None else int(cid)
        self.next_id = max(self.next_id, cid + 1)
        c = Creature(cid, x, y, body, body.capacity() * 0.5 if energy is None else float(energy),
                     kind=kind, lineage=lineage, generation=generation, stats=_stats())
        self.creatures[cid] = c
        return c

    def add_predator(self, at: tuple[int, int] | None = None) -> None:
        x, y = at if at is not None else self.free_cell()
        self.predators.append({"x": x, "y": y, "rest": 60, "target": -1})

    def remove_predator(self) -> None:
        if self.predators:
            self.predators.pop()

    # -- time

    @property
    def summer(self) -> bool:
        r = self.rules
        return ((self.t + self._season_offset) // r.season) % 2 == 0

    @property
    def light(self) -> float:
        r = self.rules
        phase = (self.t % r.day) / r.day
        return 1.0 if phase < 0.5 else 0.0

    def season_progress(self) -> float:
        r = self.rules
        return ((self.t + self._season_offset) % r.season) / r.season

    def flip_season(self) -> None:
        """Turn the season now (the visitor's control, and the scenario's)."""
        r = self.rules
        into = (self.t + self._season_offset) % r.season
        self._season_offset += r.season - into
        self.season_flips += 1

    def drop_food(self, x: int, y: int, kind: int, radius: int = 1) -> int:
        r = self.rules
        n = 0
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                xx, yy = (x + dx) % r.width, (y + dy) % r.height
                if self.terrain[yy, xx] != WATER and self.food[yy, xx] == NONE:
                    self.food[yy, xx] = kind
                    n += 1
        return n

    def _grow(self) -> None:
        r = self.rules
        empty = self.food == NONE
        u = self.rng.random(self.food.shape)
        self.food[empty & (self.terrain == BUSH) & (u < r.berry_regrow)] = BERRY
        self.food[empty & (self.terrain == MEADOW) & (u < r.leaf_regrow)] = LEAF
        self.food[empty & (self.terrain == GROUND) & (u < r.root_regrow)] = ROOT
        if self.t % r.cache_refill == 0:
            self.cache_nuts = np.minimum(self.cache_nuts + 1, r.cache_capacity)

    # -- senses

    def _ring(self, radius: int) -> tuple[np.ndarray, ...]:
        """Offsets within ``radius`` (Chebyshev), their closeness and their quadrant masks."""
        if radius not in self._offsets:
            d = np.arange(-radius, radius + 1)
            dx, dy = np.meshgrid(d, d)
            dx, dy = dx.ravel(), dy.ravel()
            keep = (dx != 0) | (dy != 0)
            dx, dy = dx[keep], dy[keep]
            dist = np.maximum(np.abs(dx), np.abs(dy)).astype(float)
            close = 1.0 - (dist - 1.0) / radius  # 1 adjacent, 1/radius at the edge
            north = (dy < 0) & (np.abs(dx) <= -dy)
            south = (dy > 0) & (np.abs(dx) <= dy)
            east = (dx > 0) & (np.abs(dy) < dx)
            west = (dx < 0) & (np.abs(dy) < -dx)
            quads = np.stack([north, east, south, west])  # (4, k)
            self._offsets[radius] = (dx, dy, close, quads)
        return self._offsets[radius]

    def observe(self, ids: list[int]) -> np.ndarray:
        """One observation row per creature, in the order of ``ids``."""
        r = self.rules
        out = np.zeros((len(ids), N_INPUTS))
        if not ids:
            return out
        light = self.light
        others = np.array([[c.x, c.y] for c in self.creatures.values() if c.alive] or
                          np.zeros((0, 2)), dtype=np.int64)
        animal = np.zeros(self.food.shape, dtype=bool)
        if len(others):
            animal[others[:, 1], others[:, 0]] = True
        hunter = np.zeros(self.food.shape, dtype=bool)
        for p in self.predators:
            hunter[p["y"], p["x"]] = True
        water = self.terrain == WATER
        noise = self._sense_rng.normal(0.0, 0.05, size=len(ids))
        for row, cid in enumerate(ids):
            c = self.creatures[cid]
            radius = c.body.sense if light > 0 else max(1, c.body.sense // 2)
            dx, dy, close, quads = self._ring(radius)
            xs, ys = (c.x + dx) % r.width, (c.y + dy) % r.height
            food = self.food[ys, xs]
            layers = (food == BERRY, food == ROOT, food == LEAF, water[ys, xs],
                      hunter[ys, xs], animal[ys, xs])
            for k, mask in enumerate(layers):
                w = np.where(mask, close, 0.0)  # (k,)
                out[row, k:4 * 6:6] = (quads * w).max(axis=1)
            here = self.food[c.y, c.x]
            base = 24
            out[row, base + 0] = here == BERRY
            out[row, base + 1] = here == ROOT
            out[row, base + 2] = here == LEAF
            out[row, base + 3] = self._cache_at(c.x, c.y) >= 0
            out[row, base + 4] = self._by_water(c.x, c.y)
            out[row, 29] = c.energy / c.body.capacity()
            out[row, 30] = c.thirst
            out[row, 31] = light
            if r.nausea_sense:
                out[row, 32] = c.sick / r.sick_moments
            if r.temperature_sense:
                out[row, 33] = min(1.0, max(0.0, 1.0 - self.temperature + noise[row]))
            ax, ay = 2 * np.pi * c.x / r.width, 2 * np.pi * c.y / r.height
            out[row, 34:38] = 0.5 + 0.5 * np.array([np.sin(ax), np.cos(ax), np.sin(ay), np.cos(ay)])
        return out

    def _cache_at(self, x: int, y: int) -> int:
        hit = np.nonzero((self.cache_pos[:, 0] == x) & (self.cache_pos[:, 1] == y))[0]
        return int(hit[0]) if len(hit) else -1

    def _by_water(self, x: int, y: int) -> bool:
        r = self.rules
        for mx, my in MOVES:
            if self.terrain[(y + my) % r.height, (x + mx) % r.width] == WATER:
                return True
        return False

    # -- one moment

    def step(self, actions: dict[int, int], learning_sweeps: dict[int, int] | None = None
             ) -> dict[int, dict[str, Any]]:
        """Execute every living creature's action; return each one's outcome.

        The outcome holds ``reward`` (the energy and water its action brought, the poison and
        bites it took), ``done`` (it died this moment) and ``events``."""
        r = self.rules
        sweeps = learning_sweeps or {}
        out: dict[int, dict[str, Any]] = {}
        order = [cid for cid in actions if cid in self.creatures and self.creatures[cid].alive]
        self.rng.shuffle(order)
        summer = self.summer
        for cid in order:
            c = self.creatures[cid]
            a = int(actions[cid])
            reward, events = 0.0, []
            here = int(self.food[c.y, c.x])
            if a < 4:
                mx, my = MOVES[a]
                for _ in range(c.body.speed):
                    nx, ny = (c.x + mx) % r.width, (c.y + my) % r.height
                    if self.terrain[ny, nx] == WATER:
                        break
                    c.x, c.y = nx, ny
                c.stats["moves"] += 1
                if here == BERRY:
                    c.stats["over_berry"] += 1
                    c.stats["refused_berry"] += 1
                    events.append("passed")
            elif a == 4:  # eat
                k = self._cache_at(c.x, c.y)
                if k >= 0 and self.cache_nuts[k] > 0:
                    self.cache_nuts[k] -= 1
                    gain = r.nut
                    c.stats["nut"] += 1
                    events.append("nut")
                    c.last_food = "nut"
                elif here == BERRY:
                    c.stats["over_berry"] += 1
                    gain = r.berry_summer if summer else r.berry_winter
                    self.food[c.y, c.x] = NONE
                    c.last_food = "berry"
                    if summer:
                        c.stats["berry_summer"] += 1
                        events.append("berry")
                    else:
                        c.stats["berry_winter"] += 1
                        c.stats["poisoned"] += 1
                        c.sick = r.sick_moments
                        events.append("poisoned")
                elif here == ROOT:
                    gain = r.root
                    self.food[c.y, c.x] = NONE
                    c.stats["root"] += 1
                    events.append("root")
                    c.last_food = "root"
                elif here == LEAF:
                    gain = r.leaf
                    self.food[c.y, c.x] = NONE
                    c.stats["leaf"] += 1
                    events.append("leaf")
                    c.last_food = "leaf"
                else:
                    gain = -r.wasted_act
                    c.stats["wasted"] += 1
                if gain > 0:
                    c.stats["eaten"] += 1
                c.energy += gain
                reward += gain
            else:  # drink
                if self._by_water(c.x, c.y):
                    quench = c.thirst
                    c.thirst = 0.0
                    reward += r.drink_value * quench
                    c.stats["drink"] += 1
                    if quench > 0.05:
                        events.append("drink")
                else:
                    c.energy -= r.wasted_act
                    reward -= r.wasted_act
                    c.stats["wasted"] += 1
            if reward > 0:
                c.stats["gained"] += reward
            out[cid] = {"reward": reward, "done": False, "events": events}
        # the predators hunt
        for p in self.predators:
            if p["rest"] > 0:
                p["rest"] -= 1
                continue
            prey = self._nearest_prey(p)
            if prey is not None and abs(prey.x - p["x"]) + abs(prey.y - p["y"]) == 0:
                bite = r.predator_bite / prey.body.size
                prey.energy -= bite
                prey.stats["bitten"] += 1
                if prey.id in out:
                    out[prey.id]["reward"] -= bite
                    out[prey.id]["events"].append("bitten")
                p["rest"] = r.predator_rest
                continue
            if self.t % r.predator_pace:
                continue
            if prey is not None:
                dx = (prey.x - p["x"] + r.width // 2) % r.width - r.width // 2
                dy = (prey.y - p["y"] + r.height // 2) % r.height - r.height // 2
                if abs(dx) >= abs(dy) and dx:
                    step = (int(np.sign(dx)), 0)
                else:
                    step = (0, int(np.sign(dy)))
            else:
                step = MOVES[int(self.rng.integers(4))]
            nx, ny = (p["x"] + step[0]) % r.width, (p["y"] + step[1]) % r.height
            if self.terrain[ny, nx] != WATER:
                p["x"], p["y"] = nx, ny
            p["target"] = -1 if prey is None else prey.id
        # bodies burn, thirst grows
        for cid, c in self.creatures.items():
            if not c.alive:
                continue
            burn = r.metabolism + c.body.burn() + c.brain_cost
            burn += c.learn_cost * sweeps.get(cid, 0)
            burn += r.dry_burn * c.thirst
            if c.sick > 0:
                burn += r.sick_burn
                c.sick -= 1
            c.energy = min(c.energy - burn, c.body.capacity())
            c.thirst = min(1.0, c.thirst + r.thirst_rate)
            c.age += 1
            if r.immortal:
                c.energy = max(c.energy, 1.0)
            elif c.energy <= 0 or c.age >= r.max_age:
                c.alive = False
                c.cause = "starved" if c.energy <= 0 else "old age"
                if cid in out:
                    out[cid]["done"] = True
                else:
                    out[cid] = {"reward": 0.0, "done": True, "events": []}
                out[cid]["events"].append("died")
        self.t += 1
        self.temperature += ((1.0 if self.summer else 0.0) - self.temperature) / r.temperature_lag
        self._grow()
        return out

    def _nearest_prey(self, p: dict[str, int]) -> Creature | None:
        r = self.rules
        best, best_d = None, r.predator_sense + 1
        for c in self.creatures.values():
            if not c.alive:
                continue
            dx = abs((c.x - p["x"] + r.width // 2) % r.width - r.width // 2)
            dy = abs((c.y - p["y"] + r.height // 2) % r.height - r.height // 2)
            d = max(dx, dy)
            if d < best_d:
                best, best_d = c, d
        return best

    def remove(self, cid: int) -> None:
        self.creatures.pop(cid, None)

    # -- the page's view

    def snapshot(self) -> dict[str, Any]:
        return {
            "t": self.t,
            "summer": bool(self.summer),
            "season_progress": round(self.season_progress(), 4),
            "light": self.light,
            "temperature": round(self.temperature, 3),
            "day_progress": (self.t % self.rules.day) / self.rules.day,
            "food": self.food.tobytes().hex(),
            "caches": [[int(x), int(y), int(n)] for (x, y), n in zip(self.cache_pos, self.cache_nuts)],
            "predators": [[p["x"], p["y"], int(p["rest"] > 0)] for p in self.predators],
            "creatures": [
                {"id": c.id, "x": c.x, "y": c.y, "energy": round(c.energy, 2),
                 "capacity": c.body.capacity(), "thirst": round(c.thirst, 3), "sick": c.sick,
                 "kind": c.kind, "age": c.age, "lineage": c.lineage, "generation": c.generation,
                 "size": c.body.size, "sense": c.body.sense, "speed": c.body.speed}
                for c in self.creatures.values() if c.alive
            ],
        }

    def terrain_bytes(self) -> str:
        return self.terrain.tobytes().hex()
