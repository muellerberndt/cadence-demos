"""Bounded common-rule acquisition and delayed recursive correction experiment.

All parameter changes use public observe_batch. The slow target is a forecast
of the frozen fast founder's mean residual over a FUTURE block. Its prediction
is delivered one block later. Fast-only and conditioned descendants receive
the same final training rows and admissions; conditioned replay includes neutral
feedback to retain the independent action path. Validation is development only.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import cadence
from cadence import Brain, Cortex

from data import load, sha


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    temporary.replace(path)


def build(width, outputs, *, seed, slow=False, device="cpu"):
    c = Cortex(
        seed=seed,
        device=device,
        dtype="float64",
        parameter_prior=0.4,
        state_prior=0.01,
        settle_budget=4096,
    )
    senses = c.input("features", shape=width)
    if slow:
        reading = c.input("readback", shape=2 * outputs)
        lower = c.column("context", patches=8, inputs=(senses, reading))
        middle = c.observer("reflection", patches=4, observes=lower)
        out = c.observer("correction", patches=outputs, observes=(lower, middle))
    else:
        feedback = c.input("feedback", shape=outputs)
        out = c.column("habit", patches=outputs, inputs=(senses, feedback))
    c.output("answer", shape=outputs, reads=out)
    return c.build()


def query_copy(brain):
    return Brain.from_snapshot(brain.snapshot(), device="python", dtype="float64")


def query(brain, x, cue):
    return brain.settle({"features": x.tolist(), "feedback": cue.tolist()})


def forecasts(brain, sequences):
    output = []
    for sequence in sequences:
        states, errors = [], []
        for x, y in zip(sequence["x"], sequence["y"], strict=True):
            result = query(brain, x, np.zeros_like(y))
            if not result["qualified"]:
                raise RuntimeError(
                    "Flat founder refused while constructing slow targets"
                )
            states.append(result["state"])
            errors.append(result["errors"])
        output.append((np.asarray(states), np.asarray(errors)))
    return output


def slow_examples(sequences, readings, period):
    rows = []
    for sequence, (states, errors) in zip(sequences, readings, strict=True):
        if sequence["split"]:
            continue
        for t in range(0, len(states) - 2 * period + 1, period):
            # At t, only x[t] and founder state/error at t are input. The future
            # residual is a teaching target, never an input or deployed correction.
            future = slice(t + period, t + 2 * period)
            target = 0.5 * (sequence["y"][future] - states[future]).mean(0)
            rows.append(
                (
                    {
                        "features": sequence["x"][t].tolist(),
                        "readback": np.r_[states[t], errors[t]].tolist(),
                    },
                    {"answer": target.tolist()},
                )
            )
    return rows


def delayed_cues(slow, sequences, readings, period):
    cues, diagnostics = [], []
    for sequence, (states, errors) in zip(sequences, readings, strict=True):
        values = np.zeros_like(sequence["y"])
        for t in range(0, len(states) - period, period):
            started = time.perf_counter()
            result = slow.settle(
                {
                    "features": sequence["x"][t].tolist(),
                    "readback": np.r_[states[t], errors[t]].tolist(),
                }
            )
            diagnostics.append(
                dict(
                    sequence=sequence["name"],
                    source_tick=t,
                    qualified=result["qualified"],
                    seconds=time.perf_counter() - started,
                    sweeps=result["sweeps"],
                    work=result["work"],
                )
            )
            if result["qualified"]:
                values[t + period : min(t + 2 * period, len(states))] = result[
                    "outputs"
                ]["answer"]
        cues.append(values)
    return cues, diagnostics


def examples(sequences, cues=None):
    rows = []
    for i, sequence in enumerate(sequences):
        if sequence["split"]:
            continue
        for j, (x, y) in enumerate(zip(sequence["x"], sequence["y"], strict=True)):
            cue = np.zeros_like(y) if cues is None else cues[i][j]
            rows.append(
                (
                    {"features": x.tolist(), "feedback": cue.tolist()},
                    {"answer": y.tolist()},
                )
            )
    return rows


def fit(
    brain,
    rows,
    *,
    updates,
    seed,
    phase,
    ledger,
    deadline,
    batch=16,
    neutral_replay=False,
):
    rng = np.random.default_rng(seed)
    summary = dict(
        phase=phase,
        planned_updates=updates,
        attempted=0,
        accepted=0,
        presentations=0,
        seconds=0.0,
        status="complete",
    )
    started = time.monotonic()
    for index in range(updates):
        if time.monotonic() >= deadline:
            summary["status"] = "time_limit"
            break
        picks = rng.choice(len(rows), size=min(batch, len(rows)), replace=False)
        selected = []
        for j, pick in enumerate(picks):
            inputs, target = rows[pick]
            if neutral_replay and j % 2 == 0:
                inputs = {**inputs, "feedback": [0.0] * len(inputs["feedback"])}
            selected.append((inputs, target))
        then = time.perf_counter()
        result = brain.observe_batch(selected, source="estimate", budget=8192)
        elapsed = time.perf_counter() - then
        entry = dict(
            phase=phase,
            update=index,
            rows=picks.tolist(),
            accepted=result["accepted"],
            reason=result["reason"],
            stationarity=result["stationarity"],
            sweeps=result["sweeps"],
            seconds=elapsed,
            work=result["work"],
            neutral_replay=neutral_replay,
        )
        ledger.write(json.dumps(entry) + "\n")
        ledger.flush()
        summary["attempted"] += 1
        summary["accepted"] += int(result["accepted"])
        summary["presentations"] += len(selected)
        if (index + 1) % 8 == 0:
            print(
                json.dumps(
                    {
                        "phase": phase,
                        "updates": index + 1,
                        "accepted": summary["accepted"],
                        "seconds": round(time.monotonic() - started, 2),
                    }
                ),
                flush=True,
            )
    summary["seconds"] = time.monotonic() - started
    return summary


def metrics(prediction, target, domain):
    p, y = np.asarray(prediction), np.asarray(target)
    valid = np.isfinite(p).all(axis=1)
    out = {
        "cases": len(y),
        "qualified": int(valid.sum()),
        "refused": int((~valid).sum()),
        "mae_with_refusal_penalty_2": float(
            np.where(valid, np.nanmean(np.abs(p - y), axis=1), 2.0).mean()
        ),
    }
    if not valid.any():
        return out
    p, y = p[valid], y[valid]
    out["mae"] = float(np.abs(p - y).mean())
    if domain == "amen":
        drums, bass = y[:, 32] > 0, y[:, 58] > 0
        out.update(
            drum_presence_accuracy=float(((p[:, 32] > 0) == drums).mean()),
            bass_presence_accuracy=float(((p[:, 58] > 0) == bass).mean()),
            drum_identity_accuracy=float(
                (p[drums, :32].argmax(1) == y[drums, :32].argmax(1)).mean()
            )
            if drums.any()
            else None,
            bass_note_accuracy=float(
                (p[bass, 34:58].argmax(1) == y[bass, 34:58].argmax(1)).mean()
            )
            if bass.any()
            else None,
        )
    elif domain == "c64":
        out.update(
            pitch_mae_semitones=float(np.abs(p[:, ::2] - y[:, ::2]).mean() * 60),
            sounding_accuracy=float(((p[:, 1::2] > 0) == (y[:, 1::2] > 0)).mean()),
        )
    else:
        pred, actual = p.argmax(1), y.argmax(1)
        out["teacher_agreement"] = float((pred == actual).mean())
        out["balanced_agreement"] = float(
            np.mean([(pred[actual == a] == a).mean() for a in np.unique(actual)])
        )
    return out


def evaluate(brain, sequences, domain, cues=None, *, cap=256):
    predictions, targets, times, sweeps = [], [], [], []
    eligible = [
        (i, j)
        for i, s in enumerate(sequences)
        if s["split"]
        for j in range(len(s["x"]))
    ]
    # Fixed evenly spaced development rows, shared by every arm/checkpoint.
    picks = np.linspace(0, len(eligible) - 1, min(cap, len(eligible)), dtype=int)
    for pick in picks:
        i, j = eligible[pick]
        s = sequences[i]
        cue = np.zeros_like(s["y"][j]) if cues is None else cues[i][j]
        started = time.perf_counter()
        result = query(brain, s["x"][j], cue)
        times.append(time.perf_counter() - started)
        sweeps.append(result["sweeps"])
        predictions.append(
            result["outputs"]["answer"]
            if result["qualified"]
            else np.full_like(cue, np.nan)
        )
        targets.append(s["y"][j])
    return {
        **metrics(predictions, targets, domain),
        "query_median_ms": 1000 * float(np.median(times)),
        "query_p95_ms": 1000 * float(np.quantile(times, 0.95)),
        "median_sweeps": float(np.median(sweeps)),
    }


def evaluate_pair(fast, slow, sequences, domain, period, *, enabled=True):
    """Causal sequential feedback from actual actor state/error at each anchor.

    Fixture inputs are teacher-context observations. Slow solves are synchronous
    in this deterministic schedule simulation, but delivery is delayed one block.
    Report both owners' work/time; this is not asynchronous wall-clock performance.
    """
    predictions, targets, fast_times, slow_times, sweeps = [], [], [], [], []
    slow_refused, delivered = 0, 0
    for sequence in sequences:
        if not sequence["split"]:
            continue
        cue = np.zeros(sequence["y"].shape[1])
        pending = {}
        for tick, (x, y) in enumerate(zip(sequence["x"], sequence["y"], strict=True)):
            if tick in pending:
                cue = pending.pop(tick)
                delivered += 1
            started = time.perf_counter()
            result = query(fast, x, cue if enabled else np.zeros_like(cue))
            fast_times.append(time.perf_counter() - started)
            sweeps.append(result["sweeps"])
            predictions.append(
                result["outputs"]["answer"]
                if result["qualified"]
                else np.full_like(y, np.nan)
            )
            targets.append(y)
            if result["qualified"] and tick % period == 0:
                started = time.perf_counter()
                correction = slow.settle(
                    {
                        "features": x.tolist(),
                        "readback": [*result["state"], *result["errors"]],
                    }
                )
                slow_times.append(time.perf_counter() - started)
                slow_refused += int(not correction["qualified"])
                pending[tick + period] = (
                    np.asarray(correction["outputs"]["answer"])
                    if correction["qualified"]
                    else np.zeros_like(cue)
                )
    return {
        **metrics(predictions, targets, domain),
        "feedback_enabled": enabled,
        "schedule": "slow query every block; deliver one block later; teacher-context sequence",
        "delivered_blocks": delivered,
        "slow_refused": slow_refused,
        "fast_query_median_ms": 1000 * float(np.median(fast_times)),
        "fast_query_p95_ms": 1000 * float(np.quantile(fast_times, 0.95)),
        "slow_query_median_ms": 1000 * float(np.median(slow_times)),
        "fast_query_seconds": sum(fast_times),
        "slow_query_seconds": sum(slow_times),
        "median_fast_sweeps": float(np.median(sweeps)),
    }


def run(args):
    if args.device != "python":
        import torch

        torch.set_num_threads(1)
    args.out.mkdir(parents=True, exist_ok=False)
    sequences, metadata, _, _ = load(args.data)
    width, outputs = sequences[0]["x"].shape[1], sequences[0]["y"].shape[1]
    sources = {p.name: sha(p) for p in Path(__file__).parent.glob("*.py")}
    protocol = dict(
        schema="cadence.fast-slow-training/1",
        data_sha256=sha(args.data),
        data=metadata,
        args={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        sources=sources,
        cadence_version=cadence.__version__,
        python=platform.python_version(),
        protocol=f"{args.fast_updates} founder updates; {args.slow_updates} slow future-residual updates; matched {args.final_updates}-update fast-only/conditioned descendants; half conditioned rows use neutral feedback; no test selection",
        target_source="estimate",
        period=args.period,
        delay_ticks=args.period,
        nonclaims=[
            "No global asynchronous-equilibrium proof",
            "No evolutionary comparison",
            "Teacher-context validation is not free behavior",
            "Delayed cues precomputed offline are not a wall-clock runtime benchmark",
        ],
    )
    write(args.out / "protocol.json", protocol)
    started = time.monotonic()
    deadline = started + args.seconds
    fast = build(width, outputs, seed=args.seed, device=args.device)
    (args.out / "untrained.json").write_text(query_copy(fast).snapshot())
    report = dict(
        status="running",
        phases=[],
        evaluation={},
        protocol_sha256=sha(args.out / "protocol.json"),
        implementation=fast.inspect()["implementation"],
    )
    write(args.out / "report.json", report)
    ledger = (args.out / "training.jsonl").open("x")
    try:
        fast_rows = examples(sequences)
        report["evaluation"]["untrained"] = evaluate(
            query_copy(fast), sequences, metadata["domain"]
        )
        for stage in range(2):
            report["phases"].append(
                fit(
                    fast,
                    fast_rows,
                    updates=args.fast_updates // 2,
                    seed=args.seed + stage,
                    phase=f"founder_{stage}",
                    ledger=ledger,
                    deadline=deadline,
                )
            )
            report["evaluation"][f"founder_{stage}"] = evaluate(
                query_copy(fast), sequences, metadata["domain"]
            )
            (args.out / "founder.json").write_text(fast.snapshot())
            write(args.out / "report.json", report)
        founder = query_copy(fast)
        readings = forecasts(founder, sequences)
        slow = build(
            width, outputs, seed=args.seed + 1000, slow=True, device=args.device
        )
        report["phases"].append(
            fit(
                slow,
                slow_examples(sequences, readings, args.period),
                updates=args.slow_updates,
                seed=args.seed,
                phase="slow",
                ledger=ledger,
                deadline=deadline,
            )
        )
        (args.out / "slow.json").write_text(query_copy(slow).snapshot())
        cues, report["slow_queries"] = delayed_cues(
            query_copy(slow), sequences, readings, args.period
        )
        conditioning = examples(sequences, cues)
        hybrid = Brain.from_snapshot(fast.snapshot())
        for model, rows, name, replay in (
            (fast, fast_rows, "fast_only", False),
            (hybrid, conditioning, "conditioned", True),
        ):
            report["phases"].append(
                fit(
                    model,
                    rows,
                    updates=args.final_updates,
                    seed=args.seed + 3000,
                    phase=name,
                    ledger=ledger,
                    deadline=deadline,
                    neutral_replay=replay,
                )
            )
            (args.out / f"{name}.json").write_text(query_copy(model).snapshot())
            write(args.out / "report.json", report)
        report["evaluation"]["fast_only"] = evaluate(
            query_copy(fast), sequences, metadata["domain"]
        )
        report["evaluation"]["conditioned_delayed"] = evaluate(
            query_copy(hybrid), sequences, metadata["domain"], cues
        )
        report["evaluation"]["conditioned_disabled"] = evaluate(
            query_copy(hybrid), sequences, metadata["domain"]
        )
        # Reverse block contexts within each sequence as a declared perturbation,
        # never crossing a train/validation boundary or presenting teacher targets.
        scrambled = [c[::-1].copy() for c in cues]
        report["evaluation"]["conditioned_scrambled"] = evaluate(
            query_copy(hybrid), sequences, metadata["domain"], scrambled
        )
        report["sequential"] = {
            "enabled": evaluate_pair(
                query_copy(hybrid),
                query_copy(slow),
                sequences,
                metadata["domain"],
                args.period,
            ),
            "disabled": evaluate_pair(
                query_copy(hybrid),
                query_copy(slow),
                sequences,
                metadata["domain"],
                args.period,
                enabled=False,
            ),
        }
        report["status"] = (
            "complete"
            if all(p["status"] == "complete" for p in report["phases"])
            else "time_limit"
        )
        report["sources_unchanged"] = all(
            sha(Path(__file__).parent / name) == digest
            for name, digest in sources.items()
        )
        if not report["sources_unchanged"]:
            report["status"] = "source_changed"
    except Exception as error:
        report.update(status="error", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        ledger.close()
        report["seconds"] = time.monotonic() - started
        report["artifacts"] = {
            p.name: sha(p) for p in args.out.glob("*.json") if p.name != "report.json"
        }
        report["ledger_sha256"] = sha(args.out / "training.jsonl")
        write(args.out / "report.json", report)
    print(
        json.dumps({"status": report["status"], "evaluation": report["evaluation"]}),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--period", type=int, default=8)
    parser.add_argument("--fast-updates", type=int, default=64)
    parser.add_argument("--slow-updates", type=int, default=24)
    parser.add_argument("--final-updates", type=int, default=32)
    parser.add_argument("--seconds", type=float, default=900)
    run(parser.parse_args())
