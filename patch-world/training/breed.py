"""Breed the founders: a nursery that raises brains, then evolution in the mortal world.

    python training/breed.py nursery --worlds 8 --moments 20000 --out runs/nursery
    python training/breed.py evolve --nursery runs/nursery --islands 6 --moments 40000 --out runs/evolve
    python training/breed.py select --evolve runs/evolve --nursery runs/nursery --out runs/founders

**Nursery.** Each world holds eight creatures that cannot die (energy never falls below one),
four gene sets each twice, once with a recall memory and once without, on the same brain seed.
They live ``--moments`` moments through summers and winters, learning from what their actions
bring. Every creature's brain, genes and curve (per 1,000 moments: income, nuts, poisonings,
good berries, drinks) are saved.

**Evolution.** Each island is one mortal world (``Ecosystem``) started from the nursery's best
brains as founders, with births: a creature that stores enough energy bears a child that takes
a copy of its brain and mutated genes. After ``--moments`` moments every living learner is
saved with its genes and lineage.

**Select.** The founders the page opens with: the evolved learners ranked by their island
income per moment, at most two per lineage, and the generation-0 founders kept beside them for
the evolution reading (``evaluate.py evolution``).
"""

from __future__ import annotations

import os

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
              "VECLIB_MAXIMUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

import argparse  # noqa: E402
import copy  # noqa: E402
import json  # noqa: E402
import multiprocessing as mp  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from patchworld.brain import load  # noqa: E402
from patchworld.ecosystem import Ecosystem, LocalMinds, run  # noqa: E402
from patchworld.genes import FOUNDER, brain_cost, mutate, structure  # noqa: E402
from patchworld.world import Rules  # noqa: E402

KEYS = ("berry_summer", "berry_winter", "poisoned", "root", "leaf", "nut", "drink", "bitten",
        "wasted", "gained", "moves")


