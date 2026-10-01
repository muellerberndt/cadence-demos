"""Verify all fifteen continued parameter trajectories and every returned call.

The failed1024 parent receipt is immutable and explicitly bound. Fresh data and
1536/2048 checks form one bounded continuation, not an independent confirmation.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from collections import Counter
from pathlib import Path

import cycle_write_continuation as frozen
import verify_cycle_write_confirmation as prior

PIN = "eb090868438ac4bf9adb8d169fb2ae0f26a443654c925dd9e723cf21aaeb9dec"
PRIOR_VERIFIER_PIN = "11bde27a2dd885860adda4c106c1f83c0adb3b8a8c3136e97716db7244d9fca8"
PARENT_PROTOCOL_PIN = "f1eaa1a615ab9fcc60f97000b420b6f54388ccd1dee319c41fc662867c207d21"
PARENT_RECEIPT_PIN = "3c71424b0f390a8e3ea9b87b1b3d9683f72e2eb0b06e538b227525d806034450"
SEEDS = (179, 181, 191, 193, 197)
REGIMES = ((0.98, 0.8), (0.999, 0.8), (0.9999, 0.8))
CHECKS = (1536, 2048)
CONFIG = dict(prior.CONFIG)
require, same, read, sha = prior.require, prior.same, prior.read, prior.sha
independent = prior.independent
expected_intent, replay_record = prior.expected_intent, prior.replay_record
checkpoint_metrics, conclusions = prior.checkpoint_metrics, prior.conclusions


def schedule(tape, regime):
    result = []
    for event, rows in enumerate(tape, start=1025):
        result.append(
            {
                "kind": "training",
                "identity": f"batch{event}",
                "checkpoint": None,
                "rows": rows,
            }
        )
        if event in CHECKS:
            for query in prior.query_plan(*REGIMES[regime]):
                result.append(
                    {
                        **query,
                        "checkpoint": event,
                        "short_identity": query["identity"],
                        "identity": f"check{event}:{query['identity']}",
                    }
                )
    return result


def parent_checkpoints(root, protocol):
    folder = root / "parent"
    manifest = protocol["parent"]
    require(manifest["collector_sha256"] == prior.PIN, "parent collector pin")
    names = {"protocol.json", "verification.json"} | {
        f"regime{r}-seed{s}.json" for s in SEEDS for r in range(3)
    }
    require(
        set(manifest["files"]) == names and {p.name for p in folder.iterdir()} == names,
        "all17 parent custody files",
    )
    for name, digest in manifest["files"].items():
        require(sha(folder / name) == digest, "copied parent file pin")
    require(
        sha(folder / "protocol.json") == PARENT_PROTOCOL_PIN
        and sha(folder / "verification.json") == PARENT_RECEIPT_PIN,
        "immutable failed1024 parent identity",
    )
    parent_protocol, receipt = (
        read(folder / "protocol.json"),
        read(folder / "verification.json"),
    )
    same(
        parent_protocol["sources"], frozen.parent.sources(), "unchanged parent sources"
    )
    same(parent_protocol["config"], CONFIG, "unchanged inherited patch law")
    require(
        receipt["valid"] is True
        and receipt["full_training_and_query_replay"] is True
        and receipt["collector_sha256"] == prior.PIN
        and receipt["verifier_sha256"] == PRIOR_VERIFIER_PIN
        and receipt["protocol_sha256"] == PARENT_PROTOCOL_PIN,
        "verified parent receipt",
    )
    require(len(receipt["cases"]) == 15, "parent fifteen-outcome inventory")
    cases = {(c["seed"], c["regime"]): c for c in receipt["cases"]}
    require(
        set(cases) == {(s, r) for s in SEEDS for r in range(3)}, "parent unique cases"
    )
    same(
        receipt["conclusions"],
        [
            {"regime": r, "all_five_complete": True, "all_five_primary_pass": False}
            for r in range(3)
        ],
        "failed parent primaries retained",
    )
    checkpoints = {}
    for (seed, regime), case in cases.items():
        cp = read(folder / f"regime{regime}-seed{seed}.json")
        require(
            case["complete"] is True
            and case["accepted_admissions"] == 1024
            and case["primary_pass"] is False,
            "qualified unselected parent",
        )
        require(
            cp["admissions"] == 1024
            and cp["state"] == [0.0]
            and cp["protocol_sha256"] == PARENT_PROTOCOL_PIN,
            "parent zero live state and admissions",
        )
        require(case["checks"][-1]["checkpoint"] == 1024, "parent terminal checkpoint")
        same(
            cp["parameters"],
            case["checks"][-1]["parameters"],
            "verified learned parent parameters",
        )
        same(
            cp["training_work"],
            case["checks"][-1]["training_work"],
            "inherited training work",
        )
        checkpoints[(seed, regime)] = cp
    return checkpoints


def sources_and_artifacts(root):
    p = read(root / "protocol.json")
    require(
        sha(Path(frozen.__file__)) == PIN
        and p["schema"] == "cycle-write-continuation/1",
        "collector pin/schema",
    )
    require(
        sha(Path(prior.__file__)) == PRIOR_VERIFIER_PIN
        and sha(Path(independent.__file__)) == prior.HELPER_PIN,
        "independent helper pins",
    )
    identities = dict(p["sources"])
    for name, pin in (
        ("cycle_write_continuation.py", PIN),
        ("cycle_write_confirmation.py", prior.PIN),
        ("learned_cycle_memory.py", independent.PIN),
    ):
        found = [key for key in identities if Path(key).name == name]
        require(
            len(found) == 1 and identities.pop(found[0]) == pin,
            "complete producer source inventory",
        )
    independent.common.source_check({"sources": identities})
    same(p["sources"], frozen.sources(), "source inventory")
    same(p["seeds"], SEEDS, "all fifteen same seeds")
    same(p["regimes"], REGIMES, "unchanged regimes")
    same(p["checks"], CHECKS, "fixed secondary and primary checkpoints")
    same(p["config"], CONFIG, "unchanged patch law")
    require(
        p["starting_admissions"] == 1024 and p["primary_checkpoint"] == 2048,
        "continuation bounds",
    )
    require(sha(root / "data.json") == p["data_sha256"], "new body data pin")
    rng, expected = random.Random(20261013), []
    for event in range(1025, 2049):
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
    data = read(root / "data.json")
    same(data, expected, "independently regenerated ordered body witnesses")
    limits = p["limits"]
    require(
        limits["arm_seconds"] == 60
        and limits["serial_start_window_seconds"] == 300
        and limits["planned_arms"] == 15
        and limits["new_training_admissions_per_arm"] == 1024
        and limits["expected_queries_per_arm"] == 1078,
        "fixed work and stopping envelope",
    )
    return p, data, parent_checkpoints(root, p)


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
    require(
        report["parent_checkpoint_sha256"]
        == sha(root / "parent" / f"regime{regime}-seed{seed}.json"),
        "parent checkpoint pin",
    )
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
    accepted = 1024
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
        and accepted == 2048
        and all(checks[n]["status"] == "complete" for n in CHECKS)
        and not unknown
        and not sum(refusals.values())
    )
    require(not complete or len(journal) == 2102, "complete call inventory")
    require(
        report["complete"] is complete
        and report["primary_pass"] is (complete and checks[2048]["bit_memory_gate"]),
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
    require(
        report["new_accepted_admissions"] == accepted - 1024,
        "new versus inherited admissions",
    )
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
        "new_accepted_admissions": accepted - 1024,
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
    protocol, data, parents = sources_and_artifacts(root)
    execution = read(root / "execution.json")
    require(len(execution) == 15, "all15 planned outcomes")
    cases = [
        verify_arm(
            root,
            seed,
            regime,
            data,
            parents[(seed, regime)]["parameters"],
            outcome,
            started + 120,
        )
        for (seed, regime), outcome in zip(
            ((s, r) for s in SEEDS for r in range(3)), execution, strict=True
        )
    ]
    summary = read(root / "summary.json")
    same(summary["outcomes"], execution, "execution census")
    derived = conclusions(cases)
    same(summary["conclusions"], derived, "all-five2048 primary")
    require(
        protocol["sources"] == frozen.sources() and sha(Path(frozen.__file__)) == PIN,
        "source changed during replay",
    )
    return {
        "schema": "cycle-write-continuation-verification/1",
        "valid": True,
        "collector_sha256": PIN,
        "verifier_sha256": sha(Path(__file__)),
        "prior_verifier_sha256": PRIOR_VERIFIER_PIN,
        "independent_scalar_helper_sha256": prior.HELPER_PIN,
        "custody_helper_sha256": sha(Path(independent.common.__file__)),
        "protocol_sha256": sha(root / "protocol.json"),
        "parent_protocol_sha256": PARENT_PROTOCOL_PIN,
        "parent_verification_sha256": PARENT_RECEIPT_PIN,
        "planned_outcomes": 15,
        "full_training_and_query_replay": True,
        "cases": cases,
        "conclusions": derived,
        "new_accepted_admissions": sum(
            c.get("new_accepted_admissions", 0) for c in cases
        ),
        "replayed_training_calls": sum(
            c.get("replayed_training_calls", 0) for c in cases
        ),
        "replayed_query_calls": sum(c.get("replayed_query_calls", 0) for c in cases),
        "elapsed_seconds": time.monotonic() - started,
        "limits": [
            "The immutable failed1024 parent is source/receipt/checkpoint-bound; its training is not repeated in this continuation replay.",
            "Every new returned admission and free query is replayed through the same pinned kernel, with independent scalar derivative, body and native-state custody checks.",
            "This is additional exposure on the same fifteen trajectories, not independent replication or survivor selection.",
            "Only2048 is primary;1536 and failed1024 remain separate. No public API, residual-observer advantage, temporal credit, planning or matched superiority claim.",
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
                k: result[k]
                for k in (
                    "valid",
                    "planned_outcomes",
                    "new_accepted_admissions",
                    "replayed_training_calls",
                    "replayed_query_calls",
                    "conclusions",
                    "elapsed_seconds",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
