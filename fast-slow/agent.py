"""One experimental application interface for a trained fast/slow agent.

Applications load one bundle, submit their usual sensory vector, and read the
qualified output. Normalization, prediction-error attention, recursive worker,
feedback timing and shutdown are internal. This is an experimental demo facade,
not a new Cadence core API or a claim of global asynchronous equilibrium.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from cadence import Brain, __version__

from actor import FastSlowActor
from attention import SurpriseAttention, threshold_from_training
from data import load, sha


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def export(run, data, output):
    run, data, output = Path(run), Path(data), Path(output)
    report = json.loads((run / "report.json").read_text())
    protocol = json.loads((run / "protocol.json").read_text())
    sequences, metadata, mean, scale = load(data)
    if report["status"] != "complete" or sha(data) != protocol["data_sha256"]:
        raise ValueError("complete training and its bound data required")
    for name in ("conditioned.json", "slow.json"):
        if sha(run / name) != report["artifacts"][name]:
            raise ValueError("checkpoint differs from training evidence")
    width = 420 if metadata["domain"] == "atari" else len(mean)
    body = {
        "schema": "cadence.experimental-agent/1",
        "cadence_version": __version__,
        "domain": metadata["domain"],
        "game": metadata.get("game"),
        "training_report_sha256": sha(run / "report.json"),
        "data_sha256": sha(data),
        "implementation": report["implementation"],
        "fast": (run / "conditioned.json").read_text(),
        "slow": (run / "slow.json").read_text(),
        "normalization": {"mean": mean.tolist(), "scale": scale.tolist()},
        "outputs": sequences[0]["y"].shape[1],
        "internal_schedule": {
            "period": protocol["period"],
            "max_age": 4.0,
            "sensory_width": width,
            "surprise_threshold": threshold_from_training(sequences, width),
        },
        "limitations": [
            "Internal timing choices are fixed experimental controls",
            "Surprise uses sensory persistence prediction",
            "Goal selection and online learning are not implemented in this facade",
            "Separate local qualification, no global-equilibrium certificate",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as handle:
        json.dump({"body": body, "sha256": digest(body)}, handle, sort_keys=True)
        handle.write("\n")
    return {"path": str(output), "bytes": output.stat().st_size, "sha256": sha(output)}


class Agent:
    def __init__(self, bundle):
        document = json.loads(Path(bundle).read_text())
        body = document["body"]
        if (
            document["sha256"] != digest(body)
            or body["schema"] != "cadence.experimental-agent/1"
        ):
            raise ValueError("invalid agent bundle")
        self.mean = np.asarray(body["normalization"]["mean"])
        self.scale = np.asarray(body["normalization"]["scale"])
        schedule = body["internal_schedule"]
        fast = Brain.from_snapshot(body["fast"], device="python")
        slow = Brain.from_snapshot(body["slow"], device="python")
        if fast.inspect()["implementation"] != body["implementation"]:
            raise ValueError("Cadence core differs from the trained implementation")
        self._actor = FastSlowActor(
            fast,
            slow,
            body["outputs"],
            period=schedule["period"],
            max_age=schedule["max_age"],
            attention=SurpriseAttention(
                schedule["surprise_threshold"],
                width=schedule["sensory_width"],
                period=schedule["period"],
            ),
        )

    def step(self, observation):
        vector = np.asarray(observation, dtype=float)
        if vector.shape != self.mean.shape or not np.isfinite(vector).all():
            raise ValueError("observation must match the bundle's sensory vector")
        result = self._actor.step(
            np.clip((vector - self.mean) / self.scale, -3, 3) * 0.2
        )
        return {"qualified": result["qualified"], "output": result["output"]}

    def close(self):
        return self._actor.close()

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.run, args.data, args.out), indent=2))
