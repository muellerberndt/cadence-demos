"""Frozen, student-only native Doom evaluation. No teacher or planner import.

The evaluator constructs the checkpoint actor itself and gives it only the
visible frame. Every decision must qualify; refusal ends the episode as a
failure. Native timeouts, external cutoffs and missing jobs stay in the declared
denominator. Evaluation results never choose or promote another checkpoint.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import time

from .tasks import DoomEnv, get_task, sha_file, task_identity


def summarize(rows, expected):
    by_key = {}
    for row in rows:
        key = row["task_id"], row["seed"]
        if key in by_key:
            raise ValueError(f"Duplicate evaluation result {key}")
        by_key[key] = row
    expected = [(str(task), int(seed)) for task, seed in expected]
    if len(set(expected)) != len(expected):
        raise ValueError("Protocol contains duplicate task/seed pairs")
    unknown = set(by_key) - set(expected)
    if unknown:
        raise ValueError(f"Unscheduled evaluation results {unknown}")
    groups = {}
    for task_id in sorted(set(t for t, _ in expected)):
        keys = [key for key in expected if key[0] == task_id]
        present = [by_key[key] for key in keys if key in by_key]
        successes = sum(bool(r.get("success")) and r.get("qualified_queries") == r.get("queries")
                        and r.get("status") == "complete" for r in present)
        groups[task_id] = {"scheduled": len(keys), "returned": len(present), "missing": len(keys)-len(present),
                           "successes": successes, "success_rate": successes / len(keys),
                           "native_exits": sum(bool(r.get("native_exit")) and r.get("status") == "complete"
                                               and r.get("qualified_queries") == r.get("queries") for r in present),
                           "deaths": sum(bool(r.get("dead")) for r in present),
                           "native_timeouts": sum(bool(r.get("timeout")) for r in present),
                           "queries": sum(r.get("queries", 0) for r in present),
                           "qualified_queries": sum(r.get("qualified_queries", 0) for r in present),
                           "cutoffs_or_errors": sum(r.get("status") != "complete" for r in present),
                           "mean_return_present": sum(r.get("return", 0) for r in present) / len(present) if present else None,
                           "mean_tics_present": sum(r.get("tics", 0) for r in present) / len(present) if present else None}
    return {"tasks": groups, "scheduled": len(expected), "returned": len(rows),
            "missing": len(expected)-len(rows), "successes": sum(g["successes"] for g in groups.values()),
            "all_scheduled_accounted": len(rows) == len(expected),
            "interpretation": "Native task outcomes at one frozen checkpoint; no selection or fallback policy"}


def evaluate_episode(bundle, task, seed, output, *, wall_seconds=300,
                     expected_checkpoint=None, expected_bundle_sha256=None):
    from .brain import Actor
    task = get_task(task)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    queries = qualified = 0
    times = []
    cutoff = None
    if expected_bundle_sha256 and sha_file(bundle) != expected_bundle_sha256:
        raise ValueError("Bundle bytes changed after evaluation freeze")
    actor = Actor(bundle, device="cpu")
    if expected_checkpoint and actor.checkpoint_hash != expected_checkpoint:
        raise ValueError("Actor checkpoint differs from evaluation freeze")
    actor.reset()
    with DoomEnv(task, seed, teacher=False) as env, (output / "decisions.jsonl").open("w") as stream:
        while not env.finished:
            if time.monotonic() - started >= wall_seconds:
                cutoff = "evaluation_wall_cap"
                break
            raw = env.observe()
            queries += 1
            try:
                decision = actor.choose(raw)
            except Exception as error:
                cutoff = "actor_query_error"
                stream.write(json.dumps({"step": queries-1, "qualified": False, "executed": False,
                                         "error": f"{type(error).__name__}: {error}"}) + "\n")
                break
            record = {"step": queries-1, "raw_sha256": hashlib.sha256(raw.tobytes()).hexdigest(),
                      "qualified": bool(decision.get("qualified")), "action": decision.get("action"),
                      "checkpoint_sha256": actor.checkpoint_hash,
                      "query_seconds": decision.get("query_seconds"), "fallback": False,
                      "behavior_source": "qualified_cadence_actor"}
            if decision.get("query_seconds") is not None:
                times.append(float(decision["query_seconds"]))
            if not decision.get("qualified"):
                cutoff = "unqualified_query"
                record["executed"] = False
                stream.write(json.dumps(record, separators=(",", ":")) + "\n")
                break
            qualified += 1
            transition = env.step(decision["action"])
            actor.acknowledge(raw, decision["action"], transition["tics"])
            record.update(executed=True, transition=transition)
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
            if queries % 100 == 0:
                stream.flush()
        result = {**env.outcome(cutoff), "queries": queries, "qualified_queries": qualified,
                  "fallback_actions": 0, "status": "complete" if cutoff is None else cutoff,
                  "checkpoint_sha256": actor.checkpoint_hash, "behavior_source": "qualified_cadence_actor",
                  "privileged_observations_enabled": False, "wall_seconds": time.monotonic() - started,
                  "mean_query_seconds": sum(times) / len(times) if times else None}
    result["decisions_sha256"] = sha_file(output / "decisions.jsonl")
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def _job(payload):
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    try:
        return evaluate_episode(**payload)
    except Exception as error:
        task = get_task(payload["task"])
        result = {"task_id": task.task_id, "seed": payload["seed"], "success": False,
                  "native_exit": False, "status": "error", "error": f"{type(error).__name__}: {error}",
                  "queries": 0, "qualified_queries": 0, "fallback_actions": 0}
        path = Path(payload["output"])
        path.mkdir(parents=True, exist_ok=True)
        (path / "failure.json").write_text(json.dumps(result, indent=2) + "\n")
        return result


def campaign(bundle, tasks, seeds, output, *, workers=1, wall_seconds=300, allow_heldout=False):
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    if not 1 <= workers <= 64 or wall_seconds <= 0:
        raise ValueError("Invalid worker or wall bound")
    specs = [get_task(task) for task in tasks]
    if any(spec.split in {"heldout", "reserved_extension"} for spec in specs) and not allow_heldout:
        raise ValueError("Heldout maps require an explicitly frozen final evaluation")
    seeds = [int(seed) for seed in seeds]
    expected = [(spec.task_id, seed) for spec in specs for seed in seeds]
    if not expected or len(set(expected)) != len(expected):
        raise ValueError("Evaluation schedule is empty or duplicated")
    output.mkdir(parents=True, exist_ok=False)
    from .brain import Actor
    actor = Actor(bundle, device="cpu")
    freeze = {"schema": "doom-v3-student-evaluation-freeze/1", "created_unix": time.time(),
              "bundle_path": str(bundle), "bundle_sha256": sha_file(bundle), "checkpoint_sha256": actor.checkpoint_hash,
              "tasks": [task_identity(spec) for spec in specs], "seeds": seeds, "expected": expected,
              "workers": workers, "episode_wall_seconds": wall_seconds, "allow_heldout": allow_heldout,
              "evaluator_sha256": sha_file(Path(__file__)), "tasks_sha256": sha_file(Path(__file__).with_name("tasks.py")),
              "interpretation": "One frozen learned actor, no oracle/planner/interventions or checkpoint selection"}
    (output / "freeze.json").write_text(json.dumps(freeze, indent=2) + "\n")
    expected_checkpoint = actor.checkpoint_hash
    del actor
    jobs = [dict(bundle=str(bundle), task=spec, seed=seed,
                 output=str(output / "episodes" / f"{spec.task_id.replace(':', '_')}_{seed}"), wall_seconds=wall_seconds,
                 expected_checkpoint=expected_checkpoint, expected_bundle_sha256=freeze["bundle_sha256"])
            for spec in specs for seed in seeds]
    rows = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool, (output / "outcomes.jsonl").open("w") as stream:
        future_map = {pool.submit(_job, job): job for job in jobs}
        for future in as_completed(future_map):
            job = future_map[future]
            try:
                row = future.result()
            except Exception as error:
                row = {"task_id": job["task"].task_id, "seed": job["seed"], "success": False,
                       "native_exit": False, "status": "worker_error", "error": repr(error),
                       "queries": 0, "qualified_queries": 0}
            rows.append(row)
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")
            stream.flush()
            report = {"schema": "doom-v3-student-evaluation-result/1", "freeze_sha256": sha_file(output / "freeze.json"),
                      **summarize(rows, expected)}
            (output / "summary.json.tmp").write_text(json.dumps(report, indent=2) + "\n")
            os.replace(output / "summary.json.tmp", output / "summary.json")
            print(json.dumps({"event": "evaluation_progress", "returned": len(rows), "scheduled": len(jobs),
                              "task": row["task_id"], "seed": row["seed"], "success": row["success"]}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--task", action="append", required=True)
    parser.add_argument("--seed-start", type=int, required=True)
    parser.add_argument("--episodes", type=int, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--wall-seconds", type=float, default=300)
    parser.add_argument("--allow-heldout", action="store_true")
    args = parser.parse_args()
    campaign(args.bundle, args.task, range(args.seed_start, args.seed_start + args.episodes), args.out,
             workers=args.workers, wall_seconds=args.wall_seconds, allow_heldout=args.allow_heldout)
