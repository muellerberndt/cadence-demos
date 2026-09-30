"""Frozen actual-Cadence navigation collection; no feedback or weight updates."""
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='1'
import numpy as np

from .brain import Actor, load_bundle
from .interface import canonical, digest
from .native_feedback import validate_record
from .tasks import DoomEnv, sha_file, task_identity, vizdoom_module

INITIAL='ad9b330cd1c1c582a0bb135956f87a9f8e4c0f106d80c35bb60b39c0328ef2cc'
ACTOR_FILE='844503dcdce34a253dcb3ba2689b7cd042a338b5bfd381684dfcf5ffc3237dd9'
CANDIDATE='00ab8c64026501c8fb276b7d25ab832ea5528e511d6c0762063d0df4abcfc153'
CANDIDATE_FILE='5896ab172bbe631777b823a2c23db1053a69a4799a5fb7a83a8ce752bfe5efcd'
SEEDS=list(range(1330000000,1330000016))
PINS={'brain.py':'d91ec34db618ace4e9c6f9c95bd1b7960b741cd8543ac84ac758bf6771495b99',
      'interface.py':'1e1fa1db2a42f8459a19ae9d1d456782d390f1e7939d0eb120a9d59c363977ce',
      'tasks.py':'2f807b7f8f1d7f5ab9bb886bb9efc8994bdfea2aa39b44e1a08fd3dfe852410d'}
ENGINE='4c228e1d0bd929dada21ed86e814a88cdc23204722916ca8223d07fc4426044a'


def atomic_json(path, value):
    path=Path(path); temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(canonical(value)+'\n');os.replace(temporary,path)


def selected_indices(length):
    if type(length) is not int or length<0:raise ValueError('Invalid actual decision count')
    if length==0:return []
    result=np.linspace(0,length-1,min(16,length),dtype=int).tolist()
    assert len(result)==len(set(result))==min(16,length)
    return result


def collect_episode(payload):
    initial,seed,directory=payload;out=Path(directory);out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();events=[];frames=[];inputs=[];outcome=None
    actor=Actor(initial,device='cpu');actor.reset();snapshot=actor.brain.snapshot()
    try:
        with DoomEnv('navigation',seed,teacher=False) as env,(out/'events.jsonl').open('w') as stream:
            while not env.finished:
                if time.monotonic()-started>=180:raise TimeoutError('180 second episode cap')
                raw=env.observe();answer=actor.choose(raw)
                if not answer['qualified']:raise ValueError('Unqualified query; no fallback')
                tr=env.step(answer['action']);actor.acknowledge(raw,answer['action'],tr['tics'])
                row=dict(step=len(events),raw_sha256=answer['raw_sha256'],inputs_sha256=digest(canonical(answer['inputs'])),
                    action=answer['action'],scores=answer['scores'],transition=tr,checkpoint_sha256=actor.checkpoint_hash,
                    qualified=True,fallback=False,query_seconds=answer['query_seconds'])
                events.append(row);frames.append(np.array(raw,copy=True));inputs.append(answer['inputs'])
                stream.write(canonical(row)+'\n');stream.flush()
            outcome=env.outcome()
        if actor.brain.snapshot()!=snapshot:raise ValueError('Collection mutated frozen brain')
        chosen=selected_indices(len(events));records=[]
        for index in chosen:
            event=events[index]
            records.append(validate_record(dict(task='navigation',seed=seed,episode_id=f'native_collect_16:{seed}',
                step_index=index,prefix_actions=[r['action'] for r in events[:index]],
                prefix_outcomes=[r['transition'] for r in events[:index]],raw_sha256=event['raw_sha256'],
                inputs=inputs[index],executed_action=event['action'],transition=event['transition'],
                policy_checkpoint_sha256=actor.checkpoint_hash,qualified=True,fallback=False,behavior_source='autonomous')))
        np.savez_compressed(out/'raw_frames.npz',frames=np.stack(frames))
        atomic_json(out/'selected_records.json',records)
        receipt=dict(status='complete',seed=seed,decisions=len(events),selected_indices=chosen,outcome=outcome,
            event_sha256=sha_file(out/'events.jsonl'),raw_frames_sha256=sha_file(out/'raw_frames.npz'),
            selected_records_sha256=sha_file(out/'selected_records.json'),snapshot_unchanged=True,seconds=time.monotonic()-started)
    except BaseException as error:
        if frames:np.savez_compressed(out/'partial_raw_frames.npz',frames=np.stack(frames))
        receipt=dict(status='error',seed=seed,decisions=len(events),outcome=outcome,error=repr(error),
            selected_indices=[],seconds=time.monotonic()-started)
    atomic_json(out/'receipt.json',receipt);return receipt


