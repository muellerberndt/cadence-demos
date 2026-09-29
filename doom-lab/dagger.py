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
from train_self import foresight_targets

LIVE_BUDGET = 512


def calibrate(brain, corpus, rows, streams, n=150, budget=512):
    """Per-button decode thresholds and score means from fixed probe rows.

    Recomputed every round: admission moves the score distribution, so the
    operating point follows the policy instead of the run's first hour.
    """
    picks = random.Random(1234).sample(list(rows), min(n, len(rows)))
    scores, truths = [], []
    for i in picks:
        r = brain.settle(ev.corpus_inputs(corpus, i, streams), budget=budget)
        if not r["qualified"]:
            continue
        scores.append(r["outputs"]["motor"])
        truths.append(corpus["buttons"][i])
    if len(scores) < 20:
        raise SystemExit(
            f"calibration failed: {len(scores)} of {len(picks)} probe "
            f"settles qualified at budget {budget}")
    S = np.array(scores)
    T = np.array(truths, int)
    base = T.mean(0)
    thresholds = [float(np.quantile(S[:, j], 1 - base[j])) if base[j] > 0
                  else None for j in range(S.shape[1])]
    return {"thresholds": thresholds,
            "score_mean": S.mean(0).round(3).tolist()}


def calibrated_decode(calibration):
    thresholds = calibration["thresholds"]

    def decode(motor):
        b = [1 if t is not None and s > t else 0
             for s, t in zip(motor, thresholds)]
        for i, j in ((0, 7), (1, 2), (5, 6)):
            if b[i] and b[j]:
                mi = motor[i] - (thresholds[i] or 0.0)
                mj = motor[j] - (thresholds[j] or 0.0)
                keep = i if mi >= mj else j
                b[i] = 1 if keep == i else 0
                b[j] = 1 if keep == j else 0
        return b

    return decode


def student_episode_with_labels(brain, seed, norms, streams, decisions=1050,
                                decode=None, beta=0.0):
    """Student drives with its full input set; teacher labels every frame.

    Each recorded witness carries the inputs the student actually settled
    on, including its own efference and history context, so corrections
    teach the teacher's action in the state the student got itself into.
    """
    lab = DoomLab()
    try:
        lab.game.set_seed(seed)
        lab.new_episode()
        teacher = Teacher()
        feeder = ev.ContextFeeder(streams)
        decode = decode or buttons_from_scores
        mix = random.Random(seed * 31 + 7)
        witnesses, labels = [], []
        steps = refusals = 0
        while not lab.finished and steps < decisions:
            state = lab.state()
            if state is None:
                break
            v = state.game_variables
            periphery, fovea = brain_view(state.screen_buffer)
            periphery, fovea = nz.apply(norms, periphery, fovea)
            label = teacher.act(state, (v[3], v[4]), angle=v[5])
            inputs = feeder.frame_inputs(periphery, fovea)
            witnesses.append(inputs)
            labels.append(label)
            result = brain.step(inputs, budget=LIVE_BUDGET)
            if result["qualified"]:
                feeder.last = decode(result["outputs"]["motor"])
            else:
                refusals += 1
            if beta > 0 and mix.random() < beta:
                # Mixed rollout: the teacher acts, the state distribution
                # reaches its route; efference stays the executed action.
                feeder.last = [int(b) for b in label]
            lab.act(feeder.last, FRAME_SKIP)
            steps += 1
        import vizdoom as vzd
        gv = lab.game.get_game_variable
        stats = {"seed": seed, "decisions": steps, "refusals": refusals,
                 "kills": gv(vzd.GameVariable.KILLCOUNT),
                 "health": gv(vzd.GameVariable.HEALTH)}
        return witnesses, labels, stats
    finally:
        lab.close()


def replay_targets(corpus, i, teach_outcome):
    """Corpus-row targets; corrections stay motor-only because the measured
    outcome followed the student's action, and the taught action is the
    teacher's."""
    targets = {"motor": targets_from_buttons(corpus["buttons"][i])}
    if teach_outcome:
        targets["outcome"] = foresight_targets(corpus, i)
    return targets


