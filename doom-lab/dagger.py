"""DAgger rounds: the student acts, the privileged teacher labels its states.

Each round runs student-driven episodes, records the teacher's chosen
buttons on every visited frame, then admits a mix of those corrections and
replayed original-corpus rows (against forgetting). Evaluation runs after
every round. This is the dataset-aggregation curriculum from the
bootstrapping guide, disclosed as such.
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

import evaluate as ev
import norms as nz
from doomlab import (DoomLab, FRAME_SKIP, Teacher, brain_view,
                     buttons_from_scores, targets_from_buttons)

LIVE_BUDGET = 384


def student_episode_with_labels(brain, seed, norms, decisions=1050):
    """Student drives; teacher labels every visited frame."""
    lab = DoomLab()
    try:
        lab.game.set_seed(seed)
        lab.new_episode()
        teacher = Teacher()
        views, labels = [], []
        last = [0] * 7
        steps = refusals = 0
        while not lab.finished and steps < decisions:
            state = lab.state()
            if state is None:
                break
            v = state.game_variables
            periphery, fovea = brain_view(state.screen_buffer)
            periphery, fovea = nz.apply(norms, periphery, fovea)
            label = teacher.act(state, (v[3], v[4]), angle=v[5])
            views.append((periphery.ravel(), fovea.ravel()))
            labels.append(label)
            result = brain.step({"periphery": periphery.ravel().tolist(),
                                 "fovea": fovea.ravel().tolist()},
                                budget=LIVE_BUDGET)
            if result["qualified"]:
                last = buttons_from_scores(result["outputs"]["motor"])
            else:
                refusals += 1
            lab.act(last, FRAME_SKIP)
            steps += 1
        import vizdoom as vzd
        gv = lab.game.get_game_variable
        stats = {"seed": seed, "decisions": steps, "refusals": refusals,
                 "kills": gv(vzd.GameVariable.KILLCOUNT),
                 "health": gv(vzd.GameVariable.HEALTH)}
        return views, labels, stats
    finally:
        lab.close()


def admit_round(brain, examples, batch_size, rng, epochs=1):
    order = list(range(len(examples)))
    admitted = refused = 0
    for _ in range(epochs):
        rng.shuffle(order)
        for start in range(0, len(order), batch_size):
            batch = [examples[i] for i in order[start:start + batch_size]]
            result = brain.observe_batch(batch)
            if result["accepted"]:
                admitted += len(batch)
            else:
                refused += 1
    return admitted, refused


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint")
    parser.add_argument("--corpus", default="data/corpus1/witnesses.npz")
    parser.add_argument("--out", default="runs/dagger1")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--episodes", type=int, default=8)
    parser.add_argument("--replay", type=int, default=4000)
    parser.add_argument("--batch-size", type=int, default=48)
    parser.add_argument("--threads", type=int, default=6)
    args = parser.parse_args()
    import torch
    torch.set_num_threads(args.threads)
    os.makedirs(args.out, exist_ok=True)
    raw = np.load(args.corpus)
    norms = nz.load(nz.sibling_path(args.checkpoint))
    periphery, fovea = nz.apply(norms, raw["periphery"], raw["fovea"])
    corpus = {"periphery": periphery, "fovea": fovea, "buttons": raw["buttons"],
              "episode": raw["episode"], "check_episodes": raw["check_episodes"]}
    check_eps = set(corpus["check_episodes"].tolist())
    check_idx = [i for i, e in enumerate(corpus["episode"]) if e in check_eps]
    train_idx = [i for i, e in enumerate(corpus["episode"])
                 if e not in check_eps]
    brain = ev.load_brain(args.checkpoint)
    rng = random.Random(11)
    log = {"start_checkpoint": args.checkpoint, "rounds": []}
    log["baseline"] = ev.evaluate(brain, corpus, check_idx, episodes=6,
                                  norms=norms)
    print("baseline:", json.dumps(log["baseline"]["live"]), flush=True)
    for round_index in range(1, args.rounds + 1):
        views, labels, stats = [], [], []
        for e in range(args.episodes):
            v, l, s = student_episode_with_labels(
                brain, seed=7000 + 100 * round_index + e, norms=norms)
            views.extend(v)
            labels.extend(l)
            stats.append(s)
        corrections = [
            ({"periphery": per.tolist(), "fovea": fov.tolist()},
             {"motor": targets_from_buttons(label)})
            for (per, fov), label in zip(views, labels)
        ]
        replay_rows = rng.sample(train_idx, min(args.replay, len(train_idx)))
        replay = [
            ({"periphery": corpus["periphery"][i].tolist(),
              "fovea": corpus["fovea"][i].tolist()},
             {"motor": targets_from_buttons(corpus["buttons"][i])})
            for i in replay_rows
        ]
        started = time.perf_counter()
        admitted, refused = admit_round(
            brain, corrections + replay, args.batch_size, rng)
        evaluation = ev.evaluate(brain, corpus, check_idx, episodes=6,
                                 norms=norms)
        entry = {
            "round": round_index,
            "student_episodes": stats,
            "corrections": len(corrections),
            "replay": len(replay),
            "admitted": admitted,
            "refused_batches": refused,
            "train_seconds": round(time.perf_counter() - started, 1),
            "evaluation": evaluation,
        }
        log["rounds"].append(entry)
        print(f"round {round_index}:", json.dumps(evaluation["live"]),
              flush=True)
        snapshot = brain.snapshot()
        round_path = os.path.join(args.out, f"dagger_r{round_index}.json.gz")
        with gzip.open(round_path, "wt") as f:
            f.write(snapshot)
        nz.save(norms, nz.sibling_path(round_path))
        log[f"round_{round_index}_sha256"] = hashlib.sha256(
            snapshot.encode()).hexdigest()
    with open(os.path.join(args.out, "dagger_log.json"), "w") as f:
        json.dump(log, f, indent=2)
    print("done")


if __name__ == "__main__":
    main()
