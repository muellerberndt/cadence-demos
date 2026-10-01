"""Cycle-only cue/exposure follow-up; historical controls stay separate.

Same private patch kernel, fresh seeds, standard1e-6 tolerance. No public
topology/API change and no promotion of the original stricter-tolerance run.
"""

from __future__ import annotations

import argparse
import math
import random
import signal
import time
import traceback
from collections import Counter
from pathlib import Path

import learned_cycle_memory as base

custody = base.custody
SEEDS = (179, 181, 191, 193, 197)
REGIMES = ((0.98, 0.8), (0.999, 0.8), (0.9999, 0.8))
CHECKS = (64, 256, 1024)
CONFIG = {**base.CONFIG, "tolerance": 1e-6}
ARM_SECONDS, START_WINDOW = 60, 300


def sources():
    return {
        **base.sources(),
        str(Path(__file__).resolve()): custody.sha(Path(__file__)),
    }


def tape():
    rng = random.Random(20261011)
    batches = []
    for event in range(1024):
        signs = [-1, 1] * 4
        rng.shuffle(signs)
        batches.append(
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
    return batches


def cue_bound(gain, bias=0.0, maximum_wrong_state=1.0):
    if gain <= 1:
        return None
    return gain * maximum_wrong_state + math.acosh(math.sqrt(gain)) + abs(bias)


def freeze(root, historical):
    root.mkdir(parents=True, exist_ok=False)
    custody.atomic(root / "data.json", tape())
    custody.atomic(root / "founders.json", {str(s): base.initial(s) for s in SEEDS})
    custody.atomic(
        root / "protocol.json",
        {
            "schema": "cycle-write-confirmation/1",
            "sources": sources(),
            "seeds": SEEDS,
            "regimes": REGIMES,
            "checks": CHECKS,
            "primary_checkpoint": 1024,
            "config": CONFIG,
            "data_sha256": custody.sha(root / "data.json"),
            "founders_sha256": custody.sha(root / "founders.json"),
            "historical_controls": {
                "path": str(historical),
                "protocol_sha256": custody.sha(historical / "protocol.json"),
                "verification_sha256": custody.sha(historical / "verification.json"),
                "scope": "Earlier flat/history controls are historical, not contemporary matched arms. Original 1e-10 refusals and failed gates remain unchanged.",
            },
            "training": "15 cycle-only arms, paired small random three-parameter founders; 1024 ordered balanced 16-row actual body batches. Private row states all zero; only qualified parameter proposals commit. Batch learning is supervised attractor acquisition, not temporal credit. Every stage continues the same parameter trajectory.",
            "evaluation": "At 64/256/1024 copy immutable parameters into an evaluation owner with zero initial state. 539 free queries per check: both cue writes, blank delays 1/8/128, opposite-cue overwrite plus 128 blanks, state-only erasure, and full body/state reset. Same explicit resets and bit gates as the historical probe. Evaluation leaves training parameters/state unchanged; no teacher-derived query initialization.",
            "primary": "Per regime all five arms must complete 1024 qualified admissions and all three full 539-query evaluations, with unchanged sources and no censors. Primary is all five bit-memory gates at 1024: signed response >= .25 for write/hold/overwrite and absolute neutral response <= .05. Show 64/256 unconditionally; never select successful seeds/checkpoints. Exact-amplitude MAE is separate. This tests acquiring usable cyclic memory, not superior matched performance.",
            "cue_analysis": "For g>1, w>0, state bound S and |bias|<=B, w>g*S+acosh(sqrt(g))+B suffices to remove all wrong-sign stationary states under the opposite cue. Then p has the correct sign and 1−g*(1−p²)>0 throughout the wrong half interval, so the negative gradient points across zero; the positive state prior reinforces it. This bound is sufficient, not necessary. Also report the bound using actual held-state magnitude. Clamped teacher fit does not guarantee switching.",
            "teacher_limits": [
                {
                    "write": a,
                    "hold": h,
                    "gain": math.atanh(h) / h,
                    "cue_weight": math.atanh(a) - a * math.atanh(h) / h,
                    "all_state_sufficient_bound": cue_bound(math.atanh(h) / h),
                }
                for a, h in REGIMES
            ],
            "precision": "Standard public 1e-6 tolerance is frozen before this new experiment. Old 1e-10 receipts are unchanged. This is not a paired precision sweep and cannot retrospectively qualify an old refused admission.",
            "limits": {
                "arm_seconds": ARM_SECONDS,
                "serial_start_window_seconds": START_WINDOW,
                "planned_arms": 15,
                "expected_queries_per_arm": 1617,
                "policy": "Start only when the full 60-second allowance remains; final bookkeeping may outlast the window. Retain all not-started arms. Raw projection must be checked below 100 MB before launch.",
            },
        },
    )


def validate(root):
    p = custody.read(root / "protocol.json")
    assert p["sources"] == sources()
    assert p["data_sha256"] == custody.sha(root / "data.json")
    assert p["founders_sha256"] == custody.sha(root / "founders.json")
    return p


def evaluate(call, theta, write, hold, checkpoint, rows=None):
    """Independent evaluation owner; only qualified native activity is retained."""
    state = 0.0
    rows = [] if rows is None else rows

    def query(cue, bit, identity, expected, scored=True):
        nonlocal state
        r = call(
            base.inputs("cycle", cue, bit),
            (state,),
            theta,
            identity=f"check{checkpoint}:{identity}",
            checkpoint=checkpoint,
        )
        state = r["state"][0]
        audit = base.scalar(cue, state, *theta)
        assert (
            base.projected_stationarity(state, audit["gradient"])
            <= CONFIG["tolerance"] * 1.0001
        )
        rows.append(
            {
                "identity": identity,
                "cue": cue,
                "body_bit": bit,
                "state": state,
                "expected": expected,
                "scored": scored,
                "qualified": r["qualified"],
                "absolute_error": abs(state - expected),
            }
        )
        return state

    # Reset chronology is deterministic and reconstructed by the identity plan.
    query(0, 0, "cold-neutral", 0)
    for sign in (-1, 1):
        state = 0.0
        written = query(sign, sign, f"write:{sign}", sign * write)
        for delay in base.DELAYS:
            state = written
            for tick in range(1, delay + 1):
                query(0, sign, f"hold:{sign}:{delay}:{tick}", sign * hold)
        query(-sign, -sign, f"overwrite:{sign}", -sign * write)
        for tick in range(1, 129):
            query(0, -sign, f"overwritten-hold:{sign}:{tick}", -sign * hold)
        state = 0.0
        query(0, -sign, f"erased-state-history-retained:{sign}", -sign * hold, False)
        state = 0.0
        query(0, 0, f"full-reset-neutral:{sign}", 0)
    return rows


def run_arm(root, seed, regime):
    out = root / f"regime{regime}-seed{seed}"
    out.mkdir(exist_ok=False)
    theta = tuple(custody.read(root / "founders.json")[str(seed)])
    started, accepted, returned = time.monotonic(), 0, 0
    training_work, query_work = Counter(), Counter()
    status, failure, unknown = "complete", None, False
    checks = [
        {
            "checkpoint": n,
            "status": "not_started",
            "queries": 0,
            "bit_memory_gate": False,
        }
        for n in CHECKS
    ]
    attempts, refusals = Counter(), Counter()
    last_good = theta
    write, hold = REGIMES[regime]

    def alarm(*_):
        raise TimeoutError("arm deadline")

    prior_alarm = signal.signal(signal.SIGALRM, alarm)

    def call(values, state, parameters, *, identity, checkpoint=None, clamps=None):
        nonlocal returned, unknown
        learning = clamps is not None
        intent = {
            "identity": identity,
            "checkpoint": checkpoint,
            "learn": learning,
            "inputs": values,
            "initial_state": state,
            "parameters_before": parameters,
            "clamps": clamps or {},
            "status": "started",
        }
        custody.atomic(out / "current-call.json", intent)
        remaining = ARM_SECONDS - (time.monotonic() - started)
        if remaining <= 0:
            custody.atomic(
                out / "current-call.json", {**intent, "status": "not_started_deadline"}
            )
            raise TimeoutError("deadline before solve")
        attempts["training" if learning else "inference"] += 1
        tick = time.perf_counter()
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            result = base.settle(
                base.graph("cycle"),
                values,
                state,
                parameters[:2],
                parameters[2:],
                learn=learning,
                clamps=clamps,
                _batch_size=16 if learning else 1,
                **CONFIG,
            )
        except Exception as exc:
            signal.setitimer(signal.ITIMER_REAL, 0)
            unknown = True
            custody.atomic(
                out / "current-call.json",
                {
                    **intent,
                    "status": "interrupted",
                    "unknown_work": True,
                    "failure": repr(exc),
                    "seconds": time.perf_counter() - tick,
                },
            )
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        returned += 1
        (training_work if learning else query_work).update(result["work"])
        receipt = {
            **intent,
            "status": "returned",
            "seconds": time.perf_counter() - tick,
            "result": {k: v for k, v in result.items() if k != "energy_history"},
            "energy_history_sha256": custody.digest(
                custody.encoded(result["energy_history"])
            ),
            "energy_history_length": len(result["energy_history"]),
        }
        with (out / "calls.jsonl").open("a") as stream:
            stream.write(custody.encoded(receipt) + "\n")
        custody.atomic(out / "current-call.json", receipt)
        if not result["qualified"]:
            refusals["training" if learning else "inference"] += 1
            raise RuntimeError(f"Refused {identity}: {result['reason']}")
        if not learning:
            assert (*result["weights"], *result["biases"]) == parameters
        return result

    try:
        for event, batch in enumerate(custody.read(root / "data.json"), start=1):
            values = tuple(
                v
                for row in batch
                for v in base.inputs("cycle", row["cue"], row["body_bit"])
            )
            clamps = {
                i: row["body_bit"] * (write if row["tick"] == 0 else hold)
                for i, row in enumerate(batch)
            }
            r = call(
                values, (0.0,) * 16, theta, identity=f"batch{event}", clamps=clamps
            )
            theta = (*r["weights"], *r["biases"])
            accepted += 1
            last_good = theta
            custody.atomic(
                out / "last-completed.json",
                {"parameters": theta, "state": [0.0], "admissions": accepted},
            )
            if event in CHECKS:
                custody.atomic(
                    out / f"checkpoint{event}.json",
                    {
                        "parameters": theta,
                        "state": [0.0],
                        "admissions": accepted,
                        "training_work": dict(training_work),
                        "protocol_sha256": custody.sha(root / "protocol.json"),
                    },
                )
                check = checks[CHECKS.index(event)]
                check["status"] = "started"
                rows = []
                try:
                    evaluate(call, theta, write, hold, event, rows)
                finally:
                    check["queries"] = len(rows)
                    custody.atomic(out / f"queries{event}.json", rows)
                    custody.atomic(out / "checks.json", checks)
                held = max(
                    abs(row["state"])
                    for row in rows
                    if row["identity"] in ("hold:-1:128:128", "hold:1:128:128")
                )
                scored = [row for row in rows if row["scored"]]
                check.update(
                    {
                        "checkpoint": event,
                        "status": "complete",
                        "parameters": theta,
                        "queries": len(rows),
                        "bit_memory_gate": base.bit_gate(rows, len(rows) == 539),
                        "free_target_mae": sum(row["absolute_error"] for row in scored)
                        / len(scored),
                        "minimum_signed_response": min(
                            row["state"] * math.copysign(1, row["expected"])
                            for row in scored
                            if row["expected"]
                        ),
                        "all_state_sufficient_cue_bound": cue_bound(theta[1], theta[2]),
                        "held_interval_sufficient_cue_bound": cue_bound(
                            theta[1], theta[2], held
                        ),
                        "held_magnitude": held,
                        "training_work": dict(training_work),
                        "inference_work_so_far": dict(query_work),
                    }
                )
                custody.atomic(out / "checks.json", checks)
    except TimeoutError as exc:
        status, failure = "timeout", str(exc)
    except Exception:  # noqa: BLE001 - Preserve complete failure evidence.
        status, failure = "error", traceback.format_exc()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior_alarm)
        custody.atomic(
            out / "last-completed.json",
            {"parameters": last_good, "state": [0.0], "admissions": accepted},
        )
        custody.atomic(out / "checks.json", checks)
        unchanged = sources() == custody.read(root / "protocol.json")["sources"]
        journal = out / "calls.jsonl"
        manifest = (
            {"bytes": journal.stat().st_size, "sha256": custody.sha(journal)}
            if journal.exists()
            else None
        )
        if time.monotonic() - started > ARM_SECONDS:
            status, failure = "timeout", failure or "deadline during bookkeeping"
        if not unchanged:
            status, failure = "error", "frozen source changed"
        complete = (
            status == "complete"
            and accepted == 1024
            and [c["checkpoint"] for c in checks] == list(CHECKS)
            and all(c["status"] == "complete" and c["queries"] == 539 for c in checks)
            and not unknown
        )
        report = {
            "seed": seed,
            "regime": regime,
            "status": status,
            "failure": failure,
            "complete": complete,
            "accepted_admissions": accepted,
            "returned_calls": returned,
            "unknown_work": unknown,
            "attempts": dict(attempts),
            "refusals": dict(refusals),
            "checks": checks,
            "seconds": time.monotonic() - started,
            "primary_pass": complete and checks[-1]["bit_memory_gate"],
            "protocol_sha256": custody.sha(root / "protocol.json"),
            "training_work": dict(training_work),
            "inference_work": dict(query_work),
            "sources_unchanged": unchanged,
            "journal": manifest,
        }
        custody.atomic(out / "result.json", report)
        if time.monotonic() - started > ARM_SECONDS and report["status"] == "complete":
            report.update(
                status="timeout",
                failure="deadline during final receipt",
                complete=False,
                primary_pass=False,
                seconds=time.monotonic() - started,
            )
            custody.atomic(out / "result.json", report)
    return report


