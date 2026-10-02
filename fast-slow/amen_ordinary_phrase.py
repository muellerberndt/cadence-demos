"""Freeze one actual Amen phrase, then run three discarded runtime preflights.

Only public dev1 Brain/Cortex calls are used. This is not the 1,024-admission
study, a model-selection command, a musical-quality gate, or a new learning law.
Run with the released core on PYTHONPATH and cadence/.venv/bin/python. The
supervisor caps each fresh worker at 60 seconds, including imports and receipts.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
ARMS = ("A", "B", "C")
SEED, STEPS, EVENTS, PREFLIGHT = 1103, 8, 256, 32
CAP_SECONDS = 60
STORAGE_BYTES = 40_000_000
CORE = {
    "_repair.py": "76f57fcdffad1e39b65e327af8a2ae26f89467dafa11520e96ac07a8ea67595a",
    "_tensor.py": "d5765b286c931863cf540d19133500f734b70270c1bf702d60476c8945d86ce9",
    "_validation.py": "05d09fd56ec96ef9315cfe569fa818a718795d1aedefd12d5b02bb619808b0ab",
    "brain.py": "93287ff9751a79065fadd462d94fc91f77a87650c28ec5c6c8bed30bd8363807",
    "column.py": "d3752d27227ca34dfc03134d792cc046fc41d96ac181f19be852a193d1eee203",
    "cortex.py": "270f963fa6ca1c91b0deb19ce0f440cd4881f79205fdd115f64ef23942463482",
    "ports.py": "f0ec46ba314ee20523ff603473256362ae84a1522e89d39751f082f278aa4dca",
    "__init__.py": "35f4f6e66da65c68cb3fbbb7c2004211088df1e3b17ffc9e907bf0523e6b0c81",
}
FINAL_GOAL = (
    "A patch-net equilibrium brain that is more scalable, more capable and more "
    "efficient than a transformer. Every Cadence result is measured against that "
    "goal at matched information, matched task and a declared resource model. "
    "The Amen jungle composer is the first test platform."
)
PRINCIPLES = (
    "The main hypothesis stays: a brain that settles in global equilibria. The "
    "building block stays as simple as possible, like in nature, and every part "
    "of the brain answers with a settled state of that same patch rule; a "
    "feed-forward readout or a copied input is a baseline, never a result. "
    "Natural evolution is preferred to design: any parameter that looks designed "
    "is a gene, picked by selection against the hand-set value, which stays as "
    "the control. Within a life only the patch rule learns; across lives the "
    "genome evolves."
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded(value) + "\n")
    temporary.replace(path)


def save_snapshot(path, text):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt") as handle:
        handle.write(text)
    temporary.replace(path)


def stream_module(path):
    spec = importlib.util.spec_from_file_location("phrase_event_stream", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public_core():
    import cadence

    directory = Path(cadence.__file__).resolve().parent
    if cadence.__version__ != "0.60.0.dev1":
        raise ValueError("exact public cadence 0.60.0.dev1 required")
    if {name: sha(directory / name) for name in CORE} != CORE:
        raise ValueError("released core source mismatch")
    return directory


def build(arm):
    from cadence import Cortex

    if arm not in ARMS:
        raise ValueError("unknown arm")
    c = Cortex(
        seed=SEED,
        device="cpu",
        dtype="float64",
        parameter_prior=0.4,
        state_prior=0.01,
        initial_scale=0.3,
        tolerance=1e-6,
        settle_budget=2048,
    )
    ports = (
        c.input("past", shape=504),
        c.input("heard", shape=72),
        c.input("clock", shape=8),
        c.input("wake", shape=()),
    )
    inputs = ports
    if arm != "A":
        hidden = c.column("hearing", patches=64, inputs=ports)
        inputs = (*ports, hidden)
    playing = c.column("playing", patches=71, inputs=inputs)
    c.output("event", shape=71, reads=playing)
    brain = c.build()
    topology(brain, arm)
    return brain


def topology(brain, arm):
    hidden = 0 if arm == "A" else 64
    graph = brain.graph
    expected = {("input", i, j) for j in range(hidden + 71) for i in range(585)}
    expected.update(
        ("state", i, j) for j in range(hidden, hidden + 71) for i in range(hidden)
    )
    if graph.n_inputs != 585 or graph.n_patches != hidden + 71:
        raise ValueError("phrase layout dimensions differ")
    if set(graph.edges) != expected or any(k == "residual" for k, _, _ in graph.edges):
        raise ValueError("ordinary complete-input bypass required; no residual edges")
    return {
        "patches": graph.n_patches,
        "inputs": graph.n_inputs,
        "connections": len(graph.edges),
        "parameters": len(brain.weights) + len(brain.biases),
        "residual_edges": 0,
    }


def select_phrase(amen, stream):
    """Read only candidate regions; never expand the full historical corpus."""
    import numpy as np

    fixture_dir = amen / "fixtures" / "reference-events-v9"
    fixture = read(fixture_dir / "fixture.json")
    if (
        digest({k: v for k, v in fixture.items() if k != "receipt_sha256"})
        != fixture["receipt_sha256"]
    ):
        raise ValueError("fixture receipt mismatch")
    if sha(fixture_dir / "arrays.npz") != fixture["arrays_sha256"]:
        raise ValueError("fixture arrays mismatch")
    examined = []
    with np.load(fixture_dir / "arrays.npz", allow_pickle=False) as arrays:
        for region in fixture["regions"]:
            name = region["id"]
            if name in stream.HELD_OUT:
                examined.append({"region": name, "decision": "held_out"})
                continue
            rows = arrays[name]
            examined.append(
                {
                    "region": name,
                    "rows": len(rows),
                    "decision": "selected" if len(rows) >= EVENTS else "too_short",
                }
            )
            if len(rows) >= EVENTS:
                events = stream.events_from_rows(
                    rows[:EVENTS],
                    arrays[name + "_profiles"][:EVENTS],
                    arrays["crop_profiles"],
                    targets="hard",
                )
                if events.shape != (EVENTS, 71) or not np.isfinite(events).all():
                    raise ValueError("invalid phrase events")
                return {
                    "region": name,
                    "start": 0,
                    "events": events.tolist(),
                    "row_ids": [[name, i] for i in range(EVENTS)],
                    "selection_trace": examined,
                    "fixture_sha256": sha(fixture_dir / "fixture.json"),
                    "arrays_sha256": sha(fixture_dir / "arrays.npz"),
                }
    raise ValueError("no non-held-out region has 256 events")


def example(data, tick, stream):
    """The actual transcribed prefix only; current/future targets cannot enter."""
    import numpy as np

    if not 0 <= tick < len(data["events"]):
        raise ValueError("row outside phrase")
    prior = ([stream.COUNT_IN] if tick < STEPS else []) + [
        stream.executed(e) for e in data["events"][max(0, tick - STEPS) : tick]
    ]
    window = np.zeros(STEPS * 72)
    for j, event in enumerate(prior):
        at = (STEPS - len(prior) + j) * 72
        window[at : at + 71], window[at + 71] = event, 1.0
    clock = [float(i == tick % 8) for i in range(8)]
    inputs = {
        "past": window[:504].tolist(),
        "heard": window[504:].tolist(),
        "clock": clock,
        "wake": float(tick == 0),
    }
    return inputs, {"event": stream.encode(data["events"][tick]).tolist()}


def freeze(root, amen):
    core = public_core()
    root.mkdir(parents=True, exist_ok=False)
    sources = {f"core/{name}": core / name for name in CORE}
    sources.update(
        {
            "app/stream.py": amen / "drsn_amen/stream.py",
            "harness/amen_ordinary_phrase.py": HERE,
            "harness/test_amen_ordinary_phrase.py": HERE.with_name(
                "test_amen_ordinary_phrase.py"
            ),
        }
    )
    pins = {}
    for name, path in sources.items():
        target = root / "sources" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        pins[name] = {"path": str(path.resolve()), "sha256": sha(target)}
    stream = stream_module(sources["app/stream.py"])
    data = select_phrase(amen, stream)
    write(root / "phrase.json", data)
    founders = {}
    for arm in ("A", "B"):
        brain = build(arm)
        path = root / f"founder-{arm}.json.gz"
        text = brain.snapshot()
        save_snapshot(path, text)
        founders[arm] = {
            "path": path.name,
            "sha256": sha(path),
            "snapshot_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "topology": topology(brain, arm),
        }
    founders["C"] = dict(founders["B"])
    p = {
        "schema": "amen-ordinary-phrase-preflight/1",
        "final_goal": FINAL_GOAL,
        "principles": PRINCIPLES,
        "sources": pins,
        "founders": founders,
        "phrase_sha256": sha(root / "phrase.json"),
        "arms": list(ARMS),
        "seed": SEED,
        "targets": "hard",
        "target_source": "estimate",
        "steps": STEPS,
        "phrase_rows": EVENTS,
        "training_indices": list(range(PREFLIGHT)),
        "query_indices": list(range(PREFLIGHT)),
        "methods": {"A": "observe_batch", "B": "observe_batch", "C": "observe"},
        "threads": 1,
        "device": "cpu",
        "dtype": "float64",
        "admission_budget": 8192,
        "query_budget": 2048,
        "seconds_per_arm": CAP_SECONDS,
        "storage_bytes": STORAGE_BYTES,
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": importlib.metadata.version("numpy"),
            "torch": importlib.metadata.version("torch"),
        },
        "scope": "Discarded runtime preflight only; no quality selection or full study authorization. "
        "B/C share one exact native founder; A differs in capacity and random coefficient allocation. "
        "A/B one-row batches preserve activity; C observe retains teaching-conditioned activity. "
        "All have 32 presentations and 32 parameter anchors. A/B/C all use hard targets. "
        "The historical flat smoke used soft targets, so it is not a matched predecessor. "
        "Actual prefix means transcribed executed event symbols, not measured PCM. "
        "Hard transcription labels are marked estimate, not authenticated body ACKs. "
        "Free MAE uses these same 32 training contexts, in decoded event units, without clamps; "
        "it is not held-out performance. No playback, listening or memory claim. "
        "Any later 1,024-admission study needs a separate reviewed freeze and fresh founders. "
        "No persisted preflight model may initialize it.",
        "cost_scope": "60 s subprocess wall cap includes imports, setup, all 96 possible calls, "
        "checkpointing and bookkeeping. Three arms run once each, with no retry. "
        "Call hashes plus nonparameter diagnostics are retained; checkpoint snapshots "
        "are compressed. A killed active call has unknown unreturned work. "
        "Storage is a soft stop checked between calls and at final closeout.",
    }
    write(root / "protocol.json", p)
    write(
        root / "freeze.json",
        {"protocol_sha256": sha(root / "protocol.json"), "learning_calls": 0},
    )
    return p


def bound(root):
    p = read(root / "protocol.json")
    if sha(root / "protocol.json") != read(root / "freeze.json")["protocol_sha256"]:
        raise ValueError("protocol changed")
    public_core()
    for name, pin in p["sources"].items():
        if (
            sha(pin["path"]) != pin["sha256"]
            or sha(root / "sources" / name) != pin["sha256"]
        ):
            raise ValueError(f"source changed: {name}")
    if sha(root / "phrase.json") != p["phrase_sha256"]:
        raise ValueError("phrase changed")
    for pin in p["founders"].values():
        if sha(root / pin["path"]) != pin["sha256"]:
            raise ValueError("founder changed")
    return p


def size(root):
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def compact(result):
    return {
        **{k: v for k, v in result.items() if k not in ("weights", "biases")},
        "full_result_sha256": digest(result),
        "parameters_sha256": digest({k: result[k] for k in ("weights", "biases")}),
    }


def returned_prefix(directory):
    """Reconcile flushed returns even when a killed worker's report lagged."""
    work, methods = Counter(), Counter()
    calls = accepted = 0
    damaged = False
    path = directory / "calls.jsonl"
    if path.exists():
        with path.open() as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    if row["ordinal"] != calls or row["status"] != "returned":
                        raise ValueError("noncontiguous return ledger")
                    work.update(row["result"]["work"])
                    methods[row["method"]] += 1
                    accepted += int(
                        row["phase"] == "train" and row["result"]["accepted"]
                    )
                    calls += 1
                except (KeyError, TypeError, ValueError):
                    damaged = True
                    break
    current = (
        read(directory / "current.json")
        if (directory / "current.json").exists()
        else {}
    )
    unknown = damaged or (
        current.get("status") == "started" and current["ordinal"] >= calls
    )
    return {
        "calls": calls,
        "accepted": accepted,
        "methods": dict(methods),
        "work": dict(work),
        "damaged_tail": damaged,
        "unknown_call_work": unknown,
    }


