"""Isolated8668 HTTP/WS/native QA; never controls8667 or8666."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import time
import aiohttp

APP = Path('/home/ec2-user/doom-v3-20260929/lab/baby_02')
BASE = 'http://127.0.0.1:8668'


async def main():
    checks = {}; samples = []; error = None
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
        async def get(path, base=BASE):
            async with session.get(base+path) as response:
                response.raise_for_status(); return await response.json()
        async def wait_model(name):
            deadline = time.monotonic()+60
            while time.monotonic()<deadline:
                state = await get('/state')
                if state['model'].get('error'): raise RuntimeError(state['model']['error'])
                expected = (payload['hashes']['checkpoint_sha256'] if name==model_id
                            else initial['learning']['champion_sha256'])
                if (state['model']['id']==name and not state['model']['pending']
                        and state['learning'].get('champion_sha256')==expected
                        and state['model'].get('fingerprint')==expected[:12]): return state
                await asyncio.sleep(.2)
            raise TimeoutError('Model swap did not complete')
        before = await get('/state', 'http://127.0.0.1:8667')
        initial = await get('/state')
        original_id = initial['model']['id']
        registry = await get('/models'); ids = {row['id'] for row in registry['models']}
        payload = json.loads((APP/'prepared/h144_update4_confirmed_practice.json').read_text())
        async with session.post(BASE+'/import', params={'name':'confirmed-h144-ad9'}, json=payload) as response:
            answer = await response.json(); response.raise_for_status(); assert answer['ok'],answer
        model_id = answer['id']
        checks['package_import_does_not_activate'] = (await get('/state'))['model']['id']==original_id
        tampered = copy.deepcopy(payload)
        tampered['metadata']['practice_package']['descriptor']['protocol']['native_contract']['horizon_tics']=300
        async with session.post(BASE+'/import', params={'name':'qa-invalid-protocol'}, json=tampered) as response:
            checks['changed_protocol_refused'] = response.status==400
        ws = await session.ws_connect(BASE+'/ws')
        try:
            await ws.send_json({'type':'model','id':model_id}); state = await wait_model(model_id)
            exported = await get('/export')
            checks['portable_package_roundtrip'] = exported==payload
            learning = state['learning']
            checks['h144_original_retention_and_frozen_continuation'] = (
                learning['native_feedback_horizon_tics']==144
                and learning['retention_founder_checkpoint_sha256'].startswith('307604135121')
                and learning['continuation_checkpoint_sha256'].startswith('ad9b330cd1c1')
                and learning['available'] and not learning['enabled'])
            graph = await get('/graph')
            checks['truthful_bounded_graph'] = (graph['total_edges']==state['model']['edges']==44384
                and graph['sampled_edges']==len(graph['edges'])==1400
                and graph['n_periphery']+graph['n_fovea']==2020 and graph['motor']==20)
            await ws.send_json({'type':'mode','mode':'student'})
            start=time.monotonic()
            while time.monotonic()-start<10:
                state=await get('/state');shadow=state['shadow']
                samples.append({'seconds':time.monotonic()-start,'episode':state['episode'],
                    'qualified':shadow.get('qualified'),'action':shadow.get('action'),
                    'query_seconds':shadow.get('query_seconds'),'error':state['learning'].get('error'),
                    'learning_enabled':state['learning']['enabled']})
                await asyncio.sleep(.25)
            await ws.send_json({'type':'mode','mode':'idle'});await asyncio.sleep(.4)
            state=await get('/state')
            checks['qualified_native_actor'] = sum(s['qualified'] is True for s in samples)>=5 and all(s['qualified'] is not False and not s['error'] for s in samples)
            checks['practice_remained_off'] = all(not s['learning_enabled'] for s in samples)
            checks['native_episode_no_fallback'] = bool(state['learning']['last_episode'] and state['learning']['last_episode']['fallback_actions']==0)
            async with session.get(BASE+'/video') as response:
                data=await response.content.read(8192)
                checks['mjpeg_frame'] = response.status==200 and b'Content-Type: image/jpeg' in data
            async with session.get(BASE+'/') as response: html=await response.text()
            checks['ui_controls_preserved'] = all(x in html for x in ('id="learn-btn"','id="model-sel"','id="import"','id="pause-btn"','FULL-GAME DEVELOPMENT'))
            checks['registry_preserved'] = ids <= {row['id'] for row in (await get('/models'))['models']}
        except Exception as exception:
            error=repr(exception)
        finally:
            await ws.send_json({'type':'mode','mode':'idle'})
            await ws.send_json({'type':'model','id':original_id})
            final=await wait_model(original_id)
            await ws.close()
        after=await get('/state','http://127.0.0.1:8667')
        checks['original8667_unchanged'] = before['model']==after['model'] and before['mode']==after['mode'] and before['learning']==after['learning']
        checks['staging_restored_idle_founder'] = final['mode']=='idle' and final['model']['fingerprint'].startswith('307604') and not final['learning']['enabled']
    receipt={'schema':'doom-protocol-staging-api-qa/1','created_unix':time.time(),'passed':not error and all(checks.values()),
        'checks':checks,'error':error,'samples':samples,'candidate_registry_id':model_id,'current_staging_id':original_id,
        'port':8668,'visual_browser_test':False,'control_requests_to8667_or8666':0,
        'package_file_sha256':hashlib.sha256((APP/'prepared/h144_update4_confirmed_practice.json').read_bytes()).hexdigest()}
    (APP/'qa/api.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='samples'}));return receipt['passed']


if __name__=='__main__': raise SystemExit(0 if asyncio.run(main()) else 1)
