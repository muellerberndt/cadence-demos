"""Frozen acquisition prerequisites, not a test of autonomous control.

Teach fixed gains and a balanced mixture before interpreting recursive repair.
All parameters learn only through public witness admission. The original
self_correction.py and its reversal evidence are never changed or consumed.

    PYTHONPATH=<candidate>/src python acquisition_controls.py --out <newdir> --freeze-only
    PYTHONPATH=<candidate>/src python acquisition_controls.py --out <newdir> --run-pilot

The pilot has twelve paired cases, one development seed, at most three local
workers, 50 seconds per arm and 120 seconds per case. Confirmation requires a
separate explicit --case invocation after reviewing the pilot selection.
"""

from __future__ import annotations

import argparse
import itertools
import math
import os
import random
import statistics
import subprocess
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import self_correction as base

from cadence import Brain, Cortex

CONDITIONS = ("fixed_positive", "fixed_negative", "balanced_mixed")
LAYOUTS = ("small", "interaction")
PRIORS = (0.1, 0.01)
CHECKPOINTS = (32, 128, 512)
SEEDS = (2, 7, 11, 19, 29)
ARM_SECONDS, CASE_SECONDS = 50, 120
MAX_BYTES = 80_000_000
THRESHOLD = 0.03
BASE_SHA = "1cd811d01a04d42166e360d0ddeac3c03670d6239cde5a5c38fb9625df94fc38"


def sources():
    assert base.sha(Path(base.__file__)) == BASE_SHA
    return {
        **base.source_identity(),
        str(Path(__file__).resolve()): base.sha(Path(__file__)),
    }


def make_brain(seed, arm, layout, prior):
    if arm not in base.ARMS or layout not in LAYOUTS or prior not in PRIORS:
        raise ValueError("Outside frozen architecture/prior grid")
    cortex = Cortex(
        seed=seed,
        device="python",
        dtype="float64",
        settle_budget=2048,
        tolerance=1e-6,
        state_prior=0.01,
        parameter_prior=prior,
    )
    previous = cortex.input("previous", shape=2)
    present = cortex.input("present", shape=2)
    memory = cortex.column("context", patches=2, inputs=previous)
    past = cortex.column("past_model", patches=2, inputs=(previous, memory))
    width = 2 if layout == "small" else 4
    if arm == "ordinary":
        interaction = cortex.column(
            "interaction", patches=width, inputs=(previous, present, past, memory)
        )
    else:
        interaction = cortex.observer(
            "interaction",
            patches=width,
            inputs=(previous, present, past),
            observes=past,
        )
    future = (
        interaction
        if layout == "small"
        else cortex.column("future_model", patches=2, inputs=interaction)
    )
    cortex.output("past", shape=2, reads=past)
    cortex.output("future", shape=2, reads=future)
    brain = cortex.build()
    expected = (6, 28) if layout == "small" else (10, 52)
    assert (brain.graph.n_patches, len(brain.weights)) == expected
    assert len(brain.weights) + len(brain.biases) == (34 if layout == "small" else 62)
    return brain


def match(ordinary, observer, layout):
    left = dict(zip(ordinary.graph.edges, ordinary.weights, strict=True))
    right = dict(zip(observer.graph.edges, observer.weights, strict=True))
    shared = left.keys() & right.keys()
    width = 2 if layout == "small" else 4
    assert len(shared) == (24 if layout == "small" else 44)
    assert all(left[key] == right[key] for key in shared)
    replacements = []
    for source, target in itertools.product(range(2), range(4, 4 + width)):
        old, new = ("state", source, target), ("residual", source + 2, target)
        assert left[old] == right[new]
        replacements.append({"ordinary": old, "observer": new, "initial": left[old]})
    assert ordinary.biases == observer.biases and ordinary.state == observer.state
    return {
        "shared_edges": len(shared),
        "initial_shared_exact": True,
        "replacements": replacements,
    }


def gains(condition):
    return {
        "fixed_positive": (0.3,),
        "fixed_negative": (-0.3,),
        "balanced_mixed": (-0.3, 0.3),
    }[condition]


