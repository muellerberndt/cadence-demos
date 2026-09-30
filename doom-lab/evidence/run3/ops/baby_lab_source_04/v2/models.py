"""Exact conditioned founder, matched controls and immutable input conditioning."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys

for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[name]='1'
import numpy as np
import torch

HERE=Path(__file__).resolve().parent
CADENCE_SRC=Path(os.environ.get('CADENCE_SRC',HERE.parents[2]/'cadence/src')).resolve()
sys.path.insert(0,str(CADENCE_SRC))
from cadence import Brain,Cortex
from cadence.brain import IMPLEMENTATION
from basic_env import compact,pool,history,sha,TRANSFORM,ACTION_NAMES
torch.set_num_threads(1)
torch.use_deterministic_algorithms(True)

def build(genome,seed):
    c=Cortex(seed=int(seed),device='cpu',dtype='float64',initial_scale=.3,
             state_prior=.01,parameter_prior=.4,settle_budget=2048,tolerance=1e-6,
             state_bound=1,parameter_bound=4)
    sensors=c.input('sensors',shape=246)
    if genome=='direct':output=c.column('policy',patches=6,inputs=sensors)
    else:
        hidden=c.column('hidden',patches=12,inputs=sensors)
        if genome=='skip_observer':output=c.observer('policy',patches=6,inputs=sensors,observes=hidden)
        elif genome=='state_skip':output=c.column('policy',patches=6,inputs=(sensors,hidden))
        else:raise ValueError(f'Unknown genome {genome}')
    c.output('utility',shape=6,reads=output)
    return c.build()

def encode_small(small,h,normalizer):
    return np.concatenate((np.clip((np.asarray(small,dtype=float)-normalizer['mean'])/
                                  normalizer['scale'],-3,3)*.2,np.asarray(h).ravel()))

def encode(raw,prefix,normalizer):
    return encode_small(compact(pool(raw)).astype(float),history(prefix),normalizer)

def load_fixture(path=None):
    path=Path(path or HERE/'fixtures/training_fixture.npz')
    with np.load(path,allow_pickle=False) as z:data={k:z[k] for k in z.files}
    pixels=compact(data['pixels']).astype(float);h=data['history'].reshape(-1,21).astype(float)
    train=np.flatnonzero(data['episode_seed']<=300031)
    dev=np.flatnonzero((data['episode_seed']>=300032)&(data['episode_seed']<=300041))
    normalizer={'mean':pixels[train].mean(0),'scale':np.maximum(pixels[train].std(0),.05)}
    x=np.column_stack((np.clip((pixels-normalizer['mean'])/normalizer['scale'],-3,3)*.2,h))
    return {'x':x,'y':data['labels'].astype(float),'train':train,'dev':dev,
            'normalizer':normalizer,'episode_seed':data['episode_seed']}

def load_bundle(path):
    path=Path(path);path=path/'bundle.json' if path.is_dir() else path
    data=json.loads(path.read_text())
    if data['schema']!='cadence-doom-lab-v2/1':raise ValueError('Unknown bundle schema')
    m=data['metadata'];n=data['normalization']
    if m['transform']!=TRANSFORM or tuple(m['action_names'])!=ACTION_NAMES:raise ValueError('Input/action contract mismatch')
    if m['query_budget']!=512 or n['clip']!=3 or n['multiplier']!=.2:raise ValueError('Numerical contract mismatch')
    import hashlib
    if hashlib.sha256(json.dumps(n,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()!=m['hashes']['normalization_values_sha256']:
        raise ValueError('Normalizer value digest mismatch')
    if hashlib.sha256(data['snapshot'].encode()).hexdigest()!=m['hashes']['checkpoint_sha256']:
        raise ValueError('Checkpoint digest mismatch')
    normalizer={k:np.asarray(n[k],dtype=float) for k in ('mean','scale')}
    if any(a.shape!=(225,) or not np.isfinite(a).all() for a in normalizer.values()) or (normalizer['scale']<=0).any():
        raise ValueError('Invalid normalizer')
    brain=Brain.from_snapshot(data['snapshot'],device='cpu')
    layout=json.loads(data['snapshot'])['layout']
    if m['scenario']!='basic' or m['repeat_tics']!=12 or m['input_shape']!=246 or m['output']!='utility':
        raise ValueError('Scenario or port contract mismatch')
    if len(layout['inputs'])!=1 or layout['inputs'][0]['name']!='sensors' or layout['inputs'][0]['shape']!=[246]:
        raise ValueError('Snapshot must have exactly one 246-coordinate sensors input')
    if len(layout['outputs'])!=1 or layout['outputs'][0]['name']!='utility' or layout['outputs'][0]['shape']!=[6]:
        raise ValueError('Snapshot must have exactly one six-coordinate utility output')
    return brain,normalizer,m

def query(brain,value):
    result=brain.settle({'sensors':np.asarray(value).tolist()},budget=512)
    return np.asarray(result['outputs']['utility']),result
