"""Portable, explicit Basic practice waves; importing never enables learning.

Training target provenance remains unchanged. A separate hash-bound package
selects future feedback and carries the original retention founder and frozen
continuation. Different waves never share native replay or pending files.
"""
from __future__ import annotations

import copy
from dataclasses import asdict
from pathlib import Path
import platform

from .brain import load_bundle
from .interface import canonical, digest

PROTOCOL_SCHEMA = 'doom-native-practice-protocol/1'
PACKAGE_SCHEMA = 'doom-browser-practice-wave/1'
PACKAGE_KEY = 'practice_package'


def _module(horizon):
    if type(horizon) is not int or horizon not in (36, 144, 300):
        raise ValueError('Browser practice supports explicit horizons36,144,300 only')
    if horizon == 36:
        from . import native_feedback as module
    else:
        from . import native_feedback_long as module
    return module


def make_protocol(horizon, continuation_checkpoint):
    module = _module(horizon)
    root = Path(__file__).parent
    # Bind both the factory and its native replay dependencies, not just H.
    names = {'native_feedback.py', 'practice.py', 'interface.py', 'tasks.py',
             'brain.py', 'evaluate.py', 'practice_protocol.py', 'runtime.py', 'experience_sampling.py',
             Path(module.__file__).name}
    from .brain import IMPLEMENTATION
    from .tasks import task_identity, vizdoom_module
    binary = Path(vizdoom_module().__file__).parent/'vizdoom'
    return {'schema': PROTOCOL_SCHEMA,
            'native_contract': module.target_contract('basic', continuation_checkpoint,
                                                       horizon_tics=horizon),
            'source_sha256': {name: digest((root/name).read_bytes()) for name in sorted(names)},
            'core_implementation': dict(IMPLEMENTATION), 'task_identity': task_identity('basic'),
            'engine_platform': {'system': platform.system(), 'machine': platform.machine(),
                                'engine_binary_sha256': digest(binary.read_bytes())}}


def resolve_protocol(protocol, continuation, config):
    if not isinstance(protocol, dict) or protocol.get('schema') != PROTOCOL_SCHEMA:
        raise ValueError('Unknown native practice protocol')
    horizon = config.feedback_horizon_tics
    expected = make_protocol(horizon, continuation['hashes']['checkpoint_sha256'])
    if canonical(protocol) != canonical(expected):
        raise ValueError('Practice protocol differs from its native factory, sources, horizon or continuation')
    if tuple(config.gate_tasks) != ('basic',):
        raise ValueError('Versioned browser native feedback is currently verified for Basic only')
    return _module(horizon)


def _companion(value):
    _, bundle = load_bundle(value, device='python')
    bundle['metadata'].pop(PACKAGE_KEY, None)
    bundle['hashes'].pop(PACKAGE_KEY+'_sha256', None)
    return bundle


def _same_boundary(founder, other):
    for field in ('contract', 'genome', 'normalization'):
        if founder[field] != other[field]:
            raise ValueError('Practice package changes original founder '+field)


def _training_provenance(active):
    """Check an existing horizon result without rewriting how it was trained."""
    target = active['target_contract']
    if 'native_contract_sha256' not in target:
        return
    native = active['metadata'].get('native_contract')
    if not isinstance(native, dict) or digest(canonical(native)) != target['native_contract_sha256']:
        raise ValueError('Native training contract is missing or its digest differs')
    horizon = target.get('native_horizon_tics')
    module = _module(horizon)
    expected = module.target_contract('basic', native.get('continuation_checkpoint_sha256'),
                                      horizon_tics=horizon)
    if canonical(native) != canonical(expected):
        raise ValueError('Training horizon or native contract version was relabeled')


