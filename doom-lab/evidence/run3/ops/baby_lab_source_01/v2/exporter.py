"""Immutable model bundle publication; latest pointer changes atomically."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import numpy as np
from basic_env import ACTION_NAMES,TRANSFORM,sha

SCHEMA='cadence-doom-lab-v2/1'

def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(data,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def export_bundle(root,brain,normalizer,metadata,*,original_train=None,publish_latest=True):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    snapshot=brain.snapshot();digest=hashlib.sha256(snapshot.encode()).hexdigest()
    model_id=f"{metadata['job_id']}_epoch{metadata['epoch']:02d}_{digest[:12]}"
    target=root/model_id
    if target.exists():raise FileExistsError(f'Immutable bundle already exists: {target}')
    temp=Path(tempfile.mkdtemp(prefix='.bundle-',dir=root))
    try:
        (temp/'checkpoint.json').write_text(snapshot)
        np.savez_compressed(temp/'normalization.npz',mean=normalizer['mean'],scale=normalizer['scale'])
        m={**metadata,'schema':SCHEMA,'model_id':model_id,'label':metadata.get('label',model_id),
           'scenario':'basic','action_names':list(ACTION_NAMES),'repeat_tics':12,'query_budget':512,
           'transform':TRANSFORM,'input_shape':246,'output':'utility','created_unix':time.time(),
           'hashes':{'checkpoint_sha256':digest,'normalization_sha256':sha(temp/'normalization.npz')}}
        if original_train is not None:
            np.savez_compressed(temp/'original_train.npz',**original_train)
            m['hashes']['original_train_sha256']=sha(temp/'original_train.npz')
            original_replay={k:np.asarray(value).tolist() for k,value in original_train.items()}
            m['hashes']['original_replay_values_sha256']=hashlib.sha256(
                json.dumps(original_replay,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        normalization={'mean':np.asarray(normalizer['mean']).tolist(),
                       'scale':np.asarray(normalizer['scale']).tolist(),'clip':3.0,'multiplier':.2}
        m['hashes']['normalization_values_sha256']=hashlib.sha256(
            json.dumps(normalization,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        atomic_json(temp/'metadata.json',m)
        portable={'schema':SCHEMA,'metadata':m,'snapshot':snapshot,
                  'normalization':normalization}
        if original_train is not None:portable['original_replay']=original_replay
        atomic_json(temp/'bundle.json',portable)
        os.replace(temp,target)
        if publish_latest:
            atomic_json(root/'latest.json',{'schema':SCHEMA,'bundle':model_id,'model_id':model_id,
                        'metadata_sha256':sha(target/'metadata.json')})
        return target
    except BaseException:
        shutil.rmtree(temp,ignore_errors=True);raise
