"""Opt-in Lab bridge: qualified visual actor, separately owned native learner.

Practice is an additional explicit opt-in. No privileged policy teacher ever
chooses browser actions; the actor always uses its current qualified patches.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import platform
import random
import threading
import time

from .brain import Actor, BUNDLE_SCHEMA, load_bundle, write_bundle
from .interface import ACTION_NAMES, REPEAT_TICS, features, canonical, digest
from .tasks import DoomEnv, get_task, sha_file, task_identity, vizdoom_module


def enabled():
    return os.environ.get('DOOM_LAB_ENABLE_V3') == '1'


def platform_identity():
    root = Path(vizdoom_module().__file__).parent
    binary = root/'vizdoom'
    if not binary.is_file():
        raise FileNotFoundError('Cannot identify the native Doom engine executable')
    return {'system': platform.system(), 'machine': platform.machine(),
            'engine_binary_sha256': sha_file(binary)}


def validate_deployment(data):
    """Task identity and transport metadata are not gameplay revalidation."""
    if not enabled():
        raise ValueError('Full-game bundle support is not enabled on this Lab process')
    _, bundle = load_bundle(data, device='python')
    metadata = bundle.get('metadata', {})
    if 'deployment_task' not in metadata or 'deployment_identity' not in metadata:
        raise ValueError('A full-game bundle must explicitly bind its deployment task and native identity')
    task = get_task(metadata['deployment_task'])
    if task.split in ('heldout', 'reserved_extension'):
        raise ValueError('Held-out tasks belong to the frozen evaluator, not browser practice')
    local_task = task_identity(task)
    if metadata['deployment_identity'] != local_task:
        raise ValueError('Deployment task/engine/WAD identity differs from this runtime')
    source, target = metadata.get('source_platform'), platform_identity()
    if not isinstance(source, dict) or set(source) != set(target):
        raise ValueError('Bundle must declare its source platform and native executable hash')
    validation = metadata.get('deployment_validation', {})
    if (validation.get('source_platform') != source or validation.get('target_platform') != target
            or validation.get('checkpoint_sha256') != bundle['hashes']['checkpoint_sha256']):
        raise ValueError('Explicit platform-specific deployment evaluation metadata is required')
    status = validation.get('status')
    if status == 'not_evaluated':
        if os.environ.get('DOOM_LAB_PORT') != '8667':
            raise ValueError('Unevaluated full-game actors are restricted to staging port8667')
    elif status == 'passed':
        receipt = validation.get('receipt_sha256', '')
        if len(receipt) != 64 or any(c not in '0123456789abcdef' for c in receipt):
            raise ValueError('A passed local evaluation must identify its retained receipt')
    else:
        raise ValueError('Deployment validation must explicitly be passed or not_evaluated')
    return task, bundle


def prepare_staging_bundle(data, task, *, source_platform=None):
    """Explicitly mark local staging as unvalidated; never manufacture a pass."""
    _, bundle = load_bundle(data, device='python')
    identity = task_identity(task)
    metadata = bundle.setdefault('metadata', {})
    source = source_platform or metadata.get('source_platform')
    if source is None:
        raise ValueError('Declare the actual training/source platform for staging transport')
    metadata.update(deployment_task=identity['task'], deployment_identity=identity,
                    source_platform=copy.deepcopy(source), deployment_validation={
                        'status': 'not_evaluated', 'source_platform': copy.deepcopy(source),
                        'target_platform': platform_identity(),
                        'checkpoint_sha256': bundle['hashes']['checkpoint_sha256']})
    return bundle


class V3Adapter:
    """The historical Student.v2 slot hosts either portable adapter version."""
    def __init__(self, path):
        self.path = Path(path)
        self.task, self.bundle = validate_deployment(json.loads(self.path.read_text()))
        self.founder_bundle = copy.deepcopy(self.bundle)
        self.founder_hash = self.bundle['hashes']['checkpoint_sha256']
        active = self.path.parent/'active_champion.json'
        if active.is_file():
            _, saved = validate_deployment(json.loads(active.read_text()))
            if saved.get('metadata', {}).get('base_checkpoint_sha256') != self.founder_hash:
                raise ValueError('Restored champion belongs to a different frozen founder')
            for field in ('contract', 'genome', 'normalization'):
                if saved[field] != self.bundle[field]:
                    raise ValueError('Restored champion changes the founder '+field)
            self.bundle = saved
        self.actor = Actor(self.bundle, device='cpu')
        self.lock = threading.RLock()
        self.learner = None
        self.enabled = False
        self._pending_promotion = None
        pending = self.path.parent/'pending_transition.json'
        self.pending = json.loads(pending.read_text()) if pending.is_file() else None
        self.error = None
        self.last_episode = None
        self._closed = False
        self.version = int(self.bundle.get('metadata', {}).get('online_version', 0))
        self.version_offset = self.version
        self._analyze()

    def _analyze(self):
        info = self.actor.brain.inspect()
        self.layout_meta = [dict(name=p['name'], role=p['role'], start=p['indices'][0], count=p['patches'])
                            for p in info['populations']]
        self.model_info = {'patches': info['patches'], 'edges': info['connections'],
                           'fingerprint': self.actor.checkpoint_hash[:12],
                           'topology_fingerprint': info['fingerprint'][:12], 'schema': BUNDLE_SCHEMA,
                           'scenario': self.task.task_id, 'champion': self.version,
                           'deployment_validation': self.bundle['metadata']['deployment_validation']['status']}

    def _practice_available(self):
        metadata = self.founder_bundle.get('metadata', {})
        rows = metadata.get('seed_replay')
        return (os.environ.get('DOOM_LAB_V3_PRACTICE') == '1' and self.task.task_id == 'basic'
                and isinstance(rows, list) and bool(rows)
                and metadata.get('seed_replay_sha256') == digest(canonical(rows)))

    def _worker_status(self):
        base = self.learner.status() if self.learner else {}
        if self.learner and not base.get('enabled'):
            self.enabled = False
        return base

    def status(self):
        base = self._worker_status()
        return {**base, 'available': self._practice_available(), 'enabled': self.enabled,
                'phase': base.get('phase', 'frozen full-game actor'),
                'queue_depth': base.get('queue', 0), 'accepted_updates': base.get('updates', 0),
                'pending_transition': self.pending is not None,
                'champion': self.version, 'champion_sha256': self.actor.checkpoint_hash,
                'error': base.get('error') or self.error, 'last_episode': self.last_episode,
                'deployment_validation': self.model_info['deployment_validation'],
                'rollback_available': base.get('rollback_available', False)}

    def set_enabled(self, value):
        if self._closed:
            raise ValueError('Model has been unloaded')
        requested = bool(value)
        if requested and not self._practice_available():
            raise ValueError('Full-game online learning is not yet attached: Basic practice opt-in and verified frozen replay are required')
        if requested and self.learner is None:
            from .practice import PracticeLearner, PracticeConfig
            config = PracticeConfig(gate_tasks=('basic',),
                gate_workers=int(os.environ.get('DOOM_PRACTICE_GATE_WORKERS', '2')),
                feedback_workers=int(os.environ.get('DOOM_FEEDBACK_WORKERS', '6')),
                max_journal_bytes=int(os.environ.get('DOOM_PRACTICE_JOURNAL_MB', '32'))*1024*1024)
            self.learner = PracticeLearner.from_bundle(self.founder_bundle,
                initial_bundle=self.bundle, journal_path=self.path.parent/'practice.jsonl', config=config)
        if self._closed:
            if self.learner:
                self.learner.close(wait=False)
            raise ValueError('Model was unloaded while its practice worker was starting')
        accepted = self.learner.set_enabled(requested) if self.learner else False
        self.enabled = requested and accepted is True
        if requested and not self.enabled:
            self.error = self._worker_status().get('error') or 'Practice worker refused to start'
            raise RuntimeError(self.error)
        if requested:
            self.error = None

    def flush_pending(self):
        self._worker_status()
        if self.pending is None or not self.enabled:
            return True
        if self.learner.submit_transition(self.pending):
            self.pending = None
            (self.path.parent/'pending_transition.json').unlink(missing_ok=True)
            return True
        self._worker_status()
        return not self.enabled

    def record_transition(self, record):
        """Persist before handing off; queue backpressure may never replace evidence."""
        from .practice import atomic_json, validate_transition
        if self.pending is not None:
            raise RuntimeError('An unconsumed native transition would be overwritten')
        record = validate_transition(record)
        atomic_json(self.path.parent/'pending_transition.json', record)
        self.pending = record
        return self.flush_pending()

    def episode_boundary(self):
        if self.learner is None:
            return False
        if self._pending_promotion is None:
            self._pending_promotion = self.learner.take_promotion()
        proposal = self._pending_promotion
        if not proposal:
            return False
        bundle = copy.deepcopy(proposal['bundle'])
        checkpoint = bundle['hashes']['checkpoint_sha256']
        gate = proposal['gate']
        if gate.get('rollback'):
            candidates = [self.founder_bundle]
            previous = self.path.parent/'previous_champion.json'
            if previous.is_file():
                candidates.append(json.loads(previous.read_text()))
            known = next((b for b in candidates if b['hashes']['checkpoint_sha256'] == checkpoint), None)
            if known is None:
                raise ValueError('Rollback did not identify a previously deployed champion')
            bundle = copy.deepcopy(known)
        else:
            if (gate.get('promote') is not True or gate.get('candidate_checkpoint') != checkpoint
                    or digest(canonical(gate)) != proposal.get('gate_sha256')):
                raise ValueError('Promotion lacks its exact qualified native gate receipt')
            platform = platform_identity()
            bundle['metadata'].update(source_platform=platform,
                deployment_task=vars(self.task), deployment_identity=task_identity(self.task),
                deployment_validation={'status': 'passed', 'source_platform': platform,
                    'target_platform': platform, 'checkpoint_sha256': checkpoint,
                    'receipt_sha256': proposal['gate_sha256'], 'scope': 'repeated Basic development gate'})
        version = self.version_offset+proposal['version']
        bundle['metadata'].update(online_version=version, base_checkpoint_sha256=self.founder_hash)
        validate_deployment(bundle)
        replacement = Actor(bundle, device='cpu')
        with self.lock:
            # A failed publication leaves the current actor and proposal intact.
            write_bundle(self.path.parent/'previous_champion.json', self.bundle)
            write_bundle(self.path.parent/'active_champion.json', bundle)
            self.bundle, self.actor, self.version = bundle, replacement, version
            self._analyze()
            self._pending_promotion = None
        return True

    def rollback(self):
        return bool(self.learner and self.learner.rollback())

    def close(self):
        self._closed = True
        self.enabled = False
        if self.learner:
            self.learner.close(wait=False)

    def export_bundle(self):
        with self.lock:
            return copy.deepcopy(self.bundle)

    def graph_payload(self):
        with self.lock:
            brain = self.actor.brain
            indices = list(range(len(brain.graph.edges)))
            if len(indices) > 1400:
                rng = random.Random(7)
                readback = [i for i in indices if brain.graph.edges[i][0] != 'input']
                sensory = [i for i in indices if brain.graph.edges[i][0] == 'input']
                recursive_sample = rng.sample(readback, min(len(readback), 700))
                indices = sorted(recursive_sample+rng.sample(sensory, 1400-len(recursive_sample)))
            kinds = {'input': 0, 'state': 1, 'residual': 2}
            return {'n_periphery': 640, 'n_fovea': 1380, 'periphery_shape': [20, 32],
                    'fovea_shape': [30, 46], 'fovea_label': 'fovea + visual/action memory',
                    'populations': self.layout_meta, 'motor': 20, 'action_names': list(ACTION_NAMES),
                    'total_edges': len(brain.graph.edges), 'sampled_edges': len(indices),
                    'edge_sample': 'readback-stratified deterministic sample, seed7, at most1400 edges',
                    'edges': [[kinds[brain.graph.edges[i][0]], *brain.graph.edges[i][1:], round(brain.weights[i], 3)]
                              for i in indices]}

    def run_session(self, lab):
        """Execute only current, qualified proposals and acknowledge actual tics."""
        if lab.mode != 'student':
            raise ValueError('The v3 runtime supports the qualified STUDENT actor only')
        generation = lab.student.generation
        env = None
        queries = qualified_queries = 0
        prefix_actions, prefix_outcomes = [], []
        cutoff = None
        def finish(reason=None):
            if env is not None:
                self.last_episode = {**env.outcome(external_cutoff=reason),
                    'session_id': lab.session_id, 'queries': queries,
                    'qualified_queries': qualified_queries, 'fallback_actions': 0,
                    'policy_checkpoint_sha256': self.actor.checkpoint_hash,
                    'behavior_source': 'qualified_cadence_actor', 'cutoff_reason': reason}
        try:
            while (not lab._stop.is_set() and not self._closed and lab.mode == 'student'
                   and lab.student.v2 is self and lab.student.generation == generation):
                if lab.student._swapping or lab.student._swap_request:
                    cutoff = 'model_change'; break
                if not self.flush_pending():
                    lab._stop.wait(.1)
                    continue
                if env is None or env.finished or lab.reset_request:
                    if env is not None:
                        finish(None if env.finished else 'reset')
                        env.close()
                    self.episode_boundary()
                    lab.reset_request = False
                    self.actor.reset()
                    env = DoomEnv(self.task, lab.rng.randrange(800000000, 900000000), teacher=False)
                    lab.episode += 1
                    queries = qualified_queries = 0
                    prefix_actions, prefix_outcomes = [], []
                learning_enabled = self.enabled
                decision_started = time.monotonic()
                raw = env.observe()
                visible = features(raw)
                lab._publish_frame(raw, (visible['periphery']*1.2-.6).reshape(20, 32),
                                   (visible['fovea']*1.2-.6).reshape(12, 32))
                with self.lock:
                    decision = self.actor.choose(raw)
                queries += 1
                qualified_queries += int(decision['qualified'])
                result = decision['result']
                lab.shadow_view = {'qualified': decision['qualified'], 'sweeps': result['sweeps'],
                    'state': list(result['state']), 'errors': list(result['errors']),
                    'ui_buttons': [int(i == decision['action']) for i in range(20)],
                    'buttons': decision['buttons'], 'retina_p': decision['inputs']['periphery'],
                    'retina_f': decision['inputs']['fovea']+decision['inputs']['visual_history']+decision['inputs']['executed_action_history'],
                    'action': decision['action'], 'checkpoint_sha256': self.actor.checkpoint_hash,
                    'query_seconds': decision['query_seconds']}
                if (lab.mode != 'student' or lab.reset_request or lab.student.v2 is not self
                        or lab.student._swapping or lab.student._swap_request
                        or lab.student.generation != generation or self._closed or lab._stop.is_set()):
                    self.actor.reset()  # discard an unexecuted proposal, never commit it
                    cutoff = 'interrupted_before_execution'; break
                if not decision['qualified']:
                    self.error = 'Query refused; no action executed'
                    cutoff = 'query_refused'
                    lab.set_mode('idle'); break
                self.error = None
                transition = env.step(decision['action'], tics=REPEAT_TICS)
                with self.lock:
                    self.actor.acknowledge(raw, decision['action'], transition['tics'])
                if learning_enabled:
                    self.record_transition({'task': vars(self.task), 'seed': env.seed,
                        'episode_id': f'{lab.session_id}:{generation}:{lab.episode}:{env.seed}',
                        'step_index': len(prefix_actions), 'prefix_actions': list(prefix_actions),
                        'prefix_outcomes': copy.deepcopy(prefix_outcomes), 'raw_sha256': decision['raw_sha256'],
                        'inputs': decision['inputs'], 'executed_action': decision['action'], 'transition': transition,
                        'policy_checkpoint_sha256': decision['checkpoint_sha256'],
                        'qualified': True, 'fallback': False, 'behavior_source': 'autonomous'})
                prefix_actions.append(decision['action'])
                prefix_outcomes.append(transition)
                facts = env.last_facts  # HUD/evidence only; never supplied to Actor
                lab.game_stats = {'health': round(facts['health']), 'ammo': round(facts['selected_weapon_ammo']),
                                  'kills': int(facts['killcount']), 'reward': env.total_reward,
                                  'scenario': self.task.task_id, 'qualified': True,
                                  'seed': env.seed, 'native_exit': bool(env.finished and not facts['dead'] and not facts['timeout']
                                                                     and self.task.objective == 'native_exit')}
                # Include perception/query/engine work in the pacing interval.
                # Solver budget is not a deadline: overrun is exposed as latency.
                lab._stop.wait(max(0, transition['tics']/35-(time.monotonic()-decision_started)))
        finally:
            if env is not None:
                finish(None if env.finished else cutoff or ('paused' if lab.mode == 'idle' else 'interrupted'))
                env.close()
