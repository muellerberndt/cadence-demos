import unittest
from . import brain
from .causal_probe import diagnostic_clone, intervention_indices, measure
from .interface import PORT_SHAPES, fixed_normalizer


class CausalProbeTests(unittest.TestCase):
    def test_detached_intervention_preserves_original_and_exact_other_parameters(self):
        original = brain.build(topology_version=2, recursion_depth=3, sensor_skip=False, device='python')
        before = original.snapshot()
        indices = intervention_indices(original)
        self.assertEqual(indices['zero_direct_current_pixels_to_policy'], [])
        chosen = set(indices['zero_all_residual_reads'])
        self.assertGreater(len(chosen), 0)
        changed = diagnostic_clone(original, chosen, device='python')
        self.assertEqual(original.snapshot(), before)
        self.assertEqual(changed.biases, original.biases)
        for index, (before_weight, after) in enumerate(zip(original.weights, changed.weights)):
            self.assertEqual(after, 0 if index in chosen else before_weight)

    def test_empty_intervention_is_control_and_all_query_refusals_remain_visible(self):
        gene = brain.genome_spec(topology_version=2, recursion_depth=3, sensor_skip=False)
        original = brain.build(device='python', **gene)
        bundle = brain.make_bundle(original, fixed_normalizer(), model_id='probe-control',
            genome=gene, target_contract={'kind': 'unit-control'})
        inputs = {name: [.1]*width for name, width in PORT_SHAPES.items()}
        result = measure(bundle, [inputs], device='python')
        self.assertEqual(result['baseline_qualified'], 1)
        control = result['results'][-1]
        self.assertEqual(control['zeroed_edges'], 0)
        self.assertEqual(control['action_changes'], 0)
        self.assertEqual(control['max_abs_score_delta'], 0.)
        self.assertTrue(result['original_preserved'])
        refused_bundle = dict(bundle, query_budget=1)
        refused = measure(refused_bundle, [inputs], device='python')
        self.assertEqual(refused['baseline_qualified'], 0)
        self.assertTrue(all(row['jointly_qualified'] == 0 for row in refused['results']))
        self.assertTrue(all(row['max_abs_score_delta'] is None for row in refused['results']))


if __name__ == '__main__':
    unittest.main()
