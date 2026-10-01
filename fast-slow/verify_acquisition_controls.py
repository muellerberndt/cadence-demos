"""Read-only acquisition evidence verifier, including fresh immutable queries.

    PYTHONPATH=<frozen Cadence>/src python verify_acquisition_controls.py \
        --root <campaign> --out <receipt.json>

All twelve pilot cases survive missing/censored outcomes. Deterministic source-
bound tape/founder regeneration uses the reviewed collector; sequence, exposure,
metric and selection checks are independent. Learning is never replayed.
Use --ledger-only to omit fresh gate queries; the receipt records that limit.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path

import acquisition_controls as producer
import verify_self_correction as common

from cadence import Brain

PIN = "8b51c48e719696794cac73a1916702efb1f7b2e654b444dd1f4edf8843a0ba54"
MILESTONES = (32, 128, 512)
ARMS = ("ordinary", "observer")
CONDITIONS = ("fixed_positive", "fixed_negative", "balanced_mixed")
require, same, read, sha = common.require, common.same, common.read, common.sha


def rms(values):
    values = list(values)
    return math.sqrt(sum(v * v for v in values) / len(values)) if values else 0.0


def frozen_artifacts(root):
    protocol = read(root / "protocol.json")
    require(protocol["schema"] == "cadence-acquisition-controls/1", "protocol schema")
    require(
        sha(Path(producer.__file__)) == PIN,
        "collector source differs from reviewed freeze",
    )
    identities = dict(protocol["sources"])
    collectors = [p for p in identities if Path(p).name == "acquisition_controls.py"]
    require(
        len(collectors) == 1 and identities.pop(collectors[0]) == PIN,
        "collector source pin",
    )
    common.source_check({"sources": identities})
    same(protocol["cases"], producer.specifications(), "case grid differs")
    same(protocol["checkpoints"], MILESTONES, "exposure checkpoints differ")
    for key, value in {
        "batch_size": 16,
        "unique_training_rows": 512,
        "arm_seconds": 50,
        "case_seconds": 120,
        "max_workers": 3,
        "settle_budget": 2048,
        "tolerance": 1e-6,
        "state_prior": 0.01,
        "device": "python",
        "dtype": "float64",
    }.items():
        require(protocol[key] == value, f"protocol {key}")
    expected_files = {
        f"{prefix}-{condition}.json"
        for condition in CONDITIONS
        for prefix in ("tape", "replay")
    }
    expected_files.update(
        f"founder-{s['id']}-{a}.json" for s in protocol["cases"] for a in ARMS
    )
    require(set(protocol["files"]) == expected_files, "frozen artifact inventory")
    for filename, digest in protocol["files"].items():
        require(sha(root / filename) == digest, f"artifact changed: {filename}")
    tapes, schedules, founders = {}, {}, {}
    for condition in CONDITIONS:
        tapes[condition] = tape = read(root / f"tape-{condition}.json")
        schedules[condition] = schedule = read(root / f"replay-{condition}.json")
        same(tape, producer.tape(condition), "deterministic tape differs")
        same(schedule, producer.replay(tape["train"]), "deterministic replay differs")
        gains = (
            {0.3}
            if condition == "fixed_positive"
            else {-0.3}
            if condition == "fixed_negative"
            else {-0.3, 0.3}
        )
        signatures = []
        for phase, size in (
            ("train", 512),
            ("development", 128),
            ("confirmation", 128),
        ):
            rows = tape[phase]
            require(len(rows) == size, "corpus size")
            cells, unique = Counter(), set()
            for i, row in enumerate(rows):
                x0, a0 = row["inputs"]["previous"]
                x1, a1 = row["inputs"]["present"]
                gain = row["audit"]["future_gain"]
                require(
                    set(row["inputs"]) == {"previous", "present"}, "privileged input"
                )
                require(
                    gain in gains and gain == row["audit"]["past_gain"], "unstable gain"
                )
                require(
                    not row["audit"]["switch"] and row["index"] == i,
                    "row identity/switch",
                )
                require(
                    0.25 <= abs(a0) <= 0.5 and 0.25 <= abs(a1) <= 0.5, "action bounds"
                )
                require(x1 == 0.8 * x0 + gain * a0, "past witness")
                y = 0.8 * x1 + gain * a1
                same(row["past"], [x1, x1 - x0], "past clamps")
                same(row["future"], [y, y - x1], "future witnesses")
                cells[(gain, a0 > 0, a1 > 0)] += 1
                unique.add((x0, a0, x1, a1))
            require(
                len(cells) == 4 * len(gains)
                and set(cells.values()) == {size // len(cells)},
                "corpus strata",
            )
            require(
                len(unique) == size and not any(unique & prior for prior in signatures),
                "held-out overlap",
            )
            signatures.append(unique)
        require(len(schedule) == 512, "replay updates")
        for indices in schedule:
            counts = Counter(tape["train"][i]["stratum"] for i in indices)
            require(len(indices) == len(set(indices)) == 16, "batch row uniqueness")
            require(
                len(counts) == 4 * len(gains)
                and set(counts.values()) == {16 // len(counts)},
                "batch strata",
            )
        for start in range(0, 512, 32):
            require(
                Counter(i for batch in schedule[start : start + 32] for i in batch)
                == Counter(range(512)),
                "epoch changes unique exposure",
            )
    for spec in protocol["cases"]:
        models = {}
        for arm in ARMS:
            text = (root / f"founder-{spec['id']}-{arm}.json").read_text()
            brain = models[arm] = Brain.from_snapshot(text)
            require(
                text
                == brain.snapshot()
                == producer.make_brain(
                    spec["seed"], arm, spec["layout"], spec["parameter_prior"]
                ).snapshot(),
                "founder initialization",
            )
            require(
                len(brain.weights) + len(brain.biases) == spec["parameters"],
                "parameter count",
            )
            founders[(spec["id"], arm)] = text
        left, right = (
            dict(zip(models[a].graph.edges, models[a].weights, strict=True))
            for a in ARMS
        )
        width = 2 if spec["layout"] == "small" else 4
        shared = left.keys() & right.keys()
        require(
            len(shared) == (24 if width == 2 else 44)
            and all(left[e] == right[e] for e in shared),
            "shared coefficients",
        )
        for source in (0, 1):
            for target in range(4, 4 + width):
                require(
                    left[("state", source, target)]
                    == right[("residual", source + 2, target)],
                    "replacement coefficients",
                )
        same(models["ordinary"].biases, models["observer"].biases, "shared biases")
    return protocol, tapes, schedules, founders


def query_plan(rows, update):
    plan = [
        {
            "kind": "forecast",
            "update": update,
            "row": r["index"],
            "gain": r["audit"]["future_gain"],
        }
        for r in rows
    ]
    cells = sorted({r["stratum"] for r in rows})
    for cell in cells:
        selected = [r for r in rows if r["stratum"] == cell]
        for row in selected[: 16 // len(cells)]:
            plan.extend(
                {
                    "kind": "secant",
                    "update": update,
                    "row": row["index"],
                    "gain": row["audit"]["future_gain"],
                    "candidate": a,
                }
                for a in (-0.5, 0.5)
            )
    plan.extend(
        {
            "kind": "full_clamp_diagnostic",
            "update": update,
            "row": next(r["index"] for r in rows if r["stratum"] == cell),
        }
        for cell in cells
    )
    return plan


def call_plan(rows, schedule, maximum):
    plan = []
    for update, indices in enumerate(schedule[:maximum], 1):
        plan.append({"kind": "admission", "update": update, "indices": indices})
        if update in MILESTONES:
            plan.extend(query_plan(rows, update))
    return plan


def independent_score(queries, rows, update, admissions, refusals, coefficients):
    forecasts = [q for q in queries if q["kind"] == "forecast"]
    by_gain = {}
    for gain in sorted({r["audit"]["future_gain"] for r in rows}):
        group = [q for q in forecasts if rows[q["row"]]["audit"]["future_gain"] == gain]
        by_gain[str(gain)] = [
            statistics.mean(
                abs(q["future"][axis] - rows[q["row"]]["future"][axis]) for q in group
            )
            for axis in (0, 1)
        ]
    secants = [q for q in queries if q["kind"] == "secant"]
    signs = [
        (b["future"][0] - a["future"][0]) * rows[a["row"]]["audit"]["future_gain"] > 0
        for a, b in zip(secants[::2], secants[1::2], strict=True)
    ]
    full = (
        len(queries) == 160 + 4 * len(by_gain)
        and len(forecasts) == 128
        and len(signs) == 16
    )
    qualified = full and all(q["qualified"] for q in queries)
    return {
        "update_attempts": update,
        "admissions": admissions,
        "presentations": admissions * 16,
        "passed": qualified
        and refusals == 0
        and all(v <= 0.03 for pair in by_gain.values() for v in pair)
        and sum(signs) / 16 >= 0.95,
        "complete": full,
        "all_queries_qualified": qualified,
        "per_gain_future_mae": by_gain,
        "correct_response_signs": sum(signs),
        "response_sign_queries": len(signs),
        "forecast_past_residual_rms": rms(
            v for q in forecasts for v in q["past_errors"]
        ),
        "all_training_qualified": refusals == 0,
        "replacement_coefficients": coefficients,
    }


def replay_queries(brain, rows, queries):
    before = brain.snapshot()
    work = Counter()
    for query in queries:
        row = rows[query["row"]]
        inputs = copy.deepcopy(row["inputs"])
        targets = {"past": row["past"]}
        if query["kind"] == "secant":
            inputs["present"][1] = query["candidate"]
        elif query["kind"] == "full_clamp_diagnostic":
            targets["future"] = row["future"]
        result = brain.settle(inputs, targets=targets)
        require(brain.snapshot() == before, "fresh query mutated checkpoint")
        for key in (
            "qualified",
            "stationarity",
            "reason",
            "work",
            "sweeps",
            "state",
            "errors",
        ):
            same(result[key], query[key], f"fresh query {key} differs")
        same(result["outputs"]["future"], query["future"], "fresh free future differs")
        work.update(result["work"])
    return dict(work)


def verify_arm(root, spec, arm, rows, schedule, founder, maximum, replay):
    folder = root / "results" / spec["id"] / arm
    if not folder.exists():
        return {"arm": arm, "status": "missing", "gates": []}
    report = read(folder / "report.json") if (folder / "report.json").exists() else None
    lines = (
        (folder / "calls.jsonl").read_text().splitlines()
        if (folder / "calls.jsonl").exists()
        else []
    )
    calls, partial_tail = [], False
    for i, line in enumerate(lines):
        try:
            calls.append(json.loads(line))
        except ValueError:
            require(
                report is None and i == len(lines) - 1, "malformed completed ledger"
            )
            partial_tail = True
    plan = call_plan(rows, schedule, maximum)
    require(len(calls) <= len(plan), "excess ledger calls")
    before, accepted, attempts, refusals = common.text_sha(founder), 0, 0, 0
    work, statuses = Counter(), Counter()
    custody = {-1: (before, 0, 0)}
    for i, c in enumerate(calls):
        require(
            c["ordinal"] == i and c["before_sha256"] == before, "ledger custody/ordinal"
        )
        same({k: c[k] for k in plan[i]}, plan[i], "causal call plan")
        require(
            i == len(calls) - 1 or c["status"] == "returned",
            "continued after failed call",
        )
        require(math.isfinite(c["seconds"]) and c["seconds"] >= 0, "call duration")
        training = c["kind"] == "admission"
        attempts += training
        statuses[c["status"]] += 1
        if c["status"] != "returned":
            require(
                c["status"] in ("error", "interrupted")
                and c["unknown_work"] is True
                and "work" not in c,
                "unknown failed work",
            )
            require(c["after_sha256"] == before, "failed call rollback")
        else:
            require(
                type(c["qualified"]) is bool
                and math.isfinite(c["stationarity"])
                and c["stationarity"] >= 0
                and c["qualified"] == (c["stationarity"] <= 1e-6),
                "qualification",
            )
            require(
                all(type(v) is int and v >= 0 for v in c["work"].values()),
                "work counters",
            )
            work.update(c["work"])
            refusals += not c["qualified"]
            if training:
                require(
                    c["source"] == "witness"
                    and c["accepted"] is c["qualified"]
                    and c["event_id"] == accepted
                    and c["batch_size"] == 16,
                    "admission provenance/ID/count",
                )
                accepted += c["accepted"]
            else:
                row = rows[c["row"]]
                same(c["state"][2:4], row["past"], "known-past clamp")
                same(c["future"], c["state"][-2:], "future output is settled head")
                same(c["past_errors"], c["errors"][2:4], "past residual readback")
                if c["kind"] == "full_clamp_diagnostic":
                    same(c["future"], row["future"], "diagnostic witness clamp")
            if not training or not c["qualified"]:
                require(c["after_sha256"] == before, "pure query/refusal mutation")
        before = c["after_sha256"]
        custody[i] = before, accepted, refusals
    inflight = (
        read(folder / "inflight.json") if (folder / "inflight.json").exists() else None
    )
    if inflight:
        i = inflight["ordinal"]
        require(
            i in (len(calls), len(calls) - 1) and 0 <= i < len(plan), "inflight ordinal"
        )
        same({k: inflight[k] for k in plan[i]}, plan[i], "inflight call plan")
        require(inflight["before_sha256"] == custody[i - 1][0], "inflight custody")
        attempts += int(i == len(calls) and inflight["kind"] == "admission")
    snapshots = {}
    paths = sorted(folder.glob("checkpoint-*.json"))
    if (folder / "latest.json").exists():
        paths.append(folder / "latest.json")
    for path in paths:
        checkpoint = read(path)
        require(checkpoint["call"] in custody, "checkpoint outside ledger")
        digest, admissions, _ = custody[checkpoint["call"]]
        require(
            checkpoint["brain_sha256"]
            == common.text_sha(checkpoint["brain"])
            == digest,
            "checkpoint digest/custody",
        )
        brain = Brain.from_snapshot(checkpoint["brain"])
        require(
            brain.snapshot() == checkpoint["brain"]
            and brain.inspect()["admissions"] == checkpoint["admissions"] == admissions,
            "checkpoint reload/admissions",
        )
        require(
            checkpoint["presentations"] == 16 * admissions,
            "checkpoint admitted presentations",
        )
        snapshots[path.name] = (checkpoint, brain)
    gates, replay_count, replay_work = [], 0, Counter()
    for update in MILESTONES:
        path = folder / f"gate-{update}.json"
        if not path.exists():
            gates.append(
                {"update_attempts": update, "status": "missing", "passed": False}
            )
            continue
        payload = read(path)
        queries = [
            copy.deepcopy(c)
            for c in calls
            if c["kind"] != "admission" and c["update"] == update
        ]
        require(
            len(queries) == len(query_plan(rows, update))
            and all(q["status"] == "returned" for q in queries),
            "incomplete gate saved as complete",
        )
        for q in queries:
            if q["kind"] == "forecast":
                q["absolute_error"] = [
                    abs(p - y)
                    for p, y in zip(q["future"], rows[q["row"]]["future"], strict=True)
                ]
        same(
            payload["queries"],
            queries,
            "gate differs from actual ledger queries/outcomes",
        )
        checkpoint, brain = snapshots[f"checkpoint-{update}.json"]
        require(
            checkpoint["call"] == queries[0]["ordinal"] - 1,
            "gate uses wrong checkpoint",
        )
        require(
            checkpoint["brain_sha256"] == queries[0]["before_sha256"],
            "gate checkpoint changed",
        )
        special = [
            i
            for i, (kind, source, target) in enumerate(brain.graph.edges)
            if target in range(4, 6 if spec["layout"] == "small" else 8)
            and (
                (arm == "ordinary" and kind == "state" and source in (0, 1))
                or (arm == "observer" and kind == "residual" and source in (2, 3))
            )
        ]
        _, n_admissions, n_refusals = custody[queries[-1]["ordinal"]]
        score = independent_score(
            queries,
            rows,
            update,
            n_admissions,
            n_refusals,
            [brain.weights[i] for i in special],
        )
        same(payload["score"], score, "gate promotion/metric mismatch")
        if replay:
            replay_work.update(replay_queries(brain, rows, queries))
            replay_count += len(queries)
        gates.append({"status": "complete", **score})
    if report:
        same(report["spec"], spec, "arm spec")
        require(
            report["arm"] == arm and report["sources_unchanged"] is True,
            "arm identity/source",
        )
        for key, path in (
            ("protocol_sha256", root / "protocol.json"),
            ("ledger_sha256", folder / "calls.jsonl"),
            ("latest_sha256", folder / "latest.json"),
        ):
            require(report[key] == sha(path), f"report {key}")
        counters = {
            "calls": len(calls),
            "admissions": accepted,
            "presentations": accepted * 16,
            "admitted_presentations": accepted * 16,
            "attempted_updates": attempts,
            "attempted_presentations": attempts * 16,
            "refusals": refusals,
            "interrupted_calls": statuses["interrupted"],
            "errored_calls": statuses["error"],
            "unknown_work_calls": statuses["interrupted"] + statuses["error"],
        }
        for key, value in counters.items():
            require(report[key] == value, f"reported {key} differs")
        same(report["work"], dict(work), "reported work differs")
        same(
            report["gates"],
            [
                {k: v for k, v in g.items() if k != "status"}
                for g in gates
                if g["status"] == "complete"
            ],
            "gate report inventory",
        )
        require(
            {c["file"] for c in report["checkpoints"]}
            == {p.name for p in paths if p.name != "latest.json"},
            "checkpoint inventory",
        )
        for entry in report["checkpoints"]:
            require(
                sha(folder / entry["file"]) == entry["sha256"], "checkpoint file hash"
            )
        require(
            snapshots["latest.json"][0]["brain_sha256"] == before,
            "latest accepted state missing",
        )
        status = report["status"]
        require(status in ("complete", "censored", "error"), "arm status")
        if status == "complete":
            require(
                len(calls) == len(plan)
                and not inflight
                and statuses["error"] + statuses["interrupted"] == 0,
                "incomplete arm claimed complete",
            )
    else:
        status = "incomplete"
    return {
        "arm": arm,
        "status": status,
        "calls": len(calls),
        "admissions": accepted,
        "attempted_presentations": attempts * 16,
        "admitted_presentations": accepted * 16,
        "refusals": refusals,
        "unknown_work_calls": statuses["error"] + statuses["interrupted"],
        "unlogged_inflight_work_unknown": bool(
            inflight and inflight["ordinal"] == len(calls)
        ),
        "partial_ledger_tail": partial_tail,
        "work": dict(work),
        "gates": gates,
        "checkpoints_reloaded": len(snapshots),
        "replayed_queries": replay_count,
        "replay_work": dict(replay_work),
    }


def choose(cases):
    options = []
    for case in cases:
        spec = case["spec"]
        if (
            spec["role"] != "development"
            or spec["condition"] != "balanced_mixed"
            or case["verification"] != "verified"
        ):
            continue
        if (
            case.get("case_status") != "complete"
            or not case.get("execution")
            or case["execution"]["returncode"] != 0
        ):
            continue
        if any(a["status"] != "complete" or a["refusals"] for a in case["arms"]):
            continue
        for update in MILESTONES:
            if all(
                any(
                    g["update_attempts"] == update
                    and g["status"] == "complete"
                    and g["passed"]
                    for g in a["gates"]
                )
                for a in case["arms"]
            ):
                options.append(
                    (
                        spec["parameters"],
                        update,
                        0 if spec["parameter_prior"] == 0.1 else 1,
                        spec,
                    )
                )
    if not options:
        return None
    _, update, _, spec = min(options, key=lambda option: option[:3])
    return {
        "layout": spec["layout"],
        "parameter_prior": spec["parameter_prior"],
        "updates": update,
        "selection_seed": 2,
        "confirmation_seeds": [7, 11, 19, 29],
    }


def verify_campaign(root, replay=True):
    started = time.perf_counter()
    protocol, tapes, schedules, founders = frozen_artifacts(root)
    cases, original_reports = [], {}
    pilot = [s for s in protocol["cases"] if s["role"] == "development"]
    for spec in pilot:
        try:
            arms = [
                verify_arm(
                    root,
                    spec,
                    a,
                    tapes[spec["condition"]][spec["role"]],
                    schedules[spec["condition"]],
                    founders[(spec["id"], a)],
                    512,
                    replay,
                )
                for a in ARMS
            ]
            path = root / "results" / spec["id"] / "report.json"
            if path.exists():
                report = read(path)
                original_reports[spec["id"]] = report
                same(report["spec"], spec, "case spec")
                same(
                    report["arms"],
                    [read(path.parent / a / "report.json") for a in spec["arm_order"]],
                    "embedded arm report",
                )
                require(
                    report["status"]
                    == (
                        "complete"
                        if all(a["status"] == "complete" for a in arms)
                        else "incomplete"
                    ),
                    "case status",
                )
            execution_path = root / f"execution-{spec['id']}.json"
            execution = read(execution_path) if execution_path.exists() else None
            if execution:
                same(execution["spec"], spec, "execution spec")
                require(execution["case_seconds_cap"] == 120, "case time cap")
                if execution["returncode"] == 0:
                    require(
                        path.exists() and all(a["status"] == "complete" for a in arms),
                        "successful exit without completed case",
                    )
            cases.append(
                {
                    "spec": spec,
                    "verification": "verified",
                    "arms": arms,
                    "execution": execution,
                    "case_status": original_reports.get(spec["id"], {}).get(
                        "status", "missing"
                    ),
                }
            )
        except (ValueError, KeyError, TypeError, IndexError, OSError) as error:
            cases.append(
                {"spec": spec, "verification": "invalid", "reason": str(error)}
            )
    selection = choose(cases)
    summary_ok, summary_error = None, None
    if (root / "pilot-summary.json").exists():
        try:
            summary = read(root / "pilot-summary.json")
            require(
                summary["protocol_sha256"] == sha(root / "protocol.json"),
                "summary protocol hash",
            )
            same(
                summary["selected"],
                selection,
                "selection promoted incomplete/unqualified pair",
            )
            same(
                summary["execution"],
                [read(root / f"execution-{s['id']}.json") for s in pilot],
                "execution inventory",
            )
            same(
                summary["case_reports"],
                [
                    {
                        "id": s["id"],
                        "status": original_reports[s["id"]]["status"],
                        "sha256": sha(root / "results" / s["id"] / "report.json"),
                    }
                    for s in pilot
                    if s["id"] in original_reports
                ],
                "case report inventory",
            )
            require(
                summary["automatic_confirmation_launched"] is False,
                "undeclared confirmation launch",
            )
            summary_ok = True
        except (ValueError, KeyError, OSError) as error:
            summary_ok, summary_error = False, str(error)
    valid = (
        all(c["verification"] == "verified" for c in cases) and summary_ok is not False
    )
    return {
        "schema": "cadence-acquisition-verification/1",
        "valid": valid,
        "protocol_sha256": sha(root / "protocol.json"),
        "verifier_sha256": sha(Path(__file__)),
        "shared_verifier_helpers_sha256": sha(Path(common.__file__)),
        "pilot_cases_expected": 12,
        "cases": cases,
        "selected": selection,
        "summary_verified": summary_ok,
        "summary_error": summary_error,
        "fresh_query_replay": replay,
        "elapsed_seconds": time.perf_counter() - started,
        "replayed_queries": sum(
            a.get("replayed_queries", 0)
            for c in cases
            if c["verification"] == "verified"
            for a in c["arms"]
        ),
        "limits": "Acquisition screen only; seed2 selects, not independent confirmation. Fresh queries are verification work, not training exposure. Numerical learning updates are not replayed. Missing/censored arms remain unselected.",
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
                    "selected",
                    "pilot_cases_expected",
                    "replayed_queries",
                    "summary_verified",
                )
            },
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
