"""Frozen Freeway routine bootstrap and serial native play; no website mutation.

The teacher is always UP. This tests acquiring and executing a simple routine,
not visual strategy, reward learning, recurrence, or browser compatibility.
All learned actions come from qualified public Cadence settlement.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.metadata
import json
import os
import platform
import signal
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

import numpy as np

import cadence
from cadence import Cortex

MODEL_SEEDS = (211, 223, 227)
TRAIN_SEEDS = (610211, 610223)
HELD_SEED = 710227
PLAY_SEEDS = (810211, 810223, 810227)
ROWS = 512
UPDATES = 64
BATCH = 16
PLAY_LIMIT = 2300
TRAIN_SECONDS = 120
PLAY_SECONDS = 600
OUTER_SECONDS = 900
DEADLINE = 1 / 15


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_sha(value):
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def write(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def text_snapshot(path, brain):
    text = brain.snapshot()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text)
    tmp.replace(path)
    return hashlib.sha256(text.encode()).hexdigest()


def sources():
    paths = [
        Path(__file__).resolve(),
        *Path(cadence.__file__).resolve().parent.rglob("*.py"),
    ]
    return {str(p): sha(p) for p in sorted(paths)}


def features(rgb, previous, action, actions):
    """Only present pixels, earlier pooled pixels, and last executed action."""
    image = np.asarray(rgb)
    if image.shape != (210, 160, 3):
        raise ValueError("expected native 210x160 RGB")
    grey = (image.astype(np.float64) @ [0.299, 0.587, 0.114]) / 255.0
    pooled = grey.reshape(21, 10, 20, 8).mean(axis=(1, 3)).reshape(-1)
    difference = np.zeros_like(pooled) if previous is None else pooled - previous
    return np.r_[pooled, difference, np.eye(actions)[action]], pooled


def normalize(raw, mean, scale):
    return np.clip((raw - mean) / scale, -3, 3) * 0.2


def make_brain(seed, actions=3, *, device="cpu"):
    c = Cortex(
        seed=seed,
        device=device,
        dtype="float64",
        parameter_prior=0.4,
        state_prior=0.01,
        initial_scale=0.3,
        tolerance=1e-6,
        settle_budget=2048,
    )
    visible = c.input("visible", shape=840 + actions)
    motor = c.column("playing", patches=actions, inputs=visible)
    c.output("motor", shape=actions, reads=motor)
    return c.build()


def action_targets(action, actions):
    return np.where(np.arange(actions) == action, 0.6, -0.6).tolist()


def admit(brain, examples, update):
    """One public event ordinal per attempted bootstrap batch."""
    return brain.observe_batch(
        examples, source="witness", event_id=update + 1, budget=8192
    )


def compact_result(result):
    """Avoid repeating thousands of parameters in every pure-query receipt."""
    parameters = {k: result[k] for k in ("weights", "biases") if k in result}
    return {
        **{k: v for k, v in result.items() if k not in parameters},
        "parameters_sha256": digest(parameters),
    }


def make_env():
    import ale_py
    import gymnasium as gym

    gym.register_envs(ale_py)
    return gym.make(
        "ALE/Freeway-v5",
        frameskip=4,
        repeat_action_probability=0.0,
        full_action_space=False,
        obs_type="rgb",
    )


def start(env, seed):
    obs, _ = env.reset(seed=seed)
    for _ in range(1 + seed % 29):
        obs, _, terminated, truncated, _ = env.step(0)
        if terminated or truncated:
            raise RuntimeError("episode ended during declared NOOP start")
    return obs


def schedule():
    # One complete shared shuffle: identical exposure for every model seed.
    return (
        np.random.default_rng(20261009)
        .permutation(2 * ROWS)
        .reshape(UPDATES, BATCH)
        .tolist()
    )


def freeze(root, rom):
    root.mkdir(parents=True, exist_ok=False)
    import ale_py

    candidates = list(Path(ale_py.__file__).resolve().parent.rglob("freeway.bin"))
    if len(candidates) != 1:
        raise ValueError("expected exactly one installed ALE Freeway ROM")
    if rom is not None and sha(rom) != sha(candidates[0]):
        raise ValueError("--rom must match the installed ROM used by ALE")
    rom = candidates[0]
    protocol = {
        "schema": "cadence.atari-flat-bootstrap/1",
        "sources": sources(),
        "cadence": cadence.__version__,
        "python": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "torch", "ale-py", "gymnasium")
        },
        "rom": {"path": str(rom.resolve()), "sha256": sha(rom)},
        "game": "Freeway",
        "model_seeds": MODEL_SEEDS,
        "train_seeds": TRAIN_SEEDS,
        "held_seed": HELD_SEED,
        "play_seeds": PLAY_SEEDS,
        "rows_per_collection": ROWS,
        "schedule": schedule(),
        "updates": UPDATES,
        "batch": BATCH,
        "teacher": "constant UP; no RAM access anywhere in this collector",
        "input": "21x20 area-pooled current RGB luminance, preceding-frame difference, last executed action; train-only mean/std floor .05, clip +/-3, multiply .2",
        "layout": "one flat input-only motor column; 3 patches, 843 inputs, 2532 parameters",
        "teaching": "actual teacher-executed action encoded +/-0.6; public observe_batch source=witness; no reward update",
        "play": "frozen final parameters; pure qualified query then exactly one synchronous body step; record both terminated and truncated; no teacher fallback",
        "play_limit": PLAY_LIMIT,
        "frameskip": 4,
        "sticky_probability": 0.0,
        "caps": {
            "acquisition_seconds": TRAIN_SECONDS,
            "native_seconds": PLAY_SECONDS,
            "outer_seconds": OUTER_SECONDS,
            "workers": 3,
            "threads": 1,
        },
        "gates": {
            "held_agreement": 0.95,
            "all_required_calls_qualify": True,
            "all_native_episodes_terminate": True,
            "native_positive_score": True,
            "native_teacher_fraction_each_seed": 0.8,
        },
        "reporting": "All seeds, refused/errored attempts, caps and censored episodes retained. 15Hz query and observation-to-action p50/p95/max/misses, including newborn and final heldout queries, reported separately from acquisition work. Gates do not require meeting 15Hz.",
        "receipt_encoding": "Solver parameter vectors are represented by their canonical SHA256; all other returned fields remain verbatim. Before/after snapshot hashes and saved checkpoints bind full parameters for independent replay.",
        "nonclaims": [
            "Not a visual-strategy test: constant UP can solve this routine.",
            "No reward-learning, recursive advantage, browser migration, or real-time guarantee.",
            "No posthoc selected model; every declared model/native seed is retained.",
        ],
    }
    write(root / "protocol.json", protocol)
    print(
        json.dumps({"protocol_sha256": sha(root / "protocol.json"), "out": str(root)})
    )


def bound_protocol(root):
    p = json.loads((root / "protocol.json").read_text())
    if p["sources"] != sources() or p["schedule"] != schedule():
        raise ValueError("frozen source or schedule changed")
    if sha(p["rom"]["path"]) != p["rom"]["sha256"]:
        raise ValueError("frozen ROM changed")
    if p["python"] != platform.python_version() or any(
        importlib.metadata.version(name) != version
        for name, version in p["packages"].items()
    ):
        raise ValueError("frozen runtime version changed")
    return p


def collect(root):
    bound_protocol(root)
    env = make_env()
    meanings = env.unwrapped.get_action_meanings()
    if list(meanings) != ["NOOP", "UP", "DOWN"]:
        raise ValueError(f"unexpected Freeway action encoding: {meanings}")
    arrays, records = {}, []
    try:
        for seed in (*TRAIN_SEEDS, HELD_SEED):
            obs = start(env, seed)
            previous, last = None, 0
            rows, actions = [], []
            for tick in range(ROWS):
                x, previous = features(obs, previous, last, len(meanings))
                before = array_sha(obs)
                action = meanings.index("UP")
                obs, reward, term, trunc, _ = env.step(action)
                rows.append(x)
                actions.append(action)
                records.append(
                    {
                        "seed": seed,
                        "tick": tick,
                        "observation_sha256": before,
                        "features_sha256": array_sha(x),
                        "executed_action": action,
                        "reward": float(reward),
                        "next_observation_sha256": array_sha(obs),
                        "terminated": bool(term),
                        "truncated": bool(trunc),
                    }
                )
                last = action
                if term or trunc:
                    raise RuntimeError("collection ended before declared row count")
            arrays[f"x{seed}"] = np.asarray(rows)
            arrays[f"a{seed}"] = np.asarray(actions)
    finally:
        env.close()
    train = np.concatenate([arrays[f"x{s}"] for s in TRAIN_SEEDS])
    arrays["mean"], arrays["scale"] = train.mean(0), np.maximum(train.std(0), 0.05)
    np.savez_compressed(root / "data.npz", **arrays)
    write(
        root / "collection.json",
        {
            "meanings": list(meanings),
            "records": records,
            "data_sha256": sha(root / "data.npz"),
            "protocol_sha256": sha(root / "protocol.json"),
        },
    )


def latency(values):
    return {
        "calls": len(values),
        "seconds": float(sum(values)),
        "median_ms": float(np.median(values) * 1000) if values else None,
        "p95_ms": float(np.quantile(values, 0.95) * 1000) if values else None,
        "max_ms": float(max(values) * 1000) if values else None,
        "misses_15hz": sum(v > DEADLINE for v in values),
    }


class TimeCap(RuntimeError):
    pass


def alarm(_signum, _frame):
    raise TimeCap("declared phase deadline")


class Journal:
    def __init__(self, out):
        self.out = out
        self.rows = []

    def call(self, brain, meta, operation):
        before = brain.snapshot()
        item = {
            "id": len(self.rows),
            **meta,
            "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
        }
        write(self.out / "inflight.json", item)
        began = time.perf_counter()
        try:
            result = operation()
        except Exception:
            item.update(
                status="error",
                seconds=time.perf_counter() - began,
                unknown_solver_work=True,
                traceback=traceback.format_exc(),
            )
            self.append(item)
            # Calls can time out after tentative mutation. The failed arm keeps
            # its previously accepted latest.json and is never promoted.
            raise
        item.update(
            status="returned",
            seconds=time.perf_counter() - began,
            result=compact_result(result),
            after_sha256=hashlib.sha256(brain.snapshot().encode()).hexdigest(),
        )
        self.append(item)
        if meta["kind"] == "admission" and result["accepted"]:
            text_snapshot(self.out / "latest.json", brain)
        (self.out / "inflight.json").unlink()
        return result, item["seconds"]

    def append(self, row):
        self.rows.append(row)
        with (self.out / "calls.jsonl").open("a") as handle:
            handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")


def heldout(brain, x, targets, journal, phase):
    correct, qualified, timing = 0, 0, []
    for i, (row, target) in enumerate(zip(x, targets, strict=True)):
        result, elapsed = journal.call(
            brain,
            {
                "kind": "heldout",
                "phase": phase,
                "row": i,
                "inputs_sha256": array_sha(row),
            },
            lambda row=row: brain.settle({"visible": row.tolist()}),
        )
        timing.append(elapsed)
        qualified += int(result["qualified"])
        correct += int(
            result["qualified"] and np.argmax(result["outputs"]["motor"]) == target
        )
    return {
        "rows": len(x),
        "qualified": qualified,
        "agreement": correct / len(x),
        "latency": latency(timing),
    }


def native_episode(
    env, seed, *, brain=None, mean=None, scale=None, journal=None, baseline=None
):
    obs = start(env, seed)
    previous, last = None, 0
    rows, timings, query_times = [], [], []
    score, terminated, truncated, refused = 0.0, False, False, False
    for tick in range(PLAY_LIMIT):
        began = time.perf_counter()
        x, previous = features(obs, previous, last, 3)
        frame_hash = array_sha(obs)
        if brain is None:
            action = 1 if baseline == "teacher" else 0
        else:
            inputs = normalize(x, mean, scale)
            result, seconds = journal.call(
                brain,
                {
                    "kind": "native",
                    "seed": seed,
                    "tick": tick,
                    "inputs_sha256": array_sha(inputs),
                    "observation_sha256": frame_hash,
                },
                lambda inputs=inputs: brain.settle({"visible": inputs.tolist()}),
            )
            query_times.append(seconds)
            if not result["qualified"]:
                refused = True
                break
            action = int(np.argmax(result["outputs"]["motor"]))
        # No body step or fabricated reward is issued on a refused decision.
        pending = {
            "seed": seed,
            "tick": tick,
            "executed_action": action,
            "observation_sha256": frame_hash,
        }
        if journal is not None:
            write(journal.out / "body-inflight.json", pending)
        duration = time.perf_counter() - began
        obs, reward, terminated, truncated, _ = env.step(action)
        score += float(reward)
        timings.append(duration)
        rows.append(
            {
                "seed": seed,
                "tick": tick,
                "executed_action": action,
                "reward": float(reward),
                "observation_sha256": frame_hash,
                "next_observation_sha256": array_sha(obs),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "observation_to_action_seconds": duration,
            }
        )
        if journal is not None:
            with (journal.out / "transitions.jsonl").open("a") as handle:
                handle.write(json.dumps(rows[-1], sort_keys=True) + "\n")
            (journal.out / "body-inflight.json").unlink()
        last = action
        if terminated or truncated:
            break
    return {
        "seed": seed,
        "baseline": baseline,
        "return": score,
        "decisions": len(rows),
        "terminated": bool(terminated),
        "truncated": bool(truncated),
        "censored": not terminated,
        "refused": refused,
        "actions": rows,
        "latency": latency(timings),
        "query_latency": latency(query_times),
    }


def baseline_runs(root):
    env = make_env()
    result = []
    try:
        for seed in PLAY_SEEDS:
            for baseline in ("teacher", "noop"):
                result.append(native_episode(env, seed, baseline=baseline))
                write(root / "baselines.json", result)
    finally:
        env.close()


def gates(report, baseline):
    by_seed = {row["seed"]: row for row in baseline if row["baseline"] == "teacher"}
    episodes = report.get("episodes", [])
    return bool(
        report.get("status") == "complete"
        and report.get("sources_unchanged")
        and report.get("accepted_updates") == UPDATES
        and report.get("refused_calls") == 0
        and report.get("unknown_calls") == 0
        and report.get("final_heldout", {}).get("qualified") == ROWS
        and report.get("final_heldout", {}).get("agreement", 0) >= 0.95
        and [e["seed"] for e in episodes] == list(PLAY_SEEDS)
        and all(
            e["terminated"]
            and not e["truncated"]
            and not e["refused"]
            and e["return"] > 0
            and by_seed[e["seed"]]["terminated"]
            and not by_seed[e["seed"]]["truncated"]
            and e["return"] >= 0.8 * by_seed[e["seed"]]["return"]
            for e in episodes
        )
    )


def run_arm(root, seed):
    p = bound_protocol(root)
    if seed not in MODEL_SEEDS:
        raise ValueError("undeclared model seed")
    import torch

    torch.set_num_threads(1)
    out = root / f"seed{seed}"
    out.mkdir(exist_ok=False)
    collection = json.loads((root / "collection.json").read_text())
    if sha(root / "data.npz") != collection["data_sha256"]:
        raise ValueError("collection hash mismatch")
    with np.load(root / "data.npz") as data:
        mean, scale = data["mean"], data["scale"]
        train = normalize(
            np.concatenate([data[f"x{s}"] for s in TRAIN_SEEDS]), mean, scale
        )
        action = np.concatenate([data[f"a{s}"] for s in TRAIN_SEEDS])
        held, held_actions = (
            normalize(data[f"x{HELD_SEED}"], mean, scale),
            data[f"a{HELD_SEED}"],
        )
    brain = make_brain(seed)
    report = {
        "seed": seed,
        "protocol_sha256": sha(root / "protocol.json"),
        "collection_sha256": sha(root / "collection.json"),
        "status": "running",
        "initial_sha256": text_snapshot(out / "initial.json", brain),
        "episodes": [],
        "checkpoints": [],
        "accepted_updates": 0,
    }
    text_snapshot(out / "latest.json", brain)
    journal = Journal(out)
    write(out / "report.json", report)
    started = time.perf_counter()
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, TRAIN_SECONDS)
    try:
        report["initial_heldout"] = heldout(
            brain, held, held_actions, journal, "newborn"
        )
        for i, indices in enumerate(p["schedule"]):
            examples = [
                (
                    {"visible": train[j].tolist()},
                    {"motor": action_targets(action[j], 3)},
                )
                for j in indices
            ]
            result, _ = journal.call(
                brain,
                {"kind": "admission", "update": i, "indices": indices},
                lambda examples=examples, i=i: admit(brain, examples, i),
            )
            report["accepted_updates"] += int(result["accepted"])
            if (i + 1) % 16 == 0:
                name = f"update{i + 1:03}.json"
                report["checkpoints"].append(
                    {"name": name, "sha256": text_snapshot(out / name, brain)}
                )
                write(out / "report.json", report)
        report["final_heldout"] = heldout(brain, held, held_actions, journal, "trained")
        report["final_sha256"] = text_snapshot(out / "final.json", brain)
        report["acquisition_seconds"] = time.perf_counter() - started
        signal.setitimer(signal.ITIMER_REAL, PLAY_SECONDS)
        env = make_env()
        try:
            for play_seed in PLAY_SEEDS:
                episode = native_episode(
                    env, play_seed, brain=brain, mean=mean, scale=scale, journal=journal
                )
                write(out / f"play{play_seed}.json", episode)
                report["episodes"].append(
                    {k: v for k, v in episode.items() if k != "actions"}
                )
                write(out / "report.json", report)
        finally:
            env.close()
        if (
            sha(out / "final.json")
            != hashlib.sha256(brain.snapshot().encode()).hexdigest()
        ):
            raise ValueError("native queries mutated frozen brain")
        report["status"] = "complete"
    except Exception:  # noqa: BLE001 — retain failed/capped arms as evidence.
        report.update(
            status="time_limit" if sys.exc_info()[0] is TimeCap else "error",
            traceback=traceback.format_exc(),
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        report["wall_seconds"] = time.perf_counter() - started
        report["sources_unchanged"] = p["sources"] == sources()
        returned = [r for r in journal.rows if r["status"] == "returned"]
        report["accepted_updates"] = sum(
            r["kind"] == "admission" and r["result"]["accepted"] for r in returned
        )
        report["returned_calls"] = len(returned)
        report["unknown_calls"] = len(journal.rows) - len(returned)
        if (out / "inflight.json").exists():
            inflight = json.loads((out / "inflight.json").read_text())
            report["inflight"] = inflight
            report["unknown_calls"] += int(
                not any(r["id"] == inflight["id"] for r in journal.rows)
            )
        if (out / "body-inflight.json").exists():
            report["body_inflight"] = json.loads(
                (out / "body-inflight.json").read_text()
            )
        report["refused_calls"] = sum(
            not r["result"].get("qualified", False)
            or (r["kind"] == "admission" and not r["result"]["accepted"])
            for r in returned
        )
        report["attempted_updates"] = sum(
            r["kind"] == "admission" for r in journal.rows
        )
        report["attempted_row_presentations"] = BATCH * report["attempted_updates"]
        report["accepted_row_presentations"] = BATCH * report["accepted_updates"]
        report["query_latency_all_phases"] = latency(
            [r["seconds"] for r in journal.rows if r["kind"] != "admission"]
        )
        report["work"] = {}
        for kind in ("admission", "heldout", "native"):
            counts = Counter()
            for row in returned:
                if row["kind"] == kind:
                    counts.update(row["result"]["work"])
            report["work"][kind] = dict(counts)
        report["passed"] = gates(
            report, json.loads((root / "baselines.json").read_text())
        )
        report["files"] = {
            f.name: {"sha256": sha(f), "bytes": f.stat().st_size}
            for f in sorted(out.iterdir())
            if f.is_file() and f.name != "report.json"
        }
        write(out / "report.json", report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "seed",
                    "status",
                    "passed",
                    "accepted_updates",
                    "refused_calls",
                    "wall_seconds",
                )
            }
        )
    )


def launch(root):
    bound_protocol(root)
    if (root / "execution.json").exists() or (root / "data.npz").exists():
        raise FileExistsError("refusing to overwrite an existing campaign")
    try:
        collect(root)
        baseline_runs(root)
    except Exception:
        write(
            root / "execution.json",
            [
                {
                    "seed": seed,
                    "status": "not_started",
                    "preparation_failure": traceback.format_exc(),
                }
                for seed in MODEL_SEEDS
            ],
        )
        raise

    def worker(seed):
        env = {
            **os.environ,
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "VECLIB_MAXIMUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "arm",
                    str(root),
                    "--seed",
                    str(seed),
                ],
                capture_output=True,
                text=True,
                env=env,
                timeout=OUTER_SECONDS,
                check=False,
            )
            return {
                "seed": seed,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired as error:
            return {
                "seed": seed,
                "status": "outer_timeout",
                "stdout": str(error.stdout),
                "stderr": str(error.stderr),
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(worker, MODEL_SEEDS))
    write(root / "execution.json", outcomes)
    print(json.dumps(outcomes))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "launch", "arm"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    if args.mode == "freeze":
        freeze(args.root.resolve(), args.rom)
    elif args.mode == "launch":
        launch(args.root.resolve())
    else:
        run_arm(args.root.resolve(), args.seed)
