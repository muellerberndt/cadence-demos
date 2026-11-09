"""The scripted scenarios that measure the page's promise, on fresh world seeds.

- ``controls``: each founder lives three times in one mortal world: as a learner, as its frozen
  twin (the same brain answering greedily, never learning) and beside a random walker. Lifespan
  and intake per moment.
- ``flip``: learners and their frozen twins live through a summer in a world where nobody dies;
  then the season turns to winter. Berries eaten (each a poisoning) per 100-moment bin after the
  turn, for learners and twins: the relearning curve.
- ``caches``: a brain with and one without a recall memory, raised on the same seed and genes,
  live in the same fresh world; nuts taken from the hidden caches per 1,000 moments.
- ``evolution``: a group of brains lives in a mortal world without births; lifespan, intake
  and the energy the brains cost. Run for the founders before and after evolution.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

import numpy as np

from .brain import FrozenMind, LiveMind, RandomMind
from .genes import SWEEP_COST, body_of, brain_cost
from .world import Rules, World


def live_world(seed: int, entries: list[dict[str, Any]], moments: int, rules: Rules,
               flip_at: int | list[int] | None = None, on_moment: Callable | None = None,
               start_summer: bool = True) -> list[dict[str, Any]]:
    """Run one world with the given creatures (``{"label", "genes", "mind"}``); return each
    one's record. Nobody is born; the dead stay dead."""
    world = World(seed, rules)
    if not start_summer:
        world.flip_season()
    rows = []
    for e in entries:
        c = world.add_creature(body_of(e["genes"]), kind=e["mind"].kind)
        c.brain_cost = brain_cost(e["genes"]) if e["mind"].kind != "random" else 0.0
        c.learn_cost = SWEEP_COST if e["mind"].kind == "live" else 0.0
        rows.append({"label": e["label"], "id": c.id, "mind": e["mind"], "reward": None,
                     "income": 0.0, "died": None, "cause": "", "sweeps": 0,
                     "berry_bins": {}, "poison_bins": {}, "over_bins": {}})
    by_id = {r["id"]: r for r in rows}
    flips = set([flip_at] if isinstance(flip_at, int) else (flip_at or []))
    for t in range(moments):
        if t in flips:
            world.flip_season()
        living = [r for r in rows if r["died"] is None]
        if not living:
            break
        obs = world.observe([r["id"] for r in living])
        actions, sweeps = {}, {}
        for k, r in enumerate(living):
            out = r["mind"].moment(obs[k], r["reward"])
            actions[r["id"]], sweeps[r["id"]] = out["action"], out["learning_sweeps"]
            r["sweeps"] += out["learning_sweeps"]
        before = {r["id"]: world.creatures[r["id"]].stats["over_berry"] for r in living}
        res = world.step(actions, sweeps)
        for cid, o in res.items():
            r = by_id.get(cid)
            if r is None:
                continue
            r["reward"] = o["reward"]
            if o["reward"] > 0:
                r["income"] += o["reward"]
            b = t // 100
            if "poisoned" in o["events"]:
                r["poison_bins"][b] = r["poison_bins"].get(b, 0) + 1
            if "berry" in o["events"]:
                r["berry_bins"][b] = r["berry_bins"].get(b, 0) + 1
            if world.creatures[cid].stats["over_berry"] > before.get(cid, 0):
                r["over_bins"][b] = r["over_bins"].get(b, 0) + 1
            if o["done"]:
                r["died"], r["cause"] = t + 1, world.creatures[cid].cause
        if on_moment is not None:
            on_moment(world, t)
    out = []
    for r in rows:
        c = world.creatures[r["id"]]
        age = r["died"] if r["died"] is not None else moments
        out.append({"label": r["label"], "kind": r["mind"].kind, "age": age,
                    "died": r["died"] is not None, "cause": r["cause"],
                    "income_per_moment": r["income"] / max(age, 1),
                    "learning_sweeps": r["sweeps"],
                    "stats": {k: int(v) for k, v in c.stats.items()},
                    "poison_bins": r["poison_bins"], "berry_bins": r["berry_bins"],
                    "over_bins": r["over_bins"], "refusals": r["mind"].refusals})
    return out


def clone(brain: Any) -> Any:
    return copy.deepcopy(brain)


def controls(seed: int, founders: list[dict[str, Any]], moments: int = 6000,
             retune: dict[str, Any] | None = None) -> list[dict]:
    """Each founder as a learner, its frozen twin and a random walker, in one mortal world.
    ``retune`` (named settings) is applied to the learners only: an experiment's lever."""
    entries = []
    for i, f in enumerate(founders):
        brain = clone(f["brain"])
        if retune:
            brain.retune(**retune)
        entries.append({"label": f"{f['name']}:live", "genes": f["genes"],
                        "mind": LiveMind(brain)})
        entries.append({"label": f"{f['name']}:frozen", "genes": f["genes"],
                        "mind": FrozenMind(clone(f["brain"]))})
        entries.append({"label": f"random{i}", "genes": f["genes"],
                        "mind": RandomMind(seed * 100 + i)})
    return live_world(seed, entries, moments, Rules())


