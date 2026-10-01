"""Public three-patch shared-innovation pilot; freeze before any training.

Usage: shared_innovation.py freeze ROOT; shared_innovation.py launch ROOT.
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

SEEDS = (2, 7, 11, 19, 29)
ARMS = ("ordinary", "observer")
CONDITIONS = {"narrow": 0.2, "wide": 0.8}
CAP = 40


def sources():
    package = Path(cadence.__file__).resolve().parent
    paths = [*package.rglob("*.py"), Path(__file__), Path(custody.__file__)]
    return {str(p.resolve()): custody.sha(p) for p in sorted(paths)}


def body(u, v, delta, identity):
    return {
        "id": identity,
        "inputs": {"u": [u], "v": [v]},
        "actual_x": [math.tanh(math.tanh(u)) + delta],
        "actual_y": [math.tanh(v + delta)],
        "delta": delta,
    }


def tape(condition):
    rng = random.Random(20261004)
    width = CONDITIONS[condition]

    def row(identity, delta=0.0):
        return body(rng.uniform(-width, width), rng.uniform(-0.4, 0.4), delta, identity)

    clean = [row(f"clean:{i}") for i in range(64 * 16)]
    mixed = []
    for i in range(128 * 8):
        delta = rng.uniform(0.03, 0.12)
        positive = row(f"mixed:{2 * i}", delta)
        u, v = positive["inputs"]["u"][0], positive["inputs"]["v"][0]
        mixed.extend([positive, body(u, v, -delta, f"mixed:{2 * i + 1}")])
    clean_test = [row(f"clean-test:{i}") for i in range(32)]
    mixed_test = [
        row(f"mixed-test:{i}", rng.choice((-1, 1)) * rng.uniform(0.03, 0.12))
        for i in range(64)
    ]
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


def brain(seed, arm, *, input_only=False):
    c = Cortex(
        seed=seed,
        state_prior=0.01,
        parameter_prior=0.1,
        tolerance=1e-6,
        settle_budget=2048,
    )
    u, v = c.input("u", shape=1), c.input("v", shape=1)
    m = None if input_only else c.column("M", patches=1, inputs=u)
    p = c.column("P", patches=1, inputs=u if input_only else m)
    h = (
        c.observer("H", patches=1, inputs=(u, v, p), observes=p)
        if arm == "observer"
        else c.column("H", patches=1, inputs=(u, v, p, m))
    )
    c.output("past", shape=1, reads=p)
    c.output("future", shape=1, reads=h)
    return c.build()


def founders(seed):
    ordinary, observer = (brain(seed, arm) for arm in ARMS)
    a = dict(zip(ordinary.graph.edges, ordinary.weights, strict=True))
    b = dict(zip(observer.graph.edges, observer.weights, strict=True))
    common = a.keys() & b.keys()
    assert len(common) == 5 and all(a[k] == b[k] for k in common)
    assert a[("state", 0, 2)] == b[("residual", 1, 2)]
    assert ordinary.weights == observer.weights and ordinary.biases == observer.biases
    assert all(len(m.weights) == 6 and len(m.biases) == 3 for m in (ordinary, observer))
    return dict(zip(ARMS, (ordinary.snapshot(), observer.snapshot()), strict=True))


def freeze(root):
    root.mkdir(parents=True, exist_ok=False)
    custody.atomic(root / "data.json", {name: tape(name) for name in CONDITIONS})
    custody.atomic(
        root / "founders.json", {str(seed): founders(seed) for seed in SEEDS}
    )
    custody.atomic(
        root / "input-only-founders.json",
        {
            str(seed): brain(seed, "observer", input_only=True).snapshot()
            for seed in SEEDS
        },
    )
    protocol = {
        "sources": sources(),
        "data_sha256": custody.sha(root / "data.json"),
        "founders_sha256": custody.sha(root / "founders.json"),
        "seeds": SEEDS,
        "input_only_founders_sha256": custody.sha(root / "input-only-founders.json"),
        "conditions": CONDITIONS,
        "arms": ARMS,
        "parameters": 9,
        "patches": 3,
        "body": "x=tanh(tanh(u))+delta; later y=tanh(v+delta)",
        "training": {
            "clean_updates": 64,
            "mixed_updates": 128,
            "batch_size": 16,
            "mixed_checks": [0, 32, 128],
        },
        "clean_acquisition_gate": "All32 independent clean queries qualify; P and H are BOTH FREE; each head MAE<=0.03. Recheck after mixed learning.",
        "test": "Only actual P observation is clamped for correction; H stays free. Offsets/future labels never enter query arguments. Queries are pure and independent of order.",
        "teacher_clamp_diagnostic": "At each check, compare same-weight P-only queries against P+actual-future clamps on identical rows. Teacher-clamped H is never scored as a prediction. Measure P error changes; no parameters or live state change.",
        "input_only_control": "Frozen but not launched: two-patch, seven-parameter observer with P reading u directly. Same-weight P residual cannot depend on H teacher clamp. Any later benefit is representation reuse, not iterative correction; not a matched-capacity primary arm.",
        "selection": "No hyperparameter grid or posthoc selection. Mixed training continues after a failed clean gate but cannot establish transfer advantage.",
        "primary_comparison": "Per condition, paired mixed128 free-H correction MAE over all64 held-out rows and all5 seeds. An advantage interpretation requires every paired arm complete, every admission accepted, every query qualified, and both initial and final clean-free P/H gates passed. No eligible-only subset comparison. Report each seed and signed offset bin; a useful effect requires at least0.005 mean absolute MAE reduction and improvement in all5 pairs. Work/latency remain separate paired endpoints; more accurate with more work is not an efficiency win.",
        "compute": {
            "arm_deadline_seconds": CAP,
            "outer_process_seconds": CAP + 5,
            "max_workers": 3,
            "backend": "python",
            "dtype": "float64",
        },
        "scope": "Matched information/counts, exact shared and replacement initial coefficients. Ordinary backreaction already exists. This is a representation/correction experiment, not proof of exclusive expressivity or temporal memory.",
        "platform": platform.platform(),
    }
    custody.atomic(root / "protocol.json", protocol)


def validate(root):
    p = custody.read(root / "protocol.json")
    assert sources() == p["sources"]
    assert custody.sha(root / "data.json") == p["data_sha256"]
    assert custody.sha(root / "founders.json") == p["founders_sha256"]
    assert (
        custody.sha(root / "input-only-founders.json")
        == p["input_only_founders_sha256"]
    )
    return p


def run(root, seed, condition, arm):
    protocol = validate(root)
    out = root / f"{condition}-{arm}-seed{seed}"
    out.mkdir(exist_ok=False)
    model = Brain.from_snapshot(custody.read(root / "founders.json")[str(seed)][arm])
    data = custody.read(root / "data.json")[condition]
    started = time.monotonic()
    last_good = model.snapshot()
    ledger, evaluations = [], []
    status, failure = "complete", None

    def alarm(*_):
        raise TimeoutError("arm deadline")

    prior_alarm = signal.signal(signal.SIGALRM, alarm)

    def bounded(call, intent):
        nonlocal model
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
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            result = call()
        except Exception as exc:
            signal.setitimer(signal.ITIMER_REAL, 0)
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
        completed = {
            **intent,
            "status": "returned",
            "seconds": time.monotonic() - tick,
            "work": result["work"],
            "sweeps": result["sweeps"],
            "after_sha256": custody.digest(model.snapshot()),
        }
        with (out / "calls.jsonl").open("a") as journal:
            journal.write(custody.encoded(completed) + "\n")
        custody.atomic(out / "current-call.json", completed)
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
        custody.atomic(out / "evaluations.json", evaluations)

    def check(update):
        (out / f"checkpoint-mixed{update}.json").write_text(model.snapshot())
        evaluate(f"mixed{update}-clean-free", data["clean_test"], False)
        evaluate(f"mixed{update}-offset-observed", data["mixed_test"], True)
        evaluate(
            f"mixed{update}-teacher-diagnostic", data["mixed_test"], True, teacher=True
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
                            for j in range(3)
                        ],
                        "error_rms": [
                            math.sqrt(sum(x[j] ** 2 for x in r["errors"]) / 16)
                            for j in range(3)
                        ],
                        "weight_displacement_rms": math.sqrt(
                            sum(
                                (x - y) ** 2
                                for x, y in zip(
                                    model.weights, prior_weights, strict=True
                                )
                            )
                            / 6
                        ),
                    }
                )
                custody.atomic(out / "updates.json", ledger)
                custody.atomic(out / "last-completed.json", last_good)
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
                        sum(r["errors"][1] ** 2 for r in good) / len(good)
                    )
                    if good
                    else None,
                    "clean_gate": len(good) == expected
                    and all(v is not None and v <= 0.03 for v in mae.values())
                    if label.endswith("clean-free")
                    else None,
                }
            )
        if status == "complete" and time.monotonic() - started > CAP:
            status, failure = "timeout", "arm deadline crossed during final bookkeeping"
        result = {
            "status": status,
            "failure": failure,
            "seed": seed,
            "condition": condition,
            "arm": arm,
            "seconds": time.monotonic() - started,
            "accepted_updates": sum(r["accepted"] for r in ledger),
            "planned_updates": 192,
            "completed_queries": len(evaluations),
            "groups": groups,
            "sources_unchanged": sources() == protocol["sources"],
            "protocol_sha256": custody.sha(root / "protocol.json"),
            "checkpoint_sha256": custody.sha(out / "last-completed.json"),
        }
        custody.atomic(out / "result.json", result)
    return 0 if status == "complete" and result["sources_unchanged"] else 1


def launch(root):
    validate(root)
    jobs = [(s, c, a) for s in SEEDS for c in CONDITIONS for a in ARMS]
    path = root / "launch.json"
    if path.exists():
        raise ValueError("A launch already exists; preserve it")
    custody.atomic(
        path, {"jobs": jobs, "max_workers": 3, "outer_timeout_seconds": CAP + 5}
    )

    def execute(job):
        seed, condition, arm = job
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "run",
            str(root),
            "--seed",
            str(seed),
            "--condition",
            condition,
            "--arm",
            arm,
        ]
        with (root / f"{condition}-{arm}-seed{seed}.log").open("x") as log:
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
        results = list(pool.map(execute, jobs))
    custody.atomic(root / "execution.json", results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "launch"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--seed", type=int, choices=SEEDS)
    parser.add_argument("--condition", choices=CONDITIONS)
    parser.add_argument("--arm", choices=ARMS)
    args = parser.parse_args()
    if args.command == "run" and None in (args.seed, args.condition, args.arm):
        parser.error("run requires --seed, --condition and --arm")
    if args.command == "freeze":
        freeze(args.root.resolve())
    elif args.command == "launch":
        launch(args.root.resolve())
    else:
        sys.exit(run(args.root.resolve(), args.seed, args.condition, args.arm))
