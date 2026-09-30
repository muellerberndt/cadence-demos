"""Prepare an allowlisted source directory and private AWS baby-Lab data.

This helper never copies credentials, corpora, logs, host checkpoints or cloud
configuration; never opens a port; and never starts/stops a process. The owner
deploys the returned directory beside the matching frozen Cadence core.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import time

from .tasks import sha_file

LAB = Path(__file__).resolve().parents[1]
SOURCES = (
    'server.py', 'brainlab.py', 'doomlab.py', 'layouts.py', 'norms.py',
    'static/index.html', 'static/brain3d.js',
    'v2/lab_adapter.py', 'v2/models.py', 'v2/basic_env.py', 'v2/exporter.py',
    'v2/online.py', 'v2/journal.py', 'v2/parallel_feedback.py',
    'v3/brain.py', 'v3/interface.py', 'v3/tasks.py', 'v3/runtime.py',
    'v3/practice.py', 'v3/practice_protocol.py', 'v3/protocol_smoke.py', 'v3/native_feedback.py', 'v3/native_feedback_long.py',
    'v3/collection.py', 'v3/training.py',
    'v3/teacher.py', 'v3/evaluate.py', 'v3/watch_training.py', 'v3/lab_deployment.py',
)


def pack(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    files = {}
    for name in SOURCES:
        source = LAB/name
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        files[name] = {'sha256': sha_file(target), 'bytes': target.stat().st_size}
    receipt = {'schema': 'doom-v3-lab-source-package/1', 'created_unix': time.time(),
        'files': files, 'bytes': sum(row['bytes'] for row in files.values()),
        'dependency_contract': 'Existing Python3.11+ environment with numpy, torch, aiohttp, pillow, ViZDoom1.3.1; exact matching Cadence core supplied via CADENCE_SRC/PYTHONPATH',
        'data_included': False, 'credentials_included': False, 'listening_port': None,
        'deployment': 'Private127.0.0.1:8667 process, browser access through owner SSH tunnel'}
    (destination/'source_manifest.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


def initialize(bundle_path, *, root=LAB, task='basic', source_platform=None,
               bootstrap_dataset=None, doom_wad=None):
    from .brain import load_bundle, write_bundle
    from .runtime import prepare_staging_bundle, validate_deployment
    from .practice import attach_seed_replay, seed_replay_from_dataset, validate_seed_replay, atomic_json
    from .interface import canonical, digest
    root = Path(root).resolve()
    if (root/'data').exists():
        raise FileExistsError('Refuse replacing an existing Lab data directory')
    _, bundle = load_bundle(bundle_path, device='python')
    if bootstrap_dataset:
        bundle = attach_seed_replay(bundle, seed_replay_from_dataset(bootstrap_dataset, bundle))
    replay = bundle.get('metadata', {}).get('seed_replay')
    if not replay or digest(canonical(replay)) != bundle['metadata'].get('seed_replay_sha256'):
        raise ValueError('Browser baby needs its finite, hash-bound bootstrap replay before initialization')
    validate_seed_replay(replay)
    bundle = prepare_staging_bundle(bundle, task, source_platform=source_platform)
    # This command prepares explicitly unvalidated staging, never production.
    os.environ['DOOM_LAB_PORT'] = '8667'
    os.environ['DOOM_LAB_ENABLE_V3'] = '1'
    validate_deployment(bundle)
    registry_id = 'baby-' + ''.join(c if c.isascii() and (c.isalnum() or c in '-_') else '-'
                                    for c in bundle['model_id'])[:80]
    target = root/'data/models/v3'/registry_id/'bundle.json'
    write_bundle(target, bundle)
    # Student creates its inert legacy startup scaffold before the queued v3
    # swap. These are declared neutral coordinates, not fitted student features;
    # the deployed actor uses only the bundle's own verified normalization.
    neutral = {'clip': 3., 'scale': .2,
               'periphery': {'mean': [0.]*640, 'std': [1.]*640},
               'fovea': {'mean': [0.]*384, 'std': [1.]*384}}
    atomic_json(root/'data/live_norms.json', neutral)
    atomic_json(root/'data/current_model.json', {'id': registry_id})
    if doom_wad:
        path = Path(doom_wad).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        (root/'wads').mkdir(exist_ok=True)
        (root/'wads/doom1.wad').symlink_to(path)
    receipt = {'schema': 'doom-v3-private-lab-initialization/1', 'created_unix': time.time(),
        'registry_id': registry_id, 'bundle': str(target),
        'checkpoint_sha256': bundle['hashes']['checkpoint_sha256'],
        'seed_replay_sha256': bundle['metadata']['seed_replay_sha256'], 'seed_replay_rows': len(replay),
        'genome': bundle['genome'], 'task': task, 'deployment_validation': 'not_evaluated',
        'source_platform': bundle['metadata']['source_platform'],
        'target_platform': bundle['metadata']['deployment_validation']['target_platform'],
        'initial_mode': 'idle', 'initial_learning_enabled': False, 'process_started': False}
    atomic_json(root/'initialization.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('pack'); export.add_argument('--out', type=Path, required=True)
    init = sub.add_parser('init')
    init.add_argument('--bundle', type=Path, required=True)
    init.add_argument('--root', type=Path, default=LAB)
    init.add_argument('--task', default='basic')
    init.add_argument('--source-platform', type=Path)
    init.add_argument('--bootstrap-dataset', type=Path)
    init.add_argument('--doom-wad', type=Path)
    args = parser.parse_args()
    if args.command == 'pack':
        receipt = pack(args.out)
        print(json.dumps({'out': str(args.out), 'bytes': receipt['bytes'], 'files': len(receipt['files'])}))
    else:
        source = json.loads(args.source_platform.read_text()) if args.source_platform else None
        print(json.dumps(initialize(args.bundle, root=args.root, task=args.task, source_platform=source,
            bootstrap_dataset=args.bootstrap_dataset, doom_wad=args.doom_wad)))


if __name__ == '__main__':
    main()
