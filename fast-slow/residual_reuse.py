"""Matched residual-reuse mechanism experiment; freeze before any training.

Usage: residual_reuse.py freeze ROOT; residual_reuse.py launch ROOT.
The launch uses at most three processes; each arm has a 40-second deadline.
This is conditional prediction, not temporal memory or autonomous control.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import math
import os
import platform
import random
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

import self_correction as custody

import cadence
from cadence import Brain, Cortex

SEEDS = (107, 109, 113, 127, 131)
ARMS = ("ordinary", "observer")
LAYOUTS = {"input_only": 6, "coupled": 9}
DATA_SEED = 20261008
CAP = 40


def sources():
    package = Path(cadence.__file__).resolve().parent
    paths = [*package.rglob("*.py"), Path(__file__), Path(custody.__file__)]
    return {str(p.resolve()): custody.sha(p) for p in sorted(paths)}


def body(u, v, delta, identity):
    # Both targets belong to the body, independently of any model residual.
    return {
        "id": identity,
        "inputs": {"u": [u], "v": [v]},
        "actual_x": [math.tanh(u) + delta],
        "actual_y": [math.tanh(v + delta)],
        "delta": delta,
    }


def tape():
    rng = random.Random(DATA_SEED)

    def row(identity, delta=0.0):
        return body(rng.uniform(-1.2, 1.2), rng.uniform(-0.4, 0.4), delta, identity)

    clean = [row(f"clean:{i}") for i in range(64 * 16)]
    mixed = []
    for i in range(128 * 8):
        delta = rng.uniform(0.03, 0.12)
        positive = row(f"mixed:{2 * i}", delta)
        u, v = positive["inputs"]["u"][0], positive["inputs"]["v"][0]
        mixed.extend([positive, body(u, v, -delta, f"mixed:{2 * i + 1}")])
    clean_test = [row(f"clean-test:{i}") for i in range(32)]
    mixed_test = []
    for i in range(32):
        delta = rng.uniform(0.03, 0.12)
        positive = row(f"mixed-test:{2 * i}", delta)
        u, v = positive["inputs"]["u"][0], positive["inputs"]["v"][0]
        mixed_test.extend([positive, body(u, v, -delta, f"mixed-test:{2 * i + 1}")])
    return {
        "clean": clean,
        "mixed": mixed,
        "clean_test": clean_test,
        "mixed_test": mixed_test,
    }


def query(record, observed=True):
    return record["inputs"], {"past": record["actual_x"]} if observed else None


def witness(record):
    return record["inputs"], {"past": record["actual_x"], "future": record["actual_y"]}


def brain(seed, layout, arm):
    if layout not in LAYOUTS or arm not in ARMS:
        raise ValueError("Unknown layout or arm")
    c = Cortex(
        seed=seed,
        state_prior=0.01,
        parameter_prior=0.1,
        tolerance=1e-6,
        settle_budget=2048,
        device="python",
        dtype="float64",
    )
    u, v = c.input("u", shape=1), c.input("v", shape=1)
    m = c.column("M", patches=1, inputs=u) if layout == "coupled" else None
    p = c.column("P", patches=1, inputs=(u, m) if m is not None else u)
    h = (
        c.observer("H", patches=1, inputs=(v, p), observes=p)
        if arm == "observer"
        else c.column("H", patches=1, inputs=(v, p, m if m is not None else u))
    )
    c.output("past", shape=1, reads=p)
    c.output("future", shape=1, reads=h)
    model = c.build()
    assert len(model.weights) + len(model.biases) == LAYOUTS[layout]
    return model


def founders(seed, layout):
    ordinary, observer = (brain(seed, layout, arm) for arm in ARMS)
    a = dict(zip(ordinary.graph.edges, ordinary.weights, strict=True))
    b = dict(zip(observer.graph.edges, observer.weights, strict=True))
    common = a.keys() & b.keys()
    p = ordinary.graph.n_patches - 2
    h = p + 1
    old = ("state", 0, h) if layout == "coupled" else ("input", 0, h)
    new = ("residual", p, h)
    assert len(common) == len(ordinary.weights) - 1
    assert all(a[k] == b[k] for k in common) and a[old] == b[new]
    assert ordinary.weights == observer.weights and ordinary.biases == observer.biases
    assert ordinary.state == observer.state
    return dict(zip(ARMS, (ordinary.snapshot(), observer.snapshot()), strict=True))


def jobs():
    return [
        (seed, layout, arm)
        for i, seed in enumerate(SEEDS)
        for layout in LAYOUTS
        for arm in (ARMS if i % 2 == 0 else ARMS[::-1])
    ]


def freeze(root):
    root.mkdir(parents=True, exist_ok=False)
    custody.atomic(root / "data.json", tape())
    custody.atomic(
        root / "founders.json",
        {
            layout: {str(seed): founders(seed, layout) for seed in SEEDS}
            for layout in LAYOUTS
        },
    )
    protocol = {
        "schema": "residual-reuse-mechanism/1",
        "sources": sources(),
        "data_sha256": custody.sha(root / "data.json"),
        "founders_sha256": custody.sha(root / "founders.json"),
        "seeds": SEEDS,
        "data_seed": DATA_SEED,
        "layouts": LAYOUTS,
        "arms": ARMS,
        "jobs": jobs(),
        "body": "x=tanh(u)+delta; later y=tanh(v+delta); u in[-1.2,1.2], v in[-.4,.4], antithetic delta in[.03,.12]. Body targets never depend on model residuals.",
        "graphs": {
            "input_only": "P<-u; ordinary H<-(v,P,u), observer H<-(v,P,eP). 2 patches,4weights,2biases,6 parameters.",
            "coupled": "M<-u; P<-(u,M); ordinary H<-(v,P,M), observer H<-(v,P,eP). 3 patches,6weights,3biases,9 parameters.",
        },
        "training": {
            "clean_updates": 64,
            "mixed_updates": 128,
            "batch_size": 16,
            "mixed_checks": [0, 32, 128],
        },
        "clean_gate": "All32 independent queries qualify with BOTH P and H FREE; both head MAE<=.03 at checks0,32,128. Every planned outcome remains; no gate-based subset selection.",
        "observed_query": "Only the actual body's P observation is clamped; H remains free. Neither delta nor future label enters the query arguments.",
        "primary": "Within EACH size, final mixed128 H MAE over all64 held-out rows and all5 seeds. All20 arms must complete, accept192 admissions, qualify every query, and pass all3 clean gates. A useful effect requires mean ordinary-minus-observer MAE>=.005 and positive improvement in all5 pairs. No selecting a better checkpoint or survivor subset.",
        "mechanism": "At input-only observed-P queries, P prediction and eP depend solely on fixed parameters/raw u/actual x, so no H feedback can change eP. A benefit there is learned residual representation reuse. Coupled graphs add a possible P-M-H return path; graph declaration or larger weights alone do not demonstrate useful use of that path. Cross-size comparisons are not matched capacity.",
        "diagnostic": "At each check, same-snapshot P-only and P+actual-future queries on the same64rows; teacher H never scores as a forecast. Record exact eP invariance for input-only and changes for coupled. Current eP is posterior model mismatch, not a stored historical forecast innovation.",
        "compute": {
            "arm_deadline_seconds": CAP,
            "outer_process_seconds": CAP + 5,
            "max_workers": 3,
            "backend": "python",
            "dtype": "float64",
        },
        "artifacts": "Bounded20-arm local pilot; estimated total<30MB. Retain every outcome and checkpoint; no training launches automatically from freeze.",
        "scope": "Same information and exact shared/replacement initialization within each size; all learning uses the same public coupled patch law. No independent optimizer, temporal memory, state-cycle or exclusive-recursion claim. Accuracy and work remain separate endpoints; no efficiency claim from equal update counts.",
        "platform": platform.platform(),
    }
    custody.atomic(root / "protocol.json", protocol)


def validate(root):
    p = custody.read(root / "protocol.json")
    assert sources() == p["sources"]
    assert custody.sha(root / "data.json") == p["data_sha256"]
    assert custody.sha(root / "founders.json") == p["founders_sha256"]
    return p


def run(root, seed, layout, arm):
    protocol = validate(root)
    out = root / f"{layout}-{arm}-seed{seed}"
    out.mkdir(exist_ok=False)
    model = Brain.from_snapshot(
        custody.read(root / "founders.json")[layout][str(seed)][arm]
    )
    data = custody.read(root / "data.json")
    started = time.monotonic()
    last_good = model.snapshot()
    ledger, evaluations = [], []
    diagnostics = []
    counts = {
        "started": 0,
        "returned": 0,
        "qualified": 0,
        "refused": 0,
        "interrupted_unknown_work": 0,
        "admissions_started": 0,
        "admissions_returned": 0,
        "admissions_accepted": 0,
    }
    status, failure = "complete", None

    def alarm(*_):
        raise TimeoutError("arm deadline")

    prior_alarm = signal.signal(signal.SIGALRM, alarm)

    def bounded(call, intent):
        nonlocal model, last_good
        before = model.snapshot()
        intent = {
            **intent,
            "before_sha256": custody.digest(before),
            "status": "started",
        }
        custody.atomic(out / "current-call.json", intent)
        tick = time.monotonic()
        remaining = CAP - (time.monotonic() - started)
        if remaining <= 0:
            custody.atomic(
                out / "current-call.json",
                {**intent, "status": "not_started_deadline", "seconds": 0, "work": {}},
            )
            raise TimeoutError("arm deadline")
        counts["started"] += 1
        counts["admissions_started"] += intent["kind"] == "admission"
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            result = call()
        except Exception as exc:
            signal.setitimer(signal.ITIMER_REAL, 0)
            counts["interrupted_unknown_work"] += 1
            model = Brain.from_snapshot(before)
            custody.atomic(
                out / "current-call.json",
                {
                    **intent,
                    "status": "interrupted",
                    "seconds": time.monotonic() - tick,
                    "unknown_work": True,
                    "failure": repr(exc),
                    "restored_sha256": custody.digest(model.snapshot()),
                },
            )
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        counts["returned"] += 1
        counts["qualified"] += result["qualified"]
        counts["refused"] += not result["qualified"]
        counts["admissions_returned"] += intent["kind"] == "admission"
        counts["admissions_accepted"] += (
            intent["kind"] == "admission" and result["accepted"]
        )
        last_good = model.snapshot()
        completed = {
            **intent,
            "status": "returned",
            "seconds": time.monotonic() - tick,
            "work": result["work"],
            "sweeps": result["sweeps"],
            "qualified": result["qualified"],
            "accepted": result.get("accepted"),
            "stationarity": result["stationarity"],
            "reason": result["reason"],
            "after_sha256": custody.digest(model.snapshot()),
        }
        with (out / "calls.jsonl").open("a") as journal:
            journal.write(custody.encoded(completed) + "\n")
        custody.atomic(out / "current-call.json", completed)
        custody.atomic(out / "last-completed.json", last_good)
        return result

    def evaluate(label, records, observed, *, teacher=False):
        before = model.snapshot()
        for row in records:
            inputs, targets = query(row, observed)
            if teacher:
                inputs, targets = witness(row)
            tick = time.perf_counter()
            r = bounded(
                lambda inputs=inputs, targets=targets: model.settle(
                    inputs, targets=targets
                ),
                {
                    "kind": "query",
                    "check": label,
                    "row": row["id"],
                    "teacher_clamped": teacher,
                },
            )
            elapsed = time.perf_counter() - tick
            assert model.snapshot() == before
            evaluations.append(
                {
                    "check": label,
                    "row": row["id"],
                    "observed": observed,
                    "teacher_clamped": teacher,
                    "qualified": r["qualified"],
                    "model_sha256": custody.digest(before),
                    "reason": r["reason"],
                    "seconds": elapsed,
                    "state": r["state"],
                    "errors": r["errors"],
                    "predictions": r["predictions"],
                    "stationarity": r["stationarity"],
                    "work": r["work"],
                    "sweeps": r["sweeps"],
                    "past_absolute_error": abs(
                        r["outputs"]["past"][0] - row["actual_x"][0]
                    ),
                    "future_absolute_error": None
                    if teacher
                    else abs(r["outputs"]["future"][0] - row["actual_y"][0]),
                    "delta": row["delta"],
                    "offset_bin": "small"
                    if abs(row["delta"]) < 0.06
                    else "medium"
                    if abs(row["delta"]) < 0.09
                    else "large",
                    "no_innovation_absolute_error": abs(
                        math.tanh(row["inputs"]["v"][0]) - row["actual_y"][0]
                    ),
                }
            )
            if not r["qualified"]:
                raise RuntimeError(f"Unqualified query: {r['reason']}")
        custody.atomic(out / "evaluations.json", evaluations)

    def check(update):
        (out / f"checkpoint-mixed{update}.json").write_text(model.snapshot())
        evaluate(f"mixed{update}-clean-free", data["clean_test"], False)
        evaluate(f"mixed{update}-offset-observed", data["mixed_test"], True)
        evaluate(
            f"mixed{update}-teacher-diagnostic", data["mixed_test"], True, teacher=True
        )
        free = {
            r["row"]: r
            for r in evaluations
            if r["check"] == f"mixed{update}-offset-observed"
        }
        teacher = {
            r["row"]: r
            for r in evaluations
            if r["check"] == f"mixed{update}-teacher-diagnostic"
        }
        p = model.graph.n_patches - 2
        shifts = [teacher[row]["errors"][p] - free[row]["errors"][p] for row in free]
        predictions_identical = all(
            teacher[row]["predictions"][p] == free[row]["predictions"][p]
            for row in free
        )
        errors_identical = all(shift == 0 for shift in shifts)
        diagnostic = {
            "update": update,
            "matched_rows": len(shifts),
            "model_sha256": custody.digest(model.snapshot()),
            "p_predictions_exactly_invariant": predictions_identical,
            "p_errors_exactly_invariant": errors_identical,
            "p_error_shift_rms": math.sqrt(sum(x * x for x in shifts) / len(shifts)),
            "p_error_shift_max": max(abs(x) for x in shifts),
        }
        if layout == "coupled":
            diagnostic["m_state_shift_rms"] = math.sqrt(
                sum(
                    (teacher[row]["state"][0] - free[row]["state"][0]) ** 2
                    for row in free
                )
                / len(shifts)
            )
        diagnostics.append(diagnostic)
        custody.atomic(out / "diagnostics.json", diagnostics)
        if layout == "input_only" and not (predictions_identical and errors_identical):
            raise AssertionError(
                "Input-only P changed under hypothetical H teaching clamp"
            )

    try:
        for phase, updates in (("clean", 64), ("mixed", 128)):
            for update in range(updates):
                rows = data[phase][16 * update : 16 * (update + 1)]
                before = model.snapshot()
                prior_weights = model.weights
                tick = time.perf_counter()
                r = bounded(
                    lambda rows=rows, phase=phase, update=update: model.observe_batch(
                        [witness(row) for row in rows],
                        event_id=update if phase == "clean" else 64 + update,
                        source="witness",
                    ),
                    {
                        "kind": "admission",
                        "phase": phase,
                        "update": update + 1,
                        "event_id": update if phase == "clean" else 64 + update,
                        "rows": [row["id"] for row in rows],
                    },
                )
                elapsed = time.perf_counter() - tick
                if not r["accepted"]:
                    assert model.snapshot() == before
                last_good = model.snapshot()
                ledger.append(
                    {
                        "phase": phase,
                        "update": update + 1,
                        "rows": [row["id"] for row in rows],
                        "accepted": r["accepted"],
                        "qualified": r["qualified"],
                        "stationarity": r["stationarity"],
                        "reason": r["reason"],
                        "source": r["source"],
                        "event_id": r["event_id"],
                        "batch_size": r["batch_size"],
                        "before_sha256": custody.digest(before),
                        "after_sha256": custody.digest(last_good),
                        "seconds": elapsed,
                        "work": r["work"],
                        "sweeps": r["sweeps"],
                        "state_rms": [
                            math.sqrt(sum(x[j] ** 2 for x in r["states"]) / 16)
                            for j in range(model.graph.n_patches)
                        ],
                        "error_rms": [
                            math.sqrt(sum(x[j] ** 2 for x in r["errors"]) / 16)
                            for j in range(model.graph.n_patches)
                        ],
                        "weight_displacement_rms": math.sqrt(
                            sum(
                                (x - y) ** 2
                                for x, y in zip(
                                    model.weights, prior_weights, strict=True
                                )
                            )
                            / len(model.weights)
                        ),
                    }
                )
                custody.atomic(out / "updates.json", ledger)
                custody.atomic(out / "last-completed.json", last_good)
                if not r["accepted"] or not r["qualified"]:
                    raise RuntimeError(f"Unaccepted admission: {r['reason']}")
                if phase == "mixed" and update + 1 in (32, 128):
                    check(update + 1)
            if phase == "clean":
                check(0)
        if time.monotonic() - started > CAP:
            raise TimeoutError("arm deadline crossed during bookkeeping")
    except TimeoutError as exc:
        status, failure = "timeout", str(exc)
    except Exception:  # noqa: BLE001 - Preserve an experiment failure receipt.
        status, failure = "error", traceback.format_exc()
    finally:
        # An interrupted call's in-memory state is discarded even if interrupted
        # around commitment; only a fully returned operation owns this checkpoint.
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior_alarm)
        custody.atomic(out / "last-completed.json", last_good)
        custody.atomic(out / "updates.json", ledger)
        custody.atomic(out / "evaluations.json", evaluations)
        custody.atomic(out / "diagnostics.json", diagnostics)
        groups = []
        for label in (
            f"mixed{n}-{kind}"
            for n in (0, 32, 128)
            for kind in ("clean-free", "offset-observed", "teacher-diagnostic")
        ):
            rows = [r for r in evaluations if r["check"] == label]
            good = [r for r in rows if r["qualified"]]
            mae = {
                head: sum(r[f"{head}_absolute_error"] for r in good) / len(good)
                if good and not label.endswith("teacher-diagnostic")
                else None
                for head in ("past", "future")
            }
            expected = 32 if label.endswith("clean-free") else 64
            groups.append(
                {
                    "check": label,
                    "completed": len(rows),
                    "expected": expected,
                    "qualified": len(good),
                    "qualified_only_mae": mae,
                    "p_error_rms_qualified": math.sqrt(
                        sum(r["errors"][model.graph.n_patches - 2] ** 2 for r in good)
                        / len(good)
                    )
                    if good
                    else None,
                    "clean_gate": len(good) == expected
                    and all(v is not None and v <= 0.03 for v in mae.values())
                    if label.endswith("clean-free")
                    else None,
                }
            )
        unchanged = sources() == protocol["sources"]
        checkpoint_sha = custody.sha(out / "last-completed.json")
        if not unchanged:
            status, failure = "error", "Frozen source changed"
        if status == "complete" and time.monotonic() - started > CAP:
            status, failure = "timeout", "arm deadline crossed during final bookkeeping"
        eligible = (
            status == "complete"
            and unchanged
            and counts["admissions_accepted"] == 192
            and len(ledger) == 192
            and counts["refused"] == counts["interrupted_unknown_work"] == 0
            and len(evaluations) == 480
            and len(diagnostics) == 3
            and all(r["qualified"] for r in evaluations)
            and all(
                g["clean_gate"] for g in groups if g["check"].endswith("clean-free")
            )
        )
        result = {
            "status": status,
            "failure": failure,
            "seed": seed,
            "layout": layout,
            "arm": arm,
            "seconds": time.monotonic() - started,
            "accepted_updates": sum(r["accepted"] for r in ledger),
            "planned_updates": 192,
            "completed_queries": len(evaluations),
            "call_counts": counts,
            "attempted_training_presentations": counts["admissions_started"] * 16,
            "admitted_training_presentations": counts["admissions_accepted"] * 16,
            "diagnostics": diagnostics,
            "eligible": bool(eligible),
            "groups": groups,
            "sources_unchanged": unchanged,
            "protocol_sha256": custody.sha(root / "protocol.json"),
            "checkpoint_sha256": checkpoint_sha,
        }
        custody.atomic(out / "result.json", result)
    return 0 if status == "complete" and result["sources_unchanged"] else 1


def campaign_summary(root):
    reports = []
    execution = custody.read(root / "execution.json")
    for (seed, layout, arm), outcome in zip(jobs(), execution, strict=True):
        assert tuple(outcome["job"]) == (seed, layout, arm), (
            "Execution identity differs"
        )
        path = root / f"{layout}-{arm}-seed{seed}" / "result.json"
        report = (
            custody.read(path)
            if path.exists()
            else {
                "seed": seed,
                "layout": layout,
                "arm": arm,
                "status": "missing",
                "eligible": False,
                "groups": [],
            }
        )
        assert (report["seed"], report["layout"], report["arm"]) == (
            seed,
            layout,
            arm,
        ), "Report identity differs"
        reports.append({"execution": outcome, "report": report})
    all_eligible = len(reports) == 20 and all(
        row["report"]["eligible"]
        and row["execution"]["status"] == "returned"
        and row["execution"]["code"] == 0
        for row in reports
    )
    comparisons = []
    for layout in LAYOUTS:
        pairs = []
        for seed in SEEDS:
            metrics = {}
            for arm in ARMS:
                report = next(
                    x["report"]
                    for x in reports
                    if x["report"]["seed"] == seed
                    and x["report"]["layout"] == layout
                    and x["report"]["arm"] == arm
                )
                final = next(
                    (
                        g
                        for g in report["groups"]
                        if g["check"] == "mixed128-offset-observed"
                    ),
                    None,
                )
                metrics[arm] = (
                    final["qualified_only_mae"]["future"]
                    if final and final["qualified"] == final["completed"] == 64
                    else None
                )
            delta = (
                metrics["ordinary"] - metrics["observer"]
                if all(v is not None for v in metrics.values())
                else None
            )
            pairs.append(
                {"seed": seed, "mae": metrics, "ordinary_minus_observer": delta}
            )
        deltas = [p["ordinary_minus_observer"] for p in pairs]
        mean = sum(deltas) / len(deltas) if all(v is not None for v in deltas) else None
        passed = (
            all_eligible
            and mean is not None
            and mean >= 0.005
            and all(v > 0 for v in deltas)
        )
        comparisons.append(
            {
                "layout": layout,
                "pairs": pairs,
                "eligible": all_eligible,
                "mean_mae_reduction": mean,
                "criterion_met": passed,
                "efficiency_claim": False,
            }
        )
    return {
        "protocol_sha256": custody.sha(root / "protocol.json"),
        "all_twenty_arms_eligible": all_eligible,
        "outcomes": reports,
        "comparisons": comparisons,
    }


def launch(root):
    validate(root)
    planned_jobs = jobs()
    path = root / "launch.json"
    if path.exists():
        raise ValueError("A launch already exists; preserve it")
    custody.atomic(
        path, {"jobs": planned_jobs, "max_workers": 3, "outer_timeout_seconds": CAP + 5}
    )

    def execute(job):
        seed, layout, arm = job
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "run",
            str(root),
            "--seed",
            str(seed),
            "--layout",
            layout,
            "--arm",
            arm,
        ]
        with (root / f"{layout}-{arm}-seed{seed}.log").open("x") as log:
            p = subprocess.Popen(
                command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
            )
            try:
                code = p.wait(timeout=CAP + 5)
                status = "returned"
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                code, status = p.wait(), "outer_timeout"
        return {"job": job, "pid": p.pid, "code": code, "status": status}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(execute, planned_jobs))
    custody.atomic(root / "execution.json", results)
    custody.atomic(root / "summary.json", campaign_summary(root))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "launch"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--seed", type=int, choices=SEEDS)
    parser.add_argument("--layout", choices=LAYOUTS)
    parser.add_argument("--arm", choices=ARMS)
    args = parser.parse_args()
    if args.command == "run" and None in (args.seed, args.layout, args.arm):
        parser.error("run requires --seed, --layout and --arm")
    if args.command == "freeze":
        freeze(args.root.resolve())
    elif args.command == "launch":
        launch(args.root.resolve())
    else:
        sys.exit(run(args.root.resolve(), args.seed, args.layout, args.arm))
