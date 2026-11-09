"""Measure the promise on fresh seeds and write the receipts in ``evidence/``.

    python training/evaluate.py controls  --founders web/pack/founders --seeds 16
    python training/evaluate.py flip      --founders web/pack/founders --seeds 16
    python training/evaluate.py caches    --nursery runs/nursery --seeds 8
    python training/evaluate.py evolution --founders web/pack/founders --before runs/founders/before --seeds 16

Every receipt names the scenario, its seeds and settings, the SHA-256 of the sources and of
every brain it read, the per-seed records and the summary readings. Seeds start at 100,000,
away from every seed of the nursery and the evolution.
"""

from __future__ import annotations

import os

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
              "VECLIB_MAXIMUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import multiprocessing as mp  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from patchworld import scenarios  # noqa: E402
from patchworld.brain import load  # noqa: E402
from patchworld.genes import brain_cost  # noqa: E402
from patchworld.world import Rules  # noqa: E402

SEED0 = 100_000


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources() -> dict[str, str]:
    return {f"patchworld/{p.name}": sha(p) for p in sorted((HERE / "patchworld").glob("*.py"))}


def read_group(folder: Path) -> list[dict]:
    roster = json.loads((folder / "founders.json").read_text())["founders"]
    out = []
    for f in roster:
        out.append({"name": f["name"], "genes": f["genes"], "file": str(folder / f["file"]),
                    "sha256": sha(folder / f["file"])})
    return out


def with_brains(group: list[dict]) -> list[dict]:
    return [{**f, "brain": load(f["file"])} for f in group]


# -- one seed of each scenario (in a worker process)

def job(args: tuple) -> dict:
    kind, seed, payload = args
    began = time.time()
    if kind == "controls":
        rows = scenarios.controls(seed, with_brains(payload["founders"]), payload["moments"],
                                  payload.get("retune"))
    elif kind == "flip":
        rows = scenarios.flip(seed, with_brains(payload["founders"]), payload["summer"],
                              payload["winter"], payload.get("retune"))
    elif kind == "seasons":
        rows = scenarios.seasons(seed, with_brains(payload["founders"]), tuple(payload["lengths"]))
    elif kind == "caches":
        pairs = [{"name": p["name"],
                  "off": {"genes": p["off"]["genes"], "brain": load(p["off"]["file"])},
                  "on": {"genes": p["on"]["genes"], "brain": load(p["on"]["file"])}}
                 for p in payload["pairs"]]
        rows = scenarios.caches(seed, pairs, payload["moments"])
    elif kind == "competition":
        out = scenarios.competition(seed, with_brains(payload["before"]), with_brains(payload["after"]),
                                    payload["moments"], payload.get("retune"))
        return {"seed": seed, "seconds": round(time.time() - began, 1), "rows": [out]}
    elif kind == "evolution":
        rows = scenarios.evolution(seed, with_brains(payload["group"]), payload["moments"],
                                   payload.get("retune"))
    else:
        raise ValueError(kind)
    return {"seed": seed, "seconds": round(time.time() - began, 1), "rows": rows,
            **({"group": payload["label"]} if "label" in payload else {})}


def pool_map(jobs: list[tuple], procs: int) -> list[dict]:
    with mp.get_context("spawn").Pool(min(procs, len(jobs))) as pool:
        return sorted(pool.map(job, jobs), key=lambda r: (r.get("group", ""), r["seed"]))


# -- summaries

def summarize_controls(results: list[dict]) -> dict:
    by: dict[str, dict[str, list]] = {}
    for res in results:
        for r in res["rows"]:
            k = by.setdefault(r["kind"], {"age": [], "income": [], "poisoned": [], "died": []})
            k["age"].append(r["age"])
            k["income"].append(r["income_per_moment"])
            k["poisoned"].append(1000 * r["stats"]["poisoned"] / max(r["age"], 1))
            k["died"].append(int(r["died"]))
    out = {}
    for kind, k in by.items():
        out[kind] = {"creatures": len(k["age"]), "mean_age": scenarios.mean(k["age"]),
                     "mean_age_ci95": scenarios.bootstrap_ci(k["age"]),
                     "median_age": float(np.median(k["age"])),
                     "income_per_moment": scenarios.mean(k["income"]),
                     "income_ci95": scenarios.bootstrap_ci(k["income"]),
                     "poisonings_per_1000": scenarios.mean(k["poisoned"]),
                     "died_share": scenarios.mean(k["died"])}
    # paired: each founder's learner against its own frozen twin, same world
    wins, diffs = 0, []
    for res in results:
        rows = {r["label"]: r for r in res["rows"]}
        for label, r in rows.items():
            if label.endswith(":live"):
                twin = rows[label.replace(":live", ":frozen")]
                diffs.append(r["age"] - twin["age"])
                wins += int(r["age"] > twin["age"])
    out["paired_live_minus_frozen_age"] = {"pairs": len(diffs), "mean": scenarios.mean(diffs),
                                           "ci95": scenarios.bootstrap_ci(diffs),
                                           "live_outlived_twin": wins}
    return out


