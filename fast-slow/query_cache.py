"""Export source-valid old brains, then compare exact query kernels on their data.

Export uses the preserved checkpoint reader; run uses the candidate package and
loads the original repair source separately. No checkpoint hash is rewritten.
This measures frozen-parameter numerical work, not acquisition or native play.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path


DOMAINS = ("amen", "c64", "Freeway", "SpaceInvaders")
SEEDS = (2, 7)
MODELS = ("fast_only", "slow")
MODES = ("cold", "live")
SOLVER_KEYS = (
    "tolerance",
    "state_prior",
    "parameter_prior",
    "state_bound",
    "parameter_bound",
    "step",
    "backtracks",
)


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    temporary.replace(path)


def sources(package, *extra):
    paths = [*Path(package.__file__).parent.glob("*.py"), Path(__file__), *extra]
    return {str(path.resolve()): sha(path) for path in paths}


def unchanged(record):
    return all(
        Path(path).is_file() and sha(path) == value for path, value in record.items()
    )


def development_rows(path, count):
    import numpy as np

    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["meta"]))
        rows = []
        for index, sequence in enumerate(metadata["sequences"]):
            if sequence["split"] != 1:
                continue
            values = archive[f"x{index}"]
            for tick, features in enumerate(values):
                if not np.isfinite(features).all():
                    raise ValueError("Nonfinite development features")
                rows.append(
                    {
                        "sequence_index": index,
                        "sequence": sequence["name"],
                        "split": sequence["split"],
                        "tick": tick,
                        "source_tick": sequence.get("start", 0) + tick,
                        "features": features.tolist(),
                    }
                )
                if len(rows) == count:
                    return rows, metadata
    raise ValueError(f"Only {len(rows)} development rows; {count} required")


def export(args):
    import cadence
    from cadence import Brain

    args.out.mkdir(parents=True, exist_ok=False)
    initial_sources = sources(cadence)
    planned = [
        {"domain": domain, "seed": seed, "model": model}
        for domain in DOMAINS
        for seed in SEEDS
        for model in MODELS
    ]
    write(
        args.out / "protocol.json",
        {
            "schema": "cadence.query-cache-export/1",
            "root": str(args.root.resolve()),
            "sources": initial_sources,
            "planned": planned,
            "rows_per_fixture": args.rows,
            "selection": "first development rows in stored sequence/tick order; split == 1",
            "reader": "Brain.from_snapshot validates original sources; official Python float64 override",
            "nonclaim": "No checkpoint migration, training, native performance or useful reflection claim",
        },
    )
    entries = []
    for item in planned:
        domain, seed, model = item["domain"], item["seed"], item["model"]
        name = f"{domain}-seed{seed}-{model}"
        run = args.root / "runs" / f"wave1-{domain}-seed{seed}"
        try:
            protocol_path = run / "protocol.json"
            protocol = json.loads(protocol_path.read_text())
            report_path = run / "report.json"
            report = json.loads(report_path.read_text())
            if report["status"] != "complete" or not report["sources_unchanged"]:
                raise ValueError("Training run lacks complete source-valid report")
            if sha(protocol_path) != report["protocol_sha256"]:
                raise ValueError("Training protocol hash differs from report")
            data = args.root / "data" / Path(protocol["args"]["data"]).name
            if sha(data) != protocol["data_sha256"]:
                raise ValueError("Data hash differs from training protocol")
            snapshot = run / f"{model}.json"
            founder_path = run / "founder.json"
            for path in (snapshot, founder_path):
                if sha(path) != report["artifacts"][path.name]:
                    raise ValueError(f"Snapshot hash differs: {path.name}")
            brain = Brain.from_snapshot(
                snapshot.read_text(), device="python", dtype="float64"
            )
            founder = Brain.from_snapshot(
                founder_path.read_text(), device="python", dtype="float64"
            )
            rows, metadata = development_rows(data, args.rows)
            before = brain.snapshot(), founder.snapshot()
            exported = []
            for row in rows:
                inputs = {"features": row["features"]}
                witness = None
                if model == "slow":
                    result = founder.settle(
                        {
                            "features": row["features"],
                            "feedback": [0.0] * len(founder.state),
                        }
                    )
                    if not result["qualified"]:
                        raise ValueError(
                            "Original founder refused development readback"
                        )
                    inputs["readback"] = [*result["state"], *result["errors"]]
                    witness = {
                        "qualified": result["qualified"],
                        "stationarity": result["stationarity"],
                        "state": result["state"],
                        "errors": result["errors"],
                        "result_sha256": digest(result),
                    }
                else:
                    inputs["feedback"] = [0.0] * len(brain.state)
                flat, clamps = brain._arguments(inputs)
                if clamps:
                    raise ValueError("Exported query unexpectedly has clamps")
                exported.append(
                    {
                        **{
                            key: value
                            for key, value in row.items()
                            if key != "features"
                        },
                        "inputs": flat,
                        "founder_readback": witness,
                    }
                )
            if before != (brain.snapshot(), founder.snapshot()):
                raise ValueError("Pure export queries changed retained continuation")
            original_snapshot = json.loads(snapshot.read_text())
            fixture = {
                "schema": "cadence.query-cache-fixture/1",
                "identity": item,
                "graph": {
                    "n_inputs": brain.graph.n_inputs,
                    "n_patches": brain.graph.n_patches,
                    "edges": brain.graph.edges,
                },
                "state": brain.state,
                "weights": brain.weights,
                "biases": brain.biases,
                "config": dict(brain.config),
                "rows": exported,
                "provenance": {
                    "snapshot_path": str(snapshot),
                    "snapshot_sha256": sha(snapshot),
                    "snapshot_implementation": original_snapshot["implementation"],
                    "founder_snapshot_sha256": sha(founder_path),
                    "data_path": str(data),
                    "data_sha256": sha(data),
                    "data_metadata_sha256": digest(metadata),
                    "training_protocol_sha256": sha(protocol_path),
                    "training_report_sha256": sha(report_path),
                    "exporter_sources": initial_sources,
                },
            }
            output = args.out / f"{name}.json"
            write(output, fixture)
            entries.append(
                {
                    **item,
                    "status": "complete",
                    "file": output.name,
                    "sha256": sha(output),
                }
            )
        except Exception as error:
            entries.append(
                {**item, "status": "error", "error": f"{type(error).__name__}: {error}"}
            )
        write(
            args.out / "manifest.json",
            {"fixtures": entries, "sources_unchanged": unchanged(initial_sources)},
        )
        print(json.dumps(entries[-1]), flush=True)
    success = unchanged(initial_sources) and all(
        row["status"] == "complete" for row in entries
    )
    write(
        args.out / "manifest.json",
        {
            "status": "complete" if success else "failed",
            "fixtures": entries,
            "sources_unchanged": unchanged(initial_sources),
            "protocol_sha256": sha(args.out / "protocol.json"),
        },
    )
    return 0 if success else 1


def load_baseline(path):
    name = "cadence._repair_baseline"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load original repair source")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def percentile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(rows):
    result = {}
    for mode in (*MODES, "all"):
        selected = [row for row in rows if mode == "all" or row["mode"] == mode]
        arms = {}
        for arm in ("baseline", "candidate"):
            calls = [row[arm] for row in selected]
            times = [row["seconds"] for row in calls]
            work = {}
            for row in calls:
                for key, value in row.get("work", {}).items():
                    work[key] = work.get(key, 0) + value
            arms[arm] = {
                "calls": len(calls),
                "qualified": sum(row.get("qualified", False) for row in calls),
                "exceptions": sum("error" in row for row in calls),
                "refused": sum(
                    "error" not in row and not row["qualified"] for row in calls
                ),
                "seconds": {
                    "total": sum(times),
                    "median": statistics.median(times),
                    "p95": percentile(times, 0.95),
                    "p99": percentile(times, 0.99),
                    "max": max(times),
                },
                "sweeps": sum(row.get("sweeps", 0) for row in calls),
                "work": work,
            }
        result[mode] = {
            "arms": arms,
            "exact_pairs": sum(row["exact"] for row in selected),
            "pairs": len(selected),
            "baseline_over_candidate": {
                name: arms["baseline"]["seconds"][name]
                / arms["candidate"]["seconds"][name]
                for name in ("total", "median", "p95", "p99", "max")
            },
        }
    return result


def call(module, graph, row, state, fixture, options):
    started = time.perf_counter()
    try:
        result = module.settle(
            graph,
            row["inputs"],
            state,
            fixture["weights"],
            fixture["biases"],
            **options,
        )
        seconds = time.perf_counter() - started
        semantic = {key: value for key, value in result.items() if key != "work"}
        diagnostics = {
            "seconds": seconds,
            "qualified": result["qualified"],
            "reason": result["reason"],
            "sweeps": result["sweeps"],
            "stationarity": result["stationarity"],
            "work": result["work"],
            "semantic_sha256": digest(semantic),
        }
        return result, semantic, diagnostics
    except Exception as error:
        return (
            None,
            None,
            {
                "seconds": time.perf_counter() - started,
                "error": f"{type(error).__name__}: {error}",
            },
        )


def run(args):
    import cadence
    from cadence import _repair

    args.out.mkdir(parents=True, exist_ok=False)
    fixture = json.loads(args.fixture.read_text())
    if fixture["schema"] != "cadence.query-cache-fixture/1":
        raise ValueError("Wrong fixture schema")
    rows = fixture["rows"]
    if len(rows) != args.rows or any(row["split"] != 1 for row in rows):
        raise ValueError("Fixture needs exactly the declared development row count")
    initial_sources = sources(cadence, args.baseline, args.fixture)
    expected = fixture["provenance"]["snapshot_implementation"]
    if sha(args.baseline) != expected["_repair.py"]:
        raise ValueError("Baseline source does not match the original snapshot")
    if (
        sha(Path(cadence.__file__).parent / "_validation.py")
        != expected["_validation.py"]
    ):
        raise ValueError("Baseline and candidate must share exact validation source")
    options = {key: fixture["config"][key] for key in SOLVER_KEYS}
    options["budget"] = fixture["config"]["settle_budget"]
    protocol = {
        "schema": "cadence.query-cache-comparison/1",
        "fixture": str(args.fixture.resolve()),
        "fixture_sha256": sha(args.fixture),
        "identity": fixture["identity"],
        "sources": initial_sources,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "rows": args.rows,
        "repeats": args.repeats,
        "modes": MODES,
        "planned_calls_per_arm": args.repeats * args.rows * len(MODES),
        "options": options,
        "order": "alternate baseline/candidate by mode index + repeat * rows + row index parity",
        "continuation": "each repeat resets to checkpoint state; cold resets each query; live keeps only qualified state per arm",
        "timing": "kernel settle call including its validation/final qualification; graph construction, export, comparisons and hashing excluded",
        "acceptance": "all semantic fields exactly equal, both arms always qualified, all calls attempted, sources unchanged",
        "nonclaims": [
            "No training",
            "No task performance",
            "No native game/music behavior",
            "No learned attention or memory",
            "No end-to-end public API latency",
        ],
    }
    write(args.out / "protocol.json", protocol)
    baseline = load_baseline(args.baseline)
    modules = {"baseline": baseline, "candidate": _repair}
    graphs = {arm: module.Graph(**fixture["graph"]) for arm, module in modules.items()}
    ledger = []
    with (args.out / "queries.jsonl").open("x") as handle:
        for mode_index, mode in enumerate(MODES):
            for repeat in range(args.repeats):
                states = {arm: fixture["state"] for arm in modules}
                for index, row in enumerate(rows):
                    order = ("baseline", "candidate")
                    if (mode_index + repeat * len(rows) + index) % 2:
                        order = tuple(reversed(order))
                    results, semantics, diagnostics = {}, {}, {}
                    for arm in order:
                        state = states[arm] if mode == "live" else fixture["state"]
                        results[arm], semantics[arm], diagnostics[arm] = call(
                            modules[arm], graphs[arm], row, state, fixture, options
                        )
                        if results[arm] is not None and results[arm]["qualified"]:
                            states[arm] = results[arm]["state"]
                    exact = (
                        semantics["baseline"] is not None
                        and semantics["baseline"] == semantics["candidate"]
                    )
                    differences = []
                    if not exact and all(
                        value is not None for value in semantics.values()
                    ):
                        differences = [
                            key
                            for key in set(semantics["baseline"])
                            | set(semantics["candidate"])
                            if semantics["baseline"].get(key)
                            != semantics["candidate"].get(key)
                        ]
                    entry = {
                        "mode": mode,
                        "repeat": repeat,
                        "row": index,
                        "order": order,
                        "exact": exact,
                        "different_fields": sorted(differences),
                        **diagnostics,
                    }
                    ledger.append(entry)
                    handle.write(
                        json.dumps(entry, sort_keys=True, allow_nan=False) + "\n"
                    )
                    handle.flush()
                print(
                    json.dumps({"mode": mode, "repeat": repeat, "pairs": len(ledger)}),
                    flush=True,
                )
    summary = summarize(ledger)
    success = (
        unchanged(initial_sources)
        and len(ledger) == protocol["planned_calls_per_arm"]
        and all(row["exact"] for row in ledger)
        and all(row[arm].get("qualified", False) for row in ledger for arm in modules)
    )
    report = {
        "status": "complete" if success else "failed",
        "sources_unchanged": unchanged(initial_sources),
        "protocol_sha256": sha(args.out / "protocol.json"),
        "ledger_sha256": sha(args.out / "queries.jsonl"),
        "summary": summary,
    }
    write(args.out / "report.json", report)
    print(json.dumps(report), flush=True)
    return 0 if success else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    exporter = commands.add_parser("export")
    exporter.add_argument("--root", type=Path, required=True)
    exporter.add_argument("--out", type=Path, required=True)
    exporter.add_argument("--rows", type=int, default=64)
    runner = commands.add_parser("run")
    runner.add_argument("--fixture", type=Path, required=True)
    runner.add_argument("--baseline", type=Path, required=True)
    runner.add_argument("--out", type=Path, required=True)
    runner.add_argument("--rows", type=int, default=64)
    runner.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.rows < 1 or getattr(args, "repeats", 1) < 1:
        parser.error("rows and repeats must be positive")
    return export(args) if args.command == "export" else run(args)


if __name__ == "__main__":
    raise SystemExit(main())
