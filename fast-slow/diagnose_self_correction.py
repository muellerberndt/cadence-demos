"""Read-only acquisition and action-sensitivity audit of frozen microtest brains.

No teaching or new comparison arm: hold each observed gate history fixed and
query its archived post-gate brain at candidate actions -0.5 and +0.5. The
receipt records complete qualification, snapshot purity, and source custody.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diagnose(root):
    first = read(root / "seed2/protocol.json")
    source = next(Path(p) for p in first["sources"] if p.endswith("/cadence/brain.py"))
    assert all(
        sha(Path(path)) == expected for path, expected in first["sources"].items()
    )
    sys.path.insert(0, str(source.parent.parent))
    from cadence import Brain

    cases, all_work, total_calls, admissions = [], Counter(), 0, 0
    for seed in (2, 7, 11, 19, 29):
        case = root / f"seed{seed}"
        protocol, tape = read(case / "protocol.json"), read(case / "tape.json")
        assert protocol["sources"] == first["sources"]
        assert protocol["tape_sha256"] == sha(case / "tape.json")
        for arm in ("ordinary", "observer"):
            folder = case / arm
            report = read(folder / "report.json")
            assert report["status"] == "complete" and report["sources_unchanged"]
            assert report["protocol_sha256"] == sha(case / "protocol.json")
            assert report["ledger_sha256"] == sha(folder / "calls.jsonl")
            calls = [
                json.loads(line)
                for line in (folder / "calls.jsonl").read_text().splitlines()
            ]
            assert len(calls) == 820
            assert all(
                c["status"] == "returned" and c["result"]["qualified"] for c in calls
            )
            taught = [c for c in calls if c["kind"] == "admission"]
            assert len(taught) == 160
            assert all(
                c["result"]["accepted"] and c["result"]["source"] == "witness"
                for c in taught
            )
            total_calls += len(calls)
            admissions += len(taught)
            all_work.update(report["groups"]["all"]["work"])
            gate = [c for c in calls if c["phase"] == "gate"]
            assert len(gate) == 16
            assert math.isclose(
                statistics.mean(c["position_error"] for c in gate),
                report["gate"]["position_mae"],
                rel_tol=0,
                abs_tol=1e-15,
            )
            checkpoint_path = folder / "checkpoint-post-gate.json"
            archived_hash = next(
                c["sha256"]
                for c in report["checkpoints"]
                if c["file"] == checkpoint_path.name
            )
            assert sha(checkpoint_path) == archived_hash
            checkpoint = read(checkpoint_path)
            assert (
                hashlib.sha256(checkpoint["brain"].encode()).hexdigest()
                == checkpoint["brain_sha256"]
            )
            brain = Brain.from_snapshot(checkpoint["brain"])
            before = brain.snapshot()
            rows, query_work = [], Counter()
            for record in tape["gate"]:
                previous, executed = record["inputs"]["previous"]
                present = record["inputs"]["present"][0]
                identifiable_gain = (present - 0.8 * previous) / executed
                assert abs(identifiable_gain - record["audit"]["future_gain"]) < 1e-14
                predictions = []
                for candidate in (-0.5, 0.5):
                    result = brain.settle(
                        {
                            "previous": [previous, executed],
                            "present": [present, candidate],
                        },
                        targets={"past": [present, present - previous]},
                    )
                    assert result["qualified"]
                    assert result["stationarity"] <= brain.config["tolerance"]
                    assert brain.snapshot() == before
                    predictions.append(result["outputs"]["future"][0])
                    query_work.update(result["work"])
                slope = predictions[1] - predictions[0]
                rows.append(
                    {
                        "gate_index": record["index"],
                        "predictions": predictions,
                        "action_secant": slope,
                        "identifiable_gain": identifiable_gain,
                        "correct_response_sign": slope * identifiable_gain > 0,
                    }
                )
            test = [
                c for c in calls if c["phase"] == "test" and c["kind"] == "forecast"
            ]
            probes = [c for c in calls if c["phase"] == "probe"]
            cases.append(
                {
                    "seed": seed,
                    "arm": arm,
                    "report_sha256": sha(folder / "report.json"),
                    "protocol_sha256": sha(case / "protocol.json"),
                    "tape_sha256": sha(case / "tape.json"),
                    "checkpoint_sha256": sha(checkpoint_path),
                    "snapshot_pure": True,
                    "calls": len(calls),
                    "admissions": len(taught),
                    "gate_passed": report["gate"]["passed"],
                    "gate_mae": report["gate"]["position_mae"],
                    "gate_by_gain": {
                        str(g): statistics.mean(
                            c["position_error"]
                            for c in gate
                            if tape["gate"][c["index"]]["audit"]["future_gain"] == g
                        )
                        for g in (-0.3, 0.3)
                    },
                    "test_mae": statistics.mean(c["position_error"] for c in test),
                    "probe_mae": statistics.mean(c["position_error"] for c in probes),
                    "recovered": sum(
                        r["recovered"] is not None for r in report["recovery"]
                    ),
                    "query_count": 32,
                    "query_work": dict(query_work),
                    "sensitivity": rows,
                }
            )
    summaries = {}
    for arm in ("ordinary", "observer"):
        selected = [case for case in cases if case["arm"] == arm]
        slopes = [
            row["action_secant"] for case in selected for row in case["sensitivity"]
        ]
        summaries[arm] = {
            "gate_passes": sum(c["gate_passed"] for c in selected),
            "gate_mae_mean": statistics.mean(c["gate_mae"] for c in selected),
            "gate_mae_range": [
                min(c["gate_mae"] for c in selected),
                max(c["gate_mae"] for c in selected),
            ],
            "test_mae_mean": statistics.mean(c["test_mae"] for c in selected),
            "probe_mae_mean": statistics.mean(c["probe_mae"] for c in selected),
            "recovered": sum(c["recovered"] for c in selected),
            "negative_action_secants": sum(value < 0 for value in slopes),
            "total_action_secants": len(slopes),
            "action_secant_range": [min(slopes), max(slopes)],
            "correct_response_signs": sum(
                row["correct_response_sign"]
                for case in selected
                for row in case["sensitivity"]
            ),
        }
    return {
        "verified": True,
        "sources": first["sources"],
        "diagnostic_sha256": sha(Path(__file__)),
        "calls": total_calls,
        "admissions": admissions,
        "refusals_errors_censors": 0,
        "recorded_experiment_work": dict(all_work),
        "brains_reloaded": 10,
        "qualified_pure_diagnostic_queries": 320,
        "summary": summaries,
        "cases": cases,
        "interpretation": [
            "All stable acquisition gates failed; no recursive-benefit verdict is eligible",
            "Every trained action-response secant is negative although half the held histories require positive response",
            "This supports an interaction/learning bottleneck; it is not a theorem that the positive-prior architecture cannot represent the task",
            "Future action enters the two output patches directly; lower latent patches see only past inputs",
            "No retraining, new model arm, teacher, or parameter mutation was used by this diagnostic",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = diagnose(args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "verified",
                    "calls",
                    "admissions",
                    "qualified_pure_diagnostic_queries",
                    "summary",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
