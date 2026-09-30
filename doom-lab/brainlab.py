"""Single-version model registry; one game owner publishes qualified actors."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import threading

from v1.brain import BUNDLE_SCHEMA, write_bundle
from v1.interface import ACTION_NAMES
from v1.practice import atomic_json
from v1.runtime import Adapter, validate_deployment

LAB = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get('DOOM_LAB_DATA', LAB/'data')).resolve()
MODELS_DIR = DATA_DIR/'models'
POINTER = DATA_DIR/'current_model.json'


class Student:
    """Registry and actor ownership only; all learning belongs to PracticeLearner."""
    def __init__(self, *, data_dir=None):
        self.data_dir = Path(data_dir or DATA_DIR).resolve()
        self.models_dir = self.data_dir/'models'
        self.pointer = self.data_dir/'current_model.json'
        self.lock = threading.RLock()
        self.adapter = None
        self.generation = 0
        self.model_id = None
        self.swap_error = None
        self._swap_request = None
        self._swapping = False
        if not self.pointer.is_file():
            raise FileNotFoundError('No active model. Run python -m v1.deployment prepare before starting the Lab.')
        model_id = json.loads(self.pointer.read_text())['id']
        if not self.request_swap(model_id):
            raise ValueError('The saved model is absent from the v1 registry: '+str(model_id))
        self.apply_swap()
        if self.adapter is None:
            raise ValueError('Cannot load the saved model: '+str(self.swap_error))

    @property
    def layout_meta(self):
        return self.adapter.layout_meta if self.adapter else []

    def scan_models(self):
        rows = []
        for path in sorted(self.models_dir.glob('*/bundle.json')):
            if path.is_symlink():
                continue
            try:
                bundle = json.loads(path.read_text())
                if bundle.get('schema') != BUNDLE_SCHEMA:
                    continue
                meta = bundle['metadata']
                task = meta.get('deployment_task', 'unknown')
                if isinstance(task, dict):
                    task = task.get('task_id', 'unknown')
                rows.append({'id': path.parent.name, 'label': meta.get('label', bundle['model_id']),
                    'checkpoint_sha256': bundle['hashes']['checkpoint_sha256'],
                    'scenario': task, 'validation': meta.get('deployment_validation', {}).get('status', 'unknown'),
                    'role': meta.get('role', 'imported')})
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return rows

    def request_swap(self, model_id):
        with self.lock:
            if model_id not in {row['id'] for row in self.scan_models()}:
                return False
            self._swap_request = model_id
            self.swap_error = None
            return True

    def apply_swap(self):
        """Called only by the game owner, after its current session has ended."""
        with self.lock:
            model_id = self._swap_request
            if model_id is None:
                return False
            self._swap_request = None
            self._swapping = True
        replacement = None
        try:
            replacement = Adapter(self.models_dir/model_id/'bundle.json')
            # Publish the pointer first. A failed write preserves the old actor.
            atomic_json(self.pointer, {'id': model_id})
            with self.lock:
                previous = self.adapter
                self.adapter = replacement
                self.model_id = model_id
                self.generation += 1
                self.swap_error = None
            if previous:
                previous.close()
            return True
        except Exception as error:
            if replacement:
                replacement.close()
            self.swap_error = str(error)
            return False
        finally:
            self._swapping = False

    def import_bundle(self, name, data):
        """Validate before writing; imports never activate or enable learning."""
        _, bundle = validate_deployment(data)
        model_id = ''.join(c if c.isascii() and (c.isalnum() or c in '-_') else '-' for c in str(name)).strip('-')[:80] or 'imported'
        with self.lock:
            base, number = model_id, 1
            while (self.models_dir/model_id).exists():
                model_id = f'{base}-{number}'; number += 1
            write_bundle(self.models_dir/model_id/'bundle.json', bundle)
        return model_id

    def export_bundle(self):
        with self.lock:
            return self.adapter.export_bundle()

    def graph_payload(self):
        return self.adapter.graph_payload()

    def save(self):
        with self.lock:
            bundle = self.export_bundle()
            model_id = self.model_id
            path = self.models_dir/model_id/'saved_export.json'
            write_bundle(path, bundle)
            return {'model_id': model_id, 'checkpoint_sha256': bundle['hashes']['checkpoint_sha256'],
                    'path': str(path), 'learning_state': 'durably owned by the practice worker'}

    def close(self):
        if self.adapter:
            self.adapter.close()
        return self.save() if self.adapter else {'saved': False}
