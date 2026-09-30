"""Versioned visual/action boundary shared by Doom collection and deployment.

History is explicit bounded external memory. It commits only after an executed
action, and never supplies a hidden controller, privileged state or neural step.
All designed constants are declared controls; the visual lags are a genome gene.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json

import numpy as np


SCHEMA = 'cadence-doom-interface-v3/1'
REPEAT_TICS = 4
RAW_SHAPE = (240, 320)
BUTTON_NAMES = ('MOVE_FORWARD', 'MOVE_BACKWARD', 'TURN_LEFT', 'TURN_RIGHT',
                'MOVE_LEFT', 'MOVE_RIGHT', 'USE', 'ATTACK', 'SELECT_NEXT_WEAPON')
ACTION_NAMES = ('noop', 'forward', 'backward', 'turn_left', 'turn_right',
                'strafe_left', 'strafe_right', 'forward_left', 'forward_right',
                'forward_strafe_left', 'forward_strafe_right', 'use', 'fire',
                'fire_left', 'fire_right', 'fire_strafe_left', 'fire_strafe_right',
                'backward_fire', 'forward_fire', 'weapon_next')
_PRESSED = ((), (0,), (1,), (2,), (3,), (4,), (5,), (0, 2), (0, 3),
            (0, 4), (0, 5), (6,), (7,), (7, 2), (7, 3), (7, 4),
            (7, 5), (1, 7), (0, 7), (8,))
ACTION_BUTTONS = tuple(tuple(int(i in pressed) for i in range(len(BUTTON_NAMES)))
                       for pressed in _PRESSED)
VISUAL_LAGS = (1, 4, 16, 64)
SHORT_VISUAL_LAGS = (1, 2, 4, 8)
ACTION_HISTORY = 16
HISTORY_SCALE = .2
PORT_SHAPES = {'periphery': 640, 'fovea': 384, 'visual_history': 644,
               'executed_action_history': 352}
OUTPUT_NAME = 'action_scores'
NORMALIZER_SCHEMA = 'cadence-doom-normalizer-v3/1'
FEATURE_SHAPES = {'periphery': 640, 'fovea': 384, 'coarse': 160}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    payload = value if isinstance(value, bytes) else value.encode()
    return hashlib.sha256(payload).hexdigest()


def validate_lags(values):
    values = tuple(values)
    if (len(values) != 4 or any(type(v) is not int or not 1 <= v <= 256 for v in values)
            or tuple(sorted(set(values))) != values):
        raise ValueError('Declare four distinct increasing visual lags in [1, 256]')
    return values


def validate_action(action):
    if isinstance(action, bool) or not isinstance(action, (int, np.integer)) or not 0 <= action < len(ACTION_NAMES):
        raise ValueError('Action must identify one of the 20 declared button macros')
    return int(action)


def action_index(buttons):
    buttons = tuple(buttons)
    if len(buttons) != len(BUTTON_NAMES) or any(type(v) is not int or v not in (0, 1) for v in buttons):
        raise ValueError('Expected nine exact binary buttons in declared order')
    try:
        return ACTION_BUTTONS.index(buttons)
    except ValueError as error:
        raise ValueError('Button combination is outside the declared action menu') from error


def contract(visual_lags=VISUAL_LAGS):
    return {'schema': SCHEMA, 'raw_shape': list(RAW_SHAPE), 'raw_dtype': 'uint8',
            'screen_format': 'GRAY8', 'render_hud': True,
            'button_names': list(BUTTON_NAMES), 'action_names': list(ACTION_NAMES),
            'action_buttons': [list(row) for row in ACTION_BUTTONS], 'repeat_tics': REPEAT_TICS,
            'ports': dict(PORT_SHAPES), 'output': OUTPUT_NAME,
            'periphery_shape': [20, 32], 'fovea_shape': [12, 32],
            'fovea_crop_yxyx': [48, 32, 192, 288], 'coarse_shape': [10, 16],
            'pixel_transform': 'exact-area-mean-div255-float64',
            'visual_lags': list(validate_lags(visual_lags)),
            'action_history': ACTION_HISTORY, 'history_scale': HISTORY_SCALE,
            'memory': 'external-causal-visual-and-executed-action-history'}


def features(raw):
    """Three exact rectangular area pools; no learned or privileged features."""
    value = np.asarray(raw)
    if value.shape != RAW_SHAPE or value.dtype != np.uint8:
        raise ValueError('A current 320x240 GRAY8 uint8 observation is required')
    return {
        'periphery': value.reshape(20, 12, 32, 10).mean(axis=(1, 3)).reshape(-1)/255,
        'fovea': value[48:192, 32:288].reshape(12, 12, 32, 8).mean(axis=(1, 3)).reshape(-1)/255,
        'coarse': value.reshape(10, 24, 16, 20).mean(axis=(1, 3)).reshape(-1)/255,
    }


def fixed_normalizer():
    """Explicit unfitted control; campaigns should compare train-only fitting."""
    return {'schema': NORMALIZER_SCHEMA, 'source': 'fixed-control', 'frames': 0,
            'clip': 3., 'multiplier': .2, 'minimum_scale': .05,
            'mean': {k: [.5]*n for k, n in FEATURE_SHAPES.items()},
            'scale': {k: [.25]*n for k, n in FEATURE_SHAPES.items()}}


def fit_normalizer(training_frames):
    """Streaming moments from the caller's declared training split only."""
    count = 0
    means = {k: np.zeros(n, dtype=np.float64) for k, n in FEATURE_SHAPES.items()}
    m2 = {k: np.zeros_like(v) for k, v in means.items()}
    for raw in training_frames:
        row = features(raw)
        count += 1
        for key, value in row.items():
            delta = value - means[key]
            means[key] += delta/count
            m2[key] += delta*(value-means[key])
    if not count:
        raise ValueError('Training frames are required to fit a normalizer')
    return {'schema': NORMALIZER_SCHEMA, 'source': 'training-frames', 'frames': count,
            'clip': 3., 'multiplier': .2, 'minimum_scale': .05,
            'mean': {k: value.tolist() for k, value in means.items()},
            'scale': {k: np.maximum(np.sqrt(np.maximum(value/count, 0)), .05).tolist()
                      for k, value in m2.items()}}


