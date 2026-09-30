"""Matched-data Cadence capacity experiments with unclamped retention checks.

Bulk preparation and training run on AWS. Teacher preferences are estimates,
never returns or Q-values. Native student-only gameplay is evaluated separately.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import shutil
import time
import traceback

for _name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS',
              'VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'
import numpy as np

from .collection import atomic_json
from .interface import (History, PORT_SHAPES, OUTPUT_NAME, ACTION_NAMES, VISUAL_LAGS,
                        canonical, contract, digest, fit_normalizer, validate_lags)
from .tasks import get_task, sha_file

LABEL_CONTRACT = {'schema':'doom-v3-teacher-action-label/1',
                  'meaning':'privileged teacher proposed action identifier', 'is_return_or_Q':False}
def target_contract(gene='centered'):
    if gene not in ('centered','offset'):raise ValueError('Unknown target gene')
    return {'schema':'doom-v3-teacher-preference/1','meaning':'privileged teacher action preference',
            'selected':.76 if gene=='centered' else .6,'other':-.04 if gene=='centered' else -.2,
            'target_gene':gene,'matched_alternative':'offset' if gene=='centered' else 'centered',
            'source':'estimate','is_return_or_Q':False,
            'deployment':'argmax of twenty unclamped settled action-score patches'}


def split_episodes(episodes, stride=5):
    """Whole-episode development split; never leak neighboring frames across it."""
    if stride < 2: raise ValueError('Development stride must be at least two')
    groups={}
    for episode in episodes:
        groups.setdefault(episode['task'], []).append(episode)
    result=[]
    for task, rows in sorted(groups.items()):
        rows=sorted(rows,key=lambda row:(row['seed'],row['path']))
        if len(rows)<2: raise ValueError('At least two eligible episodes per task: '+task)
        if len({r['seed'] for r in rows}) != len(rows):
            raise ValueError('Duplicate task/seed episodes must not cross splits')
        for index,row in enumerate(rows):
            result.append({**row,'split':'development' if index%stride==0 else 'training'})
    return result


def episode_arrays(episode):
    path=Path(episode['path'])/'frames.npz'
    if sha_file(path)!=episode['frames_sha256']:
        raise ValueError('Episode frame custody mismatch: '+str(path))
    with np.load(path,allow_pickle=False) as archive:
        data={key:archive[key] for key in ('frames','teacher_actions','executed_actions','tics')}
    n=len(data['frames'])
    if n!=episode['decisions'] or any(len(v)!=n for v in data.values()):
        raise ValueError('Episode arrays have inconsistent lengths')
    if data['frames'].dtype!=np.uint8 or data['frames'].shape!=(n,240,320):
        raise ValueError('Invalid raw frame shape/type')
    for key in ('teacher_actions','executed_actions','tics'):
        values=data[key]
        upper=4 if key=='tics' else 19;lower=1 if key=='tics' else 0
        if (values.shape!=(n,) or values.dtype.kind not in 'iu'
                or (values<lower).any() or (values>upper).any()):
            raise ValueError('Invalid action/tic data: '+key)
    return data


def prepare(corpora,out,*,sample_stride=2,dev_stride=5,visual_lags=VISUAL_LAGS,allow_failed_teacher=False,tasks=None):
    if sample_stride<1: raise ValueError('Sample stride must be positive')
    lags=validate_lags(visual_lags);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    episodes=[];excluded=[];corpus_hashes={}
    for corpus in corpora:
        corpus=Path(corpus).resolve()
        freeze=corpus/'freeze.json'
        corpus_freeze=json.loads(freeze.read_text())
        if corpus_freeze['contract']!=contract(corpus_freeze['contract']['visual_lags']):
            raise ValueError('Corpus observation/action contract mismatch')
        corpus_hashes[str(corpus)]=sha_file(freeze)
        for path in sorted(corpus.glob('episode-*/receipt.json')):
            row=json.loads(path.read_text())
            if tasks is not None and row['task'] not in tasks:
                excluded.append({'path':str(path),'reason':'task_outside_declared_bootstrap_scope','task':row['task']})
                continue
            spec=get_task(row['task'])
            if spec.split!='train': raise ValueError('Reserved or development map in training corpus')
            eligible=(row['status']=='complete' and row.get('decisions',0)>0
                      and (allow_failed_teacher or row.get('outcome',{}).get('success')))
            if not eligible:
                excluded.append({'path':str(path),'status':row['status'],'outcome':row.get('outcome')})
                continue
            if sha_file(path.parent/'events.jsonl.gz')!=row['events_sha256']:
                raise ValueError('Corpus event custody mismatch')
            episodes.append({k:row[k] for k in ('task','seed','decisions','frames_sha256','events_sha256')} |
                            {'path':str(path.parent),'receipt_sha256':sha_file(path)})
    if not episodes: raise ValueError('No eligible teacher episodes')
    episodes=split_episodes(episodes,dev_stride)
    def frames():
        for row in episodes:
            if row['split']=='training':
                yield from episode_arrays(row)['frames'][::sample_stride]
    normalizer=fit_normalizer(frames())
    n=sum((row['decisions']+sample_stride-1)//sample_stride for row in episodes)
    total_width=sum(PORT_SHAPES.values())
    encoded=np.lib.format.open_memmap(out/'inputs.npy',mode='w+',dtype=np.float64,shape=(n,total_width))
    actions=np.empty(n,dtype=np.int16);episode_ids=np.empty(n,dtype=np.int32)
    steps=np.empty(n,dtype=np.int32);training_mask=np.empty(n,dtype=bool)
    task_names=sorted({row['task'] for row in episodes});task_ids=np.empty(n,dtype=np.int16)
    cursor=0;started=time.monotonic()
    for index,row in enumerate(episodes):
        data=episode_arrays(row);history=History(lags)
        for step,raw in enumerate(data['frames']):
            if step%sample_stride==0:
                inputs=history.encode(raw,normalizer)
                encoded[cursor]=np.concatenate([inputs[k] for k in PORT_SHAPES])
                actions[cursor]=data['teacher_actions'][step];episode_ids[cursor]=index
                steps[cursor]=step;task_ids[cursor]=task_names.index(row['task'])
                training_mask[cursor]=row['split']=='training';cursor+=1
            history.acknowledge(raw,int(data['executed_actions'][step]),int(data['tics'][step]))
        encoded.flush()
        atomic_json(out/'status.json',{'status':'encoding','episodes':index+1,'scheduled':len(episodes),'rows':cursor})
    assert cursor==n
    np.savez_compressed(out/'rows.npz',actions=actions,episode_ids=episode_ids,steps=steps,
                        training_mask=training_mask,task_ids=task_ids)
    receipt={'schema':'doom-v3-imitation-dataset/1','status':'complete','created_unix':time.time(),
             'corpus_freezes':corpus_hashes,'episodes':episodes,'excluded':excluded,
             'task_names':task_names,'rows':n,'training_rows':int(training_mask.sum()),
             'development_rows':int((~training_mask).sum()),'sample_stride':sample_stride,
             'dev_stride':dev_stride,'allow_failed_teacher':allow_failed_teacher,
             'included_tasks':tasks,
             'normalizer':normalizer,'contract':contract(lags),'label_contract':LABEL_CONTRACT,
             'inputs_sha256':sha_file(out/'inputs.npy'),'rows_sha256':sha_file(out/'rows.npz'),
             'source_sha256':sha_file(Path(__file__)),'wall_seconds':time.monotonic()-started}
    atomic_json(out/'dataset.json',receipt)
    atomic_json(out/'status.json',{k:v for k,v in receipt.items() if k not in ('episodes','normalizer','contract','excluded')})
    return receipt


def unpack(flat):
    result={};offset=0
    for name,width in PORT_SHAPES.items():
        result[name]=flat[offset:offset+width].tolist();offset+=width
    return result


def balanced_order(rows,eligible,count,seed):
    """Uniform task/action groups, uniform rows within each; explicit replay."""
    rng=np.random.default_rng(seed);groups={}
    for index in eligible:
        groups.setdefault((int(rows['task_ids'][index]),int(rows['actions'][index])),[]).append(int(index))
    if not groups: raise ValueError('No training groups')
    keys=sorted(groups)
    return np.array([rng.choice(groups[keys[group]]) for group in rng.integers(len(keys),size=count)],dtype=np.int64)


def metric_ids(rows,eligible,max_rows,seed):
    # Fixed class-stratified sampling without replacement; every attempted
    # query remains in denominator, including refused ones.
    rng=np.random.default_rng(seed);groups={}
    for index in eligible:
        groups.setdefault((int(rows['task_ids'][index]),int(rows['actions'][index])),[]).append(int(index))
    groups={key:list(rng.permutation(value)) for key,value in sorted(groups.items())}
    result=[]
    while groups and len(result)<max_rows:
        for key in list(groups):
            if len(result)>=max_rows:break
            result.append(groups[key].pop())
            if not groups[key]:del groups[key]
    return np.array(result,dtype=np.int64)


def metrics(brain,inputs,rows,ids,task_names):
    from .brain import query
    confusion=np.zeros((len(ACTION_NAMES),len(ACTION_NAMES)+1),dtype=np.int64)
    tasks={};latency=[];sweeps=0
    for index in ids:
        answer=query(brain,unpack(inputs[index]));actual=int(rows['actions'][index])
        predicted=answer['action'] if answer['qualified'] else len(ACTION_NAMES)
        confusion[actual,predicted]+=1;latency.append(answer['query_seconds'])
        sweeps+=answer['result']['sweeps']
        task=task_names[int(rows['task_ids'][index])]
        row=tasks.setdefault(task,{'queries':0,'qualified':0,'correct':0})
        row['queries']+=1;row['qualified']+=bool(answer['qualified']);row['correct']+=predicted==actual
    total=confusion.sum(axis=1);correct=np.diag(confusion[:,:-1])
    return {'queries':len(ids),'qualified':int(confusion[:,:-1].sum()),'correct':int(correct.sum()),
            'accuracy':float(correct.sum()/len(ids)) if len(ids) else None,
            'macro_action_accuracy':float(np.mean(correct[total>0]/total[total>0])) if len(ids) else None,
            'confusion_rows_teacher_columns_actor_plus_refusal':confusion.tolist(),
            'by_task':tasks,'query_seconds_median':float(np.median(latency)) if latency else None,
            'query_seconds_p95':float(np.quantile(latency,.95)) if latency else None,
            'query_seconds_total':sum(latency),'sweeps':sweeps,
            'interpretation':'Unclamped teacher agreement, not autonomous gameplay success'}


class WallCap(RuntimeError): pass
def alarm(signum,frame): raise WallCap('Training job exceeded its declared wall cap')


def train(dataset,out,*,size='small',seed=0,epochs=2,batches=32,batch_size=16,
          wall_seconds=1800,metric_rows=128,resume=None,target_gene='centered',
          topology_version=2,recursion_depth=2,sensor_skip=True,device='cpu',
          initial_scale=.3,parameter_prior=.4,state_prior=.01,policy_history_skip=None):
    from .brain import build, genome_spec, make_bundle, write_bundle, load_bundle
    if min(epochs,batches,batch_size,metric_rows)<1 or wall_seconds<=0:raise ValueError('Positive finite bounds required')
    dataset=Path(dataset).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    meta=json.loads((dataset/'dataset.json').read_text())
    for name,key in (('inputs.npy','inputs_sha256'),('rows.npz','rows_sha256')):
        if sha_file(dataset/name)!=meta[key]:raise ValueError('Dataset changed: '+name)
    if meta['label_contract']!=LABEL_CONTRACT:raise ValueError('Unsupported label semantics')
    target=target_contract(target_gene)
    inputs=np.load(dataset/'inputs.npy',mmap_mode='r',allow_pickle=False)
    with np.load(dataset/'rows.npz',allow_pickle=False) as archive:rows={key:archive[key] for key in archive.files}
    eligible=np.flatnonzero(rows['training_mask']);dev=np.flatnonzero(~rows['training_mask'])
    order=balanced_order(rows,eligible,epochs*batches*batch_size,717003)
    train_ids=metric_ids(rows,eligible,metric_rows,717004);dev_ids=metric_ids(rows,dev,metric_rows,717005)
    gene=genome_spec(size,seed,topology_version=topology_version,
                     recursion_depth=recursion_depth,sensor_skip=sensor_skip,
                     initial_scale=initial_scale,parameter_prior=parameter_prior,
                     state_prior=state_prior,policy_history_skip=policy_history_skip)
    if resume:
        brain,previous=load_bundle(resume,device=device)
        if (previous['genome']!=gene or previous['normalization']!=meta['normalizer']
                or previous['contract']!=meta['contract'] or previous['target_contract']!=target):
            raise ValueError('Resume must preserve genome, normalization, contract and target semantics')
    else:brain=build(device=device,**gene)
    source_names=('training.py','collection.py','brain.py','interface.py','tasks.py','teacher.py')
    source_dir=out/'sources';source_dir.mkdir()
    source_hashes={}
    for name in source_names:
        shutil.copyfile(Path(__file__).with_name(name),source_dir/name)
        source_hashes[name]=sha_file(source_dir/name)
        if sha_file(Path(__file__).with_name(name))!=source_hashes[name]:raise ValueError('Source changed during freeze')
    freeze={'schema':'doom-v3-imitation-training-freeze/1','dataset':str(dataset),
            'dataset_sha256':sha_file(dataset/'dataset.json'),'genome':gene,'epochs':epochs,
            'execution_device':device,
            'batches_per_epoch':batches,'batch_size':batch_size,'wall_seconds':wall_seconds,
            'training_order_sha256':digest(order.tobytes()),'train_metric_ids':train_ids.tolist(),
            'development_metric_ids':dev_ids.tolist(),'source_sha256':source_hashes,
            'resume':None if not resume else str(resume),'target_contract':target,'created_unix':time.time(),
            'selection':'No deployment promotion; compare native gameplay separately'}
    atomic_json(out/'freeze.json',freeze)
    receipt={'schema':'doom-v3-imitation-training-result/1','status':'running','evidence_role':'student_training',
             'size':size,'seed':seed,'target_gene':target_gene,'execution_device':device,
             'patches':brain.graph.n_patches,'edges':len(brain.graph.edges),
             'accepted_updates':0,'attempted_updates':0,'accepted_presentations':0,'checkpoints':[],
             'epochs':[],'freeze_sha256':sha_file(out/'freeze.json')}
    started=time.monotonic();signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,wall_seconds)
    def export(epoch):
        skip='skip' if sensor_skip else 'no_skip'
        model_id=f'doom_baby_{size}_depth{recursion_depth}_{skip}_{target_gene}_{device}_seed{seed}_epoch{epoch:03d}'
        if policy_history_skip is False:model_id+='_historyomit'
        bundle=make_bundle(brain,meta['normalizer'],model_id=model_id,genome=gene,target_contract=target,
                           visual_lags=meta['contract']['visual_lags'],metadata={
                               'freeze_sha256':receipt['freeze_sha256'],'dataset_sha256':freeze['dataset_sha256'],
                               'accepted_updates':receipt['accepted_updates'],'epoch':epoch,
                               'status':'development_candidate_not_confirmed','training_task_names':meta['task_names']})
        path=out/'checkpoints'/f'{model_id}_{bundle["hashes"]["checkpoint_sha256"][:12]}.json'
        write_bundle(path,bundle);receipt['checkpoints'].append(str(path))
        return bundle['hashes']['checkpoint_sha256']
    try:
        export(0)
        receipt['initial']={'training':metrics(brain,inputs,rows,train_ids,meta['task_names']),
                            'development':metrics(brain,inputs,rows,dev_ids,meta['task_names'])}
        atomic_json(out/'status.json',receipt)
        with (out/'admissions.jsonl').open('w') as stream:
            for epoch in range(epochs):
                for batch in range(batches):
                    offset=(epoch*batches+batch)*batch_size;ids=order[offset:offset+batch_size]
                    examples=[]
                    for index in ids:
                        labels=np.full(len(ACTION_NAMES),target['other']);labels[rows['actions'][index]]=target['selected']
                        examples.append((unpack(inputs[index]),{OUTPUT_NAME:labels.tolist()}))
                    before=time.monotonic();answer=brain.observe_batch(examples,budget=2048,source='estimate')
                    receipt['attempted_updates']+=1
                    admitted=bool(answer['accepted'] and answer['qualified'] and not answer.get('duplicate',False))
                    receipt['accepted_updates']+=admitted
                    receipt['accepted_presentations']+=len(ids) if admitted else 0
                    row={'epoch':epoch+1,'batch':batch,'row_ids':ids.tolist(),'accepted':admitted,
                         'sweeps':answer['sweeps'],'stationarity':answer['stationarity'],
                         'reason':answer.get('reason'),'seconds':time.monotonic()-before,
                         'qualified':answer['qualified'],'duplicate':answer.get('duplicate'),
                         'event_id':answer['event_id'],'source':answer['source']}
                    stream.write(canonical(row)+'\n');stream.flush()
                    receipt['wall_seconds']=time.monotonic()-started
                    atomic_json(out/'status.json',receipt)
                    if not admitted:raise RuntimeError('Refused admission; rows not consumed')
                checkpoint=export(epoch+1)
                measurement={'epoch':epoch+1,'checkpoint_sha256':checkpoint,
                             'training':metrics(brain,inputs,rows,train_ids,meta['task_names']),
                             'development':metrics(brain,inputs,rows,dev_ids,meta['task_names'])}
                receipt['epochs'].append(measurement)
                atomic_json(out/'status.json',receipt)
                print(canonical({'epoch':epoch+1,'size':size,'seed':seed,'accepted_updates':receipt['accepted_updates'],
                      'training_accuracy':measurement['training']['accuracy'],
                      'development_accuracy':measurement['development']['accuracy']}),flush=True)
        receipt['status']='complete'
    except BaseException as error:
        receipt.update(status='wall_cap' if isinstance(error,WallCap) else 'failed',
                       error=f'{type(error).__name__}: {error}',traceback=traceback.format_exc())
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        receipt['wall_seconds']=time.monotonic()-started
        receipt['source_unchanged']=all(sha_file(Path(__file__).with_name(name))==value
                                       for name,value in freeze['source_sha256'].items())
        atomic_json(out/'receipt.json',receipt);atomic_json(out/'status.json',receipt)
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    prepare_parser=sub.add_parser('prepare');prepare_parser.add_argument('--corpus',type=Path,action='append',required=True)
    prepare_parser.add_argument('--out',type=Path,required=True);prepare_parser.add_argument('--sample-stride',type=int,default=2)
    prepare_parser.add_argument('--dev-stride',type=int,default=5)
    prepare_parser.add_argument('--visual-lags',type=int,nargs=4,default=list(VISUAL_LAGS))
    prepare_parser.add_argument('--allow-failed-teacher',action='store_true')
    prepare_parser.add_argument('--tasks',nargs='+')
    train_parser=sub.add_parser('train');train_parser.add_argument('--dataset',type=Path,required=True)
    train_parser.add_argument('--out',type=Path,required=True);train_parser.add_argument('--size',choices=['small','medium','large'],default='small')
    train_parser.add_argument('--seed',type=int,default=0);train_parser.add_argument('--epochs',type=int,default=2)
    train_parser.add_argument('--batches',type=int,default=32);train_parser.add_argument('--batch-size',type=int,default=16)
    train_parser.add_argument('--wall-seconds',type=float,default=1800);train_parser.add_argument('--metric-rows',type=int,default=128)
    train_parser.add_argument('--resume',type=Path)
    train_parser.add_argument('--target-gene',choices=['centered','offset'],default='centered')
    train_parser.add_argument('--topology-version',type=int,choices=[2],default=2)
    train_parser.add_argument('--recursion-depth',type=int,choices=[1,2,3],default=2)
    train_parser.add_argument('--no-sensor-skip',dest='sensor_skip',action='store_false')
    train_parser.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    train_parser.add_argument('--initial-scale',type=float,default=.3)
    train_parser.add_argument('--parameter-prior',type=float,default=.4)
    train_parser.add_argument('--state-prior',type=float,default=.01)
    train_parser.add_argument('--no-policy-history-skip',dest='policy_history_skip',action='store_false',default=None)
    args=vars(p.parse_args());command=args.pop('command')
    if command=='prepare':args['corpora']=args.pop('corpus');result=prepare(**args)
    else:result=train(**args)
    print(canonical({'status':result['status'],'rows':result.get('rows'),'accepted_updates':result.get('accepted_updates')}),flush=True)
    if result['status']!='complete':raise SystemExit(2)


if __name__=='__main__':main()
