"""Train the flagship lineage brain and export its life as regular snapshots.

Full feature set — retinas, efference, half-resolution fovea History and
foresight heads — trained from scratch on the multi-map corpus. Every
``--export-every`` batches, a registry-ready checkpoint+norms pair lands in
``<out>/exports/`` so the lab dropdown can follow the brain's growth, and a
progress sidecar makes the run resumable after interruption.
"""

from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import random
import time

import numpy as np

import norms as nz
from cadence.memory import History
from doomlab import BUTTONS, targets_from_buttons
from layouts import (HIST_SIZE, HIST_STEPS, PHIST_SIZE, PHIST_STEPS,
                     build_flagship, build_ultimate)
from train_self import foresight_targets, usable_rows

EFF_ON, EFF_OFF = 0.6, -0.6


def half_fovea(row):
    """Standardized fovea row (384,) -> half-resolution (96,) block means."""
    return np.asarray(row, np.float64).reshape(6, 64) \
        .reshape(3, 2, 32, 2).mean(axis=(1, 3)).ravel()


def quarter_periphery(row):
    """Standardized periphery row (640,) -> quarter-resolution (160,)."""
    return np.asarray(row, np.float64).reshape(20, 32) \
        .reshape(10, 2, 16, 2).mean(axis=(1, 3)).ravel()


def window_matrix(corpus, rows_needed, source, reducer, size, steps):
    """Encoded history windows for exactly the rows that will be used.

    Random-access equivalent of feeding ``History`` sequentially per episode:
    front padding, then oldest-to-newest (values, mask) blocks. Orders of
    magnitude cheaper than encoding the whole corpus.
    """
    episode = corpus["episode"]
    stream = corpus[source]
    change = np.flatnonzero(np.r_[True, episode[1:] != episode[:-1]])
    start_of = np.zeros(len(episode), np.int64)
    start_of[change] = change
    np.maximum.accumulate(start_of, out=start_of)
    width = steps * (size + 1)
    out = {}
    for i in rows_needed:
        j0 = int(max(start_of[i], i - steps + 1))
        encoded = np.zeros(width, np.float32)
        offset = width - (i + 1 - j0) * (size + 1)
        for k, j in enumerate(range(j0, i + 1)):
            p = offset + k * (size + 1)
            encoded[p:p + size] = reducer(stream[j])
            encoded[p + size] = 1.0
        out[i] = encoded
    return out


def example(corpus, i):
    eff = [EFF_ON if b else EFF_OFF for b in corpus["efference"][i]]
    inputs = {"periphery": corpus["periphery"][i].tolist(),
              "fovea": corpus["fovea"][i].tolist(),
              "efference": eff,
              "fovea_history": corpus["fovea_history"][i].tolist()}
    if "periphery_history" in corpus:
        inputs["periphery_history"] = corpus["periphery_history"][i].tolist()
    return (
        inputs,
        {"motor": targets_from_buttons(corpus["buttons"][i]),
         "outcome": foresight_targets(corpus, i)},
    )


def probe(brain, corpus, rows, rng, n=150):
    """Sampled unclamped readiness with the flagship's own input set."""
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


