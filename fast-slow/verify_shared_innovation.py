"""Verify all twenty frozen outcomes and replay saved queries without learning.

    PYTHONPATH=<frozen Cadence>/src python verify_shared_innovation.py \
        --root <finished campaign> --out <new verification.json>

Metrics, custody and the five-pair comparison are independently reconstructed.
Reviewed source-bound constructors regenerate tapes/founders. A censor never
licenses selecting surviving seeds. Numerical training updates are not replayed.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from pathlib import Path

import shared_innovation as frozen
import verify_self_correction as common

from cadence import Brain

PIN = "a2dc8d91ff9ac11e35040db1183aba9834041f7a65e5db8a128feeb99fc56ec8"
CONFIRMATION_PIN = "9110e0ddf69439b2fe39ca262e4151f52854e0d1ba2f9fcbf3a2f52e0b2fc345"
SEEDS = (2, 7, 11, 19, 29)
ARMS = ("ordinary", "observer")
CONDITIONS = {"narrow": 0.2, "wide": 0.8}
CHECKS = (0, 32, 128)
KINDS = ("clean-free", "offset-observed", "teacher-diagnostic")
require, same, read, sha = common.require, common.same, common.read, common.sha


def design(protocol):
    if protocol.get("schema") == "shared-innovation-confirmation/1":
        import innovation_confirmation as confirmation

        require(
            sha(Path(confirmation.__file__))
            == protocol["confirmation_source_sha256"]
            == CONFIRMATION_PIN,
            "confirmation wrapper source pin",
        )
        same(protocol["seeds"], (61, 67, 71, 73, 79), "confirmation seed grid")
        require(
            protocol["data_seed"] == 20261006
            and protocol["primary_condition"] == "narrow"
            and protocol["primary_checkpoint"] == 32,
            "confirmation primary endpoint",
        )
        same(protocol["required_clean_checks"], CHECKS, "confirmation clean gates")
        return {
            "mode": "confirmation",
            "seeds": tuple(protocol["seeds"]),
            "primary_checkpoint": 32,
            "required_clean_checks": CHECKS,
            "primary_condition": "narrow",
            "global_veto": True,
            "tape": confirmation.tape,
        }
    require(
        "schema" not in protocol and "confirmation_source_sha256" not in protocol,
        "unrecognized design; original endpoint cannot be replaced",
    )
    same(protocol["seeds"], SEEDS, "seed grid")
    require(
        "primary_checkpoint" not in protocol
        and "required_clean_checks" not in protocol,
        "original endpoint cannot be edited",
    )
    return {
        "mode": "development",
        "seeds": SEEDS,
        "primary_checkpoint": 128,
        "required_clean_checks": (0, 128),
        "primary_condition": None,
        "global_veto": False,
        "tape": frozen.tape,
    }


def source_and_artifacts(root):
    protocol = read(root / "protocol.json")
    declared = design(protocol)
    require(sha(Path(frozen.__file__)) == PIN, "reviewed collector source differs")
    identities = dict(protocol["sources"])
    candidates = [
        name for name in identities if Path(name).name == "shared_innovation.py"
    ]
    require(
        len(candidates) == 1 and identities.pop(candidates[0]) == PIN,
        "collector source pin",
    )
    common.source_check({"sources": identities})
    same(protocol["arms"], ARMS, "arm grid")
    same(protocol["conditions"], CONDITIONS, "condition grid")
    same(
        protocol["training"],
        {
            "clean_updates": 64,
            "mixed_updates": 128,
            "batch_size": 16,
            "mixed_checks": CHECKS,
        },
        "training schedule",
    )
    same(
        protocol["compute"],
        {
            "arm_deadline_seconds": 40,
            "outer_process_seconds": 45,
            "max_workers": 3,
            "backend": "python",
            "dtype": "float64",
        },
        "resource contract",
    )
    require(protocol["parameters"] == 9 and protocol["patches"] == 3, "model capacity")
    for name, field in (
        ("data.json", "data_sha256"),
        ("founders.json", "founders_sha256"),
        ("input-only-founders.json", "input_only_founders_sha256"),
    ):
        require(sha(root / name) == protocol[field], f"frozen {name} hash")
    data, founders, controls = (
        read(root / name)
        for name in ("data.json", "founders.json", "input-only-founders.json")
    )
    same(data, {c: declared["tape"](c) for c in CONDITIONS}, "deterministic tape")
    for condition, width in CONDITIONS.items():
        tape = data[condition]
        signatures = {}
        for phase, count in (
            ("clean", 1024),
            ("mixed", 2048),
            ("clean_test", 32),
            ("mixed_test", 64),
        ):
            require(len(tape[phase]) == count, "data row count")
            signatures[phase] = set()
            for i, row in enumerate(tape[phase]):
                require(
                    row["id"] == f"{phase.replace('_', '-')}:{i}"
                    and set(row["inputs"]) == {"u", "v"},
                    "row identity/input boundary",
                )
                u, v, delta = row["inputs"]["u"][0], row["inputs"]["v"][0], row["delta"]
                require(abs(u) <= width and abs(v) <= 0.4, "input range")
                require(
                    delta == 0
                    if phase.startswith("clean")
                    else 0.03 <= abs(delta) <= 0.12,
                    "offset range",
                )
                same(
                    row["actual_x"],
                    [math.tanh(math.tanh(u)) + delta],
                    "actual past arithmetic",
                )
                same(
                    row["actual_y"], [math.tanh(v + delta)], "actual future arithmetic"
                )
                signatures[phase].add((u, v))
            if phase.endswith("test"):
                require(
                    not signatures[phase] & (signatures["clean"] | signatures["mixed"]),
                    "held-out training overlap",
                )
        for positive, negative in zip(
            tape["mixed"][::2], tape["mixed"][1::2], strict=True
        ):
            same(positive["inputs"], negative["inputs"], "paired disturbance inputs")
            require(
                positive["delta"] == -negative["delta"] > 0,
                "balanced disturbance pairing",
            )
    require(
        set(founders) == set(controls) == {str(s) for s in declared["seeds"]},
        "founder seed inventory",
    )
    for seed in declared["seeds"]:
        same(
            founders[str(seed)], frozen.founders(seed), "seeded founder initialization"
        )
        models = {a: Brain.from_snapshot(founders[str(seed)][a]) for a in ARMS}
        maps = [
            dict(zip(models[a].graph.edges, models[a].weights, strict=True))
            for a in ARMS
        ]
        shared = maps[0].keys() & maps[1].keys()
        require(
            len(shared) == 5 and all(maps[0][e] == maps[1][e] for e in shared),
            "shared initial coefficients",
        )
        require(
            maps[0][("state", 0, 2)] == maps[1][("residual", 1, 2)],
            "replacement coefficient",
        )
        for arm, model in models.items():
            require(
                model.snapshot() == founders[str(seed)][arm]
                and len(model.weights) == 6
                and len(model.biases) == 3,
                "founder reload/capacity",
            )
        control = Brain.from_snapshot(controls[str(seed)])
        require(
            control.snapshot()
            == controls[str(seed)]
            == frozen.brain(seed, "observer", input_only=True).snapshot(),
            "input-only founder",
        )
        require(
            len(control.weights) + len(control.biases) == 7,
            "input-only control capacity",
        )
    return protocol, data, founders


def query_intents(data, update):
    return [
        {
            "kind": "query",
            "check": f"mixed{update}-{kind}",
            "row": row["id"],
            "teacher_clamped": kind == "teacher-diagnostic",
        }
        for kind in KINDS
        for row in data["clean_test" if kind == "clean-free" else "mixed_test"]
    ]


def call_plan(data):
    plan = []
    for phase, count, offset in (("clean", 64, 0), ("mixed", 128, 64)):
        for i in range(count):
            plan.append(
                {
                    "kind": "admission",
                    "phase": phase,
                    "update": i + 1,
                    "event_id": offset + i,
                    "rows": [r["id"] for r in data[phase][i * 16 : (i + 1) * 16]],
                }
            )
            if phase == "mixed" and i + 1 in (32, 128):
                plan.extend(query_intents(data, i + 1))
        if phase == "clean":
            plan.extend(query_intents(data, 0))
    return plan


def key(record):
    if record.get("kind") == "admission" or "phase" in record:
        return "admission", record["phase"], record["update"]
    return "query", record["check"], record["row"]


def qualification(record):
    value = record["stationarity"]
    require(
        type(record["qualified"]) is bool
        and math.isfinite(value)
        and value >= 0
        and record["qualified"] == (value <= 1e-6),
        "qualification versus stationarity",
    )


def groups_from_queries(queries):
    groups = []
    for update in CHECKS:
        for kind in KINDS:
            label = f"mixed{update}-{kind}"
            selected = [r for r in queries if r["check"] == label]
            good = [r for r in selected if r["qualified"]]
            expected = 32 if kind == "clean-free" else 64
            mae = {
                head: sum(r[f"{head}_absolute_error"] for r in good) / len(good)
                if good and kind != "teacher-diagnostic"
                else None
                for head in ("past", "future")
            }
            groups.append(
                {
                    "check": label,
                    "completed": len(selected),
                    "expected": expected,
                    "qualified": len(good),
                    "qualified_only_mae": mae,
                    "p_error_rms_qualified": math.sqrt(
                        sum(r["errors"][1] ** 2 for r in good) / len(good)
                    )
                    if good
                    else None,
                    "clean_gate": len(good) == expected
                    and all(v is not None and v <= 0.03 for v in mae.values())
                    if kind == "clean-free"
                    else None,
                }
            )
    return groups


def check_query(record, row):
    qualification(record)
    kind = record["check"].split("-", 1)[1]
    teacher, observed = kind == "teacher-diagnostic", kind != "clean-free"
    require(
        record["teacher_clamped"] is teacher and record["observed"] is observed,
        "query clamp role",
    )
    require(
        len(record["state"])
        == len(record["errors"])
        == len(record["predictions"])
        == 3,
        "query state dimensions",
    )
    if observed:
        require(record["state"][1] == row["actual_x"][0], "observed past clamp")
    if teacher:
        require(record["state"][2] == row["actual_y"][0], "teacher future clamp")
    expected_future = None if teacher else abs(record["state"][2] - row["actual_y"][0])
    require(
        record["future_absolute_error"] == expected_future,
        "teacher scored or forecast error altered",
    )
    require(
        record["past_absolute_error"] == abs(record["state"][1] - row["actual_x"][0]),
        "past error arithmetic",
    )
    require(record["delta"] == row["delta"], "audit offset")
    expected_bin = (
        "small"
        if abs(row["delta"]) < 0.06
        else "medium"
        if abs(row["delta"]) < 0.09
        else "large"
    )
    require(record["offset_bin"] == expected_bin, "offset bin")
    require(
        record["no_innovation_absolute_error"]
        == abs(math.tanh(row["inputs"]["v"][0]) - row["actual_y"][0]),
        "analytic baseline",
    )


def replay_queries(model, queries, lookup):
    before, work = model.snapshot(), Counter()
    for q in queries:
        row = lookup[q["row"]]
        targets = {"past": row["actual_x"]} if q["observed"] else None
        if q["teacher_clamped"]:
            targets["future"] = row["actual_y"]
        result = model.settle(row["inputs"], targets=targets)
        require(model.snapshot() == before, "fresh query changed checkpoint")
        for field in (
            "qualified",
            "reason",
            "state",
            "errors",
            "predictions",
            "stationarity",
            "work",
            "sweeps",
        ):
            same(result[field], q[field], f"fresh query {field} differs")
        work.update(result["work"])
    return dict(work)


def verify_arm(
    root,
    seed,
    condition,
    arm,
    data,
    founder,
    execution,
    replay,
    required_clean_checks=(0, 128),
    primary_checkpoint=128,
):
    folder = root / f"{condition}-{arm}-seed{seed}"
    if not folder.exists():
        return {
            "seed": seed,
            "condition": condition,
            "arm": arm,
            "status": "missing",
            "eligible": False,
            "execution": execution,
        }
    report = read(folder / "result.json") if (folder / "result.json").exists() else None
    updates = (
        read(folder / "updates.json") if (folder / "updates.json").exists() else []
    )
    queries = (
        read(folder / "evaluations.json")
        if (folder / "evaluations.json").exists()
        else []
    )
    current = (
        read(folder / "current-call.json")
        if (folder / "current-call.json").exists()
        else None
    )
    journal, partial_tail = [], False
    lines = (
        (folder / "calls.jsonl").read_text().splitlines()
        if (folder / "calls.jsonl").exists()
        else []
    )
    for i, line in enumerate(lines):
        try:
            journal.append(json.loads(line))
        except ValueError:
            require(
                report is None and i == len(lines) - 1, "malformed completed journal"
            )
            partial_tail = True
    plan = call_plan(data)
    require(len(journal) <= len(plan), "excess returned calls")
    details = {key(r): r for r in [*updates, *queries]}
    require(len(details) == len(updates) + len(queries), "duplicate call details")
    expected_updates = [key(r) for r in plan if r["kind"] == "admission"]
    expected_queries = [key(r) for r in plan if r["kind"] == "query"]
    same(
        [key(r) for r in updates],
        expected_updates[: len(updates)],
        "admission detail order",
    )
    same(
        [key(r) for r in queries],
        expected_queries[: len(queries)],
        "query detail order",
    )
    before, work, receipts = common.text_sha(founder), Counter(), {}
    accepted = 0
    custody = {before: 0}
    for i, call in enumerate(journal):
        same({k: call[k] for k in plan[i]}, plan[i], "causal call order")
        require(
            call["status"] == "returned" and call["before_sha256"] == before,
            "call state custody",
        )
        require(math.isfinite(call["seconds"]) and call["seconds"] >= 0, "call elapsed")
        require(
            all(type(v) is int and v >= 0 for v in call["work"].values()),
            "returned work counters",
        )
        work.update(call["work"])
        receipts[key(call)] = call
        if call["kind"] == "query":
            require(call["after_sha256"] == before, "query mutated brain")
        detail = details.get(key(call))
        if detail is not None:
            for field in ("work", "sweeps"):
                same(
                    detail[field],
                    call[field],
                    f"detail {field} differs from returned call",
                )
            require(
                detail["seconds"] >= call["seconds"],
                "outer timing shorter than solver timing",
            )
            if call["kind"] == "admission":
                qualification(detail)
                same(
                    {k: detail[k] for k in ("phase", "update", "rows", "event_id")},
                    {k: call[k] for k in ("phase", "update", "rows", "event_id")},
                    "admission ownership",
                )
                require(
                    detail["source"] == "witness"
                    and detail["batch_size"] == 16
                    and detail["accepted"] is detail["qualified"],
                    "actual admission provenance",
                )
                require(
                    detail["before_sha256"] == before
                    and detail["after_sha256"] == call["after_sha256"],
                    "admission snapshot chain",
                )
                if not detail["accepted"]:
                    require(call["after_sha256"] == before, "refusal mutated brain")
                accepted += detail["accepted"]
        before = call["after_sha256"]
        if detail is not None or call["kind"] == "query":
            custody[before] = accepted
    require(set(details) <= set(receipts), "details without returned calls")
    unexplained_current = False
    if current:
        if current["status"] == "returned":
            require(bool(journal), "returned current-call without journal")
            same(current, journal[-1], "current call/journal mismatch")
        else:
            require(len(journal) < len(plan), "pending call after complete plan")
            same(
                {k: current[k] for k in plan[len(journal)]},
                plan[len(journal)],
                "pending call identity",
            )
            require(current["before_sha256"] == before, "pending call state")
            require(
                current["status"] in ("started", "interrupted", "not_started_deadline"),
                "pending call status",
            )
            if current["status"] == "interrupted":
                require(
                    current["unknown_work"] is True
                    and current["restored_sha256"] == before,
                    "interrupted rollback/unknown work",
                )
            unexplained_current = current["status"] in ("started", "interrupted")
    lookup = {r["id"]: r for rows in data.values() for r in rows}
    for query in queries:
        check_query(query, lookup[query["row"]])
    groups = groups_from_queries(queries)
    replay_count, replay_work, checkpoints = 0, Counter(), 0
    for update in CHECKS:
        path = folder / f"checkpoint-mixed{update}.json"
        selected = [q for q in queries if q["check"].startswith(f"mixed{update}-")]
        if not path.exists():
            require(not selected, "queries lack checkpoint")
            continue
        snapshot = path.read_text()
        digest = common.text_sha(snapshot)
        model = Brain.from_snapshot(snapshot)
        require(
            model.snapshot() == snapshot and digest in custody,
            "checkpoint reload/custody",
        )
        require(
            model.inspect()["admissions"] == custody[digest],
            "checkpoint admission count",
        )
        before_check = next(
            i
            for i, c in enumerate(plan)
            if c["kind"] == "query" and c["check"] == f"mixed{update}-clean-free"
        )
        require(
            before_check <= len(journal)
            and journal[before_check - 1]["after_sha256"] == digest,
            "checkpoint at wrong point",
        )
        for query in selected:
            require(
                receipts[key(query)]["before_sha256"] == digest,
                "queries did not use same checkpoint",
            )
        if replay:
            replay_work.update(replay_queries(model, selected, lookup))
            replay_count += len(selected)
        checkpoints += 1
    latest_path = folder / "last-completed.json"
    if latest_path.exists():
        snapshot = read(latest_path)
        model = Brain.from_snapshot(snapshot)
        require(model.snapshot() == snapshot, "latest checkpoint canonical reload")
        digest = common.text_sha(snapshot)
        require(digest in custody, "latest checkpoint outside known custody")
        require(
            model.inspect()["admissions"] == custody[digest], "latest admission count"
        )
        checkpoints += 1
        if report:
            require(
                digest == before, "reported arm did not retain last completed state"
            )
    if report:
        require(
            report["seed"] == seed
            and report["condition"] == condition
            and report["arm"] == arm,
            "arm report identity",
        )
        require(
            report["sources_unchanged"] is True
            and report["protocol_sha256"] == sha(root / "protocol.json"),
            "report source/protocol",
        )
        require(
            report["checkpoint_sha256"] == sha(latest_path),
            "latest checkpoint file hash",
        )
        require(
            report["accepted_updates"] == accepted
            and report["planned_updates"] == 192
            and report["completed_queries"] == len(queries),
            "report call counts",
        )
        same(report["groups"], groups, "clean gate/metric promotion")
        status = report["status"]
        require(status in ("complete", "timeout", "error"), "arm report status")
        if status == "complete":
            require(
                len(journal) == 672
                and len(updates) == 192
                and len(queries) == 480
                and not unexplained_current,
                "incomplete run claimed complete",
            )
            require(report["seconds"] <= 40, "complete arm exceeded deadline")
    else:
        status = "incomplete"
    if execution and execution["status"] == "returned" and execution["code"] == 0:
        require(status == "complete", "successful process without complete arm")
    eligible = (
        status == "complete"
        and bool(execution)
        and execution["status"] == "returned"
        and execution["code"] == 0
        and accepted == 192
        and all(q["qualified"] for q in queries)
    )
    eligible = eligible and all(
        next(g for g in groups if g["check"] == f"mixed{n}-clean-free")["clean_gate"]
        for n in required_clean_checks
    )
    bins_by_checkpoint = {}
    for update in CHECKS:
        final = [q for q in queries if q["check"] == f"mixed{update}-offset-observed"]
        bins = {}
        for sign in (-1, 1):
            for size in ("small", "medium", "large"):
                subset = [
                    q
                    for q in final
                    if math.copysign(1, q["delta"]) == sign and q["offset_bin"] == size
                ]
                good = [q for q in subset if q["qualified"]]
                bins[f"{sign}:{size}"] = {
                    "completed": len(subset),
                    "qualified": len(good),
                    "qualified_only_mae": sum(q["future_absolute_error"] for q in good)
                    / len(good)
                    if good
                    else None,
                }
        bins_by_checkpoint[str(update)] = bins
    teacher_changes = {}
    endpoint_work = {}
    for update in CHECKS:
        endpoint = max(
            i
            for i, c in enumerate(plan)
            if c.get("check", "").startswith(f"mixed{update}-")
        )
        prefix = journal[: endpoint + 1]
        endpoint_work[str(update)] = {"complete": len(prefix) == endpoint + 1}
        for category in ("admission", "query"):
            consumed = [c for c in prefix if c["kind"] == category]
            total = Counter()
            for c in consumed:
                total.update(c["work"])
            endpoint_work[str(update)][category] = {
                "returned_calls": len(consumed),
                "work": dict(total),
                "solver_seconds": sum(c["seconds"] for c in consumed),
            }
        interval = [
            c
            for c in prefix
            if c["kind"] == "admission"
            and (
                c["phase"] == "clean"
                if update == 0
                else c["phase"] == "mixed"
                and (0 if update == 32 else 32) < c["update"] <= update
            )
        ]
        interval_total = Counter()
        for c in interval:
            interval_total.update(c["work"])
        endpoint_work[str(update)]["interval_training"] = {
            "phase": "clean" if update == 0 else "mixed",
            "after_mixed_update": None if update == 0 else 0 if update == 32 else 32,
            "through_mixed_update": update,
            "returned_calls": len(interval),
            "work": dict(interval_total),
            "solver_seconds": sum(c["seconds"] for c in interval),
        }
        free = {
            q["row"]: q
            for q in queries
            if q["check"] == f"mixed{update}-offset-observed"
        }
        teacher = {
            q["row"]: q
            for q in queries
            if q["check"] == f"mixed{update}-teacher-diagnostic"
        }
        shared = [
            name
            for name in free
            if name in teacher
            and free[name]["qualified"]
            and teacher[name]["qualified"]
        ]
        teacher_changes[str(update)] = {
            "qualified_pairs": len(shared),
            "p_error_change_rms": math.sqrt(
                sum(
                    (teacher[n]["errors"][1] - free[n]["errors"][1]) ** 2
                    for n in shared
                )
                / len(shared)
            )
            if shared
            else None,
        }
    return {
        "seed": seed,
        "condition": condition,
        "arm": arm,
        "status": status,
        "eligible": eligible,
        "execution": execution,
        "returned_calls": len(journal),
        "accepted_updates": accepted,
        "admitted_presentations": accepted * 16,
        "returned_training_calls": sum(c["kind"] == "admission" for c in journal),
        "returned_refusals": sum(not r["qualified"] for r in [*updates, *queries]),
        "missing_returned_details": len(journal) - len(details),
        "interrupted_work_unknown": unexplained_current,
        "partial_journal_tail": partial_tail,
        "work": dict(work),
        "groups": groups,
        "signed_offset_bins": bins_by_checkpoint[str(primary_checkpoint)],
        "signed_offset_bins_checkpoint": primary_checkpoint,
        "signed_offset_bins_by_checkpoint": bins_by_checkpoint,
        "cumulative_endpoint_work": endpoint_work,
        "same_weight_teacher_diagnostic": teacher_changes,
        "checkpoints_reloaded": checkpoints,
        "replayed_queries": replay_count,
        "replay_work": dict(replay_work),
    }


def comparison(
    cases, condition, seeds=SEEDS, checkpoint=128, *, global_veto=False, primary=True
):
    pairs = []
    for seed in seeds:
        arms = {
            c["arm"]: c
            for c in cases
            if c["condition"] == condition and c["seed"] == seed
        }
        errors = {}
        for arm in ARMS:
            group = next(
                (
                    g
                    for g in arms[arm].get("groups", [])
                    if g["check"] == f"mixed{checkpoint}-offset-observed"
                ),
                None,
            )
            errors[arm] = (
                group["qualified_only_mae"]["future"]
                if group and group["completed"] == group["qualified"] == 64
                else None
            )
        reduction = (
            errors["ordinary"] - errors["observer"]
            if all(v is not None for v in errors.values())
            else None
        )
        pairs.append(
            {
                "seed": seed,
                "eligible": all(arms[a].get("eligible", False) for a in ARMS),
                "correction_mae": errors,
                "ordinary_minus_observer": reduction,
            }
        )
    condition_eligible = all(p["eligible"] for p in pairs)
    global_eligible = len(cases) == 20 and all(c.get("eligible", False) for c in cases)
    eligible = condition_eligible and (not global_veto or global_eligible)
    average = (
        sum(p["ordinary_minus_observer"] for p in pairs) / 5
        if all(p["ordinary_minus_observer"] is not None for p in pairs)
        else None
    )
    passes = (
        eligible
        and average >= 0.005
        and all(p["ordinary_minus_observer"] > 0 for p in pairs)
    )
    return {
        "condition": condition,
        "checkpoint": checkpoint,
        "role": "primary" if primary else "secondary",
        "all_five_pairs_eligible": condition_eligible,
        "global_twenty_arm_veto_applied": global_veto,
        "global_twenty_arms_eligible": global_eligible if global_veto else None,
        "comparison_eligible": eligible,
        "pairs": pairs,
        "all_five_mean_mae_reduction": average,
        "predeclared_accuracy_criterion_met": passes if primary else None,
        "verdict": "accuracy_criterion_met"
        if passes and primary
        else "criterion_not_met"
        if eligible and primary
        else "descriptive_secondary"
        if not primary
        else "inconclusive",
        "efficiency_claim": False,
    }


def verify_campaign(root, replay=True):
    started = time.perf_counter()
    protocol, data, founders = source_and_artifacts(root)
    declared = design(protocol)
    jobs = [(s, c, a) for s in declared["seeds"] for c in CONDITIONS for a in ARMS]
    launch = read(root / "launch.json") if (root / "launch.json").exists() else None
    if launch:
        same(
            launch,
            {"jobs": jobs, **protocol["compute"]}
            if declared["mode"] == "confirmation"
            else {"jobs": jobs, "max_workers": 3, "outer_timeout_seconds": 45},
            "launch contract",
        )
    execution = (
        read(root / "execution.json") if (root / "execution.json").exists() else []
    )
    require(not execution or len(execution) == 20, "execution outcome count")
    for job, result in zip(jobs, execution, strict=bool(execution)):
        same(result["job"], job, "execution order")
        require(result["status"] in ("returned", "outer_timeout"), "execution status")
    cases = []
    for i, (seed, condition, arm) in enumerate(jobs):
        outcome = execution[i] if execution else None
        try:
            case = verify_arm(
                root,
                seed,
                condition,
                arm,
                data[condition],
                founders[str(seed)][arm],
                outcome,
                replay,
                declared["required_clean_checks"],
                declared["primary_checkpoint"],
            )
            case["verification"] = "verified"
        except (ValueError, KeyError, IndexError, TypeError, OSError) as error:
            case = {
                "seed": seed,
                "condition": condition,
                "arm": arm,
                "verification": "invalid",
                "eligible": False,
                "reason": str(error),
            }
        cases.append(case)
    return {
        "schema": "cadence-shared-innovation-verification/2",
        "design": {k: v for k, v in declared.items() if k != "tape"},
        "valid": all(c["verification"] == "verified" for c in cases),
        "protocol_sha256": sha(root / "protocol.json"),
        "verifier_sha256": sha(Path(__file__)),
        "shared_helpers_sha256": sha(Path(common.__file__)),
        "planned_outcomes": 20,
        "execution_complete": len(execution) == 20,
        "cases": cases,
        "comparisons": [
            comparison(
                cases,
                condition,
                declared["seeds"],
                checkpoint,
                global_veto=declared["global_veto"],
                primary=declared["mode"] == "development"
                or (
                    condition == declared["primary_condition"]
                    and checkpoint == declared["primary_checkpoint"]
                ),
            )
            for condition in CONDITIONS
            for checkpoint in (CHECKS if declared["mode"] == "confirmation" else (128,))
        ],
        "fresh_query_replay": replay,
        "replayed_queries": sum(c.get("replayed_queries", 0) for c in cases),
        "elapsed_seconds": time.perf_counter() - started,
        "limits": "Conditional prediction with matched counts/information; not temporal memory, exclusive expressivity or an efficiency claim. Teacher-clamped futures never score as predictions. Source-bound learning receipts checked, numerical learning not replayed. All five pairs are required without survivor selection.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--ledger-only", action="store_true")
    args = parser.parse_args()
    result = verify_campaign(args.root, replay=not args.ledger_only)
    if args.out:
        with args.out.open("x") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
    print(
        json.dumps(
            result
            if args.out is None
            else {
                k: result[k]
                for k in (
                    "valid",
                    "planned_outcomes",
                    "execution_complete",
                    "replayed_queries",
                    "comparisons",
                )
            },
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
