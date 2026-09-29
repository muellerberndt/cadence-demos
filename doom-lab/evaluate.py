"""Evaluate a checkpoint honestly: held-out agreement, live episodes, control.

Live episodes run the brain alone (pixels only, hold-last-action on refusal).
The control plays the same episode seeds with buttons drawn from the training
corpus's marginal button-row distribution, so "better than control" cannot
come from the action prior alone. The brain's declared input streams decide
what each frame carries: efference and the explicit history windows are fed
exactly as the lab's Student feeds them, so flagship and ultimate layouts
evaluate with their full input set.
"""

from __future__ import annotations

import argparse
import gzip
import json
import random

import numpy as np

from cadence import Brain
from cadence.memory import History

from doomlab import BUTTONS, DoomLab, FRAME_SKIP, brain_view, \
    buttons_from_scores
from layouts import HIST_SIZE, HIST_STEPS, PHIST_SIZE, PHIST_STEPS
from train_flagship import (EFF_ON, EFF_OFF, half_fovea, quarter_periphery,
                            window_matrix)
import norms as nz

LIVE_BUDGET = 384


def load_brain(path, device="cpu"):
    with gzip.open(path, "rt") as f:
        return Brain.from_snapshot(f.read(), device=device)


def input_streams(brain):
    """Names of the brain's declared input streams."""
    return {i["name"] for i in brain.inspect()["inputs"]}


def output_streams(brain):
    """Names of the brain's declared output streams."""
    return {o["name"] for o in brain.inspect()["outputs"]}


def corpus_inputs(corpus, i, streams):
    """One corpus row's inputs, restricted to the brain's streams."""
    inputs = {"periphery": corpus["periphery"][i].tolist(),
              "fovea": corpus["fovea"][i].tolist()}
    if "efference" in streams:
        inputs["efference"] = [EFF_ON if b else EFF_OFF
                               for b in corpus["efference"][i]]
    if "fovea_history" in streams:
        inputs["fovea_history"] = corpus["fovea_history"][i].tolist()
    if "periphery_history" in streams:
        inputs["periphery_history"] = corpus["periphery_history"][i].tolist()
    return inputs


def prepare_corpus(raw, norms, streams, needed_rows):
    """Normalized corpus dict with history windows for the needed rows."""
    periphery, fovea = nz.apply(norms, raw["periphery"], raw["fovea"])
    corpus = {"periphery": periphery, "fovea": fovea,
              "buttons": raw["buttons"], "episode": raw["episode"],
              "check_episodes": raw["check_episodes"]}
    for key in ("efference", "health", "ammo", "kills"):
        if key in raw:
            corpus[key] = raw[key]
    if "efference" in streams and "efference" not in corpus:
        raise SystemExit("brain expects efference; the corpus has none")
    rows = sorted(set(needed_rows))
    if "fovea_history" in streams:
        corpus["fovea_history"] = window_matrix(
            corpus, rows, "fovea", half_fovea, HIST_SIZE, HIST_STEPS)
    if "periphery_history" in streams:
        corpus["periphery_history"] = window_matrix(
            corpus, rows, "periphery", quarter_periphery,
            PHIST_SIZE, PHIST_STEPS)
    return corpus


class ContextFeeder:
    """Live-side context state: history windows and efference.

    Mirrors the lab Student's feeding: the window is pushed before the
    settle, so it includes the current frame, and efference carries the
    previously executed action.
    """

    def __init__(self, streams):
        self.streams = streams
        self._history = History(HIST_SIZE, steps=HIST_STEPS)
        self._phistory = History(PHIST_SIZE, steps=PHIST_STEPS)
        self.last = [0] * len(BUTTONS)

    def frame_inputs(self, periphery, fovea):
        """Inputs for one normalized frame."""
        inputs = {"periphery": np.ravel(periphery).tolist(),
                  "fovea": np.ravel(fovea).tolist()}
        if "efference" in self.streams:
            inputs["efference"] = [EFF_ON if b else EFF_OFF
                                   for b in self.last]
        if "fovea_history" in self.streams:
            inputs["fovea_history"] = list(
                self._history.push(half_fovea(fovea).tolist()))
        if "periphery_history" in self.streams:
            inputs["periphery_history"] = list(
                self._phistory.push(quarter_periphery(periphery).tolist()))
        return inputs


