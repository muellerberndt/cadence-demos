"""Preserve live champion, pause competing learner, repeat fixed >=5/s criterion.

The failed five-minute test remains immutable. This prospective two-minute test
uses a separate wave from the exact captured live champion; no queue migration.
"""
import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import aiohttp
from v3.brain import write_bundle
from v3.interface import digest
from v3.practice import PracticeConfig, atomic_json
from v3.practice_protocol import make_package, unpack_package
from v3.runtime import validate_deployment

BASE=Path('/home/ec2-user/doom-v3-20260929')
APP=BASE/'lab/baby_04'; OLD=BASE/'lab/baby_03'
MODEL='browser-h144-promoted-stride64'


async def main():
    receipt={'schema':'doom-stride64-contention-retest/1','started_unix':time.time(),
        'duration_seconds':120,'playback_threshold_decisions_per_second':5,
        'prior_failed_receipt':str(APP/'qa/stride64_api.json'),
        'prior_failed_receipt_sha256':digest((APP/'qa/stride64_api.json').read_bytes()),
        'interpretation':'Prospective contention retest after pausing old32. Same playback criterion; current autonomous champion retained.',
        'visual_browser_test':False,'control_requests_to8666':0}
    def save():atomic_json(APP/'qa/stride64_contention_retest.json',receipt)
    save()
    manifest=json.loads((APP/'source_manifest.json').read_text())
    assert all(digest((APP/k).read_bytes())==v['sha256'] for k,v in manifest['files'].items())
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as client:
        async def get(port,path='/state'):
            async with client.get(f'http://127.0.0.1:{port}'+path) as r:r.raise_for_status();return await r.json()
        async def open_control(port):
            ws=await client.ws_connect(f'http://127.0.0.1:{port}/ws')
            async def drain():
                async for _ in ws:pass
            return ws,asyncio.create_task(drain())
        ws,reader=await open_control(8667)
        try:
            await ws.send_json({'type':'mode','mode':'idle'})
            await ws.send_json({'type':'learning','enabled':False})
            for _ in range(600):
                old=await get(8667)
                if old['mode']=='idle' and not old['learning']['enabled'] and not old['learning']['busy']:break
                await asyncio.sleep(.2)
            else:raise TimeoutError('Old learner did not quiesce')
            active=await get(8667,'/export')
            checkpoint=active['hashes']['checkpoint_sha256']
            assert checkpoint==old['learning']['champion_sha256']
            assert old['model']['id']=='confirmed-h144-ad9-stride32'
            capture=OLD/'qa/before_stride64_export.json';atomic_json(capture,active)
            receipt.update(old_quiescent_state=old,old_export=str(capture),old_export_sha256=digest(capture.read_bytes()),
                           captured_checkpoint_sha256=checkpoint)
            save()
        finally:await ws.close();await reader
        previous=active['metadata']['practice_package']
        config=PracticeConfig(**previous['descriptor']['config'])
        packed=make_package(active,previous['founder'],previous['continuation'],config=config,
            wave_name='browser_h144_stride64_promoted_01',collection_stride=64)
        validate_deployment(packed)
        target=APP/'data/models/v3'/MODEL/'bundle.json'
        assert not target.exists(),'Separate fresh wave required'
        write_bundle(target,packed)
        receipt.update(model_id=MODEL,bundle=str(target),bundle_file_sha256=digest(target.read_bytes()),
            wave_sha256=unpack_package(packed)['wave_sha256'],
            source_manifest_sha256=digest((APP/'source_manifest.json').read_bytes()))
        save()
        prior=json.loads((APP/'qa/preparation.json').read_text())['staging_pid']
        command=Path('/proc')/str(prior)/'cmdline'
        if command.exists() and b'server.py' in command.read_bytes():
            os.killpg(prior,signal.SIGTERM)
            for _ in range(200):
                p=Path('/proc')/str(prior)/'stat'
                if not p.exists() or p.read_text().split()[2]=='Z':break
                await asyncio.sleep(.2)
            else:raise TimeoutError('Old staging did not stop')
        env={**os.environ,'DOOM_LAB_PORT':'8668','DOOM_LAB_ENABLE_V3':'1','DOOM_LAB_V3_PRACTICE':'1'}
        with (APP/'qa/contention_staging.log').open('ab') as log:
            process=subprocess.Popen(['timeout','-k','30s','900s','/home/ec2-user/venv/bin/python','-u','server.py'],
                cwd=APP,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        receipt['staging_pid']=process.pid;save()
        for _ in range(200):
            try:await get(8668);break
            except (aiohttp.ClientError,TimeoutError):await asyncio.sleep(.2)
        else:raise TimeoutError('New stage unavailable')
        ws,reader=await open_control(8668);samples=[];error=None
        try:
            await ws.send_json({'type':'model','id':MODEL})
            for _ in range(150):
                current=await get(8668)
                if current['model']['id']==MODEL and not current['model']['pending']:break
                await asyncio.sleep(.2)
            else:raise TimeoutError('Model did not load')
            assert current['learning']['champion_sha256']==checkpoint
            assert current['learning']['executed_decisions']==0
            await ws.send_json({'type':'learning','enabled':True})
            for _ in range(150):
                current=await get(8668)
                if current['learning']['enabled']:break
                await asyncio.sleep(.2)
            else:raise TimeoutError('Learner not enabled')
            started=time.monotonic();await ws.send_json({'type':'mode','mode':'student'})
            while True:
                current=await get(8668);elapsed=time.monotonic()-started;l=current['learning']
                samples.append({'seconds':elapsed,'mode':current['mode'],'qualified':current.get('shadow',{}).get('qualified'),
                    'model':current['model'],'learning':l})
                print(json.dumps({'seconds':round(elapsed),**{k:l.get(k) for k in ('executed_decisions','selected_transitions','processed_transitions','updates','queue_depth','error')}}),flush=True)
                if l.get('error'):raise RuntimeError(l['error'])
                if elapsed>=120:break
                await asyncio.sleep(min(10,120-elapsed))
        except Exception as exc:error=repr(exc)
        finally:
            await ws.send_json({'type':'mode','mode':'idle'})
            await ws.send_json({'type':'learning','enabled':False})
            for _ in range(600):
                final=await get(8668)
                if final['mode']=='idle' and not final['learning']['enabled'] and not final['learning']['busy']:break
                await asyncio.sleep(.2)
            await ws.close();await reader
        after=await get(8667);l=final['learning'];seconds=samples[-1]['seconds']
        work=sum(l.get(k,0) for k in ('native_feedback_seconds','repair_seconds','gate_seconds'))
        arrival=l['selected_transitions']/seconds;capacity=l.get('processed_transitions',0)/work if work else 0
        checks=dict(old_actor_preserved=after['learning']['champion_sha256']==checkpoint and after['mode']=='idle' and not after['learning']['enabled'],
            actual_qualified_play=all(s['qualified'] is not False for s in samples),
            new_counter=l['selected_transitions']==(l['executed_decisions']+63)//64,
            full_prefix_native_verified=l.get('processed_transitions',0)>=8 and l.get('rejected_contexts',0)==0,
            repair_progress=l.get('updates',0)>=1,service_above_arrival=capacity>arrival,
            playback_at_least_five_decisions_per_second=l['executed_decisions']/seconds>=5,
            queue_headroom=max(s['learning']['queue_depth'] for s in samples)<=8 and l['queue_depth']<=2,
            paused=final['mode']=='idle' and not l['enabled'] and not l['busy'],no_errors=error is None and l.get('error') is None,
            champion_preserved=l['champion_sha256']==checkpoint)
        receipt.update(unix=time.time(),passed=all(checks.values()),checks=checks,error=error,samples=samples,final=l,
            metrics=dict(decisions_per_second=l['executed_decisions']/seconds,arrival_per_minute=arrival*60,
                service_capacity_per_active_minute=capacity*60,max_queue=max(s['learning']['queue_depth'] for s in samples),
                selected=l['selected_transitions'],processed=l['processed_transitions'],updates=l['updates'],seconds=seconds))
        save();print(json.dumps({k:receipt[k] for k in ('passed','checks','metrics','captured_checkpoint_sha256','staging_pid')}),flush=True)
        return receipt['passed']


if __name__=='__main__':raise SystemExit(0 if asyncio.run(main()) else 1)
