"""Read-only unclamped acquisition probe on existing training contexts, not gameplay."""
import gzip
import json
import os
from pathlib import Path
import sys
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import numpy as np
ROOT=Path('/home/ec2-user/doom-v3-20260929')
sys.path.insert(0,str(ROOT/'code/native_blend_02'))
os.environ['CADENCE_SRC']=str(ROOT/'cadence/src')
from v3.brain import load_bundle,query
from v3.interface import canonical,digest
run=ROOT/'runs/native_blend_02';pool=ROOT/'datasets/own_rehearsal_02'
freeze=json.loads((run/'freeze.json').read_text())
scores=json.loads((pool/'navigation_scores.json').read_text())
anchors=json.loads((pool/'rehearsal_pool.json').read_text())['rows']
examples=[]
for index in freeze['native_context_indices']:
    with gzip.open(ROOT/'runs/navigation_horizon_01/h600'/f'context_{index:02d}.json.gz','rt') as stream:d=json.load(stream)
    examples.append((index,np.array(d['feedback']['labels'])))
results=[]
for name,path in [('initial',pool/'frozen_actor.json')]+[(name,run/name/'bundle.json') for name,_ in freeze['arms']]:
    brain,bundle=load_bundle(path,device='cpu');before=brain.snapshot();rows=[];basic=[]
    for index,values in examples:
        answer=query(brain,scores[index]['inputs'],budget=bundle['query_budget'])
        assert answer['qualified'];a=answer['action'];best=np.flatnonzero(values>=values.max()-1e-12)
        nonbest=[i for i in range(20) if i not in best]
        rows.append(dict(context_index=index,selected_action=a,initial_action=scores[index]['action'],
            best_actions=best.tolist(),best_action_selected=a in best,
            fixed_ad9_continuation_value=float(values[a]),
            initial_action_fixed_continuation_value=float(values[scores[index]['action']]),
            goal_branch_selected=bool(values[a]>0),
            best_action_score_margin=float(max(answer['scores'][i] for i in best)-max(answer['scores'][i] for i in nonbest))))
    for row in anchors:
        answer=query(brain,row['inputs'],budget=bundle['query_budget']);assert answer['qualified']
        basic.append(dict(row_id=row['row_id'],initial_action=int(np.argmax(row['targets'])),action=answer['action'],
            score_l2=float(np.linalg.norm(np.array(answer['scores'])-row['targets']))))
    assert brain.snapshot()==before
    results.append(dict(name=name,checkpoint_sha256=bundle['hashes']['checkpoint_sha256'],queries=46,
        native_training_best_action_agreement=sum(r['best_action_selected'] for r in rows),
        native_training_goal_branch_actions=sum(r['goal_branch_selected'] for r in rows),
        mean_fixed_ad9_continuation_value=float(np.mean([r['fixed_ad9_continuation_value'] for r in rows])),
        basic_rehearsal_action_changes=sum(r['initial_action']!=r['action'] for r in basic),
        basic_rehearsal_mean_score_l2=float(np.mean([r['score_l2'] for r in basic])),
        snapshots_unchanged=True,rows=rows,basic=basic))
print(canonical(dict(passed=True,qualified_queries=230,models=results,
    interpretation='Training-context diagnostic only. Reported branch values still assume frozenad9 continuation, not the new actor. No native gameplay or parameter admissions.')))
