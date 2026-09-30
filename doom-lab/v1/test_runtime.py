"""Actual actor/registry contract probes; fake engine supplies no privileged actor inputs."""
import copy
import json
import os
from pathlib import Path
import random
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from . import brain, runtime
from .interface import fixed_normalizer, PORT_SHAPES
from .tasks import get_task


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = brain.make_bundle(brain.build(device='python'), fixed_normalizer(),
            model_id='unit-untrained', genome=brain.genome_spec(), target_contract={'kind': 'unit-control'})
        cls.platform = {'system': 'test', 'machine': 'test', 'engine_binary_sha256': '0'*64}
        cls.task = get_task('doom1:E1M1')

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.enterContext(patch.dict(os.environ, {'DOOM_LAB_ENABLE_V3': '1', 'DOOM_LAB_PORT': '8667'}))
        self.enterContext(patch.object(runtime, 'platform_identity', return_value=self.platform))
        self.enterContext(patch.object(runtime, 'task_identity',
            side_effect=lambda task: {'task': vars(get_task(task)), 'engine_version': 'unit'}))
        self.staging = runtime.prepare_staging_bundle(self.bundle, self.task, source_platform=self.platform)

    def adapter(self):
        path = Path(self.directory.name)/'bundle.json'
        brain.write_bundle(path, self.staging)
        return runtime.Adapter(path)

    def test_deployment_requires_optin_task_and_explicit_platform_evaluation(self):
        task, restored = runtime.validate_deployment(self.staging)
        self.assertEqual(task, self.task)
        self.assertEqual(restored['metadata']['deployment_validation']['status'], 'not_evaluated')
        for variable, value, pattern in [('DOOM_LAB_PORT', '8666', 'staging')]:
            with patch.dict(os.environ, {variable: value}):
                with self.assertRaisesRegex(ValueError, pattern):
                    runtime.validate_deployment(self.staging)
        changed = copy.deepcopy(self.staging)
        changed['metadata']['deployment_identity']['engine_version'] = 'different'
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            runtime.validate_deployment(changed)
        changed = copy.deepcopy(self.staging)
        changed['metadata']['deployment_validation']['target_platform']['system'] = 'other'
        with self.assertRaisesRegex(ValueError, 'platform-specific'):
            runtime.validate_deployment(changed)
        heldout = runtime.prepare_staging_bundle(self.bundle, 'doom1:E1M5', source_platform=self.platform)
        with self.assertRaisesRegex(ValueError, 'Held-out'):
            runtime.validate_deployment(heldout)

    def test_deployment_cannot_relabel_a_protected_task_as_training(self):
        changed = copy.deepcopy(self.staging)
        task = vars(get_task('doom1:E1M5')).copy()
        task['split'] = 'train'
        changed['metadata']['deployment_task'] = task
        with self.assertRaisesRegex(ValueError, 'canonical task'):
            runtime.validate_deployment(changed)
        task['task_id'] = 'custom-train'
        with self.assertRaises(KeyError):
            runtime.validate_deployment(changed)

    def test_adapter_exports_graph_and_cannot_claim_online_learning(self):
        adapter = self.adapter()
        graph = adapter.graph_payload()
        self.assertEqual(graph['n_periphery']+graph['n_fovea'], 2020)
        self.assertEqual(graph['motor'], 20)
        self.assertEqual(len(graph['edges']), 1400)
        self.assertEqual(adapter.model_info['patches'], 52)
        self.assertEqual(adapter.export_bundle(), self.staging)
        with self.assertRaisesRegex(ValueError, 'not yet attached'):
            adapter.set_enabled(True)
        self.assertFalse(adapter.status()['available'])
        self.assertFalse(adapter.status()['enabled'])

    def exercise(self, *, qualified=True, interrupt=False):
        adapter = self.adapter()
        lab = SimpleNamespace(mode='student', episode=0, reset_request=False, session_id='unit',
            _stop=threading.Event(), rng=random.Random(0), _publish_frame=Mock(),
            student=SimpleNamespace(adapter=adapter, generation=0, _swapping=False, _swap_request=None))
        lab.set_mode = lambda mode: setattr(lab, 'mode', mode)
        raw = np.full((240, 320), 128, np.uint8)
        env = Mock(finished=False, total_reward=0., seed=1,
                   last_facts={'health': 100, 'selected_weapon_ammo': 50, 'killcount': 0,
                               'dead': False, 'timeout': False})
        env.observe.return_value = raw
        env.outcome.side_effect = lambda external_cutoff=None: {'success': False, 'reason': external_cutoff}
        def step(action, tics):
            lab._stop.set()
            return {'tics': 2}  # partial terminal action: history must record two, not requested four
        env.step.side_effect = step
        def settle(*args, **kwargs):
            if interrupt:
                lab.set_mode('idle')
            return {'qualified': qualified, 'outputs': {'action_scores': [0.]*20},
                    'state': [0.]*52, 'errors': [0.]*52, 'sweeps': 1}
        adapter.actor.brain.settle = Mock(side_effect=settle)
        with patch.object(runtime, 'DoomEnv', return_value=env) as factory:
            adapter.run_session(lab)
        self.assertFalse(factory.call_args.kwargs['teacher'])
        self.assertEqual(adapter.last_episode['fallback_actions'], 0)
        env.close.assert_called_once()
        return adapter, env, lab

    def test_qualified_action_records_actual_tics_and_only_visual_history(self):
        adapter, env, _ = self.exercise()
        env.step.assert_called_once_with(0, tics=4)
        self.assertEqual(adapter.actor.history.executed_steps, 1)
        encoded = adapter.actor.history.encode(np.zeros((240, 320), np.uint8), adapter.bundle['normalization'])
        self.assertAlmostEqual(encoded['executed_action_history'][-2], .1)
        self.assertEqual(adapter.last_episode['qualified_queries'], 1)

    def test_refused_query_never_calls_engine_or_updates_history(self):
        adapter, env, lab = self.exercise(qualified=False)
        env.step.assert_not_called()
        self.assertEqual(adapter.actor.history.executed_steps, 0)
        self.assertEqual(lab.mode, 'idle')
        self.assertEqual(adapter.last_episode['cutoff_reason'], 'query_refused')

    def test_mode_change_during_query_discards_proposal(self):
        adapter, env, _ = self.exercise(interrupt=True)
        env.step.assert_not_called()
        self.assertEqual(adapter.actor.history.executed_steps, 0)
        self.assertEqual(adapter.last_episode['cutoff_reason'], 'interrupted_before_execution')

    def test_registry_roundtrip_rejects_incompatible_families(self):
        import brainlab
        student = brainlab.Student.__new__(brainlab.Student)
        student.models_dir = Path(self.directory.name)/'models'
        student.lock = threading.RLock()
        student.swap_error = None
        with self.assertRaises((ValueError, KeyError)):
            student.import_bundle('old', {'schema': 'doomlab-brain/1'})
        first = student.import_bundle('test', self.staging)
        second = student.import_bundle('test', self.staging)
        self.assertEqual((first, second), ('test', 'test-1'))
        self.assertEqual({r['id'] for r in student.scan_models()}, {first, second})
        self.assertTrue(student.request_swap(first))
        self.assertFalse(student.request_swap('../escape'))

    def practice_adapter(self):
        from .practice import attach_seed_replay, PracticeLearner
        from .test_practice import seed_row
        from .training import target_contract
        original, _ = brain.load_bundle(self.bundle, device='python')
        source = brain.make_bundle(original, fixed_normalizer(), model_id='practice-fixture',
            genome=brain.genome_spec(), target_contract=target_contract('centered'))
        source = attach_seed_replay(source, [seed_row()])
        self.staging = runtime.prepare_staging_bundle(source, 'basic', source_platform=self.platform)
        self.enterContext(patch.dict(os.environ, {'DOOM_LAB_PRACTICE': '1'}))
        status = {'enabled': False, 'phase': 'paused', 'error': None, 'queue': 0}
        learner = Mock()
        learner.status.side_effect = lambda: dict(status)
        def set_enabled(value):
            status['enabled'] = value
            return value
        learner.set_enabled.side_effect = set_enabled
        learner.take_promotion.return_value = None
        factory = self.enterContext(patch.object(PracticeLearner, 'from_bundle', return_value=learner))
        return self.adapter(), learner, status, factory

    def test_practice_pending_evidence_survives_backpressure_and_worker_failure(self):
        from .test_practice import record
        adapter, learner, status, factory = self.practice_adapter()
        self.assertTrue(adapter.status()['available'])
        adapter.set_enabled(True)
        self.assertEqual(factory.call_args.args[0], adapter.founder_bundle)
        self.assertEqual(factory.call_args.kwargs['initial_bundle'], adapter.bundle)
        learner.submit_transition.return_value = False
        row = record()
        self.assertFalse(adapter.record_transition(row))
        pending_path = adapter.path.parent/'pending_transition.json'
        self.assertEqual(json.loads(pending_path.read_text()), row)
        with self.assertRaisesRegex(RuntimeError, 'overwritten'):
            adapter.record_transition(record('two'))
        status.update(enabled=False, error='journal cap')
        self.assertTrue(adapter.flush_pending())  # game may run frozen; evidence stays retained
        self.assertFalse(adapter.status()['enabled'])
        self.assertEqual(adapter.status()['error'], 'journal cap')
        self.assertTrue(pending_path.is_file())
        restored = runtime.Adapter(adapter.path)
        self.assertEqual(restored.pending, row)
        status.update(enabled=True, error=None)
        adapter.set_enabled(True)
        learner.submit_transition.return_value = True
        self.assertTrue(adapter.flush_pending())
        self.assertFalse(pending_path.exists())
        adapter.close()
        learner.close.assert_called_once_with(wait=False)

    def test_promotion_receipt_publication_and_restart_keep_fixed_founder(self):
        from .interface import canonical, digest
        adapter, learner, status, factory = self.practice_adapter()
        adapter.set_enabled(True)
        founder = copy.deepcopy(adapter.founder_bundle)
        gate = {'promote': True, 'candidate_checkpoint': adapter.actor.checkpoint_hash}
        proposal = {'bundle': copy.deepcopy(adapter.bundle), 'version': 2,
                    'gate': gate, 'gate_sha256': digest(canonical(gate))}
        learner.take_promotion.return_value = proposal
        before = adapter.export_bundle()
        with patch.object(runtime, 'write_bundle', side_effect=OSError('disk fixture')):
            with self.assertRaisesRegex(OSError, 'disk fixture'):
                adapter.episode_boundary()
        self.assertEqual(adapter.export_bundle(), before)
        self.assertEqual(adapter.version, 0)
        self.assertTrue(adapter.episode_boundary())
        self.assertEqual(adapter.version, 2)
        self.assertEqual(adapter.bundle['metadata']['deployment_validation']['status'], 'passed')
        restored = runtime.Adapter(adapter.path)
        self.assertEqual(restored.version_offset, 2)
        self.assertEqual(restored.founder_bundle, founder)
        self.assertEqual(restored.bundle, adapter.bundle)
        bad = copy.deepcopy(proposal)
        bad['gate_sha256'] = '0'*64
        learner.take_promotion.return_value = bad
        with self.assertRaisesRegex(ValueError, 'exact qualified native gate'):
            adapter.episode_boundary()


if __name__ == '__main__':
    unittest.main()
