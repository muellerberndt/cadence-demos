"""the AlphaZero loop for one network.

    python scripts/az.py --start runs/r3/best/final-0909-deep.npz --out runs/r3/az/deep \
        --workers 32 --sims 100 --games 192 --backend torch

Per generation g (resumable from state.json):
1. Self-play: `--games` games of the current player (network + search, `tron/mcts.py`) against
   itself, with Dirichlet noise at every root (0.25, alpha 0.3) and the move drawn from the visit
   shares for the first `--explore` rounds; `--anchor-share` of the games are against a bot of
   `--anchors` (only the network's positions are kept). Every kept position stores the network's
   sense, the root's visit shares (the policy target) and the game's outcome from that side.
2. Training: a candidate = the current network, lessons of `--rows` positions drawn from the last
   `--window` generations, each settled from rest, `lesson(x, targets=visits, weights=w)` (w 2.5
   where the visit shares are sharp at the root, max share > 0.9 against an even prior; else 1),
   one pass over the window's new positions, the rate `--eta` (small steps).
3. Value: a logistic readout of the candidate's settled state (`--pops`) fitted on up to 40,000 of
   the window's positions and their outcomes (the leaf value of its search, blended with territory
   at `--lam`); held-out accuracy and Brier score reported.
4. Gate: the candidate player against the current player, mirror pairs at `--gate-sims`, a
   sequential test (H0 mean 0.5, H1 0.55, alpha = beta = 0.1, batches of 16 pairs, cap 128 pairs;
   at the cap the mean must exceed 0.5). Kept: the candidate becomes the current network.
5. Every generation: the current network alone, 64 mirror pairs against `voronoi` (checkpoint
   seeds); every `--probe-every` generations the current player (`--probe-sims`) against
   `voronoi`, `voronoi2`, `voronoi3`, `ab5` (32 pairs each). One line in generations.jsonl.
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
from dataclasses import replace
from multiprocessing import get_context

# Process pools fork on Linux; on macOS a fork after NumPy or Numba threads have run can hang,
# so pools spawn there. TRON_MP=fork|spawn|forkserver overrides.
MP = os.environ.get("TRON_MP") or ("spawn" if sys.platform == "darwin" else "fork")
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=DeprecationWarning)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tron import mcts, r3  # noqa: E402
from tron.field import make_sense3  # noqa: E402
from tron.world import Arena, mulberry32  # noqa: E402
from phasec import OPP  # noqa: E402
import r3eval  # noqa: E402

SEE = make_sense3("field")[0]


def _selfplay(args):
    net, value, lam, sims, backend, seeds, explore, anchors, anchor_share, out_path = args
    ev = mcts.Evaluator(net, value, lam, backend=backend)
    X, PI, Z, W = [], [], [], []
    for sd in seeds:
        rng = random.Random(sd)
        nrng = np.random.default_rng(sd)
        a, dr = Arena(24, seed=sd % (1 << 30)), mulberry32(sd % (1 << 30))
        bot = anchors[rng.randrange(len(anchors))] if anchors and rng.random() < anchor_share else None
        rec = {0: [], 1: []}
        rounds = 0
        while not a.over:
            moves = []
            for seat in (0, 1):
                if bot is not None and seat == 1:
                    moves.append(OPP[bot](a, 1, dr))
                    continue
                m, visits = mcts.search(a, seat, ev, sims, noise=0.25, rng=nrng)
                if rounds < explore:
                    m = int(nrng.choice(3, p=visits))
                rec[seat].append((SEE(a, seat).astype(np.float16), visits.astype(np.float32),
                                  2.5 if visits.max() > 0.9 else 1.0))
                moves.append(m)
            a.step(tuple(moves))
            rounds += 1
        for seat in (0, 1):
            z = 1.0 if a.winner == seat else 0.5 if a.winner is None else 0.0
            for x, pi, w in rec[seat]:
                X.append(x); PI.append(pi); Z.append(z); W.append(w)  # noqa: E702
    np.savez(out_path, x=np.array(X, np.float16), pi=np.array(PI, np.float32), z=np.array(Z, np.float32),
             w=np.array(W, np.float32))
    return out_path, len(X)


def _duel(args):
    """Per-pair scores of player A (net_a) against player B (net_b), both searching."""
    na, va, nb, vb, lam, sims, lo, hi, base, backend = args
    ea = mcts.Evaluator(na, va, lam, backend=backend)
    eb = mcts.Evaluator(nb, vb, lam, backend=backend)
    pa, pb = mcts.player(ea, sims), mcts.player(eb, sims)
    out = []
    for i in range(lo, hi):
        s = base + i
        sc = 0.0
        for seat in (0, 1):
            a = Arena(24, seed=s)
            while not a.over:
                m, o = pa(a, seat), pb(a, 1 - seat)
                a.step((m, o) if seat == 0 else (o, m))
            sc += 1.0 if a.winner == seat else 0.5 if a.winner is None else 0.0
        out.append(sc / 2)
    return lo, out


def _probe(args):
    net, value, lam, sims, opp, lo, hi, base, backend = args
    ev = mcts.Evaluator(net, value, lam, backend=backend)
    me = mcts.player(ev, sims)
    w = l = d = 0
    for i in range(lo, hi):
        s = base + i
        for seat in (0, 1):
            a, dr = Arena(24, seed=s), mulberry32(s)
            while not a.over:
                m, o = me(a, seat), OPP[opp](a, 1 - seat, dr)
                a.step((m, o) if seat == 0 else (o, m))
            w += a.winner == seat
            l += a.winner == 1 - seat
            d += a.winner is None
    return opp, w, l, d


def _botpairs(args):
    """Per-pair scores of a player (network + search) against a bot."""
    net, value, lam, sims, opp, lo, hi, base, backend = args
    ev = mcts.Evaluator(net, value, lam, backend=backend)
    me = mcts.player(ev, sims)
    out = []
    for i in range(lo, hi):
        s = base + i
        sc = 0.0
        for seat in (0, 1):
            a, dr = Arena(24, seed=s), mulberry32(s)
            while not a.over:
                m, o = me(a, seat), OPP[opp](a, 1 - seat, dr)
                a.step((m, o) if seat == 0 else (o, m))
            sc += 1.0 if a.winner == seat else 0.5 if a.winner is None else 0.0
        out.append(sc / 2)
    return net, opp, lo, out


def bot_check(new, new_v, old, old_v, lam, sims, g, workers, backend, bots=("voronoi", "voronoi2"), cap=64):
    """the new player no worse than the old against each bot. Paired per-pair score
    differences (new - old) on the same seeds (40,000,000 + 1,000 g + 200 j); sequential test of
    non-inferiority, H0 mean -0.05 against H1 mean 0, alpha = beta = 0.1, 16 pairs per batch, at
    the cap the mean must be at least -0.02."""
    lo_b, hi_b = math.log(0.1 / 0.9), math.log(0.9 / 0.1)
    ctx = get_context(MP)
    out = {}
    for j, opp in enumerate(bots):
        base = 40_000_000 + 1000 * g + 200 * j
        sc = {new: {}, old: {}}
        n = 0
        while n < cap:
            hi = min(n + 16, cap)
            tasks = [(net, v, lam, sims, opp, k, min(k + 2, hi), base, backend)
                     for net, v in ((new, new_v), (old, old_v)) for k in range(n, hi, 2)]
            with ctx.Pool(min(workers, len(tasks)), maxtasksperchild=1) as pool:
                for net, _, lo, vals in pool.map(_botpairs, tasks, chunksize=1):
                    for i, v in enumerate(vals):
                        sc[net][lo + i] = v
            n = hi
            d = [sc[new][i] - sc[old][i] for i in range(n)]
            l = r3eval.llr(d, -0.05, 0.0, min_n=16)
            if l >= hi_b or l <= lo_b:
                break
        md = float(np.mean(d))
        ok = bool(l >= hi_b or (n >= cap and l > lo_b and md >= -0.02))
        out[opp] = {"pairs": n, "new": float(np.mean([sc[new][i] for i in range(n)])),
                    "old": float(np.mean([sc[old][i] for i in range(n)])), "diff": md, "llr": l, "pass": ok}
        if not ok:
            break
    out["pass"] = all(v["pass"] for k, v in out.items() if k != "pass") and len(out) == len(bots)
    return out


def _features(args):
    net, pops, xs = args
    from cadence import Brain
    b = Brain.load(net, backend="cpu")
    idx = np.concatenate([np.array(sorted(b.connectome.populations[q])) for q in pops.split(",")])
    out = []
    for k in range(0, len(xs), 64):
        x = xs[k:k + 64].astype(np.float64)
        b.reset()
        b.act(x, greedy=True)
        out.append(np.asarray(b._activity().activation).reshape(len(x), -1)[:, idx].astype(np.float32))
    return np.vstack(out)


def _train(args):
    """A candidate: the network taught the batch's visit shares, settled from rest per lesson."""
    net, batch, out_path, eta, rows, backend = args
    from cadence import Brain
    d = np.load(batch)
    cand = Brain.load(net, backend=backend)
    c = cand.learner.config
    cand.retune(learning=replace(c, eta=eta, eta_bias=eta / 10))
    X, PI, W = d["x"], d["pi"], d["w"]
    for k in range(0, len(X) - rows + 1, rows):
        cand.reset()
        cand.lesson(X[k:k + rows].astype(np.float64), targets=PI[k:k + rows].astype(np.float64),
                    weights=W[k:k + rows].astype(np.float64))
        if backend == "torch" and (k // rows) % 200 == 199:
            import torch
            torch.cuda.empty_cache()
    cand.reset()
    cand.save(out_path)
    return out_path


def fit_value(net, pops, x, z, workers, out_path):
    from value_readout import fit
    n = len(x)
    parts = np.array_split(np.arange(n), workers)
    with get_context(MP).Pool(workers) as pool:
        feats = pool.map(_features, [(net, pops, x[p]) for p in parts if len(p)])
    F = np.vstack(feats)
    cut = int(0.8 * n)
    w, b = fit(F[:cut].astype(np.float64), z[:cut])
    pt = 1 / (1 + np.exp(-(F[cut:] @ w + b)))
    zt = z[cut:]
    dec = zt != 0.5
    from cadence import Brain
    bb = Brain.load(net, backend="cpu")
    idx = np.concatenate([np.array(sorted(bb.connectome.populations[q])) for q in pops.split(",")])
    np.savez(out_path, w=w, b=b, idx=idx, brain=net)
    return {"positions": int(n), "side_accuracy": float(np.mean((pt[dec] > 0.5) == (zt[dec] > 0.5))) if dec.any() else None,
            "brier": float(np.mean((pt - zt) ** 2)), "base_brier": float(np.mean((z[:cut].mean() - zt) ** 2))}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True)
    p.add_argument("--value", default=None, help="an initial value readout (value_readout.py)")
    p.add_argument("--out", required=True)
    p.add_argument("--pops", default="association")
    p.add_argument("--lam", type=float, default=0.5)
    p.add_argument("--games", type=int, default=192)
    p.add_argument("--sims", type=int, default=100)
    p.add_argument("--explore", type=int, default=12)
    p.add_argument("--anchors", default="voronoi,voronoi2,voronoi3,ab5")
    p.add_argument("--anchor-share", type=float, default=0.4)
    p.add_argument("--window", type=int, default=3)
    p.add_argument("--rows", type=int, default=32)
    p.add_argument("--eta", type=float, default=0.00005)
    p.add_argument("--gate-sims", type=int, default=50)
    p.add_argument("--probe-sims", type=int, default=200)
    p.add_argument("--gate-cap", type=int, default=128)
    p.add_argument("--probe-pairs", type=int, default=32)
    p.add_argument("--probe-every", type=int, default=3)
    p.add_argument("--workers", type=int, default=32)
    p.add_argument("--backend", default="cpu", help="evaluator backend in the workers")
    p.add_argument("--train-backend", default="torch")
    p.add_argument("--gens", type=int, default=1000)
    p.add_argument("--s3", default=None)
    a = p.parse_args()
    from cadence import Brain
    out = Path(a.out)
    (out / "data").mkdir(parents=True, exist_ok=True)
    sp = out / "state.json"
    st = json.loads(sp.read_text()) if sp.exists() else {"gen": 0, "net": a.start, "value": a.value, "history": []}
    (out / "meta.json").write_text(json.dumps({"args": vars(a)}, indent=1))
    log = open(out / "generations.jsonl", "a")
    ctx = get_context(MP)
    while st["gen"] < a.gens:
        g, net, value = st["gen"], st["net"], st.get("value")
        t0 = time.time()
        line = {"gen": g, "net": net, "value": value}
        # 1. self-play
        per = max(1, a.games // (3 * a.workers))  # small chunks: the pool stays busy to the end
        seeds = [20_000_000 + 10_000 * g + k for k in range(a.games)]
        tasks = [(net, value, a.lam, a.sims, a.backend, seeds[i:i + per], a.explore, a.anchors.split(","),
                  a.anchor_share, str(out / "data" / f"g{g}-{i}.npz")) for i in range(0, a.games, per)]
        with ctx.Pool(min(a.workers, len(tasks)), maxtasksperchild=1) as pool:
            got = pool.map(_selfplay, tasks, chunksize=1)
        line["positions"] = int(sum(n for _, n in got))
        line["selfplay_min"] = round((time.time() - t0) / 60, 1)
        # window
        shards = sorted(out.glob("data/g*.npz"), key=lambda q: int(q.stem[1:].split("-")[0]))
        keep = [q for q in shards if int(q.stem[1:].split("-")[0]) > g - a.window]
        for q in shards:
            if q not in keep:
                q.unlink()
        D = [np.load(q) for q in keep]
        X = np.concatenate([d["x"] for d in D])
        PI = np.concatenate([d["pi"] for d in D])
        Z = np.concatenate([d["z"] for d in D])
        W = np.concatenate([d["w"] for d in D])
        # 2. train a candidate
        t1 = time.time()
        rng = np.random.default_rng(g)
        new = line["positions"]
        order = rng.permutation(len(X))[:new]
        cpath = out / f"cand-g{g + 1}.npz"
        tmp = out / "train-batch.npz"
        np.savez(tmp, x=X[order], pi=PI[order], w=W[order])
        # in a spawned process, so this one never initializes CUDA (forked workers need that)
        with get_context("spawn").Pool(1) as tp:
            tp.apply(_train, ((net, str(tmp), str(cpath), a.eta, a.rows, a.train_backend),))
        tmp.unlink()
        line["train_min"] = round((time.time() - t1) / 60, 1)
        # 3. value readout of the candidate
        t2 = time.time()
        sub = rng.permutation(len(X))[:40_000]
        vpath = out / f"value-g{g + 1}.npz"
        line["value_fit"] = fit_value(str(cpath), a.pops, X[sub], Z[sub], min(a.workers, 24), str(vpath))
        line["value_min"] = round((time.time() - t2) / 60, 1)
        # 4. gate: candidate player against the current player
        t3 = time.time()
        lo_b, hi_b = math.log(0.1 / 0.9), math.log(0.9 / 0.1)
        scores, n, cap = {}, 0, a.gate_cap
        base = 30_000_000 + 1000 * g
        while n < cap:
            hi = min(n + min(16, cap), cap)
            tasks = [(str(cpath), str(vpath), net, value, a.lam, a.gate_sims, k, min(k + 2, hi), base, a.backend)
                     for k in range(n, hi, 2)]
            with ctx.Pool(min(a.workers, len(tasks)), maxtasksperchild=1) as pool:
                for lo, sc in pool.map(_duel, tasks, chunksize=1):
                    for j, v in enumerate(sc):
                        scores[lo + j] = v
            n = hi
            x = [scores[i] for i in range(n)]
            l = r3eval.llr(x, 0.5, 0.55, min_n=min(16, cap))
            if l >= hi_b or l <= lo_b:
                break
        mean = float(np.mean([scores[i] for i in range(n)]))
        accept = l >= hi_b or (n >= cap and mean > 0.5)
        line["gate"] = {"pairs": n, "mean": mean, "llr": l, "beats_previous": bool(accept)}
        if accept:
            line["gate"]["bots"] = bot_check(str(cpath), str(vpath), net, value, a.lam, a.gate_sims, g,
                                             a.workers, a.backend)
            accept = line["gate"]["bots"]["pass"]
        line["gate"]["accepted"] = bool(accept)
        line["gate_min"] = round((time.time() - t3) / 60, 1)
        if accept:
            keepp = out / f"net-g{g + 1}.npz"
            os.replace(cpath, keepp)
            st["net"], st["value"] = str(keepp), str(vpath)
        # 5. readings of the current network
        r = r3eval.reading(st["net"], "voronoi", 64, r3eval.CHECKPOINT, min(a.workers, 24))
        line["brain_alone_voronoi_64"] = r
        if (g + 1) % a.probe_every == 0:
            tasks = [(st["net"], st["value"], a.lam, a.probe_sims, o, lo, lo + 4, r3eval.CHECKPOINT, a.backend)
                     for o in ("voronoi", "voronoi2", "voronoi3", "ab5") for lo in range(0, a.probe_pairs, 4)]
            res = {}
            with ctx.Pool(min(a.workers, len(tasks)), maxtasksperchild=1) as pool:
                for o, w, l2, d in pool.map(_probe, tasks, chunksize=1):
                    t = res.setdefault(o, [0, 0, 0])
                    t[0] += w; t[1] += l2; t[2] += d  # noqa: E702
            line["player_probe"] = {o: {"wins": t[0], "losses": t[1], "draws": t[2], "score": (t[0] + t[2] / 2) / sum(t)}
                                    for o, t in res.items()}
        line["wall_min"] = round((time.time() - t0) / 60, 1)
        log.write(json.dumps(line) + "\n")
        log.flush()
        print(json.dumps({"gen": g, "positions": line["positions"], "gate": line["gate"],
                          "brain_alone": r["score"], "value_acc": line["value_fit"]["side_accuracy"],
                          "probe": {o: v["score"] for o, v in line.get("player_probe", {}).items()},
                          "wall_min": line["wall_min"]}), flush=True)
        st["gen"] = g + 1
        st["history"].append({"gen": g, "accepted": bool(accept), "net": st["net"]})
        sp.write_text(json.dumps(st, indent=1))
        if a.s3:
            subprocess.run(["aws", "s3", "sync", str(out), a.s3, "--only-show-errors", "--exclude", "data/*"], check=False)


if __name__ == "__main__":
    main()
