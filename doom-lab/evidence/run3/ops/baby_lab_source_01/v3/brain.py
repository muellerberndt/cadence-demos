"""Measured candidate genomes and portable common-rule Doom policy bundles.

The policy is a population of Cadence patches in the same coupled equilibrium.
``query`` never substitutes a heuristic action or commits hidden recurrent state.
The caller serializes calls and commits external History only after execution.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time

import numpy as np

HERE = Path(__file__).resolve().parent
CADENCE_SRC = Path(os.environ.get('CADENCE_SRC', HERE.parents[2]/'cadence/src')).resolve()
if str(CADENCE_SRC) not in sys.path:
    sys.path.insert(0, str(CADENCE_SRC))
from cadence import Brain, Cortex
from cadence.brain import IMPLEMENTATION

try:
    from .interface import (ACTION_BUTTONS, ACTION_NAMES, History, OUTPUT_NAME, PORT_SHAPES,
                            VISUAL_LAGS, canonical, contract, digest, validate_inputs,
                            validate_lags, validate_normalizer)
except ImportError:
    from interface import (ACTION_BUTTONS, ACTION_NAMES, History, OUTPUT_NAME, PORT_SHAPES,
                           VISUAL_LAGS, canonical, contract, digest, validate_inputs,
                           validate_lags, validate_normalizer)

BUNDLE_SCHEMA = 'cadence-doom-player-v3/1'
WIDTHS = {'small': 16, 'medium': 32, 'large': 64}
QUERY_BUDGET = 512


def genome_spec(size='small', seed=0, *, observer=True, sensor_skip=True,
                parameter_prior=.4, initial_scale=.3, state_prior=.01,
                settle_budget=2048, tolerance=1e-6,
                topology_version=None, recursion_depth=None):
    if size not in WIDTHS:
        raise ValueError('Size must be small, medium or large')
    if type(observer) is not bool or type(sensor_skip) is not bool:
        raise ValueError('Observer and sensor_skip genes must be booleans')
    if type(seed) is not int or seed < 0:
        raise ValueError('Seed must be a nonnegative integer')
    gene = dict(size=size, seed=seed, observer=observer, sensor_skip=sensor_skip,
                parameter_prior=parameter_prior, initial_scale=initial_scale,
                state_prior=state_prior, settle_budget=settle_budget, tolerance=tolerance)
    if topology_version is None:
        if recursion_depth is not None:
            raise ValueError('Recursive depth requires explicit topology_version=2')
    else:
        if type(topology_version) is not int or topology_version != 2:
            raise ValueError('Supported explicit topology version is 2')
        depth = 1 if recursion_depth is None else recursion_depth
        if type(depth) is not int or depth not in (1, 2, 3):
            raise ValueError('Recursive depth must be 1, 2 or 3')
        gene.update(topology_version=2, recursion_depth=depth)
    return gene


def population_specs(gene):
    """Fixed total patch count, explicit path depth; this is not parameter matching.

    An observer reads both state and exact residual through one coupled solve.
    The observer=False control uses the same population widths and state-only
    paths. The original omitted-version genome keeps its exact old layout.
    """
    gene = genome_spec(**gene)
    depth = gene.get('recursion_depth', 1)
    factor = WIDTHS[gene['size']] // 16
    sensory_width = {1: 16, 2: 10, 3: 8}[depth] * factor
    middle_width = {1: 0, 2: 12, 3: 8}[depth] * factor
    populations = [
        {'name': 'scene', 'patches': sensory_width,
         'inputs': ['periphery', 'visual_history'], 'observes': []},
        {'name': 'aim', 'patches': sensory_width,
         'inputs': ['fovea', 'executed_action_history'], 'observes': []},
    ]
    previous = ['scene', 'aim']
    for level in range(1, depth):
        name = 'reflection' + str(level)
        populations.append({'name': name, 'patches': middle_width,
            'inputs': [] if gene['observer'] else list(previous),
            'observes': list(previous) if gene['observer'] else []})
        previous = [name]
    direct = ['periphery', 'fovea', 'executed_action_history'] if gene['sensor_skip'] else ['executed_action_history']
    populations.append({'name': 'policy', 'patches': len(ACTION_NAMES),
        'inputs': direct if gene['observer'] else direct+previous,
        'observes': previous if gene['observer'] else []})
    return populations


def build(size='small', seed=0, *, device='cpu', **genes):
    gene = genome_spec(size, seed, **genes)
    numerical = {k: gene[k] for k in ('seed', 'parameter_prior', 'initial_scale',
                 'state_prior', 'settle_budget', 'tolerance')}
    c = Cortex(device=device, dtype='float64', state_bound=1, parameter_bound=4, **numerical)
    ports = {name: c.input(name, shape=shape) for name, shape in PORT_SHAPES.items()}
    populations = {}
    for spec in population_specs(gene):
        inputs = tuple(ports[name] if name in ports else populations[name] for name in spec['inputs'])
        if spec['observes']:
            population = c.observer(spec['name'], patches=spec['patches'], inputs=inputs,
                                   observes=tuple(populations[name] for name in spec['observes']))
        else:
            population = c.column(spec['name'], patches=spec['patches'], inputs=inputs)
        populations[spec['name']] = population
    c.output(OUTPUT_NAME, shape=len(ACTION_NAMES), reads=populations['policy'])
    return c.build()


def query(brain, inputs, *, budget=QUERY_BUDGET):
    validate_inputs(inputs)
    started = time.monotonic()
    result = brain.settle(inputs, budget=budget)
    scores = np.asarray(result['outputs'][OUTPUT_NAME], dtype=np.float64)
    qualified = bool(result['qualified'] and scores.shape == (len(ACTION_NAMES),)
                     and np.isfinite(scores).all())
    action = int(np.argmax(scores)) if qualified else None
    return {'qualified': qualified, 'action': action,
            'buttons': list(ACTION_BUTTONS[action]) if action is not None else None,
            'scores': scores.tolist(), 'result': result,
            'query_seconds': time.monotonic()-started}


def validate_layout(snapshot, gene):
    gene = genome_spec(**gene)
    parsed = json.loads(snapshot)
    layout = parsed['layout']
    expected_inputs = [{'name': name, 'shape': [size]} for name, size in PORT_SHAPES.items()]
    if layout['inputs'] != expected_inputs:
        raise ValueError('Snapshot input ports differ from the v3 observation contract')
    expected_outputs = [{'name': OUTPUT_NAME, 'shape': [len(ACTION_NAMES)],
                         'reads': 'policy', 'indices': list(range(len(ACTION_NAMES)))}]
    if layout['outputs'] != expected_outputs:
        raise ValueError('Every action score must expose its own settled policy patch')
    populations = population_specs(gene)
    if layout['populations'] != populations:
        raise ValueError('Snapshot topology differs from the declared candidate genome')
    for key in ('seed', 'parameter_prior', 'initial_scale', 'state_prior', 'settle_budget', 'tolerance'):
        if parsed['config'][key] != gene[key]:
            raise ValueError('Snapshot numerical gene differs: ' + key)
    if parsed['config']['state_bound'] != 1 or parsed['config']['parameter_bound'] != 4:
        raise ValueError('Snapshot bounds differ from the common training contract')
    for key, expected in {'dtype': 'float64', 'fan_in': None, 'step': 1., 'backtracks': 32}.items():
        if parsed['config'][key] != expected:
            raise ValueError('Snapshot differs from the fixed numerical control: ' + key)
    return gene


def make_bundle(brain, normalizer, *, model_id, genome, target_contract,
                visual_lags=VISUAL_LAGS, query_budget=QUERY_BUDGET, metadata=None):
    """Declare score semantics explicitly; imitation/utility/Q are not synonyms."""
    if not isinstance(model_id, str) or not model_id or not isinstance(target_contract, dict) or not target_contract:
        raise ValueError('A model ID and explicit nonempty target contract are required')
    if type(query_budget) is not int or not 1 <= query_budget <= 65536:
        raise ValueError('Query budget must be an integer in [1, 65536]')
    validate_normalizer(normalizer)
    snapshot = brain.snapshot()
    gene = validate_layout(snapshot, genome)
    boundary = contract(visual_lags)
    # Canonical JSON copying both refuses nonfinite metadata and detaches callers.
    data = json.loads(canonical({'schema': BUNDLE_SCHEMA, 'model_id': model_id,
        'contract': boundary, 'genome': gene, 'normalization': normalizer,
        'target_contract': target_contract, 'query_budget': query_budget,
        'snapshot': snapshot, 'metadata': metadata or {}, 'implementation': dict(IMPLEMENTATION)}))
    data['hashes'] = {'checkpoint_sha256': digest(snapshot),
                      'normalization_sha256': digest(canonical(data['normalization'])),
                      'contract_sha256': digest(canonical(boundary)),
                      'target_contract_sha256': digest(canonical(data['target_contract'])),
                      'genome_sha256': digest(canonical(gene))}
    return data


def load_bundle(path_or_data, *, device='cpu'):
    """Return (Brain, detached bundle); all observation/target identities verified."""
    if isinstance(path_or_data, dict):
        data = json.loads(canonical(path_or_data))
    else:
        path = Path(path_or_data)
        data = json.loads((path/'bundle.json' if path.is_dir() else path).read_text())
    if data.get('schema') != BUNDLE_SCHEMA:
        raise ValueError('Unknown full-Doom bundle schema')
    if data['contract'] != contract(validate_lags(data['contract']['visual_lags'])):
        raise ValueError('Bundle observation/action contract is not supported')
    for field, source in (('checkpoint', data['snapshot']),
                          ('normalization', canonical(data['normalization'])),
                          ('contract', canonical(data['contract'])),
                          ('target_contract', canonical(data['target_contract'])),
                          ('genome', canonical(data['genome']))):
        if digest(source) != data['hashes'][field+'_sha256']:
            raise ValueError(field + ' digest mismatch')
    validate_normalizer(data['normalization'])
    validate_layout(data['snapshot'], data['genome'])
    if data.get('implementation') != json.loads(data['snapshot'])['implementation']:
        raise ValueError('Bundle and snapshot implementation identities differ')
    if not data.get('model_id') or not isinstance(data.get('target_contract'), dict) or not data['target_contract']:
        raise ValueError('Bundle must declare its identity and score semantics')
    if type(data.get('query_budget')) is not int or not 1 <= data['query_budget'] <= 65536:
        raise ValueError('Invalid deployment query budget')
    brain = Brain.from_snapshot(data['snapshot'], device=device)
    return brain, data


class Actor:
    """One serial actor with explicit episode history and acknowledged actions."""
    def __init__(self, path_or_data, *, device='cpu'):
        self.brain, self.bundle = load_bundle(path_or_data, device=device)
        self.checkpoint_hash = self.bundle['hashes']['checkpoint_sha256']
        self.history = History(self.bundle['contract']['visual_lags'])
        self._pending = None

    def reset(self):
        self.history.reset()
        self._pending = None

    def choose(self, raw):
        if self._pending is not None:
            raise RuntimeError('A prior action proposal has not been acknowledged')
        inputs = self.history.encode(raw, self.bundle['normalization'])
        result = query(self.brain, inputs, budget=self.bundle['query_budget'])
        frame_hash = digest(np.asarray(raw).tobytes())
        if result['qualified']:
            self._pending = {'raw_sha256': frame_hash, 'action': result['action']}
        return {**result, 'inputs': inputs, 'raw_sha256': frame_hash,
                'checkpoint_sha256': self.checkpoint_hash}

    def acknowledge(self, raw_pre_action, action, actual_tics):
        if self._pending is None:
            raise RuntimeError('No qualified action is awaiting execution acknowledgment')
        if (action != self._pending['action']
                or digest(np.asarray(raw_pre_action).tobytes()) != self._pending['raw_sha256']):
            raise ValueError('Executed action/frame differs from the qualified proposal')
        self.history.acknowledge(raw_pre_action, action, actual_tics)
        self._pending = None


def write_bundle(path, data):
    """Atomic local export; remote campaign custody remains the runner's job."""
    load_bundle(data, device='python')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                prefix='.'+path.name+'.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(canonical(data)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
