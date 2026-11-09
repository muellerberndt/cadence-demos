"""make the brain beat `voronoi`. One arm per process, resumable.

    python scripts/phasec.py --arm abdagger --start runs/r3/b/win-instruct-s21/brain-m100000.npz \
        --sense field --seed 31 --out runs/r3/c/abdagger-s31

| arm | what the brain learns from | game-time player |
| abdagger | DAgger: `ab5` (alpha-beta, 5 rounds = 10 ply, Voronoi leaf) labels every position the brain reaches | the brain alone |
| exit | expert iteration: a 3-round alpha-beta whose root adds `--prior` leaf units to the brain's own greedy move labels the position; every `--gen` moments the new generation plays the previous one (32 mirror pairs) and is kept only if it scores above 0.5, else the previous generation is restored | the brain alone |
| territory | a new brain with two Voronoi-ownership planes added to the sense (`field_vor`), same genome: corpus school, then as `abdagger` | the brain alone (reported separately) |
| league | outcome learning (`step`) against a prioritized league: `voronoi`, `voronoi3`, `ab5` and its own past checkpoints; every 2,000 moments the opponent is drawn with weight (1.05 - its running score against it)^2 | the brain alone |

Opponents while labelling (abdagger, exit, territory): `voronoi` (twice), `voronoi3`, `ab5`,
`voronoi20`, `survivor`, `chaser`, `hugger`, `racer`, drawn per game.

Checkpoints every `--every` moments: the brain saved; a frozen CPU twin plays 32 mirror pairs
(64 games) against each of `voronoi`, `voronoi3` and `ab5` on seeds 2,200,000+ (never used for
training or selection), with 95% intervals; the scenario tests; the hybrid player (the brain's
move as the prior of a 2-round alpha-beta, bonus 8) plays the same games; one line in
report.jsonl; S3 sync then and hourly.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import time
import warnings
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tron import absearch, bots, fastbots, r3, scenarios, school  # noqa: E402
from tron.field import make_sense3  # noqa: E402
from tron.world import Arena, mulberry32  # noqa: E402

TEACHER_DEPTH = 5
EXIT_DEPTH = 3
OPP = dict(school.POOL)
OPP["voronoi3"] = lambda a, s, d: fastbots.voronoi3(a, s)
OPP["ab5"] = lambda a, s, d: absearch.search(a, s, TEACHER_DEPTH)[0]
LABEL_OPPS = ("voronoi", "voronoi", "voronoi3", "ab5", "voronoi20", "survivor", "chaser", "hugger", "racer")
HEAD = ("voronoi", "voronoi3", "ab5")
EVAL_SEED = 2_200_000


def _label(args):
    """The search's move and whether the position is critical (some move scores a loss)."""
    arena, depth, prior, bonus = args
    move, values = absearch.search(arena, 0, depth, prior, bonus)
    return move, bool(values.max() - values.min() > absearch.BIG // 4)


def head_to_head(pol, opp, pairs, reset=None):
    w = l = d = 0
    for i in range(pairs):
        s = EVAL_SEED + i
        for seat in (0, 1):
            a = Arena(24, seed=s)
            draw = mulberry32(s)
            if reset:
                reset()
            while not a.over:
                mine = pol(a, seat)
                theirs = OPP[opp](a, 1 - seat, draw)
                a.step((mine, theirs) if seat == 0 else (theirs, mine))
            w += a.winner == seat
            l += a.winner == 1 - seat
            d += a.winner is None
    n = 2 * pairs
    sc = (w + 0.5 * d) / n
    return {"wins": int(w), "losses": int(l), "draws": int(d), "score": sc, "ci95": 1.96 * math.sqrt(max(sc * (1 - sc), 1e-9) / n)}


def duel(pol_a, pol_b, pairs, reset_a, reset_b, base=4_000_000):
    """Score of A against B over mirror pairs (gating; seeds 4,000,000+ are gate-only)."""
    sc = 0.0
    for i in range(pairs):
        s = base + i
        for seat in (0, 1):
            a = Arena(24, seed=s)
            reset_a(); reset_b()
            while not a.over:
                x, y = pol_a(a, seat), pol_b(a, 1 - seat)
                a.step((x, y) if seat == 0 else (y, x))
            sc += 1.0 if a.winner == seat else 0.5 if a.winner is None else 0.0
    return sc / (2 * pairs)


def gate_voronoi(pol, reset, pairs, base=4_500_000):
    sc = 0.0
    for i in range(pairs):
        s = base + i
        for seat in (0, 1):
            a = Arena(24, seed=s)
            draw = mulberry32(s)
            reset()
            while not a.over:
                m, t = pol(a, seat), OPP["voronoi"](a, 1 - seat, draw)
                a.step((m, t) if seat == 0 else (t, m))
            sc += 1.0 if a.winner == seat else 0.5 if a.winner is None else 0.0
    return sc / (2 * pairs)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--arm", required=True, choices=["abdagger", "exit", "territory", "league", "abreplay", "exitreplay", "exitreplay2"])
    p.add_argument("--start", default=None, help="the school brain (all arms but territory)")
    p.add_argument("--genome", default="runs/r3/summary.json")
    p.add_argument("--rank", type=int, default=0)
    p.add_argument("--sense", default="field")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--rows", type=int, default=16)
    p.add_argument("--moments", type=int, default=100_000)
    p.add_argument("--watch", type=int, default=15000)
    p.add_argument("--every", type=int, default=10000)
    p.add_argument("--gen", type=int, default=10000)
    p.add_argument("--prior", type=int, default=8)
    p.add_argument("--pairs", type=int, default=32)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--backend", default="torch")
    p.add_argument("--s3", default=None)
    p.add_argument("--gate-pairs", type=int, default=32)
    p.add_argument("--voronoi-pairs", type=int, default=0, help="checkpoint pairs against voronoi (0: --pairs; exit arms: 128)")
    p.add_argument("--replay", type=int, default=0, help="replay rows per moment (0: none)")
    p.add_argument("--capacity", type=int, default=60000)
    p.add_argument("--surprise", action="store_true")
    p.add_argument("--gate-voronoi", action="store_true", help="exit: the exitreplay accept rule")
    p.add_argument("--exit-depth", type=int, default=EXIT_DEPTH, help="exit search rounds (2 ply each)")
    p.add_argument("--turn-share", type=float, default=0.5, help="share of replay rows drawn from turns")
    p.add_argument("--crit-weight", type=float, default=1.0, help="replay weight multiplier for critical positions")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from cadence import Brain

    if a.arm == "exitreplay2":
        # turns at their natural share, mistakes x3, critical positions x2.
        a.turn_share, a.crit_weight = 0.36, 2.0
    if a.arm in ("abreplay", "exitreplay", "exitreplay2"):
        # Fix arms: the base arm plus a turn-balanced mistake replay, surprise
        # lessons, and for exit the larger gate with the voronoi rule.
        a.replay = a.replay or a.rows
        a.surprise = True
        if a.arm in ("exitreplay", "exitreplay2"):
            a.gate_pairs = max(a.gate_pairs, 64)
            a.gate_voronoi = True
    base_arm = {"abreplay": "abdagger", "exitreplay": "exit", "exitreplay2": "exit"}.get(a.arm, a.arm)
    if not a.voronoi_pairs:
        a.voronoi_pairs = 128 if base_arm == "exit" else a.pairs
    sense = "field_vor" if a.arm == "territory" else a.sense
    see = make_sense3(sense)[0]
    sets = scenarios.load("runs/r3/scenarios.json")
    st = {"moments": 0, "t0": time.time(), "last_sync": time.time()}
    (out / "meta.json").write_text(json.dumps({"arm": a.arm, "sense": sense, "args": vars(a)}, indent=1))

    saved = sorted(out.glob("brain-m*.npz"), key=lambda q: int(q.stem[7:]))
    if saved:
        brain = Brain.load(str(saved[-1]), backend=a.backend)
        st["moments"] = int(saved[-1].stem[7:])
    elif a.arm == "territory":
        g = dict(json.loads(Path(a.genome).read_text())[a.rank]["genome"])
        g["sense"] = "field_vor"
        brain = r3.compose(g, a.seed, backend=a.backend)
        w = r3.watch(brain, "field_vor", a.watch, a.rows, a.seed)
        (out / "school.json").write_text(json.dumps(w))
    else:
        brain = Brain.load(a.start, backend=a.backend)
    brain.reset()
    if a.surprise:
        brain.retune(learning_surprise=True, learning_surprise_share=True)
    turnset = np.load("runs/r3/turnset.npz") if Path("runs/r3/turnset.npz").exists() else None
    buf_x = np.zeros((a.capacity, make_sense3(sense)[1]), np.float32) if a.replay else None
    buf_y = np.zeros(a.capacity, np.int64)
    buf_w = np.zeros(a.capacity)  # 1 + 2 if the brain missed it
    buf = {"n": 0, "i": 0}
    rrng = np.random.default_rng(a.seed)
    gens = json.loads((out / "gens.json").read_text()) if (out / "gens.json").exists() else {"kept": [], "rejected": []}
    league = [str(q) for q in saved]
    scores = {o: [0.5] for o in HEAD}

    def sync(force=False):
        if a.s3 and (force or time.time() - st["last_sync"] > 3000):
            subprocess.run(["aws", "s3", "sync", str(out), a.s3, "--only-show-errors"], check=False)
            st["last_sync"] = time.time()

    def twin_of(path):
        t = Brain.load(str(path), backend="cpu")
        t.reset()
        pol = r3.policy(t, sense)
        return t, pol

    def checkpoint():
        path = out / f"brain-m{st['moments']}.npz"
        brain.save(str(path))
        t, pol = twin_of(path)

        def hybrid(arena, seat):
            return absearch.search(arena, seat, 2, pol(arena, seat), a.prior)[0]
        t0 = time.time()
        line = {"moments": st["moments"], "wall_h": round((time.time() - st["t0"]) / 3600, 2),
                "brain": {o: head_to_head(pol, o, a.voronoi_pairs if o == "voronoi" else a.pairs, t.reset) for o in HEAD},
                "hybrid": {o: head_to_head(hybrid, o, a.pairs // 2, t.reset) for o in HEAD},
                "scenarios": scenarios.score(pol, sets, reset=t.reset)}
        if turnset is not None and sense == "field":
            got = np.array([int(t.act(x[None, :], greedy=True)[0]) for x in turnset["x"]])
            t.reset()
            y, turn, crit = turnset["y"], turnset["turn"].astype(bool), turnset["crit"].astype(bool)
            line["ab5_agreement"] = {"all": float((got == y).mean()), "turns": float((got == y)[turn].mean()),
                                     "critical": float((got == y)[crit].mean()), "positions": int(len(y))}
        line["eval_s"] = round(time.time() - t0)
        with open(out / "report.jsonl", "a") as f:
            f.write(json.dumps(line) + "\n")
        print(json.dumps({"moments": st["moments"], "vs_voronoi": line["brain"]["voronoi"]["score"],
                          "vs_voronoi3": line["brain"]["voronoi3"]["score"], "vs_ab5": line["brain"]["ab5"]["score"],
                          "hybrid_vs_voronoi": line["hybrid"]["voronoi"]["score"],
                          "turn_agreement": line.get("ab5_agreement", {}).get("turns")}), flush=True)
        league.append(str(path))
        brain.reset()
        sync(force=True)
        return path

    if not saved:
        checkpoint()
    pool = Pool(a.workers)
    rng = random.Random(a.seed * 7 + st["moments"])

    def fresh(opp=None):
        s = rng.randrange(1 << 30)
        return {"arena": Arena(24, seed=s), "draw": mulberry32(s), "opp": opp or LABEL_OPPS[rng.randrange(len(LABEL_OPPS))]}

    outcome = a.arm == "league"
    rows = [fresh() for _ in range(a.rows)]
    pending, reward, done = False, np.zeros(a.rows), np.zeros(a.rows, bool)
    opp_brain, opp_name, opp_sense = None, None, see
    gen_start = st["moments"]
    gen_path = league[-1] if league else None
    while st["moments"] < a.moments:
        k = st["moments"]
        if outcome and k % 2000 == 0:
            # Prioritized league: play most against whoever beats it.
            names = list(HEAD) + ["self"] * (1 if len(league) > 1 else 0)
            weights = [(1.05 - float(np.mean(scores.get(nm, [0.5])[-200:]))) ** 2 for nm in names]
            opp_name = rng.choices(names, weights)[0]
            if opp_name == "self":
                opp_brain, _ = twin_of(rng.choice(league[:-1] or league))
            else:
                opp_brain = None
            rows = [fresh(opp_name) for _ in range(a.rows)]
            if pending:
                x = np.stack([see(r["arena"], 0) for r in rows])
                brain.step(x, reward=reward, done=done)
                brain.act(x, greedy=True)
                pending = False
            brain.reset()
        x = np.stack([see(r["arena"], 0) for r in rows])
        try:
            if outcome:
                moves = np.asarray(brain.step(x, reward=reward, done=done) if pending else brain.step(x)).reshape(-1)
                pending = True
            else:
                moves = np.asarray(brain.act(x, greedy=True)).reshape(-1)
                if base_arm == "exit":
                    jobs = [(r["arena"], a.exit_depth, int(moves[i]), a.prior) for i, r in enumerate(rows)]
                else:
                    jobs = [(r["arena"], TEACHER_DEPTH, -1, 0) for r in rows]
                got = pool.map(_label, jobs)
                y = np.array([m for m, _ in got])
                crit = np.array([c for _, c in got])
                brain.lesson(x, y)
                if a.replay:
                    for i in range(len(y)):
                        j = buf["i"]
                        buf_x[j], buf_y[j] = x[i], y[i]
                        buf_w[j] = (1.0 + 2.0 * (moves[i] != y[i])) * (a.crit_weight if crit[i] else 1.0)
                        buf["i"] = (j + 1) % a.capacity
                        buf["n"] = min(buf["n"] + 1, a.capacity)
                    n = buf["n"]
                    if n >= 4 * a.replay:
                        # Turn-balanced: half the replay rows are turns, half straight, each
                        # drawn with weight 3 for the brain's mistakes, 1 otherwise.
                        idx = []
                        n_turn = int(round(a.replay * a.turn_share))
                        for want_turn, count in ((True, n_turn), (False, a.replay - n_turn)):
                            pool_i = np.flatnonzero((buf_y[:n] != 1) == want_turn)
                            if len(pool_i) and count:
                                w = buf_w[pool_i] / buf_w[pool_i].sum()
                                idx.append(rrng.choice(pool_i, count, p=w))
                        idx = np.concatenate(idx)
                        bx = buf_x[idx].astype(np.float64)
                        brain.reset()
                        brain.act(bx, greedy=True)
                        brain.lesson(bx, buf_y[idx])
                        brain.reset()
        except RuntimeError:
            brain.reset()
            pending = False
            moves = np.ones(a.rows, int)
        if opp_brain is not None:
            theirs = np.asarray(opp_brain.act(np.stack([see(r["arena"], 1) for r in rows]), greedy=True)).reshape(-1)
        reward, done = np.zeros(a.rows), np.zeros(a.rows, bool)
        for i, r in enumerate(rows):
            ar = r["arena"]
            o = int(theirs[i]) if (opp_brain is not None and r["opp"] == "self") else OPP[r["opp"]](ar, 1, r["draw"])
            ar.step((int(moves[i]), o))
            if ar.over:
                rr, _ = school.outcome(ar)
                reward[i], done[i] = rr, True
                score = 1.0 if ar.winner == 0 else 0.5 if ar.winner is None else 0.0
                scores.setdefault(r["opp"], []).append(score)
                rows[i] = fresh(r["opp"] if outcome else None)
        if opp_brain is not None and done.any():
            opp_brain.reset()
        st["moments"] += 1
        if st["moments"] % 1000 == 0:
            print(json.dumps({"progress": st["moments"], "wall_h": round((time.time() - st["t0"]) / 3600, 3),
                              "opp": opp_name}), flush=True)
        if st["moments"] % a.every == 0:
            if pending:
                x = np.stack([see(r["arena"], 0) for r in rows])
                brain.step(x, reward=reward, done=done)
                brain.act(x, greedy=True)
                pending = False
            path = checkpoint()
            if base_arm == "exit" and st["moments"] - gen_start >= a.gen and gen_path:
                tn, pn = twin_of(path)
                to, po = twin_of(gen_path)
                sc = duel(pn, po, a.gate_pairs, tn.reset, to.reset)
                rule = {"moments": st["moments"], "score_vs_previous": sc}
                accept = sc > 0.5
                if a.gate_voronoi:
                    # Gate starts 4,500,000+ (gate-only): the voronoi score of both generations.
                    vn = gate_voronoi(pn, tn.reset, a.gate_pairs // 2)
                    vo = gate_voronoi(po, to.reset, a.gate_pairs // 2)
                    rule.update(voronoi_new=vn, voronoi_previous=vo)
                    accept = sc > 0.5 or (sc >= 0.45 and vn > vo)
                if accept:
                    gens["kept"].append(rule)
                    gen_path = str(path)
                else:
                    gens["rejected"].append(rule)
                    # Keep the rejected candidate as cand-m<N>.npz; brain-m<N>.npz becomes the
                    # restored generation, the one training continues from (and resumes from).
                    os.replace(path, out / f"cand-m{st['moments']}.npz")
                    brain = Brain.load(gen_path, backend=a.backend)
                    brain.reset()
                    brain.save(str(path))
                gen_start = st["moments"]
                (out / "gens.json").write_text(json.dumps(gens, indent=1))
                print(json.dumps({"gate": st["moments"], "score": sc}), flush=True)
            elif base_arm == "exit" and gen_path is None:
                gen_path = str(path)
        sync()
    pool.close()
    (out / "DONE").write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
    sync(force=True)


if __name__ == "__main__":
    main()
