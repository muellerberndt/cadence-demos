"""Bounded expert/DAgger experience collection; bulk runs belong on AWS.

The actor sees pixels and actual action history only. Teacher interventions,
failed queries, native outcomes and incomplete attempts remain separate records.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import gzip
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import tempfile
import time

for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
              'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'
import numpy as np

from .interface import contract, canonical, digest, RAW_SHAPE
from .tasks import DoomEnv, get_task, task_identity, sha_file
from .teacher import GeometryTeacher


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        stream.write(canonical(value)+'\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def collect_episode(job):
    output = Path(job['output']); output.mkdir(parents=True, exist_ok=False)
    spec = get_task(job['task'])
    if spec.split != 'train':
        raise ValueError('Training collection is confined to declared training maps/tasks')
    rng = np.random.default_rng(job['seed'])
    actor = None
    for name,expected in job['source_sha256'].items():
        if sha_file(Path(__file__).with_name(name)) != expected:
            raise ValueError('Collector source changed after freeze: '+name)
    if job['student_bundle']:
        from .brain import Actor
        if sha_file(job['student_bundle']) != job['student_bundle_sha256']:
            raise ValueError('Student bundle changed after collection freeze')
        actor = Actor(job['student_bundle'], device='cpu')
    started = time.monotonic(); cutoff = None
    shape = (job['max_decisions'], *RAW_SHAPE)
    frames = np.lib.format.open_memmap(output/'frames.partial.npy', mode='w+', dtype='uint8', shape=shape)
    proposed, executed, tics, raw_hashes = [], [], [], []
    counts = dict(teacher_actions=0, student_actions=0, warmup_actions=0, query_attempts=0, qualified_queries=0)
    receipt = dict(schema='doom-v3-collection-episode/1', task=job['task'], seed=job['seed'],
                   status='running', source='privileged_geometry_teacher', scheduled=job,
                   actor_checkpoint_sha256=None if actor is None else actor.bundle['hashes']['checkpoint_sha256'])
    atomic_json(output/'status.json', receipt)
    try:
        with DoomEnv(spec, job['seed'], teacher=True) as env, gzip.open(output/'events.jsonl.gz', 'wt') as stream:
            teacher = GeometryTeacher(spec)
            for step in range(job['max_decisions']):
                if env.finished: break
                if time.monotonic()-started > job['wall_seconds']:
                    cutoff = 'collection_wall_cap'; break
                raw = env.observe(); decision = teacher.act(env)
                warmup = step < job.get('warmup_decisions',0)
                use_teacher = actor is None or rng.random() < job['expert_probability']
                prediction = None
                if not use_teacher and not warmup:
                    counts['query_attempts'] += 1
                    prediction = actor.choose(raw)
                    if not prediction['qualified']:
                        cutoff = 'student_query_refused'
                        stream.write(canonical({'event': 'query_refused', 'step': step,
                                     'teacher_proposal': decision.record(), 'raw_sha256': digest(raw.tobytes())})+'\n')
                        break
                    counts['qualified_queries'] += 1
                action = (int(rng.choice([1,2,3,4,5,6])) if warmup else
                          decision.action if use_teacher else prediction['action'])
                transition = env.step(action)
                teacher.acknowledge(action, transition['tics'])
                # Even a teacher intervention is committed to the student's
                # external sensory history; proposed actions never advance it.
                if actor is not None:
                    if use_teacher or warmup:
                        actor.history.acknowledge(raw, action, transition['tics'])
                    else:
                        actor.acknowledge(raw, action, transition['tics'])
                frames[step] = raw
                proposed.append(decision.action); executed.append(action); tics.append(transition['tics'])
                raw_hashes.append(digest(raw.tobytes()))
                counts['warmup_actions' if warmup else 'teacher_actions' if use_teacher else 'student_actions'] += 1
                stream.write(canonical({'event': 'executed_transition', 'step': step,
                              'raw_sha256': raw_hashes[-1], 'teacher_proposal': decision.record(),
                              'behavior_source': 'declared_random_warmup' if warmup else 'teacher_intervention' if use_teacher else 'student',
                              'student_qualified': None if use_teacher or warmup else True,
                              'transition': transition})+'\n')
                if step % 128 == 0:
                    frames.flush(); stream.flush()
                    atomic_json(output/'status.json', {**receipt, **counts, 'decisions':len(executed),
                                'wall_seconds':time.monotonic()-started})
            else:
                if not env.finished: cutoff = 'collection_decision_cap'
            outcome = env.outcome(cutoff)
        frames.flush()
        np.savez_compressed(output/'frames.npz', frames=frames[:len(executed)],
                            teacher_actions=np.asarray(proposed, dtype=np.int16),
                            executed_actions=np.asarray(executed, dtype=np.int16),
                            tics=np.asarray(tics, dtype=np.int8))
        frames = None
        (output/'frames.partial.npy').unlink()
        receipt.update(status='complete' if cutoff is None else 'capped_or_refused', outcome=outcome,
                       decisions=len(executed), **counts, wall_seconds=time.monotonic()-started,
                       frames_sha256=sha_file(output/'frames.npz'),
                       events_sha256=sha_file(output/'events.jsonl.gz'),
                       teacher_proposed_action_counts=np.bincount(proposed,minlength=20).tolist(),
                       interpreted_as='training experience; assisted outcomes are never autonomous student scores')
    except BaseException as error:
        if frames is not None: frames.flush()
        receipt.update(status='failed', error=f'{type(error).__name__}: {error}',
                       decisions=len(executed), **counts, wall_seconds=time.monotonic()-started)
    atomic_json(output/'receipt.json', receipt); atomic_json(output/'status.json', receipt)
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tasks', nargs='+', required=True)
    p.add_argument('--episodes-per-task', type=int, default=2)
    p.add_argument('--seed-start', type=int, default=1100000000)
    p.add_argument('--workers', type=int, default=6)
    p.add_argument('--wall-seconds', type=float, default=240)
    p.add_argument('--max-decisions', type=int, default=5250)
    p.add_argument('--student-bundle', type=Path)
    p.add_argument('--expert-probability', type=float, default=1.)
    p.add_argument('--warmup-decisions',type=int,default=0,
                   help='Finite random move/turn prefix, recorded as exploratory interventions')
    p.add_argument('--out', type=Path, required=True)
    args=p.parse_args()
    if (not 0 <= args.expert_probability <= 1 or not 1 <= args.workers <= 64
            or args.episodes_per_task < 1 or args.wall_seconds <= 0 or args.max_decisions < 1
            or not 0 <= args.warmup_decisions <= 64):
        raise ValueError('Invalid collection bounds')
    specs=[get_task(task) for task in args.tasks]
    if any(spec.split != 'train' for spec in specs):
        raise ValueError('No development or reserved maps may enter a training corpus')
    args.out.mkdir(parents=True, exist_ok=False)
    source={name:sha_file(Path(__file__).with_name(name)) for name in
            ('collection.py','tasks.py','teacher.py','interface.py','brain.py')}
    source_dir=args.out/'sources';source_dir.mkdir()
    for name in source:
        shutil.copyfile(Path(__file__).with_name(name),source_dir/name)
        if sha_file(source_dir/name)!=source[name]:raise ValueError('Source changed during freeze')
    bundle_path=None;bundle_hash=None;boundary=contract()
    if args.student_bundle is not None:
        from .brain import load_bundle
        _,bundle=load_bundle(args.student_bundle,device='python')
        bundle_path=args.out/'student_bundle.json'
        atomic_json(bundle_path,bundle)
        bundle_path=bundle_path.resolve();bundle_hash=sha_file(bundle_path);boundary=bundle['contract']
    jobs=[]
    for index, spec in enumerate(specs):
        for episode in range(args.episodes_per_task):
            jobs.append(dict(task=spec.task_id, seed=args.seed_start+index*1000+episode,
                             output=str(args.out/f'episode-{len(jobs):04d}'),
                             wall_seconds=args.wall_seconds, max_decisions=args.max_decisions,
                             student_bundle=None if bundle_path is None else str(bundle_path),
                             student_bundle_sha256=bundle_hash,source_sha256=source,
                             warmup_decisions=args.warmup_decisions,
                             expert_probability=args.expert_probability))
    freeze=dict(schema='doom-v3-collection-freeze/1', created_unix=time.time(),
                tasks=[task_identity(spec) for spec in specs], contract=boundary, source_sha256=source,
                jobs=jobs, workers=args.workers)
    atomic_json(args.out/'freeze.json', freeze)
    rows=[];started=time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers,mp_context=multiprocessing.get_context('spawn')) as pool:
        futures={pool.submit(collect_episode,job):job for job in jobs}
        for future in as_completed(futures):
            job=futures[future]
            try:row=future.result()
            except BaseException as error:
                row=dict(task=job['task'],seed=job['seed'],status='worker_failed',error=str(error),scheduled=job)
            rows.append(row)
            status=dict(schema='doom-v3-collection/1',scheduled=len(jobs),completed=len(rows),
                        teacher_successes=sum(bool(r.get('outcome',{}).get('success')) for r in rows),
                        failures=sum(r['status'] in ('failed','worker_failed') for r in rows),
                        decisions=sum(r.get('decisions',0) for r in rows),
                        wall_seconds=time.monotonic()-started, episodes=rows,
                        freeze_sha256=sha_file(args.out/'freeze.json'))
            atomic_json(args.out/'status.json',status)
            print(canonical({k:v for k,v in status.items() if k!='episodes'}),flush=True)
    atomic_json(args.out/'summary.json',status)


if __name__=='__main__':main()
