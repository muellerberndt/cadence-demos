"""Boundary and replay tests for the explicitly separate navigation horizon gene."""
import copy
import unittest
from unittest.mock import patch
from . import native_feedback_navigation_long as feedback
from .interface import History, digest
from .test_native_feedback import BUNDLE, CHECKPOINT, FakeActor, FakeEnv


class NavEnv(FakeEnv):
    def step(self, action, *, tics=4):
        result = super().step(action, tics=tics)
        result.update(rewards=[-.0001]*tics, reward=-.0001*tics)
        return result

    def outcome(self):
        return dict(native_exit=False, success=False)


def record():
    history = History()
    with NavEnv('navigation', 10, teacher=False) as env:
        pre = env.observe(); previous = env.step(3)
        history.acknowledge(pre, 3, previous['tics'])
        raw = env.observe(); inputs = history.encode(raw, BUNDLE['normalization'])
        return dict(task='navigation', seed=10, episode_id='test-10', step_index=1,
                    prefix_actions=[3], prefix_outcomes=[previous], raw_sha256=digest(raw.tobytes()),
                    inputs={k:list(v) for k,v in inputs.items()}, executed_action=12,
                    transition=env.step(12), policy_checkpoint_sha256=CHECKPOINT,
                    qualified=True, fallback=False, behavior_source='autonomous')


class NavigationLongTests(unittest.TestCase):
    def setUp(self):
        self.assets = patch.object(feedback, 'reward_assets', return_value=feedback.REWARD_ASSET_SHA256)
        self.assets.start(); self.addCleanup(self.assets.stop)

    def test_only_explicit_horizons_and_task(self):
        for horizon in (144, 600):
            contract = feedback.target_contract('navigation', CHECKPOINT, horizon_tics=horizon)
            self.assertEqual(contract['native_return_bounds'], [-.0001*horizon, 1.])
            self.assertEqual(contract['native_return_divisor'], 1.)
        for horizon in (36, 560, 604, 600.):
            with self.assertRaises(ValueError): feedback.target_contract('navigation', CHECKPOINT, horizon_tics=horizon)
        with self.assertRaises(ValueError): feedback.target_contract('basic', CHECKPOINT)

    def test_600_tics_fresh_qualified_continuation(self):
        contract = feedback.target_contract('navigation', CHECKPOINT, horizon_tics=600)
        branch = feedback.rollout_branch(record(), 12, contract, BUNDLE, env_factory=NavEnv, actor_factory=FakeActor)
        self.assertTrue(branch['ok'], branch)
        self.assertEqual(branch['tics'], 600)
        self.assertEqual(branch['cost']['qualified_continuation_queries'], 149)
        self.assertAlmostEqual(branch['native_return'], -.06)
        self.assertFalse(branch['events']['native_goal_success'])

    def test_custody_and_refused_continuation(self):
        contract = feedback.target_contract('navigation', CHECKPOINT)
        changed = copy.deepcopy(record()); changed['transition']['health_delta'] = -1
        failed = feedback.rollout_branch(changed, 12, contract, BUNDLE, env_factory=NavEnv, actor_factory=FakeActor)
        self.assertFalse(failed['ok']); self.assertIn('executed transition differs', failed['error'])
        class RefusedActor(FakeActor): refuse = True
        failed = feedback.rollout_branch(record(), 12, contract, BUNDLE, env_factory=NavEnv, actor_factory=RefusedActor)
        self.assertFalse(failed['ok']); self.assertIn('Continuation query refused', failed['error'])

    def test_native_goal_is_distinct_from_exit_flag_and_stops_horizon(self):
        class GoalEnv(NavEnv):
            def step(self, action, *, tics=4):
                result = super().step(action, tics=tics)
                if self.tics >= 12:
                    self.finished = True
                    result['rewards'][-1] += 1.; result['reward'] += 1.
                    result['terminal'] = True
                return result
            def facts(self):
                result = super().facts(); result['terminal'] = self.finished; return result
            def outcome(self): return dict(native_exit=False, success=self.finished)
        branch = feedback.rollout_branch(record(), 12, feedback.target_contract('navigation', CHECKPOINT),
                                         BUNDLE, env_factory=GoalEnv, actor_factory=FakeActor)
        self.assertTrue(branch['ok'], branch)
        self.assertEqual(branch['tics'], 8)
        self.assertTrue(branch['events']['native_goal_success'])
        self.assertFalse(branch['events']['native_exit'])


if __name__ == '__main__': unittest.main()
