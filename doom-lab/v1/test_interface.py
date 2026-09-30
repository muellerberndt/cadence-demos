"""Pure observation/causality checks; no Doom engine or cloud is required."""
import json
import unittest

import numpy as np

try:
    from . import interface as api
except ImportError:
    import interface as api


class InterfaceTests(unittest.TestCase):
    def test_action_menu_is_exact_and_has_navigation_controls(self):
        self.assertEqual(len(api.ACTION_NAMES), 20)
        self.assertEqual(len(set(api.ACTION_BUTTONS)), 20)
        for i, buttons in enumerate(api.ACTION_BUTTONS):
            self.assertEqual(api.action_index(buttons), i)
            for a, b in ((0, 1), (2, 3), (4, 5)):
                self.assertFalse(buttons[a] and buttons[b])
        self.assertEqual(api.ACTION_BUTTONS[api.ACTION_NAMES.index('use')][6], 1)
        self.assertEqual(api.ACTION_BUTTONS[api.ACTION_NAMES.index('weapon_next')][8], 1)
        with self.assertRaises(ValueError):
            api.action_index((1, 1, 0, 0, 0, 0, 0, 0, 0))

    def test_area_pools_match_independent_rectangular_means(self):
        raw = np.random.default_rng(9).integers(0, 256, (240, 320), dtype=np.uint8)
        values = api.features(raw)
        for row, col in ((0, 0), (4, 8), (19, 31)):
            self.assertAlmostEqual(values['periphery'][row*32+col],
                raw[row*12:(row+1)*12, col*10:(col+1)*10].mean()/255)
        self.assertAlmostEqual(values['fovea'][0], raw[48:60, 32:40].mean()/255)
        self.assertAlmostEqual(values['coarse'][-1], raw[216:240, 300:320].mean()/255)

    def test_causal_visual_and_action_memory_advance_only_on_acknowledgment(self):
        history = api.History()
        norms = api.fixed_normalizer()
        raw = np.full((240, 320), 128, dtype=np.uint8)
        blank = history.encode(raw, norms)
        self.assertEqual(history.encode(raw, norms), blank)
        self.assertFalse(any(blank['visual_history']))
        self.assertFalse(any(blank['executed_action_history']))
        for step in range(64):
            history.acknowledge(np.full_like(raw, step), step % 20, 4)
        inputs = history.encode(raw, norms)
        visual = np.array(inputs['visual_history']).reshape(4, 161)
        for row, lag in enumerate(api.VISUAL_LAGS):
            expected = ((64-lag)/255-.5)/.25*.2
            self.assertTrue(np.allclose(visual[row, :160], expected))
            self.assertEqual(visual[row, 160], .2)
        actions = np.array(inputs['executed_action_history']).reshape(16, 22)
        self.assertEqual(actions[-1, 63 % 20], .2)
        self.assertEqual(actions[-1, 20], .2)
        self.assertEqual(actions[-1, 21], .2)
        self.assertEqual(sum(len(v) for v in inputs.values()), 2020)
        self.assertEqual(history.executed_steps, 64)
        history.reset()
        self.assertEqual(history.encode(raw, norms), blank)

    def test_failed_ack_and_missing_current_frame_preserve_memory(self):
        history = api.History()
        raw = np.zeros((240, 320), dtype=np.uint8)
        norms = api.fixed_normalizer()
        before = history.encode(raw, norms)
        for action, tics in ((20, 4), (0, 0), (0, 5), (True, 4)):
            with self.assertRaises(ValueError):
                history.acknowledge(raw, action, tics)
        with self.assertRaises(ValueError):
            history.encode(None, norms)
        self.assertEqual(history.encode(raw, norms), before)

    def test_train_only_fit_is_streaming_and_never_changes_during_queries(self):
        frames = [np.zeros((240, 320), np.uint8), np.full((240, 320), 255, np.uint8)]
        norms = api.fit_normalizer(iter(frames))
        for key in api.FEATURE_SHAPES:
            self.assertTrue(np.allclose(norms['mean'][key], .5))
            self.assertTrue(np.allclose(norms['scale'][key], .5))
        saved = json.dumps(norms, sort_keys=True)
        api.History().encode(frames[0], norms)
        self.assertEqual(json.dumps(norms, sort_keys=True), saved)
        with self.assertRaises(ValueError):
            api.fit_normalizer([])

    def test_history_gene_changes_context_without_changing_capacity(self):
        default, short = api.History(), api.History(api.SHORT_VISUAL_LAGS)
        norms = api.fixed_normalizer()
        raw = np.full((240, 320), 128, np.uint8)
        for step in range(8):
            frame = np.full_like(raw, step)
            for history in (default, short):
                history.acknowledge(frame, 0, 4)
        a, b = default.encode(raw, norms), short.encode(raw, norms)
        self.assertNotEqual(a['visual_history'], b['visual_history'])
        self.assertEqual({k: len(v) for k, v in a.items()}, {k: len(v) for k, v in b.items()})
        self.assertNotEqual(api.contract(), api.contract(api.SHORT_VISUAL_LAGS))


if __name__ == '__main__':
    unittest.main()
