"""a value readout from the settled state, trained on outcomes.

    python scripts/value_readout.py --brain runs/r3/best/exitsel-mako-d3-m7500.npz --out runs/r3/c/value-m16

The brain (frozen, CPU) rides `--games` games against the labelling opponents
(`phasec.LABEL_OPPS`) from seeds 9,000,000+; at every position its settled association
activity (the last state of the act's settlement, read through `cadence.record_settlements`)
is kept with the game's outcome from the rider's side (win 1, draw 0.5, loss 0). A logistic
readout over the 256 association neurons (plus a bias) is fitted on the games of the first
four fifths (L2-regularized Newton steps) and scored on the last fifth: log loss, Brier score
and the share of decided positions on the right side of 0.5, against the base rate. Saved as
`value.npz` (w, b, the neuron indices, the brain's path) with `value.json`.

`value_of(brain, readout, x)`: the readout's value of each row of sense vectors `x`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from multiprocessing import get_context

# Process pools fork on Linux; on macOS a fork after NumPy or Numba threads have run can hang,
# so pools spawn there. TRON_MP=fork|spawn|forkserver overrides.
MP = os.environ.get("TRON_MP") or ("spawn" if sys.platform == "darwin" else "fork")
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tron.field import make_sense3  # noqa: E402
from tron.world import Arena, mulberry32  # noqa: E402
from phasec import OPP, LABEL_OPPS  # noqa: E402

SEE = make_sense3("field")[0]
BASE = 9_000_000


def settled(brain, x, idx):
    """Greedy moves and the settled activity of the neurons `idx` for the rows of `x`, settled
    from rest; the state read through `Brain._activity()`."""
    brain.reset()
    moves = np.asarray(brain.act(x, greedy=True)).reshape(-1)
    act = np.asarray(brain._activity().activation)
    return moves, act.reshape(len(x), -1)[:, idx]


def value_of(brain, readout, x):
    _, a = settled(brain, x, readout["idx"])
    return 1.0 / (1.0 + np.exp(-(a @ readout["w"] + readout["b"])))


def _idx(b, pops):
    return np.concatenate([np.array(sorted(b.connectome.populations[q])) for q in pops.split(",")])


def _games(args):
    path, lo, hi, pops, self_share = args
    from cadence import Brain
    b = Brain.load(path, backend="cpu")
    twin = Brain.load(path, backend="cpu")
    idx = _idx(b, pops)
    out = []
    for g in range(lo, hi):
        s = BASE + g
        ar, dr = Arena(24, seed=s), mulberry32(s)
        selfplay = (g * 7919 % 1000) / 1000 < self_share
        opp = LABEL_OPPS[g % len(LABEL_OPPS)]
        feats = []
        while not ar.over:
            m, a = settled(b, SEE(ar, 0)[None, :].astype(np.float64), idx)
            feats.append(a[0].astype(np.float32))
            if selfplay:
                twin.reset()
                o = int(twin.act(SEE(ar, 1)[None, :].astype(np.float64), greedy=True)[0])
            else:
                o = OPP[opp](ar, 1, dr)
            ar.step((int(m[0]), o))
        z = 1.0 if ar.winner == 0 else 0.5 if ar.winner is None else 0.0
        out.append((g, np.stack(feats), z, "self" if selfplay else opp))
    return out


def fit(X, y, lam=1e-2, iters=25):
    Xb = np.hstack([X, np.ones((len(X), 1))])
    w = np.zeros(Xb.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xb @ w))
        g = Xb.T @ (p - y) / len(y) + lam * np.r_[w[:-1], 0]
        H = (Xb * (p * (1 - p))[:, None]).T @ Xb / len(y) + lam * np.diag(np.r_[np.ones(len(w) - 1), 0])
        w -= np.linalg.solve(H, g)
    return w[:-1], w[-1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--brain", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--games", type=int, default=1600)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--pops", default="association", help="populations read (comma-separated)")
    p.add_argument("--self-share", type=float, default=0.5, help="share of games against the brain itself")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    step = max(1, a.games // (4 * a.workers))
    jobs = [(a.brain, lo, min(lo + step, a.games), a.pops, a.self_share) for lo in range(0, a.games, step)]
    with get_context(MP).Pool(a.workers) as pool:
        games = sorted((r for chunk in pool.map(_games, jobs, chunksize=1) for r in chunk), key=lambda r: r[0])
    cut = int(0.8 * len(games))
    X = np.vstack([f for _, f, _, _ in games[:cut]])
    y = np.concatenate([np.full(len(f), z) for _, f, z, _ in games[:cut]])
    Xt = np.vstack([f for _, f, _, _ in games[cut:]])
    yt = np.concatenate([np.full(len(f), z) for _, f, z, _ in games[cut:]])
    w, b = fit(X.astype(np.float64), y)
    pt = 1 / (1 + np.exp(-(Xt @ w + b)))
    base = float(y.mean())
    dec = yt != 0.5
    eps = 1e-6
    report = {"brain": a.brain, "games": len(games), "positions": int(len(y)), "test_positions": int(len(yt)),
              "train_win_rate": base,
              "test_logloss": float(-np.mean(yt * np.log(pt + eps) + (1 - yt) * np.log(1 - pt + eps))),
              "base_logloss": float(-np.mean(yt * np.log(base) + (1 - yt) * np.log(1 - base))),
              "test_brier": float(np.mean((pt - yt) ** 2)), "base_brier": float(np.mean((base - yt) ** 2)),
              "test_side_accuracy": float(np.mean((pt[dec] > 0.5) == (yt[dec] > 0.5))),
              "base_side_accuracy": float(max(np.mean(yt[dec] > 0.5), np.mean(yt[dec] < 0.5))),
              "pops": a.pops, "features": int(X.shape[1]), "self_share": a.self_share,
              # calibration: the held-out positions in ten bins of the predicted value
              "calibration": [{"bin": f"{lo / 10:.1f}-{(lo + 1) / 10:.1f}", "positions": int(m.sum()),
                               "predicted": float(pt[m].mean()), "outcome": float(yt[m].mean())}
                              for lo in range(10) for m in [(pt >= lo / 10) & (pt < (lo + 1) / 10 + (lo == 9))] if m.sum()]}
    from cadence import Brain
    idx = _idx(Brain.load(a.brain, backend="cpu"), a.pops)
    np.savez(out / "value.npz", w=w, b=b, idx=idx, brain=a.brain)
    (out / "value.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
