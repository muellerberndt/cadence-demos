"""Evaluate immutable winners locally, then derive a source-bound v1 deployment.

A passed operational receipt is finite platform-specific evidence. It neither
replaces the original Linux confirmation nor establishes full-game competence.
No command in this module trains or automatically enables a learner.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import time

from .brain import load_bundle, write_bundle
from .interface import canonical, digest
from .practice import PracticeConfig, atomic_json, attach_seed_replay
from .runtime import platform_identity, validate_deployment
from .tasks import sha_file, task_identity

LAB = Path(__file__).resolve().parents[1]


def source_identity():
    return {str(p.relative_to(LAB)): sha_file(p) for p in
            sorted([LAB/'brainlab.py', LAB/'server.py'] +
                   [p for p in (LAB/'v1').glob('*.py') if not p.name.startswith('test_')])}


def _passing_rows(rows, protocol):
    return (len(rows) == 16 and len({r.get('seed') for r in rows}) == 16 and
        set(r.get('seed') for r in rows) == set(protocol['seeds']) and
        all(r.get('task_id') == 'basic' and r.get('status') == 'complete' and
            type(r.get('queries')) is int and r['queries'] > 0 and
            r['queries'] == r.get('qualified_queries') and r.get('fallback_actions') == 0 and
            r.get('checkpoint_sha256') == protocol['checkpoint_sha256'] for r in rows) and
        sum(r.get('success') is True for r in rows) >= 12)


def validate_evidence(path, bundle_path, active):
    from .evaluate import summarize
    path, bundle_path = Path(path), Path(bundle_path)
    receipt = json.loads(path.read_text())
    protocol = json.loads((path.parent/'protocol.json').read_text())
    criteria = {'all_scheduled_complete': True, 'all_queries_qualified': True,
                'fallback_actions': 0, 'minimum_successes': 12, 'scheduled': 16}
    if (receipt.get('schema') != 'doom-v1-local-operational-validation/1'
            or receipt.get('status') != 'passed' or receipt.get('training_performed') is not False
            or receipt.get('criteria') != criteria or len(receipt.get('seeds', [])) != 16
            or len(set(receipt['seeds'])) != 16
            or receipt.get('checkpoint_sha256') != active['hashes']['checkpoint_sha256']
            or receipt.get('bundle_sha256') != sha_file(bundle_path)
            or receipt.get('platform') != platform_identity()
            or receipt.get('task_identity') != task_identity('basic')
            or receipt.get('source_sha256') != source_identity()
            or any(receipt.get(k) != v for k, v in protocol.items())):
        raise ValueError('A passed, unchanged local operational validation of these exact bytes is required')
    for relative, expected in [('native/summary.json', receipt['native_summary_sha256']),
                               ('native/outcomes.jsonl', receipt['outcomes_sha256']),
                               ('protocol.json', receipt['protocol_sha256'])]:
        if sha_file(path.parent/relative) != expected:
            raise ValueError('Local validation custody differs: '+relative)
    rows = [json.loads(line) for line in (path.parent/'native/outcomes.jsonl').read_text().splitlines()]
    native = json.loads((path.parent/'native/summary.json').read_text())
    summary = summarize(rows, [('basic', seed) for seed in protocol['seeds']])
    if (not _passing_rows(rows, protocol) or receipt['summary'] != native
            or any(native.get(k) != v for k, v in summary.items())
            or native.get('freeze_sha256') != sha_file(path.parent/'native/freeze.json')):
        raise ValueError('Native outcomes do not satisfy the frozen local validation criteria')
    for row in rows:
        trace = path.parent/'native/episodes'/('basic_'+str(row['seed']))/'decisions.jsonl'
        if sha_file(trace) != row['decisions_sha256']:
            raise ValueError('Native trace differs from its retained outcome')
    return receipt


def evaluate(bundle, output, *, seed_start=1600000000, episodes=16, workers=2):
    from .evaluate import campaign
    if type(episodes) is not int or episodes != 16:
        raise ValueError('This operational protocol schedules exactly16 episodes')
    if type(seed_start) is not int or seed_start < 0 or seed_start+episodes > 2**32:
        raise ValueError('Native seeds must be uint32')
    if workers not in (1, 2, 4):
        raise ValueError('Local operational evaluation uses1,2 or4 workers')
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    _, value = load_bundle(bundle, device='python')
    identity = source_identity()
    protocol = {'schema': 'doom-v1-local-operational-validation/1',
        'created_unix': time.time(), 'source_sha256': identity,
        'bundle_sha256': sha_file(bundle), 'checkpoint_sha256': value['hashes']['checkpoint_sha256'],
        'platform': platform_identity(), 'task_identity': task_identity('basic'),
        'task': 'basic', 'seeds': list(range(seed_start, seed_start+episodes)),
        'workers': workers, 'episode_wall_seconds': 60,
        'criteria': {'all_scheduled_complete': True, 'all_queries_qualified': True,
                     'fallback_actions': 0, 'minimum_successes': 12, 'scheduled': 16},
        'scope': '16-case local Basic operational validation; no training, no global competence claim'}
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output/'protocol.json', protocol)
    result = campaign(bundle, ['basic'], protocol['seeds'], output/'native', workers=workers, wall_seconds=60)
    rows = [json.loads(line) for line in (output/'native/outcomes.jsonl').read_text().splitlines()]
    group = result['tasks']['basic']
    passed = _passing_rows(rows, protocol) and source_identity() == identity

    receipt = {**protocol, 'protocol_sha256': sha_file(output/'protocol.json'),
        'status': 'passed' if passed else 'failed', 'summary': result,
        'native_summary_sha256': sha_file(output/'native/summary.json'),
        'outcomes_sha256': sha_file(output/'native/outcomes.jsonl'),
        'finished_unix': time.time(), 'training_performed': False}
    atomic_json(output/'receipt.json', receipt)
    return receipt


def prepare(bundle, founder, evaluation, source_platform, *, name, data_dir=LAB/'data', activate=True):
    from .practice_protocol import make_package
    bundle_path, evaluation_path = Path(bundle).resolve(), Path(evaluation).resolve()
    _, active = load_bundle(bundle_path, device='python')
    _, original = load_bundle(founder, device='python')
    receipt = validate_evidence(evaluation_path, bundle_path, active)
    source = json.loads(Path(source_platform).read_text()) if not isinstance(source_platform, dict) else copy.deepcopy(source_platform)
    if set(source) != {'system', 'machine', 'engine_binary_sha256'}:
        raise ValueError('Declare the original native platform identity')
    if not name or len(name) > 80 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in name):
        raise ValueError('Registry name must be short alphanumeric text with hyphens/underscores')
    data_dir = Path(data_dir).resolve()
    target = data_dir/'models'/name/'bundle.json'
    if target.parent.exists():
        raise FileExistsError('Refuse overwriting an existing registry model or practice custody')
    rows = active.get('metadata', {}).get('seed_replay')
    if not rows:
        raise ValueError('The preserved winner must include its finite verified seed replay')
    original = attach_seed_replay(original, rows)
    continuation = copy.deepcopy(active)
    config = PracticeConfig(gate_tasks=('basic',), gate_seeds=tuple(range(1220200000,1220200032)),
        feedback_horizon_tics=144, feedback_workers=4, gate_workers=2,
        new_rows=8, candidate_lifetime=4)
    packed = make_package(active, original, continuation, config=config,
        wave_name='v1_local_'+name, collection_stride=64)
    packed['metadata'].update(label=name+' · Basic · local16-case validation',
        role='confirmed' if name.startswith('confirmed') else 'optional_confirmed',
        deployment_task='basic', deployment_identity=task_identity('basic'), source_platform=source,
        original_bundle_sha256=sha_file(bundle_path),
        original_checkpoint_sha256=active['hashes']['checkpoint_sha256'],
        deployment_validation={'status': 'passed', 'source_platform': source,
            'target_platform': platform_identity(), 'checkpoint_sha256': active['hashes']['checkpoint_sha256'],
            'receipt_sha256': sha_file(evaluation_path), 'scope': receipt['scope'],
            'successes': receipt['summary']['successes'], 'scheduled': receipt['summary']['scheduled']})
    validate_deployment(packed)
    write_bundle(target, packed)
    if activate:
        atomic_json(data_dir/'current_model.json', {'id': name})
    report = {'schema': 'doom-v1-derived-deployment/1', 'model_id': name,
        'bundle': str(target), 'bundle_sha256': sha_file(target),
        'checkpoint_sha256': packed['hashes']['checkpoint_sha256'],
        'practice_wave_sha256': packed['metadata']['practice_package']['wave_sha256'],
        'original_bundle_sha256': sha_file(bundle_path), 'evaluation_sha256': sha_file(evaluation_path),
        'activated_pointer': activate, 'process_started': False, 'learning_enabled': False,
        'source_sha256': source_identity()}
    atomic_json(target.parent/'deployment.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    evaluation = sub.add_parser('evaluate')
    evaluation.add_argument('--bundle', required=True); evaluation.add_argument('--out', required=True)
    evaluation.add_argument('--seed-start', type=int, default=1600000000)
    evaluation.add_argument('--episodes', type=int, default=16)
    evaluation.add_argument('--workers', type=int, default=2)
    preparation = sub.add_parser('prepare')
    for arg in ('bundle', 'founder', 'evaluation', 'source-platform', 'name'):
        preparation.add_argument('--'+arg, required=True)
    preparation.add_argument('--data-dir', type=Path, default=LAB/'data')
    preparation.add_argument('--no-activate', action='store_true')
    args = parser.parse_args()
    if args.command == 'evaluate':
        result = evaluate(args.bundle, args.out, seed_start=args.seed_start, episodes=args.episodes, workers=args.workers)
        print(json.dumps({'status': result['status'], 'summary': result['summary']}))
        if result['status'] != 'passed': raise SystemExit(1)
    else:
        print(json.dumps(prepare(args.bundle, args.founder, args.evaluation, args.source_platform,
                                name=args.name, data_dir=args.data_dir, activate=not args.no_activate)))


if __name__ == '__main__': main()
