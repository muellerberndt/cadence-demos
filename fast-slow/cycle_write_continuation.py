"""Final bounded continuation of all fifteen private cycle checkpoints.

This extends prior trajectories, not an independent confirmation. The original
1024-admission primary remains failed. No public API or patch law changes.
"""

from __future__ import annotations

import argparse
import math
import random
import shutil
import signal
import time
import traceback
from collections import Counter
from pathlib import Path

import cycle_write_confirmation as parent

base, custody = parent.base, parent.custody
SEEDS, REGIMES = parent.SEEDS, parent.REGIMES
CHECKS, CONFIG = (1536, 2048), dict(parent.CONFIG)
ARM_SECONDS, START_WINDOW = 60, 300
PARENT_PIN = "1c1c9de1bfed1265173c6d17baf1abb6f2ba89ce0dacd6c3e089b1d93e729506"
evaluate, cue_bound = parent.evaluate, parent.cue_bound


def sources():
    return {
        **parent.sources(),
        str(Path(__file__).resolve()): custody.sha(Path(__file__)),
    }


def tape():
    rng, batches = random.Random(20261013), []
    for event in range(1025, 2049):
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


def freeze(root, prior):
    assert custody.sha(Path(parent.__file__)) == PARENT_PIN
    p, v = (
        custody.read(prior / "protocol.json"),
        custody.read(prior / "verification.json"),
    )
    assert p["sources"] == parent.sources()
    assert v["valid"] and v["full_training_and_query_replay"]
    assert v["collector_sha256"] == PARENT_PIN
    assert v["protocol_sha256"] == custody.sha(prior / "protocol.json")
    assert len(v["cases"]) == 15
    cases = {(c["seed"], c["regime"]): c for c in v["cases"]}
    assert set(cases) == {(s, r) for s in SEEDS for r in range(3)}
    checkpoints = {}
    for key, case in cases.items():
        seed, regime = key
        assert case["complete"] and case["accepted_admissions"] == 1024
        cp = prior / f"regime{regime}-seed{seed}" / "checkpoint1024.json"
        data = custody.read(cp)
        assert data["admissions"] == 1024 and data["state"] == [0.0]
        assert data["protocol_sha256"] == v["protocol_sha256"]
        assert case["checks"][-1]["checkpoint"] == 1024
        assert data["parameters"] == case["checks"][-1]["parameters"]
        checkpoints[f"regime{regime}-seed{seed}.json"] = cp
    root.mkdir(parents=True, exist_ok=False)
    (root / "parent").mkdir()
    for name, path in {
        "protocol.json": prior / "protocol.json",
        "verification.json": prior / "verification.json",
        **checkpoints,
    }.items():
        shutil.copyfile(path, root / "parent" / name)
    custody.atomic(root / "data.json", tape())
    custody.atomic(
        root / "protocol.json",
        {
            "schema": "cycle-write-continuation/1",
            "sources": sources(),
            "seeds": SEEDS,
            "regimes": REGIMES,
            "checks": CHECKS,
            "starting_admissions": 1024,
            "primary_checkpoint": 2048,
            "config": CONFIG,
            "data_sha256": custody.sha(root / "data.json"),
            "parent": {
                "source_root": str(prior),
                "collector_sha256": PARENT_PIN,
                "files": {
                    p.name: custody.sha(p) for p in sorted((root / "parent").iterdir())
                },
            },
            "training": "Continue all fifteen qualified final 1024 parameter arrays. No founder restart or survivor selection. Another 1024 balanced 16-row actual body batches, data seed 20261013, event IDs1025..2048. Private training row states always zero; only qualified parameter proposals commit. New work counters exclude already reported parent work. Batch learning is supervised attractor acquisition, not temporal credit.",
            "evaluation": "At cumulative1536/2048 use the frozen parent 539-query evaluation and bit gate, with independent zero-start evaluation activity and immutable parameters. Both signs write, retain through1/8/128 blanks, overwrite with opposite cue, retain128 more blanks, and undergo declared state-only erasure/full reset. No output clamps or teacher-derived query initialization.",
            "primary": "Per regime all five arms must complete2048 admissions and both complete evaluations. Primary requires all five bit-memory gates at2048; show1536 and failed parent1024 unconditionally. This is one final bounded exposure continuation, not a new independent confirmation or a matched architecture comparison. Do not extend or choose successful seeds/checkpoints after seeing this tranche.",
            "historical_result": "The parent1024 experiment failed its primary in all three regimes. That result is immutable; any later success concerns additional exposure only. Historical flat/history controls remain separate. No public state-cycle API, residual-observer advantage, delayed credit or planning claim.",
            "limits": {
                "arm_seconds": ARM_SECONDS,
                "serial_start_window_seconds": START_WINDOW,
                "planned_arms": 15,
                "new_training_admissions_per_arm": 1024,
                "expected_queries_per_arm": 1078,
                "policy": "Start only with the full60-second allowance remaining. Final bookkeeping may outlast the300-second start window. Retain every not-started/censored outcome; project raw data below100MB before launch.",
            },
        },
    )


def validate(root):
    p = custody.read(root / "protocol.json")
    assert p["sources"] == sources()
    assert p["data_sha256"] == custody.sha(root / "data.json")
    assert p["parent"]["collector_sha256"] == PARENT_PIN
    assert set(p["parent"]["files"]) == {"protocol.json", "verification.json"} | {
        f"regime{r}-seed{s}.json" for s in SEEDS for r in range(3)
    }
    for name, digest in p["parent"]["files"].items():
        assert custody.sha(root / "parent" / name) == digest
    return p


def run_arm(root, seed, regime):
    out = root / f"regime{regime}-seed{seed}"
    out.mkdir(exist_ok=False)
    parent_checkpoint = custody.read(
        root / "parent" / f"regime{regime}-seed{seed}.json"
    )
    theta = tuple(parent_checkpoint["parameters"])
    started, accepted, returned = time.monotonic(), 1024, 0
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
        for event, batch in enumerate(custody.read(root / "data.json"), start=1025):
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
            and accepted == 2048
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
            "new_accepted_admissions": accepted - 1024,
            "returned_calls": returned,
            "unknown_work": unknown,
            "attempts": dict(attempts),
            "refusals": dict(refusals),
            "checks": checks,
            "seconds": time.monotonic() - started,
            "primary_pass": complete and checks[-1]["bit_memory_gate"],
            "protocol_sha256": custody.sha(root / "protocol.json"),
            "parent_checkpoint_sha256": custody.sha(
                root / "parent" / f"regime{regime}-seed{seed}.json"
            ),
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--parent", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        if args.parent is None:
            parser.error("freeze requires --parent verified 1024 run")
        freeze(args.root.resolve(), args.parent.resolve())
    else:
        run(args.root.resolve())
