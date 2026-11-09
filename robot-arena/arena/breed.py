"""Breeding against a fixed reference pool: bodies and brain genes, selected by fights and the
driving test.

    python -m arena.breed --league breed --reference league-live --generations 20 --workers 90

Every generation the newborns go through the nursery; then every robot of the population
fights royales of six in which a few candidates meet anchors drawn from the reference pool
(the shipped roster's brains and uniform-random twins). An anchor is the same brain file in
every fight: it fights and learns inside the fight, and its learning is thrown away
afterwards, so the yardstick does not move. A candidate keeps its one continuing brain
through every fight of its life. Each brain then takes the driving test. Fitness:

    mean placement score against the pool (-1 to +1) + LICENCE_WEIGHT * driving test
    + DAMAGE_WEIGHT * min(1, damage dealt per fight / DAMAGE_FULL)
    - COST_WEIGHT * (the layout's measured cost per moment / the founder's - 1, above zero)

The elite (with ``--niche``, the best of every lineage first) keep their brains and their lives; offspring of the elite (body and gene mutations,
including the brain's layout, the recall memory and the teaching point) are born with newborn
brains. A brain's learning is never inherited. Each generation is appended to the league's
``breeding`` list with every robot's readings.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import random
import shutil
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import evolve
from .brain import FOUNDER, PAGE_STAGE
from .league import League
from .parts import Blueprint, blueprint_from_dict, stock_designs
from .royale import Fighter, run_royale

# Layouts a gene may take, with their cost per moment in plain NumPy (the page's path, Pyodide)
# relative to the founder's (48, 24), measured on the Hexapod body (the most motors and inputs):
# every one runs within twice the founder's cost.
LAYOUTS: dict[tuple[int, ...], float] = {
    (48, 24): 1.0, (64,): 0.48, (128,): 0.59, (64, 32): 0.74, (96, 48): 0.85,
    (128, 64): 1.09, (256, 128): 1.41,
}
RECALL_COST = 1.36  # (128, 64) with the recall memory against without it
TEACHING = (None, "deep", "normalized")
LICENCE_WEIGHT = 1.0
DAMAGE_WEIGHT = 0.25  # times min(1, damage dealt per fight / DAMAGE_FULL): a survivor that never fights earns no part
DAMAGE_FULL = 200.0
COST_WEIGHT = 0.2
EXTRA_BOUNDS = {"eta_bias": (0.0002, 0.1)}


def cost(genes: dict[str, Any]) -> float:
    layout = tuple(int(w) for w in genes.get("modules", FOUNDER["modules"]))
    base = LAYOUTS.get(layout, 2.0)
    return base * (RECALL_COST if genes.get("recall") else 1.0)


def mutate(parent: Blueprint, name: str, seed: int, rng: random.Random, steps: int = 2) -> tuple[Blueprint, list[str]]:
    """The arena's body and gene mutations, plus the 0.95 brain genes: the layout, the recall
    memory, the teaching point and the actor's bias rate."""
    bounds = dict(evolve.GENE_BOUNDS)
    evolve.GENE_BOUNDS = {**bounds, "eta": (0.002, 1.0), **EXTRA_BOUNDS}
    try:
        child, log = evolve.mutate(parent, name, seed=seed, rng=rng, steps=steps)
    finally:
        evolve.GENE_BOUNDS = bounds
    genes = dict(child.genes)
    if rng.random() < 0.5:
        kind = rng.choice(("modules", "modules", "recall", "teaching"))
        if kind == "modules":
            current = tuple(genes.get("modules", FOUNDER["modules"]))
            layout = rng.choice([lay for lay in LAYOUTS if lay != current])
            genes["modules"] = list(layout)
            log.append(f"layout {list(current)} -> {list(layout)}")
        elif kind == "recall":
            genes["recall"] = not bool(genes.get("recall", FOUNDER["recall"]))
            log.append(f"recall {'on' if genes['recall'] else 'off'}")
        else:
            current = genes.get("teaching", FOUNDER["teaching"])
            genes["teaching"] = rng.choice([t for t in TEACHING if t != current])
            log.append(f"teaching {current} -> {genes['teaching']}")
    return replace(child, genes=genes), log


