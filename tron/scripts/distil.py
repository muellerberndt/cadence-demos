"""Distil the brain + search player into the brain alone: expert iteration with a tree-search
teacher, gated on the brain alone. Resumable (state.json in --out).

    python scripts/distil.py --start web/pack/flat/brain/brain.npz --out runs/distil/flat \\
        --league web/pack/flat/brain/brain.npz --workers 90 --sims 200

Per generation g:
1. Positions. The current best brain rides alone (reset, greedy act, every move); on a
   `--teacher-share` of the games the teacher's move is played instead, so the brain also sees the
   positions a stronger player reaches. Opponents: a `--bot-share` of the games against bots
   (`voronoi`, `voronoi2`, `voronoi3`, and `ab5` at a third of the weight), the rest against the
   current best, its kept generations and the league (brain alone). At every position the brain
   reaches, the teacher (the same frozen best brain guiding `tron/mcts.py` at `--sims`
   simulations, territory leaves, no noise) gives the root's visit shares. About `--positions`
   positions per generation, in `--workers` processes.
2. Children. `--children` children of the best, child k with the rates of `--base-eta` (a fixed
   reference, never the best's stored rate) divided by an item of `--eta-divs`; even children are
   taught the visit shares (`lesson(x, targets=...)`), odd children their argmax; positions where
   the search is sharp (top share above `--sharp`) weigh `--crit-w` (`weights=`). `--lessons`
   lessons of `--rows` positions drawn from the last `--window` generations, each after
   `brain.reset()` (the act and the lesson settle from rest). A deep brain keeps the per-synapse
   rates its checkpoint carries.
3. Gate (`select_exit.sprt_gate`, the brain alone): the children's agreement with `ab5` on the
   turn set's critical positions; a sequential test of the paired difference against the best
   over mirror pairs against `voronoi` (batches of `--batch`, cap `--cap`; undecided at the cap
   and leaning ahead: 128 pairs on fresh seeds, kept only if ahead there too); then head to head
   against the best and against each `--league` brain.
4. A kept brain is read: 128 pairs against `voronoi` on the checkpoint seeds (2,200,000+) and on
   the confirmation seeds (7,000,000+), 64 pairs against `voronoi3`. One line in generations.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from multiprocessing import get_context
from pathlib import Path
from types import SimpleNamespace

import numpy as np

warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent))
from tron import mcts  # noqa: E402
from tron.field import make_sense3  # noqa: E402
from tron.world import Arena, mulberry32  # noqa: E402
from phasec import OPP  # noqa: E402
import r3eval  # noqa: E402
import select_exit  # noqa: E402

SEE = make_sense3("field")[0]
BOTS = {"voronoi": 1.0, "voronoi2": 1.0, "voronoi3": 1.0, "ab5": 1 / 3}


def _positions(args):
    """Games of the best brain riding alone; the teacher's visit shares at each of its positions."""
    best, opponents, sims, seed, games, bot_share, teacher_share = args
    from cadence import Brain
    brain = Brain.load(best, backend="cpu")
    ev = mcts.Evaluator(best)
    rng = random.Random(seed)
    loaded = {}
    xs, ps, outs = [], [], []
    for _ in range(games):
        s = rng.randrange(1 << 30)
        arena, draw = Arena(24, seed=s), mulberry32(s)
        if rng.random() < bot_share or not opponents:
            name = rng.choices(list(BOTS), list(BOTS.values()))[0]
            opp = lambda a, d, _n=name: OPP[_n](a, 1, d)  # noqa: E731
        else:
            path = rng.choice(opponents)
            if path not in loaded:
                loaded[path] = Brain.load(path, backend="cpu")
            ob = loaded[path]

            def opp(a, d, _b=ob):
                _b.reset()
                return int(_b.act(SEE(a, 1)[None, :].astype(np.float64), greedy=True)[0])
        follow = rng.random() < teacher_share
        while not arena.over:
            x = SEE(arena, 0)
            _, visits = mcts.search(arena, 0, ev, sims=sims)
            brain.reset()
            own = int(brain.act(x[None, :].astype(np.float64), greedy=True)[0])
            xs.append(x.astype(np.uint8))
            ps.append(visits.astype(np.float32))
            mine = int(np.argmax(visits)) if follow else own
            arena.step((mine, opp(arena, draw)))
        outs.append(1.0 if arena.winner == 0 else 0.5 if arena.winner is None else 0.0)
    return np.array(xs, np.uint8).reshape(-1, xs[0].shape[0] if xs else 0), np.array(ps, np.float32).reshape(-1, 3), outs


