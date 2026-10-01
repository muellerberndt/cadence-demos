"""Independent work-crossing, custody and pure-query verification; no learning."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from pathlib import Path

import verify_self_correction as common
import work_matched_innovation as frozen

from cadence import Brain

PIN = "d7c8681d49e38b51b5a7ecd596c1943f639d82aa1a2953e109a5e0aa8d6f0609"
BASE_PIN = "a2dc8d91ff9ac11e35040db1183aba9834041f7a65e5db8a128feeb99fc56ec8"
SEEDS = (83, 89, 97, 101, 103)
ARMS = ("observer", "ordinary")
require, same, read, sha = common.require, common.same, common.read, common.sha


def source_and_artifacts(root):
    p = read(root / "protocol.json")
    require(p["schema"] == "work-matched-innovation/1", "protocol schema")
    identities = dict(p["sources"])
    for module, pin in ((frozen, PIN), (frozen.base, BASE_PIN)):
        require(sha(Path(module.__file__)) == pin, "reviewed collector bytes")
        names = [n for n in identities if Path(n).name == Path(module.__file__).name]
        require(
            len(names) == 1 and identities.pop(names[0]) == pin, "collector source pin"
        )
    common.source_check({"sources": identities})
    same(p["seeds"], SEEDS, "seed inventory")
    same(p["arms"], ("ordinary", "observer"), "arm inventory")
    require(
        p["data_seed"] == 20261007
        and p["condition"] == "narrow"
        and p["patches"] == 3
        and p["parameters"] == 9,
        "design identity",
    )
    same(
        p["training"],
        {"clean_updates": 64, "mixed_updates": 128, "batch_size": 16},
        "training contract",
    )
    same(
        p["compute"],
        {
            "arm_seconds": 40,
            "outer_seconds": 45,
            "max_workers": 3,
            "backend": "python",
            "dtype": "float64",
        },
        "resource contract",
    )
    for name in ("data", "founders"):
        require(sha(root / f"{name}.json") == p[f"{name}_sha256"], f"{name} hash")
    data, founders = read(root / "data.json"), read(root / "founders.json")
    same(data, frozen.tape(), "deterministic tape")
    signatures = {}
    for phase, count in (
        ("clean", 1024),
        ("mixed", 2048),
        ("clean_test", 32),
        ("mixed_test", 64),
    ):
        require(len(data[phase]) == count, "data count")
        signatures[phase] = set()
        for i, row in enumerate(data[phase]):
            require(row["id"] == f"{phase.replace('_', '-')}:{i}", "row identity")
            require(set(row["inputs"]) == {"u", "v"}, "input boundary")
            u, v, d = row["inputs"]["u"][0], row["inputs"]["v"][0], row["delta"]
            require(abs(u) <= 0.2 and abs(v) <= 0.4, "input support")
            require(
                d == 0 if phase.startswith("clean") else 0.03 <= abs(d) <= 0.12,
                "offset support",
            )
            same(row["actual_x"], [math.tanh(math.tanh(u)) + d], "physical observation")
            same(row["actual_y"], [math.tanh(v + d)], "physical target")
            signatures[phase].add((u, v))
        if phase.endswith("test"):
            require(
                not signatures[phase] & (signatures["clean"] | signatures["mixed"]),
                "heldout overlap",
            )
    for a, b in zip(data["mixed"][::2], data["mixed"][1::2], strict=True):
        same(a["inputs"], b["inputs"], "balanced inputs")
        require(a["delta"] == -b["delta"] > 0, "antithetic offsets")
    require(set(founders) == {str(s) for s in SEEDS}, "founder inventory")
    for seed in SEEDS:
        same(
            founders[str(seed)],
            frozen.base.founders(seed),
            "deterministic matched founders",
        )
        a, b = [Brain.from_snapshot(founders[str(seed)][arm]) for arm in ARMS]
        require(
            a.weights == b.weights and a.biases == b.biases, "initial coefficient match"
        )
        for model in (a, b):
            require(
                model.graph.n_patches == 3
                and len(model.weights) + len(model.biases) == 9,
                "capacity",
            )
    return data, founders


def cumulative(updates, count=None):
    result = Counter()
    for row in updates if count is None else updates[:count]:
        result.update(row["work"])
    return dict(result)


def first_crossing(updates, target):
    if target is None:
        return None
    work = 0
    for row in updates:
        work += row["work"]["edge_visits"]
        if not row["accepted"]:
            return None
        if row["phase"] == "mixed" and 32 <= row["update"] <= 48 and work >= target:
            return row["update"]
    return None


def check_crossing(record, updates, target, checkpoint_hash):
    crossing = first_crossing(updates, target["training_edge_visits"])
    require(crossing is not None, "no earned crossing")
    expected_work = cumulative(updates, 64 + crossing)
    same(
        record,
        {
            "mixed_update": crossing,
            "training_work": expected_work,
            "target_edge_visits": target["training_edge_visits"],
            "overshoot_edge_visits": expected_work["edge_visits"]
            - target["training_edge_visits"],
            "checkpoint_sha256": checkpoint_hash,
        },
        "first-crossing receipt",
    )


def replay_query(model, query, row):
    snapshot = model.snapshot()
    result = model.settle(
        row["inputs"],
        targets={"past": row["actual_x"]} if query["group"] == "correction" else None,
    )
    require(model.snapshot() == snapshot, "replay purity")
    for field in (
        "state",
        "predictions",
        "errors",
        "outputs",
        "qualified",
        "reason",
        "stationarity",
        "work",
        "sweeps",
    ):
        same(result[field], query[field], f"fresh {field}")
    return result


def call_plan(data, crossing):
    plan = []

    def queries(update):
        for group, key in (("clean-free", "clean_test"), ("correction", "mixed_test")):
            plan.extend(
                {
                    "kind": "query",
                    "check": f"mixed{update}",
                    "group": group,
                    "row": r["id"],
                }
                for r in data[key]
            )

    for phase, count, offset in (("clean", 64, 0), ("mixed", 128, 64)):
        for i in range(count):
            plan.append(
                {
                    "kind": "admission",
                    "phase": phase,
                    "update": i + 1,
                    "event_id": offset + i,
                    "rows": [r["id"] for r in data[phase][16 * i : 16 * (i + 1)]],
                }
            )
            if phase == "mixed" and i + 1 in {32, 128, crossing}:
                queries(i + 1)
        if phase == "clean":
            queries(0)
    return plan


def key(row):
    return (
        ("admission", row["phase"], row["update"])
        if row["kind"] == "admission"
        else ("query", row["check"], row["group"], row["row"])
    )


def groups(queries, crossing):
    checks = [0, 32, 128]
    if crossing is not None and crossing != 32:
        checks.append(crossing)
    result = []
    for check in checks:
        for group, expected in (("clean-free", 32), ("correction", 64)):
            rows = [
                q
                for q in queries
                if q["check"] == f"mixed{check}" and q["group"] == group
            ]
            good = [q for q in rows if q["qualified"]]
            mae = {
                head: sum(q[f"{head}_absolute_error"] for q in good) / len(good)
                if good
                else None
                for head in ("past", "future")
            }
            result.append(
                {
                    "check": f"mixed{check}",
                    "group": group,
                    "expected": expected,
                    "completed": len(rows),
                    "qualified": len(good),
                    "qualified_only_mae": mae,
                    "clean_gate": len(good) == expected
                    and all(v is not None and v <= 0.03 for v in mae.values())
                    if group == "clean-free"
                    else None,
                }
            )
    return result


def qualify(call):
    require(
        type(call["qualified"]) is bool
        and math.isfinite(call["stationarity"])
        and call["stationarity"] >= 0
        and call["qualified"] == (call["stationarity"] <= 1e-6),
        "qualification",
    )
    require(
        all(type(v) is int and v >= 0 for v in call["work"].values()), "work counters"
    )
    require(
        all(
            math.isfinite(call[k]) and call[k] >= 0
            for k in ("wall_seconds", "cpu_seconds")
        ),
        "call timing",
    )


def eligible(status, counts, summaries, unknown, arm, crossing):
    return (
        status == "complete"
        and counts["accepted"] == 192
        and not unknown
        and all(g["completed"] == g["qualified"] == g["expected"] for g in summaries)
        and all(g["clean_gate"] for g in summaries if g["group"] == "clean-free")
        and (arm == "observer" or crossing is not None)
    )


def verify_arm(root, seed, arm, data, founder, execution, observer_target, replay):
    folder = root / f"{arm}-seed{seed}"
    if not (folder / "result.json").exists():
        return {
            "seed": seed,
            "arm": arm,
            "status": "missing_or_censored",
            "eligible": False,
            "execution": execution,
            "groups": [],
            "ordinary_crossing": None,
        }, None
    report = read(folder / "result.json")
    updates, queries, checks = [
        read(folder / name) for name in ("updates.json", "queries.json", "checks.json")
    ]
    calls = [
        json.loads(line) for line in (folder / "calls.jsonl").read_text().splitlines()
    ]
    target = observer_target if arm == "ordinary" else None
    same(read(folder / "target-input.json"), target, "frozen target input")
    crossing = first_crossing(
        updates, target["training_edge_visits"] if target else None
    )
    plan = call_plan(data, crossing)
    require(len(calls) <= len(plan), "excess calls")
    details = {key(r): r for r in [*updates, *queries]}
    require(len(details) == len(updates) + len(queries), "duplicate detail")
    for kind, rows in (("admission", updates), ("query", queries)):
        expected = [key(r) for r in plan if r["kind"] == kind]
        same([key(r) for r in rows], expected[: len(rows)], "detail prefix")
    before, admitted = common.text_sha(founder), 0
    receipts, known = {}, {before: 0}
    training, inference = Counter(), Counter()
    for i, call in enumerate(calls):
        same({k: call[k] for k in plan[i]}, plan[i], "causal plan")
        require(
            call["status"] == "returned" and call["before_sha256"] == before,
            "call custody",
        )
        qualify(call)
        receipts[key(call)] = call
        detail = details.get(key(call))
        if detail is not None:
            same({k: detail[k] for k in call}, call, "detail versus returned call")
        if call["kind"] == "admission":
            training.update(call["work"])
            require(call["accepted"] is call["qualified"], "admission qualification")
            if detail:
                require(
                    detail["source"] == "witness" and detail["batch_size"] == 16,
                    "witness provenance",
                )
            admitted += call["accepted"]
        else:
            inference.update(call["work"])
            require(call["accepted"] is None, "query admission")
        if call["kind"] == "query" or not call["accepted"]:
            require(call["after_sha256"] == before, "pure query/refusal custody")
        if not call["qualified"]:
            require(i == len(calls) - 1, "continued after refusal")
        before = call["after_sha256"]
        known[before] = admitted
    require(set(details) <= set(receipts), "detail without call")
    current = read(folder / "current-call.json")
    unknown = False
    if current["status"] == "returned":
        same(current, calls[-1], "current returned receipt")
    else:
        require(len(calls) < len(plan), "pending after full plan")
        same(
            {k: current[k] for k in plan[len(calls)]},
            plan[len(calls)],
            "pending intent",
        )
        require(current["before_sha256"] == before, "pending state")
        require(
            current["status"] in ("started", "interrupted", "not_started_deadline"),
            "pending status",
        )
        unknown = current["status"] in ("started", "interrupted")
        if current["status"] == "interrupted":
            require(
                current["unknown_work"] is True
                and current["restored_sha256"] == before,
                "interrupted rollback",
            )
    lookup = {r["id"]: r for rows in data.values() for r in rows}
    for q in queries:
        row = lookup[q["row"]]
        require(
            len(q["state"]) == len(q["predictions"]) == len(q["errors"]) == 3,
            "query dimensions",
        )
        same(
            q["outputs"],
            {"past": [q["state"][1]], "future": [q["state"][2]]},
            "output state readout",
        )
        for head in ("past", "future"):
            actual = row["actual_x" if head == "past" else "actual_y"][0]
            require(
                q[f"{head}_absolute_error"] == abs(q["outputs"][head][0] - actual),
                "MAE arithmetic",
            )
        if q["group"] == "correction":
            require(q["state"][1] == row["actual_x"][0], "observed P clamp")
    summary = groups(queries, crossing)
    declared_labels = {f"mixed{n}" for n in (0, 32, 128)} | (
        {f"mixed{crossing}"} if crossing is not None else set()
    )
    require(set(checks) <= declared_labels, "undeclared checkpoint")
    replayed, reloaded, replay_work, endpoints = 0, 0, Counter(), {}
    for label, check in checks.items():
        update = int(label[5:])
        count = 64 + update
        require(
            len(updates) >= count and all(u["accepted"] for u in updates[:count]),
            "checkpoint before admissions",
        )
        snapshot = (folder / f"checkpoint-{label}.json").read_text()
        digest = common.text_sha(snapshot)
        model = Brain.from_snapshot(snapshot)
        require(
            model.snapshot() == snapshot
            and model.inspect()["admissions"] == count
            and known.get(digest) == count
            and updates[count - 1]["after_sha256"] == digest,
            "immutable checkpoint custody",
        )
        same(
            check,
            {"snapshot_sha256": digest, "training_work": cumulative(updates, count)},
            "checkpoint work",
        )
        selected = [q for q in queries if q["check"] == label]
        endpoints[label] = {
            "accepted_updates": count,
            "training_work": check["training_work"],
            "inference_work_at_check": cumulative(selected),
            "qualified_queries": sum(q["qualified"] for q in selected),
        }
        for q in selected:
            require(
                q["before_sha256"] == q["after_sha256"] == digest,
                "same checkpoint query",
            )
            if replay:
                row = lookup[q["row"]]
                result = replay_query(model, q, row)
                replay_work.update(result["work"])
                replayed += 1
        reloaded += 1
    require(
        all(q["check"] in checks for q in queries), "query missing saved checkpoint"
    )
    snapshot = read(folder / "last-completed.json")
    model = Brain.from_snapshot(snapshot)
    require(
        model.snapshot() == snapshot
        and common.text_sha(snapshot) == before == report["checkpoint_sha256"]
        and model.inspect()["admissions"] == known[before],
        "last retained checkpoint",
    )
    reloaded += 1
    exported_target = None
    if arm == "observer" and (folder / "work-target.json").exists():
        require("mixed32" in checks, "target without checkpoint")
        exported_target = {
            "seed": seed,
            "mixed_update": 32,
            "training_edge_visits": cumulative(updates, 96)["edge_visits"],
            "training_work": cumulative(updates, 96),
            "checkpoint_sha256": checks["mixed32"]["snapshot_sha256"],
            "protocol_sha256": sha(root / "protocol.json"),
        }
        same(
            read(folder / "work-target.json"),
            exported_target,
            "target frozen before endpoint",
        )
    if crossing is not None:
        c = read(folder / "crossing.json")
        check_crossing(
            c, updates, target, checks[f"mixed{crossing}"]["snapshot_sha256"]
        )
    else:
        require(not (folder / "crossing.json").exists(), "unearned crossing receipt")
    require(report["seed"] == seed and report["arm"] == arm, "report identity")
    require(
        report["sources_unchanged"] is True
        and report["protocol_sha256"] == sha(root / "protocol.json"),
        "source binding",
    )
    require(
        report["journal"]
        == {
            "bytes": (folder / "calls.jsonl").stat().st_size,
            "sha256": sha(folder / "calls.jsonl"),
        },
        "journal hash",
    )
    same(report["groups"], summary, "metric/gate promotion")
    same(report["training_work"], dict(training), "training work")
    same(report["inference_work"], dict(inference), "inference work")
    require(
        report["ordinary_crossing"] == crossing
        and report["target_missing"] == (arm == "ordinary" and target is None),
        "crossing/target promotion",
    )
    admissions = [c for c in calls if c["kind"] == "admission"]
    started = len(admissions) + int(
        current["kind"] == "admission" and current["status"] == "interrupted"
    )
    counts = {
        "started": started,
        "returned": len(admissions),
        "accepted": admitted,
        "refused": len(admissions) - admitted,
    }
    same(report["admission_counts"], counts, "admission counters")
    require(report["unknown_work"] is unknown, "unknown interrupted work")
    require(report["status"] in ("complete", "timeout", "error"), "report status")
    if report["status"] == "complete":
        require(
            len(calls) == len(plan)
            and len(details) == len(plan)
            and set(checks) == declared_labels
            and report["seconds"] <= 40
            and not unknown,
            "incomplete claimed complete",
        )
    own_eligible = eligible(report["status"], counts, summary, unknown, arm, crossing)
    require(report["eligible"] is bool(own_eligible), "eligibility promotion")
    process_good = execution["status"] == "returned" and execution["code"] == 0
    require(
        not process_good or report["status"] == "complete",
        "successful process without complete report",
    )
    return {
        "seed": seed,
        "arm": arm,
        "status": report["status"],
        "eligible": bool(own_eligible and process_good),
        "execution": execution,
        "ordinary_crossing": crossing,
        "groups": summary,
        "returned_calls": len(calls),
        "admitted_batches": admitted,
        "unknown_work": unknown,
        "training_work": dict(training),
        "inference_work": dict(inference),
        "returned_cpu_seconds": sum(c["cpu_seconds"] for c in calls),
        "returned_wall_seconds": sum(c["wall_seconds"] for c in calls),
        "endpoints": endpoints,
        "replayed_queries": replayed,
        "checkpoints_reloaded": reloaded,
        "replay_work": dict(replay_work),
    }, exported_target


def comparison(cases):
    rows = []
    for seed in SEEDS:
        arms = {c["arm"]: c for c in cases if c["seed"] == seed}

        def metric(arm, update, arms=arms):
            return next(
                (
                    g["qualified_only_mae"]["future"]
                    for g in arms[arm]["groups"]
                    if g["check"] == f"mixed{update}" and g["group"] == "correction"
                ),
                None,
            )

        cross = arms["ordinary"]["ordinary_crossing"]
        rows.append(
            {
                "seed": seed,
                "eligible": all(c["eligible"] for c in arms.values()),
                "observer32": metric("observer", 32),
                "ordinary32": metric("ordinary", 32),
                "ordinary_crossing": cross,
                "ordinary_matched": metric("ordinary", cross),
                "observer128": metric("observer", 128),
                "ordinary128": metric("ordinary", 128),
            }
        )
    all_good = len(rows) == 5 and all(r["eligible"] for r in rows)
    gains = {
        key: sum(r[key] - r["observer32"] for r in rows) / 5 if all_good else None
        for key in ("ordinary32", "ordinary_matched")
    }
    passed = all_good and all(
        gains[key] >= 0.005 and all(r[key] > r["observer32"] for r in rows)
        for key in gains
    )
    return {
        "all_pairs_eligible": all_good,
        "primary_pass": bool(passed),
        "rows": rows,
        "mean_mae_reductions": gains,
    }


def verify(root, replay=True):
    started = time.monotonic()
    data, founders = source_and_artifacts(root)
    same(
        read(root / "launch.json"),
        {
            "seeds": SEEDS,
            "arm_order": ARMS,
            "max_workers": 3,
            "outer_seconds_per_arm": 45,
        },
        "launch inventory",
    )
    execution = read(root / "execution.json")
    same(
        [(e["seed"], e["arm"]) for e in execution],
        [(s, a) for s in SEEDS for a in ARMS],
        "all ten executions",
    )
    cases = []
    for seed in SEEDS:
        target = None
        for arm in ARMS:
            e = next(e for e in execution if e["seed"] == seed and e["arm"] == arm)
            require(e["status"] in ("returned", "outer_timeout"), "process status")
            case, new_target = verify_arm(
                root, seed, arm, data, founders[str(seed)][arm], e, target, replay
            )
            cases.append(case)
            if arm == "observer":
                target = new_target
    compared = comparison(cases)
    raw = read(root / "comparison.json")
    require(raw["execution_complete"] is True, "complete process inventory")
    same({k: raw[k] for k in compared}, compared, "comparison promotion")
    return {
        "valid": True,
        "protocol_sha256": sha(root / "protocol.json"),
        "collector_sha256": PIN,
        "verifier_sha256": sha(Path(__file__)),
        "helper_sha256": sha(Path(common.__file__)),
        "pure_replay_enabled": replay,
        "cases": cases,
        "comparison": compared,
        "totals": {
            "planned_arms": 10,
            "statuses": dict(Counter(c["status"] for c in cases)),
            **{
                k: sum(c.get(k, 0) for c in cases)
                for k in (
                    "returned_calls",
                    "admitted_batches",
                    "replayed_queries",
                    "checkpoints_reloaded",
                )
            },
        },
        "seconds": time.monotonic() - started,
        "limits": "Learning updates are not numerically replayed. All saved queries are replayed under the pinned source. Whole-admission first crossing is conservative training-work dominance with extra ordinary examples, not exact compute, latency or exposure matching. Five model seeds share one environment tape. No planning or memory claim.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ledger-only", action="store_true")
    args = parser.parse_args()
    result = verify(args.root.resolve(), not args.ledger_only)
    with args.out.open("x") as handle:
        json.dump(result, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(
        json.dumps(
            {
                "valid": result["valid"],
                "totals": result["totals"],
                "comparison": result["comparison"],
                "seconds": result["seconds"],
            }
        )
    )
