"""Train the generalist self-play brain: motor imitation + foresight heads.

Drives ``observe_batch`` directly (no full-corpus readiness sweeps): warmup
ramp, one shuffled pass, progress lines every few batches, sampled readiness
probes, then checkpoint + norms + receipt. Foresight targets are measured
next-decision outcomes (health/ammo deltas, kill events, view change), so
reality — not a teacher — supplies them.
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

import norms as nz
from doomlab import BUTTONS, targets_from_buttons
from layouts import build_self

FORWARD_ONLY = (1, 0, 0, 0, 0, 0, 0, 0)
EFF_ON, EFF_OFF = 0.6, -0.6


def foresight_targets(corpus, index):
    """Measured next-decision outcome, encoded into the state range."""
    dh = float(np.clip(corpus["health"][index + 1] - corpus["health"][index],
                       -20, 20)) / 20 * 0.6
    da = float(np.clip(corpus["ammo"][index + 1] - corpus["ammo"][index],
                       -5, 5)) / 5 * 0.6
    kill = 0.6 if corpus["kills"][index + 1] > corpus["kills"][index] else -0.6
    dview = float(np.mean(np.abs(
        corpus["fovea"][index + 1] - corpus["fovea"][index])))
    dview = min(1.0, dview / 0.25) * 1.2 - 0.6
    return [dh, da, kill, dview]


def usable_rows(corpus, *, train, forward_keep, cap, seed):
    check_eps = set(corpus["check_episodes"].tolist())
    episode = corpus["episode"]
    rng = random.Random(seed)
    rows = []
    for i in range(len(episode) - 1):
        if episode[i + 1] != episode[i]:
            continue  # episode-final rows have no measured next outcome
        if (int(episode[i]) in check_eps) == train:
            continue
        buttons = tuple(int(b) for b in corpus["buttons"][i])
        if buttons == FORWARD_ONLY and rng.random() > forward_keep:
            continue
        rows.append(i)
    rng.shuffle(rows)
    return rows[:cap]


def example(corpus, i):
    eff = [EFF_ON if b else EFF_OFF for b in corpus["efference"][i]]
    return (
        {"periphery": corpus["periphery"][i].tolist(),
         "fovea": corpus["fovea"][i].tolist(),
         "efference": eff},
        {"motor": targets_from_buttons(corpus["buttons"][i]),
         "outcome": foresight_targets(corpus, i)},
    )


def probe(brain, corpus, rows, rng, n=200):
    """Sampled unclamped readiness: motor button accuracy + outcome MAE."""
    from doomlab import buttons_from_scores
    picks = rng.sample(rows, min(n, len(rows)))
    hits = np.zeros(len(BUTTONS))
    mae = np.zeros(4)
    refused = counted = 0
    for i in picks:
        inputs, targets = example(corpus, i)
        result = brain.settle(inputs, budget=512)
        if not result["qualified"]:
            refused += 1
            continue
        counted += 1
        decoded = np.array(buttons_from_scores(result["outputs"]["motor"]))
        hits += decoded == corpus["buttons"][i]
        mae += np.abs(np.array(result["outputs"]["outcome"])
                      - np.array(targets["outcome"]))
    if counted == 0:
        return {"refused": refused, "counted": 0}
    return {"refused": refused, "counted": counted,
            "button_acc": (hits / counted).round(3).tolist(),
            "outcome_mae": (mae / counted).round(3).tolist()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default="data/corpus3/witnesses.npz")
    parser.add_argument("--out", default="runs/self1")
    parser.add_argument("--name", default="self-grand_s0")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--parameter-prior", type=float, default=0.1)
    parser.add_argument("--max-examples", type=int, default=16000)
    parser.add_argument("--forward-keep", type=float, default=0.4)
    parser.add_argument("--batch", type=int, default=96)
    parser.add_argument("--threads", type=int, default=12)
    args = parser.parse_args()
    import torch
    torch.set_num_threads(args.threads)

    raw = np.load(args.corpus)
    train_rows_raw = usable_rows(raw, train=True, forward_keep=args.forward_keep,
                                 cap=args.max_examples, seed=args.seed)
    fit_norms = nz.fit(raw["periphery"][train_rows_raw],
                       raw["fovea"][train_rows_raw])
    periphery, fovea = nz.apply(fit_norms, raw["periphery"], raw["fovea"])
    corpus = {"periphery": periphery, "fovea": fovea,
              "buttons": raw["buttons"], "efference": raw["efference"],
              "health": raw["health"], "ammo": raw["ammo"],
              "kills": raw["kills"], "episode": raw["episode"],
              "check_episodes": raw["check_episodes"]}
    train_rows = train_rows_raw
    check_rows = usable_rows(raw, train=False, forward_keep=0.4,
                             cap=3000, seed=args.seed)
    print(f"train rows {len(train_rows)} | check rows {len(check_rows)}",
          flush=True)

    brain = build_self(args.seed, parameter_prior=args.parameter_prior)
    rng = random.Random(args.seed + 5)
    started = time.perf_counter()
    log = {"warmup": [], "probes": [], "batches": []}

    cursor = 0
    for size in (8, 8, 16, 24, 48, 64):
        batch = [example(corpus, i)
                 for i in train_rows[cursor:cursor + size]]
        cursor += size
        t0 = time.perf_counter()
        result = brain.observe_batch(batch)
        entry = {"size": size, "accepted": bool(result["accepted"]),
                 "sweeps": result["sweeps"],
                 "seconds": round(time.perf_counter() - t0, 1)}
        log["warmup"].append(entry)
        print("warmup", json.dumps(entry), flush=True)

    order = train_rows[cursor:]
    admitted = cursor
    refused_batches = 0
    for start in range(0, len(order), args.batch):
        rows = order[start:start + args.batch]
        batch = [example(corpus, i) for i in rows]
        t0 = time.perf_counter()
        result = brain.observe_batch(batch)
        seconds = time.perf_counter() - t0
        if result["accepted"]:
            admitted += len(rows)
        else:
            refused_batches += 1
        n_batch = start // args.batch
        if n_batch % 10 == 0:
            done = start + len(rows)
            rate = done / max(1e-9, time.perf_counter() - started)
            print(f"batch {n_batch:4d} admitted={admitted:6d}/"
                  f"{len(train_rows)} {seconds:6.1f}s "
                  f"sweeps={result['sweeps']:5d} "
                  f"eta={((len(order) - done) / max(rate, 1e-9)) / 60:5.1f}min",
                  flush=True)
        if n_batch % 40 == 20:
            snapshot = probe(brain, corpus, check_rows, rng)
            log["probes"].append({"batch": n_batch, **snapshot})
            print("probe", json.dumps(snapshot), flush=True)

    final_probe = probe(brain, corpus, check_rows, rng, n=600)
    os.makedirs(args.out, exist_ok=True)
    checkpoint_path = os.path.join(args.out, f"{args.name}.json.gz")
    snapshot = brain.snapshot()
    with gzip.open(checkpoint_path, "wt") as f:
        f.write(snapshot)
    nz.save(fit_norms, nz.sibling_path(checkpoint_path))
    receipt = {
        "corpus": args.corpus,
        "options": vars(args),
        "train_rows": len(train_rows),
        "admitted": admitted,
        "refused_batches": refused_batches,
        "warmup": log["warmup"],
        "probes": log["probes"],
        "final_probe": final_probe,
        "train_seconds": round(time.perf_counter() - started, 1),
        "checkpoint_sha256": hashlib.sha256(snapshot.encode()).hexdigest(),
        "implementation": brain.inspect()["implementation"],
        "edges": brain.inspect()["connections"],
        "foresight_encoding": "dh/20, da/5, kill sign, dview/0.25 -> [-0.6,0.6]",
    }
    with open(os.path.join(args.out, f"{args.name}.receipt.json"), "w") as f:
        json.dump(receipt, f, indent=2)
    print("FINAL", json.dumps(final_probe), flush=True)
    print(f"receipt written; {receipt['train_seconds']}s total", flush=True)


if __name__ == "__main__":
    main()