def agreement(brain, corpus, indices, limit=800, seed=0):
    """Per-button decoded agreement on held-out frames (pure queries)."""
    streams = input_streams(brain)
    rng = random.Random(seed)
    rows = list(indices)
    rng.shuffle(rows)
    rows = rows[:limit]
    hits = np.zeros(corpus["buttons"].shape[1])
    pressed_hits = np.zeros_like(hits)
    pressed_count = np.zeros_like(hits)
    refused = 0
    for i in rows:
        result = brain.settle(corpus_inputs(corpus, i, streams),
                              budget=LIVE_BUDGET)
        if not result["qualified"]:
            refused += 1
            continue
        decoded = np.array(buttons_from_scores(result["outputs"]["motor"]))
        truth = corpus["buttons"][i]
        hits += decoded == truth
        pressed_count += truth
        pressed_hits += (decoded == truth) & (truth == 1)
    n = len(rows) - refused
    return {
        "frames": len(rows),
        "refused": refused,
        "per_button": (hits / max(1, n)).round(3).tolist(),
        "mean": float((hits / max(1, n)).mean().round(3)),
        "pressed_recall": [
            round(float(h / c), 3) if c else None
            for h, c in zip(pressed_hits, pressed_count)
        ],
    }


def live_episode(policy, seed, decisions=1050):
    """One episode driven by policy(state_views) -> buttons."""
    import vizdoom as vzd
    lab = DoomLab()
    try:
        lab.game.set_seed(seed)
        lab.new_episode()
        steps = path = 0
        last = None
        refusals = 0
        while not lab.finished and steps < decisions:
            state = lab.state()
            if state is None:
                break
            v = state.game_variables
            if last is not None:
                path += float(np.hypot(v[3] - last[0], v[4] - last[1]))
            last = (v[3], v[4])
            views = brain_view(state.screen_buffer)
            buttons, refused = policy(views)
            refusals += int(refused)
            lab.act(buttons, FRAME_SKIP)
            steps += 1
        gv = lab.game.get_game_variable
        return {
            "seed": seed,
            "decisions": steps,
            "kills": gv(vzd.GameVariable.KILLCOUNT),
            "health": gv(vzd.GameVariable.HEALTH),
            "survived": steps >= decisions or gv(vzd.GameVariable.HEALTH) > 0,
            "path": round(path, 1),
            "refusals": refusals,
        }
    finally:
        lab.close()


def brain_policy(brain, norms=None):
    feeder = ContextFeeder(input_streams(brain))

    def policy(views):
        periphery, fovea = views
        if norms is not None:
            periphery, fovea = nz.apply(norms, periphery, fovea)
        result = brain.step(feeder.frame_inputs(periphery, fovea),
                            budget=LIVE_BUDGET)
        if result["qualified"]:
            feeder.last = buttons_from_scores(result["outputs"]["motor"])
            return feeder.last, False
        return feeder.last, True

    return policy


def marginal_policy(corpus, seed):
    rng = random.Random(seed)
    rows = corpus["buttons"]

    def policy(_views):
        return rows[rng.randrange(len(rows))].tolist(), False

    return policy


def evaluate(brain, corpus, check_indices, episodes=6, seed0=9000, norms=None):
    """corpus arrays must already be in the brain's input units."""
    report = {"agreement": agreement(brain, corpus, check_indices)}
    print(f"agreement mean={report['agreement']['mean']} "
          f"refused={report['agreement']['refused']}", flush=True)
    live = []
    for i in range(episodes):
        row = live_episode(brain_policy(brain, norms), seed0 + i)
        print(f"live seed={row['seed']} path={row['path']} "
              f"kills={row['kills']} refusals={row['refusals']}", flush=True)
        live.append(row)
    control = [live_episode(marginal_policy(corpus, 77 + i), seed0 + i)
               for i in range(episodes)]

    def summary(rows):
        return {
            "episodes": rows,
            "mean_kills": round(float(np.mean([r["kills"] for r in rows])), 2),
            "mean_path": round(float(np.mean([r["path"] for r in rows])), 1),
            "survival_rate": round(float(np.mean(
                [r["survived"] for r in rows])), 2),
            "total_refusals": int(sum(r["refusals"] for r in rows)),
        }

    report["live"] = summary(live)
    report["marginal_control"] = summary(control)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint")
    parser.add_argument("--corpus", default="data/corpus1/witnesses.npz")
    parser.add_argument("--episodes", type=int, default=6)
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args()
    import torch
    torch.set_num_threads(args.threads)
    brain = load_brain(args.checkpoint)
    raw = np.load(args.corpus)
    norms = nz.load(nz.sibling_path(args.checkpoint))
    check_eps = set(raw["check_episodes"].tolist())
    check_idx = [i for i, e in enumerate(raw["episode"]) if e in check_eps]
    corpus = prepare_corpus(raw, norms, input_streams(brain), check_idx)
    print(json.dumps(evaluate(brain, corpus, check_idx, episodes=args.episodes,
                              norms=norms), indent=2))


if __name__ == "__main__":
    main()
