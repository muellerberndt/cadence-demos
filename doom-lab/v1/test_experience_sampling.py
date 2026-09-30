"""Counter/custody faults and unchanged full-prefix actor integration."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from . import experience_sampling as sampling
from .test_practice import record


class SamplingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'collection.json'

    def sampler(self, stride=32, wave='a'*64):
        return sampling.ExperienceSampler(self.path, wave, sampling.contract(stride))

    def test_selected_global_indices_keep_complete_prefix_across_episodes_and_restart(self):
        sampler = self.sampler(); selected = []
        for index in range(70):
            if index == 19: sampler = self.sampler()  # restart does not restart cadence
            row = record('episode'+str(index//17), index%17)
            if sampler.observe(row, learning_enabled=True):
                selected.append((index, sampler.pending))
                sampler.acknowledge(row)
        self.assertEqual([i for i, _ in selected], [0,32,64])
        self.assertEqual([len(r['prefix_actions']) for _,r in selected], [0,15,13])
        self.assertEqual(sampler.status()['executed_decisions'],70)
        self.assertEqual(sampler.status()['intentionally_unsampled_transitions'],67)
        self.assertEqual(self.sampler().status(), sampler.status())

    def test_stride1_control_keeps_every_enabled_record_and_counts_paused_execution(self):
        sampler = self.sampler(1)
        for i in range(6):
            enabled = i%2 == 0; row = record(step=i)
            self.assertEqual(sampler.observe(row, learning_enabled=enabled), enabled)
            if enabled:sampler.acknowledge(row)
        self.assertEqual(sampler.status()['selected_transitions'],3)
        self.assertEqual(sampler.status()['learning_disabled_decisions'],3)
        self.assertEqual(sampler.status()['intentionally_unsampled_transitions'],0)

    def test_stride64_preserves_phase_after_disabled_decisions_and_restart(self):
        sampler=self.sampler(64);selected=[]
        for i in range(130):
            if i==47:sampler=self.sampler(64)
            row=record('episode'+str(i//21),i%21)
            if sampler.observe(row,learning_enabled=not 20<=i<30):
                selected.append(i);sampler.acknowledge(row)
        self.assertEqual(selected,[0,64,128])
        self.assertEqual(sampler.status()['executed_decisions'],130)
        self.assertEqual(sampler.status()['intentionally_unsampled_transitions'],117)
        self.assertEqual(sampler.status()['learning_disabled_decisions'],10)

    def test_selected_pending_is_atomic_with_counter_and_retried_without_reselection(self):
        sampler = self.sampler(); row = record()
        sampler.observe(row, learning_enabled=True)
        sampler = self.sampler()
        self.assertEqual(sampler.pending, row)
        self.assertEqual(sampler.status()['executed_decisions'],1)
        sampler.observe(row, learning_enabled=True)
        self.assertEqual(sampler.status()['executed_decisions'],1)
        changed = copy.deepcopy(row); changed['raw_sha256'] = 'c'*64
        with self.assertRaisesRegex(ValueError, 'changed'): sampler.observe(changed, learning_enabled=True)
        for i in range(1,32):sampler.observe(record(step=i), learning_enabled=True)
        before=self.path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'overwritten'):sampler.observe(record(step=32), learning_enabled=True)
        self.assertEqual(self.path.read_bytes(), before)
        sampler.acknowledge(row)
        self.assertTrue(sampler.observe(record(step=32), learning_enabled=True))

    def test_failed_write_keeps_previous_counter_and_selected_evidence(self):
        sampler=self.sampler(); row=record(); sampler.observe(row,learning_enabled=True)
        before=self.path.read_bytes()
        with patch('v1.practice.atomic_json',side_effect=OSError('disk fixture')):
            with self.assertRaises(OSError):sampler.acknowledge(row)
        self.assertEqual(sampler.pending,row)
        self.assertEqual(self.path.read_bytes(),before)
        sampler.acknowledge(row)
        before=self.path.read_bytes()
        with patch('v1.practice.atomic_json',side_effect=OSError('disk fixture')):
            with self.assertRaises(OSError):sampler.observe(record(step=1),learning_enabled=True)
        self.assertEqual(sampler.status()['executed_decisions'],1)
        self.assertEqual(self.path.read_bytes(),before)

    def test_wave_stride_and_counter_tampering_refused(self):
        sampler=self.sampler();sampler.observe(record(),learning_enabled=True)
        with self.assertRaisesRegex(ValueError,'different wave'):self.sampler(wave='b'*64)
        with self.assertRaisesRegex(ValueError,'different wave'):self.sampler(1)
        value=json.loads(self.path.read_text());value['executed_decisions']=0
        self.path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'counter identities'):self.sampler()
        for stride in (0,2,False,32.,None):
            with self.assertRaises(ValueError):sampling.contract(stride)


class SampledRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from .test_practice_protocol import PackageTests
        PackageTests.setUpClass()
        cls.founder,cls.active,cls.config,cls.platform=(getattr(PackageTests,k) for k in ('founder','active','config','platform'))

    def adapter(self,directory,stride=32):
        from .test_practice_protocol import PackageTests
        from .practice_protocol import make_package
        packed=make_package(self.active,self.founder,self.active,config=self.config,
                            wave_name='sampling_test',collection_stride=stride)
        return PackageTests.runtime_adapter(self,directory,packed)

    def test_runtime_recovery_preserves_selected_pending_and_full_prefix(self):
        from .runtime import Adapter
        with tempfile.TemporaryDirectory() as directory:
            adapter=self.adapter(directory);learner=Mock();learner.status.return_value={'enabled':True}
            learner.submit_transition.return_value=True
            adapter.learner=learner;adapter.enabled=True
            for i in range(33):adapter.collect_transition(record(step=i),learning_enabled=True)
            calls=learner.submit_transition.call_args_list
            self.assertEqual([c.args[0]['step_index'] for c in calls],[0,32])
            self.assertEqual(len(calls[-1].args[0]['prefix_outcomes']),32)
            learner.submit_transition.return_value=False
            for i in range(33,65):adapter.collect_transition(record(step=i),learning_enabled=True)
            expected=record(step=64);self.assertEqual(adapter.pending,expected)
            restored=Adapter(adapter.path)
            self.assertEqual(restored.pending,expected)
            self.assertEqual(restored.status()['executed_decisions'],65)
            restored.learner=learner;restored.enabled=True
            learner.submit_transition.return_value=True
            self.assertTrue(restored.flush_pending())
            self.assertIsNone(restored.pending)
            self.assertEqual(restored.status()['executed_decisions'],65)
            # Old-wave custody is neither read nor overwritten by a new stride.
            (adapter.practice_path/'old_queue_receipt').write_text('untouched')
            other=self.adapter(Path(directory)/'new',stride=1)
            self.assertEqual(other.status()['executed_decisions'],0)
            self.assertEqual((adapter.practice_path/'old_queue_receipt').read_text(),'untouched')

    def test_package_binds_collection_rule_and_rejects_relabelled_pending(self):
        from . import practice_protocol as protocol
        from .interface import canonical,digest
        from .runtime import Adapter
        with tempfile.TemporaryDirectory() as directory:
            adapter=self.adapter(directory)
            self.assertEqual(adapter.status()['collection_stride'],32)
            broken=copy.deepcopy(adapter.bundle);package=broken['metadata']['practice_package']
            package['descriptor']['experience_collection']['selection']='select on episode reset'
            package['wave_sha256']=digest(canonical(package['descriptor']))
            broken=protocol.attach_package(broken,package)
            with self.assertRaisesRegex(ValueError,'collection contract'):protocol.unpack_package(broken)
            (adapter.practice_path/'pending_transition.json').write_text(json.dumps(record()))
            with self.assertRaisesRegex(ValueError,'Historical pending'):Adapter(adapter.path)


if __name__=='__main__':unittest.main()
