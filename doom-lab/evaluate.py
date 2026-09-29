"""Evaluate a checkpoint honestly: held-out agreement, live episodes, control.

Live episodes run the brain alone (pixels only, hold-last-action on refusal).
The control plays the same episode seeds with buttons drawn from the training
corpus's marginal button-row distribution, so "better than control" cannot
come from the action prior alone.
"""

from __future__ import annotations

import argparse
import gzip
import json
import random

import numpy as np

from cadence import Brain

from doomlab import DoomLab, FRAME_SKIP, brain_view, buttons_from_scores
import norms as nz

LIVE_BUDGET = 384


def load_brain(path, device="cpu"):
    with gzip.open(path, "rt") as f:
        return Brain.from_snapshot(f.read(), device=device)


def agreement(brain, corpus, indices, limit=800, seed=0):
    """Per-button decoded agreement on held-out frames (pure queries)."""
    rng = random.Random(seed)
    rows = list(indices)
    rng.shuffle(rows)
    rows = rows[:limit]
    hits = np.zeros(corpus["buttons"].shape[1])
    pressed_hits = np.zeros_like(hits)
    pressed_count = np.zeros_like(hits)
    refused = 0
    for i in rows:
        inputs = {"periphery": corpus["periphery"][i].tolist(),
                  "fovea": corpus["fovea"][i].tolist()}
        result = brain.settle(inputs, budget=LIVE_BUDGET)
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
    state = {"last": [0] * 7}

    def policy(views):
        periphery, fovea = views
        if norms is not None:
            periphery, fovea = nz.apply(norms, periphery, fovea)
        inputs = {"periphery": periphery.ravel().tolist(),
                  "fovea": fovea.ravel().tolist()}
        result = brain.step(inputs, budget=LIVE_BUDGET)
        if result["qualified"]:
            state["last"] = buttons_from_scores(result["outputs"]["motor"])
            return state["last"], False
        return state["last"], True

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
    live = [live_episode(brain_policy(brain, norms), seed0 + i)
            for i in range(episodes)]
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
    args = parser.parse_args()
    raw = np.load(args.corpus)
    norms = nz.load(nz.sibling_path(args.checkpoint))
    periphery, fovea = nz.apply(norms, raw["periphery"], raw["fovea"])
    corpus = {"periphery": periphery, "fovea": fovea, "buttons": raw["buttons"],
              "episode": raw["episode"], "check_episodes": raw["check_episodes"]}
    check_eps = set(corpus["check_episodes"].tolist())
    check_idx = [i for i, e in enumerate(corpus["episode"]) if e in check_eps]
    brain = load_brain(args.checkpoint)
    print(json.dumps(evaluate(brain, corpus, check_idx, episodes=args.episodes,
                              norms=norms), indent=2))


if __name__ == "__main__":
    main()
