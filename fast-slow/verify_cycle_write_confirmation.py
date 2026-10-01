"""Replay the frozen cycle-only follow-up; numerical and task gates stay separate.

Every returned admission/query is replayed from independently reconstructed
inputs, private teacher rows, parameters and native-state forks. This uses the
same pinned solver, supplemented by independent scalar derivatives and custody.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from collections import Counter
from pathlib import Path

import cycle_write_confirmation as frozen
import verify_learned_cycle_memory as independent

PIN = "1c1c9de1bfed1265173c6d17baf1abb6f2ba89ce0dacd6c3e089b1d93e729506"
HELPER_PIN = "950bc676e146632673761ef1c37e753045140795827ba23ce6d0a980aebeaeb5"
SEEDS = (179, 181, 191, 193, 197)
REGIMES = ((0.98, 0.8), (0.999, 0.8), (0.9999, 0.8))
CHECKS = (64, 256, 1024)
CONFIG = {**independent.CONFIG, "tolerance": 1e-6}
require, same, read, sha = (
    independent.require,
    independent.same,
    independent.read,
    independent.sha,
)


def query_plan(write, hold):
    result = []

    def add(identity, cue, bit, expected, reset=None, scored=True):
        result.append(
            {
                "kind": "query",
                "identity": identity,
                "cue": cue,
                "bit": bit,
                "target": expected,
                "reset": reset,
                "scored": scored,
            }
        )

    add("cold-neutral", 0, 0, 0, "zero")
    for sign in (-1, 1):
        add(f"write:{sign}", sign, sign, sign * write, "zero")
        for delay in (1, 8, 128):
            for tick in range(1, delay + 1):
                add(
                    f"hold:{sign}:{delay}:{tick}",
                    0,
                    sign,
                    sign * hold,
                    f"write:{sign}" if tick == 1 else None,
                )
        add(f"overwrite:{sign}", -sign, -sign, -sign * write)
        for tick in range(1, 129):
            add(f"overwritten-hold:{sign}:{tick}", 0, -sign, -sign * hold)
        add(
            f"erased-state-history-retained:{sign}",
            0,
            -sign,
            -sign * hold,
            "zero",
            False,
        )
        add(f"full-reset-neutral:{sign}", 0, 0, 0, "zero")
    return result


def schedule(tape, regime):
    result = []
    for event, rows in enumerate(tape, start=1):
        result.append(
            {
                "kind": "training",
                "identity": f"batch{event}",
                "checkpoint": None,
                "rows": rows,
            }
        )
        if event in CHECKS:
            for query in query_plan(*REGIMES[regime]):
                result.append(
                    {
                        **query,
                        "checkpoint": event,
                        "short_identity": query["identity"],
                        "identity": f"check{event}:{query['identity']}",
                    }
                )
    return result


def cue_bound(gain, bias=0.0, maximum_wrong_state=1.0):
    return (
        gain * maximum_wrong_state + math.acosh(math.sqrt(gain)) + abs(bias)
        if gain > 1
        else None
    )


def sources_and_artifacts(root):
    p = read(root / "protocol.json")
    require(sha(Path(frozen.__file__)) == PIN, "collector source pin")
    require(sha(Path(independent.__file__)) == HELPER_PIN, "independent helper pin")
    require(p["schema"] == "cycle-write-confirmation/1", "schema")
    identities = dict(p["sources"])
    for name, pin in (
        ("cycle_write_confirmation.py", PIN),
        ("learned_cycle_memory.py", independent.PIN),
    ):
        found = [key for key in identities if Path(key).name == name]
        require(len(found) == 1 and identities.pop(found[0]) == pin, "source inventory")
    independent.common.source_check({"sources": identities})
    same(p["sources"], frozen.sources(), "complete source inventory")
    same(p["seeds"], SEEDS, "fresh seed inventory")
    same(p["regimes"], REGIMES, "predeclared regimes")
    same(p["checks"], CHECKS, "all checkpoints")
    same(p["config"], CONFIG, "frozen numerical law")
    require(p["primary_checkpoint"] == 1024, "primary checkpoint")
    for file, field in (("data", "data_sha256"), ("founders", "founders_sha256")):
        require(sha(root / f"{file}.json") == p[field], f"{file} pin")
    data, founders = read(root / "data.json"), read(root / "founders.json")
    rng, expected = random.Random(20261011), []
    for event in range(1024):
        signs = [-1, 1] * 4
        rng.shuffle(signs)
        expected.append(
            [
                {
                    "episode": f"{event}:{i}",
                    "tick": tick,
                    "cue": sign if tick == 0 else 0,
                    "body_bit": sign,
                }
                for i, sign in enumerate(signs)
                for tick in (0, 1)
            ]
        )
    same(data, expected, "independent balanced causal body tape")
    require(set(founders) == {str(s) for s in SEEDS}, "founder census")
    for seed in SEEDS:
        rng = random.Random(seed)
        same(
            founders[str(seed)],
            [rng.uniform(-0.1, 0.1) for _ in range(3)],
            "paired random acquisition founder",
        )
    expected_limits = [
        {
            "write": w,
            "hold": h,
            "gain": math.atanh(h) / h,
            "cue_weight": math.atanh(w) - w * math.atanh(h) / h,
            "all_state_sufficient_bound": cue_bound(math.atanh(h) / h),
        }
        for w, h in REGIMES
    ]
    same(p["teacher_limits"], expected_limits, "teacher implication algebra")
    require(
        p["limits"]["planned_arms"] == 15
        and p["limits"]["expected_queries_per_arm"] == 1617
        and p["limits"]["arm_seconds"] == 60
        and p["limits"]["serial_start_window_seconds"] == 300,
        "declared resource limits",
    )
    return p, data, founders


def expected_intent(op, theta, state, written, regime):
    learning = op["kind"] == "training"
    if learning:
        values = tuple(
            v
            for row in op["rows"]
            for v in independent.inputs("cycle", row["cue"], row["body_bit"])
        )
        clamps = {
            str(i): row["body_bit"] * REGIMES[regime][row["tick"]]
            for i, row in enumerate(op["rows"])
        }
        initial = (0.0,) * 16
    else:
        reset = op["reset"]
        initial = (0.0 if reset == "zero" else written[reset] if reset else state,)
        values = independent.inputs("cycle", op["cue"], op["bit"])
        clamps = {}
    return {
        "identity": op["identity"],
        "checkpoint": op["checkpoint"],
        "learn": learning,
        "inputs": values,
        "initial_state": initial,
        "parameters_before": theta,
        "clamps": clamps,
    }


def replay_record(record, intent):
    for field, expected in intent.items():
        same(record[field], expected, f"causal intent {field}")
    require(
        record["status"] == "returned"
        and math.isfinite(record["seconds"])
        and record["seconds"] >= 0,
        "returned call receipt",
    )
    theta = intent["parameters_before"]
    result = independent.settle(
        independent.graph("cycle"),
        intent["inputs"],
        intent["initial_state"],
        theta[:2],
        theta[2:],
        learn=intent["learn"],
        clamps={int(k): v for k, v in intent["clamps"].items()},
        _batch_size=16 if intent["learn"] else 1,
        **CONFIG,
    )
    same(
        {k: v for k, v in result.items() if k != "energy_history"},
        record["result"],
        "exact numerical replay",
    )
    require(
        record["energy_history_sha256"] == independent.digest(result["energy_history"])
        and record["energy_history_length"] == len(result["energy_history"]),
        "descent history replay",
    )
    discrepancy = independent.scalar_audit(
        "cycle", intent["inputs"], theta[:2], theta[2:], result, intent["learn"]
    )
    require(
        not result["qualified"] or result["stationarity"] <= 1e-6,
        "qualification threshold",
    )
    return result, discrepancy


def conclusions(cases):
    require(
        len(cases) == 15
        and {(r["seed"], r["regime"]) for r in cases}
        == {(s, r) for s in SEEDS for r in range(3)},
        "all15 planned outcomes",
    )
    return [
        {
            "regime": regime,
            "all_five_complete": all(
                r["complete"] for r in cases if r["regime"] == regime
            ),
            "all_five_primary_pass": all(
                r["primary_pass"] for r in cases if r["regime"] == regime
            ),
        }
        for regime in range(3)
    ]


def checkpoint_metrics(checkpoint, theta, rows, training_work, inference_work):
    scored = [r for r in rows if r["scored"]]
    held = max(
        abs(r["state"])
        for r in rows
        if r["identity"] in ("hold:-1:128:128", "hold:1:128:128")
    )
    return {
        "checkpoint": checkpoint,
        "status": "complete",
        "parameters": theta,
        "queries": len(rows),
        "bit_memory_gate": independent.bit_gate(rows, len(rows) == 539),
        "free_target_mae": sum(r["absolute_error"] for r in scored) / len(scored),
        "minimum_signed_response": min(
            r["state"] * math.copysign(1, r["expected"])
            for r in scored
            if r["expected"]
        ),
        "all_state_sufficient_cue_bound": cue_bound(theta[1], theta[2]),
        "held_interval_sufficient_cue_bound": cue_bound(theta[1], theta[2], held),
        "held_magnitude": held,
        "training_work": dict(training_work),
        "inference_work_so_far": dict(inference_work),
    }


def verify_arm(root, seed, regime, tape, founder, execution, deadline):
    folder = root / f"regime{regime}-seed{seed}"
    require(
        execution["seed"] == seed and execution["regime"] == regime, "execution order"
    )
    if execution["status"] == "not_started_deadline":
        same(
            execution,
            {
                "seed": seed,
                "regime": regime,
                "status": "not_started_deadline",
                "complete": False,
                "primary_pass": False,
            },
            "unstarted outcome",
        )
        require(not folder.exists(), "unstarted arm has results")
        return execution
    report = read(folder / "result.json")
    same(report, execution, "arm/execution custody")
    require(report["status"] in ("complete", "timeout", "error"), "outcome taxonomy")
    require(
        report["protocol_sha256"] == sha(root / "protocol.json"), "arm protocol pin"
    )
    path = folder / "calls.jsonl"
    journal = (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )
    same(
        report["journal"],
        {"bytes": path.stat().st_size, "sha256": sha(path)} if path.exists() else None,
        "journal custody",
    )
    plan = schedule(tape, regime)
    require(len(journal) <= len(plan), "extra calls")
    theta, state, written = tuple(founder), 0.0, {}
    rows_by_check = {n: [] for n in CHECKS}
    checks = {
        n: {
            "checkpoint": n,
            "status": "not_started",
            "queries": 0,
            "bit_memory_gate": False,
        }
        for n in CHECKS
    }
    training_work, inference_work, attempts, refusals = (Counter() for _ in range(4))
    accepted = 0
    max_gap = 0.0
    for index, record in enumerate(journal):
        require(time.monotonic() < deadline, "replay exceeded120 seconds")
        op = plan[index]
        intent = expected_intent(op, theta, state, written, regime)
        result, gap = replay_record(record, intent)
        max_gap = max(max_gap, gap)
        kind = "training" if intent["learn"] else "inference"
        attempts[kind] += 1
        (training_work if intent["learn"] else inference_work).update(result["work"])
        if not result["qualified"]:
            refusals[kind] += 1
            require(index == len(journal) - 1, "continued after refusal")
            continue
        if intent["learn"]:
            theta = (*result["weights"], *result["biases"])
            accepted += 1
            if accepted in CHECKS:
                same(
                    read(folder / f"checkpoint{accepted}.json"),
                    {
                        "parameters": theta,
                        "state": [0.0],
                        "admissions": accepted,
                        "training_work": dict(training_work),
                        "protocol_sha256": sha(root / "protocol.json"),
                    },
                    "acquired checkpoint custody",
                )
                checks[accepted]["status"] = "started"
        else:
            same(
                [*result["weights"], *result["biases"]],
                theta,
                "frozen query parameters",
            )
            state = result["state"][0]
            identity, checkpoint = op["short_identity"], op["checkpoint"]
            if identity.startswith("write:"):
                written[identity] = state
            rows = rows_by_check[checkpoint]
            rows.append(
                {
                    "identity": identity,
                    "cue": op["cue"],
                    "body_bit": op["bit"],
                    "state": state,
                    "expected": op["target"],
                    "scored": op["scored"],
                    "qualified": True,
                    "absolute_error": abs(state - op["target"]),
                }
            )
            checks[checkpoint]["queries"] = len(rows)
            if len(rows) == 539:
                checks[checkpoint] = checkpoint_metrics(
                    checkpoint, theta, rows, training_work, inference_work
                )
    current = read(folder / "current-call.json")
    unknown = False
    if current["status"] == "returned":
        require(bool(journal), "returned intent without journal")
        same(current, journal[-1], "last returned intent")
    else:
        require(len(journal) < len(plan), "pending after complete sequence")
        intent = expected_intent(plan[len(journal)], theta, state, written, regime)
        for field, value in intent.items():
            same(current[field], value, f"pending intent {field}")
        require(
            current["status"] in ("started", "interrupted", "not_started_deadline"),
            "interrupted status",
        )
        unknown = current["status"] in ("started", "interrupted")
        if unknown:
            attempts["training" if intent["learn"] else "inference"] += 1
        if current["status"] == "interrupted":
            require(current["unknown_work"] is True, "interrupted work hidden")
    same(
        read(folder / "last-completed.json"),
        {"parameters": theta, "state": [0.0], "admissions": accepted},
        "final accepted parameters and zero training state",
    )
    for checkpoint in CHECKS:
        path = folder / f"queries{checkpoint}.json"
        if accepted >= checkpoint:
            same(
                read(path),
                rows_by_check[checkpoint],
                "complete/partial evaluation rows",
            )
        else:
            require(
                not path.exists()
                and not (folder / f"checkpoint{checkpoint}.json").exists(),
                "future checkpoint or evaluation",
            )
    expected_checks = [checks[n] for n in CHECKS]
    same(read(folder / "checks.json"), expected_checks, "all checkpoint outcomes")
    same(report["checks"], expected_checks, "checkpoint metric promotion")
    complete = (
        report["status"] == "complete"
        and accepted == 1024
        and all(checks[n]["status"] == "complete" for n in CHECKS)
        and not unknown
        and not sum(refusals.values())
    )
    require(not complete or len(journal) == 2641, "complete call inventory")
    require(
        report["complete"] is complete
        and report["primary_pass"] is (complete and checks[1024]["bit_memory_gate"]),
        "numerical/task completion promotion",
    )
    require(
        report["unknown_work"] is unknown
        and report["accepted_admissions"] == accepted
        and report["returned_calls"] == len(journal),
        "truthful call counts",
    )
    for field, actual in (
        ("training_work", training_work),
        ("inference_work", inference_work),
        ("attempts", attempts),
        ("refusals", refusals),
    ):
        same(report[field], dict(actual), f"truthful {field}")
    require(report["sources_unchanged"] is True, "source drift")
    require(
        math.isfinite(report["seconds"]) and report["seconds"] >= 0, "elapsed seconds"
    )
    require(not complete or report["seconds"] <= 60, "completed beyond arm allowance")
    return {
        "seed": seed,
        "regime": regime,
        "status": report["status"],
        "complete": complete,
        "primary_pass": report["primary_pass"],
        "accepted_admissions": accepted,
        "replayed_training_calls": attempts["training"]
        - int(unknown and current["learn"]),
        "replayed_query_calls": attempts["inference"]
        - int(unknown and not current["learn"]),
        "refusals": dict(refusals),
        "unknown_work": unknown,
        "maximum_independent_derivative_gap": max_gap,
        "training_work": dict(training_work),
        "inference_work": dict(inference_work),
        "checks": expected_checks,
    }


def verify(root):
    started = time.monotonic()
    protocol, data, founders = sources_and_artifacts(root)
    execution = read(root / "execution.json")
    require(len(execution) == 15, "all15 planned execution outcomes")
    cases = [
        verify_arm(
            root, seed, regime, data, founders[str(seed)], outcome, started + 120
        )
        for (seed, regime), outcome in zip(
            ((s, r) for s in SEEDS for r in range(3)), execution, strict=True
        )
    ]
    summary = read(root / "summary.json")
    same(summary["outcomes"], execution, "retained execution census")
    derived = conclusions(cases)
    same(summary["conclusions"], derived, "per-regime all-five primary")
    require(
        protocol["sources"] == frozen.sources() and sha(Path(frozen.__file__)) == PIN,
        "sources changed during replay",
    )
    return {
        "schema": "cycle-write-confirmation-verification/1",
        "valid": True,
        "collector_sha256": PIN,
        "verifier_sha256": sha(Path(__file__)),
        "independent_helper_sha256": HELPER_PIN,
        "custody_helper_sha256": sha(Path(independent.common.__file__)),
        "protocol_sha256": sha(root / "protocol.json"),
        "planned_outcomes": 15,
        "full_training_and_query_replay": True,
        "cases": cases,
        "conclusions": derived,
        "replayed_training_calls": sum(
            c.get("replayed_training_calls", 0) for c in cases
        ),
        "replayed_query_calls": sum(c.get("replayed_query_calls", 0) for c in cases),
        "accepted_admissions": sum(c.get("accepted_admissions", 0) for c in cases),
        "elapsed_seconds": time.monotonic() - started,
        "limits": [
            "Same pinned solver is numerically replayed; independent scalar derivatives, body, reset schedule and gates supplement it.",
            "Private recurrent topology; no public API change, residual-observer advantage or matched-baseline superiority.",
            "Historical controls and stricter-tolerance refusals remain separate; this is a new supervised attractor-acquisition experiment.",
            "All checkpoint outcomes remain visible; only1024 gates enter each predeclared regime's all-five primary.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.root.resolve())
    with args.out.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "valid",
                    "planned_outcomes",
                    "replayed_training_calls",
                    "replayed_query_calls",
                    "accepted_admissions",
                    "conclusions",
                    "elapsed_seconds",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
