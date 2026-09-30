"""Audited autonomous practice with simulator feedback, using public Cadence repair.

The six outputs remain 36-tic repeated-action native returns divided by 300.
They are not Bellman Q values. A private worker teaches a candidate; the actor
receives immutable, development-gated snapshots only at episode boundaries.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import threading
import time

import numpy as np

try:
    from .journal import append_record
except ImportError:  # The original command-line entry points import this module directly.
    from journal import append_record


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def copied(value):
    """Finite JSON is also our explicit immutable handoff format."""
    return json.loads(json.dumps(value, allow_nan=False))


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")


def _outcome(value, *, prefix=False):
    _integer(value["tics"], "tics", 1, 12)
    rewards = value["rewards"]
    if len(rewards) != value["tics"] or any(not math.isfinite(float(x)) for x in rewards):
        raise ValueError("Every executed tic must have a finite native reward")
    if not math.isfinite(float(value["reward"])) or not math.isclose(
        sum(rewards), value["reward"], rel_tol=0, abs_tol=1e-9
    ):
        raise ValueError("Transition reward must equal its per-tic sum")
    if type(value["terminal"]) is not bool or type(value["timeout"]) is not bool:
        raise ValueError("terminal and timeout must be booleans")
    if value["timeout"] and not value["terminal"]:
        raise ValueError("Basic's finite task timeout is terminal, with no bootstrap")
    if prefix and value["terminal"]:
        raise ValueError("No action may follow a terminal prefix")
    if not value["terminal"] and value["tics"] != 12:
        raise ValueError("Nonterminal actor decisions execute exactly 12 tics")


def validate_transition(record):
    """Reject stale actions, malformed histories and manufactured terminal targets.

    An external collector cutoff is metadata on the last *actual* transition;
    it is never turned into a task terminal or assigned a synthetic reward.
    Simulator branch targets need no successor/bootstrap, so a missing final
    collector observation is acceptable. A pre-action observation is mandatory.
    """
    r = copied(record)
    if not isinstance(r["episode_id"], str) or not r["episode_id"]:
        raise ValueError("episode_id must be nonempty")
    _integer(r["seed"], "seed", 0, 2**32 - 1)
    _integer(r["step_index"], "step_index", 0, 24)
    _integer(r["executed_action"], "executed_action", 0, 5)
    if len(r["prefix_actions"]) != r["step_index"] or len(r["prefix_outcomes"]) != r["step_index"]:
        raise ValueError("History contains exactly the actions preceding this decision")
    for action, outcome in zip(r["prefix_actions"], r["prefix_outcomes"]):
        _integer(action, "prefix action", 0, 5)
        _outcome(outcome, prefix=True)
    _outcome(r["transition"])
    x = np.asarray(r["inputs"], dtype=float)
    if x.shape != (246,) or not np.isfinite(x).all():
        raise ValueError("Expected a finite normalized 246-coordinate pre-action input")
    raw_hash = r["raw_sha256"]
    if not isinstance(raw_hash, str) or len(raw_hash) != 64 or any(c not in "0123456789abcdef" for c in raw_hash):
        raise ValueError("Expected a raw pre-action frame SHA-256")
    if r.get("qualified") is not True or r.get("fallback", False):
        raise ValueError("Autonomous practice accepts only qualified, directly executed actor actions")
    if "buttons" in r:
        from basic_env import ACTIONS
        if tuple(r["buttons"]) != ACTIONS[r["executed_action"]]:
            raise ValueError("Executed buttons disagree with action ID")
    return r


def _same_outcome(expected, actual):
    return all(expected[k] == actual[k] for k in ("reward", "rewards", "tics", "terminal", "timeout"))


class BranchTeacher:
    """Reconstruct the actual student state and measure all six interventions."""
    def __init__(self, normalizer, *, episode_factory=None, encoder=None):
        from basic_env import Episode
        from models import encode
        self.episode_factory = episode_factory or Episode
        self.encoder = encoder or encode
        self.normalizer = normalizer
        self.cost = {}

    def __call__(self, record):
        r = validate_transition(record)
        labels = []
        for action in range(6):
            with self.episode_factory(r["seed"], self.cost) as episode:
                for old_action, expected in zip(r["prefix_actions"], r["prefix_outcomes"]):
                    actual = episode.step(old_action, 12, "teacher_replay")
                    if not _same_outcome(expected, actual):
                        raise ValueError("Simulator replay diverged from the executed prefix")
                raw = episode.raw()
                if raw is None or digest(raw.tobytes()) != r["raw_sha256"]:
                    raise ValueError("Simulator replay diverged from the pre-action pixels")
                x = self.encoder(raw, r["prefix_actions"], self.normalizer)
                if not np.allclose(x, r["inputs"], rtol=0, atol=1e-12):
                    raise ValueError("Normalized inputs/history do not belong to this replayed state")
                actual = episode.step(action, 36, "teacher_branch")
                if action == r["executed_action"]:
                    witness = r["transition"]
                    if actual["rewards"][:witness["tics"]] != witness["rewards"]:
                        raise ValueError("Executed action's native rewards disagree with its branch")
                    if witness["terminal"] and (actual["tics"] != witness["tics"] or not actual["terminal"]
                                                or actual["timeout"] != witness["timeout"]):
                        raise ValueError("Executed action terminal/timeout evidence disagrees")
                    if not witness["terminal"] and actual["tics"] < 12:
                        raise ValueError("Executed action falsely reported a nonterminal transition")
                    if not witness["terminal"] and actual["terminal"] and actual["tics"] == 12:
                        raise ValueError("Executed action omitted a terminal on its twelfth tic")
                labels.append(actual["reward"] / 300.0)
        return labels


class PolicyEvaluator:
    """Frozen free queries, exact executed action history, no fallback credit."""
    def __init__(self, normalizer, *, episode_wall_seconds=15):
        self.normalizer = normalizer
        self.episode_wall_seconds = episode_wall_seconds
        self.cost = {}

    def __call__(self, snapshot, seeds):
        from basic_env import Episode
        from models import Brain, encode, query
        brain = Brain.from_snapshot(snapshot, device="cpu")
        rows = []
        for seed in seeds:
            row = dict(seed=seed, status="running", killed=False, return_=0.0,
                       tics=0, queries=0, qualified_queries=0, fallback_actions=0)
            start = time.monotonic()
            try:
                with Episode(seed, self.cost) as episode:
                    prefix = []
                    while True:
                        if time.monotonic() - start > self.episode_wall_seconds:
                            row["status"] = "wall_cutoff"
                            break
                        raw = episode.raw()
                        if raw is None:
                            row["status"] = "missing_observation"
                            break
                        utility, result = query(brain, encode(raw, prefix, self.normalizer))
                        row["queries"] += 1
                        if not result["qualified"]:
                            row["status"] = "query_refused"
                            break
                        row["qualified_queries"] += 1
                        action = int(np.argmax(utility))
                        transition = episode.step(action, 12, "online_gate")
                        prefix.append(action)
                        row["return_"] += transition["reward"]
                        row["tics"] += transition["tics"]
                        row["killed"] |= any(reward > 50 for reward in transition["rewards"])
                        if transition["terminal"]:
                            row["status"] = "complete"
                            row["timeout"] = transition["timeout"]
                            break
                        if len(prefix) >= 25:
                            row["status"] = "tic_cutoff"
                            break
            except Exception as error:
                row["status"] = "environment_error"
                row["error"] = f"{type(error).__name__}: {error}"
            rows.append(row)
        return rows


@dataclass(frozen=True)
class OnlineConfig:
    queue_capacity: int = 128
    new_rows: int = 8
    original_rows: int = 8
    old_rows: int = 8
    replay_capacity: int = 512
    training_budget: int = 2048
    gate_seeds: tuple = tuple(range(740000, 740008))
    min_return_improvement: float = 0.1
    retention_rows: int = 32
    retention_relative: float = 0.25
    retention_absolute: float = 0.0005
    monitor_every_promotions: int = 5
    monitor_seed_start: int = 750000
    monitor_episodes: int = 8
    random_seed: int = 190929
    max_journal_bytes: int = 32 * 1024 * 1024

    def __post_init__(self):
        for name in ("queue_capacity", "new_rows", "replay_capacity", "training_budget", "retention_rows"):
            _integer(getattr(self, name), name, 1, 100000)
        _integer(self.max_journal_bytes, "max_journal_bytes", 1024, 2**40)
        for name in ("original_rows", "old_rows", "monitor_every_promotions", "monitor_episodes"):
            _integer(getattr(self, name), name, 0, 100000)
        if not self.gate_seeds or len(set(self.gate_seeds)) != len(self.gate_seeds):
            raise ValueError("Development gate seeds must be nonempty and distinct")
        for seed in self.gate_seeds:
            _integer(seed, "development seed", 0, 2**32 - 1)
            if 730000 <= seed <= 730063 or seed >= self.monitor_seed_start:
                raise ValueError("Development selection must exclude confirmation and fresh-monitor pools")
        if not 750000 <= self.monitor_seed_start < 800000000 or self.monitor_episodes == 0 and self.monitor_every_promotions:
            raise ValueError("Invalid fresh-monitor pool")
        for name in ("min_return_improvement", "retention_relative", "retention_absolute"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and nonnegative")


def promotion_gate(champion, candidate, seeds, min_improvement):
    reasons = []
    expected = list(seeds)
    for label, rows in (("champion", champion), ("candidate", candidate)):
        if [r.get("seed") for r in rows] != expected:
            reasons.append(label + " seed coverage/order mismatch")
        if any(r.get("status") != "complete" or r.get("queries", 0) < 1
               or r.get("queries") != r.get("qualified_queries")
               or r.get("fallback_actions", 0) != 0
               or not math.isfinite(float(r.get("return_", float("nan")))) for r in rows):
            reasons.append(label + " incomplete/unqualified/fallback outcome")
    if reasons:
        return {"passed": False, "reasons": reasons}
    if any(a["killed"] and not b["killed"] for a, b in zip(champion, candidate)):
        reasons.append("Candidate lost a previously successful development episode")
    delta = float(np.mean([b["return_"] - a["return_"] for a, b in zip(champion, candidate)]))
    if delta <= min_improvement:
        reasons.append("Mean native return improvement did not exceed the development threshold")
    return {"passed": not reasons, "reasons": reasons, "mean_return_delta": delta,
            "champion_kills": sum(bool(r["killed"]) for r in champion),
            "candidate_kills": sum(bool(r["killed"]) for r in candidate),
            "episodes": len(expected), "interpretation": "repeated development selection, not confirmation"}


class OnlineLearner:
    """Single mutable-brain owner with a bounded, acknowledged transition queue."""
    def __init__(self, snapshot, *, teacher, evaluator, replay_examples=(), config=None,
                 journal_path=None, brain_factory=None):
        if brain_factory is None:
            from models import Brain
            brain_factory = lambda text: Brain.from_snapshot(text, device="cpu")
        self.config = config or OnlineConfig()
        self.teacher, self.evaluator, self.brain_factory = teacher, evaluator, brain_factory
        self.original = copied(list(replay_examples))
        for pair in self.original:
            x, y = np.asarray(pair[0]["sensors"], dtype=float), np.asarray(pair[1]["utility"], dtype=float)
            if x.shape != (246,) or y.shape != (6,) or not np.isfinite(x).all() or not np.isfinite(y).all():
                raise ValueError("Original replay must obey the normalized 246-to-6 utility contract")
        self._queue = queue.Queue(maxsize=self.config.queue_capacity)
        self._lock = threading.RLock()
        self._submit_lock = threading.Lock()
        self._journal_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._enabled = False
        self._champion = snapshot
        self._previous_champion = None
        self._version = 0
        self._promotion = None
        self._reset = None
        self._busy = False
        self._monitor_next = self.config.monitor_seed_start
        self._retention_anchor_loss = None
        self._seen = {}  # only active/latest episode, not an unbounded trajectory store
        self._last_episode = None
        self._stats = dict(queued=0, queue_full=0, verified=0, invalid=0, batches=0,
                           accepted_updates=0, accepted_examples=0, refused_updates=0,
                           promotions=0, rejections=0, rollbacks=0, pending_rows=0,
                           original_replay_rows=len(self.original), retention_available=bool(self.original),
                           last_error=None, phase="paused", champion_sha256=digest(snapshot))
        self.journal_path = Path(journal_path) if journal_path else None
        if self.journal_path:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self._event("online_start", config=asdict(self.config), champion_sha256=digest(snapshot),
                    original_replay_rows=len(self.original), target="hold each action 36 tics; native return / 300")
        self._thread = threading.Thread(target=self._run, name="cadence-doom-online", daemon=True)
        self._thread.start()

    @classmethod
    def from_bundle(cls, bundle, *, journal_path, bundle_dir=None, config=None):
        """Use an already validated portable bundle; replay bytes are hash-bound."""
        from basic_env import ACTION_NAMES, TRANSFORM
        m, n = bundle["metadata"], bundle["normalization"]
        if (m["transform"] != TRANSFORM or tuple(m["action_names"]) != ACTION_NAMES
                or m["repeat_tics"] != 12 or m["query_budget"] != 512
                or n["clip"] != 3 or n["multiplier"] != .2
                or digest(bundle["snapshot"]) != m["hashes"]["checkpoint_sha256"]):
            raise ValueError("Bundle does not implement the frozen Basic utility contract")
        normalizer = {k: np.asarray(n[k], dtype=float) for k in ("mean", "scale")}
        if (digest(json.dumps(n, sort_keys=True, separators=(",", ":"), allow_nan=False))
                != m["hashes"]["normalization_values_sha256"]):
            raise ValueError("Normalizer digest mismatch")
        if any(a.shape != (225,) or not np.isfinite(a).all() for a in normalizer.values()) or (normalizer["scale"] <= 0).any():
            raise ValueError("Invalid normalizer")
        examples = []
        loaded = False
        if bundle_dir is not None:
            path = Path(bundle_dir) / "original_train.npz"
            expected = m["hashes"].get("original_train_sha256")
            if expected and path.exists():
                if digest(path.read_bytes()) != expected:
                    raise ValueError("Original replay digest mismatch")
                with np.load(path, allow_pickle=False) as rows:
                    if len(rows["inputs"]) != len(rows["labels"]):
                        raise ValueError("Original replay input/label count mismatch")
                    examples = [({"sensors": x.tolist()}, {"utility": y.tolist()})
                                for x, y in zip(rows["inputs"], rows["labels"])]
                loaded = True
        if not loaded and "original_replay" in bundle:
            rows = bundle["original_replay"]
            expected = m["hashes"].get("original_replay_values_sha256")
            if digest(json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False)) != expected:
                raise ValueError("Portable replay digest mismatch")
            if len(rows["inputs"]) != len(rows["labels"]):
                raise ValueError("Portable replay input/label count mismatch")
            examples = [({"sensors": x}, {"utility": y}) for x, y in zip(rows["inputs"], rows["labels"])]
            loaded = True
        if not loaded and any(k in m["hashes"] for k in ("original_train_sha256", "original_replay_values_sha256")):
            raise ValueError("Bundle promises original replay, but neither verified adjacent NPZ nor portable replay is available")
        return cls(bundle["snapshot"], teacher=BranchTeacher(normalizer),
                   evaluator=PolicyEvaluator(normalizer), replay_examples=examples,
                   config=config, journal_path=journal_path)

    def _event(self, kind, **data):
        event = {"event": kind, "unix": time.time(), **data}
        if self.journal_path:
            line = (json.dumps(event, separators=(",", ":"), allow_nan=False) + "\n").encode()
            with self._journal_lock:
                full = not append_record(self.journal_path, line,
                                         limit_bytes=self.config.max_journal_bytes)
            # Do not acquire the state lock while holding the journal lock.
            if full:
                self._set(last_error="Online journal size cap reached; archive it before restarting", phase="journal_full")
                with self._lock:
                    self._enabled = False
                self._stop.set()
                self._wake.set()
                return False
        return True

    def _set(self, **values):
        with self._lock:
            self._stats.update(values)

    def _inc(self, **values):
        with self._lock:
            for key, value in values.items():
                self._stats[key] = self._stats.get(key, 0) + value

    def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        with self._lock:
            if self._stop.is_set():
                return False
            self._enabled = enabled
        self._event("learning_enabled", enabled=enabled)
        self._wake.set()
        return True

    enable = set_enabled

    def submit_transition(self, record):
        r = validate_transition(record)
        key = (r["episode_id"], r["step_index"])
        fingerprint = digest(json.dumps(r, sort_keys=True, separators=(",", ":")))
        with self._submit_lock:
            with self._lock:
                if self._stop.is_set() or not self._enabled:
                    return False
            if key in self._seen:
                if self._seen[key] != fingerprint:
                    raise ValueError("A queued transition ID cannot change on retry")
                return True
            if self._queue.full():
                self._inc(queue_full=1)
                return False
            # Acknowledgement means recorded and queued, never 'already learned'.
            if not self._event("transition_queued", transition=r):
                return False
            self._queue.put_nowait(r)
            if r["episode_id"] != self._last_episode:
                self._seen.clear()
                self._last_episode = r["episode_id"]
            self._seen[key] = fingerprint
            self._inc(queued=1)
        self._wake.set()
        return True

    def status(self):
        with self._lock:
            return copied({**self._stats, "enabled": self._enabled, "busy": self._busy,
                           "queue_depth": self._queue.qsize(), "version": self._version,
                           "queue": self._queue.qsize(), "updates": self._stats["accepted_updates"],
                           "error": self._stats["last_error"],
                           "rollback_available": self._previous_champion is not None,
                           "stopped": not self._thread.is_alive(),
                           "promotion_pending": self._promotion is not None})

    def take_promotion(self):
        """The actor calls only before resetting an episode/history."""
        with self._lock:
            value, self._promotion = self._promotion, None
            return copied(value)

    def rollback(self):
        with self._lock:
            if self._previous_champion is None or self._stop.is_set():
                return False
            self._reset = self._previous_champion
        self._wake.set()
        return True

    def close(self, wait=False):
        """Stop accepting work. Current uncancellable repair/branch finishes safely.

        Queued records remain in the journal; they are not claimed as learned.
        The caller can poll status or request wait=True outside the UI thread.
        """
        self._stop.set()
        with self._lock:
            self._enabled = False
        self._wake.set()
        if wait:
            self._thread.join()
        return not self._thread.is_alive()

    def _loss(self, brain, examples):
        if not examples:
            return None
        errors = []
        for x, y in examples:
            result = brain.settle(x, budget=512)
            if not result["qualified"]:
                return float("inf")
            errors.extend((np.asarray(result["outputs"]["utility"]) - y["utility"]) ** 2)
        return float(np.mean(errors))

    def _publish(self, snapshot, *, kind):
        with self._lock:
            if kind == "promotion" and (not self._enabled or self._reset is not None or self._stop.is_set()):
                return False
            version = self._version + 1
            if not self._event(kind, version=version, snapshot=snapshot, checkpoint_sha256=digest(snapshot)):
                return False
            self._previous_champion, self._champion = self._champion, snapshot
            self._version = version
            self._promotion = {"snapshot": snapshot, "version": self._version,
                               "checkpoint_sha256": digest(snapshot), "kind": kind}
            self._stats["champion_sha256"] = digest(snapshot)
        return True

    def _monitor_seeds(self):
        """Reserve once, before evaluation; crashes consume rather than reuse seeds."""
        def reserve(start):
            start = max(int(start), self.config.monitor_seed_start)
            end = start + self.config.monitor_episodes
            if end > 800000000:
                return [], start
            return list(range(start, end)), end
        if self.journal_path is None:
            seeds, self._monitor_next = reserve(self._monitor_next)
            return seeds
        import fcntl
        cursor = self.journal_path.with_suffix(".monitor-seeds.json")
        with cursor.open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                stream.seek(0)
                previous = stream.read()
                start = json.loads(previous)["next_seed"] if previous else self.config.monitor_seed_start
                seeds, end = reserve(start)
                stream.seek(0); stream.truncate()
                json.dump({"next_seed": end}, stream)
                stream.flush(); os.fsync(stream.fileno())
                return seeds
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _run(self):
        rng = np.random.default_rng(self.config.random_seed)
        old = deque(maxlen=self.config.replay_capacity)
        new = []
        candidate = None
        try:
            candidate = self.brain_factory(self._champion)
            self._retention_anchor_loss = self._loss(candidate, self.original[:self.config.retention_rows])
            anchor = self._retention_anchor_loss
            self._set(retention_anchor_loss=anchor if anchor is None or math.isfinite(anchor) else None,
                      retention_anchor_qualified=anchor is None or math.isfinite(anchor))
            self._event("retention_anchor", checkpoint_sha256=digest(self._champion),
                        loss=anchor if anchor is None or math.isfinite(anchor) else None,
                        qualified=anchor is None or math.isfinite(anchor),
                        rows=min(len(self.original), self.config.retention_rows))
            while not self._stop.is_set():
                with self._lock:
                    reset, self._reset = self._reset, None
                    enabled = self._enabled
                if reset is not None:
                    candidate = self.brain_factory(reset)
                    if self._publish(reset, kind="rollback"):
                        self._inc(rollbacks=1)
                if not enabled:
                    self._set(phase="paused")
                    self._wake.wait(.1)
                    self._wake.clear()
                    continue
                try:
                    record = self._queue.get(timeout=.1)
                except queue.Empty:
                    self._set(phase="waiting_for_transitions")
                    continue
                with self._lock:
                    self._busy = True
                try:
                    self._set(phase="simulator_feedback")
                    labels = np.asarray(self.teacher(record), dtype=float)
                    if labels.shape != (6,) or not np.isfinite(labels).all() or np.max(np.abs(labels)) > 1:
                        raise ValueError("Simulator teacher must return six finite native returns / 300 in [-1, 1]")
                    pair = ({"sensors": record["inputs"]}, {"utility": labels.tolist()})
                    new.append(pair)
                    self._inc(verified=1)
                    self._event("transition_verified", episode_id=record["episode_id"],
                                step_index=record["step_index"], targets=labels.tolist(),
                                teacher_cost=getattr(self.teacher, "cost", {}))
                    self._set(pending_rows=len(new))
                    if len(new) >= self.config.new_rows and not self._stop.is_set():
                        with self._lock:
                            may_train = self._enabled and self._reset is None
                        if may_train:
                            candidate, promoted, admitted = self._update(candidate, new, old, rng)
                            if admitted:
                                old.extend(new)
                                new.clear()
                                self._set(pending_rows=0)
                            if promoted and self.config.monitor_every_promotions and (
                                self._stats["promotions"] % self.config.monitor_every_promotions == 0
                            ):
                                seeds = self._monitor_seeds()
                                if not seeds:
                                    self._event("fresh_monitor_pool_exhausted")
                                else:
                                    rows = self.evaluator(self._champion, seeds)
                                    self._event("fresh_monitor", seeds=seeds, outcomes=rows,
                                                checkpoint_sha256=digest(self._champion),
                                                interpretation="report only; never a promotion selection input")
                except Exception as error:
                    self._inc(invalid=1)
                    self._set(last_error=f"{type(error).__name__}: {error}")
                    self._event("transition_failed", episode_id=record["episode_id"],
                                step_index=record["step_index"], error=str(error))
                    # No partially learned candidate can escape after any worker error.
                    candidate = self.brain_factory(self._champion)
                finally:
                    self._queue.task_done()
                    with self._lock:
                        self._busy = False
        except Exception as error:
            self._set(last_error=f"{type(error).__name__}: {error}", phase="worker_failed")
            self._stop.set()
            self._event("worker_failed", error=str(error))
        finally:
            self._set(phase="closed", pending_rows=len(new))
            self._event("online_closed", pending_queue=self._queue.qsize(), pending_rows=len(new),
                        accepted_updates=self._stats["accepted_updates"])

    def _update(self, candidate, new, old, rng):
        def sample(rows, count):
            if not rows or not count:
                return []
            return [rows[int(i)] for i in rng.choice(len(rows), size=min(len(rows), count), replace=False)]
        batch = copied(new + sample(self.original, self.config.original_rows) + sample(list(old), self.config.old_rows))
        retention = self.original[:self.config.retention_rows]
        self._set(phase="candidate_learning")
        before_loss = self._loss(candidate, retention)
        start = time.monotonic()
        result = candidate.observe_batch(batch, budget=self.config.training_budget, source="estimate")
        self._inc(batches=1)
        accepted = bool(result["accepted"] and result["qualified"] and not result.get("duplicate", False))
        self._event("admission", accepted=accepted, examples=len(batch),
                    new_examples=len(new), source="estimate", seconds=time.monotonic() - start,
                    event_id=result.get("event_id"), sweeps=result.get("sweeps"), reason=result.get("reason"),
                    candidate_sha256=digest(candidate.snapshot()))
        if not accepted:
            self._inc(refused_updates=1)
            # Retain every new row; an explicit resume may attempt a new batch.
            # Admission counters/event ownership never advance on refusal.
            with self._lock:
                self._enabled = False
            self._set(last_error="Candidate admission refused; pending examples retained; learning paused")
            return self.brain_factory(self._champion), False, False
        self._inc(accepted_updates=1, accepted_examples=len(batch))
        if self._stop.is_set():
            return self.brain_factory(self._champion), False, True
        after_loss = self._loss(candidate, retention)
        anchor = self._retention_anchor_loss
        retention_ok = before_loss is None or (
            math.isfinite(before_loss) and math.isfinite(after_loss) and math.isfinite(anchor)
            and after_loss <= min(before_loss, anchor) * (1 + self.config.retention_relative)
            + self.config.retention_absolute)
        candidate_snapshot = candidate.snapshot()
        self._set(phase="development_gate")
        champion_rows = self.evaluator(self._champion, self.config.gate_seeds)
        candidate_rows = self.evaluator(candidate_snapshot, self.config.gate_seeds)
        gate = promotion_gate(champion_rows, candidate_rows, self.config.gate_seeds, self.config.min_return_improvement)
        if not retention_ok:
            gate["passed"] = False
            gate["reasons"].append("Original utility replay retention check failed")
        self._event("development_gate", **gate, champion=champion_rows, candidate=candidate_rows,
                    retention_before=before_loss if before_loss is None or math.isfinite(before_loss) else None,
                    retention_after=after_loss if after_loss is None or math.isfinite(after_loss) else None,
                    retention_anchor=anchor if anchor is None or math.isfinite(anchor) else None,
                    retention_qualified=retention_ok, candidate_sha256=digest(candidate_snapshot),
                    evaluation_cost=getattr(self.evaluator, "cost", {}))
        with self._lock:
            may_publish = self._enabled and self._reset is None and not self._stop.is_set()
        if gate["passed"] and may_publish:
            if self._publish(candidate_snapshot, kind="promotion"):
                self._inc(promotions=1)
                return candidate, True, True
        self._inc(rejections=1)
        return self.brain_factory(self._champion), False, True
