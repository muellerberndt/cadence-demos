"""Pure, post hoc diagnosis of all frozen shared-innovation final snapshots.

This issues counterfactual pre-observation queries with fixed final parameters;
it does not reconstruct a historically issued forecast or admit any learning.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import signal
import statistics
import time
import traceback
from collections import defaultdict
from pathlib import Path

from cadence import Brain


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def close(a, b):
    if not math.isclose(a, b, rel_tol=0, abs_tol=2e-14):
        raise AssertionError((a, b))


def alarm(*_):
    raise TimeoutError("60-second diagnostic deadline")


def equation_checks(row):
    u, v = row["inputs"]["u"][0], row["inputs"]["v"][0]
    baseline = math.tanh(math.tanh(u))
    close(row["actual_x"][0] - baseline, row["delta"])
    close(row["actual_y"][0], math.tanh(v + row["delta"]))
    return baseline


def decomposition(row, prior, observed, teacher):
    baseline = equation_checks(row)
    actual = row["actual_x"][0]
    for result in (prior, observed, teacher):
        assert result["qualified"]
        for state, prediction, error in zip(
            result["state"], result["predictions"], result["errors"], strict=True
        ):
            close(state - prediction, error)
    close(observed["state"][1], actual)
    close(teacher["state"][1], actual)
    close(teacher["state"][2], row["actual_y"][0])
    innovation = actual - prior["state"][1]
    posterior_residual = observed["errors"][1]
    posterior_revision = observed["predictions"][1] - prior["state"][1]
    close(innovation, posterior_residual + posterior_revision)
    close(innovation - row["delta"], baseline - prior["state"][1])
    close(row["delta"] - posterior_residual, observed["predictions"][1] - baseline)
    return {
        "physical_baseline": baseline,
        "physical_innovation": row["delta"],
        "counterfactual_prior_p_forecast": prior["state"][1],
        "counterfactual_prior_p_prediction": prior["predictions"][1],
        "prior_baseline_error": prior["state"][1] - baseline,
        "counterfactual_prior_innovation": innovation,
        "posterior_p_residual": posterior_residual,
        "posterior_prediction_minus_prior_forecast": posterior_revision,
        "posterior_prediction_minus_physical_baseline": observed["predictions"][1]
        - baseline,
        "m_state_observation_revision": observed["state"][0] - prior["state"][0],
        "teacher_p_residual": teacher["errors"][1],
        "teacher_p_residual_change": teacher["errors"][1] - posterior_residual,
        "teacher_m_state_change": teacher["state"][0] - observed["state"][0],
        "prior_future_error": prior["state"][2] - row["actual_y"][0],
        "posterior_future_error": observed["state"][2] - row["actual_y"][0],
    }


def summary(rows):
    keys = tuple(rows[0]["measurements"])
    result = {"queries": len(rows)}
    delta = [r["measurements"]["physical_innovation"] for r in rows]
    for key in keys:
        values = [r["measurements"][key] for r in rows]
        result[key] = {
            "mean": statistics.mean(values),
            "mae": statistics.mean(abs(x) for x in values),
            "rms": math.sqrt(statistics.mean(x * x for x in values)),
            "slope_against_delta_through_origin": sum(
                a * b for a, b in zip(values, delta, strict=True)
            )
            / sum(d * d for d in delta),
        }
    return result


def run(root, out):
    started = time.monotonic()
    protocol = json.loads((root / "protocol.json").read_text())
    for path, expected in protocol["sources"].items():
        assert sha(Path(path)) == expected, path
    assert sha(root / "data.json") == protocol["data_sha256"]
    data = json.loads((root / "data.json").read_text())
    execution = json.loads((root / "execution.json").read_text())
    assert len(execution) == 20 and all(x["code"] == 0 for x in execution)
    planned, files = (
        [],
        {
            "protocol.json": sha(root / "protocol.json"),
            "data.json": sha(root / "data.json"),
            "execution.json": sha(root / "execution.json"),
        },
    )
    for condition in protocol["conditions"]:
        for seed in protocol["seeds"]:
            for arm in protocol["arms"]:
                name = f"{condition}-{arm}-seed{seed}"
                folder = root / name
                result = json.loads((folder / "result.json").read_text())
                assert result["status"] == "complete" and result["sources_unchanged"]
                assert (
                    result["accepted_updates"] == 192
                    and result["completed_queries"] == 480
                )
                for filename in (
                    "checkpoint-mixed128.json",
                    "result.json",
                    "evaluations.json",
                    "calls.jsonl",
                    "updates.json",
                ):
                    files[f"{name}/{filename}"] = sha(folder / filename)
                for row in data[condition]["mixed_test"]:
                    equation_checks(row)
                planned.append(
                    {"name": name, "condition": condition, "seed": seed, "arm": arm}
                )
    assert len(planned) == 20
    out.mkdir(parents=True, exist_ok=False)
    frozen = {
        "schema": "shared-innovation-pure-diagnostic-v1",
        "analysis_source_sha256": sha(Path(__file__)),
        "original_root": str(root.resolve()),
        "original_sources": protocol["sources"],
        "files": files,
        "planned": planned,
        "queries_per_snapshot": 64,
        "total_query_deadline_seconds": 60,
        "scope": "Post hoc diagnostic. Same final parameters, raw u/v only, no target clamps, all final snapshots/all held-out mixed rows. No learning or outcome-based subset.",
        "interpretation": "A counterfactual forecast before observing x with final weights is not a historical forecast issued during training. Current posterior P residual differs from that counterfactual innovation whenever P's prediction changes after observation.",
    }
    write(out / "protocol.json", frozen)
    all_rows, status, failure = [], "complete", None
    attempted, returned, unqualified = 0, 0, 0
    previous_signal = signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, 60)
    try:
        for spec in planned:
            folder = root / spec["name"]
            snapshot = (folder / "checkpoint-mixed128.json").read_text()
            model = Brain.from_snapshot(snapshot)
            before = model.snapshot()
            assert before == snapshot
            observations = json.loads((folder / "evaluations.json").read_text())
            observed = {
                r["row"]: r
                for r in observations
                if r["check"] == "mixed128-offset-observed"
            }
            teachers = {
                r["row"]: r
                for r in observations
                if r["check"] == "mixed128-teacher-diagnostic"
            }
            assert len(observed) == len(teachers) == 64
            ledger = [
                json.loads(line)
                for line in (folder / "calls.jsonl").read_text().splitlines()
            ]
            saved = [
                x
                for x in ledger
                if x.get("check")
                in ("mixed128-offset-observed", "mixed128-teacher-diagnostic")
            ]
            assert len(saved) == 128
            assert all(
                x["before_sha256"] == x["after_sha256"] == digest(before) for x in saved
            )
            for row in data[spec["condition"]]["mixed_test"]:
                intent = {**spec, "row": row["id"], "before_sha256": digest(before)}
                write(out / "current-call.json", intent)
                tick = time.monotonic()
                attempted += 1
                prior = model.settle(row["inputs"])
                returned += 1
                unqualified += int(not prior["qualified"])
                write(
                    out / "current-call.json",
                    {
                        **intent,
                        "status": "returned",
                        "qualified": prior["qualified"],
                        "work": prior["work"],
                        "state": prior["state"],
                        "predictions": prior["predictions"],
                        "errors": prior["errors"],
                    },
                )
                assert model.snapshot() == before
                measurements = decomposition(
                    row, prior, observed[row["id"]], teachers[row["id"]]
                )
                record = {
                    **intent,
                    "after_sha256": digest(model.snapshot()),
                    "seconds": time.monotonic() - tick,
                    "qualified": prior["qualified"],
                    "reason": prior["reason"],
                    "stationarity": prior["stationarity"],
                    "work": prior["work"],
                    "state": prior["state"],
                    "predictions": prior["predictions"],
                    "errors": prior["errors"],
                    "measurements": measurements,
                }
                with (out / "calls.jsonl").open("a") as stream:
                    stream.write(json.dumps(record, sort_keys=True) + "\n")
                all_rows.append(record)
                (out / "current-call.json").unlink()
    except Exception:  # noqa: BLE001 - Preserve failed diagnostic evidence.
        status, failure = "error", traceback.format_exc()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_signal)
    grouped = defaultdict(list)
    for row in all_rows:
        grouped[(row["condition"], row["arm"])].append(row)
    unchanged = sha(Path(__file__)) == frozen["analysis_source_sha256"] and all(
        sha(root / path) == expected for path, expected in files.items()
    ) and all(
        sha(Path(path)) == expected for path, expected in protocol["sources"].items()
    )
    receipt = {
        "status": status,
        "failure": failure,
        "seconds": time.monotonic() - started,
        "queries_expected": 1280,
        "queries_completed": len(all_rows),
        "attempted": attempted,
        "returned": returned,
        "unqualified": unqualified,
        "unknown_work_calls": attempted - returned,
        "qualified": sum(r["qualified"] for r in all_rows),
        "sources_and_original_evidence_unchanged": unchanged,
        "protocol_sha256": sha(out / "protocol.json"),
        "ledger_sha256": sha(out / "calls.jsonl") if all_rows else None,
        "groups": [
            {"condition": key[0], "arm": key[1], **summary(rows)}
            for key, rows in sorted(grouped.items())
        ],
        "per_seed": [
            {**spec, **summary([r for r in all_rows if r["name"] == spec["name"]])}
            for spec in planned
            if any(r["name"] == spec["name"] for r in all_rows)
        ],
    }
    write(out / "receipt.json", receipt)
    print(
        json.dumps(
            {
                key: receipt[key]
                for key in (
                    "status",
                    "queries_completed",
                    "qualified",
                    "sources_and_original_evidence_unchanged",
                    "seconds",
                )
            }
        )
    )
    return int(status != "complete" or len(all_rows) != 1280 or not unchanged)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.root, args.out))