def export(brain, fit_norms, out_dir, name, batches, extra=None):
    os.makedirs(os.path.join(out_dir, "exports"), exist_ok=True)
    path = os.path.join(out_dir, "exports", f"{name}_b{batches:05d}.json.gz")
    snapshot = brain.snapshot()
    with gzip.open(path, "wt") as f:
        f.write(snapshot)
    nz.save(fit_norms, nz.sibling_path(path))
    with open(path.replace(".json.gz", ".meta.json"), "w") as f:
        json.dump({"label": f"Flagship after {batches} batches",
                   **(extra or {})}, f)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default="data/corpus3/witnesses.npz")
    parser.add_argument("--out", default="runs/flagship")
    parser.add_argument("--name", default="flagship_s0")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--parameter-prior", type=float, default=0.1)
    parser.add_argument("--max-examples", type=int, default=16000)
    parser.add_argument("--forward-keep", type=float, default=0.4)
    parser.add_argument("--batch", type=int, default=96)
    parser.add_argument("--export-every", type=int, default=25,
                        help="probe/export at least every N batches")
    parser.add_argument("--export-minutes", type=float, default=None,
                        help="time-based export cadence (overrides batches)")
    parser.add_argument("--layout", choices=("flagship", "ultimate"),
                        default="flagship")
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    import torch
    torch.set_num_threads(args.threads)
    os.makedirs(args.out, exist_ok=True)
    progress_path = os.path.join(args.out, "progress.json")

    raw = np.load(args.corpus)
    train_rows = usable_rows(raw, train=True, forward_keep=args.forward_keep,
                             cap=args.max_examples, seed=args.seed)
    check_rows = usable_rows(raw, train=False, forward_keep=0.4,
                             cap=3000, seed=args.seed)
    fit_norms = nz.fit(raw["periphery"][train_rows], raw["fovea"][train_rows])
    periphery, fovea = nz.apply(fit_norms, raw["periphery"], raw["fovea"])
    corpus = {"periphery": periphery, "fovea": fovea,
              "buttons": raw["buttons"], "efference": raw["efference"],
              "health": raw["health"], "ammo": raw["ammo"],
              "kills": raw["kills"], "episode": raw["episode"]}
    needed = sorted(set(train_rows) | set(check_rows))
    print(f"building history windows for {len(needed)} needed rows",
          flush=True)
    corpus["fovea_history"] = window_matrix(
        corpus, needed, "fovea", half_fovea, HIST_SIZE, HIST_STEPS)
    if args.layout == "ultimate":
        corpus["periphery_history"] = window_matrix(
            corpus, needed, "periphery", quarter_periphery,
            PHIST_SIZE, PHIST_STEPS)
    print(f"train rows {len(train_rows)} | check rows {len(check_rows)}",
          flush=True)

    done = 0
    if args.resume and os.path.exists(progress_path):
        state = json.load(open(progress_path))
        done = state["done_rows"]
        exports = sorted(glob.glob(
            os.path.join(args.out, "exports", f"{args.name}_b*.json.gz")))
        if not exports:
            raise SystemExit("resume requested but no export found")
        from cadence import Brain
        with gzip.open(exports[-1], "rt") as f:
            brain = Brain.from_snapshot(f.read(), device="cpu")
        print(f"resumed from {exports[-1]} at {done} rows", flush=True)
    else:
        builder = build_ultimate if args.layout == "ultimate" else build_flagship
        brain = builder(args.seed, parameter_prior=args.parameter_prior)

    rng = random.Random(args.seed + 5)
    started = time.perf_counter()
    if done == 0:
        cursor = 0
        for size in (8, 8, 16, 24, 48, 64, 96):
            batch = [example(corpus, i) for i in train_rows[cursor:cursor + size]]
            cursor += size
            t0 = time.perf_counter()
            result = brain.observe_batch(batch)
            print(f"warmup size={size} accepted={result['accepted']} "
                  f"sweeps={result['sweeps']} {time.perf_counter()-t0:.1f}s",
                  flush=True)
        done = cursor
        export(brain, fit_norms, args.out, args.name, 0)

    order = train_rows
    warm_total = 8 + 8 + 16 + 24 + 48 + 64 + 96
    batches = max(0, (done - warm_total) // args.batch) if done > warm_total else 0
    last_export = time.perf_counter()
    while done < len(order):
        rows = order[done:done + args.batch]
        t0 = time.perf_counter()
        result = brain.observe_batch([example(corpus, i) for i in rows])
        seconds = time.perf_counter() - t0
        done += len(rows)
        batches += 1
        if batches % 5 == 0:
            rate = (done / max(1e-9, time.perf_counter() - started))
            print(f"batch {batches:5d} rows={done}/{len(order)} "
                  f"accepted={result['accepted']} sweeps={result['sweeps']:5d} "
                  f"{seconds:6.1f}s eta={(len(order)-done)/max(rate,1e-9)/60:6.1f}min",
                  flush=True)
        due = (batches % args.export_every == 0
               if args.export_minutes is None
               else time.perf_counter() - last_export >= args.export_minutes * 60)
        if due:
            snapshot = probe(brain, corpus, check_rows, rng, n=150)
            path = export(brain, fit_norms, args.out, args.name, batches,
                          extra={"probe": snapshot, "rows": done})
            json.dump({"done_rows": done, "batches": batches},
                      open(progress_path, "w"))
            last_export = time.perf_counter()
            print(f"export {os.path.basename(path)} probe={json.dumps(snapshot)}",
                  flush=True)

    final = probe(brain, corpus, check_rows, rng, n=600)
    path = export(brain, fit_norms, args.out, args.name, batches,
                  extra={"probe": final, "rows": done, "final": True})
    json.dump({"done_rows": done, "batches": batches, "complete": True},
              open(progress_path, "w"))
    print("FINAL", json.dumps(final), flush=True)
    print(f"lineage at {path}; {round(time.perf_counter()-started,1)}s",
          flush=True)


if __name__ == "__main__":
    main()
