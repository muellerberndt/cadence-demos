"""Verified optional9b package; isolated QA then inactive import, never select live."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import aiohttp
from v3.brain import load_bundle,write_bundle
from v3.interface import canonical,digest
from v3.lab_deployment import initialize
from v3.practice import PracticeConfig,atomic_json
from v3.practice_protocol import make_package,unpack_package
from v3.runtime import platform_identity,prepare_staging_bundle,validate_deployment
from v3.tasks import task_identity

BASE=Path('/home/ec2-user/doom-v3-20260929');APP=BASE/'lab/baby_04'
STAGE=BASE/'lab/optional9b_01';OUT=BASE/'runs/optional9b_portable_01'
CHECKPOINT='9b97de044740965b8cc103b38e04e0042301896466ccb5dd08f24023c362be07'
MODEL='optional-9b-basic-reserved64of64'


async def main():
    OUT.mkdir(exist_ok=False);STAGE.mkdir(exist_ok=False)
    source=BASE/'runs/replay_ratio_01/life1_old24/exports/h144_update4/bundle.json'
    assert digest(source.read_bytes())=='05845dcb33e286669e40b3ff4a34cfebccf920531dfa0fec8c7fa189bc64bf3f'
    evidence=BASE/'runs/second_confirmation_01'
    hashes={'freeze.json':'a6ac1e4f2eb89c137b81c6a12ea3148ea17fe9b9a98b3fa496c198f2444caabc',
        'summary.json':'010a147a87e73a9a6048865489f83a2dbb65ca439ae97772ecc383c3f6b5f997',
        'independent_verification.json':'b32c3541127b6817998ef195c7dcdf4020ed80711ff309e268e19f4d5fddc33b'}
    for name,sha in hashes.items():assert digest((evidence/name).read_bytes())==sha
    freeze=json.loads((evidence/'freeze.json').read_text());verified=json.loads((evidence/'independent_verification.json').read_text())
    assert verified['passed'] and verified['native_confirmation_passed']
    assert freeze['bundles']['candidate']['checkpoint_sha256']==CHECKPOINT
    assert freeze['task']==task_identity('basic')
    platform=platform_identity();assert platform['engine_binary_sha256']==freeze['engine_binary_sha256']['vizdoom']
    _,active=load_bundle(source,device='python');assert active['hashes']['checkpoint_sha256']==CHECKPOINT
    training_path=source.parents[2]/'freeze.json'
    training=json.loads(training_path.read_text())
    assert (training['new_rows'],training['old_rows'],training['candidate_lifetime'])==(8,24,4)
    assert training['practice_config']['candidate_lifetime']==4
    assert training['native_contract']==active['metadata']['native_contract']
    active=prepare_staging_bundle(active,'basic',source_platform=platform)
    active['metadata'].update(label='Optional Basic9b ·64/64 on reserved batch1400100000–63; later versions development only',
        deployment_validation={'status':'passed','source_platform':platform,'target_platform':platform,
            'checkpoint_sha256':CHECKPOINT,'receipt_sha256':hashes['independent_verification.json'],
            'scope':'Named64-case Basic confirmation, not general Doom competence'},
        optional_confirmation={'directory':str(evidence),'sha256':hashes,'reserved_seed_start':1400100000,
            'episodes':64,'wins':64,'active_ad9_comparison':'No established return-efficiency advantage'},
        historical_training={'freeze':str(training_path),'freeze_sha256':digest(training_path.read_bytes()),
            'new_rows':training['new_rows'],'old_rows':training['old_rows'],'candidate_lifetime':training['candidate_lifetime'],
            'practice_config':training['practice_config']},
        future_practice_settings={'new_rows':8,'old_rows':8,'candidate_lifetime':4,
            'meaning':'Declared standard browser control for future practice; distinct from historical8new24old/lifetime4 training and its8case gate'})
    _,current=load_bundle(APP/'prepared/ad9_stride64_gate32.json',device='python')
    founder=current['metadata']['practice_package']['founder']
    config=PracticeConfig(**current['metadata']['practice_package']['descriptor']['config'])
    packed=json.loads(canonical(make_package(active,founder,active,config=config,
        wave_name='optional9b_h144_stride64_gate32_01',collection_stride=64)))
    validate_deployment(packed);write_bundle(OUT/'bundle.json',packed)
    manifest=json.loads((APP/'source_manifest.json').read_text())
    for name,row in manifest['files'].items():
        assert digest((APP/name).read_bytes())==row['sha256']
        target=STAGE/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(APP/name,target)
    shutil.copyfile(APP/'source_manifest.json',STAGE/'source_manifest.json')
    (STAGE/'vendor').symlink_to(APP/'vendor',target_is_directory=True)
    write_bundle(OUT/'founder.json',founder)
    initialize(OUT/'founder.json',root=STAGE,source_platform=founder['metadata']['source_platform'],
        doom_wad='/home/ec2-user/payload/doom/wads/doom1.wad')
    env={**os.environ,'PYTHONPATH':str(STAGE/'vendor')+':'+str(STAGE)+':'+str(BASE/'cadence/src'),
         'DOOM_LAB_PORT':'8668','DOOM_LAB_ENABLE_V3':'1','DOOM_LAB_V3_PRACTICE':'1'}
    with (OUT/'staging.log').open('wb') as log:
        process=subprocess.Popen(['timeout','-k','15s','180s','/home/ec2-user/venv/bin/python','-u','server.py'],cwd=STAGE,
            env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    result={'schema':'doom-optional9b-import-qa/1','started_unix':time.time(),'staging_pid':process.pid,
        'bundle':str(OUT/'bundle.json'),'bundle_file_sha256':digest((OUT/'bundle.json').read_bytes()),
        'wave_sha256':unpack_package(packed)['wave_sha256'],'checkpoint_sha256':CHECKPOINT,
        'confirmation_receipts':hashes,'visual_browser_test':False,'live_model_control_requests':0,
        'future_practice_note':active['metadata']['future_practice_settings']}
    atomic_json(OUT/'receipt.json',result);checks={}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as client:
            async def get(port,path='/state'):
                async with client.get(f'http://127.0.0.1:{port}'+path) as r:r.raise_for_status();return await r.json()
            for _ in range(200):
                try:stage=await get(8668);break
                except (aiohttp.ClientError,TimeoutError):await asyncio.sleep(.2)
            else:raise TimeoutError('Optional isolated staging unavailable')
            async with client.post('http://127.0.0.1:8668/import',params={'name':MODEL},json=packed) as response:
                imported=await response.json();response.raise_for_status();assert imported=={'ok':True,'id':MODEL}
            checks['stage_import_inactive']=(await get(8668))['model']['id']==stage['model']['id']
            ws=await client.ws_connect('http://127.0.0.1:8668/ws')
            async def drain():
                async for _ in ws:pass
            reader=asyncio.create_task(drain())
            try:
                await ws.send_json({'type':'model','id':MODEL})
                for _ in range(150):
                    state=await get(8668)
                    if state['model']['id']==MODEL and not state['model']['pending']:break
                    await asyncio.sleep(.2)
                else:raise TimeoutError('Optional model did not load')
                checks['roundtrip_exact']=(await get(8668,'/export'))==packed
                checks['own_continuation_original_retention']=(state['learning']['continuation_checkpoint_sha256']==CHECKPOINT and state['learning']['retention_founder_checkpoint_sha256'].startswith('307604135121'))
                await ws.send_json({'type':'mode','mode':'student'});samples=[];start=time.monotonic()
                while time.monotonic()-start<5:
                    state=await get(8668);samples.append(state)
                    await asyncio.sleep(.25)
                checks['qualified_native_actor']=sum(s.get('shadow',{}).get('qualified') is True for s in samples)>=5 and all(s.get('shadow',{}).get('qualified') is not False for s in samples)
                checks['no_training']=all(not s['learning']['enabled'] and not s['learning'].get('error') for s in samples)
            finally:
                await ws.send_json({'type':'mode','mode':'idle'});await ws.close();await reader
            assert all(checks.values()),checks
            before=await get(8667);registry=await get(8667,'/models')
            assert before['model']['id']=='confirmed-ad9-stride64-gate32'
            assert not any(row['id']==MODEL for row in registry['models'])
            async with client.post('http://127.0.0.1:8667/import',params={'name':MODEL},json=packed) as response:
                imported=await response.json();response.raise_for_status();assert imported=={'ok':True,'id':MODEL}
            after=await get(8667)
            checks['live_import_inactive']=(before['model']['id']==after['model']['id'] and before['mode']==after['mode'] and before['learning']['enabled']==after['learning']['enabled']
                and before['learning']['practice_wave_sha256']==after['learning']['practice_wave_sha256']
                and after['learning']['executed_decisions']>=before['learning']['executed_decisions'])
            checks['old_registry_preserved']={r['id'] for r in registry['models']} <= {r['id'] for r in (await get(8667,'/models'))['models']}
            result.update(unix=time.time(),passed=all(checks.values()),checks=checks,live_import_id=MODEL,
                live_checkpoint_before=before['learning']['champion_sha256'],live_checkpoint_after=after['learning']['champion_sha256'])
    finally:
        if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=30)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        result['staging_stopped']=True;atomic_json(OUT/'receipt.json',result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':asyncio.run(main())
