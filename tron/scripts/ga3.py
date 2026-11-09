"""the genetic search, one brain per core, resumable.

    python scripts/ga3.py --out runs/r3/ga --pop 64 --gens 30 --workers 64 --s3 s3://bucket/r3/ga

Each generation: every genome is raised from a fresh seed and plays the tournament from that
generation's start seeds (search block 600,000 + 10,000 * gen). Elites carry over and are
raised again, so a genome's fitness is the mean over all its raisings (selection on repeated,
independent draws). The next generation: the elites, then children by tournament selection
of three, uniform crossover (p 0.7) and mutation of one to three genes; a fifth of the slots
are fresh random genomes (immigrants). Generation 0 holds the founder and random genomes.

After the last generation the eight best genomes (at least two raisings each) are raised on
three new seeds and played on the validation block (900,000+), never used by selection, with
16 games per opponent; the winner list comes from that. State is written after every
generation and synced to S3.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMBA_NUM_THREADS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings  # noqa: E402

warnings.filterwarnings("ignore", category=RuntimeWarning)
from tron import r3  # noqa: E402

SEARCH, VALIDATION = 600_000, 900_000


def job(args):
    g, seed, tour_seed, games, keep, scale = args
    return r3.evaluate(g, seed, tour_seed, games=games, keep=keep, scale=scale)


def sync(out: Path, s3: str | None):
    if s3:
        subprocess.run(["aws", "s3", "sync", str(out), s3, "--only-show-errors"], check=False)


def ranked(history: dict) -> list[tuple[str, float, int]]:
    rows = [(k, sum(v["fits"]) / len(v["fits"]), len(v["fits"])) for k, v in history.items()]
    return sorted(rows, key=lambda r: -r[1])


def steady(pool, state, state_path, out, a, rng, log):
    """Steady-state selection: every core always raises a brain. When one finishes, the next
    genome is bred from the ranking at that moment: an elite raised again (0.15, the top
    `elite` with the fewest raisings), a random immigrant (0.15), else a child of two parents,
    each the best of three drawn from the 2 * pop most recent evaluations, crossed (0.7) and
    mutated. Evaluation i plays the start seeds of block i // pop, so every 64 evaluations
    share positions; the total budget is pop * gens evaluations, as the lockstep search."""
    budget = a.pop * a.gens
    state.setdefault("evals", sum(len(v["fits"]) for v in state["history"].values()))
    recent = [r for r in state.get("recent", [])]

    def breed():
        rank = ranked(state["history"])
        u = rng.random()
        if u < 0.15 and rank:
            top = rank[:a.elite]
            k = min(top, key=lambda r: r[2])[0]
            return dict(state["genomes"][k])
        if u < 0.30 or len(recent) < 6:
            return r3.random_genome(rng)

        def pick():
            return max(rng.sample(recent, 3), key=lambda r: r[1])[0]
        pa, pb = state["genomes"][pick()], state["genomes"][pick()]
        child = r3.cross(pa, pb, rng) if rng.random() < 0.7 else dict(pa)
        return r3.mutate(child, rng)

    issued = state["evals"]
    pending = []

    def submit():
        nonlocal issued
        g = breed()
        block = issued // a.pop
        args = (g, 1_000_000 + issued, SEARCH + 10_000 * block, a.games, None, a.scale)
        pending.append((block, pool.apply_async(job, (args,))))
        issued += 1

    while len(pending) < a.workers and issued < budget:
        submit()
    last_sync = time.time()
    while pending:
        time.sleep(2)
        for item in [p for p in pending if p[1].ready()]:
            pending.remove(item)
            block, handle = item
            res = handle.get()
            res["block"] = block
            if "error" not in res:
                res.pop("trace", None)
            with open(out / "evaluations.jsonl", "a") as ev:
                ev.write(json.dumps(res) + "\n")
            h = state["history"].setdefault(res["key"], {"fits": []})
            h["fits"].append(res["fitness"])
            state["genomes"][res["key"]] = res["genome"]
            recent.append((res["key"], res["fitness"]))
            del recent[:-2 * a.pop]
            state["evals"] += 1
            if state["evals"] % a.pop == 0:
                rank = ranked(state["history"])
                line = {"evals": state["evals"], "block": state["evals"] // a.pop - 1,
                        "recent_best": max(f for _, f in recent[-a.pop:]),
                        "recent_median": sorted(f for _, f in recent[-a.pop:])[a.pop // 2],
                        "leaders": [{"key": k, "mean": round(m, 4), "n": n} for k, m, n in rank[:5]]}
                with open(out / "generations.jsonl", "a") as f:
                    f.write(json.dumps(line) + "\n")
                print(json.dumps(line), file=log, flush=True)
            if issued < budget:
                submit()
        if time.time() - last_sync > 900 or not pending:
            state["recent"], state["rng"] = recent, repr(rng.getstate())
            state_path.write_text(json.dumps(state))
            sync(out, a.s3)
            last_sync = time.time()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--pop", type=int, default=64)
    p.add_argument("--gens", type=int, default=30)
    p.add_argument("--elite", type=int, default=8)
    p.add_argument("--games", type=int, default=8)
    p.add_argument("--workers", type=int, default=os.cpu_count())
    p.add_argument("--scale", type=float, default=1.0, help="school budget multiplier (smoke runs)")
    p.add_argument("--seed", type=int, default=3)
    p.add_argument("--finalists", type=int, default=8)
    p.add_argument("--fix", default="", help="pin genes, e.g. sense=field,layout=flat256 (comma-separated)")
    p.add_argument("--val-games", type=int, default=16, help="validation games per opponent")
    p.add_argument("--s3", default=None)
    p.add_argument("--sync-gens", type=int, default=1,
                   help="generations run in lockstep; after them the search runs steady-state")
    a = p.parse_args()
    for item in filter(None, a.fix.split(",")):
        k, v = item.split("=", 1)
        if k not in r3.SPACE:
            raise SystemExit(f"--fix: no gene {k!r}")
        value = type(r3.SPACE[k][0])(v)
        r3.SPACE[k] = [value]
        r3.FOUNDER[k] = value
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    state_path = out / "state.json"
    rng = random.Random(a.seed)
    if state_path.exists():
        state = json.loads(state_path.read_text())
        rng.setstate(eval(state["rng"]))  # tuple repr written by us
    else:
        pop = [dict(r3.FOUNDER)] + [r3.random_genome(rng) for _ in range(a.pop - 1)]
        state = {"gen": 0, "pop": pop, "history": {}, "genomes": {}, "rng": repr(rng.getstate()), "done": False}
    log = open(out / "log.txt", "a")
    with Pool(a.workers, maxtasksperchild=1) as pool:
        while state["gen"] < min(a.gens, a.sync_gens):
            gen, pop = state["gen"], state["pop"]
            t0 = time.time()
            jobs = [(g, 10_000 * gen + i + 1, SEARCH + 10_000 * gen, a.games, None, a.scale) for i, g in enumerate(pop)]
            results = []
            with open(out / "evaluations.jsonl", "a") as ev:
                for res in pool.imap_unordered(job, jobs):
                    res["gen"] = gen
                    res.pop("trace", None) if "error" not in res else None
                    ev.write(json.dumps(res) + "\n")
                    ev.flush()
                    results.append(res)
            for res in results:
                h = state["history"].setdefault(res["key"], {"fits": []})
                h["fits"].append(res["fitness"])
                state["genomes"][res["key"]] = res["genome"]
            rank = ranked(state["history"])
            fits = sorted((r["fitness"] for r in results), reverse=True)
            line = {"gen": gen, "wall_s": round(time.time() - t0), "best": fits[0], "median": fits[len(fits) // 2],
                    "errors": sum("error" in r for r in results),
                    "leaders": [{"key": k, "mean": round(m, 4), "n": n} for k, m, n in rank[:5]]}
            with open(out / "generations.jsonl", "a") as f:
                f.write(json.dumps(line) + "\n")
            print(json.dumps(line), file=log, flush=True)
            # Next generation: elites (by mean over raisings, among genomes alive this generation
            # or earlier), then children.
            elites = [state["genomes"][k] for k, _, _ in rank[:a.elite]]

            def pick():
                cand = rng.sample(results, 3)
                return max(cand, key=lambda r: r["fitness"])["genome"]
            nxt, seen = list(elites), {r3.key(g) for g in elites}
            immigrants = a.pop // 5
            while len(nxt) < a.pop - immigrants:
                child = r3.cross(pick(), pick(), rng) if rng.random() < 0.7 else dict(pick())
                child = r3.mutate(child, rng)
                if r3.key(child) not in seen:
                    nxt.append(child)
                    seen.add(r3.key(child))
            while len(nxt) < a.pop:
                nxt.append(r3.random_genome(rng))
            state.update(gen=gen + 1, pop=nxt, rng=repr(rng.getstate()))
            state_path.write_text(json.dumps(state))
            sync(out, a.s3)
        steady(pool, state, state_path, out, a, rng, log)
        if not state.get("validated"):
            rank = [r for r in ranked(state["history"]) if r[2] >= 2][:a.finalists] or ranked(state["history"])[:a.finalists]
            jobs = []
            for j, (k, _, _) in enumerate(rank):
                for s in range(3):
                    jobs.append((state["genomes"][k], 500_000 + 10 * j + s, VALIDATION + 100_000 * s, a.val_games,
                                 str(out / "finalists" / f"f{j}-s{s}.npz"), a.scale))
            val = list(pool.imap_unordered(job, jobs))
            with open(out / "validation.jsonl", "w") as f:
                for res in val:
                    res.pop("trace", None)
                    f.write(json.dumps(res) + "\n")
            board = {}
            for res in val:
                board.setdefault(res["key"], []).append(res["fitness"])
            summary = sorted(({"key": k, "genome": state["genomes"][k], "validation": sum(v) / len(v), "raisings": v,
                               "search_mean": dict((r[0], r[1]) for r in ranked(state["history"]))[k]}
                              for k, v in board.items()), key=lambda r: -r["validation"])
            (out / "summary.json").write_text(json.dumps(summary, indent=1))
            state["validated"] = True
            state_path.write_text(json.dumps(state))
    (out / "DONE").write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
    sync(out, a.s3)


if __name__ == "__main__":
    main()
