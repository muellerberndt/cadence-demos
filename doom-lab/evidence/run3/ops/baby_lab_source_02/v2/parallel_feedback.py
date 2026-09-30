"""Opt-in parallel simulator feedback, with fresh Doom engines per branch.

Only Python workers persist. Reusing a DoomGame after new_episode failed an
exact-frame probe and is deliberately absent from this implementation.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import os
import threading

import numpy as np

from basic_env import Episode, compact, history, pool
from online import digest, validate_transition


def _initialize_worker():
    # The parent also sets these before spawn, so imports obey the same bound.
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                 "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"


def _branch(record, action):
    """A worker owns and closes one fresh simulator, never a Cadence brain."""
    cost = {"engine_initialization_attempts": 1}
    try:
        with Episode(record["seed"], cost) as episode:
            for old_action, expected in zip(record["prefix_actions"], record["prefix_outcomes"]):
                actual = episode.step(old_action, 12, "teacher_replay")
                if any(actual[k] != expected[k] for k in ("reward", "rewards", "tics", "terminal", "timeout")):
                    raise ValueError("Simulator replay diverged from the executed prefix")
            raw = episode.raw()
            if raw is None or digest(raw.tobytes()) != record["raw_sha256"]:
                raise ValueError("Simulator replay diverged from the pre-action pixels")
            # Exact same float32 pool/compact then float64 cast as models.encode.
            small = compact(pool(raw)).astype(float).tolist()
            actual = episode.step(action, 36, "teacher_branch")
            if action == record["executed_action"]:
                witness = record["transition"]
                if actual["rewards"][:witness["tics"]] != witness["rewards"]:
                    raise ValueError("Executed action's rewards disagree with its branch")
                if witness["terminal"] and (actual["tics"] != witness["tics"] or not actual["terminal"]
                                            or actual["timeout"] != witness["timeout"]):
                    raise ValueError("Executed action terminal/timeout evidence disagrees")
                if not witness["terminal"] and (actual["tics"] < 12 or actual["terminal"] and actual["tics"] == 12):
                    raise ValueError("Executed action omitted an earlier terminal")
            return {"ok": True, "action": action, "small": small, "outcome": actual,
                    "cost": cost, "pid": os.getpid()}
    except Exception as error:
        return {"ok": False, "action": action, "error": f"{type(error).__name__}: {error}",
                "cost": cost, "pid": os.getpid()}


class ParallelBranchTeacher:
    """BranchTeacher-compatible callable; no silent serial or label fallback.

    Calls are serialized; at most six branch tasks are in flight. The parent
    owns normalization and returns targets in the declared six-action order.
    A failed branch rejects the whole teaching context. close(wait=False)
    refuses new calls and drains any current call in a cleanup thread.
    """
    def __init__(self, normalizer, *, workers=6):
        if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 6:
            raise ValueError("Simulator feedback workers must be an integer from1 through6")
        self.normalizer = {key: np.array(normalizer[key], dtype=float, copy=True) for key in ("mean", "scale")}
        if any(x.shape != (225,) or not np.isfinite(x).all() for x in self.normalizer.values()) or (self.normalizer["scale"] <= 0).any():
            raise ValueError("Expected the frozen225-coordinate mean and positive scale")
        for value in self.normalizer.values():
            value.setflags(write=False)
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                     "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
            os.environ[name] = "1"
        self.workers = workers
        self.cost = {}
        self._calls = threading.Lock()
        self._state = threading.Lock()
        self._closing = False
        self._closed = threading.Event()
        self._shutdown_thread = None
        self._executor = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                                             initializer=_initialize_worker)

    def __call__(self, record):
        from models import encode_small
        record = validate_transition(record)
        with self._calls:
            with self._state:
                if self._closing:
                    raise RuntimeError("Parallel simulator teacher is closing; no new context was submitted")
            futures, results, errors = [], [], []
            for action in range(6):
                try:
                    futures.append(self._executor.submit(_branch, record, action))
                except Exception as error:
                    errors.append(f"submission action{action}: {type(error).__name__}: {error}")
                    break
            self.cost["branch_submissions"] = self.cost.get("branch_submissions", 0) + len(futures)
            # Drain all scheduled tasks even if one fails. Do not admit partial labels.
            for action, future in enumerate(futures):
                try:
                    result = future.result()
                    results.append(result)
                    for key, count in result["cost"].items():
                        self.cost[key] = self.cost.get(key, 0) + count
                    if not result["ok"]:
                        errors.append(f"action{action}: {result['error']}")
                except Exception as error:
                    self.cost["worker_failures"] = self.cost.get("worker_failures", 0) + 1
                    errors.append(f"action{action}: {type(error).__name__}: {error}")
            self.cost["feedback_context_attempts"] = self.cost.get("feedback_context_attempts", 0) + 1
            if errors:
                self.cost["feedback_context_refusals"] = self.cost.get("feedback_context_refusals", 0) + 1
                raise RuntimeError("Parallel simulator feedback refused; " + "; ".join(errors))
            labels = []
            for action, result in enumerate(results):
                if result["action"] != action:
                    raise RuntimeError("Parallel feedback action ordering changed")
                encoded = encode_small(result["small"], history(record["prefix_actions"]), self.normalizer)
                if not np.allclose(encoded, record["inputs"], rtol=0, atol=1e-12):
                    self.cost["feedback_context_refusals"] = self.cost.get("feedback_context_refusals", 0) + 1
                    raise ValueError("Normalized inputs/history do not belong to this replayed state")
                labels.append(result["outcome"]["reward"] / 300.0)
            self.cost["feedback_contexts"] = self.cost.get("feedback_contexts", 0) + 1
            return labels

    def close(self, wait=True):
        with self._state:
            if not self._closing:
                self._closing = True
                def shutdown():
                    try:
                        with self._calls:
                            self._executor.shutdown(wait=True, cancel_futures=False)
                    finally:
                        self._closed.set()
                self._shutdown_thread = threading.Thread(target=shutdown, name="doom-feedback-cleanup", daemon=False)
                self._shutdown_thread.start()
        if wait:
            self._closed.wait()
        return self._closed.is_set()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close(wait=True)
