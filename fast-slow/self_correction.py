"""Matched small-body forecasting with ordinary or residual-reading patches.

This is a prediction/recovery experiment on a common recorded action tape,
not an autonomous controller. All learning uses actual transition witnesses.
The known past is clamped during a query; its future head always stays free.

Set PYTHONPATH to the candidate Cadence src directory, then run:
    python self_correction.py --seed 2 --out /new/run/seed2 --freeze-only
    python self_correction.py --seed 2 --out /new/run/seed2

The first command freezes sources, data, schedule, founders and protocol.
The second verifies that freeze before running. Omitting --freeze-only on a
new directory freezes it before any comparison. Each arm has 120 seconds;
the outer process allows 360 seconds. Timed-out solves are not admitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import signal
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

import cadence
from cadence import Brain, Cortex

SEEDS = (2, 7, 11, 19, 29)
ARMS = ("ordinary", "observer")
SWITCHES = (23, 51, 82, 109)
HORIZONS = (1, 2, 4, 8)
ARM_SECONDS = 120
PROCESS_SECONDS = 360
THRESHOLD = 0.03
POST_OUTCOME_PROBES = True


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded(value) + "\n")
    temporary.replace(path)


def read(path):
    return json.loads(path.read_text())


def source_identity():
    package = Path(cadence.__file__).resolve().parent
    paths = {str(path): sha(path) for path in sorted(package.rglob("*.py"))}
    paths[str(Path(__file__).resolve())] = sha(Path(__file__))
    return paths


def action(rng, sign=None):
    if sign is None:
        sign = rng.choice((-1, 1))
    return sign * rng.uniform(0.25, 0.5)


def row(phase, index, previous, executed, present, candidate, past_gain, gain):
    following = 0.8 * present + gain * candidate
    inferred_gain = (present - 0.8 * previous) / executed
    causal_forecast = 0.8 * present + inferred_gain * candidate
    return {
        "id": f"{phase}:{index}",
        "index": index,
        "phase": phase,
        "inputs": {"previous": [previous, executed], "present": [present, candidate]},
        "past": [present, present - previous],
        "future": [following, following - present],
        "audit": {
            "past_gain": past_gain,
            "future_gain": gain,
            "switch": gain != past_gain,
            "causal_forecast": causal_forecast,
            "causal_absolute_error": abs(causal_forecast - following),
        },
    }


def trajectory(phase, count, switches, *, seed):
    rng = random.Random(seed)
    previous, executed, gain = rng.uniform(-0.5, 0.5), action(rng), 0.3
    present = 0.8 * previous + gain * executed
    rows = []
    for index in range(count):
        past_gain = gain
        if index in switches:
            gain = -gain
        candidate = action(rng)
        record = row(
            phase, index, previous, executed, present, candidate, past_gain, gain
        )
        rows.append(record)
        previous, executed, present = present, candidate, record["future"][0]
    return rows


def make_tape():
    # Tape seeds are independent of initialization, and shared across all cases.
    rng = random.Random(20261003)
    gate = []
    for gain in (-0.3, 0.3):
        for previous_sign in (-1, 1):
            for candidate_sign in (-1, 1):
                for _ in range(2):
                    previous = rng.uniform(-0.5, 0.5)
                    executed = action(rng, previous_sign)
                    present = 0.8 * previous + gain * executed
                    gate.append(
                        row(
                            "gate",
                            len(gate),
                            previous,
                            executed,
                            present,
                            action(rng, candidate_sign),
                            gain,
                            gain,
                        )
                    )
    return {
        "train": trajectory("train", 512, tuple(range(16, 512, 16)), seed=20261001),
        "gate": gate,
        "test": trajectory("test", 128, SWITCHES, seed=20261002),
    }


def known_query(record):
    """Do not pass future, gain or audit fields through the brain boundary."""
    return record["inputs"], {"past": record["past"]}


def witness(record):
    return record["inputs"], {"past": record["past"], "future": record["future"]}


def make_brain(seed, arm):
    if arm not in ARMS:
        raise ValueError("Unknown arm")
    cortex = Cortex(
        seed=seed,
        device="python",
        dtype="float64",
        settle_budget=2048,
        tolerance=1e-6,
        state_prior=0.01,
        parameter_prior=0.1,
    )
    previous = cortex.input("previous", shape=2)
    present = cortex.input("present", shape=2)
    memory = cortex.column("context", patches=2, inputs=previous)
    past = cortex.column("past_model", patches=2, inputs=(previous, memory))
    if arm == "ordinary":
        head = cortex.column(
            "future_model", patches=2, inputs=(previous, present, past, memory)
        )
    else:
        head = cortex.observer(
            "future_model", patches=2, inputs=(previous, present, past), observes=past
        )
    cortex.output("past", shape=2, reads=past)
    cortex.output("future", shape=2, reads=head)
    brain = cortex.build()
    assert brain.graph.n_inputs == 4 and brain.graph.n_patches == 6
    assert len(brain.weights) == 28 and len(brain.biases) == 6
    return brain


def matched_founders(ordinary, observer):
    left = dict(zip(ordinary.graph.edges, ordinary.weights, strict=True))
    right = dict(zip(observer.graph.edges, observer.weights, strict=True))
    shared = left.keys() & right.keys()
    assert len(shared) == 24
    assert all(left[key] == right[key] for key in shared)
    assert ordinary.biases == observer.biases and ordinary.state == observer.state
    replaced = []
    for source in range(2):
        for target in (4, 5):
            old, new = ("state", source, target), ("residual", source + 2, target)
            assert left[old] == right[new]
            replaced.append(
                {"ordinary": old, "observer": new, "coefficient": left[old]}
            )
    return {
        "shared_edges": len(shared),
        "shared_coefficients_exact": True,
        "replacement_coefficients_exact": True,
        "replacements": replaced,
        "weights_sha256": digest(encoded(ordinary.weights)),
        "biases_sha256": digest(encoded(ordinary.biases)),
    }


def schedule():
    return {
        "train": [list(range(i, i + 16)) for i in range(0, 512, 16)],
        "gate": list(range(16)),
        "test": list(range(128)),
    }


def coverage(tape):
    result = {}
    for phase, rows in tape.items():
        counts = Counter(
            f"{r['audit']['future_gain']}:{math.copysign(1, r['inputs']['previous'][1]):g}:"
            f"{math.copysign(1, r['inputs']['present'][1]):g}"
            for r in rows
            if not r["audit"]["switch"]
        )
        result[phase] = {
            "stable_sign_cells": dict(sorted(counts.items())),
            "switch_rows": [r["index"] for r in rows if r["audit"]["switch"]],
        }
    return result


def freeze(out, seed):
    if seed not in SEEDS:
        raise ValueError("Seed outside the frozen five-case campaign")
    out.mkdir(parents=True, exist_ok=True)
    if (out / "protocol.json").exists():
        protocol = read(out / "protocol.json")
        if protocol["seed"] != seed or protocol["sources"] != source_identity():
            raise ValueError("Frozen seed or source identity differs")
        if (
            protocol["tape_sha256"] != sha(out / "tape.json")
            or read(out / "tape.json") != make_tape()
        ):
            raise ValueError("Frozen tape differs")
        if (
            protocol["schedule_sha256"] != sha(out / "schedule.json")
            or read(out / "schedule.json") != schedule()
        ):
            raise ValueError("Frozen schedule differs")
        for arm, expected in protocol["founders"].items():
            if sha(out / f"founder-{arm}.json") != expected:
                raise ValueError("Frozen founder differs")
        return protocol
    if any(out.iterdir()):
        raise ValueError("New freeze needs an empty output directory")
    tape = make_tape()
    brains = {arm: make_brain(seed, arm) for arm in ARMS}
    match = matched_founders(brains["ordinary"], brains["observer"])
    atomic(out / "tape.json", tape)
    atomic(out / "schedule.json", schedule())
    for arm, brain in brains.items():
        (out / f"founder-{arm}.json").write_text(brain.snapshot())
    protocol = {
        "schema": "cadence-self-correction/1",
        "seed": seed,
        "campaign_seeds": SEEDS,
        "arm_order": ARMS if SEEDS.index(seed) % 2 == 0 else tuple(reversed(ARMS)),
        "sources": source_identity(),
        "python": sys.version,
        "platform": platform.platform(),
        "tape_sha256": sha(out / "tape.json"),
        "schedule_sha256": sha(out / "schedule.json"),
        "founders": {arm: sha(out / f"founder-{arm}.json") for arm in ARMS},
        "founder_match": match,
        "coverage": coverage(tape),
        "config": dict(brains["ordinary"].config),
        "graphs": {arm: brain.graph.edges for arm, brain in brains.items()},
        "arm_seconds": ARM_SECONDS,
        "process_seconds": PROCESS_SECONDS,
        "gate": {
            "rows": 16,
            "position_mae_max": THRESHOLD,
            "requires_all_qualified": True,
            "learning": False,
            "strata": "both gains x previous action sign x next action sign x 2 draws",
        },
        "training": {
            "rows": 512,
            "batches": 32,
            "batch_size": 16,
            "forecast_every_row_before_its_batch_admission": True,
        },
        "test": {
            "rows": 128,
            "switches": SWITCHES,
            "horizons": HORIZONS,
            "forecast_before_each_admission": True,
            "post_outcome_before_admission_probes": POST_OUTCOME_PROBES,
        },
        "source": "witness",
        "primary_output": "future position",
        "recovery": "Rows s+1..s+h after switch row s is observed; first flip error reported separately",
        "recovered": "Three consecutive qualified position errors <= 0.03 before next switch",
        "work": "All calls including gate/probes; exact returned counters and solver call seconds; censors retain unknown interrupted work",
        "timeout": "120s since brain construction ends, including I/O; solve interrupted at remaining deadline; pre-call brain restored; checks between I/O; outer subprocess killed at360s",
        "interpretation": [
            "Forecasting on prerecorded actions, not a learned autonomous controller",
            "Both arms receive identical raw history and known past clamps; future stays free",
            "Same patch rule, state/parameter count and matched initial shared coefficients",
            "Matched-size wiring contrast; ordinary M-state shortcut versus P-error readback",
            "Ordinary columns already backreact through the coupled energy",
            "Past residual is retrospective transition mismatch, not a previously issued forecast",
            "Prequential recovery combines inference and admitted parameter adaptation",
            "Four identical post-outcome probes precede the changed transition admission, isolating immediate inference",
            "First unannounced reversal is unpredictable; later causal oracle uses only observed history",
            "Acquisition failure, refusal or censoring is inconclusive, not exclusive recursive incapacity",
            "Equal solver ceilings are not equal actual compute; report actual work",
        ],
    }
    atomic(out / "protocol.json", protocol)
    return read(out / "protocol.json")


class ArmTimeout(TimeoutError):
    pass


def limited_call(operation, remaining):
    if remaining <= 0:
        raise ArmTimeout("arm wall-time cap")

    def expired(signum, frame):
        raise ArmTimeout("arm wall-time cap during solve")

    prior = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    try:
        return operation()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior)


def work_summary(calls):
    work = Counter()
    for call in calls:
        work.update(call.get("result", {}).get("work", {}))
    return {
        "calls": len(calls),
        "work": dict(work),
        "solver_seconds": sum(c.get("seconds", 0) for c in calls),
        "interrupted_calls": sum(c["status"] == "interrupted" for c in calls),
        "errored_calls": sum(c["status"] == "error" for c in calls),
        "unknown_work_calls": sum(c.get("unknown_solver_work", False) for c in calls),
        "refusals": sum(c.get("result", {}).get("qualified") is False for c in calls),
        "admissions": sum(c.get("result", {}).get("accepted") is True for c in calls),
    }


def mean_error(calls):
    usable = [c for c in calls if c.get("position_error") is not None]
    return {
        "planned_or_observed": len(calls),
        "qualified": len(usable),
        "position_mae": (
            sum(c["position_error"] for c in usable) / len(usable) if usable else None
        ),
        "complete": bool(calls) and len(usable) == len(calls),
    }


def recovery_metrics(calls):
    forecasts = {
        c["index"]: c for c in calls if c["phase"] == "test" and c["kind"] == "forecast"
    }
    records = []
    for pos, switch in enumerate(SWITCHES):
        stop = SWITCHES[pos + 1] if pos + 1 < len(SWITCHES) else 128
        windows = {}
        for horizon in HORIZONS:
            indices = list(range(switch + 1, switch + horizon + 1))
            available = [forecasts[i] for i in indices if i in forecasts]
            values = mean_error(available)
            values.update(
                indices=indices,
                expected=horizon,
                complete=values["complete"] and len(available) == horizon,
            )
            windows[str(horizon)] = values
        recovered = None
        for first in range(switch + 1, stop - 2):
            triple = [forecasts.get(i) for i in range(first, first + 3)]
            if all(
                c is not None
                and c.get("position_error") is not None
                and c["position_error"] <= THRESHOLD
                for c in triple
            ):
                end = triple[-1]["ordinal"]
                beginning = forecasts[switch]["ordinal"]
                consumed = [c for c in calls if beginning < c["ordinal"] <= end]
                recovered = {
                    "first_index": first,
                    "confirmed_at": first + 2,
                    "forecasts_since_first_informed": first + 2 - switch,
                    "work_scope": "post-surprise observation, excluding first surprise forecast",
                    **work_summary(consumed),
                    "including_first_forecast": work_summary(
                        [forecasts[switch], *consumed]
                    ),
                }
                break
        first_miss = forecasts.get(switch)
        records.append(
            {
                "switch": switch,
                "first_informed_forecast": switch + 1,
                "unavoidable_first_error": None
                if first_miss is None
                else {
                    "position_error": first_miss.get("position_error"),
                    "qualified": first_miss.get("result", {}).get("qualified"),
                    "causal_oracle_error": first_miss.get("causal_oracle_error"),
                },
                "windows": windows,
                "recovered": recovered,
            }
        )
    return records


def run_arm(out, arm, protocol, tape, rows):
    folder = out / arm
    folder.mkdir(exist_ok=False)
    brain = Brain.from_snapshot((out / f"founder-{arm}.json").read_text())
    started = time.perf_counter()
    deadline = started + ARM_SECONDS
    calls, checkpoints = [], []
    status, failure, current = "running", None, None
    log_path = folder / "calls.jsonl"

    def save_checkpoint(label, ordinal):
        checkpoint = {
            "brain": brain.snapshot(),
            "ordinal": ordinal,
            "label": label,
            "admissions": brain.inspect()["admissions"],
        }
        checkpoint["brain_sha256"] = digest(checkpoint["brain"])
        atomic(folder / "latest.json", checkpoint)
        if label != "latest":
            path = folder / f"checkpoint-{label}.json"
            atomic(path, checkpoint)
            checkpoints.append(
                {"file": path.name, "sha256": sha(path), "ordinal": ordinal}
            )

    def perform(kind, phase, index, indices):
        nonlocal brain, current
        if time.perf_counter() >= deadline:
            raise ArmTimeout("arm cap before next call")
        current = {
            "ordinal": len(calls),
            "kind": kind,
            "phase": phase,
            "index": index,
            "indices": indices,
            "row_ids": [
                tape[phase if phase != "probe" else "test"][i]["id"] for i in indices
            ],
        }
        before = brain.snapshot()
        current["before_brain_sha256"] = digest(before)
        atomic(folder / "inflight.json", current)
        if kind == "forecast":
            record = tape[phase if phase != "probe" else "test"][index]
            inputs, targets = known_query(record)

            def operation():
                return brain.settle(inputs, targets=targets)

        elif phase == "train":

            def operation():
                return brain.observe_batch(
                    [witness(tape[phase][i]) for i in indices], source="witness"
                )

        else:

            def operation():
                return brain.observe(*witness(tape[phase][index]), source="witness")

        tick = time.perf_counter()
        try:
            result = limited_call(operation, deadline - tick)
        except Exception as error:
            # Public admission may have been interrupted between assignments;
            # never retain a partially completed call or infer its work count.
            brain = Brain.from_snapshot(before)
            current.update(
                status="interrupted" if isinstance(error, ArmTimeout) else "error",
                failure=f"{type(error).__name__}: {error}",
                seconds=time.perf_counter() - tick,
                after_brain_sha256=digest(brain.snapshot()),
                unknown_solver_work=True,
            )
            calls.append(current)
            log.write(encoded(current) + "\n")
            log.flush()
            (folder / "inflight.json").unlink()
            raise
        seconds = time.perf_counter() - tick
        after = brain.snapshot()
        assert result["qualified"] == (
            result["stationarity"] <= brain.config["tolerance"]
        )
        if kind == "forecast" or not result["qualified"]:
            assert before == after
        if kind == "admission":
            assert (
                result["source"] == "witness"
                and result["accepted"] == result["qualified"]
            )
        fields = (
            "qualified",
            "reason",
            "stationarity",
            "prediction_residual",
            "energy",
            "sweeps",
            "work",
            "outputs",
            "predictions",
            "errors",
            "state",
            "states",
            "accepted",
            "source",
            "event_id",
            "batch_size",
        )
        current.update(
            status="returned",
            seconds=seconds,
            result={k: result[k] for k in fields if k in result},
            after_brain_sha256=digest(after),
        )
        if kind == "forecast":
            errors = [
                abs(p - y)
                for p, y in zip(
                    result["outputs"]["future"], record["future"], strict=True
                )
            ]
            current.update(
                position_error=errors[0] if result["qualified"] else None,
                displacement_error=errors[1] if result["qualified"] else None,
                causal_oracle_error=record["audit"]["causal_absolute_error"],
                retrospective_error=list(result["errors"][2:4]),
            )
        calls.append(current)
        log.write(encoded(current) + "\n")
        log.flush()
        if kind == "admission" and result["accepted"]:
            label = "latest"
            if phase == "train" and index + 1 in (8, 16, 32):
                label = f"train-{index + 1}"
            if phase == "test" and index + 1 in (23, 24, 51, 52, 82, 83, 109, 110, 128):
                label = f"test-{index + 1}"
            save_checkpoint(label, current["ordinal"])
        (folder / "inflight.json").unlink()
        return current

    with log_path.open("x") as log:
        try:
            save_checkpoint("initial", -1)
            for batch, indices in enumerate(rows["train"]):
                for index in indices:
                    perform("forecast", "train", index, [index])
                perform("admission", "train", batch, indices)
            for index in rows["gate"]:
                perform("forecast", "gate", index, [index])
            save_checkpoint("post-gate", len(calls) - 1)
            for index in rows["test"]:
                perform("forecast", "test", index, [index])
                if POST_OUTCOME_PROBES and index in SWITCHES:
                    perform("forecast", "probe", index + 1, [index + 1])
                perform("admission", "test", index, [index])
            if time.perf_counter() > deadline:
                raise ArmTimeout("arm cap after final call bookkeeping")
            status = "complete"
        except ArmTimeout as error:
            status, failure = "censored", str(error)
        except Exception as error:
            status, failure = "error", f"{type(error).__name__}: {error}"
            (folder / "error.txt").write_text(traceback.format_exc())
        finally:
            elapsed = time.perf_counter() - started
            # latest.json already records the last accepted learning state.
            # Never replace it with an interrupted or exceptional call's state.
            gate_calls = [c for c in calls if c["phase"] == "gate"]
            gate = mean_error(gate_calls)
            gate["passed"] = (
                len(gate_calls) == 16
                and gate["complete"]
                and gate["position_mae"] <= THRESHOLD
            )
            recovery_indices = {i for s in SWITCHES for i in range(s + 1, s + 9)}
            groups = {
                "all": calls,
                "training": [c for c in calls if c["phase"] == "train"],
                "gate": gate_calls,
                "test_unavoidable": [
                    c for c in calls if c["phase"] == "test" and c["index"] in SWITCHES
                ],
                "test_recovery_first8": [
                    c
                    for c in calls
                    if c["phase"] == "test" and c["index"] in recovery_indices
                ],
                "test_stable_or_late": [
                    c
                    for c in calls
                    if c["phase"] == "test"
                    and c["index"] not in recovery_indices
                    and c["index"] not in SWITCHES
                ],
                "before_admission_probes": [c for c in calls if c["phase"] == "probe"],
            }
            report = {
                "arm": arm,
                "seed": protocol["seed"],
                "status": status,
                "failure": failure,
                "elapsed_seconds": elapsed,
                "protocol_sha256": sha(out / "protocol.json"),
                "tape_sha256": sha(out / "tape.json"),
                "ledger_sha256": sha(log_path),
                "sources_unchanged": source_identity() == protocol["sources"],
                "gate": gate,
                "recovery": recovery_metrics(calls),
                "groups": {
                    name: work_summary(selected) for name, selected in groups.items()
                },
                "checkpoints": checkpoints,
                "latest_sha256": sha(folder / "latest.json")
                if (folder / "latest.json").exists()
                else None,
            }
            atomic(folder / "report.json", report)
    return report


def run_case(out, seed):
    protocol = freeze(out, seed)
    if any((out / arm).exists() for arm in ARMS):
        raise ValueError("Existing arm evidence must not be overwritten or retried")
    tape, rows = read(out / "tape.json"), read(out / "schedule.json")
    reports = [run_arm(out, arm, protocol, tape, rows) for arm in protocol["arm_order"]]
    complete = all(report["status"] == "complete" for report in reports)
    acquisition = all(report["gate"]["passed"] for report in reports)
    qualified = all(report["groups"]["all"]["refusals"] == 0 for report in reports)
    sources = source_identity() == protocol["sources"]
    verdict = (
        "comparison_eligible"
        if complete and acquisition and qualified and sources
        else "inconclusive"
    )
    report = {
        "seed": seed,
        "status": "complete" if complete else "incomplete",
        "verdict": verdict,
        "sources_unchanged": sources,
        "protocol_sha256": sha(out / "protocol.json"),
        "arms": reports,
        "interpretation": "Matched-size prediction recovery only; no exclusive learnability or autonomous-control claim",
    }
    atomic(out / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, choices=SEEDS, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--case-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.out = args.out.resolve()
    if args.freeze_only:
        freeze(args.out, args.seed)
        print(
            encoded(
                {"frozen": True, "protocol_sha256": sha(args.out / "protocol.json")}
            )
        )
        return 0
    if args.case_worker:
        report = run_case(args.out, args.seed)
        print(
            encoded(
                {
                    "seed": args.seed,
                    "status": report["status"],
                    "verdict": report["verdict"],
                }
            )
        )
        return 0 if report["status"] == "complete" else 2
    freeze(args.out, args.seed)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--seed",
        str(args.seed),
        "--out",
        str(args.out),
        "--case-worker",
    ]
    with (args.out / "process.log").open("x") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=PROCESS_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            atomic(
                args.out / "process-timeout.json",
                {
                    "status": "censored",
                    "seconds": PROCESS_SECONDS,
                    "reason": "outer process cap",
                    "protocol_sha256": sha(args.out / "protocol.json"),
                },
            )
            return 2
    print(encoded({"seed": args.seed, "exit_code": code, "out": str(args.out)}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