def _child(args):
    """One child: lessons on the window's positions from the best, at its own step and target."""
    best, out, data, k, div, base_eta, lessons, rows, target, sharp, crit_w, seed = args
    from cadence import Brain
    x = np.concatenate([np.load(d)["x"] for d in data]).astype(np.float64)
    p = np.concatenate([np.load(d)["p"] for d in data])
    brain = Brain.load(best, backend="cpu")
    c = brain.learner.config
    brain.retune(learning=replace(c, eta=base_eta / div, eta_bias=base_eta / 10 / div))
    rng = np.random.default_rng(seed)
    w_all = np.where(p.max(1) > sharp, crit_w, 1.0)
    refused = 0
    t0 = time.time()
    for _ in range(lessons):
        idx = rng.choice(len(x), rows, replace=False)
        brain.reset()
        try:
            if target == "visits":
                brain.lesson(x[idx], targets=p[idx].astype(np.float64), weights=w_all[idx])
            else:
                brain.lesson(x[idx], p[idx].argmax(1), weights=w_all[idx])
        except RuntimeError:
            refused += 1
    brain.reset()
    brain.save(out)
    return {"child": k, "path": out, "div": div, "target": target, "refused": refused, "seconds": round(time.time() - t0)}


def sync(out: Path, s3: str | None) -> None:
    if s3:
        subprocess.run(["aws", "s3", "sync", str(out), s3, "--only-show-errors"], check=False)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--league", default="", help="comma-separated brains every pick must hold against")
    p.add_argument("--sims", type=int, default=200)
    p.add_argument("--positions", type=int, default=16000)
    p.add_argument("--games-per-task", type=int, default=2)
    p.add_argument("--bot-share", type=float, default=0.5)
    p.add_argument("--teacher-share", type=float, default=0.25)
    p.add_argument("--children", type=int, default=8)
    p.add_argument("--eta-divs", default="20,30,50")
    p.add_argument("--base-eta", type=float, default=0.0009)
    p.add_argument("--lessons", type=int, default=1200)
    p.add_argument("--rows", type=int, default=32)
    p.add_argument("--window", type=int, default=2)
    p.add_argument("--sharp", type=float, default=0.9)
    p.add_argument("--crit-w", type=float, default=2.5)
    p.add_argument("--gens", type=int, default=100)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--cap", type=int, default=512)
    p.add_argument("--survivors", type=int, default=6)
    p.add_argument("--crit-slack", type=float, default=0.03)
    p.add_argument("--delta", type=float, default=0.04)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--min-vs-best", type=float, default=0.45)
    p.add_argument("--league-floor", type=float, default=0.47)
    p.add_argument("--read-pairs", type=int, default=128)
    p.add_argument("--deadline", type=float, default=0.0, help="unix time after which no generation starts")
    p.add_argument("--s3", default=None)
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    state_path = out / "state.json"
    if state_path.exists():
        st = json.loads(state_path.read_text())
    else:
        first = out / "best-g0.npz"
        shutil.copy(a.start, first)
        st = {"gen": 0, "best": str(first), "kept": [], "data": []}
        state_path.write_text(json.dumps(st))
    league = [q for q in a.league.split(",") if q]
    divs = [float(v) for v in a.eta_divs.split(",")]
    gate = SimpleNamespace(workers=a.workers, crit_slack=a.crit_slack, survivors=a.survivors, batch=a.batch,
                           cap=a.cap, alpha=a.alpha, delta=a.delta, min_vs_best=a.min_vs_best,
                           league_floor=a.league_floor)
    ctx = get_context(r3eval.MP)
    while st["gen"] < a.gens and not (a.deadline and time.time() > a.deadline):
        g = st["gen"]
        gdir = out / f"g{g}"
        (gdir / "data").mkdir(parents=True, exist_ok=True)
        line = {"gen": g, "best": st["best"], "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        t0 = time.time()
        data = gdir / "data" / "positions.npz"
        if not data.exists():
            opponents = [st["best"]] + st["kept"][-4:] + league
            tasks = max(1, a.positions // (150 * a.games_per_task))  # about 150 positions a game
            jobs = [(st["best"], opponents, a.sims, 1_000_000 * (g + 1) + i, a.games_per_task, a.bot_share,
                     a.teacher_share) for i in range(tasks)]
            with ctx.Pool(a.workers) as pool:
                res = pool.map(_positions, jobs, chunksize=1)
            x = np.concatenate([r[0] for r in res if len(r[0])])
            pv = np.concatenate([r[1] for r in res if len(r[1])])
            np.savez_compressed(data, x=x, p=pv)
            outs = [o for r in res for o in r[2]]
            line["positions"] = int(len(x))
            line["sharp_share"] = round(float((pv.max(1) > a.sharp).mean()), 3)
            line["rider_score"] = round(float(np.mean(outs)), 3)
            st["data"] = (st.get("data", []) + [str(data)])[-a.window:]
            state_path.write_text(json.dumps(st))
        line["positions_s"] = round(time.time() - t0)
        st["data"] = [d for d in st["data"] if Path(d).exists()]
        t1 = time.time()
        kids = [str(gdir / f"child{k}.npz") for k in range(a.children)]
        todo = [(st["best"], kids[k], st["data"], k, divs[(k // 2) % len(divs)], a.base_eta, a.lessons, a.rows,
                 "visits" if k % 2 == 0 else "argmax", a.sharp, a.crit_w, 10_000 * g + k)
                for k in range(a.children) if not Path(kids[k]).exists()]
        if todo:
            with ctx.Pool(min(a.workers, len(todo))) as pool:
                line["children"] = pool.map(_child, todo, chunksize=1)
        line["children_s"] = round(time.time() - t1)
        t2 = time.time()
        top, accepted, info = select_exit.sprt_gate(kids, st["best"], g, gate, league)
        line["gate_s"] = round(time.time() - t2)
        line["gate"] = {"accepted": accepted, "top": top, "survivors": info["survivors"],
                        "voronoi": info["voronoi"], "h2h": info["h2h"], "league": info["league"]}
        if accepted:
            keep = out / f"best-g{g + 1}.npz"
            shutil.copy(top, keep)
            st["kept"].append(str(keep))
            st["best"] = str(keep)
            r = r3eval.readings([(str(keep), "voronoi", a.read_pairs, r3eval.CHECKPOINT),
                                 (str(keep), "voronoi3", a.read_pairs // 2, r3eval.CHECKPOINT)], a.workers)
            r2 = r3eval.readings([(str(keep), "voronoi", a.read_pairs, r3eval.CONFIRM)], a.workers)
            line["reading"] = {"voronoi_checkpoint": r[(str(keep), "voronoi")],
                               "voronoi_confirmation": r2[(str(keep), "voronoi")],
                               "voronoi3_checkpoint": r[(str(keep), "voronoi3")]}
        for k in kids:  # children stay only as the kept brain
            if Path(k).exists():
                os.remove(k)
        line["seconds"] = round(time.time() - t0)
        with open(out / "generations.jsonl", "a") as f:
            f.write(json.dumps(line, default=str) + "\n")
        st["gen"] = g + 1
        state_path.write_text(json.dumps(st))
        sync(out, a.s3)
        print(json.dumps({k: line.get(k) for k in ("gen", "positions", "rider_score", "seconds")} |
                         {"accepted": accepted, "reading": line.get("reading")}, default=str), flush=True)
    (out / "DONE").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    sync(out, a.s3)


if __name__ == "__main__":
    main()
