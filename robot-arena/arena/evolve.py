"""Evolution of bodies and genes, selected by the ring.

A population of robots lives in one league. Every generation, the newborns go through the
nursery, everyone fights a round of royales, and the robots are ranked by their mean
placement score in this generation's fights. The best keep their place, their record and
their one continuing brain; the rest retire, and their places are taken by offspring of the
survivors: a copy of a parent's blueprint with a few mutations of its body (a part moved,
added, removed or re-armed, a chassis changed) and of its genes (log-normal steps within
declared bounds), and a newborn brain of its own. A brain's learning is never inherited;
only the blueprint is. Lineages are named after their founder, so dominance over the
generations is a count: which lineage holds how many of the places, and the top rank.

Everything is recorded in the league's ``evolution`` list, one entry per generation, with
every robot's rank, score, Elo, lineage, parent and the mutations that made it.
"""

from __future__ import annotations

import math
import multiprocessing
import random
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from typing import Any

from .brain import FOUNDER
from .league import League
from .parts import CHASSIS, WEAPONS, Blueprint, Part, stock_designs

GENE_BOUNDS: dict[str, tuple[float, float]] = {
    "eta": (0.01, 1.0),
    "eta_critic": (0.3, 20.0),
    "lam": (0.0, 0.99),
    "trace_amplitude": (0.0, 3.0),
    "efference_amplitude": (0.0, 3.0),
    "sensory_scale": (0.5, 12.0),
    "temperature": (0.05, 0.5),
}
AROUSAL_BOUNDS: dict[str, tuple[float, float]] = {
    "need": (0.0, 0.5),
    "heat": (0.0, 4.0),
    "threshold": (0.02, 2.0),
    "decay": (0.0, 0.99),
    "youth": (0, 1000),
}


def _step(value: float, low: float, high: float, rng: random.Random, sigma: float = 0.35) -> float:
    if value <= 0.0:
        value = (high - low) * 0.05 + low  # leave zero by a small positive step
    return float(min(high, max(low, value * math.exp(rng.gauss(0.0, sigma)))))


def mutate(parent: Blueprint, name: str, seed: int, rng: random.Random, steps: int = 2) -> tuple[Blueprint, list[str]]:
    """``steps`` random mutations of the body or the genes; always a valid blueprint."""
    parts = list(parent.parts)
    chassis = parent.chassis
    genes: dict[str, Any] = {k: v for k, v in parent.genes.items() if k != "arousal"}
    arousal: dict[str, Any] = dict(parent.genes.get("arousal", {}))
    log: list[str] = []
    for _ in range(steps):
        kind = rng.choice(("move", "move", "weapon", "add", "remove", "chassis", "gene", "gene", "arousal"))
        if kind == "move" and parts:
            i = rng.randrange(len(parts))
            delta = rng.choice((-1, 1)) * rng.uniform(10.0, 45.0)
            mount = (parts[i].mount + delta + 180.0) % 360.0 - 180.0
            parts[i] = replace(parts[i], mount=round(mount, 1))
            log.append(f"moved {parts[i].kind} {i} to {mount:.0f} deg")
        elif kind == "weapon":
            arms = [i for i, p in enumerate(parts) if p.kind == "arm"]
            if arms:
                i = rng.choice(arms)
                weapon = rng.choice([w for w in WEAPONS if w != parts[i].weapon])
                parts[i] = replace(parts[i], weapon=weapon)
                log.append(f"re-armed arm {i} with a {weapon}")
            elif len(parts) < int(CHASSIS[chassis]["mounts"]):
                parts.append(Part("arm", round(rng.uniform(-60, 60), 1), rng.choice(WEAPONS)))
                log.append(f"added an arm with a {parts[-1].weapon}")
        elif kind == "add" and len(parts) < int(CHASSIS[chassis]["mounts"]):
            part_kind = rng.choice(("wheel", "leg", "leg", "arm"))
            weapon = rng.choice(WEAPONS) if part_kind == "arm" else None
            parts.append(Part(part_kind, round(rng.uniform(-180, 180), 1), weapon))
            log.append(f"added a {weapon or part_kind}")
        elif kind == "remove" and len(parts) > 2:
            i = rng.randrange(len(parts))
            drive = [p for j, p in enumerate(parts) if j != i and p.kind in ("wheel", "leg")]
            if drive:
                removed = parts.pop(i)
                log.append(f"removed {removed.weapon or removed.kind}")
        elif kind == "chassis":
            options = [c for c in CHASSIS if c != chassis and len(parts) <= int(CHASSIS[c]["mounts"])]
            if options:
                chassis = rng.choice(options)
                log.append(f"{chassis} chassis")
        elif kind == "gene":
            gene = rng.choice(list(GENE_BOUNDS))
            low, high = GENE_BOUNDS[gene]
            current = float(genes.get(gene, FOUNDER[gene]))
            genes[gene] = round(_step(current, low, high, rng), 4)
            log.append(f"{gene} {current:g} -> {genes[gene]:g}")
        elif kind == "arousal":
            gene = rng.choice(list(AROUSAL_BOUNDS))
            low, high = AROUSAL_BOUNDS[gene]
            current = float(arousal.get(gene, FOUNDER["arousal"][gene]))
            value = _step(current, low, high, rng)
            arousal[gene] = int(round(value)) if gene == "youth" else round(value, 4)
            log.append(f"arousal.{gene} {current:g} -> {arousal[gene]:g}")
    if arousal:
        genes["arousal"] = arousal
    child = Blueprint(name, chassis, tuple(parts), seed=seed, genes=genes, policy="brain")
    return child, log


