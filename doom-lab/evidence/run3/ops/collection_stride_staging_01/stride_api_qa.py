"""Bounded native throughput/feedback QA on8668; no controls to8667/8666."""
import asyncio
import json
from pathlib import Path
import time
import aiohttp

APP=Path('/home/ec2-user/doom-v3-20260929/lab/baby_03')
URL='http://127.0.0.1:8668'
MODEL='confirmed-h144-ad9-stride32'


async def main():
    samples=[];checks={};error=None
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async def state(port=8668):
            async with session.get(f'http://127.0.0.1:{port}/state') as response:
                response.raise_for_status();return await response.json()
        before=await state(8667)
        ws=await session.ws_connect(URL+'/ws')
        try:
            await ws.send_json({'type':'model','id':MODEL})
            for _ in range(100):
                current=await state();l=current['learning']
                if current['model']['id']==MODEL and l.get('collection_stride')==32 and not current['model']['pending']:break
                await asyncio.sleep(.2)
            else:raise TimeoutError('Stride model not selected')
            async with session.get(URL+'/export') as response:exported=await response.json()
            checks['explicit_portable_stride32']=exported['metadata']['practice_package']['descriptor']['experience_collection']['collection_stride']==32
            await ws.send_json({'type':'learning','enabled':True})
            await ws.send_json({'type':'mode','mode':'student'})
            start=time.monotonic()
            while time.monotonic()-start<90:
                current=await state();l=current['learning']
                samples.append({'seconds':time.monotonic()-start,'episode':current['episode'],'mode':current['mode'],
                    'qualified':current.get('shadow',{}).get('qualified'),
                    'query_seconds':current.get('shadow',{}).get('query_seconds'),
                    'learning':l})
                if l.get('error'):raise RuntimeError(l['error'])
                await asyncio.sleep(2)
            final=samples[-1]['learning'];first=samples[0]['learning']
            seconds=samples[-1]['seconds']-samples[0]['seconds']
            decision_rate=(final['executed_decisions']-first.get('executed_decisions',0))/seconds
            checks['qualified_actual_gameplay']=all(s['qualified'] is not False for s in samples) and any(s['qualified'] is True for s in samples)
            checks['stride_indices_and_counts']=final['selected_transitions']==(final['executed_decisions']+31)//32 and final['selected_transitions']+final['intentionally_unsampled_transitions']==final['learning_enabled_decisions']
            checks['full_prefix_native_replay_verified']=final.get('processed_transitions',0)>=8 and final.get('rejected_contexts',0)==0
            checks['actual_public_repair_progress']=final.get('updates',0)>=1
            checks['bounded_feedback_queue']=max(s['learning'].get('queue_depth',0) for s in samples)<64 and not any(s['learning'].get('pending_transition') for s in samples[1:])
            checks['playback_at_least_five_decisions_per_second']=decision_rate>=5
            checks['cross_episode_counter']=samples[-1]['episode']>samples[0]['episode']
        except Exception as failure:error=repr(failure)
        finally:
            await ws.send_json({'type':'learning','enabled':False})
            await ws.send_json({'type':'mode','mode':'idle'})
            await asyncio.sleep(.5)
            final_state=await state();await ws.close()
        after=await state(8667)
        checks['old_actor_control_unchanged']=before['model']['id']==after['model']['id'] and before['mode']==after['mode'] and before['learning']['enabled']==after['learning']['enabled']
        checks['stage_paused_after_test']=final_state['mode']=='idle' and not final_state['learning']['enabled']
    receipt={'schema':'doom-stride-native-staging/1','unix':time.time(),'passed':not error and all(checks.values()),
        'checks':checks,'error':error,'samples':samples,'final':final_state['learning'],
        'decisions_per_second':decision_rate if 'decision_rate' in locals() else None,
        'visual_browser_test':False,'control_requests_to8667_or8666':0,
        'selection_limit':'One90second throughput/positive-admission probe; no gameplay gain or long-run capacity claim'}
    (APP/'qa/stride_api.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('samples','final')}),flush=True)
    return receipt['passed']


if __name__=='__main__':raise SystemExit(0 if asyncio.run(main()) else 1)
