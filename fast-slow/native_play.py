"""Native ALE free-action evaluation on predeclared seeds; never fit on these runs."""

import argparse
import json
from pathlib import Path
import time

import numpy as np
from cadence import Brain

from actor import FastSlowActor
from attention import SurpriseAttention, threshold_from_training
from data import atari_features, load, sha, teacher
from train import write


def run(args):
    import ale_py
    import gymnasium as gym

    sequences, meta, mean, scale = load(args.data)
    threshold = threshold_from_training(sequences, 420)
    training = json.loads((args.run / "report.json").read_text())
    protocol = json.loads((args.run / "protocol.json").read_text())
    if training["status"] != "complete" or sha(args.data) != protocol["data_sha256"]:
        raise ValueError("requires complete training and the bound data")
    for name, digest in training["artifacts"].items():
        if sha(args.run / name) != digest:
            raise ValueError(f"modified training artifact: {name}")
    args.out.mkdir(parents=True, exist_ok=False)
    arms = (
        "untrained",
        "fast_only",
        "conditioned",
        "conditioned_disabled",
        "conditioned_surprise",
        "teacher",
    )
    evaluation = {
        "schema": "cadence.fast-slow-native/1",
        "training_report_sha256": sha(args.run / "report.json"),
        "data_sha256": sha(args.data),
        "sources": {p.name: sha(p) for p in Path(__file__).parent.glob("*.py")},
        "game": meta["game"],
        "arms": arms,
        "seeds": meta["reserved_play_seeds"],
        "frames_per_arm": args.frames,
        "attention": {
            "prediction": "persistence of normalized current pixels",
            "threshold": threshold,
            "calibration": "training transition RMS 95th percentile",
            "passive_blocks": 4,
            "burst_blocks": 2,
        },
        "seconds_per_action": 1 / 15,
        "clock": "best-effort 15 decisions/sec, frameskip=4, no sticky actions",
        "nonclaims": [
            "Bounded returns may be censored",
            "Teacher uses hidden RAM; learned actors receive pixels only",
            "No training or model selection on these outcomes",
        ],
        "episodes": [],
    }
    write(args.out / "report.json", evaluation)
    gym.register_envs(ale_py)
    env = gym.make(
        f"ALE/{meta['game']}-v5",
        frameskip=4,
        repeat_action_probability=0.0,
        full_action_space=False,
    )
    meanings = env.unwrapped.get_action_meanings()
    if meanings != meta["meanings"]:
        raise ValueError("action encoding changed")
    try:
        for seed in meta["reserved_play_seeds"]:
            for arm in arms:
                obs, _ = env.reset(seed=seed)
                for _ in range(1 + seed % 29):
                    obs, _, terminated, truncated, _ = env.step(0)
                    if terminated or truncated:
                        raise RuntimeError("native episode ended during declared start")
                actor = None
                if arm != "teacher":
                    checkpoint = "conditioned" if arm.startswith("conditioned") else arm
                    actor = FastSlowActor(
                        Brain.from_snapshot(
                            (args.run / f"{checkpoint}.json").read_text(),
                            device="python",
                        ),
                        Brain.from_snapshot(
                            (args.run / "slow.json").read_text(), device="python"
                        ),
                        len(meanings),
                        period=protocol["period"],
                        max_age=2.0,
                        enabled=arm in {"conditioned", "conditioned_surprise"},
                        attention=SurpriseAttention(
                            threshold, width=420, period=protocol["period"]
                        )
                        if arm == "conditioned_surprise"
                        else None,
                    )
                rows, pictures, latencies = [], [], []
                previous, action, score, refused = None, 0, 0.0, False
                started = time.monotonic()
                try:
                    for tick in range(args.frames):
                        began = time.monotonic()
                        if tick % 128 == 0:
                            pictures.append(obs.copy())
                        x, previous = atari_features(
                            obs, previous, action, len(meanings)
                        )
                        if actor is None:
                            action = teacher(
                                meta["game"], env.unwrapped.ale.getRAM(), meanings, tick
                            )
                        else:
                            result = actor.step(
                                np.clip((x - mean) / scale, -3, 3) * 0.2
                            )
                            if not result["qualified"]:
                                refused = True
                                break
                            action = int(np.argmax(result["output"]))
                        age = time.monotonic() - began
                        latencies.append(age)
                        obs, reward, terminated, truncated, _ = env.step(action)
                        score += float(reward)
                        rows.append(
                            {
                                "tick": tick,
                                "action": action,
                                "reward": float(reward),
                                "observation_to_action_seconds": age,
                            }
                        )
                        if terminated or truncated:
                            break
                        time.sleep(max(0, 1 / 15 - (time.monotonic() - began)))
                finally:
                    trace = actor.close() if actor is not None else None
                name = f"{seed}-{arm}"
                write(
                    args.out / f"{name}.json", {"actions": rows, "settlements": trace}
                )
                np.savez_compressed(
                    args.out / f"{name}-frames.npz", frames=np.asarray(pictures)
                )
                episode = {
                    "seed": seed,
                    "arm": arm,
                    "return": score,
                    "decisions": len(rows),
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                    "censored": not (terminated or truncated),
                    "refused": refused,
                    "wall_seconds": time.monotonic() - started,
                    "observation_to_action_median_ms": 1000
                    * float(np.median(latencies))
                    if latencies
                    else None,
                    "observation_to_action_p95_ms": 1000
                    * float(np.quantile(latencies, 0.95))
                    if latencies
                    else None,
                    "action_deadline_misses": sum(t > 1 / 15 for t in latencies),
                    "feedback_actions": sum(
                        r["feedback_source_tick"] >= 0 for r in actor.rows
                    )
                    if actor
                    else 0,
                    "runtime": trace["runtime"] if trace else None,
                    "trace_sha256": sha(args.out / f"{name}.json"),
                }
                evaluation["episodes"].append(episode)
                write(args.out / "report.json", evaluation)
                print(
                    json.dumps({k: v for k, v in episode.items() if k != "runtime"}),
                    flush=True,
                )
    finally:
        env.close()
    evaluation["status"] = "complete"
    evaluation["sources_unchanged"] = all(
        sha(Path(__file__).parent / k) == v for k, v in evaluation["sources"].items()
    )
    write(args.out / "report.json", evaluation)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=512)
    run(parser.parse_args())
