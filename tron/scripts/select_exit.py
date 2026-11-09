"""selection across short expert-iteration branches.

    python scripts/select_exit.py --start runs/r3/best/exit-s32-m40000.npz --out runs/r3/c/sel-mako \
        --children 16 --moments 2500 --s3 s3://<bucket>/r3/c/sel-mako

Every generation g, from the current best brain:
1. `--children` branches; child k divides the learner's rates by an item of `--eta-divs` and
   gives its own move an item of `--priors` leaf units (a small sweep over the step size and the
   prior inside the selection), and is raised for `--moments` moments of expert iteration: a
   `--depth`-round alpha-beta with the prior on the branch's own greedy move labels every
   position it reaches against the labelling opponents (`phasec.LABEL_OPPS`).
2. Stage 1: every branch and the best play `--gate-pairs` mirror pairs against `voronoi` on
   this generation's gate seeds (4,500,000 + 1,000 g, fresh each generation, gate-only).
3. Stage 2: the `--finalists` best branches and the best play `--gate-pairs` more pairs against
   `voronoi` on a second fresh set (4,500,500 + 1,000 g), and the finalists play the best
   (seeds 4,000,000 + 1,000 g). The pick is the finalist best on stage 2 (the maximum over all
   branches on stage 1 alone carries its noise).
4. The pick replaces the best only if it is not lower than the best on both gate sets AND
   scores at least 0.45 against the best. A rejected pick is kept as `top-g<g>.npz`.
5. A new best plays 128 pairs against `voronoi` on the checkpoint seeds (2,200,000+), written
   to report.jsonl in the expert-iteration format with `cand-m<N>.npz` beside it; read it on the
   confirmation seeds (7,000,000+) with `scripts/r3eval.py` before trusting it.

Resumable: state.json holds the generation and the best brain's path.
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
from dataclasses import replace
from multiprocessing import get_context

# Process pools fork on Linux; on macOS a fork after NumPy or Numba threads have run can hang,
# so pools spawn there. TRON_MP=fork|spawn|forkserver overrides.
MP = os.environ.get("TRON_MP") or ("spawn" if sys.platform == "darwin" else "fork")
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tron import absearch  # noqa: E402
from tron.field import make_sense3  # noqa: E402
from tron.world import Arena, mulberry32  # noqa: E402
from phasec import OPP, LABEL_OPPS  # noqa: E402
import r3eval  # noqa: E402

SEE = make_sense3("field")[0]


def _after(ar, m, r):
    """The arena after my move m and the reply r (a copy)."""
    n = Arena(ar.size, ar.seed, list(ar.grid), list(ar.heads), list(ar.headings), list(ar.alive), ar.tick, ar.over, ar.winner)
    n.step((m, r))
    return n


def value_labels(games, moves, depth, prior, vbrain, readout, vtol):
    """the search's move, except where several moves are within `vtol` leaf units of
    the best: there the move whose worst reply leaves the best value (the readout of the value
    brain's settled state, 1 a win, 0 a loss; finished games by their result)."""
    from value_readout import value_of
    y, ties, pending = [], {}, []
    for i, g in enumerate(games):
        mv, vals = absearch.search(g["arena"], 0, depth, int(moves[i]), prior)
        y.append(mv)
        top = vals.max()
        cand = [m for m in range(3) if vals[m] >= top - vtol and vals[m] > -absearch.BIG // 2]
        if len(cand) > 1:
            ties[i] = cand
            for m in cand:
                for r in range(3):
                    pending.append((i, m, _after(g["arena"], m, r)))
    if pending:
        live = [k for k, (_, _, n) in enumerate(pending) if not n.over]
        v = np.array([1.0 if n.winner == 0 else 0.5 if n.winner is None else 0.0 for _, _, n in pending])
        if live:
            vbrain.reset()
            v[live] = value_of(vbrain, readout, np.stack([SEE(pending[k][2], 0) for k in live]).astype(np.float64))
        worst = {}
        for (i, m, _), val in zip(pending, v):
            worst[(i, m)] = min(worst.get((i, m), 2.0), val)
        for i, cand in ties.items():
            y[i] = max(cand, key=lambda m: (worst[(i, m)], m == y[i]))
    return np.array(y), len(ties)


def _pfsp(names, record, base, floor, rng):
    """Prioritized fictitious self-play: weight (1 - the child's score over its last 50 games
    against the opponent)^2, at least `floor`, times the opponent's base weight."""
    w = [max((1.0 - (float(np.mean(record[n][-50:])) if record.get(n) else 0.5)) ** 2, floor) * base.get(n, 1.0) for n in names]
    return rng.choices(names, w)[0]


def branch(args):
    best, out, seed, moments, rows, eta_div, depth, prior, backend, base_eta = args[:10]
    value = args[10] if len(args) > 10 else None
    pool = args[11] if len(args) > 11 else None
    from cadence import Brain
    brain = Brain.load(best, backend=backend)
    c = brain.learner.config
    # The rates divide the start brain's rates (state.json), not the saved best's, which a
    # kept branch already carries divided.
    brain.retune(learning=replace(c, eta=base_eta[0] / eta_div, eta_bias=base_eta[1] / eta_div))
    brain.reset()
    if value:
        z = np.load(value[0])
        readout = {"w": z["w"], "b": float(z["b"]), "idx": z["idx"]}
        vbrain = Brain.load(str(z["brain"]), backend="cpu")
    rng = random.Random(seed)
    # self-play against a pool (AlphaZero / AlphaStar). `pool`: anchors (bots
    # "bot:<name>" and brain paths) drawn with probability `anchor_share`, else the line's
    # selves (the current best, its kept generations, its exploiters); within each group PFSP.
    # An exploiter child plays only the current best. Soft targets: the search's root scores
    # through a softmax at temperature `soft` (leaf units); critical positions weigh `crit_w`.
    pool = pool or {}
    record = {}
    opp_brains = {}

    def opp_brain(path):
        if path not in opp_brains:
            ob = Brain.load(path, backend="cpu")
            ob.reset()
            opp_brains[path] = ob
        return opp_brains[path]

    def fresh():
        s = rng.randrange(1 << 30)
        if pool.get("exploit"):
            opp = pool["selves"][0]
        elif pool:
            group = pool["anchors"] if rng.random() < pool["anchor_share"] else pool["selves"]
            opp = _pfsp(group, record, pool.get("base", {}), pool.get("floor", 0.05), rng)
        else:
            opp = "bot:" + LABEL_OPPS[rng.randrange(len(LABEL_OPPS))]
        return {"arena": Arena(24, seed=s), "draw": mulberry32(s), "opp": opp}
    games = [fresh() for _ in range(rows)]
    soft, crit_w = pool.get("soft"), pool.get("crit_w", 1.0)
    for step in range(moments):
        if backend == "torch" and step % 50 == 49:
            # without this a child's CUDA cache grows to several GB in a generation;
            # emptied every 50 moments it stays near 330 MB.
            import torch
            torch.cuda.empty_cache()
        x = np.stack([SEE(g["arena"], 0) for g in games])
        try:
            brain.reset()  # play from rest, as the lessons train
            moves = np.asarray(brain.act(x, greedy=True)).reshape(-1)
            if value:
                y, _ = value_labels(games, moves, depth, prior, vbrain, readout, value[1])
                brain.lesson(x, y)
            else:
                res = [absearch.search(g["arena"], 0, depth, int(moves[i]), prior) for i, g in enumerate(games)]
                w = np.array([crit_w if (r[1].max() - r[1].min()) > absearch.BIG // 4 else 1.0 for r in res])
                if soft:
                    v = np.array([np.clip(r[1].astype(float), -400.0, 400.0) for r in res])
                    t = np.exp((v - v.max(1, keepdims=True)) / soft)
                    brain.lesson(x, targets=t / t.sum(1, keepdims=True), weights=w)
                elif crit_w != 1.0:
                    brain.lesson(x, np.array([r[0] for r in res]), weights=w)
                else:
                    brain.lesson(x, np.array([r[0] for r in res]))
        except RuntimeError:
            brain.reset()
            moves = np.ones(rows, int)
        theirs = {}
        for path in {g["opp"] for g in games if not g["opp"].startswith("bot:")}:
            idx = [i for i, g in enumerate(games) if g["opp"] == path]
            ob = opp_brain(path)
            ob.reset()  # every pool brain has a working-trace amplitude of 0
            got = np.asarray(ob.act(np.stack([SEE(games[i]["arena"], 1) for i in idx]).astype(np.float64), greedy=True)).reshape(-1)
            theirs.update(zip(idx, (int(v) for v in got)))
        for i, g in enumerate(games):
            ar = g["arena"]
            o = theirs[i] if i in theirs else OPP[g["opp"][4:]](ar, 1, g["draw"])
            ar.step((int(moves[i]), o))
            if ar.over:
                record.setdefault(g["opp"], []).append(1.0 if ar.winner == 0 else 0.5 if ar.winner is None else 0.0)
                games[i] = fresh()
    brain.reset()
    brain.save(out)
    return out


def _crit_agreement(path):
    """Agreement with ab5 on the critical positions of the fixed turn set (a cheap early filter)."""
    from cadence import Brain
    ts = np.load("runs/r3/turnset.npz")
    crit = ts["crit"].astype(bool)
    b = Brain.load(path, backend="cpu")
    b.reset()
    got = np.array([int(b.act(x[None, :].astype(np.float64), greedy=True)[0]) for x in ts["x"][crit]])
    return path, float((got == ts["y"][crit]).mean())


def sprt_gate(kids, best, g, a, league):
    """the sequential gate. Returns (top or None, accepted, info).

    1. Children whose agreement with ab5 on the critical turn-set positions is more than
       `--crit-slack` under the best's are dropped; at most `--survivors` (highest agreement) go on.
    2. Survivors and the best play mirror pairs against voronoi in batches of `--batch` pairs on
       this generation's seeds (5,000,000 + 1,000 g); for each survivor the paired difference
       (its pair score less the best's on the same seed) is tested: H0 mean 0 against H1 mean
       `--delta`, alpha = beta = `--alpha` (normal-approximation SPRT, bounds ln(beta/(1-alpha))
       and ln((1-beta)/alpha)); at `--cap` pairs an undecided survivor passes if its log-likelihood ratio is above 0
       (truncated SPRT: the side the evidence leans to).
    3. Survivors accepting H1, best mean difference first: the head-to-head against the best
       (seeds 10,000,000 + 1,000 g), H0 mean `--min-vs-best` - 0.04 against H1 `--min-vs-best` +
       0.04; then each league brain j (seeds 11,000,000 + 100,000 j + 1,000 g) with the floor
       `--league-floor`. The first survivor passing every test is the pick.
    """
    lo_b, hi_b = np.log(a.alpha / (1 - a.alpha)), np.log((1 - a.alpha) / a.alpha)
    with get_context(MP).Pool(min(a.workers, len(kids) + 1)) as pool:
        ca = dict(pool.map(_crit_agreement, kids + [best], chunksize=1))
    surv = sorted([k for k in kids if ca[k] >= ca[best] - a.crit_slack], key=lambda k: -ca[k])[:a.survivors]
    info = {"crit_agreement": ca, "survivors": surv, "voronoi": {}, "h2h": {}, "league": {}}
    base = 5_000_000 + 1000 * g
    sc = {k: {} for k in surv + [best]}
    live, passed, n = list(surv), [], 0
    while live and n < a.cap:
        hi = min(n + a.batch, a.cap)
        res = r3eval.pair_scores([(k, "voronoi", n, hi, base) for k in live + [best]], a.workers)
        for k in live + [best]:
            sc[k].update(res[(k, "voronoi", base)])
        n = hi
        for k in list(live):
            d = [sc[k][i] - sc[best][i] for i in range(n)]
            l = r3eval.llr(d, 0.0, a.delta)
            info["voronoi"][k] = {"pairs": n, "mean": float(np.mean([sc[k][i] for i in range(n)])),
                                  "best_mean": float(np.mean([sc[best][i] for i in range(n)])),
                                  "diff": float(np.mean(d)), "llr": l}
            if l >= hi_b:
                passed.append(k)
                live.remove(k)
            elif l <= lo_b:
                live.remove(k)
    # Undecided at the cap and leaning to H1: confirmation on 128 pairs of a fresh seed set
    # (14,000,000 + 1,000 g); kept only if it beats the best there too.
    lean = [k for k in live if info["voronoi"][k]["llr"] > 0]
    if lean:
        cbase = 14_000_000 + 1000 * g
        rc = r3eval.pair_scores([(k, "voronoi", 0, 128, cbase) for k in lean + [best]], a.workers)
        for k in lean:
            d = [rc[(k, "voronoi", cbase)][i] - rc[(best, "voronoi", cbase)][i] for i in sorted(rc[(best, "voronoi", cbase)])]
            info["voronoi"][k]["confirm_diff"] = float(np.mean(d))
            if np.mean(d) > 0:
                passed.append(k)
    passed.sort(key=lambda k: -info["voronoi"][k]["diff"])

    def seq(k, opp, base2, floor):
        s2, m = {}, 0
        while m < a.cap:
            hi = min(m + a.batch, a.cap)
            s2.update(r3eval.pair_scores([(k, opp, m, hi, base2)], a.workers)[(k, opp, base2)])
            m = hi
            x = [s2[i] for i in range(m)]
            l = r3eval.llr(x, floor - 0.04, floor + 0.04)
            if l >= hi_b or l <= lo_b:
                break
        out = {"pairs": m, "mean": float(np.mean(x)), "llr": l, "pass": bool(l >= hi_b)}
        if m >= a.cap and lo_b < l < hi_b and l > 0:
            # undecided at the cap, leaning to H1: 128 pairs on a fresh seed set must reach the floor
            cb = base2 + 600
            xc = list(r3eval.pair_scores([(k, opp, 0, 128, cb)], a.workers)[(k, opp, cb)].values())
            out["confirm_mean"] = float(np.mean(xc))
            out["pass"] = bool(np.mean(xc) >= floor)
        return out
    for k in passed:
        h = seq(k, "brain:" + best, 10_000_000 + 1000 * g, a.min_vs_best)
        info["h2h"][k] = h
        if not h["pass"]:
            continue
        ok = True
        for j, q in enumerate(league):
            lv = seq(k, "brain:" + q, 11_000_000 + 100_000 * j + 1000 * g, a.league_floor)
            info["league"].setdefault(k, []).append(lv)
            if not lv["pass"]:
                ok = False
                break
        if ok:
            return k, True, info
    top = passed[0] if passed else (max(surv, key=lambda k: info["voronoi"].get(k, {}).get("diff", -1)) if surv else None)
    return top, False, info


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--children", type=int, default=14)
    p.add_argument("--moments", type=int, default=2500)
    p.add_argument("--rows", type=int, default=32)
    p.add_argument("--eta-divs", default="2,3,4,6", help="child k divides the rates by item k mod len")
    p.add_argument("--priors", default="8,4,16", help="child k uses prior item (k // len(eta-divs)) mod len")
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--gate-pairs", type=int, default=64)
    p.add_argument("--finalists", type=int, default=3)
    p.add_argument("--gens", type=int, default=40)
    p.add_argument("--workers", type=int, default=32)
    p.add_argument("--backend", default="cpu")
    p.add_argument("--s3", default=None)
    p.add_argument("--sprt", action="store_true", help="the sequential gate")
    p.add_argument("--delta", type=float, default=0.04)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--cap", type=int, default=512)
    p.add_argument("--survivors", type=int, default=6)
    p.add_argument("--crit-slack", type=float, default=0.03)
    p.add_argument("--league-floor", type=float, default=0.47)
    p.add_argument("--min-vs-best", type=float, default=0.45, help="the pick's least score against the best")
    p.add_argument("--pipeline", action="store_true", help="train the next generation's children during the gate")
    p.add_argument("--base-eta", type=float, default=0.0, help="the rate the divisors divide (0: the start brain's)")
    p.add_argument("--selfplay", action="store_true", help="children play the line's selves and anchors")
    p.add_argument("--anchors", default=None, help="comma-separated anchors: bot:<name> or brain paths")
    p.add_argument("--anchor-share", type=float, default=0.2)
    p.add_argument("--softs", default="", help="temperatures for the soft-target children (even children); odd children argmax")
    p.add_argument("--crit-w", type=float, default=2.5)
    p.add_argument("--exploiter", action="store_true", help="the last child plays only the current best and joins the pool")
    p.add_argument("--selves", type=int, default=8, help="past kept generations in the pool")
    p.add_argument("--train-half", action="store_true", help="children 2m and 2m+1 share step and prior")
    p.add_argument("--league", default=None, help="comma-separated past brains the finalists also play in stage 2")
    p.add_argument("--value", default=None, help="value.npz (value_readout.py): value-aided labels")
    p.add_argument("--reference", default=None, help="a brain each kept generation also plays (self-play lines)")
    p.add_argument("--check-pairs", type=int, default=128, help="pairs of the kept generation's voronoi reading")
    p.add_argument("--read-pairs", type=int, default=64, help="pairs of its voronoi3 / ab5 / reference readings")
    p.add_argument("--vtols", default="6,12,24", help="child k: leaf units (item k mod len) within the best search value that the readout decides")
    a = p.parse_args()
    out = Path(a.out)
    (out / "branches").mkdir(parents=True, exist_ok=True)
    sp = out / "state.json"
    st = json.loads(sp.read_text()) if sp.exists() else {"gen": 0, "best": a.start, "history": []}
    (out / "meta.json").write_text(json.dumps({"arm": "selection", "sense": "field", "args": vars(a)}, indent=1))
    if a.base_eta:
        st["base_eta"] = [a.base_eta, a.base_eta / 10]  # a fixed reference rate
    if "base_eta" not in st:
        from cadence import Brain
        c = Brain.load(a.start, backend="cpu").learner.config
        st["base_eta"] = [c.eta, c.eta_bias]
    divs = [float(v) for v in a.eta_divs.split(",")]
    priors = [int(v) for v in a.priors.split(",")]
    vtols = [float(v) for v in a.vtols.split(",")]
    log = open(out / "generations.jsonl", "a")
    # with --train-half, children 2m and 2m+1 share their step and prior (a paired comparison)
    hk = (lambda k: k // 2) if a.train_half else (lambda k: k)
    hp = [(divs[hk(k) % len(divs)], priors[(hk(k) // len(divs)) % len(priors)]) for k in range(a.children)]
    softs = [float(v) for v in a.softs.split(",") if v]
    anchors = [q for q in (a.anchors.split(",") if a.anchors else []) if q]

    def make_jobs(g, best):
        selves = [best] + sorted((str(q) for q in out.glob("best-g*.npz") if str(q) != best),
                                 key=lambda q: -int(Path(q).stem[6:]))[:a.selves] + sorted(str(q) for q in out.glob("league/*.npz"))

        def tl(k):
            if not a.selfplay:
                return None
            spec = {"anchors": anchors, "anchor_share": a.anchor_share, "selves": selves, "floor": 0.05,
                    "base": {"bot:ab5": 0.3}, "crit_w": a.crit_w,
                    "soft": softs[(k // 2) % len(softs)] if softs and k % 2 == 0 else None}
            if a.exploiter and k == a.children - 1:
                spec["exploit"] = True
            return spec
        jobs = [(best, str(out / "branches" / f"g{g}-b{k}.npz"), 1_000_003 * (g + 1) + 7919 * k, a.moments, a.rows,
                 hp[k][0], a.depth, hp[k][1], a.backend, st["base_eta"], (a.value, vtols[k % len(vtols)]) if a.value else None,
                 tl(k)) for k in range(a.children)]
        return jobs, tl

    # a persistent pool for the children (a fresh process per child) and, with
    # --pipeline, generation g+1's children train from the current best while generation g is in
    # its gate (most generations are rejected; a kept one makes them its siblings, gated against it).
    cpool = get_context(MP).Pool(a.children, maxtasksperchild=1)
    ahead = None
    while st["gen"] < a.gens:
        g, best = st["gen"], st["best"]
        t0 = time.time()
        if ahead is not None and ahead[0] == g:
            _, born_of, res, tl = ahead
        else:
            jobs, tl = make_jobs(g, best)
            born_of, res = best, cpool.map_async(branch, jobs, chunksize=1)
        kids = res.get()
        ahead = None
        if a.pipeline and g + 1 < a.gens:
            jobs2, tl2 = make_jobs(g + 1, best)
            ahead = (g + 1, best, cpool.map_async(branch, jobs2, chunksize=1), tl2)
        if a.selfplay and a.exploiter:
            # the exploiter is not a candidate: it joins the line's pool as an opponent
            (out / "league").mkdir(exist_ok=True)
            os.replace(kids.pop(-1), out / "league" / f"exploiter-g{g}.npz")
        t1 = time.time()
        league = [q for q in (a.league.split(",") if a.league else []) if q and q != best]
        if a.sprt:
            top, accept, info = sprt_gate(kids, best, g, a, league)
            line = {"gen": g, "best_in": best, "gate": "sprt", "info": info, "top": top, "accepted": accept,
                    "branches": [{"path": k, "eta_div": hp[i][0], "prior": hp[i][1],
                                  "soft": (tl(i) or {}).get("soft")} for i, k in enumerate(kids)],
                    "branch_min": round((t1 - t0) / 60, 1), "wall_min": round((time.time() - t0) / 60, 1)}
            v = info["voronoi"].get(top, {}) if top else {}
            summary = {"gen": g, "gate": "sprt", "survivors": len(info["survivors"]), "top_pairs": v.get("pairs"),
                       "top_mean": v.get("mean"), "best_mean": v.get("best_mean"), "diff": v.get("diff"),
                       "h2h": info["h2h"].get(top, {}).get("mean") if top else None, "accepted": accept}
        else:
            # Stage 1: every branch and the best, gate pairs against voronoi (fresh seeds per generation).
            gbase, gbase2, dbase = r3eval.GATE + 1000 * g, r3eval.GATE + 1000 * g + 500, r3eval.DUEL + 1000 * g
            r1 = r3eval.readings([(k, "voronoi", a.gate_pairs, gbase) for k in kids + [best]], a.workers)
            gv = {k: r1[(k, "voronoi")]["score"] for k in kids + [best]}
            fin = sorted(kids, key=lambda k: -gv[k])[:a.finalists]
            # Stage 2: the finalists and the best on a second fresh set (the pick is made on it, so
            # the maximum over many branches does not carry stage 1's noise), and the finalists
            # against the best.
            league = [q for q in (a.league.split(",") if a.league else []) if q and q != best]
            r2 = r3eval.readings([(k, "voronoi", a.gate_pairs, gbase2) for k in fin + [best]]
                                 + [(k, "brain:" + best, a.gate_pairs, dbase) for k in fin]
                                 + [(k, "brain:" + q, a.gate_pairs, dbase + 300 + 50 * j) for j, q in enumerate(league) for k in fin],
                                 a.workers)
            gv2 = {k: r2[(k, "voronoi")]["score"] for k in fin + [best]}
            dv = {k: r2[(k, "brain:" + best)]["score"] for k in fin}
            lv = {k: [r2[(k, "brain:" + q)]["score"] for q in league] for k in fin}
            if league:
                # the league (the best and the named past brains) in the gate; the pick
                # maximizes the second voronoi set plus the mean score against the league.
                lm = {k: float(np.mean([dv[k]] + lv[k])) for k in fin}
                top = max(fin, key=lambda k: gv2[k] + lm[k])
                accept = gv[top] >= gv[best] and gv2[top] >= gv2[best] and lm[top] >= 0.5 and dv[top] >= min(0.4, a.min_vs_best)
            else:
                top = max(fin, key=lambda k: gv2[k])
                accept = gv[top] >= gv[best] and gv2[top] >= gv2[best] and dv[top] >= a.min_vs_best
            line = {"gen": g, "best_in": best, "best_gate_voronoi": gv[best], "best_gate2_voronoi": gv2[best],
                    "branches": [{"path": k, "eta_div": hp[i][0], "prior": hp[i][1],
                                  "vtol": vtols[i % len(vtols)] if a.value else None, "gate_voronoi": gv[k],
                                  "gate2_voronoi": gv2.get(k), "vs_best": dv.get(k), "vs_league": lv.get(k)} for i, k in enumerate(kids)],
                    "top": top, "accepted": accept, "branch_min": round((t1 - t0) / 60, 1),
                    "wall_min": round((time.time() - t0) / 60, 1)}
            summary = {"gen": g, "top_gate": gv[top], "top_gate2": gv2[top], "best_gate": gv[best],
                       "best_gate2": gv2[best], "vs_best": dv[top], "accepted": accept}
        if accept:
            keep = out / f"best-g{g + 1}.npz"
            os.replace(top, keep)
            st["best"] = str(keep)
            r = r3eval.reading(str(keep), "voronoi", a.check_pairs, r3eval.CHECKPOINT, a.workers)
            line["checkpoint_voronoi"] = r
            if a.selfplay:
                # each kept generation against voronoi3 and ab5 (64 pairs), and against a reference
                # brain (--reference, e.g. the line's start) where one is named
                jobs = [(str(keep), "voronoi3", a.read_pairs, r3eval.CHECKPOINT), (str(keep), "ab5", a.read_pairs, r3eval.CHECKPOINT)]
                if a.reference:
                    jobs.append((str(keep), "brain:" + a.reference, a.read_pairs, r3eval.MAKO))
                ex = r3eval.readings(jobs, a.workers)
                line["readings"] = {"voronoi3": ex[(str(keep), "voronoi3")], "ab5": ex[(str(keep), "ab5")]}
                if a.reference:
                    line["readings"]["reference"] = ex[(str(keep), "brain:" + a.reference)]
            moments = (g + 1) * a.moments
            cand = out / f"cand-m{moments}.npz"
            if not cand.exists():
                os.link(keep, cand)
            with open(out / "report.jsonl", "a") as f:
                f.write(json.dumps({"moments": moments, "generation": g + 1, "brain": {"voronoi": r}}) + "\n")
        elif top:
            os.replace(top, out / f"top-g{g}.npz")  # the rejected pick is kept, never overwritten
        for k in kids:
            if Path(k).exists():
                os.remove(k)  # other branches: gate scores in generations.jsonl
        line["born_of"] = born_of
        log.write(json.dumps(line) + "\n")
        log.flush()
        summary["checkpoint"] = line.get("checkpoint_voronoi", {}).get("score")
        for k2, v2 in line.get("readings", {}).items():
            summary[k2] = v2["score"]
        print(json.dumps(summary), flush=True)
        st["gen"] = g + 1
        st["history"].append({"gen": g, "accepted": accept, "best": st["best"]})
        sp.write_text(json.dumps(st, indent=1))
        if a.s3:
            subprocess.run(["aws", "s3", "sync", str(out), a.s3, "--only-show-errors", "--exclude", "branches/*"], check=False)


if __name__ == "__main__":
    main()
