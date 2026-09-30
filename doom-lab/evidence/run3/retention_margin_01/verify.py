"""Read-only independent verifier for the four cached retention/margin arms."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path('/home/ec2-user/doom-v3-20260929')
sys.path.insert(0,str(ROOT/'code/retention_margin_01'))
from v3.interface import ACTION_BUTTONS,canonical,digest

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

run=ROOT/'runs/retention_margin_01';source=ROOT/'runs/navigation_novelty_01'
freeze=read(run/'freeze.json');receipt=read(run/'receipt.json')
assert receipt['status']=='complete' and not receipt['deployment']
assert receipt['freeze_sha256']==sha(run/'freeze.json')
for name,value in freeze['source_sha256'].items():assert sha(ROOT/'code/retention_margin_01/v3'/name)==value
for name,value in freeze['core_source_sha256'].items():assert sha(ROOT/'cadence/src/cadence'/name)==value
for name,value in freeze['source_artifacts'].items():assert sha(source/name)==value
with gzip.open(source/'feedback.jsonl.gz','rt') as stream:feedback=[json.loads(line)['feedback'] for line in stream]
records=read(source/'records.json');seed=read(source/'visible_novelty/bundle.json')['metadata']['seed_replay']
seed={r['row_id']:r for r in seed}
old=read(source/'visible_novelty/evaluation.json')['outcomes']
old_map={(r['task_id'],r['seed']):r for r in old}
assert read(run/'control_proof.json')['passed'] and read(run/'native_control_parity.json')['passed']
summaries=[];total_queries=total_tics=0
for name,sampler,margin in freeze['arms']:
    plan=read(run/'plans'/f'{name}.json');assert sha(run/'plans'/f'{name}.json')==freeze['plans'][name]
    assert len(plan['batches'])==2 and len(plan['pending'])==5 and len(plan['witnesses'])==21
    native={}
    for witness in plan['witnesses']:
        i=witness['index'];answer=feedback[i];values=np.array(answer['novelty_labels'])
        winners=np.flatnonzero(values>=values.max()-1e-12)
        assert 0<len(winners)<20 and np.ptp(answer['native_control_labels'])==0
        targets=np.full(20,-.04);targets[winners]=.8*(1/len(winners)-.05)
        assert np.allclose(witness['original_targets'],targets,rtol=0,atol=1e-15)
        assert np.allclose(witness['assigned_targets'],targets*(margin/.8),rtol=0,atol=1e-15)
        assert witness['feedback_sha256']==digest(canonical(answer))
        assert witness['row_id']==digest(canonical(records[i]))
        native[witness['row_id']]=witness
    basic_counts=[]
    for batch in plan['batches']:
        assert len(batch)==16
        basic_counts.append(sum(r.get('task')=='basic' for r in batch))
        for row in batch:
            if row['source']=='bootstrap_seed':assert row==seed[row['row_id']]
            else:
                w=native[row['row_id']]
                assert row['targets']==w['assigned_targets']
                assert row['inputs']==records[w['index']]['inputs']
        if sampler=='stratified':
            assert [r['task'] for r in batch[8:]]==['basic']*6+['doors','navigation']
            assert all(r['source']=='bootstrap_seed' for r in batch[8:])
    trained=read(run/name/'training_receipt.json');bundle=read(run/name/'bundle.json')
    assert trained['status']=='complete' and trained['accepted_repairs']==2 and trained['pending_rows']==5
    assert sha(run/name/'bundle.json')==trained['bundle_sha256']
    assert digest(bundle['snapshot'])==trained['checkpoint_sha256']
    for admission,batch in zip(trained['admissions'],plan['batches'],strict=True):
        assert admission['accepted'] and admission['diagnostics']['qualified'] and not admission['diagnostics']['duplicate']
        assert admission['row_ids']==[r['row_id'] for r in batch]
    result=read(run/name/'evaluation.json');assert not result['gate']['eligible'] and not result['auto_deployment']
    counts={}
    for row in result['rows']:
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
        if name=='uniform_m08':
            expected=old_map[(row['task_id'],row['seed'])]
            for key in ['return','success','queries','qualified_queries','decision_trace_sha256']:assert row[key]==expected[key]
        total_queries+=len(trace);total_tics+=tics
        task=counts.setdefault(row['task_id'],dict(episodes=0,wins=0,total_return=0.,queries=0))
        task['episodes']+=1;task['wins']+=row['success'];task['total_return']+=row['return'];task['queries']+=len(trace)
    assert {(r['task_id'],r['seed']) for r in result['rows']}=={(t,s) for t,ss in freeze['gate_tasks'].items() for s in ss}
    for task in counts.values():task['mean_return']=task.pop('total_return')/task['episodes']
    summaries.append(dict(name=name,checkpoint_sha256=trained['checkpoint_sha256'],tasks=counts,
        basic_presentations_per_repair=basic_counts,parameter_delta_l2_squared=trained['parameter_delta_l2_squared'],gate=result['gate']))
assert read(run.with_name(run.name+'_supervisor.json'))['external_cutoff'] is False
print(canonical(dict(passed=True,freeze_sha256=sha(run/'freeze.json'),receipt_sha256=sha(run/'receipt.json'),
    arms=summaries,complete_episodes=48,qualified_queries=total_queries,native_tics=total_tics,
    scope='All frozen sources/plans/targets/admissions/checkpoints and native trace actions/rewards/tics verified; no training or new gameplay.')))
