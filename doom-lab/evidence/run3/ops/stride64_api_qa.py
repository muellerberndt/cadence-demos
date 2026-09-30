"""Fixed five-minute capture/service test; isolated8668 only, explicit stride64."""
import asyncio
import json
from pathlib import Path
import time
import aiohttp

APP=Path('/home/ec2-user/doom-v3-20260929/lab/baby_04')
URL='http://127.0.0.1:8668';MODEL='confirmed-h144-ad9-stride64'


async def main():
    samples=[];checks={};error=None
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as client:
        async def state(port=8668):
            async with client.get(f'http://127.0.0.1:{port}/state') as response:response.raise_for_status();return await response.json()
        before=await state(8667)
        for _ in range(150):
            try:
                await state();break
            except (aiohttp.ClientError,TimeoutError):await asyncio.sleep(.2)
        else:raise TimeoutError('Staging HTTP server is not ready')
        ws=await client.ws_connect(URL+'/ws')
        async def drain():
            async for _ in ws:pass
        reader=asyncio.create_task(drain())
        try:
            await ws.send_json({'type':'model','id':MODEL})
            for _ in range(150):
                current=await state();l=current['learning']
                if current['model']['id']==MODEL and l.get('collection_stride')==64 and not current['model']['pending']:break
                await asyncio.sleep(.2)
            else:raise TimeoutError('Stride64 model not selected')
            assert l['executed_decisions']==0 and l['selected_transitions']==0
            await ws.send_json({'type':'learning','enabled':True})
            for _ in range(150):
                current=await state()
                if current['learning']['enabled']:break
                await asyncio.sleep(.2)
            else:raise TimeoutError('Learner not enabled')
            start=time.monotonic();await ws.send_json({'type':'mode','mode':'student'})
            while True:
                current=await state();l=current['learning'];seconds=time.monotonic()-start
                samples.append({'seconds':seconds,'episode':current['episode'],'mode':current['mode'],
                    'qualified':current.get('shadow',{}).get('qualified'),
                    'query_seconds':current.get('shadow',{}).get('query_seconds'),
                    'fingerprint':current['model'].get('fingerprint'),
                    'learning':l})
                print(json.dumps({'seconds':round(seconds),**{k:l.get(k) for k in ('executed_decisions','selected_transitions','processed_transitions','updates','queue_depth','phase','error')}}),flush=True)
                if l.get('error'):raise RuntimeError(l['error'])
                if seconds>=300:break
                await asyncio.sleep(min(10,300-seconds))
        except Exception as failure:error=repr(failure)
        finally:
            await ws.send_json({'type':'mode','mode':'idle'})
            await ws.send_json({'type':'learning','enabled':False})
            for _ in range(300):
                final=await state()
                if final['mode']=='idle' and not final['learning']['enabled'] and not final['learning'].get('busy'):break
                await asyncio.sleep(.2)
            await ws.close();await reader
        after=await state(8667)
    l=final['learning'];seconds=samples[-1]['seconds'] if samples else 0
    work=sum(l.get(k,0) for k in ('native_feedback_seconds','repair_seconds','gate_seconds'))
    arrival=l['selected_transitions']/seconds if seconds else 0
    capacity=l.get('processed_transitions',0)/work if work else 0
    checks.update(fresh_counter_wave=bool(samples) and samples[0]['learning']['executed_decisions']<4,
        qualified_actual_gameplay=bool(samples) and all(s['qualified'] is not False for s in samples),
        sampled_counts=l['selected_transitions']==(l['executed_decisions']+63)//64 and l['intentionally_unsampled_transitions']+l['selected_transitions']==l['learning_enabled_decisions'],
        full_prefix_native_replay_verified=l.get('processed_transitions',0)>=16 and l.get('rejected_contexts',0)==0,
        actual_public_repair_progress=l.get('updates',0)>=2,
        service_capacity_above_arrival=capacity>arrival,
        queue_headroom=max((s['learning'].get('queue_depth',0) for s in samples),default=64)<=8 and l.get('queue_depth',64)<=2,
        playback_at_least_five_decisions_per_second=l['executed_decisions']/seconds>=5 if seconds else False,
        old_actor_controls_unchanged=before['model']['id']==after['model']['id'] and before['mode']==after['mode'] and before['learning']['enabled']==after['learning']['enabled'],
        stage_paused=final['mode']=='idle' and not l['enabled'] and not l.get('busy'),
        no_errors=not error and not l.get('error'))
    receipt={'schema':'doom-stride64-five-minute-staging/1','unix':time.time(),'passed':all(checks.values()),'checks':checks,
        'error':error,'samples':samples,'final':l,'seconds':seconds,
        'metrics':{'decisions_per_second':l['executed_decisions']/seconds if seconds else None,
                   'arrival_per_minute':arrival*60,'service_capacity_per_active_minute':capacity*60,
                   'accounted_feedback_repair_gate_seconds':work,'max_queue':max((s['learning'].get('queue_depth',0) for s in samples),default=None),
                   'selected':l['selected_transitions'],'processed':l.get('processed_transitions',0),'updates':l.get('updates',0)},
        'interpretation':'Measured service capacity uses completed native feedback, repair and gate work seconds; it excludes bookkeeping and is not a long-run guarantee. Queue headroom is checked separately.',
        'visual_browser_test':False,'control_requests_to8667_or8666':0}
    (APP/'qa/stride64_api.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('samples','final')}),flush=True)
    return receipt['passed']


if __name__=='__main__':raise SystemExit(0 if asyncio.run(main()) else 1)
