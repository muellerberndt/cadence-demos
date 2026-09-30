"""Range, custody and control equivalence tests for the separate v2 contract."""
import copy
import unittest
from unittest.mock import patch

from . import native_feedback as old
from . import native_feedback_long as new
from .interface import History, digest
from .test_native_feedback import BUNDLE, CHECKPOINT, FakeActor, FakeEnv, record


def make_record(env_type):
    history = History()
    with env_type('basic', 10, teacher=False) as env:
        pre = env.observe(); previous = env.step(3)
        history.acknowledge(pre, 3, previous['tics'])
        raw = env.observe(); inputs = history.encode(raw, BUNDLE['normalization'])
        return dict(task='basic', seed=10, episode_id='test-10', step_index=1,
                    prefix_actions=[3], prefix_outcomes=[previous], raw_sha256=digest(raw.tobytes()),
                    inputs={k:list(v) for k,v in inputs.items()}, executed_action=12,
                    transition=env.step(12), policy_checkpoint_sha256=CHECKPOINT,
                    qualified=True, fallback=False, behavior_source='autonomous')


class LongFeedbackTests(unittest.TestCase):
    def test_explicit_source_bound_and_horizons(self):
        for horizon, divisor in ((36,216.), (144,864.), (300,1800.)):
            contract = new.target_contract('basic', CHECKPOINT, horizon_tics=horizon)
            self.assertEqual(contract['native_return_divisor'], divisor)
            self.assertEqual(contract['native_return_bounds'], [-6.*horizon,106.])
        with self.assertRaises(ValueError):new.target_contract('navigation', CHECKPOINT)
        with self.assertRaises(ValueError):new.target_contract('basic', CHECKPOINT, horizon_tics=148)
        with patch.object(new, 'sha_file', return_value='0'*64):
            with self.assertRaisesRegex(ValueError,'assets differ'):new.target_contract('basic', CHECKPOINT)

    def test_36_control_same_native_rewards_and_action_ranking(self):
        row=record(); before=[]; after=[]
        for action in range(20):
            a=old.rollout_branch(row, action, old.target_contract('basic',CHECKPOINT), BUNDLE,
                                 env_factory=FakeEnv,actor_factory=FakeActor)
            b=new.rollout_branch(row, action, new.target_contract('basic',CHECKPOINT,horizon_tics=36), BUNDLE,
                                 env_factory=FakeEnv,actor_factory=FakeActor)
            self.assertTrue(a['ok'] and b['ok'],(a,b))
            self.assertEqual(a['native_return'], b['native_return'])
            self.assertEqual(a['transitions'], b['transitions'])
            before.append(a['label']);after.append(b['label'])
        for i in range(20):
            for j in range(20):self.assertEqual(before[i]>before[j],after[i]>after[j])

    def test_long_negative_value_is_admitted_with_explicit_bound(self):
        class PenaltyEnv(FakeEnv):
            def step(self,action,*,tics=4):
                r=super().step(action,tics=tics)
                r.update(rewards=[-1.5]*tics,reward=-1.5*tics)
                return r
        row=make_record(PenaltyEnv)
        a=old.rollout_branch(row,12,old.target_contract('basic',CHECKPOINT,horizon_tics=300),BUNDLE,
                             env_factory=PenaltyEnv,actor_factory=FakeActor)
        b=new.rollout_branch(row,12,new.target_contract('basic',CHECKPOINT,horizon_tics=300),BUNDLE,
                             env_factory=PenaltyEnv,actor_factory=FakeActor)
        self.assertFalse(a['ok']);self.assertTrue(b['ok'],b)
        self.assertEqual(b['native_return'],-450.);self.assertEqual(b['label'],-.25)

    def test_changed_scale_or_replayed_actual_transition_is_refused(self):
        row=record(); contract=new.target_contract('basic',CHECKPOINT)
        changed=copy.deepcopy(contract);changed['native_return_divisor']=9000
        failed=new.rollout_branch(row,12,changed,BUNDLE,env_factory=FakeEnv,actor_factory=FakeActor)
        self.assertFalse(failed['ok'])
        row['transition']['health_delta']=-10
        failed=new.rollout_branch(row,12,contract,BUNDLE,env_factory=FakeEnv,actor_factory=FakeActor)
        self.assertFalse(failed['ok']);self.assertIn('executed transition differs',failed['error'])


if __name__=='__main__':unittest.main()
