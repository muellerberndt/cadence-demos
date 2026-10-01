"""Bounded delayed-outcome ownership experiment; freeze before any training.

One collector owns one outstanding executed decision. Delay is explicit ledger
memory, not learned temporal memory, planning, or Reinforcement clamp support.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
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

SEEDS = (41, 43, 47, 53, 59)
ARMS = ("ordinary", "observer")
DELAYS = (0, 2, 4)
HEADS = ("q_minus", "q_plus")
UPDATES = {"clean": 64, "mixed": 128}
BATCH = 16
CAP = 60
MAX_WORKERS = 15


def sources():
    package = Path(cadence.__file__).resolve().parent
    paths = [*package.rglob("*.py"), Path(__file__), Path(custody.__file__)]
    return {str(p.resolve()): custody.sha(p) for p in sorted(paths)}


def brain(seed, arm):
    c = Cortex(
        seed=seed,
        state_prior=0.01,
        parameter_prior=0.1,
        tolerance=1e-6,
        settle_budget=2048,
    )
    u, v = c.input("u", shape=1), c.input("v", shape=1)
    m = c.column("M", patches=1, inputs=u)
    p = c.column("P", patches=1, inputs=m)
    h = (
        c.observer("H", patches=2, inputs=(u, v, p), observes=p)
        if arm == "observer"
        else c.column("H", patches=2, inputs=(u, v, p, m))
    )
    c.output("past", shape=1, reads=p)
    for action, name in enumerate(HEADS):
        c.output(name, shape=1, reads=h, indices=(action,))
    return c.build()


def founders(seed):
    a, b = (brain(seed, arm) for arm in ARMS)
    assert a.graph.n_patches == b.graph.n_patches == 4
    assert len(a.weights) == len(b.weights) == 10
    assert a.weights == b.weights and a.biases == b.biases
    for ordinary, observer in zip(a.graph.edges, b.graph.edges, strict=True):
        assert ordinary == observer or (
            ordinary[0:2] == ("state", 0)
            and observer[0:2] == ("residual", 1)
            and ordinary[2] == observer[2] in (2, 3)
        )
    return dict(zip(ARMS, (a.snapshot(), b.snapshot()), strict=True))


def tape():
    rng = random.Random(20261005)
    data = {}
    for phase, groups, offsets, width in (
        ("clean", 512, False, 0.4),
        ("mixed", 512, True, 0.4),
        ("clean_test", 32, False, 0.4),
        ("policy_test", 128, True, 0.08),
    ):
        rows = []
        for _ in range(groups):
            u, v = rng.uniform(-0.8, 0.8), rng.uniform(-width, width)
            magnitude = rng.uniform(0.03, 0.12) if offsets else 0.0
            deltas = (
                (magnitude, -magnitude)
                if phase == "mixed"
                else (rng.choice((-1, 1)) * magnitude,)
            )
            actions = (None,) if phase == "policy_test" else (0, 1)
            for delta in deltas:
                for action in actions:
                    rows.append(
                        {
                            "id": f"{phase}:{len(rows)}",
                            "u": u,
                            "v": v,
                            "delta": delta,
                            "executed_action": action,
                        }
                    )
        data[phase] = rows
    assert len(data["clean"]) == UPDATES["clean"] * BATCH
    assert len(data["mixed"]) == UPDATES["mixed"] * BATCH
    return data


def observation(row):
    """Only the body's already available observation crosses this boundary."""
    return {"u": [row["u"]], "v": [row["v"]]}, math.tanh(math.tanh(row["u"])) + row[
        "delta"
    ]


def terminal_reward(row, executed_action):
    """The simulated body emits this signed outcome only at its due tick."""
    return (2 * executed_action - 1) * math.tanh(row["v"] + row["delta"])


