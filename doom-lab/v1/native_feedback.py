"""Exact native experience labels for the twenty-action, four-tic Doom actor.

Each intervention starts from a fresh engine and replays actual action history.
After one four-tic action, only the frozen Cadence actor controls continuation.
No geometry teacher, privileged route, invented action value, or failed-query
fallback is used. Native events are recorded separately from scalar reward.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path
import time

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import numpy as np

from .interface import ACTION_NAMES, PORT_SHAPES, REPEAT_TICS, canonical, digest
from .tasks import DoomEnv, get_task


CONTRACT_ID = "native_action4_frozen_actor_continuation_v1"
COMPARE_FIELDS = ("action", "buttons", "requested_tics", "tics", "rewards", "reward",
                  "terminal", "dead", "timeout", "native_kill_delta", "health_delta", "episode_tic")


def target_contract(task, continuation_checkpoint_sha256, *, horizon_tics=None):
    task = get_task(task)
    if task.task_id not in {"basic", "navigation", "survival", "health_survival", "doors", "combined"} and task.objective != "native_exit":
        raise ValueError("Task lacks a declared native feedback contract")
    if not isinstance(continuation_checkpoint_sha256, str) or len(continuation_checkpoint_sha256) != 64:
        raise ValueError("A frozen continuation checkpoint hash is required")
    if any(c not in "0123456789abcdef" for c in continuation_checkpoint_sha256):
        raise ValueError("Malformed checkpoint hash")
    horizon = (144 if task.objective == "survival" else 36) if horizon_tics is None else horizon_tics
    if type(horizon) is not int or not REPEAT_TICS <= horizon <= 560 or horizon % REPEAT_TICS:
        raise ValueError("Native feedback horizon must be4..560 tics in whole decisions")
    divisor = 300.0 if task.task_id == "basic" else float(horizon) if task.objective == "survival" else 1.0
    return {"id": CONTRACT_ID, "task": task.__dict__, "action_names": list(ACTION_NAMES),
            "initial_action_tics": REPEAT_TICS, "continuation": "frozen_qualified_cadence_actor",
            "continuation_checkpoint_sha256": continuation_checkpoint_sha256,
            "horizon_tics": horizon, "native_return_divisor": divisor, "discount": 1.0,
            "bootstrap": False, "output": "action_scores", "dimensions": len(ACTION_NAMES),
            "value_source": "sum of native game rewards only", "privileged_reward_shaping": False,
            "native_events": ["kill_delta", "health_delta", "damage_taken_delta", "item_delta", "native_exit", "dead", "timeout"],
            "partial_or_refused_branch": "reject complete twenty-coordinate context",
            "full_game_caveat": "Unmodified IWAD native rewards can all be zero; event evidence is not silently converted into utility",
            "target_boundary": "Native action values have different units from bootstrap expert action codes; do not silently mix them as replay labels"}


def validate_record(record):
    row = json.loads(canonical(record))
    required = {"task", "seed", "episode_id", "step_index", "prefix_actions", "prefix_outcomes",
                "raw_sha256", "inputs", "executed_action", "transition", "policy_checkpoint_sha256",
                "qualified", "fallback", "behavior_source"}
    if not required <= row.keys():
        raise ValueError(f"Native transition lacks {sorted(required-row.keys())}")
    get_task(row["task"])
    if row["qualified"] is not True or row["fallback"] is not False or row["behavior_source"] != "autonomous":
        raise ValueError("Online native feedback requires qualified autonomous experience without fallback")
    if type(row["seed"]) is not int or type(row["step_index"]) is not int or row["step_index"] < 0:
        raise ValueError("Seed and step index must be integers")
    if len(row["prefix_actions"]) != row["step_index"] or len(row["prefix_outcomes"]) != row["step_index"]:
        raise ValueError("History length does not match step index")
    for action in row["prefix_actions"] + [row["executed_action"]]:
        if type(action) is not int or action not in range(len(ACTION_NAMES)):
            raise ValueError("Illegal action in native transition")
    if set(row["inputs"]) != set(PORT_SHAPES):
        raise ValueError("Transition requires the complete four-port actor observation")
    for name, size in PORT_SHAPES.items():
        values = np.asarray(row["inputs"][name], dtype=float)
        if values.shape != (size,) or not np.isfinite(values).all():
            raise ValueError(f"Invalid {name} observation")
    for value in (row["raw_sha256"], row["policy_checkpoint_sha256"]):
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("Malformed transition content hash")
    for index, transition in enumerate(row["prefix_outcomes"] + [row["transition"]]):
        if not set(COMPARE_FIELDS) <= transition.keys():
            raise ValueError("Native outcome omits replay custody fields")
        if (type(transition["tics"]) is not int or not 1 <= transition["tics"] <= REPEAT_TICS
                or len(transition["rewards"]) != transition["tics"]
                or abs(sum(transition["rewards"])-transition["reward"]) > 1e-12):
            raise ValueError("Native outcome has invalid time/reward accounting")
        if transition["action"] != (row["prefix_actions"] + [row["executed_action"]])[index]:
            raise ValueError("Outcome does not belong to its executed action")
        if index < row["step_index"] and transition["terminal"]:
            raise ValueError("Current frame cannot follow a terminal prefix")
    return row


def same_transition(actual, expected):
    return all(actual[key] == expected[key] for key in COMPARE_FIELDS)


def rollout_branch(record, action, contract, bundle, *, env_factory=DoomEnv, actor_factory=None):
    from .brain import Actor
    actor_factory = actor_factory or Actor
    cost = {"engine_initialization_attempts": 0, "replay_tics": 0, "branch_tics": 0,
            "continuation_queries": 0, "qualified_continuation_queries": 0}
    started = time.monotonic()
    try:
        row = validate_record(record)
        actor = actor_factory(bundle, device="cpu")
        expected_contract = target_contract(row["task"], actor.checkpoint_hash, horizon_tics=contract["horizon_tics"])
        if canonical(contract) != canonical(expected_contract):
            raise ValueError("Native target contract does not match task/frozen continuation actor")
        if type(action) is not int or action not in range(len(ACTION_NAMES)):
            raise ValueError("Invalid branch action")
        actor.reset()
        cost["engine_initialization_attempts"] += 1
        with env_factory(row["task"], row["seed"], teacher=False) as env:
            cost["engine_initializations"] = 1
            for previous, expected in zip(row["prefix_actions"], row["prefix_outcomes"]):
                raw = env.observe()
                actual = env.step(previous, tics=expected["requested_tics"])
                if not same_transition(actual, expected):
                    raise ValueError("Actual prefix does not reproduce exact native outcomes")
                actor.history.acknowledge(raw, previous, actual["tics"])
                cost["replay_tics"] += actual["tics"]
            raw = env.observe()
            if digest(raw.tobytes()) != row["raw_sha256"]:
                raise ValueError("Exact pre-action pixel digest differs on fresh replay")
            inputs = actor.history.encode(raw, actor.bundle["normalization"])
            if any(not np.allclose(inputs[name], row["inputs"][name], rtol=0, atol=1e-12) for name in PORT_SHAPES):
                raise ValueError("Actor sensory/history ports differ on replay")
            before = env.facts()
            transitions, actions, queries = [], [], []
            remaining = contract["horizon_tics"]
            while remaining > 0 and not env.finished:
                raw = env.observe()
                if not transitions:
                    selected = action
                else:
                    proposal = actor.choose(raw)
                    cost["continuation_queries"] += 1
                    if not proposal.get("qualified"):
                        raise ValueError("Continuation query refused; no fallback value")
                    selected = proposal["action"]
                    cost["qualified_continuation_queries"] += 1
                    queries.append({"action": selected, "qualified": True, "query_seconds": proposal.get("query_seconds")})
                transition = env.step(selected, tics=min(REPEAT_TICS, remaining))
                if not transitions:
                    if action == row["executed_action"] and not same_transition(transition, row["transition"]):
                        raise ValueError("Recorded executed transition differs from native branch replay")
                    actor.history.acknowledge(raw, selected, transition["tics"])
                else:
                    actor.acknowledge(raw, selected, transition["tics"])
                actions.append(selected)
                transitions.append(transition)
                remaining -= transition["tics"]
                cost["branch_tics"] += transition["tics"]
            after = env.facts()
            native_outcome = env.outcome()
            reward = sum(t["reward"] for t in transitions)
            value = reward / contract["native_return_divisor"]
            if not np.isfinite(value) or abs(value) > 1:
                raise ValueError("Native value exceeds declared patch-state range; require a new explicit scale contract")
            events = {"kill_delta": after["killcount"]-before["killcount"],
                      "health_delta": after["health"]-before["health"],
                      "damage_taken_delta": after["damage_taken"]-before["damage_taken"],
                      "item_delta": after["itemcount"]-before["itemcount"],
                      "native_exit": native_outcome["native_exit"], "dead": after["dead"], "timeout": after["timeout"]}
            return {"ok": True, "action": action, "label": value, "native_return": reward,
                    "actions": actions, "transitions": transitions, "continuation_queries": queries,
                    "events": events, "terminal": after["terminal"], "tics": cost["branch_tics"],
                    "behavior_checkpoint_sha256": row["policy_checkpoint_sha256"],
                    "continuation_checkpoint_sha256": actor.checkpoint_hash,
                    "cost": cost, "wall_seconds": time.monotonic()-started}
    except Exception as error:
        return {"ok": False, "action": action, "error": f"{type(error).__name__}: {error}",
                "cost": cost, "wall_seconds": time.monotonic()-started}


def aggregate(branches, contract):
    valid = (len(branches) == len(ACTION_NAMES)
             and all(row.get("ok") and row.get("action") == index for index, row in enumerate(branches)))
    labels = [row["label"] for row in branches] if valid else None
    cost = {}
    for row in branches:
        for key, value in row.get("cost", {}).items():
            cost[key] = cost.get(key, 0) + value
    return {"ok": valid, "labels": labels, "contract": contract, "branches": branches, "cost": cost,
            "informative": bool(valid and max(labels)-min(labels) > 1e-12),
            "label_range": [min(labels), max(labels)] if valid else None,
            "interpretation": "Native reward interventions under one frozen continuation policy; no teacher action labels"}


def label(record, contract, *, bundle):
    return aggregate([rollout_branch(record, action, contract, bundle) for action in range(len(ACTION_NAMES))], contract)


def _initialize(bundle):
    from .brain import Actor
    global _BUNDLE, _ACTOR
    _BUNDLE = bundle
    # Each process is serial and never learns. Reset discards proposal/history;
    # parsing the same immutable brain once does not reuse native game state.
    _ACTOR = Actor(bundle, device="cpu")


def _branch(payload):
    record, action, contract = payload
    return rollout_branch(record, action, contract, _BUNDLE,
                          actor_factory=lambda _bundle, device: _ACTOR)


class NativeFeedbackPool:
    def __init__(self, bundle, workers=6):
        if type(workers) is not int or not 1 <= workers <= 32:
            raise ValueError("workers must be1..32")
        if isinstance(bundle, (str, Path)):
            bundle = json.loads(Path(bundle).read_text())
        self.bundle = json.loads(canonical(bundle))
        self.pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                                        initializer=_initialize, initargs=(self.bundle,))
        self.closed = False
        self.cost = {}

    def label(self, record, contract):
        if self.closed:
            raise RuntimeError("Native feedback pool is closed")
        row = validate_record(record)
        futures = []
        for action in range(len(ACTION_NAMES)):
            try:
                futures.append(self.pool.submit(_branch, (row, action, contract)))
            except Exception as error:
                futures.append(error)
        branches = []
        for action, future in enumerate(futures):
            try:
                if isinstance(future, Exception):
                    raise future
                branches.append(future.result())
            except Exception as error:
                branches.append({"ok": False, "action": action, "error": repr(error), "cost": {"worker_failures": 1}})
        result = aggregate(branches, contract)
        for key, value in result["cost"].items():
            self.cost[key] = self.cost.get(key, 0) + value
        return result

    def close(self):
        if not self.closed:
            self.pool.shutdown(wait=True, cancel_futures=False)
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
