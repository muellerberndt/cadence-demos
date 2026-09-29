"""Per-export enrichment prober for a training lineage.

Watches an exports directory and gives every checkpoint a ``deep`` block in
its meta file: a fixed-row settle probe (same rows for every checkpoint, so
trends are free of sample noise), per-button pressed recall and predicted
press rates (immune to the never-press base rate), and short closed-loop
episodes measuring path, kills and button usage in the brain's own context.
Runs beside a live trainer; reads exports, writes only meta files.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import random
import time

import numpy as np
import torch

import evaluate as ev
import norms as nz
from doomlab import BUTTONS, buttons_from_scores
from train_self import foresight_targets, usable_rows

FIXED_SEED = 1234
N_ROWS = 150
EPISODE_SEEDS = (9500, 9501)
DECISIONS = 300
BUDGET = 384  # matches the lab's live budget


def fixed_probe(brain, corpus, rows, streams):
    picks = random.Random(FIXED_SEED).sample(rows, min(N_ROWS, len(rows)))
    hits = np.zeros(len(BUTTONS))
    press_hits = np.zeros(len(BUTTONS))
    press_n = np.zeros(len(BUTTONS))
    pred_press = np.zeros(len(BUTTONS))
    mae = np.zeros(4)
    refused = counted = 0
    for i in picks:
        result = brain.settle(ev.corpus_inputs(corpus, i, streams),
                              budget=BUDGET)
        if not result["qualified"]:
            refused += 1
            continue
        counted += 1
        decoded = np.array(buttons_from_scores(result["outputs"]["motor"]))
        truth = corpus["buttons"][i]
        hits += decoded == truth
        press_n += truth
        press_hits += decoded * truth
        pred_press += decoded
        outcome = result["outputs"].get("outcome")
        if outcome is not None:
            mae += np.abs(np.array(outcome)
                          - np.array(foresight_targets(corpus, i)))
    if counted == 0:
        return {"refused": refused, "counted": 0}
    return {
        "refused": refused,
        "counted": counted,
        "button_acc": (hits / counted).round(3).tolist(),
        "pressed_recall": [
            round(float(h / n), 3) if n else None
            for h, n in zip(press_hits, press_n)
        ],
        "pred_press_rate": (pred_press / counted).round(3).tolist(),
        "outcome_mae": (mae / counted).round(3).tolist(),
        "budget": BUDGET,
    }


def closed_loop(brain, norms):
    episodes = []
    for seed in EPISODE_SEEDS:
        counts = np.zeros(len(BUTTONS))
        decided = [0]
        inner = ev.brain_policy(brain, norms)

        def policy(views):
            buttons, refused = inner(views)
            counts[:] += buttons
            decided[0] += 1
            return buttons, refused

        row = ev.live_episode(policy, seed, decisions=DECISIONS)
        n = max(1, decided[0])
        row["press_rate"] = {
            name: round(float(c / n), 3)
            for name, c in zip(BUTTONS, counts)
        }
        episodes.append(row)
    return episodes


def process(path, corpus, rows, base_norms):
    meta_path = path.replace(".json.gz", ".meta.json")
    meta = json.load(open(meta_path))
    brain = ev.load_brain(path)
    streams = ev.input_streams(brain)
    norms = nz.load(nz.sibling_path(path))
    started = time.perf_counter()
    deep = {"probe": fixed_probe(brain, corpus, rows, streams)}
    deep["live"] = closed_loop(brain, norms)
    deep["seconds"] = round(time.perf_counter() - started, 1)
    meta["deep"] = deep
    tmp = meta_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(meta, f)
    os.replace(tmp, meta_path)
    print(os.path.basename(path), json.dumps(deep["probe"]), flush=True)
    live = deep["live"]
    print("  live:", json.dumps([
        {k: e[k] for k in ("seed", "path", "kills", "refusals")}
        for e in live]), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exports", default="runs/ultimate/exports")
    parser.add_argument("--corpus", default="data/corpus3/witnesses.npz")
    parser.add_argument("--threads", type=int, default=12)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    raw = np.load(args.corpus)
    rows = usable_rows(raw, train=False, forward_keep=0.4, cap=3000, seed=0)
    corpus = norms_holder = None
    while True:
        for path in sorted(glob.glob(
                os.path.join(args.exports, "*_b*.json.gz"))):
            meta_path = path.replace(".json.gz", ".meta.json")
            if not os.path.exists(meta_path) or not os.path.exists(
                    nz.sibling_path(path)):
                continue
            try:
                meta = json.load(open(meta_path))
            except ValueError:
                continue
            if "deep" in meta:
                continue
            if corpus is None:
                norms_holder = nz.load(nz.sibling_path(path))
                brain = ev.load_brain(path)
                corpus = ev.prepare_corpus(raw, norms_holder,
                                           ev.input_streams(brain), rows)
            process(path, corpus, rows, norms_holder)
        if args.once:
            return
        time.sleep(120)


if __name__ == "__main__":
    main()
