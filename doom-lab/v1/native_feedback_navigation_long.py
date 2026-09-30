"""Versioned navigation native-return diagnosis at 144 and 600 tics.

The exact my_way_home assets supply one +1 goal reward then Exit_Normal,
with -0.0001 living reward per tic. Fresh engines, actual-prefix custody,
and qualified frozen-policy continuation are inherited verbatim from the
reviewed Basic long-horizon implementation; its contract remains unchanged.
No visual novelty, teacher policy, or learning is included.
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
from .tasks import DoomEnv, get_task, sha_file, vizdoom_module
from .native_feedback import validate_record, same_transition, target_contract as v1_target_contract

CONTRACT_ID = "navigation_native_action4_frozen_actor_continuation_bounded_v2"
REWARD_ASSET_SHA256 = {
    "my_way_home.cfg": "3dc0eb5e3557df7918484f91bdc4bc13b78cf67c6a6eaf2052e8ad66cfccbe46",
    "my_way_home.wad": "18e98ff4c9186808eb00696b799cfe88a79e7486429c1692aafbed8ef359c0b1",
}
SCRIPTS_SHA256 = "592e9441323839b7c0f041da80218c4de31e7d4059d4758447bd16b71e0c95d6"


def reward_assets():
    root = Path(vizdoom_module().__file__).parent / "scenarios"
    actual = {name: sha_file(root / name) for name in REWARD_ASSET_SHA256}
    if actual != REWARD_ASSET_SHA256:
        raise ValueError("Navigation reward assets differ from the source-audited bound")
    return actual


def target_contract(task, continuation_checkpoint_sha256, *, horizon_tics=144):
    task = get_task(task)
    if task != get_task("navigation"):
        raise ValueError("Navigation-long contract is declared only for navigation")
    if type(horizon_tics) is not int or horizon_tics not in (144, 600):
        raise ValueError("Navigation-long diagnosis declares only horizons144,600")
    # Shared action/checkpoint validation comes from v1. This NEW contract
    # explicitly owns its horizon and bound, extending v1's 560-tic ceiling.
    value = v1_target_contract(task, continuation_checkpoint_sha256, horizon_tics=36)
    value.update(id=CONTRACT_ID, horizon_tics=horizon_tics, native_return_divisor=1.0,
        native_return_bounds=[-.0001*horizon_tics, 1.0],
        reward_asset_sha256=reward_assets(), scripts_sha256=SCRIPTS_SHA256,
        reward_bound_basis={"living_reward_per_tic": -.0001, "maximum_goal_rewards": 1,
            "goal_reward": 1.0, "source": "my_way_home SCRIPTS script3 gives reward1.0 then Exit_Normal; cfg living_reward=-0.0001"},
        value_role="Diagnostic native return only; no training or preference conversion",
        horizon_stop="At most H additional native tics or first native terminal; no bootstrap")
    value["native_events"] = value["native_events"] + ["native_goal_success"]
    return value


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
            if (not np.isfinite(value) or abs(value) > 1 + 1e-12
                    or reward < contract["native_return_bounds"][0] - 1e-9
                    or reward > contract["native_return_bounds"][1] + 1e-9):
                raise ValueError("Native value exceeds declared patch-state range; require a new explicit scale contract")
            events = {"kill_delta": after["killcount"]-before["killcount"],
                      "health_delta": after["health"]-before["health"],
                      "damage_taken_delta": after["damage_taken"]-before["damage_taken"],
                      "item_delta": after["itemcount"]-before["itemcount"],
                      "native_exit": native_outcome["native_exit"], "native_goal_success": bool(native_outcome["success"]),
                      "dead": after["dead"], "timeout": after["timeout"]}
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
