"""Ridge preflight: the linear floor a training run must clear.

Fits closed-form ridge on the corpus with the full input set the brain
will see and reports per-button AUC on held-out rows. Run it before
spending a training hour; a learner that lands under these numbers is
extracting less than its inputs support, and the numbers also bound
what the demonstrator's policy makes visible.

    python preflight_ridge.py --corpus data/corpus3/witnesses.npz
"""

from __future__ import annotations

import argparse
import json
import random

import numpy as np

import evaluate as ev
import norms as nz
from deep_probe import rank_auc
from doomlab import BUTTONS
from train_self import usable_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default="data/corpus3/witnesses.npz")
    parser.add_argument("--cap", type=int, default=20000)
    parser.add_argument("--rows", type=int, default=400)
    parser.add_argument("--lam", type=float, default=10.0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    raw = np.load(args.corpus)
    train_rows = usable_rows(raw, train=True, forward_keep=0.4,
                             cap=args.cap, seed=0)
    check_rows = usable_rows(raw, train=False, forward_keep=0.4,
                             cap=3000, seed=0)
    picks = random.Random(1234).sample(check_rows,
                                       min(args.rows, len(check_rows)))
    streams = {"periphery", "fovea", "efference", "fovea_history",
               "periphery_history"}
    needed = sorted(set(train_rows) | set(picks))
    fit = nz.fit(raw["periphery"][train_rows], raw["fovea"][train_rows])
    corpus = ev.prepare_corpus(raw, fit, streams, needed)

    def matrix(rows):
        eff = np.where(raw["efference"][rows] > 0, 0.6, -0.6)
        fh = np.stack([corpus["fovea_history"][i] for i in rows])
        ph = np.stack([corpus["periphery_history"][i] for i in rows])
        return np.hstack([corpus["periphery"][rows],
                          corpus["fovea"][rows], eff, fh, ph])

    X = matrix(train_rows)
    T = np.where(raw["buttons"][train_rows] > 0, 0.6, -0.6)
    W = np.linalg.solve(X.T @ X + args.lam * np.eye(X.shape[1]), X.T @ T)
    S = matrix(picks) @ W
    Y = raw["buttons"][picks].astype(int)
    auc = [rank_auc(S[Y[:, j] == 1, j], S[Y[:, j] == 0, j])
           for j in range(len(BUTTONS))]
    known = [a for a in auc if a is not None]
    floor = {
        "rows_fit": len(train_rows),
        "rows_eval": len(picks),
        "press_base": raw["buttons"][picks].mean(0).round(3).tolist(),
        "auc": [round(a, 3) if a is not None else None for a in auc],
        "mean_auc": round(float(np.mean(known)), 3) if known else None,
    }
    print(json.dumps(floor, indent=1))
    if args.out:
        json.dump(floor, open(args.out, "w"))
    print("LINEAR-FLOOR:", floor["mean_auc"], flush=True)


if __name__ == "__main__":
    main()