def run(args):
    started=time.monotonic();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    assert sha_file(args.initial)==ACTOR_FILE
    assert sha_file(args.candidate)==CANDIDATE_FILE
    _,bundle=load_bundle(args.initial,device='cpu');assert bundle['hashes']['checkpoint_sha256']==INITIAL
    _,candidate=load_bundle(args.candidate,device='cpu');assert candidate['hashes']['checkpoint_sha256']==CANDIDATE
    for field in ('contract','genome','normalization','query_budget'):assert bundle[field]==candidate[field]
    root=Path(__file__).parent
    for name,value in PINS.items():assert sha_file(root/name)==value,(name,'source mismatch')
    engine_root=Path(vizdoom_module().__file__).parent
    engine={p.name:sha_file(p) for p in [engine_root/'vizdoom',engine_root/'vizdoom.pk3',*engine_root.glob('*.so')] if p.is_file()}
    assert engine['vizdoom']==ENGINE
    shutil.copyfile(args.initial,out/'initial.json')
    shutil.copyfile(args.candidate,out/'candidate.json')
    actors={'ad9':dict(file='initial.json',checkpoint_sha256=INITIAL,file_sha256=ACTOR_FILE),
        'eta1':dict(file='candidate.json',checkpoint_sha256=CANDIDATE,file_sha256=CANDIDATE_FILE)}
    freeze=dict(schema='doom-native-navigation-actual-paired-collection/1',created_unix=time.time(),actors=actors,
        continuation='Each actor is its own frozen eventual continuation; feedback is not authorized by this collection',checkpoint_sha256=INITIAL,
        actor_file_sha256=ACTOR_FILE,actor_hashes=bundle['hashes'],contract=bundle['contract'],genome=bundle['genome'],
        normalization=bundle['normalization'],query_budget=bundle['query_budget'],task=task_identity('navigation'),
        source_sha256={p.name:sha_file(p) for p in sorted(root.glob('*.py'))},engine_binary_sha256=engine,
        core_sha256={str(p.relative_to(Path(os.environ['CADENCE_SRC']))):sha_file(p) for p in sorted(Path(os.environ['CADENCE_SRC']).rglob('*.py'))},
        seeds=SEEDS,workers=32,episode_wall_seconds=180,campaign_process_group_seconds=900,
        selection='min(16,n) unique evenly spaced actual decision indices per complete episode; round robin by temporal quantile then seed',
        failures='Retain every scheduled outcome; no replacement episode; incomplete episodes contribute no contexts',
        evidence='All pre-action uint8 pixels, qualified scores/action hashes, native transitions, selected complete history ports and exact prefixes',
        feedback=False,training=False,deployment=False)
    atomic_json(out/'freeze.json',freeze);(out/'collection').mkdir();results={}
    for name in actors:(out/'collection'/name).mkdir()
    with ProcessPoolExecutor(max_workers=32,mp_context=multiprocessing.get_context('spawn')) as pool:
        futures={pool.submit(collect_episode,(str(out/actor['file']),seed,str(out/'collection'/name/str(seed)))):(name,seed)
            for name,actor in actors.items() for seed in SEEDS}
        for future in as_completed(futures):
            name,seed=futures[future]
            try:results[(name,seed)]={**future.result(),'actor':name}
            except BaseException as error:results[(name,seed)]=dict(actor=name,seed=seed,status='worker_error',error=repr(error),selected_indices=[])
            atomic_json(out/'status.json',dict(phase='collection',finished=len(results),total=32,last_actor=name,last_seed=seed,seconds=time.monotonic()-started))
    episodes=[results[(name,seed)] for name in actors for seed in SEEDS];fixtures={};total=0
    for name in actors:
        lists=[json.loads((out/'collection'/name/str(seed)/'selected_records.json').read_text()) if results[(name,seed)]['status']=='complete' else [] for seed in SEEDS]
        records=[rows[quantile] for quantile in range(16) for rows in lists if len(rows)>quantile]
        atomic_json(out/(name+'_records.json'),records);total+=len(records)
        fixtures[name]=dict(records_file=name+'_records.json',records_sha256=sha_file(out/(name+'_records.json')),
            context_sha256=[digest(canonical(r)) for r in records],selected_count=len(records),continuation_checkpoint=actors[name]['checkpoint_sha256'])
    atomic_json(out/'fixture_freeze.json',dict(before_feedback_and_training=True,actors=fixtures,
        order='temporal quantile then ascending frozen seed within each actor; no contexts from incomplete episodes'))
    atomic_json(out/'receipt.json',dict(status='complete' if all(r['status']=='complete' for r in episodes) else 'closed_with_errors',
        episodes=episodes,selected_contexts=total,native_successes=sum(bool(r.get('outcome',{}).get('success')) for r in episodes if r.get('outcome')),
        total_decisions=sum(r.get('decisions',0) for r in episodes),seconds=time.monotonic()-started,
        freeze_sha256=sha_file(out/'freeze.json'),fixture_sha256=sha_file(out/'fixture_freeze.json'),feedback=False,training=False,deployment=False))


def supervise(args):
    command=[sys.executable,'-m','v1.navigation_collection','run','--initial',str(args.initial),'--candidate',str(args.candidate),'--out',str(args.out)]
    started=time.monotonic();log=args.out.parent/(args.out.name+'_supervisor.log')
    with log.open('wb') as stream:
        process=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=process.wait(timeout=890);timed_out=False
        except subprocess.TimeoutExpired:
            timed_out=True;os.killpg(process.pid,signal.SIGTERM)
            try:code=process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);code=process.wait(timeout=5)
    atomic_json(args.out.parent/(args.out.name+'_supervisor.json'),dict(returncode=code,timed_out=timed_out,
        child_process_group=process.pid,command=command,seconds=time.monotonic()-started,cap_seconds=900))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['run','supervise'])
    parser.add_argument('--initial',type=Path,required=True);parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();(run if args.mode=='run' else supervise)(args)
