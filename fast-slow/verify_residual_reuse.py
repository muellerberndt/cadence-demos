"""Independent source/custody/arithmetic verifier; fresh pure queries, no learning.

The original all20-arm gate remains frozen even when a failed comparator is an
interesting measured outcome. Learning receipts are checked, not numerically
replayed. Missing/censored/invalid arms are retained and cannot promote a claim.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from pathlib import Path

import residual_reuse as frozen
import verify_self_correction as common

from cadence import Brain

PIN = "eadce708160ee1f498bad9e9c715b78d3ad7996008127737aa07d299b3f7627c"
PROTOCOL_PIN = "2a67788ddc3ddd1342a53412dcc92da645ecb7bc3399fd0d70c7af7c7262fc16"
SEEDS = (107, 109, 113, 127, 131)
ARMS = ("ordinary", "observer")
LAYOUTS = {"input_only": 6, "coupled": 9}
CHECKS = (0, 32, 128)
KINDS = ("clean-free", "offset-observed", "teacher-diagnostic")
require, same, read, sha = common.require, common.same, common.read, common.sha


def jobs():
    return [
        (seed, layout, arm)
        for index, seed in enumerate(SEEDS)
        for layout in LAYOUTS
        for arm in (ARMS if index % 2 == 0 else ARMS[::-1])
    ]


def source_and_artifacts(root):
    protocol = read(root / "protocol.json")
    require(sha(root / "protocol.json") == PROTOCOL_PIN, "frozen protocol differs")
    require(sha(Path(frozen.__file__)) == PIN, "collector pin")
    identities = dict(protocol["sources"])
    names = [name for name in identities if Path(name).name == "residual_reuse.py"]
    require(
        len(names) == 1 and identities.pop(names[0]) == PIN, "frozen collector identity"
    )
    common.source_check({"sources": identities})
    same(protocol["jobs"], jobs(), "planned arm order")
    same(protocol["seeds"], SEEDS, "seed inventory")
    same(protocol["arms"], ARMS, "arm inventory")
    same(protocol["layouts"], LAYOUTS, "capacity inventory")
    for name in ("data", "founders"):
        require(
            sha(root / f"{name}.json") == protocol[f"{name}_sha256"], f"{name} identity"
        )
    data, founders = read(root / "data.json"), read(root / "founders.json")
    same(data, frozen.tape(), "deterministic new tape")
    signatures = {}
    for phase, count in (
        ("clean", 1024),
        ("mixed", 2048),
        ("clean_test", 32),
        ("mixed_test", 64),
    ):
        require(len(data[phase]) == count, "data cardinality")
        signatures[phase] = set()
        for index, row in enumerate(data[phase]):
            require(
                row["id"] == f"{phase.replace('_', '-')}:{index}"
                and set(row["inputs"]) == {"u", "v"},
                "row identity/boundary",
            )
            u, v, delta = row["inputs"]["u"][0], row["inputs"]["v"][0], row["delta"]
            require(abs(u) <= 1.2 and abs(v) <= 0.4, "body input range")
            require(
                delta == 0 if phase.startswith("clean") else 0.03 <= abs(delta) <= 0.12,
                "body disturbance range",
            )
            same(
                row["actual_x"],
                [math.tanh(u) + delta],
                "independent observed body equation",
            )
            same(
                row["actual_y"],
                [math.tanh(v + delta)],
                "independent future body equation",
            )
            require(abs(row["actual_x"][0]) < 1, "actual state bound")
            signatures[phase].add((u, v))
        if phase.endswith("test"):
            require(
                not signatures[phase] & (signatures["clean"] | signatures["mixed"]),
                "heldout overlap",
            )
    for phase in ("mixed", "mixed_test"):
        for a, b in zip(data[phase][::2], data[phase][1::2], strict=True):
            same(a["inputs"], b["inputs"], "antithetic common input")
            require(a["delta"] == -b["delta"] > 0, "antithetic disturbances")
    require(set(founders) == set(LAYOUTS), "founder layout inventory")
    for layout, size in LAYOUTS.items():
        require(set(founders[layout]) == {str(s) for s in SEEDS}, "founder seeds")
        for seed in SEEDS:
            same(
                founders[layout][str(seed)],
                frozen.founders(seed, layout),
                "founder regeneration",
            )
            models = {
                arm: Brain.from_snapshot(founders[layout][str(seed)][arm])
                for arm in ARMS
            }
            maps = {
                arm: dict(zip(model.graph.edges, model.weights, strict=True))
                for arm, model in models.items()
            }
            shared = maps["ordinary"].keys() & maps["observer"].keys()
            require(
                len(shared) == len(models["ordinary"].weights) - 1
                and all(maps["ordinary"][e] == maps["observer"][e] for e in shared),
                "shared coefficients",
            )
            patches = 2 if layout == "input_only" else 3
            replacement = ("input", 0, 1) if layout == "input_only" else ("state", 0, 2)
            require(
                maps["ordinary"][replacement]
                == maps["observer"][("residual", patches - 2, patches - 1)],
                "replacement coefficient",
            )
            for arm, model in models.items():
                require(
                    model.snapshot() == founders[layout][str(seed)][arm]
                    and model.graph.n_patches == patches
                    and len(model.weights) + len(model.biases) == size,
                    "founder reload/capacity",
                )
                require(model.biases == models["ordinary"].biases, "shared biases")
                expected = {("input", 0, patches - 2)} | (
                    {("state", 0, 1)} if layout == "coupled" else set()
                )
                require(
                    {e for e in model.graph.edges if e[2] == patches - 2} == expected,
                    "P dependence topology",
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


def groups_from_queries(queries, p_index):
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
                        sum(r["errors"][p_index] ** 2 for r in good) / len(good)
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


def check_query(record, row, patches):
    p_index = patches - 2
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
        == patches,
        "query state dimensions",
    )
    for state, prediction, error in zip(
        record["state"], record["predictions"], record["errors"], strict=True
    ):
        require(
            all(math.isfinite(v) for v in (state, prediction, error))
            and abs(state - prediction - error) < 2e-14,
            "independent residual equation",
        )
    if observed:
        require(record["state"][p_index] == row["actual_x"][0], "observed past clamp")
    if teacher:
        require(
            record["state"][p_index + 1] == row["actual_y"][0], "teacher future clamp"
        )
    expected_future = (
        None if teacher else abs(record["state"][p_index + 1] - row["actual_y"][0])
    )
    require(
        record["future_absolute_error"] == expected_future,
        "teacher scored or forecast error altered",
    )
    require(
        record["past_absolute_error"]
        == abs(record["state"][p_index] - row["actual_x"][0]),
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


def diagnostics_from_queries(queries, layout):
    p = 0 if layout == "input_only" else 1
    diagnostics = []
    for update in CHECKS:
        free = {
            r["row"]: r
            for r in queries
            if r["check"] == f"mixed{update}-offset-observed"
        }
        teacher = {
            r["row"]: r
            for r in queries
            if r["check"] == f"mixed{update}-teacher-diagnostic"
        }
        if len(free) != 64 or len(teacher) != 64:
            continue
        require(free.keys() == teacher.keys(), "diagnostic paired rows")
        require(
            all(
                free[row]["model_sha256"] == teacher[row]["model_sha256"]
                for row in free
            ),
            "same-weight diagnostic",
        )
        require(
            len({q["model_sha256"] for q in [*free.values(), *teacher.values()]}) == 1,
            "diagnostic checkpoint identity",
        )
        shifts = [teacher[row]["errors"][p] - free[row]["errors"][p] for row in free]
        predictions_identical = all(
            teacher[row]["predictions"][p] == free[row]["predictions"][p]
            for row in free
        )
        errors_identical = all(x == 0 for x in shifts)
        result = {
            "update": update,
            "matched_rows": 64,
            "model_sha256": next(iter(free.values()))["model_sha256"],
            "p_predictions_exactly_invariant": predictions_identical,
            "p_errors_exactly_invariant": errors_identical,
            "p_error_shift_rms": math.sqrt(sum(x * x for x in shifts) / len(shifts)),
            "p_error_shift_max": max(abs(x) for x in shifts),
        }
        if layout == "coupled":
            result["m_state_shift_rms"] = math.sqrt(
                sum(
                    (teacher[row]["state"][0] - free[row]["state"][0]) ** 2
                    for row in free
                )
                / len(shifts)
            )
        diagnostics.append(result)
    return diagnostics


def verify_arm(
    root,
    seed,
    layout,
    arm,
    data,
    founder,
    execution,
    replay,
    required_clean_checks=CHECKS,
    primary_checkpoint=128,
):
    patches = 2 if layout == "input_only" else 3
    p_index = patches - 2
    folder = root / f"{layout}-{arm}-seed{seed}"
    if not folder.exists():
        return {
            "seed": seed,
            "layout": layout,
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
        qualification(call)
        if not call["qualified"]:
            require(i == len(journal) - 1, "continued after refusal")
        receipts[key(call)] = call
        if call["kind"] == "query":
            require(call["after_sha256"] == before, "query mutated brain")
            require(call["accepted"] is None, "query claimed admission")
        else:
            require(call["accepted"] is call["qualified"], "admission qualification")
            if not call["accepted"]:
                require(call["after_sha256"] == before, "refusal changed checkpoint")
            accepted += call["accepted"]
        detail = details.get(key(call))
        if detail is not None:
            for field in ("work", "sweeps", "qualified", "reason", "stationarity"):
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
                require(
                    detail["accepted"] == call["accepted"],
                    "admission acceptance receipt",
                )
        before = call["after_sha256"]
        custody[before] = accepted
    require(set(details) <= set(receipts), "details without returned calls")
    unexplained_current = False
    lagging_current = False
    if current:
        if current["status"] == "returned":
            require(bool(journal), "returned current-call without journal")
            same(current, journal[-1], "current call/journal mismatch")
        else:
            if (
                current["status"] == "started"
                and journal
                and key(current) == key(journal[-1])
            ):
                same(
                    {k: current[k] for k in plan[len(journal) - 1]},
                    plan[len(journal) - 1],
                    "lagging current-call identity",
                )
                require(
                    current["before_sha256"] == journal[-1]["before_sha256"],
                    "lagging current-call state",
                )
                require(
                    report is None, "reported arm has unfinished receipt bookkeeping"
                )
                lagging_current = True
            if lagging_current:
                current = None
        if current and current["status"] != "returned":
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
        check_query(query, lookup[query["row"]], patches)
        require(
            query["model_sha256"] == receipts[key(query)]["before_sha256"],
            "query model identity",
        )
    groups = groups_from_queries(queries, p_index)
    diagnostics = diagnostics_from_queries(queries, layout)
    saved_diagnostics = (
        read(folder / "diagnostics.json")
        if (folder / "diagnostics.json").exists()
        else []
    )
    require(
        len(saved_diagnostics) <= len(diagnostics),
        "diagnostics without complete queries",
    )
    same(
        saved_diagnostics,
        diagnostics[: len(saved_diagnostics)],
        "diagnostic arithmetic",
    )
    if layout == "input_only":
        require(
            all(
                d["p_predictions_exactly_invariant"] and d["p_errors_exactly_invariant"]
                for d in diagnostics
            ),
            "input-only invariant failed",
        )
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
            and report["layout"] == layout
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
            report["accepted_updates"] == sum(u["accepted"] for u in updates)
            and report["planned_updates"] == 192
            and report["completed_queries"] == len(queries),
            "report call counts",
        )
        same(report["groups"], groups, "clean gate/metric promotion")
        same(report["diagnostics"], saved_diagnostics, "diagnostic report")
        unknown_count = int(bool(current and current["status"] == "interrupted"))
        unknown_admission = int(bool(unknown_count and current["kind"] == "admission"))
        admissions = [c for c in journal if c["kind"] == "admission"]
        expected_counts = {
            "started": len(journal) + unknown_count,
            "returned": len(journal),
            "qualified": sum(c["qualified"] for c in journal),
            "refused": sum(not c["qualified"] for c in journal),
            "interrupted_unknown_work": unknown_count,
            "admissions_started": len(admissions) + unknown_admission,
            "admissions_returned": len(admissions),
            "admissions_accepted": accepted,
        }
        same(report["call_counts"], expected_counts, "attempt/refusal counters")
        require(
            report["attempted_training_presentations"]
            == expected_counts["admissions_started"] * 16
            and report["admitted_training_presentations"] == accepted * 16,
            "row presentations",
        )
        status = report["status"]
        require(status in ("complete", "timeout", "error"), "arm report status")
        if status == "complete":
            require(
                len(journal) == 672
                and len(updates) == 192
                and len(queries) == 480
                and len(saved_diagnostics) == 3
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
    if report:
        intrinsic = (
            status == "complete"
            and accepted == 192
            and len(updates) == 192
            and len(queries) == 480
            and len(saved_diagnostics) == 3
            and not unexplained_current
            and all(c["qualified"] for c in journal)
            and all(
                next(g for g in groups if g["check"] == f"mixed{n}-clean-free")[
                    "clean_gate"
                ]
                for n in CHECKS
            )
        )
        require(report["eligible"] is bool(intrinsic), "arm eligibility promotion")
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
                    (teacher[n]["errors"][p_index] - free[n]["errors"][p_index]) ** 2
                    for n in shared
                )
                / len(shared)
            )
            if shared
            else None,
        }
    return {
        "seed": seed,
        "layout": layout,
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
        "diagnostics": diagnostics,
        "lagging_current_call_after_returned_journal": lagging_current,
        "checkpoints_reloaded": checkpoints,
        "replayed_queries": replay_count,
        "replay_work": dict(replay_work),
    }


def comparisons(cases):
    eligible = len(cases) == 20 and all(c.get("eligible", False) for c in cases)
    result = []
    for layout in LAYOUTS:
        pairs = []
        for seed in SEEDS:
            metrics = {}
            for arm in ARMS:
                case = next(
                    c
                    for c in cases
                    if c["seed"] == seed and c["layout"] == layout and c["arm"] == arm
                )
                final = next(
                    (
                        g
                        for g in case.get("groups", [])
                        if g["check"] == "mixed128-offset-observed"
                    ),
                    None,
                )
                metrics[arm] = (
                    final["qualified_only_mae"]["future"]
                    if final and final["qualified"] == final["completed"] == 64
                    else None
                )
            difference = (
                metrics["ordinary"] - metrics["observer"]
                if all(v is not None for v in metrics.values())
                else None
            )
            pairs.append(
                {"seed": seed, "mae": metrics, "ordinary_minus_observer": difference}
            )
        deltas = [p["ordinary_minus_observer"] for p in pairs]
        mean = sum(deltas) / 5 if all(v is not None for v in deltas) else None
        passed = (
            eligible
            and mean is not None
            and mean >= 0.005
            and all(v > 0 for v in deltas)
        )
        result.append(
            {
                "layout": layout,
                "pairs": pairs,
                "eligible": eligible,
                "mean_mae_reduction": mean,
                "criterion_met": passed,
                "efficiency_claim": False,
            }
        )
    return result


def verify(root, replay=True):
    started = time.monotonic()
    protocol, data, founders = source_and_artifacts(root)
    execution = (
        read(root / "execution.json") if (root / "execution.json").exists() else []
    )
    if (root / "launch.json").exists():
        same(
            read(root / "launch.json"),
            {"jobs": jobs(), "max_workers": 3, "outer_timeout_seconds": 45},
            "launch contract",
        )
    require(not execution or len(execution) == 20, "execution inventory")
    cases = []
    for index, (seed, layout, arm) in enumerate(jobs()):
        outcome = execution[index] if execution else None
        if outcome:
            same(outcome["job"], (seed, layout, arm), "execution identity")
            require(
                outcome["status"] in ("returned", "outer_timeout"), "execution status"
            )
        try:
            case = verify_arm(
                root,
                seed,
                layout,
                arm,
                data,
                founders[layout][str(seed)][arm],
                outcome,
                replay,
            )
            case["verification"] = "verified"
        except (ValueError, KeyError, TypeError, IndexError, OSError) as error:
            case = {
                "seed": seed,
                "layout": layout,
                "arm": arm,
                "eligible": False,
                "verification": "invalid",
                "reason": str(error),
            }
        cases.append(case)
    comparison = comparisons(cases)
    summary_error = None
    if (root / "summary.json").exists():
        try:
            summary = read(root / "summary.json")
            require(
                summary["protocol_sha256"] == sha(root / "protocol.json"),
                "summary protocol",
            )
            same(summary["comparisons"], comparison, "summary comparison promotion")
            require(
                summary["all_twenty_arms_eligible"]
                is all(c.get("eligible", False) for c in cases),
                "global veto promotion",
            )
            require(len(summary["outcomes"]) == 20, "summary retained inventory")
            for (seed, layout, arm), row, outcome in zip(
                jobs(), summary["outcomes"], execution, strict=True
            ):
                same(row["execution"], outcome, "summary execution binding")
                path = root / f"{layout}-{arm}-seed{seed}" / "result.json"
                if path.exists():
                    same(row["report"], read(path), "summary report binding")
        except (ValueError, KeyError, TypeError, OSError) as error:
            summary_error = str(error)
    still_pinned = (
        sha(Path(frozen.__file__)) == PIN and protocol["sources"] == frozen.sources()
    )
    return {
        "schema": "residual-reuse-verification/1",
        "valid": all(c["verification"] == "verified" for c in cases)
        and summary_error is None
        and still_pinned,
        "protocol_sha256": sha(root / "protocol.json"),
        "collector_sha256": PIN,
        "verifier_sha256": sha(Path(__file__)),
        "shared_helpers_sha256": sha(Path(common.__file__)),
        "sources_still_pinned": still_pinned,
        "planned_outcomes": 20,
        "execution_complete": len(execution) == 20,
        "cases": cases,
        "comparisons": comparison,
        "summary_error": summary_error,
        "fresh_query_replay": replay,
        "replayed_queries": sum(c.get("replayed_queries", 0) for c in cases),
        "elapsed_seconds": time.monotonic() - started,
        "limits": [
            "Learning custody and declared witnesses are checked; numerical learning is not replayed.",
            "Every primary retains the original all20-arm/all-three-clean-gate veto; descriptive errors never replace that criterion.",
            "Exact input-only P-residual invariance at fixed observed P excludes feedback from H to that feature; any benefit there is representation reuse.",
            "Coupled graph feedback may alter the feature; this is not proof of useful iterative correction, persistent memory or exclusive learnability.",
            "Cross-size comparisons are not capacity matched; equal updates do not establish efficiency.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ledger-only", action="store_true")
    args = parser.parse_args()
    result = verify(args.root, replay=not args.ledger_only)
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
                    "replayed_queries",
                    "summary_error",
                    "elapsed_seconds",
                    "comparisons",
                )
            }
        )
    )
    return int(not result["valid"])


if __name__ == "__main__":
    raise SystemExit(main())
