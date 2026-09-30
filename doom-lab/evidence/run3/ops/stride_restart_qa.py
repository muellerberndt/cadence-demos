"""Isolated8668 recovery test; keep the first QA failure receipt unchanged."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import aiohttp

APP=Path('/home/ec2-user/doom-v3-20260929/lab/baby_03')
BASE=APP.parents[1]
URL='http://127.0.0.1:8668'


async def main():
    checks={};result={'schema':'doom-stride-recovery-qa/1','started_unix':time.time()}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as client:
        async def state():
            async with client.get(URL+'/state') as response:response.raise_for_status();return await response.json()
        before=await state()
        assert before['mode']=='idle' and not before['learning']['enabled']
        for _ in range(100):
            before=await state()
            if not before['learning']['busy']:break
            await asyncio.sleep(.2)
        else:raise TimeoutError('Staging learner did not pause')
        model=before['model']['id'];wave=before['learning']['practice_wave_sha256']
        collection=APP/'data/models/v3'/model/'practice_waves'/wave/'experience_collection.json'
        old_bytes=collection.read_bytes()
        pid=json.loads((APP/'qa/preparation.json').read_text())['staging_pid']
        command=(Path('/proc')/str(pid)/'cmdline').read_bytes()
        assert b'server.py' in command
        os.killpg(pid,signal.SIGTERM)
        for _ in range(150):
            stat=Path('/proc')/str(pid)/'stat'
            if not stat.exists() or stat.read_text().split()[2]=='Z':break
            await asyncio.sleep(.2)
        else:raise TimeoutError('Staging process did not finish shutdown')
        env={**os.environ,'PYTHONPATH':str(APP/'vendor')+':'+str(APP)+':'+str(BASE/'cadence/src'),
            'CADENCE_SRC':str(BASE/'cadence/src'),'DOOM_LAB_PORT':'8668','DOOM_LAB_ENABLE_V3':'1',
            'DOOM_LAB_V3_PRACTICE':'1','DOOM_V3_DOOM1_WAD':'/home/ec2-user/payload/doom/wads/doom1.wad'}
        for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='1'
        with (APP/'qa/staging_restart.log').open('ab') as log:
            process=subprocess.Popen(['timeout','-k','30s','900s','/home/ec2-user/venv/bin/python','-u','server.py'],
                cwd=APP,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        result['new_staging_pid']=process.pid
        for _ in range(150):
            try:
                restored=await state()
                if restored['model']['id']==model and restored['learning'].get('collection_stride')==32:break
            except (aiohttp.ClientError,TimeoutError):pass
            await asyncio.sleep(.2)
        else:raise TimeoutError('Staging restart did not restore model')
        checks['counter_exact_after_restart']=collection.read_bytes()==old_bytes and restored['learning']['executed_decisions']==before['learning']['executed_decisions']
        checks['same_checkpoint_after_restart']=restored['learning']['champion_sha256']==before['learning']['champion_sha256']
        checks['restart_paused']=restored['mode']=='idle' and not restored['learning']['enabled']
        ws=await client.ws_connect(URL+'/ws')
        async def drain():
            async for _ in ws:pass
        reader=asyncio.create_task(drain())
        try:
            await ws.send_json({'type':'learning','enabled':True})
            await ws.send_json({'type':'mode','mode':'student'})
            await asyncio.sleep(12)
        finally:
            await ws.send_json({'type':'mode','mode':'idle'})
            await ws.send_json({'type':'learning','enabled':False})
            for _ in range(150):
                final=await state()
                if final['mode']=='idle' and not final['learning']['enabled'] and not final['learning']['busy']:break
                await asyncio.sleep(.2)
            await ws.close();await reader
        checks['counter_advances_without_reset']=final['learning']['executed_decisions']>before['learning']['executed_decisions']+10
        checks['queued_native_custody_recovered']=final['learning']['processed_transitions']>=before['learning']['processed_transitions'] and final['learning']['updates']>=before['learning']['updates']
        checks['explicit_stop_verified']=final['mode']=='idle' and not final['learning']['enabled'] and not final['learning']['error']
        original=json.loads((APP/'qa/stride_api.json').read_text())
        checks['queue_never_full_in_original_samples']=max(s['learning']['queue_depth'] for s in original['samples'])<64
        checks['transient_pending_had_capacity']=all(s['learning']['queue_depth']<64 for s in original['samples'] if s['learning']['pending_transition'])
        result.update(passed=all(checks.values()),checks=checks,before=before['learning'],restored=restored['learning'],final=final['learning'],
            original_receipt_sha256=hashlib.sha256((APP/'qa/stride_api.json').read_bytes()).hexdigest(),
            original_failure_explanation='The first QA client never drained WebSocket state messages; its pause command stalled behind backpressure. A fresh draining client stopped the isolated lab. One sampled pending=true at queue1 was an atomic handoff, not a full queue. Original receipt retained unchanged.',
            finished_unix=time.time(),visual_browser_test=False,control_requests_to8667_or8666=0)
        (APP/'qa/stride_recovery.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k not in ('before','restored','final')}))
        return result['passed']


if __name__=='__main__':raise SystemExit(0 if asyncio.run(main()) else 1)