def _pool_fight(job: tuple) -> dict[str, Any]:
    """One royale of candidates (brains saved in place) and anchors (fresh copies, discarded)."""
    candidates, anchors, seed, duration, zone_moments, zone_end, stage = job
    with tempfile.TemporaryDirectory() as tmp:
        fighters = []
        for c in candidates:
            fighters.append(Fighter(name=c["name"], blueprint=blueprint_from_dict(c["blueprint"]), policy="brain",
                                    brain_path=Path(c["brain_path"]),
                                    owed=None if c["owed"] is None else (float(c["owed"][0]), bool(c["owed"][1])),
                                    stage=stage))
        for a in anchors:
            path = None
            if a["policy"] == "brain":
                path = Path(tmp) / f"{a['name']}.npz"
                shutil.copy(a["brain_path"], path)
            fighters.append(Fighter(name=a["name"], blueprint=blueprint_from_dict(a["blueprint"]), policy=a["policy"],
                                    brain_path=path,
                                    owed=None if a["owed"] is None else (float(a["owed"][0]), bool(a["owed"][1])),
                                    stage=stage))
        began = time.perf_counter()
        outcome = run_royale(fighters, seed=seed, duration=duration, zone_moments=zone_moments, zone_end=zone_end,
                             workers=0, record=False, save=True)
    return {"stats": {f.name: f.stats for f in fighters}, "owed": {f.name: f.owed for f in fighters},
            "moments": outcome["moments"], "seconds": round(time.perf_counter() - began, 1)}


def reference_pool(path: Path, names: list[str] | None = None) -> list[dict[str, Any]]:
    """The anchors: the reference league's robots (``names``, or all), brain files read in place
    (never written)."""
    ref = json.loads((path / "league.json").read_text())
    pool = []
    for name, e in ref["robots"].items():
        if names and name not in names:
            continue
        pool.append({"name": f"ref:{name}", "blueprint": e["blueprint"], "policy": e["policy"],
                     "brain_path": str(path / "brains" / f"{name}.npz") if e["policy"] == "brain" else None,
                     "owed": e.get("owed")})
    return pool


