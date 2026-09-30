"""Bounded native protocol/repair/recovery smoke, never a deployment or gate.

The owner must apply an external process-group wall cap. The diagnostic uses
one new plus one retained row per repair and never offers an actor to a Lab.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import time

from .brain import Actor, load_bundle
from .interface import canonical, digest
from .practice import PracticeLearner, atomic_json
from .practice_protocol import unpack_package
from .tasks import DoomEnv


def run(path, output, *, seed=1300900000, wall_seconds=120):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    _, bundle = load_bundle(path, device='cpu')
    wave = unpack_package(bundle)
    if wave is None:
        raise ValueError('An explicit portable practice package is required')
    config = replace(wave['config'], new_rows=1, candidate_lifetime=4)
    smoke_id = digest(canonical({'package_wave': wave['wave_sha256'], 'config': asdict(config), 'role': 'native_diagnostic'}))
    atomic_json(output/'freeze.json', {'schema': 'doom-protocol-native-smoke/1',
        'created_unix': time.time(), 'source_package_sha256': bundle['hashes']['practice_package_sha256'],
        'protocol': wave['protocol'], 'config': asdict(config), 'diagnostic_wave_sha256': smoke_id,
        'seeds': list(range(seed, seed+3)), 'wall_seconds': wall_seconds,
        'scope': 'Native feedback, public repair and exact recovery only; no gameplay improvement claim or Lab mutation'})
    actor = Actor(bundle)
    kwargs = dict(config=config, initial_bundle=bundle, continuation_bundle=wave['continuation'],
                  native_protocol=wave['protocol'], practice_wave_sha256=smoke_id)
    learner = PracticeLearner.from_bundle(wave['founder'], journal_path=output/'practice.jsonl', **kwargs)
    started = time.monotonic(); records = []; before = learner.candidate.snapshot(); failure = None
    try:
        learner.set_enabled(True)
        for index in range(3):
            if time.monotonic()-started >= wall_seconds:
                raise TimeoutError('Native smoke wall bound reached')
            actor.reset()
            with DoomEnv('basic', seed+index, teacher=False) as env:
                raw = env.observe(); decision = actor.choose(raw)
                if not decision['qualified']:
                    raise ValueError('Diagnostic actor refused; no engine action executed')
                transition = env.step(decision['action'])
                actor.acknowledge(raw, decision['action'], transition['tics'])
                record = {'task': 'basic', 'seed': seed+index, 'episode_id': 'protocol-smoke-'+smoke_id+':'+str(index),
                    'step_index': 0, 'prefix_actions': [], 'prefix_outcomes': [],
                    'raw_sha256': decision['raw_sha256'], 'inputs': decision['inputs'],
                    'executed_action': decision['action'], 'transition': transition,
                    'policy_checkpoint_sha256': decision['checkpoint_sha256'], 'qualified': True,
                    'fallback': False, 'behavior_source': 'autonomous'}
            records.append(record)
            atomic_json(output/'records.json', records)
            if not learner.submit_transition(record):
                raise RuntimeError('Diagnostic queue refused durable input')
            while True:
                status = learner.status()
                atomic_json(output/'status.json', {'phase': 'native_smoke', 'seconds': time.monotonic()-started, **status})
                if status['error']: raise RuntimeError(status['error'])
                if status['processed_transitions'] >= index+1 and not status['busy']: break
                if time.monotonic()-started >= wall_seconds: raise TimeoutError('Native smoke wall bound reached')
                time.sleep(.1)
            if status['updates']: break
    except Exception as error:
        failure = type(error).__name__+': '+str(error)
    finally:
        learner.close(wait=True)
    state_before = json.loads((output/'practice_continuation.json').read_text()) if (output/'practice_continuation.json').exists() else None
    restored = None
    checks = {'actual_records_qualified': bool(records) and all(r['qualified'] and not r['fallback'] for r in records),
              'public_repair_admitted': learner.status()['updates'] >= 1 and learner.status()['accepted_examples'] >= 2,
              'parameters_or_admission_changed': learner.candidate.snapshot() != before,
              'no_gate_or_promotion': learner.status()['promotions'] == 0}
    if failure is None:
        try:
            restored = PracticeLearner.from_bundle(wave['founder'], journal_path=output/'practice.jsonl', **kwargs)
            checks['exact_candidate_restart'] = restored.candidate.snapshot() == learner.candidate.snapshot()
            checks['exact_replay_restart'] = list(restored._replay) == list(learner._replay)
            checks['exact_rng_restart'] = restored._rng.bit_generator.state == learner._rng.bit_generator.state
            checks['protocol_restart'] = restored.target == learner.target
            checks['paused_after_restart'] = not restored.status()['enabled']
        except Exception as error:
            failure = type(error).__name__+': '+str(error)
        finally:
            if restored: restored.close(wait=True)
    result = {'schema': 'doom-protocol-native-smoke-result/1', 'passed': failure is None and all(checks.values()),
              'checks': checks, 'error': failure, 'seconds': time.monotonic()-started,
              'status': learner.status(), 'contexts': len(records), 'lab_control_requests': 0,
              'candidate_checkpoint_sha256': digest(learner.candidate.snapshot()),
              'retained_continuation_bytes': (output/'practice_continuation.json').stat().st_size if state_before else None}
    atomic_json(output/'summary.json', result)
    print(canonical(result), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--wall-seconds', type=float, default=120)
    args = parser.parse_args()
    if not 0 < args.wall_seconds <= 120:
        raise ValueError('Smoke budget must be positive and at most120seconds')
    result = run(args.bundle, args.out, wall_seconds=args.wall_seconds)
    raise SystemExit(0 if result['passed'] else 1)
