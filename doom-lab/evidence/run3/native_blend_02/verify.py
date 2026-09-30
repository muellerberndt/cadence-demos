"""Independent fixed-input/target/admission/native-outcome audit, no new learning."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path('/home/ec2-user/doom-v3-20260929')
sys.path.insert(0,str(ROOT/'code/native_blend_02'))
from v3.interface import ACTION_BUTTONS,canonical,digest

def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

run=ROOT/'runs/native_blend_02';pool=ROOT/'datasets/own_rehearsal_02'
freeze=read(run/'freeze.json');receipt=read(run/'receipt.json')
assert receipt['status']=='complete' and not receipt['auto_deployment']
assert sha(run/'freeze.json')==receipt['freeze_sha256']
for name,value in freeze['source_sha256'].items():assert sha(ROOT/'code/native_blend_02/v3'/name)==value
for name,value in freeze['core_sha256'].items():assert sha(ROOT/'cadence/src/cadence'/name)==value
for path,value in {**freeze['native_artifacts'],**freeze['baseline_artifacts']}.items():assert sha(path)==value
assert sha(pool/'rehearsal_pool.json')==freeze['rehearsal_pool_sha256']
assert sha(pool/'navigation_scores.json')==freeze['navigation_scores_sha256']
anchors=read(pool/'rehearsal_pool.json')['rows'];navscores=read(pool/'navigation_scores.json')
baselines=read(ROOT/'runs/navigation_novelty_01/baseline_outcomes.json')
native={}
for index in freeze['native_context_indices']:
    path=ROOT/'runs/navigation_horizon_01/h600'/f'context_{index:02d}.json.gz'
    with gzip.open(path,'rt') as stream:entry=json.load(stream)
    assert entry['record_sha256']==navscores[index]['row_id']
    native[index]=entry['feedback']['labels']
expected={(t,s) for t,seeds in freeze['gates'].items() for s in seeds}
totals=dict(episodes=0,qualified_queries=0,native_tics=0,admissions=0)
summary=[];all_orders=[]
for name,eta in freeze['arms']:
    plan=read(run/'plans'/f'{name}.json');assert sha(run/'plans'/f'{name}.json')==freeze['plans'][name]
    assert len(plan['batches'])==4
    native_indices=[];old=[];orders=[]
    for batch in plan['batches']:
        assert len(batch)==15
        orders.append([r['row_id'] for r in batch])
        for row in batch[:7]:
            i=row['context_index'];native_indices.append(i)
            values=np.array(native[i]);winners=np.flatnonzero(values>=values.max()-1e-12)
            p=np.zeros(20);p[winners]=1/len(winners);rank=.8*(p-.05)
            scores=np.array(navscores[i]['scores'])
            target=scores if eta==0 else rank if eta==1 else (1-eta)*scores+eta*rank
            assert np.array_equal(row['targets'],target)
            assert row['inputs']==navscores[i]['inputs'] and row['row_id']==navscores[i]['row_id']
            assert np.isfinite(target).all() and (np.abs(target)<=1).all()
            assert row['lesson']['native_values']==native[i] and row['source']=='estimate'
        old+=batch[7:]
    assert native_indices==freeze['native_context_indices']*2 and old==anchors
    assert len({r['row_id'] for r in old})==32
    all_orders.append(orders)
    trained=read(run/name/'training_receipt.json');model=read(run/name/'bundle.json')
    assert trained['status']=='complete' and trained['accepted_repairs']==4 and trained['accepted_presentations']==60
    assert sha(run/name/'bundle.json')==trained['bundle_sha256'] and digest(model['snapshot'])==trained['checkpoint_sha256']
    for admission,batch in zip(trained['admissions'],plan['batches'],strict=True):
        assert admission['accepted'] and admission['diagnostics']['qualified'] and not admission['diagnostics']['duplicate']
        assert admission['row_ids']==[r['row_id'] for r in batch] and admission['batch_sha256']==digest(canonical(batch))
        totals['admissions']+=1
    result=read(run/name/'evaluation.json');rows=result['rows']
    assert not result['auto_deployment'] and {(r['task_id'],r['seed']) for r in rows}==expected
    candidate={};tasks={}
    for row in rows:
        assert row['status']=='complete' and row['queries']==row['qualified_queries'] and row['fallback_actions']==0
        path=Path(row['decision_trace_artifact']);assert sha(path)==row['decision_trace_file_sha256']
        with gzip.open(path,'rt') as stream:trace=json.load(stream)
        assert len(trace)==row['queries'] and digest(canonical(trace))==row['decision_trace_sha256']
        reward=0.;tics=0
        for event in trace:
            tr=event['transition'];assert tr['buttons']==list(ACTION_BUTTONS[tr['action']])
            assert tr['requested_tics']==4 and 1<=tr['tics']<=4 and (tr['tics']==4 or tr['terminal'])
            assert len(tr['rewards'])==tr['tics'] and abs(sum(tr['rewards'])-tr['reward'])<1e-12
            reward+=tr['reward'];tics+=tr['tics']
        assert abs(reward-row['return'])<1e-8 and tics==row['tics']
        totals['episodes']+=1;totals['qualified_queries']+=len(trace);totals['native_tics']+=tics
        candidate[(row['task_id'],row['seed'])]=row
        t=tasks.setdefault(row['task_id'],dict(wins=0,episodes=0,total_return=0.))
        t['wins']+=row['success'];t['episodes']+=1;t['total_return']+=row['return']
    eligible=True
    for before in baselines.values():
        index={(r['task_id'],r['seed']):r for r in before}
        assert set(index)==expected
        eligible &= not any(index[k]['success'] and not candidate[k]['success'] for k in expected)
        for task,seeds in freeze['gates'].items():
            eligible &= sum(candidate[(task,s)]['return']-index[(task,s)]['return'] for s in seeds)/len(seeds)>=-1e-9
    current={(r['task_id'],r['seed']):r for r in baselines['initial']}
    nav=freeze['gates']['navigation']
    gain=sum(candidate[('navigation',s)]['success'] for s in nav)>sum(current[('navigation',s)]['success'] for s in nav) or sum(candidate[('navigation',s)]['return']-current[('navigation',s)]['return'] for s in nav)>4e-9
    eligible=bool(eligible and gain)
    assert eligible==result['gate']['eligible']
    for task in tasks.values():task['mean_return']=task.pop('total_return')/task['episodes']
    summary.append(dict(name=name,eta=eta,checkpoint_sha256=trained['checkpoint_sha256'],tasks=tasks,
        parameter_delta_l2_squared=trained['parameter_delta_l2_squared'],eligible=eligible,gate=result['gate']))
assert all(order==all_orders[0] for order in all_orders)
supervisor=read(run.with_name(run.name+'_supervisor.json'))
assert not supervisor['external_cutoff'] and supervisor['returncode']==0
print(canonical(dict(passed=True,freeze_sha256=sha(run/'freeze.json'),receipt_sha256=sha(run/'receipt.json'),
    totals=totals,arms=summary,scope='Independent source/target/order/admission/checkpoint/native-action/reward/tic and strict-gate checks; no learning or new gameplay.')))