def summarize_flip(results: list[dict], summer: int, winter: int) -> dict:
    bins = (summer + winter) // 100
    first = summer // 100
    curve: dict[str, list[list[float]]] = {"live": [], "frozen": []}
    accept: dict[str, list[list[float]]] = {"live": [], "frozen": []}
    after_first: dict[str, list[int]] = {"live": [], "frozen": []}
    for res in results:
        for r in res["rows"]:
            kind = r["kind"]
            pb = {int(k): v for k, v in r["poison_bins"].items()}
            bb = {int(k): v for k, v in r["berry_bins"].items()}
            ob = {int(k): v for k, v in r["over_bins"].items()}
            curve[kind].append([pb.get(b, 0) + bb.get(b, 0) for b in range(bins)])
            accept[kind].append([(pb.get(b, 0) + bb.get(b, 0)) / ob[b] if ob.get(b) else np.nan
                                 for b in range(bins)])
            # winter berries eaten after the creature's first poisoning
            winter_bins = [pb.get(b, 0) for b in range(first, bins)]
            total = sum(winter_bins)
            after_first[kind].append(max(0, total - 1) if total else 0)
    out: dict = {"bin_moments": 100, "flip_bin": first, "bins": bins}
    for kind in ("live", "frozen"):
        a = np.asarray(curve[kind], dtype=float)
        acc = np.asarray(accept[kind], dtype=float)
        out[kind] = {
            "creatures": len(a),
            "berries_per_creature_per_bin": [round(float(v), 4) for v in a.mean(axis=0)],
            "acceptance_per_bin": [None if np.isnan(v) else round(float(v), 4)
                                   for v in np.nanmean(np.where(np.isnan(acc), np.nan, acc), axis=0)],
            "summer_berries_per_100": float(a[:, :first].mean()) if first else None,
            "winter_first_300_per_100": float(a[:, first:first + 3].mean()),
            "winter_last_500_per_100": float(a[:, bins - 5:].mean()),
            "winter_poisonings_per_creature": float(a[:, first:].sum(axis=1).mean()),
            "winter_poisonings_after_the_first": scenarios.mean(after_first[kind]),
        }
    return out


def summarize_seasons(results: list[dict], lengths: list[int]) -> dict:
    """Per season: berries eaten per creature per 100 moments, in the first 300 moments of the
    season and over all of it, and the share eaten of the berries stood on."""
    edges = np.concatenate([[0], np.cumsum(lengths)]) // 100
    out: dict = {"lengths": lengths, "seasons": ["summer", "winter", "summer", "winter"][:len(lengths)]}
    for kind in ("live", "frozen"):
        per = []
        for i in range(len(lengths)):
            lo, hi = int(edges[i]), int(edges[i + 1])
            first, whole, ate, stood = [], [], 0, 0
            for res in results:
                for r in res["rows"]:
                    if r["kind"] != kind:
                        continue
                    eat = {int(k): v for k, v in r["berry_bins"].items()}
                    for k, v in r["poison_bins"].items():
                        eat[int(k)] = eat.get(int(k), 0) + v
                    over = {int(k): v for k, v in r["over_bins"].items()}
                    first.append(sum(eat.get(b, 0) for b in range(lo, lo + 3)) / 3)
                    whole.append(sum(eat.get(b, 0) for b in range(lo, hi)) / (hi - lo))
                    ate += sum(eat.get(b, 0) for b in range(lo, hi))
                    stood += sum(over.get(b, 0) for b in range(lo, hi))
            per.append({"first_300_per_100": scenarios.mean(first),
                        "first_300_ci95": scenarios.bootstrap_ci(first),
                        "season_per_100": scenarios.mean(whole),
                        "acceptance": ate / stood if stood else None})
        out[kind] = per
    return out


def summarize_caches(results: list[dict], moments: int) -> dict:
    on, off, diffs = [], [], []
    for res in results:
        rows = {r["label"]: r for r in res["rows"]}
        for label, r in rows.items():
            if label.endswith(":on"):
                o = rows[label.replace(":on", ":off")]
                a, b = 1000 * r["stats"]["nut"] / moments, 1000 * o["stats"]["nut"] / moments
                on.append(a)
                off.append(b)
                diffs.append(a - b)
    return {"pairs": len(diffs), "nuts_per_1000_recall_on": scenarios.mean(on),
            "nuts_per_1000_recall_off": scenarios.mean(off),
            "paired_on_minus_off": scenarios.mean(diffs),
            "paired_ci95": scenarios.bootstrap_ci(diffs),
            "on_better": int(sum(d > 0 for d in diffs)), "off_better": int(sum(d < 0 for d in diffs))}