def worker(root, arm):
    started = time.monotonic()
    directory = root / arm
    directory.mkdir(exist_ok=False)
    report = {
        "arm": arm,
        "status": "started",
        "discarded": True,
        "calls": 0,
        "accepted": 0,
        "work": {},
        "mae_before": None,
        "mae_after": None,
        "setup_complete": False,
    }
    write(directory / "report.json", report)
    work = Counter()
    try:
        p = bound(root)
        import torch

        from cadence import Brain

        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        data = read(root / "phrase.json")
        stream = stream_module(Path(p["sources"]["app/stream.py"]["path"]))
        with gzip.open(root / p["founders"][arm]["path"], "rt") as handle:
            brain = Brain.from_snapshot(handle.read())
        topology(brain, arm)
        report["initial_snapshot_sha256"] = hashlib.sha256(
            brain.snapshot().encode()
        ).hexdigest()
        report["setup_complete"] = True
        write(directory / "report.json", report)

        def call(phase, tick):
            if time.monotonic() - started >= CAP_SECONDS or size(root) > STORAGE_BYTES:
                raise TimeoutError("soft time/storage cap before call")
            inputs, targets = example(data, tick, stream)
            method = "settle" if phase != "train" else p["methods"][arm]
            before = brain.snapshot()
            intent = {
                "ordinal": report["calls"],
                "phase": phase,
                "row_id": data["row_ids"][tick],
                "method": method,
                "inputs_sha256": digest(inputs),
                "targets_sha256": digest(targets) if phase == "train" else None,
                "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
                "status": "started",
            }
            write(directory / "current.json", intent)
            begin = time.perf_counter()
            if method == "settle":
                result = brain.settle(inputs, budget=p["query_budget"])
            elif method == "observe":
                result = brain.observe(
                    inputs, targets, budget=p["admission_budget"], source="estimate"
                )
            else:
                result = brain.observe_batch(
                    [(inputs, targets)], budget=p["admission_budget"], source="estimate"
                )
            seconds = time.perf_counter() - begin
            row = {
                **intent,
                "status": "returned",
                "seconds": seconds,
                "result": compact(result),
            }
            with (directory / "calls.jsonl").open("a") as handle:
                handle.write(encoded(row) + "\n")
                handle.flush()
            write(directory / "current.json", row)
            after = brain.snapshot()
            report["calls"] += 1
            work.update(result["work"])
            report["work"] = dict(work)
            if phase == "train" and result["accepted"]:
                report["accepted"] += 1
                save_snapshot(directory / "discarded-latest.json.gz", after)
            write(directory / "report.json", report)
            if not result["qualified"]:
                raise RuntimeError(f"refused {phase} row {tick}: {result['reason']}")
            if method == "settle" and before != after:
                raise ValueError("pure query changed continuation")
            if (
                method == "observe_batch"
                and json.loads(before)["state"] != json.loads(after)["state"]
            ):
                raise ValueError("one-row batch changed live activity")
            return result

        def measure(phase):
            error = 0.0
            for tick in p["query_indices"]:
                result = call(phase, tick)
                prediction = stream.decode(result["outputs"]["event"])
                error += sum(
                    abs(float(x) - y)
                    for x, y in zip(prediction, data["events"][tick], strict=True)
                )
            return error / (71 * len(p["query_indices"]))

        report["mae_before"] = measure("before")
        for tick in p["training_indices"]:
            call("train", tick)
        report["mae_after"] = measure("after")
        report["final_snapshot_sha256"] = hashlib.sha256(
            brain.snapshot().encode()
        ).hexdigest()
        report["status"] = "complete"
        bound(root)
    except Exception as error:  # noqa: BLE001 - retain every failed/capped arm.
        report.update(status="stopped", error=f"{type(error).__name__}: {error}")
    finally:
        report["returned_prefix"] = returned_prefix(directory)
        report["unknown_call_work"] = report["returned_prefix"]["unknown_call_work"]
        report["seconds"] = time.monotonic() - started
        write(directory / "report.json", report)
        report["seconds"] = time.monotonic() - started
        if report["seconds"] >= CAP_SECONDS or size(root) > STORAGE_BYTES:
            report["status"] = "censored"
        write(directory / "report.json", report)
    return report


