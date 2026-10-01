"""Verify preserved training evidence and reload the actual candidate snapshots."""

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
from cadence import Brain

from data import load, sha


def verify(run, data, sources):
    report = json.loads((run / "report.json").read_text())
    protocol = json.loads((run / "protocol.json").read_text())
    assert report["status"] == "complete" and report["sources_unchanged"]
    assert sha(run / "protocol.json") == report["protocol_sha256"]
    assert sha(data) == protocol["data_sha256"]
    assert sha(run / "training.jsonl") == report["ledger_sha256"]
    for name, digest in report["artifacts"].items():
        assert sha(run / name) == digest, name
    for name, digest in protocol["sources"].items():
        assert sha(sources / name) == digest, name
    rows = [
        json.loads(line) for line in (run / "training.jsonl").read_text().splitlines()
    ]
    attempted = Counter(r["phase"] for r in rows)
    accepted = Counter(r["phase"] for r in rows if r["accepted"])
    for phase in report["phases"]:
        assert phase["status"] == "complete"
        assert (
            phase["attempted"] == attempted[phase["phase"]] == phase["planned_updates"]
        )
        assert phase["accepted"] == accepted[phase["phase"]]
    matched = [
        [r["rows"] for r in rows if r["phase"] == phase]
        for phase in ("fast_only", "conditioned")
    ]
    assert matched[0] == matched[1]
    sequences, _, _, _ = load(data)
    train_names = {s["name"] for s in sequences if not s["split"]}
    valid_names = {s["name"] for s in sequences if s["split"]}
    assert train_names.isdisjoint(valid_names)
    sequence = next(s for s in sequences if s["split"])
    reloaded = {}
    for model in ("untrained", "founder", "fast_only", "conditioned", "slow"):
        brain = Brain.from_snapshot(
            (run / f"{model}.json").read_text(), device="python"
        )
        before = brain.snapshot()
        n = sequence["y"].shape[1]
        inputs = {
            "features": sequence["x"][0].tolist(),
            "readback" if model == "slow" else "feedback": [0.0]
            * (2 * n if model == "slow" else n),
        }
        result = brain.settle(inputs)
        assert result["qualified"] and np.isfinite(result["outputs"]["answer"]).all()
        assert brain.snapshot() == before
        reloaded[model] = {
            "qualified": True,
            "sweeps": result["sweeps"],
            "outputs": result["outputs"]["answer"],
        }
    return {
        "run": run.name,
        "report_sha256": sha(run / "report.json"),
        "data_sha256": sha(data),
        "verified": True,
        "attempted_updates": len(rows),
        "accepted_updates": sum(accepted.values()),
        "matched_final_training_rows": True,
        "reloaded": reloaded,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.run, args.data, args.sources), indent=2))
