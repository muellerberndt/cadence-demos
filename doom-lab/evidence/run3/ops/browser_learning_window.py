"""Bound an authorized browser learning window; never choose gameplay actions."""
import argparse
import asyncio
import json
from pathlib import Path
import time
import aiohttp


async def monitor(args):
    start = time.time(); deadline = start+args.seconds
    out = args.out; out.mkdir(parents=True, exist_ok=False)
    receipt = {'schema':'doom-browser-learning-window/1','started_unix':start,'deadline_unix':deadline,
               'model_id':args.model,'url':args.url,'seconds':args.seconds,'state':'watching',
               'purpose':'Read-only supervision until deadline/error; then disable learning and pause this model only'}
    def save():
        temporary=out/'status.tmp';temporary.write_text(json.dumps(receipt,indent=2)+'\n');temporary.replace(out/'status.json')
    save();failures=0;reason='deadline'
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async def state():
            async with session.get(args.url+'/state') as response:
                response.raise_for_status();return await response.json()
        while time.time()<deadline:
            try:
                current=await state();failures=0
                sample={'unix':time.time(),'mode':current['mode'],'model':current['model'],
                        'learning':current['learning'],'episode':current['episode']}
                with (out/'samples.jsonl').open('a') as stream:stream.write(json.dumps(sample,separators=(',',':'))+'\n')
                receipt.update(last_sample=sample,updated_unix=time.time());save()
                if current['model']['id']!=args.model:
                    receipt.update(state='model_changed_by_another_controller',finished_unix=time.time());save();return
                if current['learning'].get('error'):
                    reason='learner_error';break
            except Exception as error:
                failures+=1;receipt.update(last_error=repr(error),consecutive_errors=failures);save()
                if failures>=3:reason='health_unavailable';break
            await asyncio.sleep(min(15,max(0,deadline-time.time())))
        try:
            current=await state()
            if current['model']['id']==args.model:
                async with session.ws_connect(args.url+'/ws') as ws:
                    await ws.send_json({'type':'learning','enabled':False})
                    await ws.send_json({'type':'mode','mode':'idle'})
                    for _ in range(30):
                        await asyncio.sleep(.2);current=await state()
                        if not current['learning']['enabled'] and current['mode']=='idle':break
                if current['learning']['enabled'] or current['mode']!='idle':
                    raise RuntimeError('Bounded window could not verify its pause request')
                receipt.update(state='paused',pause_reason=reason,final=current)
            else:receipt.update(state='model_changed_by_another_controller',pause_reason=reason)
        except Exception as error:
            receipt.update(state='pause_failed',pause_reason=reason,last_error=repr(error))
        receipt['finished_unix']=time.time();save()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8667')
    parser.add_argument('--model',required=True)
    parser.add_argument('--seconds',type=float,default=7200)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if not 0<args.seconds<=7200:raise ValueError('Positive finite window at most2hours required')
    if args.url not in ('http://127.0.0.1:8667','http://127.0.0.1:8668'):
        raise ValueError('Private experimental Lab ports only')
    asyncio.run(monitor(args))
