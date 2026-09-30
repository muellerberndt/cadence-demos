"""Explicit protocol actor-custody tests; fake repairs are not gameplay evidence."""
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from . import practice as p
from .test_practice import bundle,load,make,record,result,seed_row,Teacher


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'practice.jsonl'
        self.learners=[]
        self.patchers=[patch.object(p,'load_bundle',load),patch.object(p,'make_bundle',make),
                      patch.object(p,'write_bundle',lambda path,data:p.atomic_json(path,data)),
                      patch.object(p,'task_identity',lambda task:{'task':task}),
                      patch('v1.practice_protocol.resolve_protocol',return_value=SimpleNamespace(
                          target_contract=p.native_contract,NativeFeedbackPool=Teacher))]
        for item in self.patchers:item.start()
        self.config=p.PracticeConfig(new_rows=1,candidate_lifetime=1,gate_tasks=('basic',),gate_seeds=(1220000000,))
        self.protocol={'native_contract':p.native_contract('basic',bundle()['hashes']['checkpoint_sha256'],horizon_tics=36)}
    def tearDown(self):
        for learner in self.learners:learner.close(wait=True)
        for item in reversed(self.patchers):item.stop()
        self.temp.cleanup()
    def learner(self,initial=None):
        value=p.PracticeLearner.from_bundle(bundle(),journal_path=self.path,config=self.config,
            initial_bundle=initial or bundle(),seed_replay=[seed_row()],teacher=Teacher(),
            evaluator=lambda b:[result(float(json.loads(b['snapshot'])['generation']))],
            native_protocol=self.protocol,practice_wave_sha256='d'*64)
        self.learners.append(value);return value
    def wait(self,predicate):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if predicate():return
            for learner in self.learners:
                if learner.status()['error']:self.fail(learner.status()['error'])
            time.sleep(.01)
        self.fail('worker did not complete control operation')
    def update(self,learner,name,count):
        learner.set_enabled(True);self.assertTrue(learner.submit_transition(record(name)))
        self.wait(lambda:learner.status()['processed_transitions']>=count and not learner.status()['busy'])
    def ack(self,learner,proposal):
        checkpoint=proposal['bundle']['hashes']['checkpoint_sha256']
        self.assertTrue(learner.acknowledge_deployment(checkpoint))
        self.wait(lambda:learner._deployed['hashes']['checkpoint_sha256']==checkpoint and not learner._deployment_acks)
    def test_new_gate_does_not_replace_offered_actor(self):
        learner=self.learner();self.update(learner,'a',1);first=learner.take_promotion()
        self.update(learner,'b',2);self.assertIsNone(learner.take_promotion())
        self.assertEqual(learner._offered['proposal']['snapshot'],first['snapshot'])
        self.assertNotEqual(learner._ready['proposal']['snapshot'],first['snapshot'])
        self.ack(learner,first)
        second=learner.take_promotion();self.assertIsNotNone(second)
        self.assertEqual(learner._offered['source_checkpoint'],first['bundle']['hashes']['checkpoint_sha256'])
    def test_restart_reoffers_exact_unacknowledged_target(self):
        learner=self.learner();self.update(learner,'a',1);first=learner.take_promotion();learner.close(wait=True)
        restored=self.learner();proposal=restored.take_promotion()
        self.assertEqual(proposal['snapshot'],first['snapshot']);self.assertEqual(proposal['gate'],first['gate'])
        self.assertEqual(proposal['version'],1)
    def test_publication_before_ack_is_recognized_on_restart(self):
        learner=self.learner();self.update(learner,'a',1);first=learner.take_promotion()
        self.update(learner,'b',2);learner.close(wait=True)
        restored=self.learner(initial=first['bundle']);second=restored.take_promotion()
        self.assertEqual(restored._deployed['snapshot'],first['snapshot'])
        self.assertNotEqual(second['snapshot'],first['snapshot']);self.assertEqual(second['version'],1)
        self.assertEqual(restored._offered['source_checkpoint'],first['bundle']['hashes']['checkpoint_sha256'])
    def test_unrelated_actor_and_false_ack_are_refused(self):
        learner=self.learner();self.update(learner,'a',1)
        with self.assertRaisesRegex(ValueError,'offered checkpoint'):learner.acknowledge_deployment('e'*64)
        learner.close(wait=True)
        with self.assertRaisesRegex(ValueError,'neither'):self.learner(initial=bundle(999))
        restored=self.learner()  # Refused construction released its process lock.
        self.assertIsNotNone(restored.take_promotion())
    def test_portable_companion_package_is_not_duplicated_in_state(self):
        imported=bundle();imported['metadata']['practice_package']={'large_companions':'x'*10000}
        imported['hashes']['practice_package_sha256']='c'*64
        learner=self.learner(initial=imported)
        self.assertNotIn('practice_package',learner.champion['metadata'])
        self.assertNotIn('practice_package_sha256',learner._deployed['hashes'])
        self.assertEqual(learner.champion['snapshot'],imported['snapshot'])
    def test_rollback_crash_reoffers_rollback_not_normal_promotion(self):
        learner=self.learner();self.update(learner,'a',1);first=learner.take_promotion();self.ack(learner,first)
        learner.set_enabled(False);self.assertTrue(learner.rollback(bundle()))
        self.wait(lambda:learner._offered is not None and learner._offer_durable)
        rollback=learner.take_promotion();self.assertTrue(rollback['gate']['rollback'])
        learner.close(wait=True)
        restored=self.learner(initial=first['bundle']);again=restored.take_promotion()
        self.assertEqual(again['gate'],{'rollback':True});self.assertEqual(again['snapshot'],bundle()['snapshot'])
    def test_rollback_publication_before_ack_recovers_previous_deployment(self):
        learner=self.learner();self.update(learner,'a',1);first=learner.take_promotion();self.ack(learner,first)
        learner.set_enabled(False);self.assertTrue(learner.rollback(bundle()))
        self.wait(lambda:learner._offered is not None and learner._offer_durable)
        learner.take_promotion();learner.close(wait=True)
        restored=self.learner(initial=bundle())
        self.assertIsNone(restored.take_promotion())
        self.assertEqual(restored._deployed['snapshot'],bundle()['snapshot'])
        self.assertEqual(restored._deployed_previous['snapshot'],first['snapshot'])
    def test_internal_unpublished_previous_cannot_be_rolled_back(self):
        learner=self.learner();self.update(learner,'a',1);first=learner.take_promotion()
        self.update(learner,'b',2)
        self.assertFalse(learner.rollback(first['bundle']))

if __name__=='__main__':unittest.main()