class Ledger:
    """Single-flight evidence ownership, deliberately outside Cadence core."""

    def __init__(self):
        self.pending = None
        self.issued = 0

    def issue(self, *, inputs, actual_x, forecasts, model_id, event_id, tick, row):
        if self.pending is not None:
            raise ValueError("A decision is already pending")
        if len(forecasts) != 2 or not all(math.isfinite(v) for v in forecasts):
            raise ValueError("Two finite original forecasts are required")
        self.issued += 1
        self.pending = copy.deepcopy(
            {
                "decision_id": self.issued,
                "row": row,
                "inputs": inputs,
                "actual_x": actual_x,
                "original_forecasts": list(forecasts),
                "model_id": model_id,
                "event_id": event_id,
                "issued_tick": tick,
                "proposed_action": int(forecasts[1] > forecasts[0]),
            }
        )
        return copy.deepcopy(self.pending)

    def execute(self, decision_id, action, tick, delay):
        p = self.pending
        if (
            type(decision_id) is not int
            or p is None
            or decision_id != p["decision_id"]
            or "executed_action" in p
        ):
            raise ValueError("Execution must acknowledge the pending proposal once")
        if type(action) is not int or action not in (0, 1):
            raise ValueError("An actual action index is required")
        if (
            type(tick) is not int
            or type(delay) is not int
            or delay not in DELAYS
            or tick < p["issued_tick"]
        ):
            raise ValueError("Invalid execution time or declared delay")
        p.update(executed_action=action, executed_tick=tick, due_tick=tick + delay)
        return copy.deepcopy(p)

    def outcome(self, *, decision_id, executed_action, reward, tick):
        p = self.pending
        if (
            type(decision_id) is not int
            or type(executed_action) is not int
            or p is None
            or decision_id != p["decision_id"]
            or "executed_action" not in p
            or executed_action != p["executed_action"]
        ):
            raise ValueError("Outcome does not own the pending executed decision")
        if (
            type(tick) is not int
            or tick < p["due_tick"]
            or type(reward) not in (int, float)
            or not math.isfinite(reward)
            or abs(reward) > 1
        ):
            raise ValueError("Premature or invalid actual outcome")
        result = {
            **copy.deepcopy(p),
            "outcome_tick": tick,
            "reward": reward,
            "original_surprise": reward - p["original_forecasts"][executed_action],
        }
        self.pending = None
        return result

    def cancel(self):
        if self.pending is None:
            raise ValueError("No outstanding decision")
        result = {**copy.deepcopy(self.pending), "cancelled": True}
        self.pending = None
        return result


def witness(receipt):
    return receipt["inputs"], {
        "past": [receipt["actual_x"]],
        HEADS[receipt["executed_action"]]: [receipt["reward"]],
    }


def freeze(root):
    root.mkdir(parents=True, exist_ok=False)
    custody.atomic(root / "data.json", tape())
    custody.atomic(root / "founders.json", {str(s): founders(s) for s in SEEDS})
    custody.atomic(
        root / "protocol.json",
        {
            "sources": sources(),
            "data_sha256": custody.sha(root / "data.json"),
            "founders_sha256": custody.sha(root / "founders.json"),
            "seeds": SEEDS,
            "data_seed": 20261005,
            "arms": ARMS,
            "delays": DELAYS,
            "patches": 4,
            "parameters": 14,
            "updates": UPDATES,
            "batch_size": BATCH,
            "body": "Observed x=tanh(tanh(u))+delta; executed a in {-1,+1}; at D ticks actual r=a*tanh(v+delta). Delta stays private body state.",
            "ownership": "Single flight. Preserve both pre-execution forecasts, original model identity, proposed and acknowledged actual action, original context, planned admission event and ticks. Reject every duplicate, stale, changed, cancelled, unexecuted or premature outcome. No new decision before outcome/cancellation.",
            "learning": "Only actual past x and the executed action's observed terminal signed outcome are witnesses. Other value head stays free. This is terminal contextual-bandit outcome regression, not raw reward as action target and not the normalized discounted Reinforcement Q target. All patches share the existing coupled repair law.",
            "clean_gate": "After64 clean batches all64 heldout queries qualify with P and BOTH value heads FREE; each executed-head MAE and P MAE<=0.03. Failure stops mixed training. Repeat the same clean gate after mixed training.",
            "primary": "Delayed evidence ownership and actual-outcome learning: every retained outcome belongs to one executed decision, no pre-outcome future target, and D0/2/4 admit identical witnesses in identical order. Successful eligible arms must pass final clean retention and final executed-outcome MAE<=0.03. Report signed return, oracle regret, prediction MAE and actual work before/after mixed learning, with every seed/failure preserved.",
            "delay_control": "No brain call or learning occurs on neutral ticks. D0/2/4 MUST be bit-identical in model trajectory, decisions, values, witnesses and solve work; only body ticks/timing differ. This establishes collector credit custody, not learned temporal memory.",
            "secondary": "Architecture comparison uses D0 only (other delays are repeats, not extra seeds); all5 paired arms must complete, qualify, admit all192 batches and pass both clean gates. Report all paired return/regret/MAE/work. Any advantage requires at least0.005 mean oracle-regret reduction and improvement in all5 pairs. Work/latency are separate; no subset selection, hyperparameter tuning or planning claim.",
            "surprise": "Compute r-original_forecast[executed_action] before learning and retain it immutably. After each admission re-query the first batch context with only actual P clamped, recording r-current_forecast and internal patch errors separately. Neither later prediction error nor internal settlement residual replaces historical surprise. Surprise is diagnostic only, with no designed surprise threshold or scheduler in this experiment.",
            "compute": {
                "arm_seconds": CAP,
                "outer_seconds": CAP + 5,
                "max_workers": MAX_WORKERS,
                "backend": "python",
                "dtype": "float64",
            },
            "artifacts": "Complete raw journals stay on AWS. Estimated episode journals170MB plus checkpoints/evaluations; no local comparative campaign. Fetch compact verified receipts only; retain complete archive on AWS.",
            "runtime": {"platform": platform.platform(), "python": sys.version},
            "scope": "One body outcome interface, no per-population external evaluator. Shared valence is a signed actual outcome entering one connected objective, not identical reward targets broadcast to every patch. Explicit collector memory and body-designed reward are not claims of intrinsic emotions, learned memory or planning.",
        },
    )


