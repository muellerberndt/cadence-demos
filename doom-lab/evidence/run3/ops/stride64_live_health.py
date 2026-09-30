"""Read-only fixed two-minute private Lab health, no WebSocket/control requests."""
import json
from pathlib import Path
import time
import urllib.request
from v3.interface import digest
from v3.practice import atomic_json

APP=Path('/home/ec2-user/doom-v3-20260929/lab/baby_04')
URL='http://127.0.0.1:8667'


def main():
    def read(path):
        with urllib.request.urlopen(URL+path,timeout=20) as response:return response.read()
    start=time.monotonic();samples=[]
    while True:
        state=json.loads(read('/state'));l=state['learning'];seconds=time.monotonic()-start
        samples.append(dict(seconds=seconds,model=state['model'],mode=state['mode'],episode=state['episode'],
            qualified=state.get('shadow',{}).get('qualified'),learning=l))
        print(json.dumps(dict(seconds=round(seconds),**{k:l.get(k) for k in
            ('executed_decisions','selected_transitions','processed_transitions','updates','promotions','queue_depth','error')})),flush=True)
        if seconds>=120:break
        time.sleep(min(10,120-seconds))
    first=samples[0]['learning'];last=samples[-1]['learning'];elapsed=samples[-1]['seconds']-samples[0]['seconds']
    delta={k:last.get(k,0)-first.get(k,0) for k in ('executed_decisions','selected_transitions','processed_transitions','updates','promotions','intentionally_unsampled_transitions')}
    manifest=json.loads((APP/'source_manifest.json').read_text())
    source_checks={k:digest((APP/k).read_bytes())==v['sha256'] for k,v in manifest['files'].items()}
    html=read('/').decode();graph=json.loads(read('/graph'));training=json.loads(read('/static/v3_training_status.json'))
    checks=dict(no_errors=all(not s['learning'].get('error') for s in samples),
        qualified_sampled_queries=all(s['qualified'] is True for s in samples),
        correct_model=all(s['model']['id']=='confirmed-ad9-stride64-gate32' for s in samples),
        enabled_student=all(s['mode']=='student' and s['learning']['enabled'] for s in samples),
        actor_identity_coherent=all(s['model']['fingerprint']==s['learning']['champion_sha256'][:12] for s in samples),
        stride64=all(s['learning']['collection_stride']==64 for s in samples),
        queue_headroom=max(s['learning']['queue_depth'] for s in samples)<64,
        source_unchanged=all(source_checks.values()),
        collection_status_served='collection_stride' in html and 'intentionally_unsampled_transitions' in html,
        actual_native_feedback_progress=delta['processed_transitions']>0,
        actual_public_repair_progress=delta['updates']>0)
    receipt=dict(schema='doom-stride64-live-health/1',read_only=True,unix=time.time(),seconds=elapsed,
        passed=all(checks.values()),checks=checks,samples=samples,delta=delta,
        decisions_per_second=delta['executed_decisions']/elapsed,
        selected_per_minute=delta['selected_transitions']/elapsed*60,
        processed_per_minute=delta['processed_transitions']/elapsed*60,
        max_queue=max(s['learning']['queue_depth'] for s in samples),source_checks=source_checks,
        graph_keys=list(graph),training_status_unix=training.get('updated_unix'),
        visual_browser_test=False,control_requests=0)
    atomic_json(APP/'qa/live_stride64_health.json',receipt)
    print(json.dumps({k:receipt[k] for k in ('passed','checks','delta','decisions_per_second','selected_per_minute','processed_per_minute','max_queue')}))


if __name__=='__main__':main()
