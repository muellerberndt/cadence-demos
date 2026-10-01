"""Independently check completed numerical and credit development receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root):
    sys.path.insert(0, str(root / "code/src"))
    from cadence import Brain

    query = []
    for path in sorted((root / "query").glob("*/report.json")):
        report = read(path)
        folder = path.parent
        protocol = read(folder / "protocol.json")
        assert report["status"] == "complete" and report["sources_unchanged"]
        assert report["protocol_sha256"] == sha(folder / "protocol.json")
        assert report["ledger_sha256"] == sha(folder / "queries.jsonl")
        assert all(sha(Path(p)) == h for p, h in protocol["sources"].items())
        rows = [
            json.loads(line)
            for line in (folder / "queries.jsonl").read_text().splitlines()
        ]
        assert len(rows) == 640 == protocol["planned_calls_per_arm"]
        for row in rows:
            assert row["exact"] and not row["different_fields"]
            assert row["baseline"]["qualified"] and row["candidate"]["qualified"]
            assert (
                row["baseline"]["semantic_sha256"]
                == row["candidate"]["semantic_sha256"]
            )
            assert row["baseline"]["sweeps"] == row["candidate"]["sweeps"]
        for arm in ("baseline", "candidate"):
            totals = Counter()
            for row in rows:
                totals.update(row[arm]["work"])
            assert dict(totals) == report["summary"]["all"]["arms"][arm]["work"]
        query.append(
            {
                "name": folder.name,
                "identity": protocol["identity"],
                "report_sha256": sha(path),
                "summary": report["summary"],
            }
        )
    assert len(query) == 16
    credit = []
    executed = 0
    for path in sorted((root / "credit").glob("*/report.json")):
        report = read(path)
        folder = path.parent
        protocol = report["protocol"]
        assert report["status"] == "complete" and report["sources_unchanged"]
        for name, expected in protocol["sources"].items():
            assert sha(root / "code" / name) == expected
        assert report["collection_sha256"] == sha(folder / "collection.json")
        assert report["batches_sha256"] == sha(folder / "batches.json")
        batches = read(folder / "batches.json")
        delay, preferred = protocol["delay"], protocol["preferred"]
        assert len(batches) == 32
        assert len(report["records"]) == 24 * (delay + 1)
        for i, row in enumerate(report["records"]):
            stage, episode = i % (delay + 1), i // (delay + 1)
            assert row["stage"] == stage and row["episode"] == episode
            terminal = stage == delay
            assert (row["following"] is None) == terminal
            expected_reward = (
                (1 if row["first_action"] == preferred else -1) if terminal else 0
            )
            assert row["reward"] == expected_reward
            if not terminal:
                assert row["following"] == report["records"][i + 1]["context"]
        arms = []
        for arm in report["arms"]:
            assert arm["status"] == "complete" and len(arm["updates"]) == 32
            assert [u["indices"] for u in arm["updates"]] == batches
            assert all(
                u["accepted"] and u["source"] == "estimate" for u in arm["updates"]
            )
            assert all(abs(v) <= 0.9 for u in arm["updates"] for v in u["targets"])
            checkpoint = folder / f"{arm['name']}-brain.json"
            assert sha(checkpoint) == arm["brain_sha256"]
            brain = Brain.from_snapshot(checkpoint.read_text())
            before = brain.snapshot()
            initial = [1.0] + [0.0] * (2 * delay)
            root_result = brain.settle({"senses": initial})
            assert root_result["qualified"] and brain.snapshot() == before
            values = [root_result["outputs"][f"q{i}"][0] for i in range(2)]
            assert values == arm["queries"][-1]["values"]
            actions = arm["evaluation"]["actions"]
            assert len(actions) == delay + 1
            for stage, action in enumerate(actions):
                inputs = [0.0] * (1 + 2 * delay)
                inputs[0 if stage == 0 else 1 + 2 * (stage - 1) + actions[0]] = 1.0
                result = brain.step({"senses": inputs})
                assert result["qualified"]
                values = [result["outputs"][f"q{i}"][0] for i in range(2)]
                assert values[action] == max(values)
                executed += 1
            assert arm["evaluation"]["reward"] == (1 if actions[0] == preferred else -1)
            arms.append(
                {
                    "name": arm["name"],
                    "reward": arm["evaluation"]["reward"],
                    "queries": [
                        {k: v for k, v in q.items() if k != "work"}
                        for q in arm["queries"]
                    ],
                    "work": arm["work"],
                    "replay_seconds": arm["replay_seconds"],
                    "brain_sha256": arm["brain_sha256"],
                }
            )
        credit.append(
            {
                "name": folder.name,
                "seed": protocol["seed"],
                "delay": delay,
                "preferred": preferred,
                "coverage_missing": len(report["coverage"]["missing"]),
                "arms": arms,
                "report_sha256": sha(path),
                "collection_sha256": report["collection_sha256"],
            }
        )
    assert len(credit) == 30
    return {
        "query_pairs": 10240,
        "credit_brains_reloaded": 90,
        "credit_updates": 2880,
        "credit_presentations": 46080,
        "credit_free_decisions_rechecked": executed,
        "query": query,
        "credit": credit,
        "verifier_sha256": sha(Path(__file__)),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.root)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in {"query", "credit"}
            }
        )
    )
