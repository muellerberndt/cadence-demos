"""Prospective experience selection with atomic counter and pending custody.

This changes which executed contexts are collected, never the actor, native
feedback values or admission rule. Episode resets do not reset this counter.
"""
import copy
import json
from pathlib import Path

from .interface import canonical, digest

SCHEMA = 'doom-executed-experience-sampling/1'


def contract(stride):
    if type(stride) is not int or stride not in (1, 32, 64):
        raise ValueError('Explicit collection stride must be1,32 or64')
    return {'schema': SCHEMA, 'collection_stride': stride,
            'selection': 'zero-based durable global executed-decision index modulo stride equals zero, while learning enabled',
            'counter_scope': 'all qualified actual autonomous decisions in this wave, including learning-disabled decisions; persistent across episodes and restarts',
            'history': 'all actual decisions advance complete actor history and episode replay prefix',
            'backpressure': 'selected records retain atomic durable custody until learner acknowledges them; unselected contexts are counted explicitly'}


def validate_contract(value):
    if not isinstance(value, dict) or value != contract(value.get('collection_stride')):
        raise ValueError('Experience collection contract differs')
    return value['collection_stride']


class ExperienceSampler:
    def __init__(self, path, wave_sha256, specification):
        self.path = Path(path)
        self.stride = validate_contract(specification)
        self.identity = {'schema': SCHEMA, 'practice_wave_sha256': wave_sha256,
                         'contract': copy.deepcopy(specification)}
        self.data = {**self.identity, 'executed_decisions': 0, 'learning_enabled_decisions': 0,
                     'selected_transitions': 0, 'intentionally_unsampled_transitions': 0,
                     'learning_disabled_decisions': 0, 'pending': None,
                     'pending_global_index': None, 'last_transition_key': None,
                     'last_transition_sha256': None}
        if self.path.exists():
            loaded = json.loads(self.path.read_text())
            if any(loaded.get(k) != v for k, v in self.identity.items()):
                raise ValueError('Collection state belongs to a different wave or stride')
            for key in ('executed_decisions', 'learning_enabled_decisions', 'selected_transitions',
                        'intentionally_unsampled_transitions', 'learning_disabled_decisions'):
                if type(loaded.get(key)) is not int or loaded[key] < 0:
                    raise ValueError('Invalid durable collection counter')
            if (loaded['learning_enabled_decisions'] != loaded['selected_transitions']+loaded['intentionally_unsampled_transitions']
                    or loaded['executed_decisions'] != loaded['learning_enabled_decisions']+loaded['learning_disabled_decisions']):
                raise ValueError('Collection counter identities differ')
            if loaded.get('pending') is not None:
                from .practice import validate_transition
                validate_transition(loaded['pending'])
                index = loaded.get('pending_global_index')
                if type(index) is not int or not 0 <= index < loaded['executed_decisions'] or index % self.stride:
                    raise ValueError('Pending record has an invalid selected index')
            self.data = loaded

    @property
    def pending(self):
        return copy.deepcopy(self.data['pending'])

    def _write(self, value):
        from .practice import atomic_json
        atomic_json(self.path, value)
        self.data = value

    def observe(self, record, *, learning_enabled):
        """Called only after actual execution/acknowledgment, before any offer."""
        from .practice import validate_transition
        if type(learning_enabled) is not bool:
            raise ValueError('Explicit learning-enabled boolean required')
        row = validate_transition(record)
        key = digest(canonical([row['episode_id'], row['step_index']]))
        sha = digest(canonical(row))
        if key == self.data['last_transition_key']:
            if sha != self.data['last_transition_sha256']:
                raise ValueError('A retried executed transition changed')
            return self.data['pending'] == row
        index = self.data['executed_decisions']
        selected = learning_enabled and index % self.stride == 0
        if selected and self.data['pending'] is not None:
            raise RuntimeError('Selected pending evidence would be overwritten')
        value = copy.deepcopy(self.data)
        value['executed_decisions'] += 1
        value['last_transition_key'], value['last_transition_sha256'] = key, sha
        if learning_enabled:
            value['learning_enabled_decisions'] += 1
            value['selected_transitions' if selected else 'intentionally_unsampled_transitions'] += 1
        else:
            value['learning_disabled_decisions'] += 1
        if selected:
            value['pending'], value['pending_global_index'] = row, index
        self._write(value)
        return selected

    def acknowledge(self, record):
        """Clear only after the learner confirms durable, deduplicated custody."""
        if self.data['pending'] != record:
            raise ValueError('Learner acknowledgment differs from selected pending record')
        value = copy.deepcopy(self.data)
        value['pending'], value['pending_global_index'] = None, None
        self._write(value)

    def status(self):
        return {'collection_stride': self.stride,
                **{k: self.data[k] for k in ('executed_decisions', 'learning_enabled_decisions',
                    'selected_transitions', 'intentionally_unsampled_transitions', 'learning_disabled_decisions')},
                'collection_pending_global_index': self.data['pending_global_index']}