def preflight(root):
    p = bound(root)
    with (root / "execution-intent.json").open("x") as handle:
        handle.write(
            encoded(
                {"protocol_sha256": sha(root / "protocol.json"), "arms": list(ARMS)}
            )
            + "\n"
        )
    rows = [{"arm": a, "status": "not_started", "discarded": True} for a in ARMS]
    write(root / "results.json", {"arms": rows, "full_study_authorized": False})
    environment = dict(os.environ)
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        environment[name] = "1"
    for row in rows:
        if size(root) > p["storage_bytes"]:
            break
        row["status"] = "started"
        write(root / "results.json", {"arms": rows, "full_study_authorized": False})
        begin = time.monotonic()
        with (root / f"{row['arm']}-stdout.log").open("w") as output:
            command = [
                sys.executable,
                str(HERE),
                "worker",
                "--out",
                str(root),
                "--arm",
                row["arm"],
            ]
            try:
                result = subprocess.run(
                    command,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=p["seconds_per_arm"],
                    env=environment,
                    check=False,
                )
                row["exit_code"] = result.returncode
            except subprocess.TimeoutExpired:
                row.update(status="censored", exit_code=None, external_timeout=True)
            except OSError as error:
                row.update(status="failed", exit_code=None, launch_error=str(error))
        row["outer_seconds"] = time.monotonic() - begin
        report = root / row["arm"] / "report.json"
        row["report"] = read(report) if report.exists() else None
        row["returned_prefix"] = returned_prefix(root / row["arm"])
        row["unknown_call_work"] = row["returned_prefix"]["unknown_call_work"]
        row["setup_complete"] = bool(
            row["report"] and row["report"].get("setup_complete")
        )
        if not row.get("external_timeout") and not row.get("launch_error"):
            row["status"] = row["report"]["status"] if row["report"] else "failed"
        if row.get("external_timeout") or row["outer_seconds"] >= CAP_SECONDS:
            row["status"] = "censored"
        elif row.get("exit_code") != 0:
            row["status"] = "failed"
        write(root / "results.json", {"arms": rows, "full_study_authorized": False})
    stable = True
    try:
        bound(root)
    except (OSError, ValueError):
        stable = False
    summary = {
        "arms": rows,
        "sources_data_unchanged": stable,
        "all_three_complete": all(
            r["status"] == "complete"
            and r["report"]["calls"] == 96
            and r["report"]["accepted"] == 32
            and r["returned_prefix"]["calls"] == 96
            and r["returned_prefix"]["accepted"] == 32
            and r["report"]["work"] == r["returned_prefix"]["work"]
            and r["setup_complete"]
            and not r["unknown_call_work"]
            for r in rows
        ),
        "full_study_authorized": False,
        "all_models_discarded": True,
    }
    write(root / "results.json", summary)
    summary["retained_bytes"] = size(root)
    summary["within_storage"] = summary["retained_bytes"] <= STORAGE_BYTES
    summary["preflight_complete"] = (
        summary["all_three_complete"] and stable and summary["within_storage"]
    )
    write(root / "results.json", summary)
    if size(root) > STORAGE_BYTES:
        summary.update(within_storage=False, preflight_complete=False)
        write(root / "results.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "preflight", "worker"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--amen", type=Path, default=HERE.parents[2] / "cadence-amen")
    parser.add_argument("--arm", choices=ARMS)
    args = parser.parse_args()
    root = args.out.resolve()
    if args.command == "freeze":
        freeze(root, args.amen.resolve())
        print(sha(root / "protocol.json"))
    elif args.command == "preflight":
        print(encoded(preflight(root)))
    else:
        if args.arm is None:
            parser.error("worker requires --arm")
        worker(root, args.arm)


if __name__ == "__main__":
    main()