def make_package(active, founder, continuation, *, config, wave_name, collection_stride=None):
    from .practice import validate_seed_replay
    if (not isinstance(wave_name, str) or not 1 <= len(wave_name) <= 96
            or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in wave_name)):
        raise ValueError('An explicit short alphanumeric wave name is required')
    active, founder, continuation = map(_companion, (active, founder, continuation))
    _same_boundary(founder, active)
    _same_boundary(founder, continuation)
    _training_provenance(active)
    rows = validate_seed_replay(founder['metadata'].get('seed_replay', []))
    replay_hash = digest(canonical(rows))
    if not rows or founder['metadata'].get('seed_replay_sha256') != replay_hash:
        raise ValueError('Original retention founder requires verified finite bootstrap replay')
    declared = active['target_contract'].get('retention_founder_checkpoint_sha256')
    if declared is not None and declared != founder['hashes']['checkpoint_sha256']:
        raise ValueError('Selected checkpoint declares a different original retention founder')
    protocol = make_protocol(config.feedback_horizon_tics, continuation['hashes']['checkpoint_sha256'])
    resolve_protocol(protocol, continuation, config)
    descriptor = {'schema': PACKAGE_SCHEMA, 'wave_name': wave_name,
        'initial_checkpoint_sha256': active['hashes']['checkpoint_sha256'],
        'initial_training_target_sha256': active['hashes']['target_contract_sha256'],
        'retention_founder_checkpoint_sha256': founder['hashes']['checkpoint_sha256'],
        'continuation_checkpoint_sha256': continuation['hashes']['checkpoint_sha256'],
        'founder_bundle_sha256': digest(canonical(founder)),
        'continuation_bundle_sha256': digest(canonical(continuation)),
        'seed_replay_sha256': replay_hash, 'protocol': protocol, 'config': asdict(config)}
    if collection_stride is not None:
        from .experience_sampling import contract
        descriptor['experience_collection'] = contract(collection_stride)
    package = {'schema': PACKAGE_SCHEMA, 'wave_sha256': digest(canonical(descriptor)),
               'descriptor': descriptor, 'founder': founder, 'continuation': continuation}
    return attach_package(active, package)


def attach_package(active, package):
    value = copy.deepcopy(active)
    value.setdefault('metadata', {})[PACKAGE_KEY] = copy.deepcopy(package)
    value['hashes'][PACKAGE_KEY+'_sha256'] = digest(canonical(package))
    return value