def generation(league: League, pool: list[dict[str, Any]], *, population: int, elite: int, nursery_moments: int,
               fights_each: int, per_fight: int, workers: int, rng: random.Random, duration: int, zone_moments: int,
               zone_end: float, stage: dict[str, Any], niche: int = 0, refresher_moments: int = 0,
               verbose: bool = True) -> dict[str, Any]:
    data = league.data
    data.setdefault("breeding", [])
    data.setdefault("retired", {})
    number = len(data["breeding"]) + 1
    began = time.perf_counter()
    names = league.names("brain")
    newborn = [n for n in names if data["robots"][n]["nursery"] is None]
    veterans = [n for n in names if n not in newborn] if refresher_moments else []
    if newborn:  # (an empty list would mean every brain to League.nursery)
        if verbose:
            print(f"generation {number}: nursery for {len(newborn)} newborns ({nursery_moments} moments)"
                  + (f", refresher for {len(veterans)} veterans ({refresher_moments})" if veterans else ""), flush=True)
        league.nursery(newborn, moments=nursery_moments, workers=workers, seed=number,
                       refresher=veterans or None, refresher_moments=refresher_moments)
    nursery_s = time.perf_counter() - began
    # fights: every candidate meets the pool fights_each times, per_fight candidates a fight
    slots: list[str] = []
    for _ in range(fights_each):
        order = names[:]
        rng.shuffle(order)
        slots += order
    jobs = []
    for k in range(0, len(slots), per_fight):
        group = list(dict.fromkeys(slots[k:k + per_fight]))
        cands = [{"name": n, "blueprint": data["robots"][n]["blueprint"], "brain_path": str(league.brain_path(n)),
                  "owed": data["robots"][n].get("owed")} for n in group]
        anchors = rng.sample(pool, 6 - len(cands))
        jobs.append((cands, anchors, number * 100_000 + k, duration, zone_moments, zone_end, stage))
    # a robot fights one fight at a time: run the jobs in waves without repeated names
    waves: list[list[tuple]] = []
    for job in jobs:
        for wave in waves:
            if not ({c["name"] for c in job[0]} & {c["name"] for j in wave for c in j[0]}):
                wave.append(job)
                break
        else:
            waves.append([job])
    fight_began = time.perf_counter()
    rows: dict[str, list[dict[str, Any]]] = {n: [] for n in names}
    anchor_rows: dict[str, list[float]] = {}
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as ex:
        for wave in waves:
            # owed outcomes must be current at submission: rebuild candidates' owed per wave
            wave = [([{**c, "owed": data["robots"][c["name"]].get("owed")} for c in j[0]], *j[1:]) for j in wave]
            for job, out in zip(wave, ex.map(_pool_fight, wave), strict=True):
                for c in job[0]:
                    st = out["stats"][c["name"]]
                    entry = data["robots"][c["name"]]
                    entry["fights"] += 1
                    entry["wins"] += int(st["place"] == 1)
                    entry["places"].append(int(st["place"]))
                    entry["dealt"] += st["dealt"]
                    entry["taken"] += st["taken"]
                    entry["moments"] += st["moments"]
                    o = out["owed"][c["name"]]
                    entry["owed"] = None if o is None else [float(o[0]), bool(o[1])]
                    entry["history"].append({"generation": number, **st})
                    rows[c["name"]].append(st)
                for a in job[1]:
                    anchor_rows.setdefault(a["name"], []).append(out["stats"][a["name"]]["score"])
    fight_s = time.perf_counter() - fight_began
    # the driving test of every brain
    tests = {}
    tests_jobs = [(data["robots"][n]["blueprint"], str(league.brain_path(n))) for n in names]
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as ex:
        for n, t in zip(names, ex.map(evolve._licence_job, tests_jobs), strict=True):
            tests[n] = t
    ranking = []
    for n in names:
        r = rows[n]
        genes = blueprint_from_dict(data["robots"][n]["blueprint"]).genes
        score = sum(x["score"] for x in r) / len(r) if r else -1.0
        lic = float(tests[n]["licence"])
        c = cost({**FOUNDER, **genes})
        dealt = sum(x["dealt"] for x in r) / max(1, len(r))
        fit = (score + LICENCE_WEIGHT * lic + DAMAGE_WEIGHT * min(1.0, dealt / DAMAGE_FULL)
               - COST_WEIGHT * max(0.0, c - 1.0))
        ranking.append({"name": n, "fitness": round(fit, 4), "score": round(score, 3), "licence": round(lic, 3),
                        "passes": int(tests[n]["passes"]), "cost": round(c, 2), "fights": len(r),
                        "dealt": round(sum(x["dealt"] for x in r) / max(1, len(r)), 1),
                        "aroused": round(sum(x["aroused_share"] for x in r) / max(1, len(r)), 3),
                        "ms": round(sum(x["ms_per_moment"] for x in r) / max(1, len(r)), 2),
                        "lineage": data["robots"][n].get("lineage", n), "born": data["robots"][n].get("generation", 0),
                        "layout": list(genes.get("modules", FOUNDER["modules"])), "recall": bool(genes.get("recall", False)),
                        "teaching": genes.get("teaching"), "eta": genes.get("eta", FOUNDER["eta"])})
        data["robots"][n]["licence"] = {"licence": round(lic, 3), "passes": int(tests[n]["passes"]),
                                        "marks": "".join("+" if v else "-" for v in tests[n]["passed"].values())}
        data["robots"][n]["fitness"] = round(fit, 4)
    ranking.sort(key=lambda r: -r["fitness"])
    # the best ``niche`` of every lineage survive whatever the ranking; the rest of the elite by rank
    protected: list[str] = []
    seen: dict[str, int] = {}
    for r in ranking:
        if seen.get(r["lineage"], 0) < niche:
            protected.append(r["name"])
            seen[r["lineage"]] = seen.get(r["lineage"], 0) + 1
    survivors = protected + [r["name"] for r in ranking if r["name"] not in protected][: max(0, elite - len(protected))]
    survivors.sort(key=lambda n: next(k for k, r in enumerate(ranking) if r["name"] == n))
    retired = [r["name"] for r in ranking if r["name"] not in survivors]
    for n in retired:
        entry = data["robots"].pop(n)
        entry["retired_in"] = number
        data["retired"][n] = {k: v for k, v in entry.items() if k != "history"}
        path = league.brain_path(n)
        if path.exists():
            path.unlink()
    born = []
    weights = [1.0 / (k + 1) for k in range(len(survivors))]
    # every lineage's protected survivors have one child each first, then parents by rank
    leaders = [n for n in survivors if n in protected]
    for k in range(population - len(survivors)):
        parent_name = leaders[k] if k < len(leaders) else rng.choices(survivors, weights=weights)[0]
        parent = league.blueprint(parent_name)
        lineage = data["robots"][parent_name].get("lineage", parent_name)
        name = f"{lineage.split('-')[0]}-{number}.{k + 1}"
        while name in data["robots"] or name in data["retired"]:
            name += "x"
        child, log = mutate(parent, name, seed=rng.randrange(1_000_000), rng=rng)
        entry = league.add(child)
        entry.update({"lineage": lineage, "parent": parent_name, "generation": number, "mutations": log})
        born.append({"name": name, "parent": parent_name, "mutations": log})
    anchors = {a: round(sum(v) / len(v), 3) for a, v in sorted(anchor_rows.items())}
    record = {"generation": number, "when": time.strftime("%Y-%m-%d %H:%M:%S"),
              "seconds": {"total": round(time.perf_counter() - began, 1), "nursery": round(nursery_s, 1),
                          "fights": round(fight_s, 1)},
              "fights": len(jobs), "ranking": ranking, "survivors": survivors, "born": born, "anchors": anchors}
    data["breeding"].append(record)
    league.save()
    if verbose:
        top = ranking[:8]
        print(f"generation {number} in {record['seconds']['total']:.0f} s (nursery {nursery_s:.0f}, fights {fight_s:.0f}, "
              f"{len(jobs)} fights); anchors {anchors}", flush=True)
        for r in top:
            print(f"  {r['name']:16s} fit {r['fitness']:+.3f} score {r['score']:+.2f} licence {r['licence']:+.2f} "
                  f"({r['passes']}/8) layout {r['layout']} recall {int(r['recall'])} teaching {r['teaching']} "
                  f"eta {r['eta']:g} dealt {r['dealt']:.0f} ms {r['ms']:.1f}", flush=True)
    return record


