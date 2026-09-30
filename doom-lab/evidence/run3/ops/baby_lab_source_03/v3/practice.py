"""Autonomous native-feedback policy improvement through public Cadence repair.

The twenty outputs are centered preferences, never Q values or expected returns.
Only the worker owns the mutable candidate. Executed observations are durably
queued; complete native interventions supply estimated preferences. Promotion
requires qualified native gameplay and retention against both founder and the
current champion. Repeated development gates are selection, not confirmation.
"""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
import fcntl
import gzip
import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
              'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'

import numpy as np

from .brain import Actor, load_bundle, make_bundle, write_bundle
from .interface import ACTION_BUTTONS, ACTION_NAMES, OUTPUT_NAME, PORT_SHAPES, canonical, digest
from .native_feedback import NativeFeedbackPool, target_contract as native_contract, validate_record
from .tasks import DoomEnv, get_task, sha_file, task_identity
from v2.journal import append_record


PREFERENCE_SCHEMA = 'doom-v3-native-ranked-preference/1'


def copied(value):
    return json.loads(canonical(value))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w') as stream:
        stream.write(canonical(value) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def preference_target(native_values, *, tie_tolerance=1e-12):
    """A probability over the best native actions; all ties carry no lesson."""
    values = np.asarray(native_values, dtype=float)
    if values.shape != (20,) or not np.isfinite(values).all():
        raise ValueError('Expected twenty finite native intervention values')
    if not np.isfinite(tie_tolerance) or tie_tolerance < 0:
        raise ValueError('Tie tolerance must be finite and nonnegative')
    winners = np.flatnonzero(values >= values.max() - tie_tolerance)
    if len(winners) == 20:
        return None
    probability = np.zeros(20)
    probability[winners] = 1 / len(winners)
    return {'targets': (.8 * (probability - .05)).tolist(),
            'best_actions': winners.tolist(), 'native_values': values.tolist()}


def preference_contract(founder, *, tie_tolerance=1e-12):
    return {'schema': PREFERENCE_SCHEMA, 'meaning': 'centered action preference',
            'transform': '0.8 * (uniform_probability_over_best_native_actions - 0.05)',
            'tie_tolerance': tie_tolerance, 'all_actions_tied': 'skip context',
            'source': 'estimate', 'is_return_or_Q': False,
            'new_label_source': 'native simulator interventions on qualified executed autonomous contexts',
            'initial_action_tics': 4, 'continuation': 'fixed founder qualified Cadence actor',
            'continuation_checkpoint_sha256': founder['hashes']['checkpoint_sha256'],
            'seed_replay': 'finite frozen bootstrap preferences; source and row identities retained',
            'deployment': 'argmax of twenty unclamped settled action-score patches'}


def validate_transition(record):
    row = validate_record(record)
    if not isinstance(row['episode_id'], str) or not row['episode_id']:
        raise ValueError('episode_id must be nonempty text')
    if not 0 <= row['seed'] < 2**32:
        raise ValueError('Native seed must be uint32')
    elapsed = None
    for index, transition in enumerate(row['prefix_outcomes'] + [row['transition']]):
        if type(transition['requested_tics']) is not int or transition['requested_tics'] != 4:
            raise ValueError('Autonomous actor requests exactly four native tics')
        if any(type(transition[k]) is not bool for k in ('terminal', 'dead', 'timeout')):
            raise ValueError('Native terminal/dead/timeout flags must be booleans')
        if (transition['dead'] or transition['timeout']) and not transition['terminal']:
            raise ValueError('Dead and native task timeout outcomes must be terminal')
        if transition['tics'] != 4 and not transition['terminal']:
            raise ValueError('A short action is legal only at a native terminal')
        action = (row['prefix_actions'] + [row['executed_action']])[index]
        if transition['buttons'] != list(ACTION_BUTTONS[action]):
            raise ValueError('Physical buttons do not match the executed action')
        tic = transition['episode_tic']
        terminal_reset = transition['terminal'] and tic == 0
        if type(tic) is not int or (elapsed is not None and tic != elapsed + transition['tics'] and not terminal_reset):
            raise ValueError('Native episode time is not aligned to actual action tics')
        elapsed = tic
    # External collector cutoff is not a native terminal and supplies no target.
    return row


def _inputs(value):
    if set(value) != set(PORT_SHAPES):
        raise ValueError('Replay requires the complete four-port observation')
    result = {}
    for name, width in PORT_SHAPES.items():
        x = np.asarray(value[name], dtype=float)
        if x.shape != (width,) or not np.isfinite(x).all():
            raise ValueError('Invalid replay port: ' + name)
        result[name] = x.tolist()
    return result


def validate_seed_replay(rows):
    result, seen = [], set()
    for row in copied(rows):
        if (row.get('source') != 'bootstrap_seed' or not row.get('row_id')
                or row.get('split') != 'training' or not row.get('source_sha256')):
            raise ValueError('Frozen bootstrap replay needs explicit source and row custody')
        sha = row['source_sha256']
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('Bootstrap replay source hash is malformed')
        if row['row_id'] in seen:
            raise ValueError('Duplicate bootstrap replay row')
        seen.add(row['row_id'])
        x = _inputs(row['inputs'])
        target = np.asarray(row['targets'], dtype=float)
        # A finite teacher demonstration is one selected action with .8 margin.
        if target.shape != (20,) or not np.isfinite(target).all():
            raise ValueError('Bootstrap replay needs twenty finite preferences')
        expected = np.full(20, -.04)
        expected[int(np.argmax(target))] = .76
        if target.shape != (20,) or not np.allclose(target, expected, atol=1e-12, rtol=0):
            raise ValueError('Bootstrap replay must use the centered preference convention')
        result.append({**row, 'inputs': x, 'targets': target.tolist()})
    return result


def attach_seed_replay(bundle, rows):
    result = copied(bundle)
    values = validate_seed_replay(rows)
    result.setdefault('metadata', {})['seed_replay'] = values
    result['metadata']['seed_replay_sha256'] = digest(canonical(values))
    return result


def seed_replay_from_dataset(path, bundle, *, max_rows=192):
    """Read only the frozen training split, balanced by task/action, no new labels."""
    from .training import metric_ids, unpack
    path = Path(path)
    receipt = json.loads((path / 'dataset.json').read_text())
    if (receipt['normalizer'] != bundle['normalization'] or receipt['contract'] != bundle['contract']
            or sha_file(path / 'inputs.npy') != receipt['inputs_sha256']
            or sha_file(path / 'rows.npz') != receipt['rows_sha256']):
        raise ValueError('Bootstrap replay observation or dataset custody mismatch')
    inputs = np.load(path / 'inputs.npy', mmap_mode='r', allow_pickle=False)
    with np.load(path / 'rows.npz', allow_pickle=False) as archive:
        rows = {key: archive[key] for key in archive.files}
    selected = metric_ids(rows, np.flatnonzero(rows['training_mask']), max_rows, 290929)
    receipt_hash = sha_file(path / 'dataset.json')
    result = []
    for index in selected:
        target = np.full(20, -.04)
        target[int(rows['actions'][index])] = .76
        result.append({'source': 'bootstrap_seed', 'source_sha256': receipt_hash,
                       'row_id': receipt_hash + ':' + str(int(index)), 'split': 'training',
                       'task': receipt['task_names'][int(rows['task_ids'][index])],
                       'inputs': unpack(inputs[index]), 'targets': target.tolist()})
    return validate_seed_replay(result)


@dataclass(frozen=True)
class PracticeConfig:
    new_rows: int = 8
    candidate_lifetime: int = 4
    replay_capacity: int = 512
    queue_capacity: int = 64
    training_budget: int = 2048
    feedback_workers: int = 6
    gate_workers: int = 4
    gate_tasks: tuple = ('basic', 'navigation', 'doors')
    gate_seeds: tuple = tuple(range(1220000000, 1220000008))
    episode_wall_seconds: float = 120
    feedback_horizon_tics: int = 36
    tie_tolerance: float = 1e-12
    return_tolerance: float = 1e-9
    random_seed: int = 290929
    max_journal_bytes: int = 32 * 1024 * 1024

    def __post_init__(self):
        for name in ('new_rows', 'candidate_lifetime', 'replay_capacity', 'queue_capacity',
                     'training_budget', 'feedback_workers', 'gate_workers', 'feedback_horizon_tics',
                     'max_journal_bytes'):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(name + ' must be a positive integer')
        if self.replay_capacity < self.new_rows or self.feedback_workers > 32 or self.gate_workers > 32:
            raise ValueError('Invalid replay or worker bound')
        if not self.gate_tasks or not self.gate_seeds or len(set(self.gate_seeds)) != len(self.gate_seeds):
            raise ValueError('A nonempty distinct repeated-development gate is required')
        if len(set(self.gate_tasks)) != len(self.gate_tasks):
            raise ValueError('Duplicate gate tasks')
        for task in self.gate_tasks:
            if get_task(task).split != 'train':
                raise ValueError('Practice may select only on development seeds of training tasks')
        if any(type(seed) is not int or not 0 <= seed < 2**32 for seed in self.gate_seeds):
            raise ValueError('Invalid development seed')
        if self.episode_wall_seconds <= 0 or not np.isfinite(self.episode_wall_seconds):
            raise ValueError('Positive finite episode wall cap required')
        if not 4 <= self.feedback_horizon_tics <= 560 or self.feedback_horizon_tics % 4:
            raise ValueError('Feedback horizon must be 4..560 whole decision tics')
        if (not all(np.isfinite(v) for v in (self.tie_tolerance, self.return_tolerance))
                or min(self.tie_tolerance, self.return_tolerance) < 0):
            raise ValueError('Tolerances must be nonnegative')


def _evaluate_one(payload):
    bundle, task, seed, wall = payload
    started = time.monotonic()
    queries = qualified = 0
    trace = []
    try:
        actor = Actor(bundle, device='cpu')
        with DoomEnv(task, seed, teacher=False) as env:
            cutoff = None
            while not env.finished:
                if time.monotonic() - started >= wall:
                    cutoff = 'wall_cutoff'
                    break
                raw = env.observe()
                proposal = actor.choose(raw)
                queries += 1
                if not proposal['qualified']:
                    cutoff = 'query_refused'
                    break
                qualified += 1
                transition = env.step(proposal['action'])
                actor.acknowledge(raw, proposal['action'], transition['tics'])
                trace.append({'raw_sha256': proposal['raw_sha256'], 'transition': transition})
            result = {**env.outcome(cutoff), 'status': 'complete' if cutoff is None else cutoff,
                      'checkpoint_sha256': actor.checkpoint_hash}
    except Exception as error:
        result = {'task_id': get_task(task).task_id, 'seed': seed, 'success': False,
                  'status': 'error', 'error': repr(error)}
    return {**result, 'queries': queries, 'qualified_queries': qualified, 'fallback_actions': 0,
            'decision_trace': trace,
            'decision_trace_sha256': digest(canonical(trace)), 'seconds': time.monotonic() - started}


class DevelopmentEvaluator:
    """Repeated selection seeds only; fixed actor, complete native accounting."""
    def __init__(self, config, output):
        self.config = config
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.pool = ProcessPoolExecutor(max_workers=config.gate_workers,
                                        mp_context=multiprocessing.get_context('spawn'))

    def __call__(self, bundle):
        payloads = [(bundle, task, seed, self.config.episode_wall_seconds)
                    for task in self.config.gate_tasks for seed in self.config.gate_seeds]
        futures = [self.pool.submit(_evaluate_one, payload) for payload in payloads]
        result = []
        for payload, future in zip(payloads, futures):
            try:
                row = future.result()
                trace = row.pop('decision_trace')
                encoded = gzip.compress((canonical(trace) + '\n').encode(), mtime=0)
                name = digest(canonical([bundle['hashes']['checkpoint_sha256'], payload[1], payload[2]])) + '.json.gz'
                destination = self.output / name
                if not destination.exists():
                    if sum(path.stat().st_size for path in self.output.glob('*.gz')) + len(encoded) > self.config.max_journal_bytes:
                        raise OSError('Development trace archive cap reached; preserve/upload it before resuming')
                    with destination.open('wb') as stream:
                        stream.write(encoded)
                        stream.flush()
                        os.fsync(stream.fileno())
                row['decision_trace_artifact'] = str(destination)
                row['decision_trace_file_sha256'] = digest(encoded)
                result.append(row)
            except Exception as error:
                result.append({'task_id': payload[1], 'seed': payload[2], 'status': 'worker_error',
                               'success': False, 'error': repr(error), 'queries': 0,
                               'qualified_queries': 0, 'fallback_actions': 0})
        return result

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=False)


