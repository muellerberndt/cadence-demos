"""The living population: births, deaths, inheritance and the controls, around one world.

The ecosystem keeps the world and every creature's genes and life record; it does not hold the
brains. Each moment it asks for one action per living creature (``requests``) and executes
them (``advance``). Whoever holds the brains answers: ``LocalMinds`` in one process for the
training runs and the scenario tests, the page's brain workers in the browser. The same code
decides births, deaths and inheritance in both.

A creature whose stored energy passes its ``birth`` gene's share of its capacity bears one
child, while the living learners are fewer than ``cap``: the child takes half the energy,
mutated genes, and a copy of its parent's brain as it is at that moment (what the parent has
learned is inherited; the child's own rates and arousal are its genes). A ``recall`` gene
switched on by mutation grows a recall memory onto the inherited brain
(``brain.grow(recall=True)``). Anatomy (width and depth) is inherited unchanged.

The controls live in the same world and do not bear young: frozen twins (a founder's brain
answering greedily, never learning) and random walkers. A dead control is replaced by a new one
of its kind, so the page always shows both beside the learners.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .genes import SWEEP_COST, body_of, brain_cost, mutate
from .world import Rules, World


@dataclass
class Life:
    id: int
    kind: str
    genes: dict[str, Any]
    lineage: int
    generation: int
    parent: int | None
    born: int
    founder: int | None = None  # the founder whose brain it carries (controls, reseeds)
    died: int | None = None
    cause: str = ""
    income: float = 0.0  # energy and water its actions brought
    expense: float = 0.0  # poison, bites, and everything it burned
    children: int = 0
    stats: dict[str, float] = field(default_factory=dict)
    poison_times: list[int] = field(default_factory=list)  # moments of its life it was poisoned
    berry_times: list[int] = field(default_factory=list)  # moments it ate a good berry

    def summary(self) -> dict[str, Any]:
        age = (self.died if self.died is not None else self.born) - self.born
        return {"id": self.id, "kind": self.kind, "lineage": self.lineage,
                "generation": self.generation, "born": self.born, "died": self.died,
                "age": age, "cause": self.cause, "income": round(self.income, 2),
                "expense": round(self.expense, 2), "children": self.children,
                "stats": {k: round(v, 2) for k, v in self.stats.items()},
                "poisonings": len(self.poison_times)}


class Ecosystem:
    def __init__(self, seed: int = 0, rules: Rules | None = None, founders: list[dict] | None = None,
                 cap: int = 12, frozen: int = 2, random: int = 2, floor: int = 3,
                 mutation: float = 0.25, structures: list[str] | None = None,
                 births: bool = True) -> None:
        self.world = World(seed, rules)
        self.rng = np.random.default_rng(seed + 7919)
        self.founders = founders or []  # [{"genes": {...}, "lineage": int}]
        self.cap = cap
        self.controls = {"frozen": frozen, "random": random}
        self.floor = floor
        self.mutation = mutation
        self.structures = structures
        self.births_on = births
        self.lives: dict[int, Life] = {}
        self.dead: list[dict[str, Any]] = []
        self.pending: dict[int, tuple[float, bool]] = {}
        self.reseeded = 0
        self.events: list[dict[str, Any]] = []  # births, deaths, poisonings of the last moment

    # -- population

    def spawn(self, genes: dict[str, Any], kind: str = "live", parent: int | None = None,
              energy: float | None = None, at: tuple[int, int] | None = None,
              lineage: int = 0, generation: int = 0, founder: int | None = None) -> dict:
        c = self.world.add_creature(body_of(genes), kind=kind, energy=energy, at=at,
                                    lineage=lineage, generation=generation)
        c.brain_cost = brain_cost(genes) if kind != "random" else 0.0
        c.learn_cost = SWEEP_COST if kind == "live" else 0.0
        self.lives[c.id] = Life(c.id, kind, copy.deepcopy(genes), lineage, generation, parent,
                                self.world.t, founder=founder)
        self.pending[c.id] = (0.0, False)
        return {"id": c.id, "kind": kind, "genes": copy.deepcopy(genes), "parent": parent,
                "founder": founder, "lineage": lineage, "generation": generation}

    def populate(self, count: int | None = None) -> list[dict]:
        """The opening population: the founders as learners, then the controls."""
        born = []
        n = len(self.founders) if count is None else count
        for i in range(n):
            f = self.founders[i % len(self.founders)]
            born.append(self.spawn(f["genes"], "live", lineage=f.get("lineage", i), founder=i))
        born += self._refill_controls()
        return born

    def _refill_controls(self) -> list[dict]:
        born = []
        for kind, want in self.controls.items():
            have = sum(1 for lf in self.lives.values() if lf.kind == kind and lf.died is None)
            for _ in range(want - have):
                i = int(self.rng.integers(len(self.founders))) if self.founders else 0
                f = self.founders[i] if self.founders else {"genes": {}}
                genes = copy.deepcopy(f["genes"])
                born.append(self.spawn(genes, kind, lineage=-1, founder=i))
        return born

    def learners(self) -> list[Life]:
        return [lf for lf in self.lives.values() if lf.kind == "live" and lf.died is None]

    # -- one moment

    def requests(self) -> list[dict[str, Any]]:
        """One request per living creature: its observation and the outcome of its last
        action (``reward`` None on its first moment)."""
        ids = [cid for cid, lf in self.lives.items() if lf.died is None]
        obs = self.world.observe(ids)
        out = []
        for row, cid in enumerate(ids):
            reward, _ = self.pending.get(cid, (0.0, False))
            first = self.lives[cid].born == self.world.t
            out.append({"id": cid, "obs": obs[row], "reward": None if first else reward,
                        "kind": self.lives[cid].kind})
        return out

    def advance(self, replies: dict[int, dict[str, Any]]) -> dict[str, list]:
        """Execute the actions; return the births, deaths and events of the moment."""
        w = self.world
        actions = {cid: int(r["action"]) for cid, r in replies.items()}
        sweeps = {cid: int(r.get("learning_sweeps", 0)) for cid, r in replies.items()}
        before = {cid: w.creatures[cid].energy for cid in actions if cid in w.creatures}
        outcome = w.step(actions, sweeps)
        births: list[dict] = []
        deaths: list[dict] = []
        events: list[dict] = []
        for cid, res in outcome.items():
            lf = self.lives.get(cid)
            if lf is None:
                continue
            c = w.creatures[cid]
            reward = float(res["reward"])
            self.pending[cid] = (reward, bool(res["done"]))
            if reward > 0:
                lf.income += reward
            # everything else the body lost this moment
            lf.expense += max(0.0, before.get(cid, c.energy) + max(reward, 0.0) - c.energy)
            for e in res["events"]:
                if e == "poisoned":
                    lf.poison_times.append(c.age)
                    events.append({"id": cid, "event": e, "kind": lf.kind})
                elif e == "berry":
                    lf.berry_times.append(c.age)
                    events.append({"id": cid, "event": e, "kind": lf.kind})
                elif e in ("bitten", "nut", "passed"):
                    events.append({"id": cid, "event": e, "kind": lf.kind})
            if res["done"]:
                lf.died, lf.cause = w.t, c.cause
                lf.stats = dict(c.stats)
                rec = lf.summary()
                self.dead.append(rec)
                deaths.append({"id": cid, "kind": lf.kind, "cause": c.cause, "age": c.age})
                w.remove(cid)
                self.pending.pop(cid, None)
        if self.births_on:
            living = self.learners()
            room = self.cap - len(living)
            for lf in sorted(living, key=lambda x: -w.creatures[x.id].energy):
                if room <= 0:
                    break
                c = w.creatures[lf.id]
                if c.energy >= float(lf.genes["birth"]) * c.body.capacity():
                    child_genes = mutate(lf.genes, self.rng, rate=self.mutation, structural=0.0)
                    if not lf.genes["recall"] and self.rng.random() < self.mutation * 0.1:
                        child_genes["recall"] = True  # grown onto the inherited brain
                    share = c.energy / 2
                    c.energy -= share
                    lf.children += 1
                    births.append(self.spawn(child_genes, "live", parent=lf.id, energy=share,
                                             at=(c.x, c.y), lineage=lf.lineage,
                                             generation=lf.generation + 1))
                    room -= 1
            if len(self.learners()) < self.floor and self.founders:
                # the population died out: founders come back (counted on the page)
                for _ in range(self.floor - len(self.learners())):
                    i = int(self.rng.integers(len(self.founders)))
                    f = self.founders[i]
                    births.append(self.spawn(f["genes"], "live", lineage=f.get("lineage", i),
                                             founder=i))
                    self.reseeded += 1
        births += self._refill_controls()
        for lf in self.lives.values():
            if lf.died is None and lf.id in w.creatures:
                lf.stats = dict(w.creatures[lf.id].stats)
        # forget the records of the long dead, keep their summaries
        for cid in [cid for cid, lf in self.lives.items() if lf.died is not None]:
            self.lives.pop(cid)
        self.events = events
        return {"births": births, "deaths": deaths, "events": events}

    # -- readings

    def tally(self, since: int = 0) -> dict[str, Any]:
        """Per kind of mind: lives ended, mean age at death, poisonings and berries per 1,000
        moments lived, income per moment."""
        rows: dict[str, dict[str, float]] = {}
        everyone = list(self.dead) + [lf.summary() | {"age": self.world.t - lf.born}
                                      for lf in self.lives.values() if lf.died is None]
        for rec in everyone:
            if rec["died"] is not None and rec["died"] < since:
                continue
            k = rows.setdefault(rec["kind"], {"lives": 0, "ended": 0, "age_at_death": 0.0,
                                              "moments": 0, "poisoned": 0, "berries": 0,
                                              "winter_berries": 0, "income": 0.0})
            k["lives"] += 1
            k["moments"] += rec["age"]
            k["poisoned"] += rec["stats"].get("poisoned", 0)
            k["berries"] += rec["stats"].get("berry_summer", 0)
            k["income"] += rec["income"]
            if rec["died"] is not None:
                k["ended"] += 1
                k["age_at_death"] += rec["age"]
        out = {}
        for kind, k in rows.items():
            m = max(k["moments"], 1)
            out[kind] = {"lives": k["lives"], "ended": k["ended"],
                         "mean_age_at_death": round(k["age_at_death"] / k["ended"], 1) if k["ended"] else None,
                         "poisonings_per_1000": round(1000 * k["poisoned"] / m, 3),
                         "good_berries_per_1000": round(1000 * k["berries"] / m, 3),
                         "income_per_moment": round(k["income"] / m, 4)}
        return out


class LocalMinds:
    """Every brain in this process: the training runs' and the scenario tests' mind holder."""

    def __init__(self, founder_brains: list[Any] | None = None, seed: int = 0) -> None:
        from .brain import FrozenMind, LiveMind, RandomMind, compose, retune

        self._kinds = (FrozenMind, LiveMind, RandomMind)
        self._compose, self._retune = compose, retune
        self.founder_brains = founder_brains or []
        self.minds: dict[int, Any] = {}
        self.seed = seed
        self.ms = 0.0

    def brain_for(self, birth: dict) -> Any:
        """The brain a newborn starts from: its parent's copy, a founder's copy or new."""
        if birth.get("parent") is not None and birth["parent"] in self.minds:
            brain = copy.deepcopy(self.minds[birth["parent"]].brain)
            if birth["genes"]["recall"] and brain.recall is None:
                brain = brain.grow(recall=True)
            self._retune(brain, birth["genes"])
            return brain
        f = birth.get("founder")
        if f is not None and f < len(self.founder_brains) and self.founder_brains[f] is not None:
            brain = copy.deepcopy(self.founder_brains[f])
            if birth["kind"] == "live":
                self._retune(brain, birth["genes"])
            return brain
        return self._compose(birth["genes"], seed=self.seed + birth["id"])

    def born(self, births: list[dict]) -> None:
        FrozenMind, LiveMind, RandomMind = self._kinds
        for b in births:
            if b["kind"] == "random":
                self.minds[b["id"]] = RandomMind(self.seed + b["id"])
            elif b["kind"] == "frozen":
                self.minds[b["id"]] = FrozenMind(self.brain_for(b))
            else:
                self.minds[b["id"]] = LiveMind(self.brain_for(b))

    def died(self, deaths: list[dict]) -> None:
        for d in deaths:
            self.minds.pop(d["id"], None)

    def answer(self, requests: list[dict]) -> dict[int, dict]:
        out = {}
        for r in requests:
            mind = self.minds[r["id"]]
            out[r["id"]] = mind.moment(r["obs"], r["reward"])
        return out


def run(eco: Ecosystem, minds: LocalMinds, moments: int, every: int = 0,
        report=None) -> None:
    """Live ``moments`` moments; call ``report(eco, minds)`` every ``every`` moments."""
    for t in range(moments):
        replies = minds.answer(eco.requests())
        changes = eco.advance(replies)
        minds.died(changes["deaths"])
        minds.born(changes["births"])
        if every and report is not None and (t + 1) % every == 0:
            report(eco, minds)
