"""Adversarial target/terminal/history tests; no training or live actor calls."""
from __future__ import annotations
import copy
import unittest
import numpy as np

from feedback import HOLD, CONTINUE, rollout_branch, target_contract, sha
from feedback_experiment import SEEDS, strict_gate


def outcome(rewards, *, terminal=False, timeout=False):
    return dict(reward=sum(rewards), rewards=rewards, tics=len(rewards),
                terminal=terminal, timeout=timeout)


class FakeEpisode:
    timeout = False
    def __init__(self, seed, cost):
        self.done = False
        cost['engine_initializations'] = cost.get('engine_initializations',0)+1
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def raw(self): return None if self.done else np.zeros((2,2),dtype=np.uint8)
    def step(self, action, tics, kind):
        if self.done: raise AssertionError('Action after terminal')
        assert tics == 12
        if self.timeout:
            self.done = True
            return outcome([-1.]*12,terminal=True,timeout=True)
        if action == 3:
            self.done = True
            return outcome([-1.,100.],terminal=True)
        return outcome([-1.]*12)


def record():
    return dict(episode_id='fixture',seed=12,step_index=0,
        prefix_actions=[],prefix_outcomes=[],inputs=[0.]*246,
        raw_sha256=sha(np.zeros((2,2),dtype=np.uint8).tobytes()),
        executed_action=0,transition=outcome([-1.]*12),qualified=True,fallback=False)


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        FakeEpisode.timeout = False
        self.histories = []
    def encode(self,raw,prefix,normalizer):
        self.histories.append(list(prefix))
        return np.zeros(246)
    def query(self,brain,x):
        return np.array([0,0,0,1,0,0]),dict(qualified=True,sweeps=2)
    def branch(self, r, action, contract, query=None):
        return rollout_branch(r,action,contract,{},object(),episode_factory=FakeEpisode,
                              encoder=self.encode,query_fn=query or self.query)
    def test_target_contracts_are_distinct_and_freeze_continuation(self):
        a=target_contract(HOLD,'a'*64);b=target_contract(CONTINUE,'a'*64)
        self.assertNotEqual(a,b)
        self.assertEqual(b['horizon_tics'],36)
        self.assertEqual(b['continuation_checkpoint_sha256'],'a'*64)
        self.assertFalse(b['bootstrap'])
        self.assertIsNone(a['continuation_checkpoint_sha256'])
    def test_hold36_does_not_query_continuation(self):
        def forbidden(*args): raise AssertionError('hold control queried brain')
        r=self.branch(record(),1,HOLD,forbidden)
        self.assertTrue(r['ok']);self.assertEqual(r['label'],-36/300)
        self.assertEqual(r['actions'],[1,1,1]);self.assertEqual(r['queries'],[])
    def test_continuation_observes_executed_intervention_history(self):
        r=self.branch(record(),1,CONTINUE)
        self.assertTrue(r['ok']);self.assertEqual(r['actions'],[1,3])
        self.assertEqual(r['label'],87/300);self.assertEqual(r['tics'],14)
        self.assertEqual(self.histories,[[],[1]])
    def test_terminal_first_intervention_never_queries_or_bootstraps(self):
        def forbidden(*args):raise AssertionError('query after terminal')
        r=self.branch(record(),3,CONTINUE,forbidden)
        self.assertTrue(r['ok']);self.assertEqual(r['actions'],[3])
        self.assertEqual(r['label'],99/300)
    def test_true_task_timeout_stops_at_native_rewards(self):
        FakeEpisode.timeout=True
        r=record();r['transition']=outcome([-1.]*12,terminal=True,timeout=True)
        x=self.branch(r,0,CONTINUE)
        self.assertTrue(x['ok']);self.assertEqual(x['label'],-12/300)
        self.assertEqual(len(x['transitions']),1)
    def test_collector_cutoff_metadata_does_not_fabricate_terminal(self):
        r=record();r['collector_truncated']=True
        x=self.branch(r,1,HOLD)
        self.assertTrue(x['ok']);self.assertEqual(x['tics'],36)
    def test_qualification_refusal_has_no_partial_label(self):
        def refused(*args):return np.zeros(6),dict(qualified=False,sweeps=512)
        r=self.branch(record(),1,CONTINUE,refused)
        self.assertFalse(r['ok']);self.assertNotIn('label',r)
        self.assertIn('no fallback',r['error'])
    def test_executed_outcome_mismatch_refuses_label(self):
        r=record();r['transition']=outcome([-2.]*12)
        x=self.branch(r,0,HOLD)
        self.assertFalse(x['ok']);self.assertIn('transition does not match',x['error'])
    def test_prefix_and_frame_mismatch_refuse_label(self):
        r=record();r.update(step_index=1,prefix_actions=[1],prefix_outcomes=[outcome([-2.]*12)])
        self.assertFalse(self.branch(r,0,HOLD)['ok'])
        r=record();r['raw_sha256']='a'*64
        self.assertFalse(self.branch(r,0,HOLD)['ok'])
    def test_history_is_new_for_each_episode(self):
        a=record();a.update(step_index=1,prefix_actions=[2],prefix_outcomes=[outcome([-1.]*12)])
        self.branch(a,1,CONTINUE);self.branch(record(),1,CONTINUE)
        self.assertEqual(self.histories,[[2],[2,1],[],[1]])
    def test_gate_protects_old_mean_and_wins_while_allowing_new_improvement(self):
        anchor=[dict(seed=s,status='complete',killed=True,return_=50.,queries=1,
                     qualified_queries=1,fallback_actions=0,tics=20,timeout=False) for s in SEEDS]
        candidate=copy.deepcopy(anchor);candidate[-1]['return_']+=16
        self.assertTrue(strict_gate(anchor,anchor,candidate)['passed'])
        candidate[0]['return_']-=1
        self.assertFalse(strict_gate(anchor,anchor,candidate)['passed'])
        candidate=copy.deepcopy(anchor);candidate[-1]['return_']+=16;candidate[0]['killed']=False
        self.assertFalse(strict_gate(anchor,anchor,candidate)['passed'])
    def test_gate_refuses_missing_or_unqualified_episode(self):
        anchor=[dict(seed=s,status='complete',killed=True,return_=50.,queries=1,
                     qualified_queries=1,fallback_actions=0,tics=20,timeout=False) for s in SEEDS]
        self.assertFalse(strict_gate(anchor,anchor,anchor[:-1])['passed'])
        candidate=copy.deepcopy(anchor);candidate[-1]['qualified_queries']=0
        self.assertFalse(strict_gate(anchor,anchor,candidate)['passed'])


if __name__=='__main__':unittest.main()
