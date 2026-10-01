"""Frozen conservative work comparison; no training before protocol review.

Observer mixed32 is fixed. Ordinary gets at least that training work, in whole
admissions, and its original mixed32 checkpoint remains a second comparator.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import platform
import random
import signal
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

import shared_innovation as base

from cadence import Brain

custody = base.custody
SEEDS = (83, 89, 97, 101, 103)
DATA_SEED = 20261007
CAP = 40
BATCH = 16
CHECKS = (0, 32, 128)


def sources():
    return {
        **base.sources(),
        str(Path(__file__).resolve()): custody.sha(Path(__file__)),
    }


def tape():
    rng = random.Random(DATA_SEED)

    def row(identity, delta=0.0):
        return base.body(
            rng.uniform(-0.2, 0.2), rng.uniform(-0.4, 0.4), delta, identity
        )

    clean = [row(f"clean:{i}") for i in range(64 * BATCH)]
    mixed = []
    for i in range(128 * 8):
        delta = rng.uniform(0.03, 0.12)
        positive = row(f"mixed:{2 * i}", delta)
        u, v = positive["inputs"]["u"][0], positive["inputs"]["v"][0]
        mixed.extend((positive, base.body(u, v, -delta, f"mixed:{2 * i + 1}")))
    return {
        "clean": clean,
        "mixed": mixed,
        "clean_test": [row(f"clean-test:{i}") for i in range(32)],
        "mixed_test": [
            row(f"mixed-test:{i}", rng.choice((-1, 1)) * rng.uniform(0.03, 0.12))
            for i in range(64)
        ],
    }


def freeze(root):
    root.mkdir(parents=True, exist_ok=False)
    custody.atomic(root / "data.json", tape())
    custody.atomic(root / "founders.json", {str(s): base.founders(s) for s in SEEDS})
    custody.atomic(
        root / "protocol.json",
        {
            "schema": "work-matched-innovation/1",
            "sources": sources(),
            "data_sha256": custody.sha(root / "data.json"),
            "founders_sha256": custody.sha(root / "founders.json"),
            "seeds": SEEDS,
            "data_seed": DATA_SEED,
            "condition": "narrow",
            "arms": base.ARMS,
            "patches": 3,
            "parameters": 9,
            "training": {
                "clean_updates": 64,
                "mixed_updates": 128,
                "batch_size": BATCH,
            },
            "primary": "Observer mixed32 versus BOTH ordinary mixed32 and ordinary first training-work crossing. Each separate comparison requires mean ordinary-minus-observer heldout free-H MAE>=0.005 and improvement in all5 paired seeds. No checkpoint chosen by accuracy; no eligible-only subset. Earlier threshold failures and late reversal remain unchanged.",
            "work_matching": "Target is observer cumulative returned clean+mixed training edge_visits through mixed32, including every attempt. Ordinary takes the same ordered tape until its FIRST whole admission at mixed32..48 with cumulative training edge_visits>=target. Include and report overshoot. If no crossing by48 or observer lacks a source-valid32 target, comparison is censored; both arms still continue to128 where possible. This is conservative training-work dominance, NOT exact equal compute or latency.",
            "eligibility": "All10 arms complete all192 accepted admissions; every solve qualifies, no unknown work or source drift. Clean P and H BOTH free MAE<=0.03 at0,32,128 and ordinary crossing if distinct. Every declared correction endpoint has all64 qualified heldout rows. Missing crossing or failure vetoes comparison.",
            "continuation": "Always retain/check mixed0,32,128; ordinary adds its first crossing only if different from32. Continue each live parameter trajectory to128 with no reset or model selection. Show late crossover for every seed even when primary passes.",
            "compute": {
                "arm_seconds": CAP,
                "outer_seconds": CAP + 5,
                "max_workers": 3,
                "backend": "python",
                "dtype": "float64",
            },
            "resource_boundary": "Training edge visits define the declared primary resource. All returned training attempts, including refusals, count. Inference work and call CPU/wall seconds are separately retained; they are not omitted or exchanged for training work. Interrupted work is unknown and vetoes a complete comparison. No end-to-end efficiency claim follows from training edge visits alone.",
            "scope": "Same public patch law and exact initial9parameter mapping; ordinary already has energy backreaction. One fresh shared environment tape across five initialization seeds, not five independent environments. No input-only ablation, latent clamping, temporal-memory or planning claim in this experiment.",
            "runtime": {"platform": platform.platform(), "python": sys.version},
        },
    )


def validate(root):
    p = custody.read(root / "protocol.json")
    assert p["sources"] == sources()
    assert p["data_sha256"] == custody.sha(root / "data.json")
    assert p["founders_sha256"] == custody.sha(root / "founders.json")
    return p


def crossing(update, work, target):
    return target is not None and 32 <= update <= 48 and work >= target


def observer_target(root, seed):
    folder = root / f"observer-seed{seed}"
    path = folder / "work-target.json"
    if not path.exists():
        return None
    target = custody.read(path)
    assert target["seed"] == seed and target["mixed_update"] == 32
    assert target["protocol_sha256"] == custody.sha(root / "protocol.json")
    snapshot = (folder / "checkpoint-mixed32.json").read_text()
    assert custody.digest(snapshot) == target["checkpoint_sha256"]
    assert Brain.from_snapshot(snapshot).inspect()["admissions"] == 96
    updates = custody.read(folder / "updates.json")[:96]
    assert len(updates) == 96 and all(r["accepted"] for r in updates)
    assert [r["event_id"] for r in updates] == list(range(96))
    assert (
        sum(r["work"]["edge_visits"] for r in updates) == target["training_edge_visits"]
    )
    return target


def run(root, seed, arm):
    protocol = validate(root)
    out = root / f"{arm}-seed{seed}"
    out.mkdir(exist_ok=False)
    model = Brain.from_snapshot(custody.read(root / "founders.json")[str(seed)][arm])
    data = custody.read(root / "data.json")
    target = observer_target(root, seed) if arm == "ordinary" else None
    custody.atomic(out / "target-input.json", target)
    started, last_good = time.monotonic(), model.snapshot()
    updates, queries = [], []
    training_work, query_work = Counter(), Counter()
    checks, match = {}, None
    status, failure, unknown_work = "complete", None, False
    admission_counts = {"started": 0, "returned": 0, "accepted": 0, "refused": 0}

    def alarm(*_):
        raise TimeoutError("arm deadline")

    old_alarm = signal.signal(signal.SIGALRM, alarm)

    def solve(call, intent):
        nonlocal model, last_good, unknown_work
        before = model.snapshot()
        intent = {
            **intent,
            "status": "started",
            "before_sha256": custody.digest(before),
        }
        custody.atomic(out / "current-call.json", intent)
        remaining = CAP - (time.monotonic() - started)
        if remaining <= 0:
            custody.atomic(
                out / "current-call.json",
                {**intent, "status": "not_started_deadline", "work": {}},
            )
            raise TimeoutError("arm deadline before solve")
        wall, cpu = time.perf_counter(), time.process_time()
        if intent["kind"] == "admission":
            admission_counts["started"] += 1
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            result = call()
        except Exception as exc:
            signal.setitimer(signal.ITIMER_REAL, 0)
            unknown_work = True
            model = Brain.from_snapshot(before)
            custody.atomic(
                out / "current-call.json",
                {
                    **intent,
                    "status": "interrupted",
                    "unknown_work": True,
                    "wall_seconds": time.perf_counter() - wall,
                    "cpu_seconds": time.process_time() - cpu,
                    "failure": repr(exc),
                    "restored_sha256": custody.digest(model.snapshot()),
                },
            )
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        last_good = model.snapshot()
        (training_work if intent["kind"] == "admission" else query_work).update(
            result["work"]
        )
        if intent["kind"] == "admission":
            admission_counts["returned"] += 1
            admission_counts["accepted" if result["accepted"] else "refused"] += 1
        receipt = {
            **intent,
            "status": "returned",
            "qualified": result["qualified"],
            "accepted": result.get("accepted"),
            "reason": result["reason"],
            "stationarity": result["stationarity"],
            "work": result["work"],
            "sweeps": result["sweeps"],
            "wall_seconds": time.perf_counter() - wall,
            "cpu_seconds": time.process_time() - cpu,
            "after_sha256": custody.digest(last_good),
        }
        with (out / "calls.jsonl").open("a") as stream:
            stream.write(custody.encoded(receipt) + "\n")
        custody.atomic(out / "current-call.json", receipt)
        custody.atomic(out / "last-completed.json", last_good)
        return result, receipt

    def check(update):
        label = f"mixed{update}"
        if label in checks:
            return
        snapshot = model.snapshot()
        (out / f"checkpoint-{label}.json").write_text(snapshot)
        checks[label] = {
            "snapshot_sha256": custody.digest(snapshot),
            "training_work": dict(training_work),
        }
        custody.atomic(out / "checks.json", checks)
        for kind, rows, observed in (
            ("clean-free", data["clean_test"], False),
            ("correction", data["mixed_test"], True),
        ):
            for row in rows:
                inputs, targets = base.query(row, observed)
                r, receipt = solve(
                    lambda inputs=inputs, targets=targets: model.settle(
                        inputs, targets=targets
                    ),
                    {"kind": "query", "check": label, "group": kind, "row": row["id"]},
                )
                assert model.snapshot() == snapshot
                queries.append(
                    {
                        **receipt,
                        "outputs": r["outputs"],
                        "state": r["state"],
                        "errors": r["errors"],
                        "predictions": r["predictions"],
                        "past_absolute_error": abs(
                            r["outputs"]["past"][0] - row["actual_x"][0]
                        ),
                        "future_absolute_error": abs(
                            r["outputs"]["future"][0] - row["actual_y"][0]
                        ),
                    }
                )
                if not r["qualified"]:
                    raise RuntimeError("Query refused; diagnostic retained")
        custody.atomic(out / "queries.json", queries)

    def summaries():
        labels = [f"mixed{n}" for n in CHECKS]
        if match is not None and f"mixed{match}" not in labels:
            labels.append(f"mixed{match}")
        groups = []
        for label in labels:
            for kind, expected in (("clean-free", 32), ("correction", 64)):
                rows = [
                    r for r in queries if r["check"] == label and r["group"] == kind
                ]
                good = [r for r in rows if r["qualified"]]
                mae = {
                    head: sum(r[f"{head}_absolute_error"] for r in good) / len(good)
                    if good
                    else None
                    for head in ("past", "future")
                }
                groups.append(
                    {
                        "check": label,
                        "group": kind,
                        "expected": expected,
                        "completed": len(rows),
                        "qualified": len(good),
                        "qualified_only_mae": mae,
                        "clean_gate": len(good) == expected
                        and all(v is not None and v <= 0.03 for v in mae.values())
                        if kind == "clean-free"
                        else None,
                    }
                )
        return groups

    try:
        for phase, count in (("clean", 64), ("mixed", 128)):
            for update in range(1, count + 1):
                rows = data[phase][BATCH * (update - 1) : BATCH * update]
                event_id = update - 1 if phase == "clean" else 63 + update
                r, receipt = solve(
                    lambda rows=rows, event_id=event_id: model.observe_batch(
                        [base.witness(row) for row in rows],
                        event_id=event_id,
                        source="witness",
                    ),
                    {
                        "kind": "admission",
                        "phase": phase,
                        "update": update,
                        "event_id": event_id,
                        "rows": [row["id"] for row in rows],
                    },
                )
                updates.append(
                    {
                        **receipt,
                        "event_id": r["event_id"],
                        "source": r["source"],
                        "batch_size": r["batch_size"],
                    }
                )
                custody.atomic(out / "updates.json", updates)
                if not r["accepted"] or not r["qualified"]:
                    raise RuntimeError("Admission refused; actual work retained")
                if phase != "mixed":
                    continue
                if arm == "observer" and update == 32:
                    # Freeze work and exact model before looking at endpoint errors.
                    (out / "checkpoint-mixed32.json").write_text(model.snapshot())
                    custody.atomic(
                        out / "work-target.json",
                        {
                            "seed": seed,
                            "mixed_update": 32,
                            "training_edge_visits": training_work["edge_visits"],
                            "training_work": dict(training_work),
                            "checkpoint_sha256": custody.digest(model.snapshot()),
                            "protocol_sha256": custody.sha(root / "protocol.json"),
                        },
                    )
                if (
                    arm == "ordinary"
                    and match is None
                    and crossing(
                        update,
                        training_work["edge_visits"],
                        target["training_edge_visits"] if target is not None else None,
                    )
                ):
                    match = update
                    custody.atomic(
                        out / "crossing.json",
                        {
                            "mixed_update": update,
                            "training_work": dict(training_work),
                            "target_edge_visits": target["training_edge_visits"],
                            "overshoot_edge_visits": training_work["edge_visits"]
                            - target["training_edge_visits"],
                            "checkpoint_sha256": custody.digest(model.snapshot()),
                        },
                    )
                    check(update)
                if update in CHECKS:
                    check(update)
            if phase == "clean":
                check(0)
        if time.monotonic() - started > CAP:
            raise TimeoutError("arm deadline during bookkeeping")
    except TimeoutError as exc:
        status, failure = "timeout", str(exc)
    except Exception:  # noqa: BLE001 - Keep every failed experimental arm.
        status, failure = "error", traceback.format_exc()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_alarm)
        custody.atomic(out / "updates.json", updates)
        custody.atomic(out / "queries.json", queries)
        custody.atomic(out / "checks.json", checks)
        custody.atomic(out / "last-completed.json", last_good)
        groups = summaries()
        unchanged = sources() == protocol["sources"]
        journal = out / "calls.jsonl"
        journal_manifest = (
            {"bytes": journal.stat().st_size, "sha256": custody.sha(journal)}
            if journal.exists()
            else None
        )
        if time.monotonic() - started > CAP:
            status, failure = "timeout", failure or "deadline during final bookkeeping"
        if not unchanged:
            status, failure = "error", "Frozen source changed"
        eligible = (
            status == "complete"
            and admission_counts["accepted"] == 192
            and not unknown_work
            and all(g["completed"] == g["qualified"] == g["expected"] for g in groups)
            and all(g["clean_gate"] for g in groups if g["group"] == "clean-free")
            and (arm == "observer" or match is not None)
        )
        custody.atomic(
            out / "result.json",
            {
                "seed": seed,
                "arm": arm,
                "status": status,
                "failure": failure,
                "eligible": eligible,
                "seconds": time.monotonic() - started,
                "admission_counts": admission_counts,
                "unknown_work": unknown_work,
                "ordinary_crossing": match,
                "target_missing": arm == "ordinary" and target is None,
                "training_work": dict(training_work),
                "inference_work": dict(query_work),
                "groups": groups,
                "sources_unchanged": unchanged,
                "protocol_sha256": custody.sha(root / "protocol.json"),
                "checkpoint_sha256": custody.digest(last_good),
                "journal": journal_manifest,
            },
        )
    return 0 if status == "complete" else 1


def comparison(root):
    execution_path = root / "execution.json"
    execution = custody.read(execution_path) if execution_path.exists() else []
    expected = {(seed, arm) for seed in SEEDS for arm in base.ARMS}
    executions = {(r["seed"], r["arm"]): r for r in execution}
    execution_complete = len(execution) == len(expected) and set(executions) == expected
    rows, eligible = [], True
    for seed in SEEDS:
        reports = {}
        for arm in base.ARMS:
            path = root / f"{arm}-seed{seed}" / "result.json"
            reports[arm] = custody.read(path) if path.exists() else None
        good = execution_complete and all(
            reports[arm] is not None
            and reports[arm]["eligible"]
            and executions[(seed, arm)]["status"] == "returned"
            and executions[(seed, arm)]["code"] == 0
            for arm in base.ARMS
        )
        eligible &= good
        row = {"seed": seed, "eligible": good}

        def metric(arm, update, reports=reports):
            report = reports[arm]
            return (
                next(
                    (
                        g["qualified_only_mae"]["future"]
                        for g in report["groups"]
                        if g["check"] == f"mixed{update}" and g["group"] == "correction"
                    ),
                    None,
                )
                if report
                else None
            )

        matched = (
            reports["ordinary"]["ordinary_crossing"] if reports["ordinary"] else None
        )
        row.update(
            observer32=metric("observer", 32),
            ordinary32=metric("ordinary", 32),
            ordinary_crossing=matched,
            ordinary_matched=metric("ordinary", matched),
            observer128=metric("observer", 128),
            ordinary128=metric("ordinary", 128),
        )
        rows.append(row)
    reductions = {
        key: sum(r[key] - r["observer32"] for r in rows) / len(SEEDS)
        if eligible
        else None
        for key in ("ordinary32", "ordinary_matched")
    }
    passed = eligible and all(
        reductions[key] >= 0.005 and all(r[key] > r["observer32"] for r in rows)
        for key in reductions
    )
    return {
        "execution_complete": execution_complete,
        "all_pairs_eligible": eligible,
        "primary_pass": bool(passed),
        "rows": rows,
        "mean_mae_reductions": reductions,
        "scope": "Conservative training-edge-visit comparison; query work and latency remain separate. Same-exposure and late endpoints retained; no temporal or planning claim.",
    }


def launch(root):
    validate(root)
    if (root / "launch.json").exists():
        raise ValueError("Preserve the prior launch")
    custody.atomic(
        root / "launch.json",
        {
            "seeds": SEEDS,
            "arm_order": ["observer", "ordinary"],
            "max_workers": 3,
            "outer_seconds_per_arm": CAP + 5,
        },
    )

    def execute_pair(seed):
        receipts = []
        for arm in ("observer", "ordinary"):
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "run",
                str(root),
                "--seed",
                str(seed),
                "--arm",
                arm,
            ]
            with (root / f"{arm}-seed{seed}.log").open("x") as log:
                p = subprocess.Popen(
                    command,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    code, status = p.wait(timeout=CAP + 5), "returned"
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    code, status = p.wait(), "outer_timeout"
            receipts.append(
                {"seed": seed, "arm": arm, "pid": p.pid, "code": code, "status": status}
            )
        return receipts

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        receipts = list(pool.map(execute_pair, SEEDS))
    custody.atomic(root / "execution.json", [r for pair in receipts for r in pair])
    custody.atomic(root / "comparison.json", comparison(root))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "launch"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--seed", type=int, choices=SEEDS)
    parser.add_argument("--arm", choices=base.ARMS)
    args = parser.parse_args()
    if args.command == "run" and None in (args.seed, args.arm):
        parser.error("run requires --seed and --arm")
    if args.command == "freeze":
        freeze(args.root.resolve())
    elif args.command == "launch":
        launch(args.root.resolve())
    else:
        sys.exit(run(args.root.resolve(), args.seed, args.arm))