def validate(root):
    p = custody.read(root / "protocol.json")
    assert p["sources"] == sources()
    assert p["data_sha256"] == custody.sha(root / "data.json")
    assert p["founders_sha256"] == custody.sha(root / "founders.json")
    return p


def run(root, seed, arm, delay):
    protocol = validate(root)
    out = root / f"{arm}-seed{seed}-delay{delay}"
    out.mkdir(exist_ok=False)
    model = Brain.from_snapshot(custody.read(root / "founders.json")[str(seed)][arm])
    data, owner = custody.read(root / "data.json"), Ledger()
    started, tick = time.monotonic(), 0
    status, failure = "complete", None
    updates, evaluations = [], []
    admission_counts = {
        "started": 0,
        "returned": 0,
        "accepted": 0,
        "refused": 0,
        "interrupted_unknown_work": 0,
    }
    last_good = model.snapshot()

    def journal(name, record):
        with (out / f"{name}.jsonl").open("a") as handle:
            handle.write(custody.encoded(record) + "\n")

    def alarm(*_):
        raise TimeoutError("arm deadline")

    old_alarm = signal.signal(signal.SIGALRM, alarm)

    def solve(call, intent):
        nonlocal model, last_good
        before = model.snapshot()
        intent = {
            **intent,
            "before_sha256": custody.digest(before),
            "status": "started",
        }
        custody.atomic(out / "current-call.json", intent)
        remaining = CAP - (time.monotonic() - started)
        if remaining <= 0:
            custody.atomic(
                out / "current-call.json",
                {**intent, "status": "not_started_deadline", "work": {}, "seconds": 0},
            )
            raise TimeoutError("arm deadline before solve")
        began = time.perf_counter()
        if intent["kind"] == "admission":
            admission_counts["started"] += 1
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            result = call()
        except Exception as exc:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if intent["kind"] == "admission":
                admission_counts["interrupted_unknown_work"] += 1
            model = Brain.from_snapshot(before)
            custody.atomic(
                out / "current-call.json",
                {
                    **intent,
                    "status": "interrupted",
                    "unknown_work": True,
                    "seconds": time.perf_counter() - began,
                    "failure": repr(exc),
                    "restored_sha256": custody.digest(model.snapshot()),
                },
            )
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        last_good = model.snapshot()
        if intent["kind"] == "admission":
            admission_counts["returned"] += 1
            admission_counts["accepted" if result["accepted"] else "refused"] += 1
        receipt = {
            **intent,
            "status": "returned",
            "qualified": result["qualified"],
            "accepted": result.get("accepted"),
            "stationarity": result["stationarity"],
            "reason": result["reason"],
            "work": result["work"],
            "sweeps": result["sweeps"],
            "seconds": time.perf_counter() - began,
            "after_sha256": custody.digest(last_good),
        }
        journal("calls", receipt)
        custody.atomic(out / "current-call.json", receipt)
        custody.atomic(out / "last-completed.json", last_good)
        if not result["qualified"]:
            raise RuntimeError(f"Unqualified {intent['kind']}: {result['reason']}")
        if intent["kind"] == "admission" and not result["accepted"]:
            raise RuntimeError("Qualified admission was not accepted")
        return result

    def episode(row, event_id, *, observed=True, policy=False, label="training"):
        nonlocal tick
        inputs, x = observation(row)
        before = model.snapshot()
        r = solve(
            lambda: model.settle(inputs, targets={"past": [x]} if observed else None),
            {
                "kind": "forecast",
                "check": label,
                "row": row["id"],
                "event_id": event_id,
            },
        )
        assert model.snapshot() == before
        forecasts = [r["outputs"][head][0] for head in HEADS]
        issued = owner.issue(
            inputs=inputs,
            actual_x=x,
            forecasts=forecasts,
            model_id=custody.digest(before),
            event_id=event_id,
            tick=tick,
            row=row["id"],
        )
        journal("decisions", issued)
        action = issued["proposed_action"] if policy else row["executed_action"]
        execution = owner.execute(issued["decision_id"], action, tick, delay)
        journal("executions", execution)
        custody.atomic(out / "pending.json", execution)
        # Neutral body ticks make no brain call and expose no future outcome.
        for _ in range(delay):
            tick += 1
        reward = terminal_reward(row, action)
        receipt = owner.outcome(
            decision_id=issued["decision_id"],
            executed_action=action,
            reward=reward,
            tick=tick,
        )
        journal("outcomes", receipt)
        custody.atomic(out / "pending.json", None)
        tick += 1
        return receipt, r

    def evaluate(label, rows, observed):
        for row in rows:
            receipt, r = episode(
                row, None, observed=observed, policy=observed, label=label
            )
            action = receipt["executed_action"]
            evaluations.append(
                {
                    "check": label,
                    "row": row["id"],
                    "decision_id": receipt["decision_id"],
                    "qualified": r["qualified"],
                    "past_absolute_error": abs(
                        r["outputs"]["past"][0] - receipt["actual_x"]
                    ),
                    "executed_action": action,
                    "prediction_absolute_error": abs(receipt["original_surprise"]),
                    "reward": receipt["reward"],
                    "oracle_regret": abs(math.tanh(row["v"] + row["delta"]))
                    - receipt["reward"],
                    "offset_sign": 0
                    if row["delta"] == 0
                    else (1 if row["delta"] > 0 else -1),
                    "state": r["state"],
                    "errors": r["errors"],
                    "predictions": r["predictions"],
                }
            )
        custody.atomic(out / "evaluations.json", evaluations)

    def groups():
        result = []
        for label in ("clean-gate", "policy-before", "clean-retention", "policy-final"):
            rows = [r for r in evaluations if r["check"] == label]
            expected = 64 if label.startswith("clean") else 128
            means = {
                field: sum(r[field] for r in rows) / len(rows) if rows else None
                for field in (
                    "past_absolute_error",
                    "prediction_absolute_error",
                    "reward",
                    "oracle_regret",
                )
            }
            head_mae = [
                sum(
                    r["prediction_absolute_error"]
                    for r in rows
                    if r["executed_action"] == a
                )
                / sum(r["executed_action"] == a for r in rows)
                if any(r["executed_action"] == a for r in rows)
                else None
                for a in (0, 1)
            ]
            gate = (
                (
                    len(rows) == expected
                    and means["past_absolute_error"] <= 0.03
                    and all(v is not None and v <= 0.03 for v in head_mae)
                )
                if label.startswith("clean")
                else None
            )
            result.append(
                {
                    "check": label,
                    "expected": expected,
                    "completed": len(rows),
                    "means": means,
                    "executed_head_mae": head_mae,
                    "clean_gate": gate,
                }
            )
        return result

    try:
        for phase, count in UPDATES.items():
            for update in range(count):
                event_id = update if phase == "clean" else UPDATES["clean"] + update
                rows = data[phase][update * BATCH : (update + 1) * BATCH]
                receipts = [episode(row, event_id)[0] for row in rows]
                r = solve(
                    lambda receipts=receipts, event_id=event_id: model.observe_batch(
                        [witness(x) for x in receipts],
                        event_id=event_id,
                        source="witness",
                    ),
                    {
                        "kind": "admission",
                        "phase": phase,
                        "update": update + 1,
                        "event_id": event_id,
                        "decisions": [x["decision_id"] for x in receipts],
                    },
                )
                updates.append(
                    {
                        "phase": phase,
                        "update": update + 1,
                        "event_id": r["event_id"],
                        "source": r["source"],
                        "batch_size": r["batch_size"],
                        "accepted": r["accepted"],
                        "qualified": r["qualified"],
                        "stationarity": r["stationarity"],
                        "witness_sha256": custody.digest(
                            custody.encoded([witness(x) for x in receipts])
                        ),
                        "after_sha256": custody.digest(model.snapshot()),
                    }
                )
                custody.atomic(out / "updates.json", updates)
                # A declared diagnostic, not an additional learning admission.
                # The original surprise remains immutable even after repair.
                receipt = receipts[0]
                r = solve(
                    lambda receipt=receipt: model.settle(
                        receipt["inputs"], targets={"past": [receipt["actual_x"]]}
                    ),
                    {
                        "kind": "post-update-forecast",
                        "decision_id": receipt["decision_id"],
                        "event_id": event_id,
                    },
                )
                current = r["outputs"][HEADS[receipt["executed_action"]]][0]
                journal(
                    "surprise",
                    {
                        "decision_id": receipt["decision_id"],
                        "original_surprise": receipt["original_surprise"],
                        "post_update_prediction_error": receipt["reward"] - current,
                        "current_internal_errors": r["errors"],
                        "current_model_id": custody.digest(model.snapshot()),
                    },
                )
            (out / f"checkpoint-{phase}.json").write_text(model.snapshot())
            evaluate(
                "clean-gate" if phase == "clean" else "clean-retention",
                data["clean_test"],
                False,
            )
            if phase == "clean" and not groups()[0]["clean_gate"]:
                status = "acquisition_failed"
                break
            evaluate(
                "policy-before" if phase == "clean" else "policy-final",
                data["policy_test"],
                True,
            )
        if time.monotonic() - started > CAP:
            raise TimeoutError("arm deadline during bookkeeping")
    except TimeoutError as exc:
        status, failure = "timeout", str(exc)
    except Exception:  # noqa: BLE001 - Retain every failed experimental arm.
        status, failure = "error", traceback.format_exc()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_alarm)
        custody.atomic(out / "last-completed.json", last_good)
        custody.atomic(out / "updates.json", updates)
        custody.atomic(out / "evaluations.json", evaluations)
        custody.atomic(out / "pending.json", owner.pending)
        summary = groups()
        unchanged = sources() == protocol["sources"]
        journals = {
            p.name: {"bytes": p.stat().st_size, "sha256": custody.sha(p)}
            for p in sorted(out.glob("*.jsonl"))
        }
        if time.monotonic() - started > CAP:
            status, failure = "timeout", failure or "deadline during final bookkeeping"
        if not unchanged:
            status, failure = "error", "Frozen source changed"
        primary_pass = (
            status == "complete"
            and admission_counts["accepted"] == sum(UPDATES.values())
            and summary[0]["clean_gate"]
            and summary[2]["clean_gate"]
            and summary[3]["completed"] == summary[3]["expected"]
            and summary[3]["means"]["prediction_absolute_error"] <= 0.03
        )
        custody.atomic(
            out / "result.json",
            {
                "status": status,
                "failure": failure,
                "seed": seed,
                "arm": arm,
                "delay": delay,
                "seconds": time.monotonic() - started,
                "body_ticks": tick,
                "issued_decisions": owner.issued,
                "completed_updates": len(updates),
                "accepted_updates": sum(r["accepted"] for r in updates),
                "admission_counts": admission_counts,
                "primary_learning_gate": bool(primary_pass),
                "planned_updates": sum(UPDATES.values()),
                "groups": summary,
                "sources_unchanged": unchanged,
                "protocol_sha256": custody.sha(root / "protocol.json"),
                "checkpoint_sha256": custody.digest(last_good),
                "journals": journals,
            },
        )
    return 0 if status in ("complete", "acquisition_failed") else 1


