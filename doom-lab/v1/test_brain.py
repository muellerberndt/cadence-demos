"""Small contract/qualification probes, not a trained Doom capability claim."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np

try:
    from . import brain as api
    from .interface import History, OUTPUT_NAME, PORT_SHAPES, fixed_normalizer
except ImportError:
    import brain as api
    from interface import History, OUTPUT_NAME, PORT_SHAPES, fixed_normalizer


class BrainContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.brain = api.build(device='python')
        cls.bundle = api.make_bundle(cls.brain, fixed_normalizer(), model_id='unit-untrained',
            genome=api.genome_spec(), target_contract={'kind': 'imitation-control', 'chosen': .6, 'other': -.6})

    def test_genomes_expose_twenty_distinct_common_patch_outputs(self):
        for size, patches in (('small', 52), ('medium', 84), ('large', 148)):
            brain = api.build(size, device='python')
            self.assertEqual(brain.graph.n_patches, patches)
            self.assertEqual(brain.graph.n_inputs, 2020)
            layout = json.loads(brain.snapshot())['layout']
            output = layout['outputs'][0]
            self.assertEqual(output['indices'], list(range(20)))
            self.assertEqual(output['reads'], 'policy')
            self.assertEqual(layout['populations'][-1]['observes'], ['scene', 'aim'])
            api.validate_layout(brain.snapshot(), api.genome_spec(size))

    def test_state_only_and_no_sensor_skip_controls_are_explicit(self):
        brain = api.build(observer=False, sensor_skip=False, device='python')
        api.validate_layout(brain.snapshot(), api.genome_spec(observer=False, sensor_skip=False))
        self.assertFalse(any(kind == 'error' for kind, _, _ in brain.graph.edges))
        self.assertLess(len(brain.graph.edges), len(self.brain.graph.edges))

    def test_history_skip_omission_preserves_legacy_genome_and_snapshot(self):
        for options in ({}, {'topology_version': 2, 'recursion_depth': 3, 'sensor_skip': False},
                        {'topology_version': 2, 'recursion_depth': 2, 'observer': False}):
            old_gene = api.genome_spec(**options)
            old = api.build(device='python', **old_gene)
            self.assertNotIn('policy_history_skip', old_gene)
            self.assertEqual(api.genome_spec(policy_history_skip=None, **options), old_gene)
            self.assertEqual(api.build(device='python', policy_history_skip=None, **old_gene).snapshot(), old.snapshot())
            self.assertEqual(api.build(device='python', policy_history_skip=True, **old_gene).snapshot(), old.snapshot())
        for value in (0, 1, 'false', [], {}):
            with self.assertRaisesRegex(ValueError, 'policy_history_skip'):
                api.genome_spec(policy_history_skip=value)

    def test_policy_history_skip_is_independent_and_retains_causal_aim_input(self):
        for observer in (True, False):
            for pixel_skip in (True, False):
                gene = api.genome_spec(topology_version=2, recursion_depth=3,
                    observer=observer, sensor_skip=pixel_skip, policy_history_skip=False)
                brain = api.build(device='python', **gene)
                api.validate_layout(brain.snapshot(), gene)
                specs = api.population_specs(gene)
                self.assertIn('executed_action_history', specs[1]['inputs'])
                self.assertNotIn('executed_action_history', specs[-1]['inputs'])
                self.assertEqual(specs[-1]['observes'], ['reflection2'] if observer else [])
                self.assertEqual(specs[-1]['inputs'], (['periphery','fovea'] if pixel_skip else []) +
                                 ([] if observer else ['reflection2']))
                info = {p['name']: p for p in brain.inspect()['populations']}
                policy = set(info['policy']['indices'])
                deepest = set(info['reflection2']['indices'])
                incoming = [(kind,s,t) for kind,s,t in brain.graph.edges if t in policy]
                if not pixel_skip:
                    self.assertTrue(incoming)
                    self.assertTrue(all(kind in (('state','residual') if observer else ('state',))
                                        and s in deepest for kind,s,t in incoming))
                original = api.build(device='python', **{k:v for k,v in gene.items() if k!='policy_history_skip'})
                self.assertEqual(len(original.graph.edges)-len(brain.graph.edges), 352*20)

    def test_history_skip_bundle_roundtrip_and_false_metadata_refusal(self):
        gene = api.genome_spec(topology_version=2, recursion_depth=3,
                              sensor_skip=False, policy_history_skip=False)
        brain = api.build(device='python', **gene)
        bundle = api.make_bundle(brain, fixed_normalizer(), model_id='no-policy-bypasses',
            genome=gene, target_contract={'kind':'unit-control'})
        restored, data = api.load_bundle(bundle, device='python')
        self.assertEqual(restored.snapshot(), brain.snapshot())
        self.assertIs(data['genome']['policy_history_skip'], False)
        self.assertEqual(len(brain.graph.edges), 16864)
        changed = copy.deepcopy(bundle)
        changed['genome']['policy_history_skip'] = True
        changed['hashes']['genome_sha256'] = api.digest(api.canonical(changed['genome']))
        with self.assertRaisesRegex(ValueError, 'topology'):
            api.load_bundle(changed, device='python')
        brain.settle = Mock(wraps=brain.settle)
        result = api.query(brain, {name:[.1]*size for name,size in PORT_SHAPES.items()}, budget=128)
        self.assertTrue(result['qualified'])
        brain.settle.assert_called_once()
        self.assertEqual(result['scores'], list(result['result']['state'][-20:]))

    def test_deep_genomes_preserve_total_states_and_read_exact_errors_at_each_level(self):
        edges = {'small': (61120, 48680, 44384), 'medium': (94720, 70800, 62016),
                 'large': (161920, 117920, 99584)}
        for size, patches in (('small', 52), ('medium', 84), ('large', 148)):
            for depth in (1, 2, 3):
                gene = api.genome_spec(size, topology_version=2, recursion_depth=depth)
                brain = api.build(device='python', **gene)
                self.assertEqual(brain.graph.n_patches, patches)
                self.assertEqual(len(brain.graph.edges), edges[size][depth-1])
                api.validate_layout(brain.snapshot(), gene)
                info = {p['name']: p for p in brain.inspect()['populations']}
                specs = api.population_specs(gene)
                self.assertEqual(sum(bool(p['observes']) for p in specs), depth)
                for spec in specs:
                    for source in spec['observes']:
                        source_indices, target_indices = info[source]['indices'], info[spec['name']]['indices']
                        incoming = {(kind, s, t) for kind, s, t in brain.graph.edges
                                    if s in source_indices and t in target_indices and kind != 'input'}
                        expected = {(kind, s, t) for kind in ('state', 'residual')
                                    for s in source_indices for t in target_indices}
                        self.assertEqual(incoming, expected)
                if depth > 1:
                    self.assertEqual(specs[-1]['observes'], ['reflection'+str(depth-1)])

    def test_version_omission_preserves_original_snapshot_and_rejects_mismatched_depth(self):
        versioned = api.build(topology_version=2, recursion_depth=1, device='python')
        self.assertEqual(versioned.snapshot(), self.brain.snapshot())
        deep = api.build(topology_version=2, recursion_depth=3, device='python')
        with self.assertRaisesRegex(ValueError, 'topology'):
            api.validate_layout(deep.snapshot(), api.genome_spec(topology_version=2, recursion_depth=2))
        for invalid in ({'seed': -1}, {'recursion_depth': 2},
                        {'topology_version': 2, 'recursion_depth': 4}):
            with self.assertRaises(ValueError):
                api.genome_spec(**invalid)

    def test_deep_query_uses_one_coupled_settlement_and_keeps_output_rule(self):
        brain = api.build(topology_version=2, recursion_depth=3, sensor_skip=False, device='python')
        brain.settle = Mock(wraps=brain.settle)
        inputs = {name: [.1]*size for name, size in PORT_SHAPES.items()}
        result = api.query(brain, inputs, budget=128)
        self.assertTrue(result['qualified'])
        brain.settle.assert_called_once()
        self.assertEqual(len(result['result']['state']), 52)
        self.assertEqual(result['scores'], list(result['result']['state'][-20:]))
        gene = api.genome_spec(topology_version=2, recursion_depth=3, sensor_skip=False)
        bundle = api.make_bundle(brain, fixed_normalizer(), model_id='deep-control',
            genome=gene, target_contract={'kind': 'unit-control'})
        restored, data = api.load_bundle(bundle, device='python')
        self.assertEqual(data['genome'], gene)
        self.assertEqual(restored.snapshot(), brain.snapshot())

    def test_bundle_roundtrip_and_tampering_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bundle.json'
            api.write_bundle(path, self.bundle)
            restored, bundle = api.load_bundle(path, device='python')
        self.assertEqual(restored.snapshot(), self.brain.snapshot())
        self.assertEqual(bundle, self.bundle)
        for field in ('normalization', 'contract', 'genome', 'target_contract'):
            changed = copy.deepcopy(self.bundle)
            changed[field]['tampered'] = True
            with self.assertRaises(ValueError):
                api.load_bundle(changed, device='python')
        changed = copy.deepcopy(self.bundle)
        changed['contract']['visual_lags'] = [1, 2, 4, 8]
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            api.load_bundle(changed, device='python')
        with self.assertRaisesRegex(ValueError, 'seed'):
            api.make_bundle(self.brain, fixed_normalizer(), model_id='incorrect-seed',
                genome=api.genome_spec(seed=3), target_contract={'kind': 'test'})

    def test_real_qualified_query_has_no_hidden_state_commit(self):
        inputs = {name: [0.]*size for name, size in PORT_SHAPES.items()}
        state = self.brain.state
        result = api.query(self.brain, inputs, budget=64)
        self.assertTrue(result['qualified'])
        self.assertIsInstance(result['action'], int)
        self.assertEqual(len(result['buttons']), 9)
        self.assertEqual(self.brain.state, state)

    def test_refused_or_nonfinite_query_never_supplies_an_action(self):
        inputs = {name: [0.]*size for name, size in PORT_SHAPES.items()}
        for qualified, scores in ((False, [0.]*20), (True, [float('nan')]*20)):
            brain = Mock(settle=Mock(return_value={'qualified': qualified,
                'outputs': {OUTPUT_NAME: scores}}))
            result = api.query(brain, inputs)
            self.assertFalse(result['qualified'])
            self.assertIsNone(result['action'])
            self.assertIsNone(result['buttons'])
        with self.assertRaises(ValueError):
            api.query(Mock(), {'periphery': [0.]*640})

    def test_actor_memory_requires_matching_executed_proposal(self):
        actor = api.Actor(self.bundle, device='python')
        actor.brain = Mock(settle=Mock(return_value={'qualified': True,
            'outputs': {OUTPUT_NAME: [0.]*20}}))
        raw = np.full((240, 320), 128, np.uint8)
        proposal = actor.choose(raw)
        self.assertEqual(actor.history.executed_steps, 0)
        with self.assertRaises(RuntimeError):
            actor.choose(raw)
        with self.assertRaises(ValueError):
            actor.acknowledge(raw, 1, 4)
        changed = raw.copy(); changed[0, 0] = 0
        with self.assertRaises(ValueError):
            actor.acknowledge(changed, proposal['action'], 4)
        actor.acknowledge(raw, proposal['action'], 4)
        self.assertEqual(actor.history.executed_steps, 1)
        with self.assertRaises(RuntimeError):
            actor.acknowledge(raw, proposal['action'], 4)
        actor.reset()
        self.assertEqual(actor.history.executed_steps, 0)
        actor.brain.settle.return_value['qualified'] = False
        self.assertIsNone(actor.choose(raw)['action'])
        with self.assertRaises(RuntimeError):
            actor.acknowledge(raw, 0, 4)


if __name__ == '__main__':
    unittest.main()
