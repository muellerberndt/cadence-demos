import copy
import unittest
import numpy as np
from .retained_targets import blend_native_target, score_vector
from .practice import preference_target


class RetainedTargetTests(unittest.TestCase):
    def test_eta_one_exact_control_and_inputs_unchanged(self):
        scores=np.linspace(-1,1,20).tolist();values=[-.1]*20;values[3]=.9
        before=copy.deepcopy((scores,values))
        self.assertEqual(blend_native_target(scores,values,0)['targets'],scores)
        self.assertEqual(blend_native_target(scores,values,1)['targets'],preference_target(values)['targets'])
        self.assertEqual((scores,values),before)

    def test_convex_step_and_bounds(self):
        scores=np.linspace(-1,1,20);values=[0.]*20;values[2]=values[4]=1.
        preference=np.array(preference_target(values)['targets'])
        for eta in [0.,.1,.25,1.]:
            target=np.array(blend_native_target(scores,values,eta)['targets'])
            self.assertTrue(np.all(np.abs(target)<=1))
            np.testing.assert_allclose(target-scores,eta*(preference-scores),rtol=0,atol=2e-16)
            self.assertAlmostEqual(float(target.sum()),(1-eta)*float(scores.sum()))

    def test_ties_and_invalid_evidence_refused(self):
        self.assertIsNone(blend_native_target([0.]*20,[0.]*20,.1))
        for scores in [[0.]*19,[float('nan')]*20,[1.00001]*20]:
            with self.assertRaises(ValueError):score_vector(scores)
        for eta in [-1,.2,2,True,float('nan')]:
            with self.assertRaises(ValueError):blend_native_target([0.]*20,[1.]+[0.]*19,eta)
        with self.assertRaises(ValueError):blend_native_target([0.]*20,[float('inf')]*20,.1)


if __name__=='__main__':unittest.main()
