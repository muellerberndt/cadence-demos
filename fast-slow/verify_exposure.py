"""Verify frozen exposure receipts without repeating every training admission.

Every saved checkpoint, reported decision, calibration value, schedule entry
and work total is checked. TD targets immediately after available checkpoints
are recomputed independently; intermediate target histories are not retrained.
Hashes bind local source/artifact identity, not authenticated external custody.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

SEEDS = (2, 7, 11, 19, 29)
POINTS = (0, 32, 128, 512)
ARMS = ("stratified", "reverse_stage")


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(left, right):
    require(math.isfinite(left) and math.isfinite(right), "Nonfinite value")
    require(
        math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12),
        f"Numerical mismatch: {left} != {right}",
    )


def context(stage, chosen, delay):
    values = [0.0] * (1 + 2 * delay)
    values[0 if stage == 0 else 1 + 2 * (stage - 1) + chosen] = 1.0
    return {"senses": values}


def validate_collection(collection, seed, preferred, delay):
    records, outcomes = collection["records"], collection["outcomes"]
    require(
        len(records) == 24 * (delay + 1) and len(outcomes) == 24,
        "Incorrect original collection size",
    )
    rng = random.Random(seed)
    for episode, outcome in enumerate(outcomes):
        actions = []
        for _ in range(delay + 1):
            rng.random()  # epsilon=1 at every qualified collection decision
            actions.append(rng.choice([0, 1]))
        require(
            outcome["episode"] == episode and outcome["actions"] == actions,
            "Executed collection action/RNG identity differs",
        )
        reward = 1 if actions[0] == preferred else -1
        require(outcome["reward"] == reward, "Wrong actual terminal reward")
        for stage, action in enumerate(actions):
            row = records[episode * (delay + 1) + stage]
            require(
                row["episode"] == episode and row["stage"] == stage,
                "Transition ordering differs",
            )
            require(
                row["action"] == action and row["first_action"] == actions[0],
                "Transition action custody differs",
            )
            require(
                row["context"] == context(stage, actions[0], delay),
                "Observed context differs",
            )
            terminal = stage == delay
            require(
                row["following"]
                == (None if terminal else context(stage + 1, actions[0], delay)),
                "Transition successor differs",
            )
            require(
                row["reward"] == (reward if terminal else 0),
                "Unobserved or mistimed reward",
            )
    return records


def validate_schedules(schedules, records, seed):
    require(set(schedules) == set(ARMS), "Unexpected replay arms")
    left, right = (schedules[name] for name in ARMS)
    require(len(left) == len(right) == 512, "Incorrect replay schedule length")
    require(all(len(batch) == 16 for batch in left + right), "Incorrect batch width")
    require(
        all(
            type(index) is int and 0 <= index < len(records)
            for batch in left + right
            for index in batch
        ),
        "Invalid row ID",
    )
    roots = [
        [
            i
            for i, row in enumerate(records)
            if row["stage"] == 0 and row["action"] == action
        ]
        for action in (0, 1)
    ]
    others = [i for i, row in enumerate(records[:-1]) if row["stage"] != 0]
    require(all(roots), "Missing root-action coverage")
    rng = random.Random(seed + 1000003)
    expected = [
        [
            rng.choice(roots[0]),
            rng.choice(roots[1]),
            *rng.sample(others, 13),
            len(records) - 1,
        ]
        for _ in range(512)
    ]
    require(left == expected, "Stratified source schedule differs")
    for start in range(0, 512, 32):
        original = [i for row in left[start : start + 32] for i in row]
        reversed_rows = [i for row in right[start : start + 32] for i in row]
        require(Counter(original) == Counter(reversed_rows), "Row exposure differs")
        expected = sorted(original, key=lambda i: records[i]["stage"], reverse=True)
        require(reversed_rows == expected, "Reverse-stage order or seeded ties differ")


def founder(Cortex, seed, delay, records):
    layout = Cortex(seed=seed, parameter_prior=0.02, tolerance=1e-5)
    senses = layout.input("senses", shape=1 + 2 * delay)
    values = layout.column(patches=4, inputs=senses)
    for action in (0, 1):
        layout.output(f"q{action}", shape=(), reads=values, indices=(action,))
    brain = layout.build()
    work = Counter()
    for record in records:
        query = brain.settle(record["context"])
        require(query["qualified"], "Unqualified reconstructed collection query")
        result = brain.step(record["context"])
        require(result["accepted"], "Unqualified reconstructed collection action")
        work.update(query["work"])
        work.update(result["work"])
    require(brain.inspect()["admissions"] == 0, "Collection changed parameters")
    return brain, dict(work)


def validate_checkpoint(brain, check, records, delay, preferred):
    before = brain.snapshot()
    result = brain.settle(context(0, 0, delay))
    require(
        result["qualified"] and brain.snapshot() == before,
        "Root query refused or mutated",
    )
    root = check["root"]
    require(root["qualified"] and root["query_pure"], "Stored root query is invalid")
    values = [result["outputs"][f"q{i}"][0] for i in (0, 1)]
    require(root["values"] == values, "Saved root values differ")
    close(root["preferred_margin"], values[preferred] - values[1 - preferred])
    require(
        root["greedy_actions"] == [i for i in (0, 1) if values[i] == max(values)],
        "Root greedy choices differ",
    )
    calibration = check["calibration"]
    require(
        calibration["qualified"] and calibration["query_pure"],
        "Calibration refused or mutated",
    )
    expected_keys = {(r["stage"], r["first_action"], r["action"]) for r in records}
    rows = calibration["rows"]
    keys = [(r["stage"], r["first_action"], r["action"]) for r in rows]
    require(
        len(keys) == len(set(keys)) and set(keys) == expected_keys,
        "Calibration coverage differs",
    )
    gamma = delay / (delay + 1)
    for row in rows:
        require(row["qualified"], "Unqualified calibration value")
        result = brain.settle(context(row["stage"], row["first_action"], delay))
        require(result["qualified"], "Reloaded calibration query refused")
        value = result["outputs"][f"q{row['action']}"][0]
        require(value == row["value"], "Reloaded calibration value differs")
        reward = 1 if row["first_action"] == preferred else -1
        target = (1 - gamma) * 0.9 * reward * gamma ** (delay - row["stage"])
        close(row["observed_return"], target)
        close(row["absolute_error"], abs(value - row["observed_return"]))
    require(brain.snapshot() == before, "Calibration query changed continuation")
    evaluation = check["evaluation"]
    actions = evaluation["actions"]
    require(
        evaluation["status"] == "complete" and len(actions) == delay + 1,
        "Incomplete free episode",
    )
    for stage, action in enumerate(actions):
        require(type(action) is int and action in (0, 1), "Invalid executed action")
        values = brain.settle(context(stage, actions[0], delay))
        require(values["qualified"], "Free query refused")
        q = [values["outputs"][f"q{i}"][0] for i in (0, 1)]
        require(q[action] == max(q), "Executed action is not greedy")
        accepted = brain.step(context(stage, actions[0], delay))
        require(accepted["accepted"], "Free action refused")
    reward = 1 if actions[0] == preferred else -1
    require(evaluation["reward"] == reward, "Free episode outcome differs")
    return dict(
        update=check["update"],
        reward=reward,
        values=root["values"],
        preferred_margin=root["preferred_margin"],
        calibration_cases=len(rows),
        observed_return_mae=sum(r["absolute_error"] for r in rows) / len(rows),
        free_decisions=delay + 1,
    )


def validate_targets(brain, row, records, delay):
    gamma = delay / (delay + 1)
    before = brain.snapshot()
    for index, value in zip(row["indices"], row["targets"], strict=True):
        record = records[index]
        target = (1 - gamma) * 0.9 * record["reward"]
        if record["following"] is not None:
            result = brain.settle(record["following"])
            require(result["qualified"], "TD bootstrap query refused")
            best = max(result["outputs"][f"q{i}"][0] for i in (0, 1))
            target += gamma * max(-0.9, min(0.9, best))
        close(value, target)
    require(brain.snapshot() == before, "TD target query changed continuation")


def verify_case(root, folder, Brain, Cortex):
    report = read(folder / "report.json")
    protocol = read(folder / "protocol.json")
    require(report["protocol"] == protocol, "Protocol files differ")
    require(
        report["status"] in {"complete", "incomplete"} and report["sources_unchanged"],
        "Run errored or sources changed",
    )
    require(
        protocol["schema"] == "credit-exposure/1" and protocol["credit_horizon"] == 1,
        "Unexpected algorithm",
    )
    require(
        protocol["updates"] == 512
        and protocol["batch_size"] == 16
        and protocol["block"] == 32,
        "Unexpected exposure contract",
    )
    require(protocol["checkpoints"] == list(POINTS), "Unexpected checkpoint contract")
    seed, delay, preferred = (protocol[key] for key in ("seed", "delay", "preferred"))
    require(seed in SEEDS and delay == 128 and preferred in (0, 1), "Unexpected case")
    for name, expected in protocol["sources"].items():
        require(sha(root / "code" / name) == expected, f"Source hash differs: {name}")
    collection_path = root / "credit" / folder.name / "collection.json"
    require(
        sha(collection_path) == protocol["collection_sha256"],
        "Original collection hash differs",
    )
    collection = read(collection_path)
    require(
        collection["protocol"] == protocol["source_collection_protocol"],
        "Collection protocol differs",
    )
    require(
        report["collection_verified"] and all(report["source_compatibility"].values()),
        "Collection verification failed",
    )
    for name, expected in collection["protocol"]["sources"].items():
        require(
            protocol["sources"][name] == expected, "Original source identity differs"
        )
    records = validate_collection(collection, seed, preferred, delay)
    require(
        sha(folder / "schedules.json") == report["schedules_sha256"],
        "Schedule hash differs",
    )
    schedules = read(folder / "schedules.json")
    validate_schedules(schedules, records, seed)
    expected_points = {str(point): True for point in range(32, 513, 32)}
    require(
        report["planned_matched_prefixes"] == expected_points,
        "Planned equality receipt differs",
    )
    require(
        report["actual_matched_prefixes"]
        == {
            str(point): all(len(arm["updates"]) >= point for arm in report["arms"])
            for point in POINTS[1:]
        },
        "Actual checkpoint exposure receipt differs",
    )
    initial, reconstruction_work = founder(Cortex, seed, delay, records)
    require(
        reconstruction_work == report["reconstruction_work"],
        "Reconstruction work differs",
    )
    initial_snapshot = initial.snapshot()
    require(
        [arm["name"] for arm in report["arms"]] == list(ARMS), "Reported arms differ"
    )
    arms, total, target_checks = [], Counter(reconstruction_work), 0
    for arm in report["arms"]:
        name = arm["name"]
        count = len(arm["updates"])
        require(
            0 <= count <= 512
            and (
                (arm["status"] == "complete" and count == 512)
                or (
                    arm["status"] in {"arm_time_limit", "case_time_limit"}
                    and count < 512
                )
            ),
            "Unsupported replay failure or invalid censoring",
        )
        if arm["status"] == "arm_time_limit":
            require(
                arm["seconds"] >= protocol["arm_seconds"], "Premature claimed arm cap"
            )
        require(
            [c["update"] for c in arm["checkpoints"]]
            == [point for point in POINTS if point <= count],
            "Missing checkpoints",
        )
        training = Counter()
        for index, row in enumerate(arm["updates"]):
            require(
                row["update"] == index + 1 and row["indices"] == schedules[name][index],
                "Admitted row order differs",
            )
            require(
                row["accepted"] and row["source"] == "estimate",
                "Unaccepted or mislabeled admission",
            )
            require(
                row["horizons"] == [1] * 16 and len(row["targets"]) == 16,
                "Non-one-step target",
            )
            require(
                all(math.isfinite(v) and abs(v) <= 0.9 for v in row["targets"]),
                "Unbounded target",
            )
            require(
                row["stops"]
                == [
                    "terminal" if records[i]["following"] is None else "horizon"
                    for i in row["indices"]
                ],
                "Target stopping reason differs",
            )
            training.update(row["work"])
        require(dict(training) == arm["training_work"], "Training work totals differ")
        summaries, hashes, work = [], {}, Counter(training)
        for check in arm["checkpoints"]:
            point = check["update"]
            if point:
                path = folder / f"{name}-{point}-brain.json"
                snapshot = path.read_text()
                hashes[path.name] = sha(path)
            else:
                snapshot = initial_snapshot
            brain = Brain.from_snapshot(snapshot)
            require(
                brain.inspect()["admissions"] == point,
                "Checkpoint admission count differs",
            )
            if point < count:
                validate_targets(brain, arm["updates"][point], records, delay)
                target_checks += 16
            summaries.append(
                validate_checkpoint(brain, check, records, delay, preferred)
            )
            for key in ("root", "calibration", "evaluation"):
                work.update(check[key]["work"])
        require(dict(work) == arm["total_work"], "Arm work totals differ")
        final = folder / f"{name}-final-brain.json"
        require(
            sha(final) == arm["final_brain_sha256"], "Final checkpoint hash differs"
        )
        final_brain = Brain.from_snapshot(final.read_text())
        require(
            final_brain.inspect()["admissions"] == count,
            "Final admission count differs",
        )
        final_before = final_brain.snapshot()
        final_query = final_brain.settle(context(0, 0, delay))
        require(
            final_query["qualified"] and final_brain.snapshot() == final_before,
            "Final query refused or changed continuation",
        )
        if count == 512:
            require(
                final.read_bytes() == (folder / f"{name}-512-brain.json").read_bytes(),
                "Final and512-update checkpoints differ",
            )
        hashes[final.name] = sha(final)
        total.update(work)
        arms.append(
            dict(
                name=name,
                status=arm["status"],
                admitted_updates=count,
                refused_updates=0,
                checkpoints=summaries,
                final_root_values=[final_query["outputs"][f"q{i}"][0] for i in (0, 1)],
                seconds=arm["seconds"],
                training_work=dict(training),
                total_work=dict(work),
                checkpoint_sha256=hashes,
            )
        )
    require(dict(total) == report["total_work"], "Case work totals differ")
    return dict(
        name=folder.name,
        verified=True,
        experiment_complete=report["status"] == "complete",
        seed=seed,
        delay=delay,
        preferred=preferred,
        report_sha256=sha(folder / "report.json"),
        protocol_sha256=sha(folder / "protocol.json"),
        collection_sha256=protocol["collection_sha256"],
        schedules_sha256=report["schedules_sha256"],
        arms=arms,
        td_targets_spot_checked=target_checks,
        total_work=dict(total),
    )


def verify(root):
    sys.path.insert(0, str(root / "code/src"))
    from cadence import Brain, Cortex

    expected = {
        f"seed{seed}-preferred{preferred}-delay128"
        for seed in SEEDS
        for preferred in (0, 1)
    }
    folders = {
        path.parent.name: path.parent
        for path in (root / "exposure").glob("*/report.json")
    }
    cases = []
    for name in sorted(expected):
        try:
            require(name in folders, "Missing case report")
            cases.append(verify_case(root, folders[name], Brain, Cortex))
        except Exception as error:
            cases.append(
                dict(
                    name=name, verified=False, error=f"{type(error).__name__}: {error}"
                )
            )
    complete = [case for case in cases if case["verified"]]

    def available(case, arm, point):
        return next(
            (
                check
                for a in case["arms"]
                if a["name"] == arm
                for check in a["checkpoints"]
                if check["update"] == point
            ),
            None,
        )

    outcomes, paired = {}, {}
    for point in POINTS:
        common = [
            case
            for case in complete
            if all(available(case, arm, point) for arm in ARMS)
        ]
        paired[str(point)] = dict(
            cases=len(common),
            names=[case["name"] for case in common],
            successes={
                arm: sum(available(case, arm, point)["reward"] > 0 for case in common)
                for arm in ARMS
            },
        )
    for arm in ARMS:
        outcomes[arm] = {}
        for point in POINTS:
            retained = [case for case in complete if available(case, arm, point)]
            outcomes[arm][str(point)] = dict(
                successes=sum(
                    available(case, arm, point)["reward"] > 0 for case in retained
                ),
                cases=len(retained),
                names=[case["name"] for case in retained],
                comparison="Use paired outcomes for arm comparisons; this may include unpaired extra cases",
            )
    execution = read(root / "exposure/execution.json")
    execution_ok = (
        len(execution) == 10
        and {row["name"] for row in execution} == expected
        and all(
            any(
                case["name"] == row["name"]
                and (
                    (
                        case["experiment_complete"]
                        and row["status"] == "complete"
                        and row["returncode"] == 0
                    )
                    or (
                        not case["experiment_complete"]
                        and row["status"] == "failed"
                        and row["returncode"] == 1
                    )
                )
                for case in complete
            )
            for row in execution
        )
    )
    arms = [arm for case in complete for arm in case["arms"]]
    admissions = sum(arm["admitted_updates"] for arm in arms)
    checkpoints = sum(len(arm["checkpoints"]) for arm in arms)
    return dict(
        verified=len(complete) == 10 and set(folders) == expected and execution_ok,
        experiment_complete=len(complete) == 10
        and all(case["experiment_complete"] for case in complete),
        cases=cases,
        outcomes=outcomes,
        paired_outcomes=paired,
        execution_verified=execution_ok,
        admissions_verified=admissions,
        presentations_verified=admissions * 16,
        refused_updates=sum(arm["refused_updates"] for arm in arms),
        censored_arms=sum(arm["status"] != "complete" for arm in arms),
        brains_reloaded=checkpoints + len(arms),
        free_decisions_verified=checkpoints * 129,
        td_targets_spot_checked=sum(
            case["td_targets_spot_checked"] for case in complete
        ),
        verifier_sha256=sha(Path(__file__)),
        scope="All checkpoints and receipt structure verified; intermediate TD histories were not retrained. "
        "Toy action-irrelevant continuation with explicit memory; no native, recursive or strategic claim.",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.root)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "cases"}))
    raise SystemExit(0 if result["verified"] else 1)
