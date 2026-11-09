"""The gate a new roster passes before it replaces the shipped one.

    python -m arena.gate --new breed:Name1,Name2,... --old league-live:Dozer,Crab,... --out gate

1. Head to head: ``--mixed`` royales of six, three new robots and three old ones drawn at
   random each fight, both sides' brains continuing (and learning) through the series as in
   the page. Readings: Elo of every robot over the series, the mean placement score of each
   side and its difference with a 95% bootstrap interval over fights.
2. The random twins: ``--twins`` royales of six drawn from the new robots and the two
   uniform-random twins; every twin must end below every new brain on Elo.
3. The driving test of every new brain as it arrives (before the gate's fights).

Writes ``<out>/gate.json`` with every reading and fight.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import random
import shutil
from dataclasses import replace
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from .brain import PAGE_STAGE
from .evolve import _licence_job
from .league import League, baseline_bots
from .parts import blueprint_from_dict, stock_designs


def _side(spec: str) -> tuple[Path, list[str]]:
    root, names = spec.split(":")
    return Path(root), names.split(",")


def _copy_into(league: League, prefix: str, root: Path, names: list[str]) -> list[str]:
    src = json.loads((root / "league.json").read_text())["robots"]
    out = []
    for n in names:
        e = src[n]
        bp = blueprint_from_dict(e["blueprint"])
        name = f"{prefix}{n}"
        entry = league.add(replace(bp, name=name))
        shutil.copy(root / "brains" / f"{n}.npz", league.brain_path(name))
        entry["owed"] = e.get("owed")
        entry["nursery"] = e.get("nursery") or {"moments": 0}
        out.append(name)
    return out


def _boot(diffs: list[float], rng: random.Random, n: int = 4000) -> tuple[float, float]:
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--new", required=True)
    p.add_argument("--old", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--mixed", type=int, default=48)
    p.add_argument("--twins", type=int, default=36)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args(argv)
    rng = random.Random(a.seed)
    out = Path(a.out)
    stage = dict(PAGE_STAGE)
    new_root, new_names = _side(a.new)
    old_root, old_names = _side(a.old)

    # 3. the driving test of the new brains as they arrive
    src = json.loads((new_root / "league.json").read_text())["robots"]
    jobs = [(src[n]["blueprint"], str(new_root / "brains" / f"{n}.npz")) for n in new_names]
    with ProcessPoolExecutor(max_workers=a.workers, mp_context=multiprocessing.get_context("spawn")) as ex:
        tests = list(ex.map(_licence_job, jobs))
    licence = {n: {"licence": round(float(t["licence"]), 3), "passes": int(t["passes"]),
                   "marks": "".join("+" if v else "-" for v in t["passed"].values())} for n, t in zip(new_names, tests)}
    mean_licence = sum(v["licence"] for v in licence.values()) / len(licence)
    print(f"driving test: mean {mean_licence:+.3f}; " + ", ".join(f"{n} {v['licence']:+.2f}" for n, v in licence.items()), flush=True)

    # 1. head to head
    h2h = League(out / "head-to-head")
    h2h.create([])
    new = _copy_into(h2h, "new-", new_root, new_names)
    old = _copy_into(h2h, "old-", old_root, old_names)
    h2h.save()
    diffs = []
    for k in range(a.mixed):
        group = rng.sample(new, 3) + rng.sample(old, 3)
        row = h2h.royale(group, seed=10_000 + k, duration=2400, zone_moments=2000, zone_end=3.5, stage=stage,
                         workers=a.workers, record=False)
        score = {r["name"]: r["score"] for r in row["results"]}
        diffs.append(sum(score[n] for n in group[:3]) / 3 - sum(score[n] for n in group[3:]) / 3)
        print(f"  mixed {k + 1}/{a.mixed}: winner {row['results'][0]['name']}, new - old {diffs[-1]:+.2f}", flush=True)
    low, high = _boot(diffs, rng)
    elo = {n: h2h.data["robots"][n]["elo"] for n in new + old}
    head = {"fights": len(diffs), "new_minus_old": round(sum(diffs) / len(diffs), 3), "ci95": [round(low, 3), round(high, 3)],
            "elo": elo, "elo_new_mean": round(sum(elo[n] for n in new) / len(new), 1),
            "elo_old_mean": round(sum(elo[n] for n in old) / len(old), 1),
            "wins": {n: h2h.data["robots"][n]["wins"] for n in new + old}}
    print(f"head to head: new - old {head['new_minus_old']:+.3f} [{low:+.3f}, {high:+.3f}]; "
          f"Elo new {head['elo_new_mean']} old {head['elo_old_mean']}", flush=True)

    # 2. the random twins
    tw = League(out / "twins")
    tw.create(baseline_bots(stock_designs()))
    tnew = _copy_into(tw, "", new_root, new_names)
    tw.save()
    everyone = tnew + [b.name for b in baseline_bots(stock_designs())]
    for k in range(a.twins):
        group = sorted(everyone, key=lambda n: (tw.data["robots"][n]["fights"], rng.random()))[:6]
        tw.royale(group, seed=20_000 + k, duration=2400, zone_moments=2000, zone_end=3.5, stage=stage,
                  workers=a.workers, record=False)
    telo = {n: tw.data["robots"][n]["elo"] for n in everyone}
    twins_below = all(telo[t] < min(telo[n] for n in tnew) for t in everyone if t.startswith("Random-"))
    print(f"twins: {telo}; every twin below every brain: {twins_below}", flush=True)

    result = {"licence": licence, "licence_mean": round(mean_licence, 3), "head_to_head": head,
              "twins": {"fights": a.twins, "elo": telo, "every_twin_below_every_brain": twins_below},
              "passes": {"a_head_to_head": low > 0.0, "b_licence": mean_licence >= 0.54, "c_twins": twins_below}}
    (out / "gate.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result["passes"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
