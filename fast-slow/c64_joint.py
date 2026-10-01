"""Dimensioning pilot for one coupled C64 event/longer-context brain.

The twelve-update comparison is a cost and learning-sign screen, not evidence
of musical quality, learned temporal memory, useful reflection or release readiness.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import time

import numpy as np


HISTORY = HORIZON = 64
RAW_WIDTH = 6 * HISTORY + 16
ARMS = {
    "flat": (11,),
    "ordinary64": (32, 16, 16),
    "observer64": (32, 16, 16),
    "ordinary128": (64, 32, 32),
    "observer128": (64, 32, 32),
}
HEADS = {"next_event": 6, "future64": 5}
DATA_LIMIT = 100_000_000


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    temporary.replace(path)


def feature_module(workspace):
    path = Path(workspace) / "cadence-c64-maestro/population_composer/features.py"
    spec = importlib.util.spec_from_file_location("c64_joint_features", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_row(features, gestures, goals, tick):
    tracks = features.voice_tracks(gestures)
    return track_row(features, tracks, goals, tick)


def track_row(features, tracks, goals, tick):
    if tick < HISTORY or tick + HORIZON > len(goals):
        raise ValueError("A row requires all 64 past and 64 future frames")
    past = features.interleave(
        tracks["pitch"][tick - HISTORY : tick], tracks["flags"][tick - HISTORY : tick]
    )
    inputs = np.r_[past, np.asarray(goals[tick], dtype=float)]
    targets = {
        "next_event": features.interleave(tracks["pitch"][tick], tracks["flags"][tick]),
        "future64": features.window_stats(tracks, tick, tick + HORIZON),
    }
    if inputs.shape != (RAW_WIDTH,) or not np.isfinite(inputs).all():
        raise ValueError(
            "Inputs must contain 384 carried-pitch/flag values and 16 finite cues"
        )
    if any(
        value.shape != (HEADS[name],) or not np.isfinite(value).all()
        for name, value in targets.items()
    ):
        raise ValueError("Invalid target shape or values")
    return inputs, targets


def select_families(records, limits, seed=101):
    family_splits = {}
    for row in records:
        family_splits.setdefault(row["family"], set()).add(row["split"])
    # The corpus uses file-level splits and contains cross-split families.
    # Exclude all of those families before creating any windows, including a
    # family whose otherwise usable training file has a test-split sibling.
    excluded = {family for family, splits in family_splits.items() if len(splits) != 1}
    rng = np.random.default_rng(seed)
    selected = []
    for split, limit in limits.items():
        groups = {}
        for row in records:
            if (
                row["split"] == split
                and row["family"] not in excluded
                and row["frames"] >= HISTORY + HORIZON
            ):
                groups.setdefault(row["family"], []).append(row)
        families = sorted(groups)
        if len(families) < limit:
            raise ValueError(
                f"Only {len(families)} eligible {split} families; {limit} required"
            )
        for index in rng.permutation(len(families))[:limit]:
            performances = sorted(groups[families[index]], key=lambda row: row["file"])
            selected.append(performances[int(rng.integers(len(performances)))])
    return selected


def build_data(args):
    args.out.mkdir(parents=True, exist_ok=False)
    features = feature_module(args.workspace)
    corpus = args.workspace / "cadence-c64-maestro/data/performances"
    source_hashes = {
        str(Path(__file__).resolve()): sha(__file__),
        str(Path(features.__file__).resolve()): sha(features.__file__),
    }
    write(
        args.out / "protocol.json",
        {
            "schema": "cadence.c64-joint-data/1",
            "seed": 101,
            "families": {"train": 64, "validation": 24},
            "rows_per_family": 64,
            "selection": "metadata-only family selection, excluding every cross-split family before opening selected performance arrays; original test arrays never opened",
            "inputs": "[t-64,t) frame-major carried pitch/flags, then the 16 corpus metronome/source cues at t; no t/total-length coordinate",
            "targets": "next_event at t; window_stats over [t,t+64)",
            "memory": "declared fixed sensory history; carried pitch can retain a note predating that history; not learned memory",
            "sources": source_hashes,
        },
    )
    records = []
    for path in sorted(corpus.glob("*.npz")):
        with np.load(path, allow_pickle=False) as archive:
            meta = json.loads(str(archive["meta"]))
        records.append(
            {
                "file": path.name,
                "family": meta["family"],
                "split": meta["split"],
                "frames": int(meta["frames"]),
            }
        )
    selected = select_families(records, {"train": 64, "validation": 24})
    family_splits = {}
    for row in records:
        family_splits.setdefault(row["family"], set()).add(row["split"])
    rng = np.random.default_rng(101)
    buckets = {split: [] for split in ("train", "validation")}
    identities = {split: [] for split in buckets}
    evidence = []
    for record in selected:
        path = corpus / record["file"]
        source_hashes[str(path.resolve())] = sha(path)
        with np.load(path, allow_pickle=False) as archive:
            gestures, goals = archive["gestures"], archive["goals"]
        if len(gestures) != record["frames"] or goals.shape != (len(gestures), 16):
            raise ValueError("Metadata/array shape disagreement")
        tracks = features.voice_tracks(gestures)
        available = np.arange(HISTORY, len(gestures) - HORIZON + 1)
        ticks = sorted(
            rng.choice(available, size=min(64, len(available)), replace=False).tolist()
        )
        for tick in ticks:
            buckets[record["split"]].append(track_row(features, tracks, goals, tick))
            identities[record["split"]].append(
                {"file": record["file"], "family": record["family"], "tick": tick}
            )
        evidence.append(
            {**record, "sha256": source_hashes[str(path.resolve())], "ticks": ticks}
        )
    arrays = {}
    for split, rows in buckets.items():
        arrays[f"{split}_inputs"] = np.stack([row[0] for row in rows])
        for name in HEADS:
            arrays[f"{split}_{name}"] = np.stack([row[1][name] for row in rows])
    schedule = np.random.default_rng(101)
    arrays["training_rows"] = np.stack(
        [
            schedule.choice(len(buckets["train"]), size=32, replace=False)
            for _ in range(12)
        ]
    )
    arrays["evaluation_rows"] = np.sort(
        schedule.choice(len(buckets["validation"]), size=64, replace=False)
    )
    manifest = {
        "schema": "cadence.c64-joint-rows/1",
        "metadata_inventory_sha256": digest(records),
        "excluded_cross_split_families": {
            family: sorted(splits)
            for family, splits in sorted(family_splits.items())
            if len(splits) != 1
        },
        "protocol_sha256": sha(args.out / "protocol.json"),
        "sources": source_hashes,
        "performances": evidence,
        "row_identity": identities,
        "rows": {split: len(rows) for split, rows in buckets.items()},
        "training_schedule_sha256": digest(arrays["training_rows"].tolist()),
        "evaluation_schedule_sha256": digest(arrays["evaluation_rows"].tolist()),
        "selected_evaluation_families": sorted(
            {
                identities["validation"][index]["family"]
                for index in arrays["evaluation_rows"]
            }
        ),
    }
    arrays["manifest"] = np.array(json.dumps(manifest, sort_keys=True))
    if sum(array.nbytes for array in arrays.values()) >= DATA_LIMIT:
        raise ValueError("Prepared data exceeds the local 100 MB limit")
    output = args.out / "data.npz"
    with output.open("xb") as handle:
        np.savez_compressed(handle, **arrays)
    if output.stat().st_size >= DATA_LIMIT:
        raise ValueError("Prepared file exceeds the local 100 MB limit")
    if not all(sha(path) == expected for path, expected in source_hashes.items()):
        raise ValueError("Data or source changed during collection")
    receipt = {
        "status": "complete",
        "data_sha256": sha(output),
        "bytes": output.stat().st_size,
        "uncompressed_bytes": sum(array.nbytes for array in arrays.values()),
        **manifest,
    }
    write(args.out / "manifest.json", receipt)
    print(
        json.dumps(
            {
                key: receipt[key]
                for key in (
                    "status",
                    "data_sha256",
                    "bytes",
                    "uncompressed_bytes",
                    "rows",
                )
            }
        ),
        flush=True,
    )
    return 0


def build(arm, beta, *, seed=2, device="cpu", raw_width=RAW_WIDTH, widths=None):
    from cadence import Cortex

    widths = ARMS[arm] if widths is None else widths
    cortex = Cortex(
        seed=seed,
        parameter_prior=beta,
        state_prior=0.01,
        device=device,
        dtype="float64",
        settle_budget=4096,
    )
    raw = cortex.input("raw", shape=raw_width)
    base = cortex.column("base", patches=widths[0], inputs=raw)
    if arm == "flat":
        top = base
        future_indices = tuple(range(6, 11))
    else:
        if arm.startswith("observer"):
            middle = cortex.observer(
                "context", patches=widths[1], inputs=raw, observes=base
            )
            top = cortex.observer(
                "reflection", patches=widths[2], inputs=raw, observes=(base, middle)
            )
        else:
            middle = cortex.column("context", patches=widths[1], inputs=(raw, base))
            top = cortex.column(
                "reflection", patches=widths[2], inputs=(raw, base, middle)
            )
        future_indices = tuple(range(5))
    cortex.output("next_event", shape=6, reads=base)
    cortex.output("future64", shape=5, reads=top, indices=future_indices)
    return cortex.build()


def add_work(total, work):
    for key, value in work.items():
        total[key] = total.get(key, 0) + value


def activity(states, errors, populations):
    x, e = np.asarray(states), np.asarray(errors)
    if x.ndim == 1:
        x, e = x[None, :], e[None, :]
    return {
        row["name"]: {
            "state_rms": float(np.sqrt(np.mean(x[:, row["indices"]] ** 2))),
            "error_rms": float(np.sqrt(np.mean(e[:, row["indices"]] ** 2))),
        }
        for row in populations
    }


def displacement(brain, initial, populations):
    old_weights, old_biases = initial
    result = {}
    for row in populations:
        indices = set(row["indices"])
        changes = [
            new - old
            for (_, _, target), new, old in zip(
                brain.graph.edges, brain.weights, old_weights, strict=True
            )
            if target in indices
        ]
        changes += [brain.biases[index] - old_biases[index] for index in indices]
        values = np.asarray(changes)
        result[row["name"]] = {
            "parameters": len(changes),
            "rms": float(np.sqrt(np.mean(values**2))),
            "l2": float(np.linalg.norm(values)),
            "max_abs": float(np.max(np.abs(values))),
        }
    return result


def evaluate(brain, arrays, indices, populations, path):
    before = brain.snapshot()
    rows, errors = [], {name: [] for name in HEADS}
    work = {}
    states, residuals = [], []
    for index in indices:
        started = time.perf_counter()
        try:
            result = brain.settle({"raw": arrays["validation_inputs"][index].tolist()})
            elapsed = time.perf_counter() - started
            row = {
                "row": int(index),
                "qualified": result["qualified"],
                "reason": result["reason"],
                "seconds": elapsed,
                "sweeps": result["sweeps"],
                "stationarity": result["stationarity"],
                "work": result["work"],
            }
            add_work(work, result["work"])
            if result["qualified"]:
                states.append(result["state"])
                residuals.append(result["errors"])
                row["head_mae"] = {
                    name: float(
                        np.mean(
                            np.abs(
                                np.asarray(result["outputs"][name])
                                - arrays[f"validation_{name}"][index]
                            )
                        )
                    )
                    for name in HEADS
                }
                for name in HEADS:
                    errors[name].append(row["head_mae"][name])
        except Exception as error:
            row = {
                "row": int(index),
                "qualified": False,
                "seconds": time.perf_counter() - started,
                "error": f"{type(error).__name__}: {error}",
            }
        rows.append(row)
        write(path, rows)
    if brain.snapshot() != before:
        raise ValueError("Held-out pure evaluation changed continuation")
    qualified = sum(row["qualified"] for row in rows)
    times = [row["seconds"] for row in rows]
    return {
        "cases": len(rows),
        "qualified": qualified,
        "refused_or_error": len(rows) - qualified,
        "heads": {
            name: {
                "mae_qualified": float(np.mean(values)) if values else None,
                "mae_with_refusal_penalty_2": float(
                    (sum(values) + 2 * (len(rows) - len(values))) / len(rows)
                ),
            }
            for name, values in errors.items()
        },
        "seconds": {
            "total": sum(times),
            "median": float(np.median(times)),
            "p95": float(np.quantile(times, 0.95)),
            "max": max(times),
        },
        "sweeps": sum(row.get("sweeps", 0) for row in rows),
        "work": work,
        "layer_activity_qualified": activity(states, residuals, populations)
        if states
        else None,
        "ledger_sha256": sha(path),
    }


def train(args):
    import cadence

    if args.device != "python":
        import torch

        torch.set_num_threads(1)
    args.out.mkdir(parents=True, exist_ok=False)
    with np.load(args.data, allow_pickle=False) as archive:
        arrays = {
            name: archive[name].copy() for name in archive.files if name != "manifest"
        }
        manifest = json.loads(str(archive["manifest"]))
    if arrays["training_rows"].shape != (12, 32) or arrays["evaluation_rows"].shape != (
        64,
    ):
        raise ValueError(
            "Pilot requires 12 common batches of 32 and 64 common held-out rows"
        )
    sources = {
        str(path.resolve()): sha(path)
        for path in [
            Path(__file__),
            args.data,
            *Path(cadence.__file__).parent.glob("*.py"),
        ]
    }
    brain = build(args.arm, args.beta, seed=args.seed, device=args.device)
    inspection = brain.inspect()
    populations = inspection["populations"]
    initial = brain.weights, brain.biases
    (args.out / "initial.json").write_text(brain.snapshot())
    protocol = {
        "schema": "cadence.c64-joint-pilot/1",
        "sources": sources,
        "arm": args.arm,
        "seed": args.seed,
        "beta": args.beta,
        "alpha": 0.01,
        "device": args.device,
        "dtype": "float64",
        "python": platform.python_version(),
        "updates": 12,
        "batch_size": 32,
        "learning_budget": 8192,
        "query_budget": 4096,
        "target_source": "estimate",
        "inputs": "400: raw carried pitch/flags from past64 +16 known cues; no length/position feature",
        "targets": HEADS,
        "future_horizon": HORIZON,
        "training_rows": arrays["training_rows"].tolist(),
        "evaluation_rows": arrays["evaluation_rows"].tolist(),
        "data_manifest_sha256": digest(manifest),
        "counts": {
            "inputs": brain.graph.n_inputs,
            "patches": brain.graph.n_patches,
            "edges": len(brain.graph.edges),
            "parameters": len(brain.weights) + len(brain.biases),
            "edge_kinds": dict(Counter(kind for kind, _, _ in brain.graph.edges)),
        },
        "populations": populations,
        "config": dict(brain.config),
        "comparison": "same rows/targets and corresponding state/skip topology; observer adds residual edges and parameters, so parameter count and initialization differ",
        "work_units": "library-reported scalar patch/edge traversals including reference qualification; not hardware FLOPs",
        "nonclaims": [
            "Only dimensioning, time and acquisition-sign sanity",
            "No final capability gate",
            "No native rendering/listening",
            "No learned recurrent memory",
            "No causal proof of useful reflection",
        ],
    }
    write(args.out / "protocol.json", protocol)
    started = time.perf_counter()
    report = {
        "status": "running",
        "protocol_sha256": sha(args.out / "protocol.json"),
        "counts": protocol["counts"],
    }
    report["before"] = evaluate(
        brain, arrays, arrays["evaluation_rows"], populations, args.out / "before.json"
    )
    write(args.out / "report.json", report)
    ledger, work = [], {}
    with (args.out / "training.jsonl").open("x") as handle:
        for update, picks in enumerate(arrays["training_rows"]):
            examples = [
                (
                    {"raw": arrays["train_inputs"][index].tolist()},
                    {name: arrays[f"train_{name}"][index].tolist() for name in HEADS},
                )
                for index in picks
            ]
            then = time.perf_counter()
            try:
                result = brain.observe_batch(examples, source="estimate", budget=8192)
                elapsed = time.perf_counter() - then
                entry = {
                    "update": update,
                    "rows": picks.tolist(),
                    "accepted": result["accepted"],
                    "reason": result["reason"],
                    "seconds": elapsed,
                    "sweeps": result["sweeps"],
                    "stationarity": result["stationarity"],
                    "work": result["work"],
                    "proposal_layer_activity": activity(
                        result["states"], result["errors"], populations
                    ),
                    "retained_parameter_displacement": displacement(
                        brain, initial, populations
                    ),
                }
                add_work(work, result["work"])
            except Exception as error:
                entry = {
                    "update": update,
                    "rows": picks.tolist(),
                    "accepted": False,
                    "seconds": time.perf_counter() - then,
                    "error": f"{type(error).__name__}: {error}",
                }
            ledger.append(entry)
            handle.write(json.dumps(entry, sort_keys=True, allow_nan=False) + "\n")
            handle.flush()
            print(
                json.dumps(
                    {key: entry[key] for key in ("update", "accepted", "seconds")}
                ),
                flush=True,
            )
    report["after"] = evaluate(
        brain, arrays, arrays["evaluation_rows"], populations, args.out / "after.json"
    )
    (args.out / "final.json").write_text(brain.snapshot())
    report.update(
        {
            "training": {
                "attempted": len(ledger),
                "accepted": sum(row["accepted"] for row in ledger),
                "attempted_presentations": 32 * len(ledger),
                "accepted_presentations": 32 * sum(row["accepted"] for row in ledger),
                "seconds": sum(row["seconds"] for row in ledger),
                "sweeps": sum(row.get("sweeps", 0) for row in ledger),
                "work": work,
            },
            "retained_parameter_displacement": displacement(
                brain, initial, populations
            ),
            "sources_unchanged": all(
                sha(path) == expected for path, expected in sources.items()
            ),
            "seconds": time.perf_counter() - started,
            "head_mae_change": {
                name: report["after"]["heads"][name]["mae_with_refusal_penalty_2"]
                - report["before"]["heads"][name]["mae_with_refusal_penalty_2"]
                for name in HEADS
            },
            "artifacts": {
                name: sha(args.out / name)
                for name in (
                    "initial.json",
                    "final.json",
                    "training.jsonl",
                    "before.json",
                    "after.json",
                )
            },
        }
    )
    success = (
        report["sources_unchanged"]
        and report["training"]["accepted"] == 12
        and all(report[phase]["qualified"] == 64 for phase in ("before", "after"))
    )
    report["status"] = "complete" if success else "failed"
    write(args.out / "report.json", report)
    print(json.dumps(report), flush=True)
    return 0 if success else 1


def self_test(args):
    from cadence import Brain

    features = feature_module(args.workspace)
    gestures = np.zeros((160, 28), dtype=np.uint8)
    gestures[:, list(features.VOICE_NOTE)] = 48
    gestures[:, list(features.VOICE_GATE)] = 1
    goals = np.zeros((160, 16))
    goals[:, 4] = np.arange(160) % 8 / 8
    before = make_row(features, gestures, goals, 80)
    altered = gestures.copy()
    altered[80:, list(features.VOICE_NOTE)] = 84
    later_goals = goals.copy()
    later_goals[81:] = 0.7
    after = make_row(features, altered, later_goals, 80)
    assert np.array_equal(before[0], after[0])
    assert not np.array_equal(before[1]["next_event"], after[1]["next_event"])
    assert not np.array_equal(before[1]["future64"], after[1]["future64"])
    extended = make_row(
        features, np.r_[gestures, gestures[:20]], np.r_[goals, goals[:20]], 80
    )
    assert np.array_equal(before[0], extended[0])
    records = [
        {
            "file": f"{split}-{index}.npz",
            "split": split,
            "family": f"{split}-{index}",
            "frames": 160,
        }
        for split in ("train", "validation", "test")
        for index in range(4)
    ]
    selected = select_families(records, {"train": 2, "validation": 2})
    assert selected == select_families(
        list(reversed(records)), {"train": 2, "validation": 2}
    )
    assert len({row["family"] for row in selected}) == 4
    assert all(row["split"] != "test" for row in selected)
    excluded = select_families(
        [*records, {**records[0], "split": "validation"}],
        {"train": 2, "validation": 2},
    )
    assert all(row["family"] != records[0]["family"] for row in excluded)
    ordinary = build("ordinary64", 0.1, device="python", raw_width=4, widths=(6, 2, 5))
    brain = build("observer64", 0.1, device="python", raw_width=4, widths=(6, 2, 5))
    assert set(ordinary.graph.edges) == set(
        edge for edge in brain.graph.edges if edge[0] != "residual"
    )
    examples = [
        (
            {"raw": [value, -value, 0.2, -0.1]},
            {"next_event": [value] * 6, "future64": [-value] * 5},
        )
        for value in (-0.3, 0.3)
    ]

    def loss():
        return float(
            np.mean(
                [
                    abs(actual - wanted)
                    for inputs, targets in examples
                    for name, output in brain.predict(inputs).items()
                    for actual, wanted in zip(output, targets[name], strict=True)
                ]
            )
        )

    initial = loss()
    for _ in range(6):
        assert brain.observe_batch(examples, source="estimate", budget=8192)["accepted"]
    final = loss()
    assert final < initial
    restored = Brain.from_snapshot(brain.snapshot())
    assert restored.predict(examples[0][0]) == brain.predict(examples[0][0])
    print(
        json.dumps(
            {
                "future_input_invariance": True,
                "length_input_invariance": True,
                "family_separation": True,
                "matching_state_contacts": True,
                "joint_learning_before_mae": initial,
                "joint_learning_after_mae": final,
                "qualified_snapshot_continuation": True,
                "source_sha256": sha(__file__),
            }
        ),
        flush=True,
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    data = commands.add_parser("build-data")
    data.add_argument("--workspace", type=Path, required=True)
    data.add_argument("--out", type=Path, required=True)
    trainer = commands.add_parser("train")
    trainer.add_argument("--data", type=Path, required=True)
    trainer.add_argument("--out", type=Path, required=True)
    trainer.add_argument("--arm", choices=ARMS, required=True)
    trainer.add_argument("--beta", type=float, choices=(0.1, 0.01), required=True)
    trainer.add_argument("--seed", type=int, default=2)
    trainer.add_argument("--device", choices=("python", "cpu"), default="cpu")
    check = commands.add_parser("self-test")
    check.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    return {"build-data": build_data, "train": train, "self-test": self_test}[
        args.command
    ](args)


if __name__ == "__main__":
    raise SystemExit(main())