def seed(league: League, population: int, rng: random.Random) -> None:
    """The stock bodies with the founder genes (the control) and mutants of them."""
    stock = stock_designs()
    designs = list(stock)
    k = 0
    while len(designs) < population:
        parent = stock[k % len(stock)]
        child, log = mutate(parent, f"{parent.name}-0.{k + 1}", seed=rng.randrange(1_000_000), rng=rng,
                            steps=rng.choice((1, 2)))
        designs.append(child)
        k += 1
    league.create(designs)
    for b in designs:
        e = league.data["robots"][b.name]
        e.update({"lineage": b.name.split("-")[0], "parent": b.name.split("-")[0], "generation": 0})
    league.save()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--league", required=True)
    p.add_argument("--reference", required=True, help="the league whose robots are the anchors")
    p.add_argument("--anchors", help="comma-separated names of the reference league's anchors (default: all)")
    p.add_argument("--generations", type=int, default=10)
    p.add_argument("--population", type=int, default=64)
    p.add_argument("--elite", type=int, default=16)
    p.add_argument("--nursery-moments", type=int, default=80_000)
    p.add_argument("--fights-each", type=int, default=6)
    p.add_argument("--per-fight", type=int, default=2, help="candidates per royale of six")
    p.add_argument("--duration", type=int, default=2400)
    p.add_argument("--zone-moments", type=int, default=2000)
    p.add_argument("--zone-end", type=float, default=3.5)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--hours", type=float, default=0.0, help="start no generation after this many hours")
    p.add_argument("--niche", type=int, default=0, help="the best N of every lineage survive each generation")
    p.add_argument("--refresher-moments", type=int, default=0,
                   help="more nursery for every surviving brain while the newborns are raised")
    a = p.parse_args(argv)
    rng = random.Random(a.seed)
    league = League(a.league)
    if not league.path.exists():
        seed(league, a.population, rng)
    else:  # resume: the league's own generations continue
        rng = random.Random(a.seed + len(league.data.get("breeding", [])))
    pool = reference_pool(Path(a.reference), a.anchors.split(",") if a.anchors else None)
    print(f"anchors: {', '.join(x['name'] for x in pool)}", flush=True)
    began = time.time()
    for _ in range(a.generations):
        if a.hours and time.time() - began > a.hours * 3600:
            print("time budget reached", flush=True)
            break
        generation(league, pool, population=a.population, elite=a.elite, nursery_moments=a.nursery_moments,
                   fights_each=a.fights_each, per_fight=a.per_fight, workers=a.workers, rng=rng,
                   duration=a.duration, zone_moments=a.zone_moments, zone_end=a.zone_end, stage=dict(PAGE_STAGE),
                   niche=a.niche, refresher_moments=a.refresher_moments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
