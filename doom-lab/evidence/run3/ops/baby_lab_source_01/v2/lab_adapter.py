"""Demo Lab bridge: a frozen, qualified actor and an independent learner."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import threading
import time

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from models import load_bundle, encode
from exporter import atomic_json
from basic_env import engine, sha
from cadence import Brain

SCHEMA = 'cadence-doom-lab-v2/1'


def validate_bundle(data):
    if not isinstance(data, dict) or data.get('schema') != SCHEMA:
        raise ValueError('Not a Cadence Doom v2 bundle')
    with tempfile.TemporaryDirectory(prefix='doom-bundle-check-') as folder:
        path = Path(folder) / 'bundle.json'
        atomic_json(path, data)
        brain, normalizer, metadata = load_bundle(path)
    return brain, normalizer, metadata


def buttons_for(action):
    """Six Basic actions displayed in the existing eight-button interface."""
    buttons = [0] * 8
    buttons[5] = int(action in (1, 4))
    buttons[6] = int(action in (2, 5))
    buttons[3] = int(action in (3, 4, 5))
    return buttons


class V2Adapter:
    def __init__(self, path):
        self.path = Path(path)
        self.bundle = json.loads(self.path.read_text())
        self.base_digest = self.bundle['metadata']['hashes']['checkpoint_sha256']
        selected = self.path
        active = self.path.parent/'active_champion.json'
        if active.is_file():
            saved = json.loads(active.read_text())
            if saved['metadata'].get('base_checkpoint_sha256') != self.base_digest:
                raise ValueError('Saved champion belongs to a different imported founder')
            self.bundle = saved
            selected = active
        self.brain, self.normalizer, self.metadata = load_bundle(selected)
        # Native binaries differ across platforms. The actual task assets must
        # match the exporter; local replay verifies each practice trajectory.
        identity = self.metadata.get('engine_identity')
        if identity:
            runtime = engine()
            if identity.get('version') != runtime.__version__:
                raise ValueError('Bundle engine version differs from the runtime')
            for asset in ('scenarios/basic.cfg', 'scenarios/basic.wad', 'freedoom2.wad'):
                expected = identity.get('files', {}).get(asset, {}).get('sha256')
                if not expected or sha(Path(runtime.root_path)/asset) != expected:
                    raise ValueError('Bundle Basic task asset differs from runtime: ' + asset)
        self.lock = threading.RLock()
        self.learner = None
        self._feedback_pool = None
        self._cleanup_thread = None
        self.feedback_workers = 1
        self.version = int(self.metadata.get('online_version', 0))
        self.version_offset = self.version
        self.enabled = False
        self.error = None
        pending_path = self.path.parent/'pending_transition.json'
        self.pending = json.loads(pending_path.read_text()) if pending_path.is_file() else None
        self._closed = False
        self._pending_promotion = None
        self.last_episode = None
        self._analyze()

    def _analyze(self):
        info = self.brain.inspect()
        self.layout_meta = [dict(name=p['name'], role=p['role'],
                                start=p['indices'][0], count=p['patches'])
                            for p in info['populations']]
        self.model_info = dict(patches=info['patches'], edges=info['connections'],
                               fingerprint=info['fingerprint'][:12] + '-v' + str(self.version), scenario='basic',
                               champion=self.version, schema=SCHEMA)

    def graph_payload(self):
        with self.lock:
            edges = list(enumerate(self.brain.graph.edges))
            if len(edges) > 1400:
                edges = sorted(random.Random(7).sample(edges, 1400))
            kinds = {'input': 0, 'state': 1, 'residual': 2}
            weights = self.brain.weights
            return dict(n_periphery=225, n_fovea=21, periphery_shape=[15, 15],
                        fovea_shape=[3, 7], fovea_label='action history',
                        populations=self.layout_meta, motor=6,
                        edges=[[kinds[k], s, t, round(weights[i], 3)]
                               for i, (k, s, t) in edges])

    def predict(self, raw, prefix):
        inputs = encode(raw, prefix, self.normalizer)
        started = time.monotonic()
        with self.lock:
            result = self.brain.settle({'sensors': inputs.tolist()}, budget=512)
            version = self.version
        scores = result['outputs']['utility']
        qualified = bool(result['qualified']) and np.isfinite(scores).all()
        action = int(np.argmax(scores)) if qualified else None
        return dict(action=action, buttons=buttons_for(action),
                    ui_buttons=[int(i == action) for i in range(6)], scores=list(scores),
                    qualified=bool(qualified), sweeps=result['sweeps'],
                    state=list(result['state']), errors=list(result['errors']),
                    energy=result['energy'], stationarity=result['stationarity'],
                    retina_p=inputs[:225].tolist(), retina_f=inputs[225:].tolist(),
                    inputs=inputs.tolist(), champion=version,
                    query_seconds=time.monotonic()-started)

    def _worker_status(self):
        base = self.learner.status() if self.learner else {}
        if self.learner and (not base.get('enabled', False) or base.get('stopped', False)):
            # A refused admission, exhausted journal or failed worker can pause
            # itself. Report that pause and stop treating its queue as live.
            self.enabled = False
        return base

    def set_enabled(self, enabled):
        if self._closed:
            raise ValueError('Model has been unloaded')
        requested = bool(enabled)
        if requested and self.learner is None:
            workers = int(os.environ.get('DOOM_FEEDBACK_WORKERS', '1'))
            if not 1 <= workers <= 6:
                raise ValueError('DOOM_FEEDBACK_WORKERS must be an integer from 1 to 6')
            from online import OnlineLearner
            learner = OnlineLearner.from_bundle(
                self.bundle, journal_path=self.path.parent/'online.jsonl',
                bundle_dir=self.path.parent)
            try:
                if workers > 1:
                    from parallel_feedback import ParallelBranchTeacher
                    pool = ParallelBranchTeacher(self.normalizer, workers=workers)
                    # The new worker starts paused: no transition can call its
                    # teacher until set_enabled below completes this handoff.
                    learner.teacher = pool
                    self._feedback_pool = pool
            except BaseException:
                learner.close(wait=False)
                raise
            self.learner = learner
            self.feedback_workers = workers
        accepted = self.learner.set_enabled(requested) if self.learner else True
        self.enabled = requested and accepted is not False
        base = self._worker_status()
        if requested and not self.enabled:
            self.error = base.get('error') or base.get('last_error') or 'Learner is stopped; reload after resolving its failure'
            raise RuntimeError(self.error)
        if requested:
            self.error = None

    def flush_pending(self):
        self._worker_status()
        if self.pending is None or not self.enabled:
            return True
        if self.learner is not None and self.learner.submit_transition(self.pending):
            self.pending = None
            (self.path.parent/'pending_transition.json').unlink(missing_ok=True)
            return True
        self._worker_status()
        return not self.enabled

    def acknowledge(self, record):
        """Never replace an unconsumed transition: caller pauses on backpressure."""
        if not record.get('learning_enabled', self.enabled):
            return True
        if self.pending is not None:
            raise RuntimeError('Unconsumed transition would be overwritten')
        if self.learner.submit_transition(record):
            return True
        self.pending = copy.deepcopy(record)
        atomic_json(self.path.parent/'pending_transition.json', self.pending)
        self._worker_status()
        return False

    def episode_boundary(self):
        if self.learner is None:
            return False
        if self._pending_promotion is None:
            self._pending_promotion = self.learner.take_promotion()
        promoted = self._pending_promotion
        if not promoted:
            return False
        replacement = Brain.from_snapshot(promoted['snapshot'], device='cpu')
        with self.lock:
            version = self.version_offset + promoted['version']
            bundle = copy.deepcopy(self.bundle)
            bundle['snapshot'] = promoted['snapshot']
            bundle['metadata']['hashes']['checkpoint_sha256'] = hashlib.sha256(
                promoted['snapshot'].encode()).hexdigest()
            bundle['metadata']['online_version'] = version
            bundle['metadata']['base_checkpoint_sha256'] = self.base_digest
            # Persist first. A failed write leaves the executing actor unchanged
            # and keeps this exact qualified proposal available for retry.
            atomic_json(self.path.parent/'active_champion.json', bundle)
            self.brain, self.version, self.bundle = replacement, version, bundle
            self.metadata = bundle['metadata']
            self._analyze()
            self._pending_promotion = None
        return True

    def rollback(self):
        return bool(self.learner and self.learner.rollback())

    def status(self):
        base = self._worker_status()
        return {**base, 'available': True, 'enabled': self.enabled,
                'champion': self.version, 'feedback_workers': self.feedback_workers,
                'pending_transition': self.pending is not None,
                'error': base.get('error') or self.error, 'last_episode': self.last_episode}

    def export_bundle(self):
        with self.lock:
            data = copy.deepcopy(self.bundle)
        data['model_id'] = self.metadata['model_id']
        data['exported'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        return data

    def close(self):
        self._closed = True
        self.enabled = False
        if self.learner:
            self.learner.close(wait=False)
        if self._feedback_pool is not None and self._cleanup_thread is None:
            learner, pool = self.learner, self._feedback_pool
            def finish_feedback():
                # Never terminate the pool during an acknowledged feedback call.
                # This cleanup thread, rather than the UI caller, waits for it.
                try:
                    if learner is not None:
                        learner.close(wait=True)
                finally:
                    pool.close(wait=True)
            self._cleanup_thread = threading.Thread(target=finish_feedback,
                name='doom-feedback-cleanup', daemon=False)
            self._cleanup_thread.start()
