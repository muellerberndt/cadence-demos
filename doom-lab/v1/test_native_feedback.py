"""Adverse replay/qualification tests; native engine equivalence has own receipt."""
import copy
import unittest

import numpy as np

from .interface import ACTION_BUTTONS, History, digest, fixed_normalizer
from .native_feedback import aggregate, rollout_branch, target_contract, validate_record


CHECKPOINT = "a" * 64
BUNDLE = {"normalization": fixed_normalizer()}


class FakeEnv:
    opened = 0

    def __init__(self, task, seed, *, teacher):
        assert teacher is False
        self.seed, self.tics, self.position, self.finished = seed, 0, 0, False
        type(self).opened += 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def observe(self):
        return np.full((240, 320), (self.position + self.seed) % 256, np.uint8)

    def step(self, action, *, tics=4):
        self.position += action
        self.tics += tics
        rewards = [float(action == 12)] * tics
        return {"action": action, "buttons": list(ACTION_BUTTONS[action]),
                "requested_tics": tics, "tics": tics, "rewards": rewards,
                "reward": sum(rewards), "terminal": False, "dead": False,
                "timeout": False, "native_kill_delta": 0., "health_delta": 0.,
                "episode_tic": self.tics}

    def facts(self):
        return dict(killcount=0., health=100., damage_taken=0., itemcount=0.,
                    terminal=False, dead=False, timeout=False)

    def outcome(self):
        return dict(native_exit=False)


class FakeActor:
    refuse = False

    def __init__(self, bundle, *, device):
        self.bundle, self.checkpoint_hash = bundle, CHECKPOINT
        self.history = History()
        self.pending = False

    def reset(self):
        self.history.reset()
        self.pending = False

    def choose(self, raw):
        assert not self.pending
        self.pending = not self.refuse
        return dict(action=12, qualified=not self.refuse, query_seconds=0.)

    def acknowledge(self, raw, action, tics):
        assert self.pending
        self.history.acknowledge(raw, action, tics)
        self.pending = False


def record():
    history = History()
    with FakeEnv('basic', 10, teacher=False) as env:
        pre = env.observe()
        previous = env.step(3)
        history.acknowledge(pre, 3, previous['tics'])
        raw = env.observe()
        inputs = history.encode(raw, BUNDLE['normalization'])
        return dict(task='basic', seed=10, episode_id='test-10', step_index=1,
                    prefix_actions=[3], prefix_outcomes=[previous], raw_sha256=digest(raw.tobytes()),
                    inputs={k: list(v) for k, v in inputs.items()}, executed_action=12,
                    transition=env.step(12), policy_checkpoint_sha256=CHECKPOINT,
                    qualified=True, fallback=False, behavior_source='autonomous')


class NativeFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.row = record()
        self.contract = target_contract('basic', CHECKPOINT, horizon_tics=12)

    def branch(self, row=None, action=12, actor_factory=FakeActor):
        return rollout_branch(row or self.row, action, self.contract, BUNDLE,
                              env_factory=FakeEnv, actor_factory=actor_factory)

    def test_fresh_engine_and_frozen_continuation(self):
        before = FakeEnv.opened
        branches = [self.branch(action=i) for i in range(20)]
        result = aggregate(branches, self.contract)
        self.assertTrue(result['ok'], branches)
        self.assertEqual(FakeEnv.opened-before, 20)
        self.assertEqual(result['cost']['replay_tics'], 80)
        self.assertEqual(result['cost']['branch_tics'], 240)
        self.assertEqual(result['cost']['qualified_continuation_queries'], 40)
        self.assertEqual(branches[12]['native_return'], 12.)
        self.assertEqual(branches[0]['actions'], [0, 12, 12])

    def test_selected_actual_outcome_is_bound(self):
        row = copy.deepcopy(self.row)
        row['transition']['health_delta'] = -10.
        result = self.branch(row)
        self.assertFalse(result['ok'])
        self.assertIn('executed transition differs', result['error'])

    def test_prefix_native_outcome_is_bound(self):
        row = copy.deepcopy(self.row)
        row['prefix_outcomes'][0]['episode_tic'] += 1
        self.assertIn('prefix does not reproduce', self.branch(row)['error'])

    def test_pixels_and_history_both_bound(self):
        row = copy.deepcopy(self.row)
        row['raw_sha256'] = '0' * 64
        self.assertIn('pixel digest differs', self.branch(row)['error'])
        row = copy.deepcopy(self.row)
        row['inputs']['executed_action_history'][0] += .1
        self.assertIn('ports differ', self.branch(row)['error'])

    def test_continuation_refusal_rejects_whole_context(self):
        class RefusedActor(FakeActor):
            refuse = True
        branches = [self.branch(action=i) for i in range(20)]
        branches[6] = self.branch(action=6, actor_factory=RefusedActor)
        result = aggregate(branches, self.contract)
        self.assertFalse(result['ok'])
        self.assertIsNone(result['labels'])
        self.assertIn('Continuation query refused', branches[6]['error'])

    def test_non_autonomous_or_fallback_context_refused(self):
        for key, value in [('behavior_source', 'teacher'), ('fallback', True), ('qualified', False)]:
            row = copy.deepcopy(self.row)
            row[key] = value
            with self.assertRaises(ValueError):
                validate_record(row)

    def test_target_contract_and_checkpoint_bound(self):
        contract = copy.deepcopy(self.contract)
        contract['native_return_divisor'] = 1000.
        result = rollout_branch(self.row, 12, contract, BUNDLE,
                                env_factory=FakeEnv, actor_factory=FakeActor)
        self.assertFalse(result['ok'])
        self.assertIn('target contract does not match', result['error'])

    def test_reset_cached_actor_removes_previous_branch_memory(self):
        cached = FakeActor(BUNDLE, device='cpu')
        fresh = [self.branch(action=i) for i in range(20)]
        reused = [self.branch(action=i, actor_factory=lambda _bundle, device: cached) for i in range(20)]
        for a, b in zip(fresh, reused):
            a.pop('wall_seconds'); b.pop('wall_seconds')
            self.assertEqual(a, b)

    def test_native_terminal_time_reset_and_short_action_are_replayed(self):
        class TerminalEnv(FakeEnv):
            def step(self, action, *, tics=4):
                result = super().step(action, tics=2 if action == 12 else tics)
                if action == 12:
                    self.finished = True
                    result.update(requested_tics=tics, terminal=True, episode_tic=0,
                                  native_kill_delta=1.)
                return result

            def facts(self):
                result = super().facts()
                result.update(terminal=self.finished, killcount=float(self.finished))
                return result

        row = copy.deepcopy(self.row)
        with TerminalEnv('basic', row['seed'], teacher=False) as env:
            env.step(3)
            row['transition'] = env.step(12)
        result = rollout_branch(row, 12, self.contract, BUNDLE,
                                env_factory=TerminalEnv, actor_factory=FakeActor)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['tics'], 2)
        self.assertEqual(result['events']['kill_delta'], 1.)
        self.assertEqual(result['continuation_queries'], [])
        self.assertEqual(result['transitions'][0]['episode_tic'], 0)


if __name__ == '__main__':
    unittest.main()