def corpus(condition, phase, count, seed):
    rng = random.Random(seed)
    cells = list(itertools.product(gains(condition), (-1, 1), (-1, 1)))
    assert count % len(cells) == 0
    records = []
    for cell, (gain, old_sign, new_sign) in enumerate(cells):
        for _ in range(count // len(cells)):
            previous = rng.uniform(-0.5, 0.5)
            executed, candidate = base.action(rng, old_sign), base.action(rng, new_sign)
            present = 0.8 * previous + gain * executed
            record = base.row(
                phase, len(records), previous, executed, present, candidate, gain, gain
            )
            record["stratum"] = cell
            records.append(record)
    return records


def tape(condition):
    offset = 100 * CONDITIONS.index(condition)
    return {
        "train": corpus(condition, "train", 512, 20261101 + offset),
        "development": corpus(condition, "development", 128, 20261102 + offset),
        "confirmation": corpus(condition, "confirmation", 128, 20261103 + offset),
    }


def replay(rows):
    cells = sorted({row["stratum"] for row in rows})
    take = 16 // len(cells)
    rng = random.Random(20261111)
    schedule = []
    for _ in range(16):
        pools = {
            cell: [i for i, row in enumerate(rows) if row["stratum"] == cell]
            for cell in cells
        }
        for values in pools.values():
            rng.shuffle(values)
        for batch in range(32):
            selected = [
                index
                for cell in cells
                for index in pools[cell][batch * take : (batch + 1) * take]
            ]
            rng.shuffle(selected)
            schedule.append(selected)
    assert len(schedule) == 512 and all(len(row) == 16 for row in schedule)
    return schedule


def case_id(seed, condition, layout, prior):
    return f"seed{seed}-{condition}-{layout}-beta{str(prior).replace('.', 'p')}"


def specifications():
    result = []
    for seed, condition, layout, prior in itertools.product(
        SEEDS, CONDITIONS, LAYOUTS, PRIORS
    ):
        if seed != 2 and condition != "balanced_mixed":
            continue
        result.append(
            {
                "id": case_id(seed, condition, layout, prior),
                "seed": seed,
                "condition": condition,
                "layout": layout,
                "parameter_prior": prior,
                "parameters": 34 if layout == "small" else 62,
                "arm_order": list(
                    base.ARMS
                    if (len(result) + SEEDS.index(seed)) % 2 == 0
                    else reversed(base.ARMS)
                ),
                "role": "development" if seed == 2 else "confirmation",
            }
        )
    return result


def freeze(out):
    out.mkdir(parents=True, exist_ok=True)
    path = out / "protocol.json"
    if path.exists():
        protocol = base.read(path)
        if protocol["sources"] != sources() or protocol["cases"] != specifications():
            raise ValueError("Frozen source or case grid changed")
        for relative, expected in protocol["files"].items():
            if base.sha(out / relative) != expected:
                raise ValueError(f"Frozen artifact changed: {relative}")
        return protocol
    if any(out.iterdir()):
        raise ValueError("Freeze requires an empty new directory")
    files, founders = {}, {}
    for condition in CONDITIONS:
        dataset = tape(condition)
        for name, value in (
            (f"tape-{condition}.json", dataset),
            (f"replay-{condition}.json", replay(dataset["train"])),
        ):
            base.atomic(out / name, value)
            files[name] = base.sha(out / name)
    for spec in specifications():
        brains = {
            arm: make_brain(spec["seed"], arm, spec["layout"], spec["parameter_prior"])
            for arm in base.ARMS
        }
        founders[spec["id"]] = match(
            brains["ordinary"], brains["observer"], spec["layout"]
        )
        for arm, brain in brains.items():
            name = f"founder-{spec['id']}-{arm}.json"
            (out / name).write_text(brain.snapshot())
            files[name] = base.sha(out / name)
    protocol = {
        "schema": "cadence-acquisition-controls/1",
        "sources": sources(),
        "files": files,
        "cases": specifications(),
        "founder_matches": founders,
        "checkpoints": CHECKPOINTS,
        "batch_size": 16,
        "unique_training_rows": 512,
        "epochs_at_checkpoints": [1, 4, 16],
        "arm_seconds": ARM_SECONDS,
        "case_seconds": CASE_SECONDS,
        "max_workers": 3,
        "artifact_stop_bytes": MAX_BYTES,
        "state_prior": 0.01,
        "parameter_priors": PRIORS,
        "settle_budget": 2048,
        "tolerance": 1e-6,
        "device": "python",
        "dtype": "float64",
        "quality": "All scored/diagnostic queries and training admissions qualified; per-gain MAE<=.03 for BOTH future heads;>=95% correct action-response signs on16histories",
        "selection": "Pilotseed2 development only; only complete paired cases with no refusals/errors/censors; smallest parameter count, then earliest shared passing checkpoint, then beta.1 before.01; both arms must pass same checkpoint",
        "confirmation": "Only selected balanced layout/prior/exposure; separately authorized seeds7,11,19,29; fresh frozen confirmation rows. Seed2 is not an independent confirmation replicate",
        "limits": [
            "Prediction on recorded candidate actions; no learned controller",
            "Neither hidden gain nor algebraic oracle is a model input or learning target",
            "No reversal tape or switch metric is used for training or selection",
            "512-row fixed corpus is replayed, not expanded at later checkpoints",
            "Both arms share raw information, known-past clamps, row order, patch law and initial common coefficients",
            "34-versus62 parameters is a capacity contrast; observer-versusordinary is compared only within layout",
            "Parameter prior anchors each admission's starting parameters; it is adaptation resistance, not zero-centered decay",
            "Only real future witnesses are admitted; hypothetical full-witness queries are diagnostic and never scored as forecasts",
            "No early-success stopping or deletion; retain all12pilot cases and allplanned checkpoint outcomes",
            "Failure to acquire is inconclusive about recursive benefit; equal ceilings do not imply equal actual work",
        ],
    }
    base.atomic(path, protocol)
    return base.read(path)


def rms(values):
    values = list(values)
    return (
        math.sqrt(sum(value * value for value in values) / len(values))
        if values
        else 0.0
    )


def replacement_indices(brain, arm, layout):
    width = 2 if layout == "small" else 4
    return [
        i
        for i, (kind, source, target) in enumerate(brain.graph.edges)
        if target in range(4, 4 + width)
        and (
            (arm == "ordinary" and kind == "state" and source in (0, 1))
            or (arm == "observer" and kind == "residual" and source in (2, 3))
        )
    ]


def gate_score(records):
    forecasts = [record for record in records if record["kind"] == "forecast"]
    secants = [record for record in records if record["kind"] == "secant"]
    by_gain = {}
    for gain in sorted({record["gain"] for record in forecasts}):
        selected = [record for record in forecasts if record["gain"] == gain]
        by_gain[str(gain)] = [
            statistics.mean(row["absolute_error"][axis] for row in selected)
            for axis in (0, 1)
        ]
    signs = []
    for i in range(0, len(secants), 2):
        pair = secants[i : i + 2]
        if len(pair) == 2:
            signs.append(
                (pair[1]["future"][0] - pair[0]["future"][0]) * pair[0]["gain"] > 0
            )
    diagnostics = [
        record for record in records if record["kind"] == "full_clamp_diagnostic"
    ]
    full = (
        len(forecasts) == 128
        and len(secants) == 32
        and len(diagnostics) == 4 * len(by_gain)
    )
    qualified = full and all(record["qualified"] for record in records)
    passed = (
        qualified
        and all(error <= THRESHOLD for errors in by_gain.values() for error in errors)
        and sum(signs) / len(signs) >= 0.95
    )
    return {
        "passed": passed,
        "complete": full,
        "all_queries_qualified": qualified,
        "per_gain_future_mae": by_gain,
        "correct_response_signs": sum(signs),
        "response_sign_queries": len(signs),
        "forecast_past_residual_rms": rms(
            v for row in forecasts for v in row["past_errors"]
        ),
    }


def run_arm(out, spec, arm, protocol, maximum):
    folder = out / "results" / spec["id"] / arm
    folder.mkdir(parents=True, exist_ok=False)
    brain = Brain.from_snapshot((out / f"founder-{spec['id']}-{arm}.json").read_text())
    started = time.perf_counter()
    deadline = started + ARM_SECONDS
    dataset = base.read(out / f"tape-{spec['condition']}.json")
    batches = base.read(out / f"replay-{spec['condition']}.json")
    heldout = dataset[spec["role"]]
    special = replacement_indices(brain, arm, spec["layout"])
    origin = [brain.weights[i] for i in special]
    total_work, accepted, presentations, calls, failures = Counter(), 0, 0, 0, 0
    attempted_updates, attempted_presentations = 0, 0
    interrupted_calls, errored_calls, unknown_work_calls = 0, 0, 0
    checkpoints, scores = [], []
    status, reason = "running", None
    log = (folder / "calls.jsonl").open("x")

    def save(label):
        state = {
            "brain": brain.snapshot(),
            "call": calls - 1,
            "admissions": accepted,
            "presentations": presentations,
            "label": label,
        }
        state["brain_sha256"] = base.digest(state["brain"])
        base.atomic(folder / "latest.json", state)
        if label != "latest":
            name = f"checkpoint-{label}.json"
            base.atomic(folder / name, state)
            checkpoints.append({"file": name, "sha256": base.sha(folder / name)})

    def execute(operation, info, training=False):
        nonlocal brain, accepted, presentations, calls, failures
        nonlocal attempted_updates, attempted_presentations
        nonlocal interrupted_calls, errored_calls, unknown_work_calls
        before = brain.snapshot()
        info = {"ordinal": calls, "before_sha256": base.digest(before), **info}
        if training:
            attempted_updates += 1
            attempted_presentations += 16
        base.atomic(folder / "inflight.json", info)
        tick = time.perf_counter()
        old_weights = [brain.weights[i] for i in special]
        try:
            result = base.limited_call(operation, deadline - tick)
        except Exception as error:
            brain = Brain.from_snapshot(before)
            interrupted_calls += isinstance(error, base.ArmTimeout)
            errored_calls += not isinstance(error, base.ArmTimeout)
            unknown_work_calls += 1
            info.update(
                status="interrupted" if isinstance(error, base.ArmTimeout) else "error",
                seconds=time.perf_counter() - tick,
                unknown_work=True,
                reason=f"{type(error).__name__}: {error}",
                after_sha256=base.digest(brain.snapshot()),
            )
            log.write(base.encoded(info) + "\n")
            log.flush()
            calls += 1
            (folder / "inflight.json").unlink()
            raise
        info.update(
            seconds=time.perf_counter() - tick,
            status="returned",
            qualified=result["qualified"],
            stationarity=result["stationarity"],
            reason=result["reason"],
            work=result["work"],
            sweeps=result["sweeps"],
        )
        assert result["qualified"] == (result["stationarity"] <= 1e-6)
        total_work.update(result["work"])
        failures += not result["qualified"]
        if training:
            assert (
                result["source"] == "witness"
                and result["accepted"] == result["qualified"]
            )
            accepted += int(result["accepted"])
            presentations += 16 * int(result["accepted"])
            info.update(
                source=result["source"],
                accepted=result["accepted"],
                event_id=result["event_id"],
                batch_size=result["batch_size"],
                past_residual_rms=rms(e for row in result["errors"] for e in row[2:4]),
                replacement_delta_rms=rms(
                    brain.weights[i] - old
                    for i, old in zip(special, old_weights, strict=True)
                ),
                replacement_from_founder_rms=rms(
                    brain.weights[i] - old
                    for i, old in zip(special, origin, strict=True)
                ),
            )
        else:
            assert before == brain.snapshot()
            info.update(
                future=list(result["outputs"]["future"]),
                past_errors=list(result["errors"][2:4]),
                state=list(result["state"]),
                errors=list(result["errors"]),
            )
        if not result["qualified"]:
            assert before == brain.snapshot()
        info["after_sha256"] = base.digest(brain.snapshot())
        log.write(base.encoded(info) + "\n")
        log.flush()
        calls += 1
        if training and result["accepted"]:
            save("latest")
        (folder / "inflight.json").unlink()
        return info

    def evaluate(update):
        results = []
        for record in heldout:
            inputs, past = base.known_query(record)
            info = execute(
                lambda inputs=inputs, past=past: brain.settle(inputs, targets=past),
                {
                    "kind": "forecast",
                    "update": update,
                    "row": record["index"],
                    "gain": record["audit"]["future_gain"],
                },
            )
            # Scored outputs came from the preceding past-only, immutable query.
            info["absolute_error"] = [
                abs(p - y)
                for p, y in zip(info["future"], record["future"], strict=True)
            ]
            results.append(info)
        cells = sorted({record["stratum"] for record in heldout})
        per_cell = 16 // len(cells)
        selected = [
            record
            for cell in cells
            for record in [row for row in heldout if row["stratum"] == cell][:per_cell]
        ]
        for record in selected:
            for candidate in (-0.5, 0.5):
                inputs = {
                    "previous": record["inputs"]["previous"],
                    "present": [record["past"][0], candidate],
                }
                info = execute(
                    lambda inputs=inputs, record=record: brain.settle(
                        inputs, targets={"past": record["past"]}
                    ),
                    {
                        "kind": "secant",
                        "update": update,
                        "row": record["index"],
                        "candidate": candidate,
                        "gain": record["audit"]["future_gain"],
                    },
                )
                results.append(info)
        for cell in cells:
            record = next(row for row in heldout if row["stratum"] == cell)
            inputs, targets = base.witness(record)
            results.append(
                execute(
                    lambda inputs=inputs, targets=targets: brain.settle(
                        inputs, targets=targets
                    ),
                    {
                        "kind": "full_clamp_diagnostic",
                        "update": update,
                        "row": record["index"],
                    },
                )
            )
        score = {
            "update_attempts": update,
            "admissions": accepted,
            "presentations": presentations,
            **gate_score(results),
            "all_training_qualified": failures == 0,
            "replacement_coefficients": [brain.weights[i] for i in special],
        }
        score["passed"] = score["passed"] and failures == 0
        scores.append(score)
        base.atomic(
            folder / f"gate-{update}.json", {"score": score, "queries": results}
        )

    try:
        save("initial")
        for update, indices in enumerate(batches[:maximum], 1):
            execute(
                lambda indices=indices: brain.observe_batch(
                    [base.witness(dataset["train"][i]) for i in indices],
                    source="witness",
                ),
                {"kind": "admission", "update": update, "indices": indices},
                training=True,
            )
            if update in CHECKPOINTS:
                save(str(update))
                evaluate(update)
                if (
                    sum(
                        path.stat().st_size for path in out.rglob("*") if path.is_file()
                    )
                    >= MAX_BYTES
                ):
                    raise base.ArmTimeout("artifact-size guard; all evidence preserved")
        if time.perf_counter() > deadline:
            raise base.ArmTimeout("arm cap after bookkeeping")
        status = "complete"
    except base.ArmTimeout as error:
        status, reason = "censored", str(error)
    except Exception as error:
        status, reason = "error", f"{type(error).__name__}: {error}"
        (folder / "error.txt").write_text(traceback.format_exc())
    finally:
        log.close()
    report = {
        "spec": spec,
        "arm": arm,
        "status": status,
        "reason": reason,
        "seconds": time.perf_counter() - started,
        "admissions": accepted,
        "presentations": presentations,
        "admitted_presentations": presentations,
        "attempted_updates": attempted_updates,
        "attempted_presentations": attempted_presentations,
        "interrupted_calls": interrupted_calls,
        "errored_calls": errored_calls,
        "unknown_work_calls": unknown_work_calls,
        "calls": calls,
        "refusals": failures,
        "work": dict(total_work),
        "checkpoints": checkpoints,
        "gates": scores,
        "protocol_sha256": base.sha(out / "protocol.json"),
        "ledger_sha256": base.sha(folder / "calls.jsonl"),
        "latest_sha256": base.sha(folder / "latest.json"),
        "sources_unchanged": sources() == protocol["sources"],
    }
    base.atomic(folder / "report.json", report)
    return report


def selected(pilot_reports):
    options = []
    for report in pilot_reports:
        spec = report["spec"]
        if spec["condition"] != "balanced_mixed" or len(report.get("arms", [])) != 2:
            continue
        if report["status"] != "complete" or any(
            arm["status"] != "complete" or arm["refusals"] for arm in report["arms"]
        ):
            continue
        if not all(arm["sources_unchanged"] for arm in report["arms"]):
            continue
        for update in CHECKPOINTS:
            if all(
                any(
                    gate["update_attempts"] == update and gate["passed"]
                    for gate in arm["gates"]
                )
                for arm in report["arms"]
            ):
                options.append(
                    (
                        spec["parameters"],
                        update,
                        PRIORS.index(spec["parameter_prior"]),
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


def run_case(out, identifier):
    protocol = freeze(out)
    spec = next(item for item in protocol["cases"] if item["id"] == identifier)
    maximum = 512
    if spec["role"] == "confirmation":
        choice = base.read(out / "pilot-summary.json")["selected"]
        if choice is None or any(
            spec[key] != choice[key] for key in ("layout", "parameter_prior")
        ):
            raise ValueError(
                "Confirmation is restricted to the declared pilot selection"
            )
        maximum = choice["updates"]
    folder = out / "results" / identifier
    if folder.exists():
        raise ValueError("Never overwrite or retry existing case evidence")
    arms = [run_arm(out, spec, arm, protocol, maximum) for arm in spec["arm_order"]]
    report = {
        "spec": spec,
        "arms": arms,
        "status": "complete"
        if all(arm["status"] == "complete" for arm in arms)
        else "incomplete",
    }
    base.atomic(folder / "report.json", report)
    return report


def launch(out, spec):
    name = spec["id"]
    env = dict(os.environ)
    env.update(
        {
            key: "1"
            for key in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        }
    )
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--out",
        str(out),
        "--case",
        name,
        "--worker",
    ]
    with (out / f"{name}.log").open("x") as log:
        process = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT, env=env
        )
        try:
            returncode = process.wait(timeout=CASE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            returncode = 124
    outcome = {"spec": spec, "returncode": returncode, "case_seconds_cap": CASE_SECONDS}
    base.atomic(out / f"execution-{name}.json", outcome)
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze-only", action="store_true")
    mode.add_argument("--run-pilot", action="store_true")
    mode.add_argument("--case")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    out = args.out.resolve()
    protocol = freeze(out)
    if args.freeze_only:
        print(
            base.encoded(
                {
                    "frozen": True,
                    "protocol_sha256": base.sha(out / "protocol.json"),
                    "pilot_cases": 12,
                }
            )
        )
        return 0
    if args.case:
        spec = next(item for item in protocol["cases"] if item["id"] == args.case)
        if args.worker:
            result = run_case(out, args.case)
            return 0 if result["status"] == "complete" else 2
        return launch(out, spec)["returncode"]
    pilot = [spec for spec in protocol["cases"] if spec["role"] == "development"]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        execution = list(executor.map(lambda spec: launch(out, spec), pilot))
    reports = [
        base.read(out / "results" / spec["id"] / "report.json")
        for spec in pilot
        if (out / "results" / spec["id"] / "report.json").exists()
    ]
    summary = {
        "protocol_sha256": base.sha(out / "protocol.json"),
        "execution": execution,
        "selected": selected(reports),
        "automatic_confirmation_launched": False,
        "case_reports": [
            {
                "id": report["spec"]["id"],
                "status": report["status"],
                "sha256": base.sha(
                    out / "results" / report["spec"]["id"] / "report.json"
                ),
            }
            for report in reports
        ],
    }
    base.atomic(out / "pilot-summary.json", summary)
    print(
        base.encoded(
            {
                "selected": summary["selected"],
                "cases": len(execution),
                "reports": len(reports),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
