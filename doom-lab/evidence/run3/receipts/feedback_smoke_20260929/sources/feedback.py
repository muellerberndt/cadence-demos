"""Explicit finite-horizon simulator labels; no mutation of the live v2 actor.

Only independent process workers own simulators/continuation brains. A failed
branch invalidates the complete six-coordinate label, never a fallback target.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import hashlib
import multiprocessing
import os
from pathlib import Path
import sys

for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
              'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'
V2 = Path(__file__).resolve().parents[1] / 'v2'
sys.path.insert(0, str(V2))
import numpy as np
from basic_env import ACTION_NAMES, Episode
from online import PolicyEvaluator, validate_transition

HOLD = 'utility_hold36_v1'
CONTINUE = 'utility_action12_frozen_champion36_v1'
CONTRACTS = (HOLD, CONTINUE)


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def target_contract(name, continuation_sha256):
    if name not in CONTRACTS:
        raise ValueError('Unknown simulator utility contract')
    if not isinstance(continuation_sha256, str) or len(continuation_sha256) != 64:
        raise ValueError('Expected exact continuation checkpoint SHA-256')
    return dict(id=name, scenario='basic', action_names=list(ACTION_NAMES),
                actor_repeat_tics=12, horizon_tics=36, native_return_divisor=300,
                discount=1, bootstrap=False, initial_action_tics=36 if name == HOLD else 12,
                continuation='hold_initial_action' if name == HOLD else 'frozen_champion',
                continuation_checkpoint_sha256=None if name == HOLD else continuation_sha256,
                continuation_query_budget=None if name == HOLD else 512,
                continuation_uses_executed_action_history=True,
                refusal='reject_complete_context', native_timeout_is_terminal=True,
                external_interruption='incomplete_context', output='utility', dimensions=6)


def same_outcome(a, b):
    return all(a[k] == b[k] for k in ('reward', 'rewards', 'tics', 'terminal', 'timeout'))


def rollout_branch(record, action, contract, normalizer, brain, *,
                   episode_factory=Episode, encoder=None, query_fn=None):
    """One exact reconstructed intervention; dependency hooks support custody tests."""
    from models import encode, query
    encoder = encoder or encode
    query_fn = query_fn or query
    if contract not in CONTRACTS or isinstance(action, bool) or action not in range(6):
        raise ValueError('Expected a declared contract and six-way action ID')
    r = validate_transition(record)
    cost = {'engine_initialization_attempts': 1}
    try:
        with episode_factory(r['seed'], cost) as episode:
            prefix = list(r['prefix_actions'])
            for old_action, expected in zip(prefix, r['prefix_outcomes']):
                actual = episode.step(old_action, 12, 'feedback_replay')
                if not same_outcome(actual, expected):
                    raise ValueError('Executed prefix does not replay exactly')
            raw = episode.raw()
            if raw is None or sha(raw.tobytes()) != r['raw_sha256']:
                raise ValueError('Pre-action frame does not replay exactly')
            if not np.allclose(encoder(raw, prefix, normalizer), r['inputs'], rtol=0, atol=1e-12):
                raise ValueError('Inputs/history do not belong to reconstructed frame')
            transitions, actions, queries = [], [], []
            # Segment even the hold control into12tics so executed-action custody
            # is checked with exactly the same complete first transition.
            for decision in range(3):
                if decision and contract == CONTINUE:
                    raw = episode.raw()
                    if raw is None:
                        raise ValueError('Continuation has no pre-action observation')
                    utilities, result = query_fn(brain, encoder(raw, prefix, normalizer))
                    cost['continuation_queries'] = cost.get('continuation_queries', 0) + 1
                    cost['continuation_sweeps'] = cost.get('continuation_sweeps', 0) + result.get('sweeps', 0)
                    if not result['qualified']:
                        raise ValueError('Continuation query refused; no fallback target')
                    utilities = np.asarray(utilities, dtype=float)
                    if utilities.shape != (6,) or not np.isfinite(utilities).all():
                        raise ValueError('Continuation returned invalid utilities')
                    selected = int(np.argmax(utilities))
                    queries.append(dict(action=selected, qualified=True, sweeps=result.get('sweeps')))
                else:
                    selected = action
                outcome = episode.step(selected, 12, 'feedback_branch')
                if decision == 0 and action == r['executed_action'] and not same_outcome(outcome, r['transition']):
                    raise ValueError('Executed action transition does not match native replay')
                actions.append(selected)
                transitions.append(outcome)
                prefix.append(selected)
                if outcome['terminal']:
                    break
            reward = sum(t['reward'] for t in transitions)
            return dict(ok=True, action=action, contract=contract, label=reward/300,
                        reward=reward, tics=sum(t['tics'] for t in transitions),
                        actions=actions, transitions=transitions, queries=queries, cost=cost)
    except Exception as error:
        return dict(ok=False, action=action, contract=contract,
                    error=f'{type(error).__name__}: {error}', cost=cost)


def _initialize(snapshot, normalizer):
    from models import Brain
    global _BRAIN, _NORMALIZER
    _BRAIN = Brain.from_snapshot(snapshot, device='cpu')
    _NORMALIZER = {k: np.asarray(normalizer[k], dtype=float) for k in ('mean', 'scale')}


def _branch(task):
    record, action, contract = task
    return rollout_branch(record, action, contract, _NORMALIZER, _BRAIN)


def _evaluate(task):
    snapshot, seed = task
    evaluator = PolicyEvaluator(_NORMALIZER)
    return dict(outcome=evaluator(snapshot, [seed])[0], cost=evaluator.cost)


class FeedbackPool:
    """A bounded pool, used serially by one experiment owner; fresh engines always."""
    def __init__(self, snapshot, normalizer, workers=6):
        if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 32:
            raise ValueError('workers must be an integer from1 through32')
        self.cost = {}
        self.closed = False
        self.executor = ProcessPoolExecutor(max_workers=workers,
            mp_context=multiprocessing.get_context('spawn'), initializer=_initialize,
            initargs=(snapshot, {k: np.asarray(v).tolist() for k, v in normalizer.items()}))

    def _add_cost(self, values):
        for key, value in values.items():
            self.cost[key] = self.cost.get(key, 0) + value

    def label(self, record, contract):
        if self.closed:
            raise RuntimeError('Feedback pool is closed')
        record = validate_transition(record)
        tasks = [(record, action, contract) for action in range(6)]
        rows = list(self.executor.map(_branch, tasks))
        for row in rows:
            self._add_cost(row['cost'])
        valid = len(rows) == 6 and all(row['ok'] and row['action'] == i for i, row in enumerate(rows))
        labels = [row['label'] for row in rows] if valid else None
        if labels is not None and (not np.isfinite(labels).all() or max(map(abs, labels)) > 1):
            valid, labels = False, None
        return dict(ok=valid, contract=contract, labels=labels, branches=rows)

    def evaluate(self, snapshot, seeds):
        if self.closed:
            raise RuntimeError('Feedback pool is closed')
        rows = list(self.executor.map(_evaluate, [(snapshot, int(seed)) for seed in seeds]))
        for row in rows:
            self._add_cost(row['cost'])
        return [row['outcome'] for row in rows]

    def close(self):
        if not self.closed:
            self.closed = True
            self.executor.shutdown(wait=True, cancel_futures=False)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