def flip(seed: int, founders: list[dict[str, Any]], summer: int = 1000,
         winter: int = 1500, retune: dict[str, Any] | None = None) -> list[dict]:
    """Learners and frozen twins through a summer, then the turn to winter; nobody dies.
    ``retune`` (named settings) is applied to the learners only: an experiment's lever."""
    entries = []
    for f in founders:
        brain = clone(f["brain"])
        if retune:
            brain.retune(**retune)
        entries.append({"label": f"{f['name']}:live", "genes": f["genes"],
                        "mind": LiveMind(brain)})
        entries.append({"label": f"{f['name']}:frozen", "genes": f["genes"],
                        "mind": FrozenMind(clone(f["brain"]))})
    rules = Rules(immortal=True, predators=0, season=summer + winter + 1)
    return live_world(seed, entries, summer + winter, rules, flip_at=summer)


def seasons(seed: int, founders: list[dict[str, Any]], lengths: tuple[int, ...] = (1000, 1500, 1500, 1500)
            ) -> list[dict]:
    """Learners and frozen twins through summer, winter, summer, winter (``lengths``); nobody
    dies, no predators. Is a learner's second winter easier than its first?"""
    entries = []
    for f in founders:
        entries.append({"label": f"{f['name']}:live", "genes": f["genes"],
                        "mind": LiveMind(clone(f["brain"]))})
        entries.append({"label": f"{f['name']}:frozen", "genes": f["genes"],
                        "mind": FrozenMind(clone(f["brain"]))})
    total = sum(lengths)
    flips = list(np.cumsum(lengths)[:-1])
    rules = Rules(immortal=True, predators=0, season=total + 1)
    return live_world(seed, entries, total, rules, flip_at=[int(x) for x in flips])


def caches(seed: int, pairs: list[dict[str, Any]], moments: int = 3000) -> list[dict]:
    """Recall on and off, same genes and raising seed, in one immortal world."""
    entries = []
    for p in pairs:
        for side in ("off", "on"):
            entries.append({"label": f"{p['name']}:{side}", "genes": p[side]["genes"],
                            "mind": LiveMind(clone(p[side]["brain"]))})
    return live_world(seed, entries, moments, Rules(immortal=True))


def evolution(seed: int, group: list[dict[str, Any]], moments: int = 6000,
              retune: dict[str, Any] | None = None) -> list[dict]:
    """A group of learners in a mortal world without births. ``retune`` (named settings) is
    applied to every brain of the group, as the evolution applied the founders' genes."""
    entries = []
    for f in group:
        brain = clone(f["brain"])
        if retune:
            brain.retune(**retune)
        entries.append({"label": f["name"], "genes": f["genes"], "mind": LiveMind(brain)})
    return live_world(seed, entries, moments, Rules())


def competition(seed: int, before: list[dict[str, Any]], after: list[dict[str, Any]],
                moments: int = 12000, before_genes: dict[str, Any] | None = None,
                cap: int = 16, every: int = 1000) -> dict[str, Any]:
    """The generation-0 founders and the evolved founders in one mortal world with births, as
    the islands ran: whose descendants hold the population? ``before_genes`` are set on the
    generation-0 founders as the evolution set them."""
    from .ecosystem import Ecosystem, LocalMinds

    group = ([{"genes": {**f["genes"], **(before_genes or {})}, "lineage": i, "side": "before"}
              for i, f in enumerate(before)]
             + [{"genes": f["genes"], "lineage": len(before) + i, "side": "after"}
                for i, f in enumerate(after)])
    brains = [f["brain"] for f in before] + [f["brain"] for f in after]
    eco = Ecosystem(seed, Rules(), founders=group, cap=cap, frozen=0, random=0, floor=0)
    minds = LocalMinds([clone(b) for b in brains], seed=seed)
    minds.born(eco.populate())
    side = {i: g["side"] for i, g in enumerate(group)}
    curve = []
    for t in range(moments):
        changes = eco.advance(minds.answer(eco.requests()))
        minds.died(changes["deaths"])
        minds.born(changes["births"])
        if (t + 1) % every == 0 or t + 1 == moments or not eco.learners():
            ls = eco.learners()
            curve.append({"t": t + 1, "before": sum(1 for lf in ls if side[lf.lineage] == "before"),
                          "after": sum(1 for lf in ls if side[lf.lineage] == "after")})
            if not ls:
                break
    births = {"before": 0, "after": 0}
    for rec in eco.dead + [lf.summary() for lf in eco.lives.values()]:
        if rec["generation"] > 0:
            births[side[rec["lineage"]]] += 1
    return {"curve": curve, "births": births}


def mean(xs: list[float]) -> float:
    return float(np.mean(xs)) if xs else float("nan")


def bootstrap_ci(xs: list[float], seed: int = 0, n: int = 2000) -> list[float]:
    if not xs:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    a = np.asarray(xs, dtype=float)
    means = a[rng.integers(len(a), size=(n, len(a)))].mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]