def promotion_gate(candidate, champion, anchor, config):
    expected = {(task, seed) for task in config.gate_tasks for seed in config.gate_seeds}
    mapped = []
    for name, rows in (('candidate', candidate), ('champion', champion), ('anchor', anchor)):
        index = {(row['task_id'], row['seed']): row for row in rows}
        if (len(index) != len(rows) or set(index) != expected
                or any(row.get('status') != 'complete' or row.get('queries', 0) < 1
                       or row['qualified_queries'] != row['queries'] or row.get('fallback_actions') != 0
                       or not np.isfinite(row.get('return', float('nan'))) for row in rows)):
            return {'promote': False, 'reason': name + '_incomplete_or_unqualified'}
        mapped.append(index)
    candidate, champion, anchor = mapped
    for baseline_name, baseline in (('founder', anchor), ('champion', champion)):
        for key in expected:
            if baseline[key]['success'] and not candidate[key]['success']:
                return {'promote': False, 'reason': baseline_name + '_retained_success_lost', 'episode': list(key)}
        for task in config.gate_tasks:
            keys = [key for key in expected if key[0] == task]
            delta = sum(candidate[key]['return'] - baseline[key]['return'] for key in keys) / len(keys)
            if delta < -config.return_tolerance:
                return {'promote': False, 'reason': baseline_name + '_task_return_declined', 'task': task, 'delta': delta}
    more_successes = sum(row['success'] for row in candidate.values()) > sum(row['success'] for row in champion.values())
    gains = {task: sum(candidate[key]['return'] - champion[key]['return'] for key in expected if key[0] == task)
             / len(config.gate_seeds) for task in config.gate_tasks}
    improve = more_successes or any(delta > config.return_tolerance for delta in gains.values())
    return {'promote': bool(improve), 'reason': 'qualified_native_improvement' if improve else 'no_strict_improvement',
            'task_return_deltas': gains, 'successes': sum(row['success'] for row in candidate.values()),
            'denominator': len(expected), 'interpretation': 'Repeated development selection, not fresh confirmation'}


