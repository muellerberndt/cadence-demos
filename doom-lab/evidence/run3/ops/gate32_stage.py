"""New ad9/stride64/32-development-case wave; no live8667 or8666 controls."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import time
import aiohttp
from v3.brain import load_bundle,write_bundle
from v3.interface import canonical,digest
from v3.practice import PracticeConfig,atomic_json
from v3.practice_protocol import make_package,unpack_package
from v3.runtime import validate_deployment

BASE=Path('/home/ec2-user/doom-v3-20260929');APP=BASE/'lab/baby_04'
MODEL='confirmed-ad9-stride64-gate32'
AD9='ad9b330cd1c1c582a0bb135956f87a9f8e4c0f106d80c35bb60b39c0328ef2cc'


async def main():
    previous=json.loads((APP/'qa/stride64_contention_retest.json').read_text());assert previous['passed']
    manifest=json.loads((APP/'source_manifest.json').read_text())
    assert all(digest((APP/k).read_bytes())==v['sha256'] for k,v in manifest['files'].items())
    path=BASE/'lab/baby_02/prepared/h144_update4_confirmed_practice.json'
    assert digest(path.read_bytes())=='fb43a6bdf087777e616c2dd018bdd1f16a4d326c695f1daa4606a8a254562685'
    _,active=load_bundle(path,device='python');assert active['hashes']['checkpoint_sha256']==AD9
    companions=active['metadata']['practice_package']
    config=replace(PracticeConfig(**companions['descriptor']['config']),gate_tasks=('basic',),
        gate_seeds=tuple(range(1220200000,1220200032)),feedback_workers=20,gate_workers=4,
        max_journal_bytes=512*1024**2)
    active['metadata']['label']='Basic ad9 confirmed starting checkpoint; future versions development only · stride64 / gate32'
    active['metadata']['prospective_selection']={'seeds':list(config.gate_seeds),'scope':'repeated development selection, not confirmation',
        'retention':'every original-founder and current-champion success; no task-mean return loss; strict native improvement required',
        'control':'8-case development gate remains in immutable earlier waves',
        'reason':'Browser7613 failed fresh64 retention despite higher mean return; original confirmedad9 retained'}
    packed=make_package(active,companions['founder'],active,config=config,
        wave_name='browser_h144_stride64_gate32_01',collection_stride=64)
    packed=json.loads(canonical(packed))
    validate_deployment(packed)
    prepared=APP/'prepared/ad9_stride64_gate32.json'
    if prepared.exists():assert json.loads(prepared.read_text())==packed
    else:write_bundle(prepared,packed)
    result={'schema':'doom-gate32-staging/1','started_unix':time.time(),'model_id':MODEL,
        'captured_checkpoint_sha256':AD9,'old_checkpoint_sha256':previous['captured_checkpoint_sha256'],
        'old_export_sha256':previous['old_export_sha256'],'staging_pid':previous['staging_pid'],
        'source_manifest_sha256':digest((APP/'source_manifest.json').read_bytes()),
        'bundle':str(prepared),'bundle_file_sha256':digest(prepared.read_bytes()),
        'wave_sha256':unpack_package(packed)['wave_sha256'],
        'prior_operational_retest_sha256':digest((APP/'qa/stride64_contention_retest.json').read_bytes()),
        'prior_failed_receipt_sha256':previous['prior_failed_receipt_sha256'],
        'gate_seeds':list(config.gate_seeds),'future_gate_workers':4,
        'old_pending_records_preserved':True,'control_requests_to8667_or8666':0,'visual_browser_test':False}
    atomic_json(APP/'qa/gate32_stage.json',result)
    checks={};samples=[]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as client:
        async def get(port,path='/state'):
            async with client.get(f'http://127.0.0.1:{port}'+path) as r:r.raise_for_status();return await r.json()
        before=await get(8667);stage=await get(8668);registry=await get(8668,'/models')
        assert before['mode']=='idle' and not before['learning']['enabled'] and not before['learning']['busy']
        assert stage['mode']=='idle' and not stage['learning']['enabled'] and not stage['learning'].get('busy',False)
        existing=any(row['id']==MODEL for row in registry['models'])
        import_id='qa-gate32-import' if existing else MODEL
        assert not any(row['id']==import_id for row in registry['models'])
        async with client.post('http://127.0.0.1:8668/import',params={'name':import_id},json=packed) as response:
            answer=await response.json();response.raise_for_status();assert answer=={'ok':True,'id':import_id},answer
        checks['import_does_not_activate']=(await get(8668))['model']['id']==stage['model']['id']
        ws=await client.ws_connect('http://127.0.0.1:8668/ws')
        async def drain():
            async for _ in ws:pass
        reader=asyncio.create_task(drain())
        try:
            await ws.send_json({'type':'model','id':MODEL})
            for _ in range(200):
                state=await get(8668)
                if state['model']['id']==MODEL and not state['model']['pending']:break
                await asyncio.sleep(.2)
            else:raise TimeoutError('Gate32 model did not load')
            exported=await get(8668,'/export');checks['package_roundtrip_exact']=exported==packed
            descriptor=exported['metadata']['practice_package']['descriptor']
            checks['exact32_case_schedule']=descriptor['config']['gate_seeds']==list(range(1220200000,1220200032))
            checks['retention_and_continuation_unchanged']=(descriptor['retention_founder_checkpoint_sha256'].startswith('307604135121') and descriptor['continuation_checkpoint_sha256']==AD9)
            await ws.send_json({'type':'mode','mode':'student'});start=time.monotonic()
            while time.monotonic()-start<12:
                state=await get(8668);samples.append({'qualified':state.get('shadow',{}).get('qualified'),
                    'learning_enabled':state['learning']['enabled'],'error':state['learning'].get('error')})
                await asyncio.sleep(.4)
        finally:
            await ws.send_json({'type':'mode','mode':'idle'})
            await ws.send_json({'type':'learning','enabled':False})
            for _ in range(100):
                final=await get(8668)
                if final['mode']=='idle' and not final['learning']['enabled'] and not final['learning'].get('busy',False):break
                await asyncio.sleep(.2)
            await ws.close();await reader
        after=await get(8667);graph=await get(8668,'/graph')
        checks.update(qualified_actual_queries=all(s['qualified'] is not False and not s['error'] for s in samples) and sum(s['qualified'] is True for s in samples)>=10,
            remained_learning_off=all(not s['learning_enabled'] for s in samples),
            no_training_or_selected_records=final['learning'].get('updates',0)==0 and final['learning']['selected_transitions']==0,
            final_paused=final['mode']=='idle' and not final['learning']['enabled'] and not final['learning'].get('busy',False),
            confirmed_ad9_actor=final['learning']['champion_sha256']==AD9,
            graph_contract=graph['total_edges']==44384 and graph['sampled_edges']==1400 and graph['motor']==20,
            old_live_unchanged=before['model']==after['model'] and before['mode']==after['mode'] and before['learning']==after['learning'],
            registry_preserved={r['id'] for r in registry['models']} <= {r['id'] for r in (await get(8668,'/models'))['models']})
        result.update(unix=time.time(),passed=all(checks.values()),checks=checks,samples=samples,final=final['learning'])
        if existing:
            imported=APP/'data/models/v3'/import_id/'bundle.json'
            assert json.loads(imported.read_text())==packed
            imported.unlink();imported.parent.rmdir()
            result['duplicate_qa_import_removed']=True
        atomic_json(APP/'qa/gate32_stage.json',result)
        print(json.dumps({k:result[k] for k in ('passed','checks','wave_sha256','bundle_file_sha256')}),flush=True)
        return result['passed']


if __name__=='__main__':raise SystemExit(0 if asyncio.run(main()) else 1)
