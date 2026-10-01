"""Six-case Amen startup-exposure experiment; frozen app/core remain unchanged.

Freeze schedules and founders before launch. Only the selected witness rows
differ between paired arms; all predictions use the common public patch law.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

import numpy as np

import cadence
from cadence import Brain

SEEDS = (1103, 1109, 1117)
ARMS = ("uniform", "startup-balanced")
UPDATES, BATCH, PREFIX, CAP = 128, 32, 8, 900


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    temporary.replace(path)


def snapshot(path, brain):
    text = brain.snapshot()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(text)
    temporary.replace(path)
    return hashlib.sha256(text.encode()).hexdigest()


def app_modules(app):
    sys.path.insert(0, str(app))
    from drsn_amen import compose as C
    from drsn_amen import model as M
    from drsn_amen import stream as S
    from drsn_amen import train as T

    return C, M, S, T


def reference(path):
    spec = importlib.util.spec_from_file_location("frozen_amen_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sources(app, helper):
    paths = [
        Path(__file__).resolve(),
        helper.resolve(),
        *sorted((app / "drsn_amen").glob("*.py")),
        *sorted(Path(cadence.__file__).resolve().parent.glob("*.py")),
    ]
    return {str(p.resolve()): sha(p) for p in paths}


def jobs():
    return [(seed, arm) for seed in SEEDS for arm in ARMS]


def row_pools(lengths):
    offsets = np.r_[0, np.cumsum(lengths[:-1])].astype(int)
    prefix = np.concatenate(
        [
            np.arange(offset, offset + min(PREFIX, n))
            for offset, n in zip(offsets, lengths, strict=True)
        ]
    )
    return offsets, prefix


def schedules(lengths, seed):
    _, pool = row_pools(lengths)
    uniform = (
        np.random.default_rng(seed)
        .permutation(sum(lengths))[: UPDATES * BATCH]
        .reshape(UPDATES, BATCH)
    )
    rng = np.random.default_rng(np.random.SeedSequence([seed, 20261010]))
    chosen = []
    while len(chosen) < UPDATES * (BATCH // 2):
        chosen.extend(rng.permutation(pool).tolist())
    balanced = uniform.copy()
    balanced[:, BATCH // 2 :] = np.asarray(chosen[: UPDATES * (BATCH // 2)]).reshape(
        UPDATES, BATCH // 2
    )
    return {"uniform": uniform.tolist(), "startup-balanced": balanced.tolist()}


def exposure(indices, lengths):
    starts, prefix = row_pools(lengths)
    flat = np.asarray(indices).reshape(-1)
    return {
        "presentations": len(flat),
        "unique_rows": len(set(flat.tolist())),
        "repeated_presentations": len(flat) - len(set(flat.tolist())),
        "wake_rows": int(np.isin(flat, starts).sum()),
        "prefix_rows": int(np.isin(flat, prefix).sum()),
        "other_rows": int((~np.isin(flat, prefix)).sum()),
    }


def build(M, seed):
    return M.layout(
        steps=8,
        hearing=0,
        groove=0,
        seed=seed,
        device="cpu",
        dtype="float64",
        parameter_prior=0.4,
        tolerance=1e-6,
        settle_budget=2048,
        initial_scale=0.3,
        state_prior=0.01,
        wiring="flat",
    )


def freeze(root, app, helper, baseline_run):
    import torch

    root.mkdir(parents=True, exist_ok=False)
    _C, M, S, T = app_modules(app)
    pins = sources(app, helper)
    fixture, regions, _ = S.load_fixture("soft")
    ids = [r["id"] for r in fixture["regions"] if r["id"] not in S.HELD_OUT]
    lengths = [len(regions[r]) for r in ids]
    if len(ids) != 71 or len(S.HELD_OUT) != 8:
        raise ValueError("frozen corpus split changed")
    root.joinpath("data").mkdir()
    rows = T.build_rows(regions, ids, 8)
    for name, values in zip(
        ("history", "clock", "wake", "targets", "origin"), rows, strict=True
    ):
        np.save(root / "data" / f"{name}.npy", values)
    del rows
    held = []
    picks = T.evaluation_sample(regions, 8, 16, 1103)
    for name, start, history, clock, wake, events in picks:
        for i in range(len(events)):
            held.append(
                {
                    "region": name,
                    "row": start + i,
                    "inputs": M.inputs_of(history[i], clock[i], wake[i], 8),
                    "truth": events[i].tolist(),
                }
            )
    write(root / "heldout.json", held)
    tapes = {str(seed): schedules(lengths, seed) for seed in SEEDS}
    write(root / "schedules.json", tapes)
    founders = root / "founders"
    founders.mkdir()
    hashes = {
        str(seed): snapshot(founders / f"seed{seed}.json", build(M, seed))
        for seed in SEEDS
    }
    starts = np.asarray([regions[r][0] for r in ids])
    prefixes = np.concatenate([regions[r][:PREFIX] for r in ids])
    source_ids = {r["id"]: r["source_sha256"] for r in fixture["regions"]}
    training_sources = {source_ids[r] for r in ids}
    protocol = {
        "schema": "amen-startup-curriculum/1",
        "runtime": {
            "python": sys.version,
            "numpy": np.__version__,
            "torch": torch.__version__,
            "cadence": cadence.__version__,
        },
        "app": str(app),
        "reference_helper": str(helper),
        "original_uniform128": str(baseline_run),
        "baseline_files": {
            str(baseline_run / name): sha(baseline_run / name)
            for name in ("final.json", "receipt.json")
        },
        "sources": pins,
        "fixture_receipt": fixture["receipt_sha256"],
        "fixture_files": {
            str(p): sha(p)
            for p in (S.FIXTURE / "fixture.json", S.FIXTURE / "arrays.npz")
        },
        "data_files": {p.name: sha(p) for p in sorted((root / "data").glob("*.npy"))},
        "heldout_sha256": sha(root / "heldout.json"),
        "schedules_sha256": sha(root / "schedules.json"),
        "founders": hashes,
        "seeds": SEEDS,
        "arms": ARMS,
        "jobs": jobs(),
        "train_regions": ids,
        "lengths": lengths,
        "held_out": list(S.HELD_OUT),
        "evaluation_sample": [
            {"region": r, "start": s, "rows": len(e)} for r, s, _, _, _, e in picks
        ],
        "source_overlap": {r: source_ids[r] in training_sources for r in S.HELD_OUT},
        "sampler": "Uniform: original rng(seed) permutation first4096 rows. Balanced: retain first16 IDs of each uniform32 batch; replace last16 with cyclic complete permutations of every actual train-region first8 row, independent RNG SeedSequence([seed,20261010]). Preserve repeats/overlap. No target-dependent selection, synthetic starts, altered history or decoder.",
        "prefix_steps": PREFIX,
        "prefix_fraction": 0.5,
        "updates": UPDATES,
        "batch": BATCH,
        "exposure": {
            f"{s}-{arm}": exposure(tapes[str(s)][arm], lengths) for s, arm in jobs()
        },
        "startup_targets": {
            "regions": len(ids),
            "prefix_rows": len(prefixes),
            "wake_drums": int((starts[:, S.DRUM_ON] > 0.5).sum()),
            "wake_bass": int((starts[:, S.BASS_ON] > 0.5).sum()),
            "prefix_drum_fraction": float((prefixes[:, S.DRUM_ON] > 0.5).mean()),
            "prefix_bass_fraction": float((prefixes[:, S.BASS_ON] > 0.5).mean()),
        },
        "compute": {
            "workers": 6,
            "threads": 4,
            "arm_hard_seconds": CAP,
            "signal_seconds": CAP - 5,
            "dtype": "float64",
            "device": "cpu",
            "admission_budget": 8192,
        },
        "gates": {
            "all128_admissions": True,
            "all_free_calls_qualified": True,
            "heldout_mae_gain_min": 0.01,
            "argmax_half_beats": 128,
            "argmax_drum_min": 0.5,
            "argmax_bass_min": 0.25,
            "sample_seeds": [1, 2, 3, 4],
            "browser_export_ready": False,
        },
        "conclusion": "Campaign requires all6 numerically complete/no-refusal and all3 balanced original smoke gates. Report every paired direction and balanced-minus-uniform heldoutMAE (.01 degradation diagnostic). No best-seed/checkpoint selection. Uniform failures remain outcomes, not removed comparators.",
        "scope": "Development curriculum gene (half prefix/eight steps), not architecture advantage.1103 reused;1109/1117 fresh seeds within the same development hypothesis, not fresh task confirmation. Five heldoutregions share source recordings with training. No listening/browser/export/long-term music-quality claim.",
        "receipt_encoding": "All returned solver fields except parameters; canonical weights/biases hash instead. Full snapshots and call before/after hashes retained; unknown interrupted work explicitly counted.",
    }
    if pins != sources(app, helper):
        raise ValueError("source changed during freeze")
    write(root / "protocol.json", protocol)
    print(
        json.dumps(
            {
                "protocol_sha256": sha(root / "protocol.json"),
                "exposure": protocol["exposure"],
            }
        ),
        flush=True,
    )


def bound(root):
    import torch

    p = read(root / "protocol.json")
    if p["sources"] != sources(Path(p["app"]), Path(p["reference_helper"])):
        raise ValueError("frozen sources changed")
    if p["runtime"] != {
        "python": sys.version,
        "numpy": np.__version__,
        "torch": torch.__version__,
        "cadence": cadence.__version__,
    }:
        raise ValueError("frozen runtime changed")
    for seed, pin in p["founders"].items():
        if sha(root / "founders" / f"seed{seed}.json") != pin:
            raise ValueError("frozen founder changed")
    for name, pin in p["data_files"].items():
        if sha(root / "data" / name) != pin:
            raise ValueError("frozen prepared data changed")
    if any(sha(path) != value for path, value in p["fixture_files"].items()):
        raise ValueError("fixture changed")
    if any(sha(path) != value for path, value in p.get("baseline_files", {}).items()):
        raise ValueError("original baseline changed")
    for file, pin in (
        ("schedules.json", "schedules_sha256"),
        ("heldout.json", "heldout_sha256"),
    ):
        if sha(root / file) != p[pin]:
            raise ValueError(f"changed {file}")
    return p


class TimeCap(RuntimeError):
    pass


def alarm(*_):
    raise TimeCap("declared arm time cap")


def compact(result):
    parameters = {k: result[k] for k in ("weights", "biases") if k in result}
    return {
        **{k: v for k, v in result.items() if k not in parameters},
        "parameters_sha256": digest(parameters),
    }


class Calls:
    def __init__(self, out, brain):
        self.out, self.brain, self.rows = out, brain, []

    def call(self, metadata, operation):
        before = self.brain.snapshot()
        item = {
            "id": len(self.rows),
            **metadata,
            "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
        }
        write(self.out / "inflight.json", item)
        start = time.perf_counter()
        try:
            result = operation()
        except Exception:
            self.append(
                {
                    **item,
                    "status": "interrupted_or_error",
                    "seconds": time.perf_counter() - start,
                    "unknown_solver_work": True,
                    "traceback": traceback.format_exc(),
                }
            )
            raise
        item.update(
            status="returned",
            seconds=time.perf_counter() - start,
            result=compact(result),
            after_sha256=hashlib.sha256(self.brain.snapshot().encode()).hexdigest(),
        )
        self.append(item)
        if metadata["kind"] == "admission" and result["accepted"]:
            snapshot(self.out / "latest.json", self.brain)
        (self.out / "inflight.json").unlink()
        return result

    def append(self, row):
        self.rows.append(row)
        with (self.out / "calls.jsonl").open("a") as f:
            f.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")


def evaluate(calls, held, S, ref, phase):
    predictions, qualified = [], 0
    for i, row in enumerate(held):
        r = calls.call(
            {
                "kind": "heldout",
                "phase": phase,
                "row": i,
                "inputs_sha256": digest(row["inputs"]),
            },
            lambda row=row: calls.brain.settle(row["inputs"]),
        )
        qualified += int(r["qualified"])
        predictions.append(S.decode(r["outputs"]["event"]).tolist())
    truth = [r["truth"] for r in held]
    return {
        "qualified": qualified,
        "metrics": ref.metrics(predictions, truth, S),
        "by_region": {
            name: ref.metrics(
                [
                    v
                    for v, r in zip(predictions, held, strict=True)
                    if r["region"] == name
                ],
                [r["truth"] for r in held if r["region"] == name],
                S,
            )
            for name in S.HELD_OUT
        },
    }


def generate(calls, C, S, mode, seed):
    window, rng, events = [S.COUNT_IN.copy()], np.random.default_rng(seed), []
    for t in range(128):
        values = C.senses(window, t, 8)
        r = calls.call(
            {
                "kind": "generation",
                "mode": mode,
                "seed": seed,
                "tick": t,
                "inputs_sha256": digest(values),
            },
            lambda values=values: calls.brain.settle(values),
        )
        if not r["qualified"]:
            return {"complete": False, "refused": True, "events": events, "at": t}
        event = S.executed(
            S.decode(r["outputs"]["event"]),
            mode,
            rng,
            previous=window[-1] if mode == "sample" else None,
        )
        events.append(event.tolist())
        window.append(event)
    e = np.asarray(events)
    parts = {"first8": e[:8], "rest": e[8:]}
    return {
        "complete": True,
        "refused": False,
        "events": events,
        "drum_fraction": float((e[:, S.DRUM_ON] > 0.5).mean()),
        "bass_fraction": float((e[:, S.BASS_ON] > 0.5).mean()),
        "statistics": S.statistics(e),
        "parts": {
            k: {
                "drum_fraction": float((v[:, S.DRUM_ON] > 0.5).mean()),
                "bass_fraction": float((v[:, S.BASS_ON] > 0.5).mean()),
            }
            for k, v in parts.items()
        },
        "per_bar": [
            {
                "drum_fraction": float((e[i : i + 8, S.DRUM_ON] > 0.5).mean()),
                "bass_fraction": float((e[i : i + 8, S.BASS_ON] > 0.5).mean()),
            }
            for i in range(0, 128, 8)
        ],
    }


def gate(report):
    free = report.get("generation", {}).get("argmax-0", {})
    gain = report.get("heldout_mae_gain", float("-inf"))
    return bool(
        report.get("status") == "complete"
        and report.get("sources_unchanged")
        and report.get("accepted_admissions") == 128
        and report.get("refused_calls") == 0
        and report.get("unknown_calls") == 0
        and report.get("initial_heldout", {}).get("qualified") == 128
        and report.get("final_heldout", {}).get("qualified") == 128
        and gain >= 0.01
        and free.get("complete")
        and free.get("drum_fraction", 0) >= 0.5
        and free.get("bass_fraction", 0) >= 0.25
        and all(
            report.get("generation", {}).get(f"sample-{seed}", {}).get("complete")
            for seed in (1, 2, 3, 4)
        )
    )


def run_arm(root, seed, arm):
    started = time.monotonic()
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, CAP - 5)
    p, report, calls = (
        None,
        {
            "seed": seed,
            "arm": arm,
            "status": "running",
            "generation": {},
            "checkpoints": [],
        },
        None,
    )
    out = root / f"{arm}-seed{seed}"
    out.mkdir(exist_ok=False)
    write(out / "report.json", report)
    try:
        import torch

        torch.set_num_threads(4)
        p = bound(root)
        if (seed, arm) not in jobs():
            raise ValueError("undeclared arm")
        C, _M, S, T = app_modules(Path(p["app"]))
        ref = reference(p["reference_helper"])
        report["protocol_sha256"] = sha(root / "protocol.json")
        rows = tuple(
            np.load(root / "data" / f"{name}.npy", mmap_mode="r")
            for name in ("history", "clock", "wake", "targets", "origin")
        )
        held = read(root / "heldout.json")
        brain = Brain.from_snapshot(
            (root / "founders" / f"seed{seed}.json").read_text(),
            device="cpu",
            dtype="float64",
        )
        ref.flat_check(brain, 8)
        report["initial_sha256"] = snapshot(out / "initial.json", brain)
        snapshot(out / "latest.json", brain)
        calls = Calls(out, brain)
        report["initial_heldout"] = evaluate(calls, held, S, ref, "newborn")
        write(out / "report.json", report)
        for i, indices in enumerate(read(root / "schedules.json")[str(seed)][arm]):
            examples = [T.example(rows, int(j), 8) for j in indices]
            calls.call(
                {"kind": "admission", "update": i, "indices": indices},
                lambda examples=examples: brain.observe_batch(
                    examples, budget=8192, source="witness"
                ),
            )
            if (i + 1) % 32 == 0:
                name = f"update{i + 1:03}.json"
                report["checkpoints"].append(
                    {"name": name, "sha256": snapshot(out / name, brain)}
                )
                write(out / "report.json", report)
        report["final_sha256"] = snapshot(out / "final.json", brain)
        report["final_heldout"] = evaluate(calls, held, S, ref, "trained")
        report["heldout_mae_gain"] = (
            report["initial_heldout"]["metrics"]["decoded_all_port_mae"]
            - report["final_heldout"]["metrics"]["decoded_all_port_mae"]
        )
        for mode, s in [("argmax", 0), *[("sample", s) for s in (1, 2, 3, 4)]]:
            report["generation"][f"{mode}-{s}"] = generate(calls, C, S, mode, s)
            write(out / "report.json", report)
        if (
            sha(out / "final.json")
            != hashlib.sha256(brain.snapshot().encode()).hexdigest()
        ):
            raise ValueError("pure evaluation changed continuation")
        report["status"] = "complete"
    except Exception:  # noqa: BLE001 - preserve every failed arm.
        report.update(
            status="time_limit" if sys.exc_info()[0] is TimeCap else "error",
            traceback=traceback.format_exc(),
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        rows = calls.rows if calls else []
        returned = [r for r in rows if r["status"] == "returned"]
        report["unknown_calls"] = len(rows) - len(returned)
        if (out / "inflight.json").exists():
            pending = read(out / "inflight.json")
            report["inflight"] = pending
            report["unknown_calls"] += int(
                not any(r["id"] == pending["id"] for r in rows)
            )
        report["accepted_admissions"] = sum(
            r["kind"] == "admission" and r["result"]["accepted"] for r in returned
        )
        report["attempted_admissions"] = sum(r["kind"] == "admission" for r in rows)
        if (out / "inflight.json").exists():
            pending = read(out / "inflight.json")
            report["attempted_admissions"] += int(
                pending["kind"] == "admission"
                and not any(r["id"] == pending["id"] for r in rows)
            )
        report["refused_calls"] = sum(
            not r["result"]["qualified"]
            or (r["kind"] == "admission" and not r["result"]["accepted"])
            for r in returned
        )
        report["returned_calls"] = len(returned)
        report["attempted_presentations"] = 32 * report["attempted_admissions"]
        report["accepted_presentations"] = 32 * report["accepted_admissions"]
        report["work"] = {}
        for kind in ("admission", "heldout", "generation"):
            counter = Counter()
            for r in returned:
                if r["kind"] == kind:
                    counter.update(r["result"]["work"])
            report["work"][kind] = dict(counter)
        report["sources_unchanged"] = bool(
            p and p["sources"] == sources(Path(p["app"]), Path(p["reference_helper"]))
        )
        report["files"] = {
            f.name: {"sha256": sha(f), "bytes": f.stat().st_size}
            for f in sorted(out.iterdir())
            if f.is_file() and f.name != "report.json"
        }
        report["wall_seconds"] = time.monotonic() - started
        if report["wall_seconds"] >= CAP:
            report["status"] = "time_limit"
        report["smoke_passed"] = gate(report)
        write(out / "report.json", report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "seed",
                    "arm",
                    "status",
                    "smoke_passed",
                    "accepted_admissions",
                    "wall_seconds",
                )
            }
        ),
        flush=True,
    )


def launch(root):
    bound(root)
    if (root / "execution.json").exists() or any(
        (root / f"{arm}-seed{seed}").exists() for seed, arm in jobs()
    ):
        raise FileExistsError("do not overwrite attempted campaign")
    write(
        root / "planned-cases.json",
        [{"seed": s, "arm": a, "status": "planned"} for s, a in jobs()],
    )

    def worker(job):
        seed, arm = job
        env = {
            **os.environ,
            "OMP_NUM_THREADS": "4",
            "MKL_NUM_THREADS": "4",
            "OPENBLAS_NUM_THREADS": "1",
            "VECLIB_MAXIMUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
        try:
            r = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "arm",
                    str(root),
                    "--seed",
                    str(seed),
                    "--arm",
                    arm,
                ],
                capture_output=True,
                text=True,
                timeout=CAP,
                env=env,
                check=False,
            )
            return {
                "seed": seed,
                "arm": arm,
                "exit_code": r.returncode,
                "stdout": r.stdout,
                "stderr": r.stderr,
            }
        except subprocess.TimeoutExpired as e:
            return {
                "seed": seed,
                "arm": arm,
                "status": "outer_timeout",
                "stdout": str(e.stdout),
                "stderr": str(e.stderr),
            }
        except Exception:  # noqa: BLE001 - retain every planned subprocess outcome.
            return {
                "seed": seed,
                "arm": arm,
                "status": "launch_error",
                "traceback": traceback.format_exc(),
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(worker, jobs()))
    write(root / "execution.json", outcomes)
    print(json.dumps(outcomes), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "launch", "arm"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--app", type=Path)
    parser.add_argument("--reference-helper", type=Path)
    parser.add_argument("--baseline-run", type=Path)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--arm", choices=ARMS)
    args = parser.parse_args()
    if args.mode == "freeze":
        freeze(
            args.root.resolve(),
            args.app.resolve(),
            args.reference_helper.resolve(),
            args.baseline_run.resolve(),
        )
    elif args.mode == "launch":
        launch(args.root.resolve())
    else:
        run_arm(args.root.resolve(), args.seed, args.arm)