def nursery_genes(world: int, rng: np.random.Generator) -> list[dict]:
    """Four gene sets for one nursery world, each with recall off and on."""
    out = []
    widths = (16, 24, 32, 48)
    for k in range(4):
        g = copy.deepcopy(FOUNDER)
        if world > 0 or k > 0:  # the first set of the first world is the founder itself
            g = mutate(g, rng, rate=0.6, structural=0.0)
        g["width"] = widths[(world + k) % 4]
        g["depth"] = 1 + (world // 2 + k) % 2
        for recall in (False, True):
            out.append({**g, "recall": recall})
    return out


def nursery_world(args: tuple) -> dict:
    index, moments, seed, out, rules = args
    rng = np.random.default_rng(seed * 1000 + index)
    genes = nursery_genes(index, rng)
    founders = [{"genes": g, "lineage": index * 100 + i} for i, g in enumerate(genes)]
    eco = Ecosystem(seed * 1000 + index, Rules(**{**rules, "immortal": True}), founders=founders,
                    cap=len(founders), frozen=0, random=0, births=False)
    minds = LocalMinds(seed=seed * 1000 + index)
    births = eco.populate()
    # each pair (recall off/on) starts from the same brain seed
    for b in births:
        from patchworld.brain import LiveMind, compose

        pair_seed = seed * 1000 + index * 10 + (b["founder"] // 2)
        minds.minds[b["id"]] = LiveMind(compose(b["genes"], seed=pair_seed))
    ids = [b["id"] for b in births]
    curves: dict[int, list[dict]] = {i: [] for i in ids}
    last = {i: {k: 0.0 for k in KEYS} for i in ids}
    began = time.time()

    def report(eco: Ecosystem, minds: LocalMinds) -> None:
        for cid in ids:
            lf = eco.lives[cid]
            row = {k: lf.stats.get(k, 0.0) - last[cid][k] for k in KEYS}
            last[cid] = {k: lf.stats.get(k, 0.0) for k in KEYS}
            m = minds.minds[cid]
            row["t"] = eco.world.t
            row["aroused"] = int(m.brain.arousal.moments.get("aroused", 0))
            row["refusals"] = m.refusals
            curves[cid].append(row)

    run(eco, minds, moments, every=1000, report=report)
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for k, cid in enumerate(ids):
        name = f"n{index:02d}-{k}"
        minds.minds[cid].brain.save(folder / f"{name}.npz")
        tail = curves[cid][-5:]
        span = 1000 * len(tail)
        rows.append({
            "name": name, "world": index, "pair": k // 2, "genes": genes[k],
            "structure": structure(genes[k]), "brain_cost": brain_cost(genes[k]),
            "tail_income": sum(r["gained"] for r in tail) / span,
            "tail_nuts": sum(r["nut"] for r in tail) / span * 1000,
            "tail_poisoned": sum(r["poisoned"] for r in tail) / span * 1000,
            "curve": curves[cid],
            "refusals": minds.minds[cid].refusals,
            "moments": moments,
        })
    (folder / f"world{index:02d}.json").write_text(json.dumps(
        {"world": index, "seed": seed, "seconds": round(time.time() - began, 1),
         "rules": vars(Rules(**{**rules, "immortal": True})), "creatures": rows}, indent=1))
    return {"world": index, "seconds": round(time.time() - began, 1)}


def load_nursery(folder: Path) -> list[dict]:
    rows = []
    for f in sorted(folder.glob("world*.json")):
        rows += json.loads(f.read_text())["creatures"]
    return rows


def island(args: tuple) -> dict:
    index, moments, seed, cap, founder_rows, nursery, out, rules, mutation = args
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    brains = [load(Path(nursery) / f"{r['name']}.npz") for r in founder_rows]
    founders = [{"genes": r["genes"], "lineage": i} for i, r in enumerate(founder_rows)]
    eco = Ecosystem(seed * 1000 + index, Rules(**rules), founders=founders, cap=cap, frozen=0,
                    random=0, floor=3, mutation=mutation)
    minds = LocalMinds(brains, seed=seed * 1000 + index)
    minds.born(eco.populate())
    log = []
    began = time.time()

    def report(eco: Ecosystem, minds: LocalMinds) -> None:
        ls = eco.learners()
        gens = [lf.generation for lf in ls]
        tally = eco.tally(since=eco.world.t - 2000).get("live", {})
        log.append({"t": eco.world.t, "learners": len(ls),
                    "generation_mean": float(np.mean(gens)) if gens else 0.0,
                    "generation_max": max(gens) if gens else 0, "reseeded": eco.reseeded,
                    "lineages": sorted({lf.lineage for lf in ls}),
                    "recall_share": float(np.mean([lf.genes["recall"] for lf in ls])) if ls else 0.0,
                    "tally": tally, "seconds": round(time.time() - began, 1)})
        print(f"island {index} t={eco.world.t} learners={len(ls)} gen={log[-1]['generation_mean']:.1f}"
              f" reseeded={eco.reseeded} income={tally.get('income_per_moment')}"
              f" {time.time() - began:.0f}s", flush=True)

    run(eco, minds, moments, every=2000, report=report)
    survivors = []
    for lf in eco.learners():
        name = f"i{index:02d}-c{lf.id}"
        minds.minds[lf.id].brain.save(folder / f"{name}.npz")
        c = eco.world.creatures[lf.id]
        age = eco.world.t - lf.born
        survivors.append({"name": name, "island": index, "genes": lf.genes,
                          "structure": structure(lf.genes), "lineage": lf.lineage,
                          "founder": founder_rows[lf.lineage]["name"],
                          "generation": lf.generation, "age": age,
                          "income_per_moment": lf.income / max(age, 1),
                          "children": lf.children, "energy": c.energy})
    (folder / f"island{index:02d}.json").write_text(json.dumps(
        {"island": index, "seed": seed, "moments": moments, "cap": cap,
         "seconds": round(time.time() - began, 1), "rules": vars(Rules(**rules)),
         "founders": [r["name"] for r in founder_rows],
         "founder_genes": [r["genes"] for r in founder_rows], "log": log,
         "dead": eco.dead[-400:], "survivors": survivors}, indent=1))
    return {"island": index, "survivors": len(survivors)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="stage", required=True)
    n = sub.add_parser("nursery")
    n.add_argument("--worlds", type=int, default=8)
    n.add_argument("--moments", type=int, default=20000)
    n.add_argument("--seed", type=int, default=1)
    n.add_argument("--procs", type=int, default=8)
    n.add_argument("--out", type=Path, default=HERE / "runs" / "nursery")
    e = sub.add_parser("evolve")
    e.add_argument("--nursery", type=Path, default=HERE / "runs" / "nursery",
                   help="a nursery run, or a folder with founders.json from select (a later round)")
    e.add_argument("--islands", type=int, default=6)
    e.add_argument("--moments", type=int, default=40000)
    e.add_argument("--founders", type=int, default=8, help="nursery brains that found each island")
    e.add_argument("--cap", type=int, default=12)
    e.add_argument("--seed", type=int, default=2)
    e.add_argument("--procs", type=int, default=6)
    e.add_argument("--mutation", type=float, default=0.25, help="chance each gene moves at a birth")
    e.add_argument("--genes", type=json.loads, default={},
                   help="genes set on every founder, as JSON (they retune the nursery brains)")
    e.add_argument("--out", type=Path, default=HERE / "runs" / "evolve")
    for q in (n, e):
        q.add_argument("--rules", type=json.loads, default={},
                       help="world rules other than the defaults, as JSON (an experiment)")
    c = sub.add_parser("select")
    c.add_argument("--evolve", type=Path, default=HERE / "runs" / "evolve")
    c.add_argument("--nursery", type=Path, default=HERE / "runs" / "nursery")
    c.add_argument("--founders", type=int, default=8)
    c.add_argument("--min-age", type=int, default=1500, help="survivors younger than this are not ranked")
    c.add_argument("--out", type=Path, default=HERE / "runs" / "founders")
    c.add_argument("--prefix", default="evolved", help="the founders' names: <prefix>-1 ...")
    a = p.parse_args()
    if a.stage == "nursery":
        jobs = [(i, a.moments, a.seed, str(a.out), a.rules) for i in range(a.worlds)]
        with mp.get_context("spawn").Pool(min(a.procs, len(jobs))) as pool:
            for r in pool.imap_unordered(nursery_world, jobs):
                print(json.dumps(r), flush=True)
    elif a.stage == "evolve":
        if (a.nursery / "founders.json").exists():
            # a later round: the founders a select stage wrote (their brains beside founders.json)
            best = [{**r, "name": Path(r["file"]).stem, "genes": {**r["genes"], **a.genes}}
                    for r in json.loads((a.nursery / "founders.json").read_text())["founders"]]
            best = best[:a.founders]
        else:
            rows = load_nursery(a.nursery)
            # net of what the brain costs to run
            rows.sort(key=lambda r: -(r["tail_income"] - r["brain_cost"]))
            best = [{**r, "genes": {**r["genes"], **a.genes}} for r in rows[:a.founders]]
        print("founders:", [(r["name"], r["structure"], round(r.get("tail_income", 0.0), 3)) for r in best])
        jobs = [(i, a.moments, a.seed, a.cap, best, str(a.nursery), str(a.out), a.rules, a.mutation)
                for i in range(a.islands)]
        with mp.get_context("spawn").Pool(min(a.procs, len(jobs))) as pool:
            for r in pool.imap_unordered(island, jobs):
                print(json.dumps(r), flush=True)
    elif a.stage == "select":
        select(a)


def select(a: argparse.Namespace) -> None:
    """The page's founders: the evolved survivors with the best intake per moment, at most one
    per island; and the generation-0 founders the islands started from, for the comparison."""
    import shutil

    islands = [json.loads(f.read_text()) for f in sorted(a.evolve.glob("island*.json"))]
    cands = [s for isl in islands for s in isl["survivors"] if s["age"] >= a.min_age]
    cands.sort(key=lambda s: -s["income_per_moment"])
    chosen, seen = [], set()
    for s in cands:
        if s["island"] in seen:
            continue
        chosen.append(s)
        seen.add(s["island"])
        if len(chosen) == a.founders:
            break
    after = a.out / "after"
    before = a.out / "before"
    for d in (after, before):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    rows = []
    for i, s in enumerate(chosen):
        name = f"{a.prefix}-{i + 1}"
        shutil.copyfile(a.evolve / f"{s['name']}.npz", after / f"{name}.npz")
        rows.append({"name": name, "file": f"{name}.npz", "genes": s["genes"],
                     "structure": structure(s["genes"]), "generation": s["generation"],
                     "lineage": s["lineage"], "origin": {k: s[k] for k in (
                         "name", "island", "founder", "generation", "age", "income_per_moment",
                         "children")}})
    (after / "founders.json").write_text(json.dumps({"founders": rows}, indent=1))
    names = islands[0]["founders"]
    rows = []
    if (a.nursery / "founders.json").exists():  # a later round: its founders were a select's
        for r in json.loads((a.nursery / "founders.json").read_text())["founders"]:
            shutil.copyfile(a.nursery / r["file"], before / r["file"])
            rows.append(r)
    else:
        nursery = {r["name"]: r for r in load_nursery(a.nursery)}
        for name in names:
            r = nursery[name]
            shutil.copyfile(a.nursery / f"{name}.npz", before / f"{name}.npz")
            rows.append({"name": name, "file": f"{name}.npz", "genes": r["genes"],
                         "structure": r["structure"], "generation": 0})
    (before / "founders.json").write_text(json.dumps({"founders": rows}, indent=1))
    print(json.dumps([{k: s[k] for k in ("name", "generation", "age", "income_per_moment", "founder")}
                      for s in chosen], indent=1))


if __name__ == "__main__":
    main()