def launch(root):
    validate(root)
    jobs = [(s, a, d) for s in SEEDS for a in ARMS for d in DELAYS]
    if (root / "launch.json").exists():
        raise ValueError("Preserve the previous launch")
    custody.atomic(
        root / "launch.json",
        {"jobs": jobs, "max_workers": MAX_WORKERS, "outer_seconds": CAP + 5},
    )

    def execute(job):
        seed, arm, delay = job
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "run",
            str(root),
            "--seed",
            str(seed),
            "--arm",
            arm,
            "--delay",
            str(delay),
        ]
        with (root / f"{arm}-seed{seed}-delay{delay}.log").open("x") as handle:
            p = subprocess.Popen(
                command, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True
            )
            try:
                code, status = p.wait(timeout=CAP + 5), "returned"
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                code, status = p.wait(), "outer_timeout"
        return {
            "job": job,
            "pid": p.pid,
            "code": code,
            "status": status,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        custody.atomic(root / "execution.json", list(pool.map(execute, jobs)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "launch"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--seed", type=int, choices=SEEDS)
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--delay", type=int, choices=DELAYS)
    args = parser.parse_args()
    if args.command == "run" and None in (args.seed, args.arm, args.delay):
        parser.error("run requires --seed, --arm and --delay")
    if args.command == "freeze":
        freeze(args.root.resolve())
    elif args.command == "launch":
        launch(args.root.resolve())
    else:
        sys.exit(run(args.root.resolve(), args.seed, args.arm, args.delay))