def admit_round(brain, examples, batch_size, rng, epochs=1):
    order = list(range(len(examples)))
    admitted = refused = batches = 0
    started = time.perf_counter()
    for _ in range(epochs):
        rng.shuffle(order)
        for start in range(0, len(order), batch_size):
            batch = [examples[i] for i in order[start:start + batch_size]]
            result = brain.observe_batch(batch)
            batches += 1
            if result["accepted"]:
                admitted += len(batch)
            else:
                refused += 1
            if batches % 10 == 0:
                print(f"admit {admitted}/{len(order) * epochs} "
                      f"sweeps={result['sweeps']} "
                      f"{time.perf_counter() - started:.0f}s", flush=True)
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
    parser.add_argument("--decisions", type=int, default=1050,
                        help="decision steps per student episode")
    parser.add_argument("--eval-episodes", type=int, default=6)
    parser.add_argument("--beta0", type=float, default=0.0,
                        help="round-1 teacher-mixing rate")
    parser.add_argument("--beta-decay", type=float, default=0.2,
                        help="mixing reduction per round")
    args = parser.parse_args()
    import torch
    torch.set_num_threads(args.threads)
    os.makedirs(args.out, exist_ok=True)
    brain = ev.load_brain(args.checkpoint)
    streams = ev.input_streams(brain)
    raw = np.load(args.corpus)
    norms = nz.load(nz.sibling_path(args.checkpoint))
    episode = raw["episode"]
    check_eps = set(raw["check_episodes"].tolist())
    check_idx = [i for i, e in enumerate(episode) if e in check_eps]
    # Replay rows need a measured next-step outcome: same-episode successor.
    train_idx = [i for i in range(len(episode) - 1)
                 if episode[i] not in check_eps
                 and episode[i + 1] == episode[i]]
    rng = random.Random(11)
    replay_plan = [rng.sample(train_idx, min(args.replay, len(train_idx)))
                   for _ in range(args.rounds)]
    needed = set(check_idx)
    for rows in replay_plan:
        needed.update(rows)
    corpus = ev.prepare_corpus(raw, norms, streams, needed)
    teach_outcome = ("outcome" in ev.output_streams(brain)
                     and all(k in corpus for k in ("health", "ammo", "kills")))
    log = {"start_checkpoint": args.checkpoint, "rounds": []}
    calibration = calibrate(brain, corpus, check_idx, streams)
    print("calibration:", json.dumps(calibration), flush=True)
    log["baseline_calibration"] = calibration
    log["baseline"] = ev.evaluate(brain, corpus, check_idx,
                                  episodes=args.eval_episodes, norms=norms,
                                  decode=calibrated_decode(calibration))
    print("baseline:", json.dumps(log["baseline"]["live"]), flush=True)
    for round_index in range(1, args.rounds + 1):
        decode = calibrated_decode(calibration)
        beta = max(0.0, args.beta0 - args.beta_decay * (round_index - 1))
        print(f"round {round_index} beta={beta}", flush=True)
        witnesses, labels, stats = [], [], []
        for e in range(args.episodes):
            w, l, s = student_episode_with_labels(
                brain, seed=7000 + 100 * round_index + e, norms=norms,
                streams=streams, decisions=args.decisions, decode=decode,
                beta=beta)
            witnesses.extend(w)
            labels.extend(l)
            stats.append(s)
            print(f"round {round_index} episode {e + 1}: "
                  f"{json.dumps(s)}", flush=True)
        corrections = [
            (inputs, {"motor": targets_from_buttons(label)})
            for inputs, label in zip(witnesses, labels)
        ]
        replay_rows = replay_plan[round_index - 1]
        replay = [
            (ev.corpus_inputs(corpus, i, streams),
             replay_targets(corpus, i, teach_outcome))
            for i in replay_rows
        ]
        started = time.perf_counter()
        admitted, refused = admit_round(
            brain, corrections + replay, args.batch_size, rng)
        calibration = calibrate(brain, corpus, check_idx, streams)
        print(f"round {round_index} calibration:",
              json.dumps(calibration), flush=True)
        evaluation = ev.evaluate(brain, corpus, check_idx,
                                 episodes=args.eval_episodes, norms=norms,
                                 decode=calibrated_decode(calibration))
        entry = {
            "round": round_index,
            "student_episodes": stats,
            "corrections": len(corrections),
            "replay": len(replay),
            "admitted": admitted,
            "refused_batches": refused,
            "train_seconds": round(time.perf_counter() - started, 1),
            "calibration": calibration,
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
        with open(round_path.replace(".json.gz", ".meta.json"), "w") as f:
            json.dump({"label": f"DAgger round {round_index}",
                       "deep": {"probe": calibration}}, f)
        log[f"round_{round_index}_sha256"] = hashlib.sha256(
            snapshot.encode()).hexdigest()
        # The log survives an interrupted run round by round.
        with open(os.path.join(args.out, "dagger_log.json"), "w") as f:
            json.dump(log, f, indent=2)
    with open(os.path.join(args.out, "dagger_log.json"), "w") as f:
        json.dump(log, f, indent=2)
    print("done", flush=True)


if __name__ == "__main__":
    main()
