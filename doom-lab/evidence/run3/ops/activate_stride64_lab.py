"""Coordinated private8667 stride64 cutover; retains the prior wave directory."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import aiohttp

BASE=Path('/home/ec2-user/doom-v3-20260929')
APP=BASE/'lab/baby_04';OLD=BASE/'lab/baby_03'
MODEL='confirmed-ad9-stride64-gate32'


async def main():
    receipt={'schema':'doom-stride-live-activation/1','started_unix':time.time(),'old_app':str(OLD),'new_app':str(APP)}
    def save():
        temporary=APP/'qa/activation.tmp';temporary.write_text(json.dumps(receipt,indent=2)+'\n');temporary.replace(APP/'qa/activation.json')
    manifest=json.loads((APP/'source_manifest.json').read_text())
    assert all(hashlib.sha256((APP/k).read_bytes()).hexdigest()==v['sha256'] for k,v in manifest['files'].items())
    recovery=json.loads((APP/'qa/gate32_stage.json').read_text());assert recovery['passed']
    EXPECTED=recovery['captured_checkpoint_sha256']
    OLD_EXPECTED=recovery['old_checkpoint_sha256']
    assert recovery['model_id']==MODEL
    assert hashlib.sha256((APP/'qa/stride64_api.json').read_bytes()).hexdigest()==recovery['prior_failed_receipt_sha256']
    receipt['staging_retest_sha256']=hashlib.sha256((APP/'qa/gate32_stage.json').read_bytes()).hexdigest()
    performance=json.loads((APP/'qa/stride64_contention_retest.json').read_text());assert performance['passed']
    assert hashlib.sha256((APP/'qa/stride64_contention_retest.json').read_bytes()).hexdigest()==recovery['prior_operational_retest_sha256']
    receipt['prior_five_minute_failed_receipt_sha256']=recovery['prior_failed_receipt_sha256']
    receipt['captured_checkpoint_sha256']=EXPECTED
    receipt['replaced_retention_failed_checkpoint_sha256']=OLD_EXPECTED
    receipt['selection_gene']={'gate_seeds':recovery['gate_seeds'],'gate_workers':4,'scope':'repeated development selection; not a success guarantee'}
    staging_pid=recovery['staging_pid']
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as client:
        async def get(port,path='/state'):
            async with client.get(f'http://127.0.0.1:{port}'+path) as response:response.raise_for_status();return await response.json()
        async def commands(port,values,predicate):
            ws=await client.ws_connect(f'http://127.0.0.1:{port}/ws')
            async def drain():
                async for _ in ws:pass
            reader=asyncio.create_task(drain())
            try:
                for value in values:await ws.send_json(value)
                for _ in range(200):
                    state=await get(port)
                    if predicate(state):return state
                    await asyncio.sleep(.3)
                raise TimeoutError('Control did not reach its declared state')
            finally:await ws.close();await reader
        old=await get(8667);stage=await get(8668)
        assert old['model']['id']=='confirmed-h144-ad9-stride32' and old['learning']['champion_sha256']==OLD_EXPECTED
        assert old['mode']=='idle' and not old['learning']['enabled'] and not old['learning']['busy']
        assert stage['model']['id']==MODEL and stage['learning']['champion_sha256']==EXPECTED
        assert stage['mode']=='idle' and not stage['learning']['enabled'] and not stage['learning'].get('busy',False)
        old=await commands(8667,[{'type':'mode','mode':'idle'},{'type':'learning','enabled':False}],
            lambda s:s['mode']=='idle' and not s['learning']['enabled'] and not s['learning']['busy'])
        receipt['old_quiescent_state']=old
        exported=await get(8667,'/export')
        snapshot=OLD/'qa/before_stride64_export.json'
        assert json.loads(snapshot.read_text())==exported
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==recovery['old_export_sha256']
        receipt['old_export']={'path':str(snapshot),'sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest()}
        save()
        async def stop(pid,expected):
            command=Path('/proc')/str(pid)/'cmdline'
            if not command.exists():return
            assert expected.encode() in command.read_bytes()
            os.killpg(pid,signal.SIGTERM)
            for _ in range(200):
                stat=Path('/proc')/str(pid)/'stat'
                if not stat.exists() or stat.read_text().split()[2]=='Z':return
                await asyncio.sleep(.2)
            raise TimeoutError('Process did not finish: '+str(pid))
        await stop(518480,'browser_learning_window.py')
        await stop(518373,'v3.watch_training')
        await stop(518372,'server.py')
        await stop(staging_pid,'server.py')
        # Existing bare founder imports remain selectable byte-for-byte.
        copied=[]
        for original in (OLD/'data/models/v3').glob('baby-*/bundle.json'):
            target=APP/'data/models/v3'/original.parent.name/'bundle.json'
            if target.exists():
                assert target.read_bytes()==original.read_bytes()
            else:
                target.parent.mkdir(parents=True);shutil.copyfile(original,target)
            copied.append({'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
        receipt['preserved_founder_imports']=copied
        env={**os.environ,'PYTHONPATH':str(APP/'vendor')+':'+str(APP)+':'+str(BASE/'cadence/src'),
            'CADENCE_SRC':str(BASE/'cadence/src'),'DOOM_LAB_PORT':'8667','DOOM_LAB_ENABLE_V3':'1',
            'DOOM_LAB_V3_PRACTICE':'1','DOOM_V3_DOOM1_WAD':'/home/ec2-user/payload/doom/wads/doom1.wad'}
        for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='1'
        def launch(name,command):
            with (APP/'qa'/name).open('ab') as log:
                return subprocess.Popen(command,cwd=APP,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True).pid
        server=launch('live.log',['timeout','-k','30s','7500s','/home/ec2-user/venv/bin/python','-u','server.py'])
        monitor=launch('live_monitor.log',['timeout','-k','15s','7560s','/home/ec2-user/venv/bin/python','-u','-m','v3.watch_training',
            '--local-base',str(BASE),'--url','http://127.0.0.1:8667','--hours','2.1','--interval','15',
            '--output',str(APP/'static/v3_training_status.json'),'--receipt',str(APP/'qa/live_monitor.json')])
        receipt['processes']={'server':server,'monitor':monitor};save()
        for _ in range(150):
            try:
                current=await get(8667)
                if current['model']['id']==MODEL and current['learning'].get('collection_stride')==64:break
            except (aiohttp.ClientError,TimeoutError):pass
            await asyncio.sleep(.2)
        else:raise TimeoutError('New live actor did not restore')
        assert current['mode']=='idle' and not current['learning']['enabled']
        assert current['learning']['champion_sha256']==EXPECTED
        assert current['learning']['executed_decisions']==stage['learning']['executed_decisions']
        receipt['counter_exact_after_stage_restart']=True
        guard=launch('live_window.log',['timeout','-k','15s','7350s','/home/ec2-user/venv/bin/python','-u',
            str(BASE/'lab/baby_02/qa/browser_learning_window.py'),'--url','http://127.0.0.1:8667','--model',MODEL,
            '--seconds','7200','--out',str(APP/'qa/browser_window_01')])
        receipt['processes']['guard']=guard;save()
        current=await commands(8667,[{'type':'learning','enabled':True},{'type':'mode','mode':'student'}],
            lambda s:s['mode']=='student' and s['learning']['enabled'] and s.get('shadow',{}).get('qualified') is True)
        receipt.update(activated_unix=time.time(),active={'mode':current['mode'],'model':current['model'],
                       'learning':current['learning']},source_manifest_sha256=hashlib.sha256((APP/'source_manifest.json').read_bytes()).hexdigest(),
                       old_wave_preserved=True,live8666_controls=0,visual_browser_test=False)
        save();print(json.dumps({'processes':receipt['processes'],'activated_unix':receipt['activated_unix'],'active_model':current['model'],'learning_enabled':current['learning']['enabled']}))


if __name__=='__main__':asyncio.run(main())