def run(root):
    validate(root)
    if (root / "execution.json").exists():
        raise ValueError("Preserve previous campaign")
    started, reports = time.monotonic(), []
    for seed in SEEDS:
        for regime in range(len(REGIMES)):
            if START_WINDOW - (time.monotonic() - started) < ARM_SECONDS:
                r = {
                    "seed": seed,
                    "regime": regime,
                    "status": "not_started_deadline",
                    "complete": False,
                    "primary_pass": False,
                }
            else:
                r = run_arm(root, seed, regime)
            reports.append(r)
            custody.atomic(root / "execution.json", reports)
    custody.atomic(
        root / "summary.json",
        {
            "outcomes": reports,
            "seconds": time.monotonic() - started,
            "conclusions": [
                {
                    "regime": regime,
                    "all_five_complete": sum(r["regime"] == regime for r in reports)
                    == 5
                    and all(r["complete"] for r in reports if r["regime"] == regime),
                    "all_five_primary_pass": sum(r["regime"] == regime for r in reports)
                    == 5
                    and all(
                        r["primary_pass"] for r in reports if r["regime"] == regime
                    ),
                }
                for regime in range(len(REGIMES))
            ],
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("freeze", "run"))
    p.add_argument("root", type=Path)
    p.add_argument("--historical", type=Path)
    a = p.parse_args()
    if a.command == "freeze":
        if a.historical is None:
            p.error("freeze requires --historical verified prior run")
        freeze(a.root.resolve(), a.historical.resolve())
    else:
        run(a.root.resolve())
