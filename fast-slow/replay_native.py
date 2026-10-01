"""Independently replay saved actions in ALE and verify observation/reward custody."""

import argparse
import json
from pathlib import Path

import ale_py
import gymnasium as gym
import numpy as np

from data import sha


def verify(root):
    gym.register_envs(ale_py)
    checked = []
    for path in sorted(root.glob("native-wave1-*/report.json")):
        report = json.loads(path.read_text())
        assert report["status"] == "complete" and report["sources_unchanged"]
        env = gym.make(
            f"ALE/{report['game']}-v5",
            frameskip=4,
            repeat_action_probability=0.0,
            full_action_space=False,
        )
        try:
            for episode in report["episodes"]:
                name = f"{episode['seed']}-{episode['arm']}"
                trace_path = path.parent / f"{name}.json"
                assert sha(trace_path) == episode["trace_sha256"]
                trace = json.loads(trace_path.read_text())
                with np.load(path.parent / f"{name}-frames.npz") as z:
                    frames = z["frames"].copy()
                obs, _ = env.reset(seed=episode["seed"])
                for _ in range(1 + episode["seed"] % 29):
                    obs, _, terminated, truncated, _ = env.step(0)
                    assert not (terminated or truncated)
                reward = 0
                for tick, row in enumerate(trace["actions"]):
                    assert row["tick"] == tick
                    if tick % 128 == 0:
                        assert np.array_equal(obs, frames[tick // 128])
                    if trace["settlements"]:
                        decision = trace["settlements"]["fast"][tick]
                        assert decision["qualified"]
                        assert int(np.argmax(decision["output"])) == row["action"]
                        source = decision["feedback_source_tick"]
                        if source >= 0:
                            assert 8 <= tick - source < 16
                            assert 0 <= decision["feedback_age_seconds"] <= 2
                        else:
                            assert all(x == 0 for x in decision["feedback"])
                    obs, received, terminated, truncated, _ = env.step(row["action"])
                    assert float(received) == row["reward"]
                    reward += float(received)
                    if terminated or truncated:
                        assert tick == len(trace["actions"]) - 1
                assert reward == episode["return"]
                assert bool(terminated) == episode["terminated"]
                assert bool(truncated) == episode["truncated"]
                assert len(trace["actions"]) == episode["decisions"]
                if trace["settlements"]:
                    runtime = trace["settlements"]["runtime"]
                    assert (
                        not runtime["worker_alive"]
                        and not runtime["errors"]
                        and not runtime["refused"]
                    )
                checked.append(
                    {
                        "run": path.parent.name,
                        "episode": name,
                        "decisions": len(trace["actions"]),
                        "return": reward,
                        "verified": True,
                    }
                )
        finally:
            env.close()
    assert len(checked) == 48
    return {
        "schema": "cadence.fast-slow-native-replay/1",
        "source_sha256": sha(__file__),
        "ale_version": ale_py.__version__,
        "episodes": checked,
        "verified": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.root)
    with args.out.open("x") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(
        f"Verified {len(result['episodes'])} native episodes, every action/reward, captured frames and feedback timing."
    )