def generation(
    league: League,
    *,
    population: int,
    elite: int,
    nursery_moments: int,
    fights: int,
    size: int,
    duration: int,
    zone_moments: int,
    workers: int,
    rng: random.Random,
    verbose: bool = False,
    rounds: int = 0,
    parallel: int = 0,
    inner_workers: int = 0,
    zone_end: float = 2.5,
    fitness: str = "placement",
    niche_min: int = 0,
    refresher_moments: int = 0,
    stage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = league.data
    data.setdefault("evolution", [])
    data.setdefault("retired", {})
    number = len(data["evolution"]) + 1
    names = league.names()
    began = time.perf_counter()
    # 1. newborns learn to move; survivors spar a while longer on the idle cores
    newborn = [n for n in names if data["robots"][n]["policy"] == "brain" and data["robots"][n]["nursery"] is None]
    veterans = [n for n in names if data["robots"][n]["policy"] == "brain" and data["robots"][n]["nursery"] is not None]
    if newborn:
        if verbose:
            print(f"generation {number}: nursery for {len(newborn)} newborns ({nursery_moments} moments each)"
                  + (f", refresher for {len(veterans)} veterans ({refresher_moments})" if refresher_moments and veterans else ""), flush=True)
        league.nursery(newborn, moments=nursery_moments, workers=workers, seed=number,
                       refresher=veterans if refresher_moments else None, refresher_moments=refresher_moments)
    # 2. fights; everyone fights about equally often
    fought_before = {n: data["robots"][n]["fights"] for n in names}
    if rounds:
        for k in range(rounds):
            rows = league.round(
                size=size, parallel=parallel, inner_workers=inner_workers, seed=number * 1000 + k,
                duration=duration, zone_moments=zone_moments, record=False, rng=rng, zone_end=zone_end,
                stage=stage,
            )
            if verbose:
                took = data["rounds"][-1]["seconds"]
                winners = ", ".join(r["results"][0]["name"] for r in rows[:6])
                print(f"  round {k + 1}/{rounds}: {len(rows)} fights in {took} s; winners {winners}"
                      f"{' ...' if len(rows) > 6 else ''}", flush=True)
    for k in range(0 if rounds else fights):
        order = sorted(names, key=lambda n: (data["robots"][n]["fights"], rng.random()))
        row = league.royale(order[:size], seed=number * 1000 + k, duration=duration,
                            zone_moments=zone_moments, zone_end=zone_end, stage=stage,
                            workers=min(size, workers) if size > 2 else 0, record=True, verbose=False)
        if verbose:
            top = row["results"][0]
            print(f"  fight {row['id']}: {top['name']} won ({row['moments']} moments, {row['seconds']} s)", flush=True)
    # 3. rank by this generation's mean placement score
    ranking = []
    for n in names:
        entry = data["robots"][n]
        rows = entry["history"][-(entry["fights"] - fought_before[n]):] if entry["fights"] > fought_before[n] else []
        score = sum(r["score"] for r in rows) / len(rows) if rows else -1.0
        dealt = sum(r["dealt"] for r in rows)
        ranking.append({"name": n, "score": round(score, 3), "fights": len(rows), "elo": entry["elo"],
                        "dealt": round(dealt, 1), "lineage": entry.get("lineage", n),
                        "generation_born": entry.get("generation", 0), "policy": entry["policy"],
                        "aroused": round(sum(r["aroused_share"] for r in rows) / len(rows), 3) if rows else None})
    if fitness == "licence":
        # the driving test of every brain's greedy policy, in parallel; placement breaks ties
        jobs = [(data["robots"][r["name"]]["blueprint"], str(league.brain_path(r["name"]))) for r in ranking if r["policy"] == "brain"]
        if workers > 1 and len(jobs) > 1:
            with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
                tests = list(pool.map(_licence_job, jobs))
        else:
            tests = [_licence_job(j) for j in jobs]
        by_name = {t["robot"]: t for t in tests}
        for r in ranking:
            t = by_name.get(r["name"])
            if t:
                r["licence"] = t["licence"]
                r["test"] = {k: t[k] for k in ("approach", "kills", "escape", "engage_dealt", "engage_taken", "spin")}
        ranking.sort(key=lambda r: (-(r.get("licence", -9.0)), -r["score"], -r["elo"]))
    else:
        ranking.sort(key=lambda r: (-r["score"], -r["elo"]))
    for k, r in enumerate(ranking):
        r["rank"] = k + 1
    # 4. selection: the elite stays (brains and all); the rest retire; offspring fill the places.
    # With a niche quota, the best ``niche_min`` of every lineage survive whatever the ranking.
    survivors = [r["name"] for r in ranking if r["policy"] == "brain"][:elite]
    if niche_min:
        protected: list[str] = []
        seen: dict[str, int] = {}
        for r in ranking:
            if r["policy"] != "brain":
                continue
            lineage = r["lineage"]
            if seen.get(lineage, 0) < niche_min:
                protected.append(r["name"])
                seen[lineage] = seen.get(lineage, 0) + 1
        rest = [r["name"] for r in ranking if r["policy"] == "brain" and r["name"] not in protected]
        survivors = (protected + rest)[:max(elite, len(protected))]
    baselines = [r["name"] for r in ranking if r["policy"] != "brain"]
    retired = [r["name"] for r in ranking if r["name"] not in survivors and r["name"] not in baselines]
    for n in retired:
        entry = data["robots"].pop(n)
        entry["retired_in"] = number
        data["retired"][n] = {k: v for k, v in entry.items() if k != "history"}
        path = league.brain_path(n)
        if path.exists():
            path.unlink()
    born: list[dict[str, Any]] = []
    slots_open = population - len(survivors) - len(baselines)
    for k in range(max(0, slots_open)):
        parent_name = rng.choice(survivors[: max(1, len(survivors))]) if survivors else None
        if parent_name is None:
            break
        parent = league.blueprint(parent_name)
        lineage = data["robots"][parent_name].get("lineage", parent_name)
        name = f"{lineage}-{number}.{k + 1}"
        while name in data["robots"] or name in data["retired"]:
            name += "x"
        child, log = mutate(parent, name, seed=rng.randrange(1_000_000), rng=rng)
        entry = league.add(child)
        entry["lineage"] = lineage
        entry["parent"] = parent_name
        entry["generation"] = number
        entry["mutations"] = log
        born.append({"name": name, "parent": parent_name, "lineage": lineage, "mutations": log,
                     "chassis": child.chassis, "parts": [p.to_dict() for p in child.parts]})
        if verbose:
            print(f"  born {name} from {parent_name}: {'; '.join(log) or 'a copy'}", flush=True)
    lineages: dict[str, int] = {}
    for n in league.names("brain"):
        lineage = data["robots"][n].get("lineage", n)
        lineages[lineage] = lineages.get(lineage, 0) + 1
    record = {
        "generation": number,
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seconds": round(time.perf_counter() - began, 1),
        "ranking": ranking,
        "survivors": survivors,
        "retired": retired,
        "born": born,
        "lineages": lineages,
    }
    data["evolution"].append(record)
    league.save()
    return record


def _licence_job(job: tuple) -> dict[str, Any]:
    from .licence import licence
    from .parts import blueprint_from_dict

    bp_dict, path = job
    return licence(blueprint_from_dict(bp_dict), path, "brain")


def seed_population(
    league: League, population: int, rng: random.Random, founders: list[str] | None = None
) -> list[str]:
    """Fill the league up to ``population`` brains with mutants: of the named founders (robots
    already in the league, which keep their lives and found their lineages) or of the stock
    designs."""
    if founders:
        parents = {n: league.blueprint(n) for n in founders}
    else:
        parents = {b.name: b for b in stock_designs()}
    for n in league.names("brain"):
        league.data["robots"][n].setdefault("lineage", n)
        league.data["robots"][n].setdefault("generation", 0)
    born = []
    k = 0
    while len(league.names("brain")) < population:
        parent_name = list(parents)[k % len(parents)]
        parent = parents[parent_name]
        name = f"{parent_name}-0{k // len(parents) + 1}"
        k += 1
        while name in league.data["robots"] or name in league.data.get("retired", {}):
            name += "x"
        child, log = mutate(parent, name, seed=rng.randrange(1_000_000), rng=rng, steps=rng.choice((1, 2)))
        entry = league.add(child)
        entry.update({"lineage": parent_name, "parent": parent_name, "generation": 0, "mutations": log})
        born.append(name)
    league.save()
    return born


def final_cut(league: League, keep: int, per_lineage: int = 0) -> list[str]:
    """Keep the ``keep`` best brains of the last generation's ranking, with the best
    ``per_lineage`` of every lineage kept first; retire the rest."""
    evolution = league.data.get("evolution", [])
    if not evolution:
        return []
    rows = [r for r in evolution[-1]["ranking"] if r["name"] in league.data["robots"]]
    survivors: list[str] = []
    if per_lineage:
        seen: dict[str, int] = {}
        for r in rows:
            if seen.get(r["lineage"], 0) < per_lineage:
                survivors.append(r["name"])
                seen[r["lineage"]] = seen.get(r["lineage"], 0) + 1
    for r in rows:
        if len(survivors) >= max(keep, len(survivors)):
            break
        if r["name"] not in survivors:
            survivors.append(r["name"])
    survivors = survivors[: max(keep, len([s for s in survivors]))] if keep >= len(survivors) else survivors[:max(keep, per_lineage * len({r["lineage"] for r in rows}))]
    gone = [n for n in league.data["robots"] if n not in survivors]
    return league.retire(gone, reason="final cut", delete_brains=True)
