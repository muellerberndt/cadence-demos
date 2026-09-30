"""Versioned Basic native-return contract for delayed-outcome comparison.

This module leaves native_feedback v1 unchanged. Interventions, replay custody,
fresh engines and frozen qualified continuation are identical. The scale bound
is derived from the exact installed Basic SCRIPTS and cfg, bound by file hashes:
one -5 ammo penalty at most per tic, -1 living reward per tic, one +106 kill
reward followed immediately by Exit_Normal. The conservative H-tic return
interval is [-6H,106]. Native values are intermediate ranking evidence; the
practice learner still has to declare its bounded policy-preference transform.
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

CONTRACT_ID = "basic_native_action4_frozen_actor_continuation_bounded_v2"
REWARD_ASSET_SHA256 = {
    "basic.cfg": "306ce424442279a1e5d98a75c36a900b616c2496dcdac93a2923946049c926e7",
    "basic.wad": "fd0b7e5e2422e09288c786e7fc32181bb8ee4a3faa613a75ef88a3e39b5ce94e",
}
BASIC_SCRIPTS_SHA256 = "7d8c0261fdc1df7c775445ab518576ca157aaea76723541999c37b626f689f6a"


def reward_assets():
    """Reject an unreviewed scenario instead of assuming its reward bound."""
    root = Path(vizdoom_module().__file__).parent / "scenarios"
    actual = {name: sha_file(root / name) for name in REWARD_ASSET_SHA256}
    if actual != REWARD_ASSET_SHA256:
        raise ValueError("Basic reward assets differ from the source-audited bound")
    return actual


def target_contract(task, continuation_checkpoint_sha256, *, horizon_tics=144):
    task = get_task(task)
    if task != get_task("basic"):
        raise ValueError("Version2 reward bound is declared only for the unchanged Basic task")
    if horizon_tics not in (36, 144, 300):
        raise ValueError("Version2 comparison declares only horizons36,144,300")
    value = v1_target_contract(task, continuation_checkpoint_sha256, horizon_tics=horizon_tics)
    value.update(id=CONTRACT_ID, native_return_divisor=float(max(106, 6*horizon_tics)),
                 native_return_bounds=[float(-6*horizon_tics), 106.0],
                 reward_asset_sha256=reward_assets(), scripts_sha256=BASIC_SCRIPTS_SHA256,
                 reward_bound_basis={"living_reward_per_tic": -1.0,
                     "maximum_ammo_penalties_per_tic": 1, "ammo_penalty": -5.0,
                     "maximum_kill_rewards": 1, "kill_reward": 106.0,
                     "source": "Basic SCRIPTS ammo loop delay(1); kill script immediately Exit_Normal; cfg living_reward=-1"},
                 value_role="intermediate native-return ranking evidence; not bootstrap action codes or automatically admitted patch targets",
                 horizon_stop="at most H additional native tics or first native terminal; no zero-value bootstrap")
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