class PracticeLearner:
    @classmethod
    def from_bundle(cls, bundle, *, journal_path, config=None, initial_bundle=None,
                    continuation_bundle=None, seed_replay=None, teacher=None, evaluator=None,
                    native_protocol=None, practice_wave_sha256=None):
        return cls(bundle, journal_path=journal_path, config=config or PracticeConfig(),
                   initial_bundle=initial_bundle, continuation_bundle=continuation_bundle,
                   seed_replay=seed_replay, teacher=teacher, evaluator=evaluator,
                   native_protocol=native_protocol, practice_wave_sha256=practice_wave_sha256)

    def __init__(self, bundle, *, journal_path, config, initial_bundle=None,
                 continuation_bundle=None, seed_replay=None, teacher=None, evaluator=None,
                 native_protocol=None, practice_wave_sha256=None):
        _, self.founder = load_bundle(bundle, device='cpu')
        _, self.continuation = load_bundle(continuation_bundle or bundle, device='cpu')
        self.candidate, self.champion = load_bundle(initial_bundle or bundle, device='cpu')
        for field in ('contract', 'normalization', 'genome'):
            if self.champion[field] != self.founder[field]:
                raise ValueError('Resumed champion changes frozen founder ' + field)
            if self.continuation[field] != self.founder[field]:
                raise ValueError('Wave continuation changes founder observation or genome ' + field)
        active_target = self.champion['target_contract']
        if (active_target != self.founder['target_contract']
                and not (active_target.get('schema') == PREFERENCE_SCHEMA
                         and active_target.get('is_return_or_Q') is False)):
            raise ValueError('Resumed champion has incompatible preference/continuation semantics')
        source = self.founder['target_contract']
        if not (source.get('target_gene') == 'centered' and source.get('is_return_or_Q') is False
                or source.get('schema') == PREFERENCE_SCHEMA):
            raise ValueError('Practice requires an explicitly centered preference founder')
        self.config = config
        self.target = preference_contract(self.continuation, tie_tolerance=config.tie_tolerance)
        self.target['retention_founder_checkpoint_sha256'] = self.founder['hashes']['checkpoint_sha256']
        self.target['wave_contract'] = 'Frozen continuation within this wave; next wave uses new durable state and relabeled native replay'
        # The omitted option is exactly the historical v1 factory and target.
        self.native_protocol = copied(native_protocol) if native_protocol is not None else None
        if self.native_protocol is not None:
            # The adapter owns the portable companion package and reattaches it
            # on publication. Do not recursively duplicate it in learner state.
            for owned in (self.founder, self.continuation, self.champion):
                owned.get('metadata', {}).pop('practice_package', None)
                owned.get('hashes', {}).pop('practice_package_sha256', None)
        self._native_contract_factory, pool_type = native_contract, NativeFeedbackPool
        self._practice_wave_sha256 = practice_wave_sha256
        if self.native_protocol is not None:
            from .practice_protocol import resolve_protocol
            module = resolve_protocol(self.native_protocol, self.continuation, config)
            self._native_contract_factory, pool_type = module.target_contract, module.NativeFeedbackPool
            native = self.native_protocol['native_contract']
            self.target.update(native_contract_sha256=digest(canonical(native)),
                               native_horizon_tics=config.feedback_horizon_tics,
                               native_protocol_sha256=digest(canonical(self.native_protocol)))
            if practice_wave_sha256 is not None:
                if (not isinstance(practice_wave_sha256, str) or len(practice_wave_sha256) != 64
                        or any(c not in '0123456789abcdef' for c in practice_wave_sha256)):
                    raise ValueError('Malformed practice wave digest')
                self.target['practice_wave_sha256'] = practice_wave_sha256
        elif practice_wave_sha256 is not None:
            raise ValueError('A versioned wave requires an explicit native protocol')
        metadata = self.founder.get('metadata', {})
        embedded = metadata.get('seed_replay', [])
        if seed_replay is None and embedded and digest(canonical(embedded)) != metadata.get('seed_replay_sha256'):
            raise ValueError('Portable seed replay digest mismatch')
        self.seed_replay = validate_seed_replay(seed_replay if seed_replay is not None else embedded)
        self.path = Path(journal_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.pending_dir = self.path.parent / (self.path.stem + '_pending')
        self.pending_dir.mkdir(exist_ok=True)
        self._file_lock = self.path.with_suffix('.lock').open('a')
        fcntl.flock(self._file_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self._condition = threading.Condition(threading.RLock())
        self._journal_lock = threading.Lock()
        self._queue, self._new = deque(), deque()
        self._replay = deque(maxlen=config.replay_capacity)
        self._seen = {}
        self._enabled = self._closing = self._busy = False
        self._rollback_requested = False
        self._promotion = None
        self._pending_promotion = None
        self._previous = None
        self._completed = {}
        self._version = self._block_updates = 0
        self._anchor_rows = self._champion_rows = None
        self._rng = np.random.default_rng(config.random_seed)
        self._counts = dict(queued_transitions=0, processed_transitions=0, informative_contexts=0,
                            uninformative_contexts=0, rejected_contexts=0, updates=0, attempted_updates=0,
                            accepted_examples=0, promotions=0, gate_rejections=0, bootstrap_presentations=0,
                            native_presentations=0, native_feedback_seconds=0., repair_seconds=0., gate_seconds=0.)
        self._phase, self._error = 'paused', None
        self._state_path = self.path.parent / (self.path.stem + '_continuation.json')
        # Explicit protocols keep learner champions separate from actors that
        # have actually been durably published by the browser.
        self._deployed = copied(self.champion)
        self._deployed_previous = None
        self._offered = self._ready = None
        self._offer_delivered = self._offer_durable = False
        self._deployment_acks = deque()
        self._rollback_bundle = None
        try:
            self._restore_continuation()
            self._recover_pending()
        except Exception:
            self._file_lock.close()
            raise
        self.teacher = teacher or pool_type(self.continuation, workers=config.feedback_workers)
        self.evaluator = evaluator or DevelopmentEvaluator(config, self.path.parent/'development_traces')
        self._owned_teacher, self._owned_evaluator = teacher is None, evaluator is None
        self._event('practice_start', config=asdict(config), founder_checkpoint=self.founder['hashes']['checkpoint_sha256'],
                    continuation_checkpoint=self.continuation['hashes']['checkpoint_sha256'],
                    resumed_checkpoint=self.champion['hashes']['checkpoint_sha256'], target_contract=self.target,
                    seed_replay_rows=len(self.seed_replay), seed_replay_sha256=digest(canonical(self.seed_replay)),
                    recovered_pending=len(self._queue), gate_task_identities=[task_identity(t) for t in config.gate_tasks])
        self._thread = threading.Thread(target=self._run, name='cadence-v3-practice', daemon=True)
        self._thread.start()

    def _recover_pending(self):
        for path in sorted(self.pending_dir.glob('*.json')):
            item = json.loads(path.read_text())
            if item['founder_checkpoint'] != self.founder['hashes']['checkpoint_sha256']:
                raise ValueError('Durable pending record belongs to a different continuation founder')
            if item.get('continuation_checkpoint', self.founder['hashes']['checkpoint_sha256']) != self.continuation['hashes']['checkpoint_sha256']:
                raise ValueError('Pending context belongs to a different frozen continuation wave')
            expected_protocol = digest(canonical(self.native_protocol)) if self.native_protocol is not None else None
            if (item.get('native_protocol_sha256') != expected_protocol
                    or item.get('practice_wave_sha256') != self._practice_wave_sha256):
                raise ValueError('Pending context belongs to a different native protocol or practice wave')
            row = validate_transition(item['record'])
            key = self._key(row)
            if key in self._completed:
                if self._completed[key] != digest(canonical(row)):
                    raise ValueError('Recovered processed record changed its durable content')
                path.unlink()  # The atomic learner continuation already includes it.
                continue
            self._seen[key] = digest(canonical(row))
            self._queue.append((key, row, path))
        if len(self._queue) > self.config.queue_capacity:
            raise ValueError('Recovered queue exceeds configured capacity; increase capacity without dropping it')

    @staticmethod
    def _key(row):
        return digest(canonical([row['episode_id'], row['step_index']]))

    def _restore_continuation(self):
        if not self._state_path.exists():
            return
        state = json.loads(self._state_path.read_text())
        if (state['founder_checkpoint'] != self.founder['hashes']['checkpoint_sha256']
                or state['target_contract'] != self.target
                or state['config'] != copied(asdict(self.config))
                or state['seed_replay_sha256'] != digest(canonical(self.seed_replay))):
            raise ValueError('Saved learner continuation changes its founder, target, replay, or frozen configuration')
        initial_hash = self.champion['hashes']['checkpoint_sha256']
        _, restored = load_bundle(state['champion'], device='cpu')
        previous = state['previous']
        if self.native_protocol is not None:
            deployment = state.get('deployment')
            if not isinstance(deployment, dict):
                raise ValueError('Explicit protocol continuation lacks durable deployment custody')
            self._deployed = deployment['current']
            self._deployed_previous = deployment['previous']
            self._offered, self._ready = deployment['offered'], deployment['ready']
            for companion in (self._deployed, self._deployed_previous):
                if companion is not None:load_bundle(companion, device='cpu')
            for handoff in (self._offered, self._ready):
                if handoff:
                    load_bundle(handoff['proposal']['bundle'], device='cpu')
                    if handoff['source_checkpoint'] != self._deployed['hashes']['checkpoint_sha256']:
                        raise ValueError('Saved handoff has a different deployed source')
            if initial_hash != self._deployed['hashes']['checkpoint_sha256']:
                if not self._offered or initial_hash != self._offered['proposal']['bundle']['hashes']['checkpoint_sha256']:
                    raise ValueError('Actual actor is neither the acknowledged deployment nor its offered target')
                # Publication reached disk before its worker acknowledgment.
                self._apply_deployment_ack(initial_hash)
            self._version = 0
            for handoff in (self._offered, self._ready):
                if handoff:
                    self._version += 1
                    handoff['proposal']['version'] = self._version
            self._offer_delivered = self._offer_durable = False
        elif initial_hash != restored['hashes']['checkpoint_sha256']:
            possible = {self.founder['hashes']['checkpoint_sha256']}
            if previous:
                possible.add(previous[0]['hashes']['checkpoint_sha256'])
            if initial_hash not in possible:
                raise ValueError('Active actor is not the saved champion or a pending predecessor')
            self._version = 1  # Adapter supplies the persisted actor-version offset.
            self._promotion = {'bundle': copied(restored), 'snapshot': restored['snapshot'], 'version': 1,
                               'gate': restored.get('metadata', {}).get('practice_gate', {'recovered': True}),
                               'gate_sha256': restored.get('metadata', {}).get('practice_gate_sha256')}
        self.champion = restored
        candidate_bundle = copied(restored)
        candidate_bundle['snapshot'] = state['candidate_snapshot']
        candidate_bundle['hashes']['checkpoint_sha256'] = digest(state['candidate_snapshot'])
        self.candidate, _ = load_bundle(candidate_bundle, device='cpu')
        self._new = deque(state['new'])
        self._replay = deque(state['replay'], maxlen=self.config.replay_capacity)
        self._completed = state['completed']
        self._seen.update(self._completed)
        self._counts.update(state['counts'])
        self._block_updates = state['block_updates']
        self._rng.bit_generator.state = state['rng_state']
        self._anchor_rows, self._champion_rows = state['anchor_rows'], state['champion_rows']
        self._previous = previous
        if self.native_protocol is not None:
            self._save_continuation()  # Persist recovered publication and rebased local versions.

    def _save_continuation(self):
        if self.native_protocol is not None and self._pending_promotion:
            with self._condition:
                handoff = {'source_checkpoint': self._deployed['hashes']['checkpoint_sha256'],
                           'proposal': self._pending_promotion}
                if self._offered is None:
                    self._offered = handoff
                    self._offer_delivered = self._offer_durable = False
                else:
                    self._ready = handoff  # Latest qualified result; offered actor stays immutable.
                self._pending_promotion = None
        state = {'schema': 'doom-v3-practice-continuation/1',
                 'founder_checkpoint': self.founder['hashes']['checkpoint_sha256'],
                 'target_contract': self.target, 'config': asdict(self.config),
                 'seed_replay_sha256': digest(canonical(self.seed_replay)),
                 'champion': self.champion, 'candidate_snapshot': self.candidate.snapshot(),
                 'previous': self._previous, 'new': list(self._new), 'replay': list(self._replay),
                 'completed': self._completed, 'counts': self._counts, 'block_updates': self._block_updates,
                 'rng_state': self._rng.bit_generator.state, 'anchor_rows': self._anchor_rows,
                 'champion_rows': self._champion_rows}
        if self.native_protocol is not None:
            state['deployment'] = {'current': self._deployed, 'previous': self._deployed_previous,
                                   'offered': self._offered, 'ready': self._ready}
        if len(canonical(state).encode()) > self.config.max_journal_bytes:
            raise OSError('Bounded learner continuation cap reached; retain pending input and stop')
        atomic_json(self._state_path, state)
        with self._condition:
            if self.native_protocol is not None:
                self._offer_durable = self._offered is not None
            elif self._pending_promotion:
                self._promotion, self._pending_promotion = self._pending_promotion, None

    def _event(self, kind, **fields):
        event = {'kind': kind, 'time_unix': time.time(), **fields}
        with self._journal_lock:
            if not append_record(self.path, (canonical(event) + '\n').encode(),
                                 limit_bytes=self.config.max_journal_bytes):
                raise OSError('Practice journal backlog cap reached; archive verified segments before resuming')
        return event

    def submit_transition(self, record):
        row = validate_transition(record)
        key, sha = self._key(row), digest(canonical(row))
        with self._condition:
            if key in self._seen:
                if self._seen[key] != sha:
                    raise ValueError('Retry changed an already witnessed episode/step')
                return True
            if self._closing or not self._enabled or self._error or len(self._queue) >= self.config.queue_capacity:
                return False
            path = self.pending_dir / (key + '.json')
            self._event('transition_queued', key=key, record=row)
            item = {'founder_checkpoint': self.founder['hashes']['checkpoint_sha256'],
                    'continuation_checkpoint': self.continuation['hashes']['checkpoint_sha256'], 'record': row}
            if self.native_protocol is not None:
                item.update(native_protocol_sha256=digest(canonical(self.native_protocol)),
                            practice_wave_sha256=self._practice_wave_sha256)
            atomic_json(path, item)
            self._seen[key] = sha
            self._queue.append((key, row, path))
            self._counts['queued_transitions'] += 1
            self._condition.notify_all()
            return True

    def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('enabled must be a boolean')
        with self._condition:
            self._enabled = enabled and not self._closing and not self._error
            self._condition.notify_all()
            return self._enabled

    def status(self):
        with self._condition:
            rollback_available = (self._deployed_previous is not None and not self._busy
                and self._offered is None and self._ready is None and not self._deployment_acks
                if self.native_protocol is not None else self._previous is not None)
            return copied({**self._counts, 'schema': 'doom-v3-practice-status/1', 'enabled': self._enabled,
                           'phase': self._phase, 'busy': self._busy, 'queue': len(self._queue),
                           'queue_capacity': self.config.queue_capacity, 'new_pending': len(self._new),
                           'replay_rows': len(self._replay), 'seed_replay_rows': len(self.seed_replay),
                           'candidate_block_updates': self._block_updates, 'candidate_lifetime': self.config.candidate_lifetime,
                           'version': self._version, 'champion_checkpoint': self.champion['hashes']['checkpoint_sha256'],
                           'continuation_checkpoint': self.continuation['hashes']['checkpoint_sha256'],
                           'rollback_available': rollback_available, 'error': self._error,
                           'target_contract': self.target, 'last_gate': getattr(self, '_last_gate', None)})

    def take_promotion(self):
        with self._condition:
            if self.native_protocol is not None:
                if not self._offered or not self._offer_durable or self._offer_delivered:
                    return None
                self._offer_delivered = True
                return copied(self._offered['proposal'])
            result, self._promotion = self._promotion, None
            return copied(result) if result else None

    def acknowledge_deployment(self, checkpoint):
        """Queue acknowledgment only after the adapter atomically publishes its actor."""
        with self._condition:
            if self.native_protocol is None:
                return False
            if checkpoint == self._deployed['hashes']['checkpoint_sha256']:
                return True
            if self._closing or not self._offered or checkpoint != self._offered['proposal']['bundle']['hashes']['checkpoint_sha256']:
                raise ValueError('Deployment acknowledgment does not identify the offered checkpoint')
            if checkpoint not in self._deployment_acks:self._deployment_acks.append(checkpoint)
            self._condition.notify_all()
            return True

    def _apply_deployment_ack(self, checkpoint):
        """Only initialization or the serial learner owner mutates durable custody."""
        if checkpoint == self._deployed['hashes']['checkpoint_sha256']:return
        if not self._offered or checkpoint != self._offered['proposal']['bundle']['hashes']['checkpoint_sha256']:
            raise ValueError('Queued deployment acknowledgment no longer matches its offered checkpoint')
        self._deployed_previous = self._deployed
        self._deployed = copied(self._offered['proposal']['bundle'])
        self._offered, self._ready = self._ready, None
        if self._offered:self._offered['source_checkpoint'] = checkpoint
        self._offer_delivered = self._offer_durable = False

    def rollback(self, previous_deployed_bundle=None):
        with self._condition:
            if self.native_protocol is not None:
                if (self._deployed_previous is None or self._closing or self._busy
                        or self._offered or self._ready or self._deployment_acks):
                    return False
                requested = previous_deployed_bundle or self._deployed_previous
                if (requested['hashes']['checkpoint_sha256'] != self._deployed_previous['hashes']['checkpoint_sha256']
                        or requested['snapshot'] != self._deployed_previous['snapshot']):
                    raise ValueError('Rollback must identify the previous acknowledged deployment')
                self._rollback_bundle = copied(self._deployed_previous)
            elif previous_deployed_bundle is not None:
                raise ValueError('Explicit deployed rollback requires a native protocol')
            elif self._previous is None or self._closing:
                return False
            self._rollback_requested = True
            self._condition.notify_all()
            return True

    def close(self, wait=False):
        with self._condition:
            self._closing, self._enabled = True, False
            self._condition.notify_all()
        if wait:
            self._thread.join()

    def _bundle(self):
        protocol_metadata = ({'native_contract': self.native_protocol['native_contract'],
                              'native_protocol': self.native_protocol}
                             if self.native_protocol is not None else {})
        return make_bundle(self.candidate, self.founder['normalization'],
                           model_id=self.founder['model_id'] + '_practice_' + str(self._counts['updates']),
                           genome=self.founder['genome'], target_contract=self.target,
                           visual_lags=self.founder['contract']['visual_lags'],
                           query_budget=self.founder['query_budget'],
                           metadata={**self.founder.get('metadata', {}), **protocol_metadata,
                                     'practice_generation': self._version + 1,
                                     'practice_config': asdict(self.config), 'seed_replay': self.seed_replay,
                                     'seed_replay_sha256': digest(canonical(self.seed_replay)),
                                     'continuation_checkpoint_sha256': self.continuation['hashes']['checkpoint_sha256'],
                                     'retention_founder_checkpoint_sha256': self.founder['hashes']['checkpoint_sha256']})

    def _old_rows(self, count):
        pools = [pool for pool in (self.seed_replay, list(self._replay)) if pool]
        if not pools:
            return []
        return [copied(pools[i % len(pools)][int(self._rng.integers(len(pools[i % len(pools)])))]) for i in range(count)]

    def _update(self):
        new = [self._new.popleft() for _ in range(self.config.new_rows)]
        old = self._old_rows(len(new))
        if not old:
            self._replay.extend(new)
            self._event('replay_warmup', rows=[r['row_id'] for r in new], reason='No old preferences yet; preserve 50/50 batch contract')
            return
        rows = new + old
        self._phase = 'repair'
        before = time.monotonic()
        batch_sha = digest(canonical([self._counts['attempted_updates'], [r['row_id'] for r in rows]]))
        answer = self.candidate.observe_batch([(r['inputs'], {OUTPUT_NAME: r['targets']}) for r in rows],
                                              budget=self.config.training_budget, source='estimate')
        seconds = time.monotonic() - before
        admitted = bool(answer.get('accepted') and answer.get('qualified') and not answer.get('duplicate'))
        self._counts['attempted_updates'] += 1
        self._counts['repair_seconds'] += seconds
        self._replay.extend(new)
        seed_count = sum(r['source'] == 'bootstrap_seed' for r in rows)
        if admitted:
            self._counts['updates'] += 1
            self._counts['accepted_examples'] += len(rows)
            self._counts['bootstrap_presentations'] += seed_count
            self._counts['native_presentations'] += len(rows) - seed_count
            self._block_updates += 1
        self._event('admission', admitted=admitted, examples=len(rows), new_rows=len(new), old_rows=len(old),
                    ordered_batch_sha256=batch_sha,
                    bootstrap_rows=seed_count, row_ids=[r['row_id'] for r in rows], seconds=seconds,
                    diagnostics={k: answer.get(k) for k in ('accepted', 'qualified', 'duplicate', 'event_id', 'source', 'sweeps', 'stationarity', 'reason')},
                    block_updates=self._block_updates, candidate_checkpoint=digest(self.candidate.snapshot()))
        if admitted and self._block_updates >= self.config.candidate_lifetime:
            self._gate()

    def _gate(self):
        self._phase = 'development_gate'
        started = time.monotonic()
        candidate = self._bundle()
        if self._anchor_rows is None:
            self._anchor_rows = self.evaluator(self.founder)
            self._event('founder_development_anchor', rows=self._anchor_rows)
        if self._champion_rows is None:
            if self.champion['hashes']['checkpoint_sha256'] == self.founder['hashes']['checkpoint_sha256']:
                self._champion_rows = copied(self._anchor_rows)
            else:
                self._champion_rows = self.evaluator(self.champion)
        candidate_rows = self.evaluator(candidate)
        gate = promotion_gate(candidate_rows, self._champion_rows, self._anchor_rows, self.config)
        gate.update(candidate_checkpoint=candidate['hashes']['checkpoint_sha256'],
                    champion_checkpoint=self.champion['hashes']['checkpoint_sha256'],
                    founder_checkpoint=self.founder['hashes']['checkpoint_sha256'], rows=candidate_rows,
                    admitted_updates_in_block=self._block_updates)
        self._last_gate = gate
        self._event('development_gate', **gate)
        if gate['promote']:
            self._previous = (self.champion, self._champion_rows)
            self.champion, self._champion_rows = candidate, candidate_rows
            self._version += 1
            self._counts['promotions'] += 1
            gate_sha = digest(canonical(gate))
            self.champion['metadata']['practice_gate_sha256'] = gate_sha
            self.champion['metadata']['practice_gate'] = gate
            path = self.path.parent / 'exports' / self.champion['model_id'] / 'bundle.json'
            write_bundle(path, self.champion)
            atomic_json(path.parent.parent / 'latest.json', {'bundle': str(path), 'version': self._version,
                                                           'checkpoint_sha256': self.champion['hashes']['checkpoint_sha256']})
            with self._condition:
                self._pending_promotion = {'bundle': copied(self.champion), 'snapshot': self.champion['snapshot'],
                                   'version': self._version, 'gate': gate, 'gate_sha256': gate_sha}
        else:
            self._counts['gate_rejections'] += 1
        self.candidate, _ = load_bundle(self.champion, device='cpu')
        self._block_updates = 0
        self._counts['gate_seconds'] += time.monotonic() - started

    def _process(self, key, row):
        self._phase = 'native_feedback'
        started = time.monotonic()
        contract = self._native_contract_factory(row['task'], self.continuation['hashes']['checkpoint_sha256'],
                                   horizon_tics=self.config.feedback_horizon_tics)
        feedback = self.teacher.label(row, contract)
        self._counts['native_feedback_seconds'] += time.monotonic() - started
        self._event('native_feedback', key=key, feedback=feedback)
        if self.native_protocol is not None and feedback.get('contract') != contract:
            raise ValueError('Native feedback was produced under a different protocol')
        if not feedback.get('ok'):
            self._counts['rejected_contexts'] += 1
            return
        lesson = preference_target(feedback['labels'], tie_tolerance=self.config.tie_tolerance)
        if lesson is None:
            self._counts['uninformative_contexts'] += 1
            return
        example = {'inputs': row['inputs'], 'targets': lesson['targets'], 'source': 'autonomous_native_rank',
                   'row_id': key, 'task': get_task(row['task']).task_id,
                   'feedback_sha256': digest(canonical(feedback)), 'native_contract': contract,
                   'native_values': lesson['native_values'], 'best_actions': lesson['best_actions']}
        self._event('preference_example', example=example)
        self._counts['informative_contexts'] += 1
        self._new.append(example)
        if len(self._new) >= self.config.new_rows:
            self._update()

    def _run(self):
        try:
            while True:
                with self._condition:
                    while (not self._closing and not self._rollback_requested and not self._deployment_acks
                           and (not self._enabled or not self._queue)):
                        self._phase = 'paused' if not self._enabled else 'awaiting_experience'
                        self._condition.wait()
                    if self._closing:
                        break
                    if self._deployment_acks:
                        self._apply_deployment_ack(self._deployment_acks.popleft())
                        self._save_continuation()
                        self._event('deployment_acknowledged', checkpoint=self._deployed['hashes']['checkpoint_sha256'])
                        continue
                    if self._rollback_requested:
                        self._rollback_requested = False
                        if self.native_protocol is not None:
                            self.champion, self._champion_rows = self._rollback_bundle, None
                            self._rollback_bundle = None
                        else:
                            self.champion, self._champion_rows = self._previous
                        self._previous = None
                        self.candidate, _ = load_bundle(self.champion, device='cpu')
                        self._version += 1
                        self._block_updates = 0
                        self._pending_promotion = {'bundle': copied(self.champion), 'snapshot': self.champion['snapshot'],
                                           'version': self._version, 'gate': {'rollback': True}, 'gate_sha256': None}
                        self._event('rollback', version=self._version, checkpoint=self.champion['hashes']['checkpoint_sha256'])
                        self._save_continuation()
                        continue
                    key, row, pending = self._queue.popleft()
                    self._busy = True
                self._process(key, row)
                self._completed[key] = digest(canonical(row))
                self._counts['processed_transitions'] += 1
                self._save_continuation()
                self._event('transition_processed', key=key)
                pending.unlink()
                with self._condition:
                    self._busy = False
                    self._condition.notify_all()
        except Exception as error:
            with self._condition:
                self._error = type(error).__name__ + ': ' + str(error)
                self._phase, self._enabled = 'error', False
            try:
                self._event('worker_error', error=self._error, pending_preserved=True)
            except Exception:
                pass
        finally:
            if self._owned_teacher:
                self.teacher.close()
            if self._owned_evaluator:
                self.evaluator.close()
            with self._condition:
                self._busy = False
                if not self._error:
                    self._phase = 'closed'
            fcntl.flock(self._file_lock, fcntl.LOCK_UN)
            self._file_lock.close()


def run_headless(args):
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=False)
    _, bundle = load_bundle(args.bundle, device='cpu')
    _, retention_founder = load_bundle(args.retention_founder or args.bundle, device='cpu')
    tasks = tuple(args.task or ['basic'])
    config = PracticeConfig(new_rows=args.new_rows, candidate_lifetime=args.candidate_lifetime,
                            feedback_workers=args.feedback_workers, gate_workers=args.gate_workers,
                            gate_tasks=tuple(args.gate_task or tasks),
                            gate_seeds=tuple(range(args.gate_seed_start, args.gate_seed_start + args.gate_episodes)),
                            episode_wall_seconds=args.episode_wall_seconds,
                            feedback_horizon_tics=args.feedback_horizon_tics, max_journal_bytes=args.journal_mb * 1024**2)
    seeds = seed_replay_from_dataset(args.bootstrap_dataset, retention_founder) if args.bootstrap_dataset else None
    atomic_json(output / 'freeze.json', {'schema': 'doom-v3-autonomous-practice-freeze/1', 'config': asdict(config),
                'bundle_sha256': sha_file(args.bundle), 'founder_checkpoint': retention_founder['hashes']['checkpoint_sha256'],
                'retention_founder_file_sha256': sha_file(args.retention_founder or args.bundle),
                'continuation_checkpoint': bundle['hashes']['checkpoint_sha256'],
                'practice_seed_start': args.seed_start, 'tasks': [task_identity(t) for t in tasks],
                'wall_seconds': args.wall_seconds, 'drain_seconds': args.drain_seconds,
                'source_sha256': {name: sha_file(Path(__file__).with_name(name)) for name in
                                 ('practice.py','native_feedback.py','tasks.py','brain.py','interface.py')},
                'seed_replay_sha256': digest(canonical(seeds)),
                'claim': 'Development-only policy improvement; no fresh confirmation'})
    learner = PracticeLearner.from_bundle(retention_founder, initial_bundle=bundle, continuation_bundle=bundle,
                                         journal_path=output / 'online.jsonl', config=config, seed_replay=seeds)
    actor = Actor(bundle, device='cpu')
    learner.set_enabled(True)
    started = time.monotonic()
    episodes = []
    try:
        episode = total_transitions = 0
        while time.monotonic() - started < args.wall_seconds and episode < args.max_episodes:
            task, seed = tasks[episode % len(tasks)], args.seed_start + episode
            promotion = learner.take_promotion()
            if promotion:
                actor = Actor(promotion['bundle'], device='cpu')
            actor.reset()
            prefix, outcomes = [], []
            episode_started = time.monotonic()
            cutoff = None
            queries = qualified = 0
            with DoomEnv(task, seed, teacher=False) as env:
                while not env.finished:
                    if time.monotonic() - started >= args.wall_seconds:
                        cutoff = 'collector_wall_cap'
                        break
                    if time.monotonic() - episode_started >= args.episode_wall_seconds:
                        cutoff = 'episode_wall_cap'
                        break
                    if total_transitions >= args.max_transitions:
                        cutoff = 'collector_transition_cap'
                        break
                    raw = env.observe()
                    queries += 1
                    decision = actor.choose(raw)
                    if not decision['qualified']:
                        cutoff = 'query_refused'
                        break
                    qualified += 1
                    transition = env.step(decision['action'])
                    actor.acknowledge(raw, decision['action'], transition['tics'])
                    record = {'task': task, 'seed': seed, 'episode_id': f'{task}:{seed}', 'step_index': len(prefix),
                              'prefix_actions': list(prefix), 'prefix_outcomes': copied(outcomes),
                              'raw_sha256': decision['raw_sha256'], 'inputs': decision['inputs'],
                              'executed_action': decision['action'], 'transition': transition,
                              'policy_checkpoint_sha256': actor.checkpoint_hash,
                              'qualified': True, 'fallback': False, 'behavior_source': 'autonomous'}
                    accepted = learner.submit_transition(record)
                    while not accepted and time.monotonic() - started < args.wall_seconds and not learner.status()['error']:
                        time.sleep(.05)
                        accepted = learner.submit_transition(record)
                    if not accepted:
                        atomic_json(output / 'collector_pending.json', record)
                        cutoff = 'collector_backpressure_or_error'
                    prefix.append(decision['action'])
                    outcomes.append(transition)
                    total_transitions += 1
                    if cutoff:
                        break
                row = {**env.outcome(cutoff), 'status': 'complete' if cutoff is None else cutoff,
                       'checkpoint_sha256': actor.checkpoint_hash, 'queries': queries,
                       'qualified_queries': qualified, 'fallback_actions': 0}
            episodes.append(row)
            episode += 1
            atomic_json(output / 'status.json', {**learner.status(), 'seconds': time.monotonic() - started,
                                                 'episodes': episodes, 'actor_checkpoint': actor.checkpoint_hash})
            if learner.status()['error'] or total_transitions >= args.max_transitions:
                break
        drain_end = time.monotonic() + args.drain_seconds
        while time.monotonic() < drain_end:
            status = learner.status()
            if status['error'] or not (status['queue'] or status['busy']):
                break
            atomic_json(output / 'status.json', {**status, 'seconds': time.monotonic()-started, 'episodes': episodes})
            time.sleep(.2)
    finally:
        learner.close(wait=True)
        report = {**learner.status(), 'seconds': time.monotonic()-started, 'episodes': episodes,
                  'pending_records_preserved': len(list(learner.pending_dir.glob('*.json'))),
                  'interpretation': 'Practice and repeated development selection only; not fresh confirmation'}
        atomic_json(output / 'receipt.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--retention-founder', help='Original retained-skills anchor; bundle is the new wave actor and continuation')
    parser.add_argument('--bootstrap-dataset')
    parser.add_argument('--out', required=True)
    parser.add_argument('--task', action='append')
    parser.add_argument('--seed-start', type=int, default=1300000000)
    parser.add_argument('--max-episodes', type=int, default=10000)
    parser.add_argument('--max-transitions', type=int, default=10000000)
    parser.add_argument('--wall-seconds', type=float, default=300)
    parser.add_argument('--drain-seconds', type=float, default=30)
    parser.add_argument('--episode-wall-seconds', type=float, default=120)
    parser.add_argument('--new-rows', type=int, default=8)
    parser.add_argument('--candidate-lifetime', type=int, choices=(1, 4, 16), default=4)
    parser.add_argument('--feedback-workers', type=int, default=6)
    parser.add_argument('--feedback-horizon-tics', type=int, default=36)
    parser.add_argument('--gate-workers', type=int, default=4)
    parser.add_argument('--gate-task', action='append')
    parser.add_argument('--gate-seed-start', type=int, default=1220000000)
    parser.add_argument('--gate-episodes', type=int, default=8)
    parser.add_argument('--journal-mb', type=int, default=32)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (not np.isfinite(args.wall_seconds) or not np.isfinite(args.drain_seconds)
            or args.wall_seconds <= 0 or args.drain_seconds < 0
            or args.max_episodes < 1 or args.max_transitions < 1):
        parser.error('Finite positive collection bounds are required')
    if not args.worker:
        # Bounds include interpreter, brain restoration, repairs and slow gates.
        # Internal budgets alone cannot cancel an in-progress solver or engine.
        started = time.monotonic()
        cap = args.wall_seconds + args.drain_seconds + 60
        process = subprocess.Popen([sys.executable, '-m', 'v3.practice', *sys.argv[1:], '--worker'],
                                   start_new_session=True)
        cutoff = False
        def interrupted(_signal, _frame):
            raise KeyboardInterrupt
        old_handler = signal.signal(signal.SIGTERM, interrupted)
        try:
            process.wait(timeout=cap)
        except subprocess.TimeoutExpired:
            cutoff = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        except KeyboardInterrupt:
            cutoff = True
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            signal.signal(signal.SIGTERM, old_handler)
        atomic_json(Path(args.out) / 'supervisor.json', {'schema': 'doom-v3-practice-supervisor/1',
                    'returncode': process.returncode, 'external_wall_cutoff': cutoff,
                    'seconds': time.monotonic()-started, 'hard_cap_seconds': cap+10,
                    'missing_receipt': not (Path(args.out)/'receipt.json').exists(),
                    'pending_records_preserved': len(list((Path(args.out)/'online_pending').glob('*.json')))})
        raise SystemExit(process.returncode if not cutoff else 124)
    report = run_headless(args)
    raise SystemExit(2 if report['error'] else 0)


if __name__ == '__main__':
    main()
