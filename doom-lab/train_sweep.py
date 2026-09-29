"""Train and evaluate one sweep candidate; write checkpoint + receipt.

Balancing is a disclosed curriculum choice: pure-forward frames are
subsampled to keep rare decisions (fire, use, strafe) visible, and the
example count is capped. Checks come from held-out episodes only.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import time

import numpy as np

from cadence import bootstrap

import evaluate as ev
import norms as nz
from doomlab import targets_from_buttons
from layouts import build

FORWARD_ONLY = (1, 0, 0, 0, 0, 0, 0)


def select_rows(corpus, *, train, forward_keep, cap, seed):
    check_eps = set(corpus["check_episodes"].tolist())
    rng = random.Random(seed)
    rows = []
    for i, episode in enumerate(corpus["episode"]):
        if (episode in check_eps) == train:
            continue
        buttons = tuple(int(b) for b in corpus["buttons"][i])
        if buttons == FORWARD_ONLY and rng.random() > forward_keep:
            continue
        rows.append(i)
    rng.shuffle(rows)
    return rows[:cap]


def pairs(corpus, rows):
    return [
        (
            {"periphery": corpus["periphery"][i].tolist(),
             "fovea": corpus["fovea"][i].tolist()},
            {"motor": targets_from_buttons(corpus["buttons"][i])},
        )
        for i in rows
    ]


def run(spec, corpus_path, out_dir):
    raw = np.load(corpus_path)
    train_rows = select_rows(raw, train=True,
                             forward_keep=spec["forward_keep"],
                             cap=spec["max_examples"], seed=spec["seed"])
    check_rows = select_rows(raw, train=False, forward_keep=0.3,
                             cap=spec["max_checks"], seed=spec["seed"])
    # Fit conditioning on bootstrap examples only, then transform everything.
    norms = nz.fit(raw["periphery"][train_rows], raw["fovea"][train_rows])
    periphery, fovea = nz.apply(norms, raw["periphery"], raw["fovea"])
    corpus = {"periphery": periphery, "fovea": fovea,
              "buttons": raw["buttons"], "episode": raw["episode"],
              "check_episodes": raw["check_episodes"]}
    brain = build(spec["layout"], spec["seed"],
                  parameter_prior=spec["parameter_prior"])
    # Cold-start ramp: a fresh brain needs a few small batches before large
    # ones qualify within budget. Same public admission rule, replay-legal.
    started = time.perf_counter()
    warm_rng = random.Random(spec["seed"] + 1)
    warm_total = sum(spec.get("warmup_sizes", (8, 8, 16, 24)))
    warm_rows = warm_rng.sample(train_rows, min(warm_total, len(train_rows)))
    warm = {"batches": [], "admitted": 0}
    cursor = 0
    for size in spec.get("warmup_sizes", (8, 8, 16, 24)):
        batch = pairs(corpus, warm_rows[cursor:cursor + size])
        cursor += size
        result = brain.observe_batch(batch)
        warm["batches"].append(
            {"size": len(batch), "accepted": bool(result["accepted"]),
             "sweeps": result["sweeps"]})
        if result["accepted"]:
            warm["admitted"] += len(batch)
    warm["seconds"] = round(time.perf_counter() - started, 1)
    started = time.perf_counter()
    report = bootstrap(
        brain,
        pairs(corpus, train_rows),
        checks=pairs(corpus, check_rows),
        max_error=spec["max_error"],
        epochs=spec["epochs"],
        seed=spec["seed"],
        batch_size=spec["batch_size"],
    )
    train_seconds = time.perf_counter() - started
    started = time.perf_counter()
    check_eps = set(corpus["check_episodes"].tolist())
    check_idx = [i for i, e in enumerate(corpus["episode"]) if e in check_eps]
    evaluation = ev.evaluate(brain, corpus, check_idx,
                             episodes=spec["eval_episodes"], norms=norms)
    eval_seconds = time.perf_counter() - started
    os.makedirs(out_dir, exist_ok=True)
    name = spec["name"]
    checkpoint_path = os.path.join(out_dir, f"{name}.json.gz")
    snapshot = brain.snapshot()
    with gzip.open(checkpoint_path, "wt") as f:
        f.write(snapshot)
    nz.save(norms, nz.sibling_path(checkpoint_path))
    receipt = {
        "spec": spec,
        "train_rows": len(train_rows),
        "check_rows": len(check_rows),
        "warmup": warm,
        "bootstrap": {k: report[k] for k in
                      ("passed", "reason", "epochs", "presentations",
                       "accepted", "updates", "history", "failure", "options")},
        "work": report["work"],
        "train_seconds": round(train_seconds, 1),
        "eval_seconds": round(eval_seconds, 1),
        "evaluation": evaluation,
        "conditioning": "per-coordinate standardize, clip 3, scale 0.2, fitted on train rows",
        "checkpoint": os.path.basename(checkpoint_path),
        "checkpoint_sha256": hashlib.sha256(snapshot.encode()).hexdigest(),
        "implementation": brain.inspect()["implementation"],
        "edges": brain.inspect()["connections"],
    }
    with open(os.path.join(out_dir, f"{name}.receipt.json"), "w") as f:
        json.dump(receipt, f, indent=2)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, help="JSON spec string or path")
    parser.add_argument("--corpus", default="data/corpus1/witnesses.npz")
    parser.add_argument("--out", default="runs/sweep1")
    parser.add_argument("--threads", type=int, default=3)
    args = parser.parse_args()
    import torch
    torch.set_num_threads(args.threads)
    spec = (json.load(open(args.spec)) if os.path.exists(args.spec)
            else json.loads(args.spec))
    receipt = run(spec, args.corpus, args.out)
    summary = {
        "name": spec["name"],
        "mean_kills": receipt["evaluation"]["live"]["mean_kills"],
        "control_kills": receipt["evaluation"]["marginal_control"]["mean_kills"],
        "agreement": receipt["evaluation"]["agreement"]["mean"],
        "train_seconds": receipt["train_seconds"],
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
