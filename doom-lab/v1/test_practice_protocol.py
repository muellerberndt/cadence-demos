"""Custody/dispatch tests; synthetic checkpoints are not gameplay evidence."""
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from . import brain, practice as p, practice_protocol as protocol, runtime
from .interface import canonical, digest, fixed_normalizer
from . import test_practice as fixtures
from .test_practice import Teacher, bundle as fake_bundle, record, seed_row
from .training import target_contract


def changed(bundle, amount=.01):
    value = copy.deepcopy(bundle)
    snapshot = json.loads(value['snapshot'])
    snapshot['state'][0] += amount
    value['snapshot'] = canonical(snapshot)
    value['hashes']['checkpoint_sha256'] = digest(value['snapshot'])
    return value


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gene = brain.genome_spec()
        cls.founder = p.attach_seed_replay(brain.make_bundle(brain.build(device='python'),
            fixed_normalizer(), model_id='protocol-unit-founder', genome=gene,
            target_contract=target_contract('centered')), [seed_row()])
        cls.active = changed(cls.founder)
        cls.config = p.PracticeConfig(gate_tasks=('basic',), feedback_horizon_tics=144)
        cls.platform = {'system': 'test', 'machine': 'test', 'engine_binary_sha256': '0'*64}

    def package(self, horizon=144, wave_name='unit_wave'):
        return protocol.make_package(self.active, self.founder, self.active,
            config=replace(self.config, feedback_horizon_tics=horizon), wave_name=wave_name)

    def test_dispatch_binds_original36_and_reviewed_long_units(self):
        from . import native_feedback as short, native_feedback_long as long
        for horizon, module, divisor in ((36, short, 300.), (144, long, 864.), (300, long, 1800.)):
            with self.subTest(horizon=horizon):
                packed = self.package(horizon)
                resolved = protocol.unpack_package(packed)
                actual = resolved['protocol']['native_contract']
                self.assertEqual(actual['native_return_divisor'], divisor)
                self.assertIs(protocol.resolve_protocol(resolved['protocol'], self.active, resolved['config']), module)
                self.assertEqual(actual, module.target_contract('basic', self.active['hashes']['checkpoint_sha256'], horizon_tics=horizon))
                self.assertEqual(packed['snapshot'], self.active['snapshot'])
                self.assertEqual(packed['target_contract'], self.active['target_contract'])
                self.assertEqual(resolved['founder'], self.founder)
                self.assertEqual(resolved['continuation'], self.active)
                self.assertIn('brain.py', resolved['protocol']['source_sha256'])
                self.assertIn('engine_binary_sha256', resolved['protocol']['engine_platform'])

    def test_unknown_relabelled_and_changed_native_sources_refused(self):
        for value in (35, 560, True, '144'):
            with self.assertRaises(ValueError): self.package(value)
        original = self.package()
        broken = copy.deepcopy(original)
        broken['metadata']['practice_package']['descriptor']['protocol']['native_contract']['horizon_tics'] = 300
        with self.assertRaisesRegex(ValueError, 'digest'): protocol.unpack_package(broken)
        # Recomputing superficial hashes must still fail factory equivalence.
        package = broken['metadata']['practice_package']
        package['wave_sha256'] = digest(canonical(package['descriptor']))
        broken = protocol.attach_package(self.active, package)
        with self.assertRaisesRegex(ValueError, 'factory'): protocol.unpack_package(broken)
        resolved = protocol.unpack_package(original)
        altered = copy.deepcopy(resolved['protocol'])
        altered['source_sha256']['brain.py'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'sources'):
            protocol.resolve_protocol(altered, self.active, resolved['config'])

    def test_training_native_provenance_cannot_be_silently_retagged(self):
        from .native_feedback_long import target_contract as native_contract
        from .practice import preference_contract
        winner = copy.deepcopy(self.active)
        native = native_contract('basic', self.founder['hashes']['checkpoint_sha256'], horizon_tics=144)
        target = preference_contract(self.founder)
        target.update(native_contract_sha256=digest(canonical(native)), native_horizon_tics=144,
                      retention_founder_checkpoint_sha256=self.founder['hashes']['checkpoint_sha256'])
        winner['target_contract'] = target
        winner['hashes']['target_contract_sha256'] = digest(canonical(target))
        winner['metadata']['native_contract'] = native
        packed = protocol.make_package(winner, self.founder, winner, config=self.config, wave_name='winner')
        self.assertEqual(packed['target_contract'], target)
        self.assertNotEqual(protocol.unpack_package(packed)['protocol']['native_contract'], native)
        # Old training used founder continuation; new practice explicitly freezes winner.
        winner['metadata']['native_contract']['horizon_tics'] = 300
        with self.assertRaisesRegex(ValueError, 'digest differs'):
            protocol.make_package(winner, self.founder, winner, config=self.config, wave_name='bad')

    def test_wave_directory_never_moves_or_relabels_pending_rows(self):
        a, b = protocol.unpack_package(self.package(144)), protocol.unpack_package(self.package(300))
        with tempfile.TemporaryDirectory() as directory:
            first = protocol.prepare_wave_directory(directory, a)
            pending = first/'pending_transition.json'; pending.write_text('original144bytes')
            second = protocol.prepare_wave_directory(directory, b)
            self.assertNotEqual(first, second)
            self.assertEqual(pending.read_text(), 'original144bytes')
            self.assertFalse((second/'pending_transition.json').exists())
            (first/'wave.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'custody'):
                protocol.prepare_wave_directory(directory, a)

    def runtime_adapter(self, directory, packed):
        self.enterContext(patch.dict(os.environ, {'DOOM_LAB_ENABLE_V3': '1', 'DOOM_LAB_PORT': '8667',
                                                'DOOM_LAB_PRACTICE': '1'}))
        self.enterContext(patch.object(runtime, 'platform_identity', return_value=self.platform))
        self.enterContext(patch.object(runtime, 'task_identity', side_effect=lambda task: {'task': vars(runtime.get_task(task))}))
        staged = runtime.prepare_staging_bundle(packed, 'basic', source_platform=self.platform)
        path = Path(directory)/'bundle.json'; brain.write_bundle(path, staged)
        adapter = runtime.Adapter(path)
        return adapter

    def test_runtime_factory_separates_founder_continuation_and_wave_config(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = self.runtime_adapter(directory, self.package())
            learner = Mock(); learner.set_enabled.return_value = True
            learner.status.return_value = {'enabled': True}
            with patch.object(p.PracticeLearner, 'from_bundle', return_value=learner) as factory:
                adapter.set_enabled(True)
            self.assertEqual(factory.call_args.args[0], self.founder)
            options = factory.call_args.kwargs
            self.assertEqual(options['continuation_bundle'], self.active)
            self.assertEqual(options['config'].feedback_horizon_tics, 144)
            self.assertIn(adapter.practice_wave['wave_sha256'], str(options['journal_path']))
            self.assertEqual(adapter.status()['native_feedback_horizon_tics'], 144)
            self.assertEqual(adapter.status()['retention_founder_checkpoint_sha256'], self.founder['hashes']['checkpoint_sha256'])
            learner.submit_transition.return_value = False
            self.assertFalse(adapter.record_transition(record()))
            restored = runtime.Adapter(adapter.path)
            self.assertEqual(restored.pending, record())
            self.assertEqual(restored.export_bundle(), adapter.export_bundle())

    def test_promotion_export_restart_and_rollback_preserve_original_package(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = self.runtime_adapter(directory, self.package())
            learner = Mock(); learner.status.return_value = {'enabled': False}
            learner.acknowledge_deployment.return_value = True
            adapter.learner = learner
            before = adapter.export_bundle()
            proposed = changed(before)
            wave = adapter.practice_wave
            proposed['target_contract'] = p.preference_contract(self.active)
            proposed['target_contract'].update(practice_wave_sha256=wave['wave_sha256'],
                native_contract_sha256=digest(canonical(wave['protocol']['native_contract'])),
                native_protocol_sha256=digest(canonical(wave['protocol'])),
                native_horizon_tics=144, retention_founder_checkpoint_sha256=adapter.founder_hash)
            proposed['metadata']['native_contract'] = wave['protocol']['native_contract']
            proposed['hashes']['target_contract_sha256'] = digest(canonical(proposed['target_contract']))
            gate = {'promote': True, 'candidate_checkpoint': proposed['hashes']['checkpoint_sha256']}
            learner.take_promotion.return_value = {'bundle': proposed, 'version': 1,
                                                  'gate': gate, 'gate_sha256': digest(canonical(gate))}
            self.assertTrue(adapter.episode_boundary())
            learner.acknowledge_deployment.assert_called_once_with(proposed['hashes']['checkpoint_sha256'])
            restored = runtime.Adapter(adapter.path)
            self.assertEqual(restored.founder_bundle, self.founder)
            self.assertEqual(restored.continuation_bundle, self.active)
            self.assertEqual(restored.export_bundle(), adapter.export_bundle())
            learner.take_promotion.return_value = {'bundle': before, 'version': 2, 'gate': {'rollback': True}}
            self.assertTrue(adapter.episode_boundary())
            self.assertEqual(adapter.actor.checkpoint_hash, before['hashes']['checkpoint_sha256'])
            self.assertEqual(protocol.unpack_package(adapter.export_bundle())['wave_sha256'], wave['wave_sha256'])

    def test_old_pending_state_cannot_be_overlaid_with_new_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = self.runtime_adapter(directory, self.package())
            (Path(directory)/'pending_transition.json').write_text(json.dumps(record()))
            with self.assertRaisesRegex(ValueError, 'original model directory'):
                runtime.Adapter(adapter.path)

    def test_import_roundtrip_retains_package_without_activation_or_registry_loss(self):
        import brainlab
        with tempfile.TemporaryDirectory() as directory:
            adapter = self.runtime_adapter(directory, self.package())
            payload = adapter.export_bundle()
            student = brainlab.Student.__new__(brainlab.Student)
            student.device = 'python'
            student.lock = threading.RLock()
            registry = Path(directory)/'models'; registry.mkdir()
            legacy = registry/'legacy.json.gz'; legacy.write_bytes(b'original-registry-fixture')
            student.models_dir = registry
            name = student.import_bundle('unit-native-wave', payload)
            imported = runtime.Adapter(registry/name/'bundle.json')
            self.assertEqual(imported.export_bundle(), payload)
            self.assertFalse(imported.enabled)
            self.assertIsNone(imported.learner)
            self.assertEqual(legacy.read_bytes(), b'original-registry-fixture')

    def test_versioned_learner_calls_actual_public_repair(self):
        import time
        config = replace(self.config, new_rows=1, candidate_lifetime=4)
        native = protocol.make_protocol(144, self.active['hashes']['checkpoint_sha256'])
        with tempfile.TemporaryDirectory() as directory:
            learner = p.PracticeLearner.from_bundle(self.founder, initial_bundle=self.active,
                continuation_bundle=self.active, journal_path=Path(directory)/'practice.jsonl',
                config=config, native_protocol=native, practice_wave_sha256='d'*64,
                teacher=Teacher(), evaluator=Mock())
            try:
                before = learner.candidate.snapshot()
                learner.set_enabled(True)
                learner.submit_transition(record())
                deadline = time.monotonic()+20
                while time.monotonic()<deadline:
                    status = learner.status()
                    if status['error'] or status['processed_transitions']:
                        break
                    time.sleep(.02)
                self.assertIsNone(status['error'])
                self.assertEqual(status['updates'], 1)
                self.assertEqual(status['accepted_examples'], 2)
                self.assertNotEqual(before, learner.candidate.snapshot())
                self.assertEqual(json.loads(learner.candidate.snapshot())['admissions'], 1)
            finally:
                learner.close(wait=True)

    def test_adapter_recovers_publication_before_owner_ack(self):
        import time
        config = replace(self.config, new_rows=1, candidate_lifetime=1, gate_seeds=(1220000000,))
        packed = protocol.make_package(self.active, self.founder, self.active,
                                        config=config, wave_name='ack_crash')
        original_factory = p.PracticeLearner.from_bundle
        def factory(*args, **kwargs):
            kwargs.update(teacher=Teacher(), evaluator=lambda b: [fixtures.result(float(json.loads(b['snapshot'])['admissions']))])
            return original_factory(*args, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            adapter = self.runtime_adapter(directory, packed)
            before = adapter.export_bundle()
            with patch.object(p.PracticeLearner, 'from_bundle', side_effect=factory):
                adapter.set_enabled(True)
            learner = adapter.learner
            try:
                adapter.record_transition(record())
                deadline = time.monotonic()+20
                while time.monotonic()<deadline:
                    status = learner.status()
                    if status['error']: self.fail(status['error'])
                    if status['processed_transitions'] and not status['busy']: break
                    time.sleep(.02)
                self.assertEqual(learner.status()['promotions'], 1)
                with patch.object(learner, 'acknowledge_deployment', side_effect=RuntimeError('crash fixture')):
                    with self.assertRaisesRegex(RuntimeError, 'requires recovery'):
                        adapter.episode_boundary()
                self.assertNotEqual(adapter.actor.checkpoint_hash, before['hashes']['checkpoint_sha256'])
                self.assertEqual(json.loads((Path(directory)/'previous_champion.json').read_text()), before)
                self.assertIsNone(adapter._pending_promotion)
            finally:
                learner.close(wait=True)
            restored = runtime.Adapter(adapter.path)
            with patch.object(p.PracticeLearner, 'from_bundle', side_effect=factory):
                restored.set_enabled(True)
            try:
                self.assertEqual(restored.learner._deployed['hashes']['checkpoint_sha256'], restored.actor.checkpoint_hash)
                self.assertIsNone(restored.learner.take_promotion())
                self.assertEqual(restored.learner._deployed_previous['hashes']['checkpoint_sha256'], before['hashes']['checkpoint_sha256'])
            finally:
                restored.learner.close(wait=True)


class LearnerProtocolTests(unittest.TestCase):
    setUp = fixtures.PracticeTests.setUp
    tearDown = fixtures.PracticeTests.tearDown
    learner = fixtures.PracticeTests.learner
    wait = fixtures.PracticeTests.wait

    def test_actual_worker_dispatch_and_restart_keep_protocol(self):
        config = p.PracticeConfig(new_rows=1, candidate_lifetime=4, gate_tasks=('basic',),
                                  gate_seeds=(1220000000,), feedback_horizon_tics=144)
        native = protocol.make_protocol(144, fake_bundle()['hashes']['checkpoint_sha256'])
        teacher = Teacher()
        with patch.object(teacher, 'label', wraps=teacher.label) as label:
            learner = self.learner(config=config, teacher=teacher, native_protocol=native,
                                   practice_wave_sha256='d'*64)
            learner.set_enabled(True); learner.submit_transition(record())
            self.wait(learner, 1)
        self.assertEqual(label.call_args.args[1], native['native_contract'])
        self.assertEqual(learner._new, p.deque())
        self.assertEqual(learner._replay[0]['native_contract'], native['native_contract'])
        learner.close(wait=True)
        restored = p.PracticeLearner.from_bundle(fake_bundle(), journal_path=learner.path,
            config=config, seed_replay=[seed_row()], teacher=Teacher(), evaluator=learner.evaluator,
            native_protocol=native, practice_wave_sha256='d'*64)
        self.learners.append(restored)
        self.assertEqual(restored.candidate.snapshot(), learner.candidate.snapshot())
        self.assertEqual(restored._rng.bit_generator.state, learner._rng.bit_generator.state)
        self.assertEqual(list(restored._replay), list(learner._replay))
        restored.close(wait=True)
        with self.assertRaisesRegex(ValueError, 'target'):
            p.PracticeLearner.from_bundle(fake_bundle(), journal_path=learner.path,
                config=config, seed_replay=[seed_row()], teacher=Teacher(), evaluator=learner.evaluator)

    def test_mismatched_teacher_contract_never_reaches_patch_admission(self):
        config = p.PracticeConfig(new_rows=1, gate_tasks=('basic',), feedback_horizon_tics=144)
        native = protocol.make_protocol(144, fake_bundle()['hashes']['checkpoint_sha256'])
        teacher = Teacher()
        wrong = teacher.label(record(), {'id': 'wrong'})
        teacher.label = Mock(return_value=wrong)
        learner = self.learner(config=config, teacher=teacher, native_protocol=native)
        with self.assertRaisesRegex(ValueError, 'different protocol'):
            learner._process('test', record())
        self.assertEqual(learner.status()['updates'], 0)
        self.assertEqual(learner.candidate.owners, [])


if __name__ == '__main__': unittest.main()
