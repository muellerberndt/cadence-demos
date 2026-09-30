"""Read-only audit of existing artifacts; run on the AWS host, print a small receipt.

No training, native environment, target admission, file mutation, or export.
"""
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time

for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import numpy as np

ROOT = Path('/home/ec2-user/doom-v3-20260929')
sys.path.insert(0, str(ROOT / 'code/navigation_novelty_01'))
os.environ['CADENCE_SRC'] = str(ROOT / 'cadence/src')
from v3.brain import load_bundle, query
from v3.interface import ACTION_NAMES, canonical, digest
from v3.practice import preference_target


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


started = time.monotonic()
nav = ROOT / 'runs/navigation_novelty_01'
initial = read(nav / 'initial.json')
candidate = read(nav / 'visible_novelty/bundle.json')
seed = candidate['metadata']['seed_replay']
seed_map = {row['row_id']: row for row in seed}
receipt = dict(schema='doom-learning-diagnosis/1', read_only=True,
    initial_checkpoint=initial['hashes']['checkpoint_sha256'],
    candidate_checkpoint=candidate['hashes']['checkpoint_sha256'],
    source_sha256={name: sha(ROOT / 'code/navigation_novelty_01/v3' / name)
                   for name in ['brain.py', 'practice.py', 'training.py']},
    replay_pool_tasks=dict(collections.Counter(r['task'] for r in seed)),
    source_artifacts={}, admission_coverage={})
native_tasks = {}
for relative in ['datasets/practice_horizon_01/fixed128_v2',
                 'runs/practice_repeat_01/collection0/fixture',
                 'runs/practice_repeat_01/collection1/fixture']:
    path = ROOT / relative / 'records.json.gz'
    receipt['source_artifacts'][str(path)] = sha(path)
    with gzip.open(path, 'rt') as stream:
        for record in json.load(stream):
            native_tasks[digest(canonical(record))] = record['task']

for relative in ['practice_horizon_01/h144', 'practice_repeat_01/life0',
                 'practice_repeat_01/life1', 'replay_ratio_01/life0_old8',
                 'replay_ratio_01/life1_old8', 'replay_ratio_01/life0_old24',
                 'replay_ratio_01/life1_old24']:
    path = ROOT / 'runs' / relative / 'events.jsonl'
    receipt['source_artifacts'][str(path)] = sha(path)
    rows = dict(seed_map)
    admissions = []
    native_targets = []
    for line in path.read_text().splitlines():
        event = json.loads(line)
        if 'example' in event:
            example = event['example']
            example['task'] = native_tasks[example['row_id']]
            rows[example['row_id']] = example
            native_targets.append(example)
        if event['kind'] == 'admission':
            batch = [rows[key] for key in event['row_ids']]
            new, old = batch[:8], batch[8:]
            admissions.append(dict(update=len(admissions)+1, accepted=event['admitted'],
                checkpoint=event['candidate_checkpoint'],
                new_tasks=dict(collections.Counter(r['task'] for r in new)),
                old_tasks=dict(collections.Counter(r['task'] for r in old)),
                bootstrap_basic=sum(r['source'] == 'bootstrap_seed' and r['task'] == 'basic' for r in old),
                bootstrap_count=sum(r['source'] == 'bootstrap_seed' for r in old),
                native_basic=sum(r['source'] != 'bootstrap_seed' and r['task'] == 'basic' for r in batch),
                examples=len(batch)))
    receipt['admission_coverage'][relative] = admissions

nav_batches = []
for path in sorted((nav / 'visible_novelty').glob('repair*-input.json')):
    batch = read(path)
    receipt['source_artifacts'][str(path)] = sha(path)
    nav_batches.append(dict(file=path.name,
        tasks=dict(collections.Counter(r.get('task', 'navigation') for r in batch)),
        sources=dict(collections.Counter(r['source'] for r in batch)),
        old_tasks=dict(collections.Counter(r.get('task', 'navigation') for r in batch[8:])),
        basic_rows=sum(r.get('task') == 'basic' for r in batch),
        mean_targets=np.mean([r['targets'] for r in batch], axis=0).tolist()))
receipt['navigation_batches'] = nav_batches

lessons = []
with gzip.open(nav / 'feedback.jsonl.gz', 'rt') as stream:
    for line in stream:
        row = json.loads(line)
        answer = row['feedback']
        values = np.array(answer['novelty_labels'])
        native = np.array(answer['native_control_labels'])
        lesson = preference_target(values)
        if lesson is not None:
            k = len(lesson['best_actions'])
            lessons.append(dict(index=row['index'], winners=lesson['best_actions'],
                native_range=float(np.ptp(native)),
                utility_gap=float(values.max()-np.sort(values)[-k-1]),
                target_margin=float(.8/k), target_l2=float(np.linalg.norm(lesson['targets'])),
                hundredth_bonus_same_targets=preference_target(native+(values-native)/100)['targets'] == lesson['targets']))
receipt['navigation_target_geometry'] = lessons

before_brain, _ = load_bundle(initial, device='cpu')
after_brain, _ = load_bundle(candidate, device='cpu')
snapshots = [brain.snapshot() for brain in [before_brain, after_brain]]
basic_rows = [r for r in seed if r['task'] == 'basic']
measurements = []
for row in basic_rows:
    a = query(before_brain, row['inputs'])
    b = query(after_brain, row['inputs'])
    assert a['qualified'] and b['qualified']
    expected = int(np.argmax(row['targets']))
    measurements.append(dict(row_id=row['row_id'], teacher=expected,
        before=a['action'], after=b['action'],
        before_teacher_margin=float(a['scores'][expected]-max(v for i,v in enumerate(a['scores']) if i != expected)),
        after_teacher_margin=float(b['scores'][expected]-max(v for i,v in enumerate(b['scores']) if i != expected)),
        score_l2=float(np.linalg.norm(np.array(b['scores'])-a['scores']))))
assert snapshots == [brain.snapshot() for brain in [before_brain, after_brain]]
receipt['basic_bootstrap_unclamped_queries'] = dict(rows=measurements,
    all_qualified=True, snapshots_unchanged=True, queries=2*len(measurements),
    before_teacher_agreement=sum(r['before'] == r['teacher'] for r in measurements),
    after_teacher_agreement=sum(r['after'] == r['teacher'] for r in measurements),
    changed_actions=sum(r['before'] != r['after'] for r in measurements),
    interpretation='Existing bootstrap training inputs; not fresh gameplay and not a competence metric')

s0, s1 = [json.loads(s) for s in snapshots]
dw = np.array(s1['weights'])-s0['weights']
db = np.array(s1['biases'])-s0['biases']
population = []
for spec in s0['layout']['populations']:
    population.extend([spec['name']]*spec['patches'])
groups = collections.defaultdict(list)
for index, (kind, source, target) in enumerate(before_brain.graph.edges):
    groups[population[target] + ':' + kind].append(float(dw[index]))
receipt['parameter_delta_l2_squared'] = {name: float(np.dot(v,v)) for name,v in groups.items()}
receipt['parameter_delta_l2_squared']['biases'] = float(np.dot(db,db))
receipt['policy_bias_delta'] = {name:float(db[-20+i]) for i,name in enumerate(ACTION_NAMES)}
receipt['seconds'] = time.monotonic()-started
print(json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False))
