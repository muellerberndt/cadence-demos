"""raise a validated genome long, one arm per process.

    python scripts/phaseb.py --arm instruct --genome runs/r3/ga/summary.json --rank 0 --seed 21 --out runs/r3/b/instruct-s21

Every arm: the long corpus school (`--watch` lessons from the voronoi3 corpus), then stage 2
for `--stage2` moments, then stage 3 for `--stage3` moments. A moment is one tick of all rows.

| arm | stage 2 | stage 3 |
| control  | DAgger, voronoi2 labels | DAgger, voronoi2 labels |
| instruct | DAgger, voronoi3 labels | DAgger, voronoi3 labels |
| selfplay | DAgger, voronoi3 labels | outcome learning (`step`), half the rows against a league of its own past checkpoints, half against the pool |
| combined | DAgger, voronoi3 labels | stretches of `--stretch` moments alternating: DAgger with voronoi3 labels, outcome learning, both against the league and the pool |

Checkpoints every `--every` moments and at each stage end: the brain saved, a frozen CPU twin
scored on the scenario tests and a 24-game tournament per opponent (seeds 2,100,000+), one line
in report.jsonl; the run directory synced to S3 then and at least hourly.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
import warnings
from multiprocessing import Pool
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=RuntimeWarning)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tron import bots, fastbots, r3, scenarios, school  # noqa: E402
from tron.field import make_sense3  # noqa: E402
from tron.world import Arena, mulberry32  # noqa: E402

TEACHERS = {"voronoi2": fastbots.voronoi2, "voronoi3": fastbots.voronoi3}  # Numba ports, identical moves


def _label(args):
    name, arena = args
    return TEACHERS[name](arena, 0)


class Rows:
    def __init__(self, n, seed, league_share=0.0):
        self.rng = random.Random(seed)
        self.n, self.league_share = n, league_share
        self.items = [self.fresh(i) for i in range(n)]

    def fresh(self, i):
        s = self.rng.randrange(1 << 30)
        league = i < int(self.n * self.league_share)
        return {"arena": Arena(24, seed=s), "draw": mulberry32(s),
                "opp": "league" if league else r3.SCHOOL[self.rng.randrange(len(r3.SCHOOL))]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--arm", required=True, choices=["control", "instruct", "selfplay", "combined"])
    p.add_argument("--genome", required=True)
    p.add_argument("--rank", type=int, default=0)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--rows", type=int, default=16)
    p.add_argument("--watch", type=int, default=15000)
    p.add_argument("--stage2", type=int, default=40000)
    p.add_argument("--stage3", type=int, default=60000)
    p.add_argument("--every", type=int, default=10000)
    p.add_argument("--stretch", type=int, default=50)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--backend", default="torch")
    p.add_argument("--games", type=int, default=24)
    p.add_argument("--scenarios", default="runs/r3/scenarios.json")
    p.add_argument("--s3", default=None)
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    g = json.loads(Path(a.genome).read_text())[a.rank]["genome"]
    sets = scenarios.load(a.scenarios)
    see = make_sense3(g["sense"])[0]
    state = {"moments": 0, "stage": 1, "t0": time.time(), "last_sync": time.time()}
    meta = {"arm": a.arm, "genome": g, "seed": a.seed, "args": vars(a)}
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    from cadence import Brain

    # Resume: the latest saved brain (brain-school or brain-m<moments>) in the run directory.
    saved = sorted(out.glob("brain-m*.npz"), key=lambda q: int(q.stem[7:]))
    start = 0
    if saved:
        brain = Brain.load(str(saved[-1]), backend=a.backend)
        start = int(saved[-1].stem[7:])
    elif (out / "brain-school.npz").exists():
        brain = Brain.load(str(out / "brain-school.npz"), backend=a.backend)
    else:
        brain = None
    league: list[str] = [str(q) for q in saved] if a.arm in ("selfplay", "combined") else []
    state["moments"] = start

    def sync(force=False):
        if a.s3 and (force or time.time() - state["last_sync"] > 3000):
            subprocess.run(["aws", "s3", "sync", str(out), a.s3, "--only-show-errors"], check=False)
            state["last_sync"] = time.time()

    def checkpoint(tag):
        path = out / f"brain-{tag}.npz"
        brain.save(str(path))
        twin = Brain.load(str(path), backend="cpu")
        twin.reset()
        pol = r3.policy(twin, g["sense"])
        pol.reset = twin.reset
        t = time.time()
        line = {"tag": tag, "stage": state["stage"], "moments": state["moments"],
                "wall_h": round((time.time() - state["t0"]) / 3600, 2),
                "scenarios": scenarios.score(pol, sets, reset=twin.reset),
                "tournament": r3.tournament(pol, 2_100_000, a.games)}
        line["eval_s"] = round(time.time() - t)
        with open(out / "report.jsonl", "a") as f:
            f.write(json.dumps(line) + "\n")
        print(json.dumps({k: line[k] for k in ("tag", "moments", "wall_h")}), round(line["tournament"]["strength"], 3), flush=True)
        if a.arm in ("selfplay", "combined"):
            league.append(str(path))
        brain.reset()
        sync(force=True)

    # Stage 1: the corpus school (skipped when resuming).
    if brain is None:
        brain = r3.compose(g, a.seed, backend=a.backend)
        w = r3.watch(brain, g["sense"], a.watch, a.rows, a.seed)
        with open(out / "school.json", "w") as f:
            json.dump(w, f)
        checkpoint("school")
    brain.reset()

    pool = Pool(a.workers)
    stage_plan = [(2, a.stage2), (3, a.stage3)]
    for stage, moments in stage_plan:
        before = a.stage2 if stage == 3 else 0
        moments -= max(0, min(moments, start - before))
        if moments <= 0:
            continue
        state["stage"] = stage
        outcome_stage = stage == 3 and a.arm in ("selfplay", "combined")
        rows = Rows(a.rows, a.seed * 1000 + stage, league_share=0.5 if outcome_stage else 0.0)
        teacher = "voronoi2" if a.arm == "control" else "voronoi3"
        opp_brain = None
        pending = False
        reward = np.zeros(a.rows)
        done = np.zeros(a.rows, bool)
        brain.reset()
        stats = {"games": 0, "score": 0.0}
        for k in range(moments):
            if outcome_stage and k % 2000 == 0 and league:
                opp_brain = Brain.load(random.Random(k + a.seed).choice(league), backend="cpu")
                opp_brain.reset()
            labelled = not outcome_stage or (a.arm == "combined" and (k // a.stretch) % 2 == 0)
            x = np.stack([see(r["arena"], 0) for r in rows.items])
            try:
                if labelled:
                    if pending:
                        brain.step(x, reward=reward, done=done)
                        pending = False
                    y = np.array(pool.map(_label, [(teacher, r["arena"]) for r in rows.items]))
                    moves = np.asarray(brain.act(x, greedy=True)).reshape(-1)
                    brain.lesson(x, y)
                else:
                    moves = np.asarray(brain.step(x, reward=reward, done=done) if pending else brain.step(x)).reshape(-1)
                    pending = True
            except RuntimeError:
                brain.reset()
                pending = False
                moves = np.ones(a.rows, int)
            if opp_brain is not None:
                xo = np.stack([see(r["arena"], 1) if r["opp"] == "league" else np.zeros_like(x[0]) for r in rows.items])
                theirs = np.asarray(opp_brain.act(xo, greedy=True)).reshape(-1)
            reward = np.zeros(a.rows)
            done = np.zeros(a.rows, bool)
            for i, r in enumerate(rows.items):
                ar = r["arena"]
                if r["opp"] == "league":
                    o = int(theirs[i]) if opp_brain is not None else bots.voronoi(ar, 1)
                else:
                    o = school.POOL[r["opp"]](ar, 1, r["draw"])
                ar.step((int(moves[i]), o))
                if ar.over:
                    rr, _ = school.outcome(ar)
                    reward[i], done[i] = rr, True
                    stats["games"] += 1
                    stats["score"] += 1.0 if ar.winner == 0 else 0.5 if ar.winner is None else 0.0
                    rows.items[i] = rows.fresh(i)
                    if opp_brain is not None and rows.items[i]["opp"] == "league":
                        pass
            if opp_brain is not None and done.any():
                opp_brain.reset()  # a new league game starts without the old trace (all rows share it)
            state["moments"] += 1
            if state["moments"] % 1000 == 0:
                print(json.dumps({"progress": state["moments"], "wall_h": round((time.time() - state["t0"]) / 3600, 3)}), flush=True)
            if state["moments"] % a.every == 0 or k + 1 == moments:
                if pending:
                    x = np.stack([see(r["arena"], 0) for r in rows.items])
                    brain.step(x, reward=reward, done=done)
                    brain.act(x, greedy=True)
                    pending = False
                with open(out / "train.jsonl", "a") as f:
                    f.write(json.dumps({"stage": stage, "moments": state["moments"], "own_score": stats["score"] / max(stats["games"], 1), "games": stats["games"]}) + "\n")
                stats = {"games": 0, "score": 0.0}
                checkpoint(f"m{state['moments']}")
            sync()
    pool.close()
    (out / "DONE").write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
    sync(force=True)


if __name__ == "__main__":
    main()