def summarize_evolution(results: list[dict], groups: dict[str, list[dict]]) -> dict:
    out = {}
    for label, group in groups.items():
        rows = [r for res in results if res["group"] == label for r in res["rows"]]
        ages = [r["age"] for r in rows]
        income = [r["income_per_moment"] for r in rows]
        cost = [brain_cost(f["genes"]) for f in group]
        out[label] = {"creatures": len(rows), "mean_age": scenarios.mean(ages),
                      "mean_age_ci95": scenarios.bootstrap_ci(ages),
                      "income_per_moment": scenarios.mean(income),
                      "income_ci95": scenarios.bootstrap_ci(income),
                      "brain_cost_per_moment": scenarios.mean(cost),
                      "learning_sweeps_per_moment": scenarios.mean(
                          [r["learning_sweeps"] / max(r["age"], 1) for r in rows]),
                      "structures": sorted({f"w{f['genes']['width']}d{f['genes']['depth']}"
                                            f"{'r' if f['genes']['recall'] else ''}" for f in group})}
    return out


def strip(group: list[dict]) -> list[dict]:
    return [{"name": f["name"], "file": Path(f["file"]).name, "sha256": f["sha256"]} for f in group]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("scenario", choices=("controls", "flip", "seasons", "caches", "evolution", "competition"))
    p.add_argument("--founders", type=Path, default=HERE / "web" / "pack" / "founders")
    p.add_argument("--before", type=Path, default=HERE / "runs" / "founders" / "before")
    p.add_argument("--nursery", type=Path, default=HERE / "runs" / "nursery")
    p.add_argument("--seeds", type=int, default=16)
    p.add_argument("--moments", type=int, default=6000)
    p.add_argument("--summer", type=int, default=1000)
    p.add_argument("--winter", type=int, default=1500)
    p.add_argument("--pairs", type=int, default=16, help="caches: recall pairs from the nursery")
    p.add_argument("--procs", type=int, default=16)
    p.add_argument("--retune", type=json.loads, default=None,
                   help="flip: named settings applied to the learners (an experiment)")
    p.add_argument("--retune-before", type=json.loads, default=None,
                   help="evolution: named settings for the generation-0 founders, as evolve --genes set them")
    p.add_argument("--name", default=None, help="the receipt's file name (default: the scenario)")
    p.add_argument("--out", type=Path, default=HERE / "evidence")
    a = p.parse_args()
    seeds = [SEED0 + s for s in range(a.seeds)]
    began = time.time()
    receipt: dict = {"scenario": a.scenario, "seeds": seeds, "sources_sha256": sources(),
                     "rules": vars(Rules()), "date": time.strftime("%Y-%m-%d")}
    import cadence

    receipt["cadence"] = cadence.__version__
    if a.scenario == "seasons":
        group = read_group(a.founders)
        lengths = [a.summer, a.winter, a.winter, a.winter]
        results = pool_map([("seasons", s, {"founders": group, "lengths": lengths}) for s in seeds], a.procs)
        receipt["brains"] = strip(group)
        receipt["settings"] = {"lengths": lengths, "world": "nobody dies, no predators"}
        receipt["summary"] = summarize_seasons(results, lengths)
    elif a.scenario in ("controls", "flip"):
        group = read_group(a.founders)
        payload = {"founders": group, "moments": a.moments, "summer": a.summer, "winter": a.winter,
                   "retune": a.retune}
        results = pool_map([(a.scenario, s, payload) for s in seeds], a.procs)
        receipt["brains"] = strip(group)
        if a.scenario == "controls":
            receipt["settings"] = {"moments": a.moments, "world": "mortal, no births"}
            receipt["summary"] = summarize_controls(results)
        else:
            receipt["settings"] = {"summer": a.summer, "winter": a.winter,
                                   "world": "nobody dies, no predators"}
            receipt["summary"] = summarize_flip(results, a.summer, a.winter)
    elif a.scenario == "caches":
        rows = []
        for f in sorted(a.nursery.glob("world*.json")):
            rows += json.loads(f.read_text())["creatures"]
        pairs: dict[tuple, dict] = {}
        for r in rows:
            side = "on" if r["genes"]["recall"] else "off"
            pairs.setdefault((r["world"], r["pair"]), {})[side] = {
                "genes": r["genes"], "file": str(a.nursery / f"{r['name']}.npz"),
                "name": r["name"], "tail_income": r["tail_income"]}
        # the pairs whose recall-off brain foraged best in the nursery, at most a.pairs
        chosen = sorted(pairs.items(), key=lambda kv: -kv[1]["off"]["tail_income"])[:a.pairs]
        plist = [{"name": f"w{k[0]}p{k[1]}", **v} for k, v in chosen]
        payload = {"pairs": plist, "moments": a.moments}
        results = pool_map([("caches", s, payload) for s in seeds], a.procs)
        receipt["brains"] = [{"pair": q["name"], "off": Path(q["off"]["file"]).name,
                              "on": Path(q["on"]["file"]).name,
                              "off_sha256": sha(Path(q["off"]["file"])),
                              "on_sha256": sha(Path(q["on"]["file"]))} for q in plist]
        receipt["settings"] = {"moments": a.moments, "world": "nobody dies"}
        receipt["summary"] = summarize_caches(results, a.moments)
        receipt["nursery_tail"] = {
            "pairs": len(pairs),
            "nuts_per_1000_on": scenarios.mean([v["on"].get("tail_nuts", 0) for v in pairs.values()
                                                if "on" in v]),
        }
        nursery_rows = {(r["world"], r["pair"], bool(r["genes"]["recall"])): r for r in rows}
        diffs = [nursery_rows[(w, q, True)]["tail_nuts"] - nursery_rows[(w, q, False)]["tail_nuts"]
                 for (w, q, rec) in nursery_rows if rec]
        receipt["nursery_tail"] = {"pairs": len(diffs),
                                   "paired_on_minus_off_nuts_per_1000": scenarios.mean(diffs),
                                   "ci95": scenarios.bootstrap_ci(diffs),
                                   "on_better": int(sum(d > 0 for d in diffs)),
                                   "off_better": int(sum(d < 0 for d in diffs))}
    elif a.scenario == "competition":
        before, after = read_group(a.before), read_group(a.founders)
        genes = (a.retune_before or {}).get("arousal", {})
        payload = {"before": before, "after": after, "moments": a.moments, "retune": genes}
        results = pool_map([("competition", s, payload) for s in seeds], a.procs)
        receipt["brains"] = {"before": strip(before), "after": strip(after)}
        receipt["settings"] = {"moments": a.moments, "world": "mortal, births on, cap 16, 8 founders a side",
                               "before_genes": genes}
        last = [r["rows"][0]["curve"][-1] for r in results]
        shares = [x["after"] / (x["after"] + x["before"]) for x in last if x["after"] + x["before"]]
        receipt["summary"] = {
            "worlds": len(results), "evolved_share_of_learners_at_end": scenarios.mean(shares),
            "ci95": scenarios.bootstrap_ci(shares),
            "worlds_evolved_hold_all": int(sum(1 for x in last if x["after"] and not x["before"])),
            "worlds_generation0_hold_all": int(sum(1 for x in last if x["before"] and not x["after"])),
            "births_after": int(sum(r["rows"][0]["births"]["after"] for r in results)),
            "births_before": int(sum(r["rows"][0]["births"]["before"] for r in results)),
            "mean_curve": [{"t": c["t"], "after": scenarios.mean([r["rows"][0]["curve"][i]["after"] for r in results if len(r["rows"][0]["curve"]) > i]),
                            "before": scenarios.mean([r["rows"][0]["curve"][i]["before"] for r in results if len(r["rows"][0]["curve"]) > i])}
                           for i, c in enumerate(results[0]["rows"][0]["curve"])]}
    else:
        groups = {"before": read_group(a.before), "after": read_group(a.founders)}
        # the generation-0 founders as the islands received them: their genes set by evolve --genes
        jobs = [("evolution", s, {"group": g, "moments": a.moments, "label": label,
                                  "retune": a.retune_before if label == "before" else None})
                for label, g in groups.items() for s in seeds]
        receipt["retune_before"] = a.retune_before
        results = pool_map(jobs, a.procs)
        receipt["brains"] = {k: strip(v) for k, v in groups.items()}
        receipt["settings"] = {"moments": a.moments, "world": "mortal, no births"}
        receipt["summary"] = summarize_evolution(results, groups)
    receipt["per_seed"] = [{k: v for k, v in r.items()} for r in results]
    receipt["seconds"] = round(time.time() - began, 1)
    a.out.mkdir(parents=True, exist_ok=True)
    receipt["retune"] = a.retune
    path = a.out / f"{a.name or a.scenario}.json"
    # the summary readable, the per-seed records one line per seed
    per_seed = receipt.pop("per_seed")
    text = json.dumps(receipt, indent=1, default=float)[:-2]
    text += ',\n "per_seed": [\n' + ",\n".join(
        json.dumps(r, separators=(",", ":"), default=float) for r in per_seed) + "\n ]\n}\n"
    json.loads(text)
    path.write_text(text)
    receipt["per_seed"] = per_seed
    print(json.dumps(receipt["summary"], indent=1, default=float))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
