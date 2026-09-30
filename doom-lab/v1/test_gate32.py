"""Prospective32-case selection configuration; mocked outcomes are not evidence."""
import copy
from concurrent.futures import Future
import tempfile
import unittest
from unittest.mock import patch
from . import practice as p

SEEDS=tuple(range(1220200000,1220200032))


def rows(value=1.):
    return [dict(task_id='basic',seed=seed,status='complete',success=True,
                 queries=2,qualified_queries=2,fallback_actions=0,return_=value,
                 **{'return':value}) for seed in SEEDS]


class Gate32Tests(unittest.TestCase):
    def setUp(self):self.config=p.PracticeConfig(gate_tasks=('basic',),gate_seeds=SEEDS,gate_workers=4)

    def test_all32_scheduled_once_and_returned_in_order(self):
        calls=[]
        class Pool:
            def submit(self,function,payload):
                calls.append(payload);future=Future()
                future.set_result(dict(task_id=payload[1],seed=payload[2],status='complete',
                    success=True,queries=1,qualified_queries=1,fallback_actions=0,
                    decision_trace=[],**{'return':1.}))
                return future
            def shutdown(self,**_):pass
        with tempfile.TemporaryDirectory() as directory,patch.object(p,'ProcessPoolExecutor',return_value=Pool()) as factory:
            evaluator=p.DevelopmentEvaluator(self.config,directory)
            result=evaluator({'hashes':{'checkpoint_sha256':'a'*64}});evaluator.close()
        self.assertEqual(factory.call_args.kwargs['max_workers'],4)
        self.assertEqual([payload[2] for payload in calls],list(SEEDS))
        self.assertEqual([row['seed'] for row in result],list(SEEDS))

    def test_no_omission_duplicate_or_unqualified_result_can_pass(self):
        baseline=rows();candidate=rows(2.)
        self.assertTrue(p.promotion_gate(candidate,baseline,baseline,self.config)['promote'])
        for owner in range(3):
            for omitted in range(32):
                sets=[copy.deepcopy(candidate),copy.deepcopy(baseline),copy.deepcopy(baseline)]
                sets[owner].pop(omitted)
                self.assertFalse(p.promotion_gate(*sets,self.config)['promote'])
            sets=[copy.deepcopy(candidate),copy.deepcopy(baseline),copy.deepcopy(baseline)]
            sets[owner][-1]=copy.deepcopy(sets[owner][0])
            self.assertFalse(p.promotion_gate(*sets,self.config)['promote'])
        candidate[-1]['qualified_queries']=1
        self.assertFalse(p.promotion_gate(candidate,baseline,baseline,self.config)['promote'])

    def test_every_baseline_win_and_mean_retained_with_strict_gain(self):
        baseline=rows()
        for lost in range(32):
            candidate=rows(100.);candidate[lost]['success']=False
            self.assertFalse(p.promotion_gate(candidate,baseline,baseline,self.config)['promote'])
        self.assertFalse(p.promotion_gate(rows(),baseline,baseline,self.config)['promote'])
        self.assertFalse(p.promotion_gate(rows(0.),baseline,rows(-1.),self.config)['promote'])
        self.assertFalse(p.promotion_gate(rows(2.),baseline,rows(3.),self.config)['promote'])


if __name__=='__main__':unittest.main()