def validate_normalizer(normalizer):
    if (normalizer.get('schema') != NORMALIZER_SCHEMA or normalizer.get('clip') != 3.
            or normalizer.get('multiplier') != .2 or normalizer.get('minimum_scale') != .05):
        raise ValueError('Normalizer does not match the frozen conditioning contract')
    result = {}
    for kind in ('mean', 'scale'):
        if set(normalizer.get(kind, {})) != set(FEATURE_SHAPES):
            raise ValueError('Normalizer must cover every pixel feature group exactly')
        result[kind] = {}
        for key, size in FEATURE_SHAPES.items():
            value = np.asarray(normalizer[kind][key], dtype=np.float64)
            if value.shape != (size,) or not np.isfinite(value).all():
                raise ValueError('Invalid normalizer coordinates for ' + key)
            if kind == 'scale' and (value < .05).any():
                raise ValueError('Normalizer scales must preserve the declared .05 floor')
            result[kind][key] = value
    return result


class History:
    """Episode-local causal context; querying alone never advances its memory."""
    def __init__(self, visual_lags=VISUAL_LAGS):
        self.visual_lags = validate_lags(visual_lags)
        self._frames = deque(maxlen=max(self.visual_lags))
        self._actions = deque(maxlen=ACTION_HISTORY)
        self.executed_steps = 0

    def reset(self):
        self._frames.clear()
        self._actions.clear()
        self.executed_steps = 0

    def acknowledge(self, raw_pre_action, action, actual_tics):
        """Call once after actual execution, never for a proposal or refused query."""
        action = validate_action(action)
        if type(actual_tics) is not int or not 1 <= actual_tics <= REPEAT_TICS:
            raise ValueError('Record one through four actual executed tics')
        coarse = features(raw_pre_action)['coarse']
        self._frames.append(coarse.copy())
        self._actions.append((action, actual_tics))
        self.executed_steps += 1

    def encode(self, raw, normalizer):
        row = features(raw)  # A missing observation is refused, never copied forward.
        norms = validate_normalizer(normalizer)
        def condition(name, values):
            return np.clip((values-norms['mean'][name])/norms['scale'][name], -3, 3)*.2
        visual = np.zeros((4, 161), dtype=np.float64)
        for i, lag in enumerate(self.visual_lags):
            if len(self._frames) >= lag:
                visual[i, :160] = condition('coarse', self._frames[-lag])
                visual[i, 160] = HISTORY_SCALE
        actions = np.zeros((ACTION_HISTORY, 22), dtype=np.float64)
        for i, (action, tics) in enumerate(self._actions, start=ACTION_HISTORY-len(self._actions)):
            actions[i, action] = HISTORY_SCALE
            actions[i, 20] = HISTORY_SCALE*tics/REPEAT_TICS
            actions[i, 21] = HISTORY_SCALE
        return {'periphery': condition('periphery', row['periphery']).tolist(),
                'fovea': condition('fovea', row['fovea']).tolist(),
                'visual_history': visual.reshape(-1).tolist(),
                'executed_action_history': actions.reshape(-1).tolist()}


def validate_inputs(inputs):
    if not isinstance(inputs, dict) or set(inputs) != set(PORT_SHAPES):
        raise ValueError('All four declared current/history input ports are required')
    for name, size in PORT_SHAPES.items():
        value = np.asarray(inputs[name], dtype=np.float64)
        if value.shape != (size,) or not np.isfinite(value).all():
            raise ValueError('Invalid input coordinates for ' + name)
        if np.max(np.abs(value), initial=0) > .6000000000000001:
            raise ValueError('Inputs exceed the declared conditioned boundary')
    return inputs