def unpack_package(active):
    """Validate all identities before any journal, worker or pool is created."""
    from .practice import PracticeConfig, PREFERENCE_SCHEMA, validate_seed_replay
    package = active.get('metadata', {}).get(PACKAGE_KEY)
    if package is None:
        if PACKAGE_KEY+'_sha256' in active.get('hashes', {}):
            raise ValueError('Practice package is missing')
        return None
    if (not isinstance(package, dict) or package.get('schema') != PACKAGE_SCHEMA
            or digest(canonical(package)) != active['hashes'].get(PACKAGE_KEY+'_sha256')):
        raise ValueError('Practice package digest or schema mismatch')
    descriptor = package['descriptor']
    if descriptor.get('schema') != PACKAGE_SCHEMA or digest(canonical(descriptor)) != package.get('wave_sha256'):
        raise ValueError('Practice wave descriptor digest mismatch')
    founder, continuation = map(_companion, (package['founder'], package['continuation']))
    _same_boundary(founder, active)
    _same_boundary(founder, continuation)
    for name, bundle in (('founder', founder), ('continuation', continuation)):
        if digest(canonical(bundle)) != descriptor[name+'_bundle_sha256']:
            raise ValueError('Practice '+name+' companion changed')
    if (founder['hashes']['checkpoint_sha256'] != descriptor['retention_founder_checkpoint_sha256']
            or continuation['hashes']['checkpoint_sha256'] != descriptor['continuation_checkpoint_sha256']):
        raise ValueError('Practice companion checkpoint binding differs')
    rows = validate_seed_replay(founder['metadata'].get('seed_replay', []))
    replay_hash = digest(canonical(rows))
    if not rows or replay_hash != descriptor['seed_replay_sha256'] or replay_hash != founder['metadata'].get('seed_replay_sha256'):
        raise ValueError('Practice original replay custody differs')
    config = PracticeConfig(**descriptor['config'])
    collection = descriptor.get('experience_collection')
    if collection is not None:
        from .experience_sampling import validate_contract
        validate_contract(collection)
    resolve_protocol(descriptor['protocol'], continuation, config)
    declared = active['target_contract'].get('retention_founder_checkpoint_sha256')
    if declared is not None and declared != descriptor['retention_founder_checkpoint_sha256']:
        raise ValueError('Checkpoint and package declare different original retention founders')
    initial = active['hashes']['checkpoint_sha256'] == descriptor['initial_checkpoint_sha256']
    if initial:
        if active['hashes']['target_contract_sha256'] != descriptor['initial_training_target_sha256']:
            raise ValueError('Initial checkpoint training semantics changed')
        _training_provenance(active)
    else:
        target = active['target_contract']
        native = descriptor['protocol']['native_contract']
        if (target.get('practice_wave_sha256') != package['wave_sha256']
                or target.get('schema') != PREFERENCE_SCHEMA or target.get('is_return_or_Q') is not False
                or target.get('native_contract_sha256') != digest(canonical(native))
                or target.get('native_protocol_sha256') != digest(canonical(descriptor['protocol']))
                or target.get('native_horizon_tics') != config.feedback_horizon_tics
                or target.get('retention_founder_checkpoint_sha256') != descriptor['retention_founder_checkpoint_sha256']):
            raise ValueError('Active checkpoint does not belong to this practice wave')
        _training_provenance(active)
    return {'package': copy.deepcopy(package), 'founder': founder, 'continuation': continuation,
            'config': config, 'protocol': copy.deepcopy(descriptor['protocol']),
            'experience_collection': copy.deepcopy(collection),
            'wave_sha256': package['wave_sha256']}


def prepare_wave_directory(base, resolved):
    """One immutable wave identity; no implicit migration of existing queues."""
    from .practice import atomic_json
    path = Path(base)/'practice_waves'/resolved['wave_sha256']
    path.mkdir(parents=True, exist_ok=True)
    identity = path/'wave.json'
    descriptor = resolved['package']['descriptor']
    if identity.exists():
        import json
        if canonical(json.loads(identity.read_text())) != canonical(descriptor):
            raise ValueError('Existing practice wave custody differs')
    else:
        if any(path.iterdir()):
            raise ValueError('Practice state exists without its wave descriptor')
        atomic_json(identity, descriptor)
    return path


def main():
    """Create a portable package only; never deploy, select or enable it."""
    import argparse
    import json
    from .brain import write_bundle
    from .practice import PracticeConfig
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--active', type=Path, required=True)
    parser.add_argument('--founder', type=Path, required=True)
    parser.add_argument('--continuation', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True,
                        help='Explicit PracticeConfig JSON, including chosen horizon and resource bounds')
    parser.add_argument('--wave-name', required=True)
    parser.add_argument('--collection-stride', type=int, choices=(1,32,64), default=None,
                        help='Explicit prospective collection gene; omitted preserves historical every-action custody')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError('Refuse overwriting an existing deployment package')
    config = PracticeConfig(**json.loads(args.config.read_text()))
    packed = make_package(args.active, args.founder, args.continuation,
                          config=config, wave_name=args.wave_name, collection_stride=args.collection_stride)
    resolved = unpack_package(packed)
    write_bundle(args.out, packed)
    print(canonical({'path': str(args.out), 'wave_sha256': resolved['wave_sha256'],
                     'native_contract': resolved['protocol']['native_contract'],
                     'checkpoint_sha256': packed['hashes']['checkpoint_sha256'],
                     'learning_enabled': False, 'deployment_performed': False}))


if __name__ == '__main__':
    main()
