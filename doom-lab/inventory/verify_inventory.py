#!/usr/bin/env python3
"""Verify saved local models, pinned evidence and the exact runtime without training/network.

Default mode writes nothing; --out records a new receipt.
"""
from __future__ import annotations
import argparse,datetime,hashlib,json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def read(path):return json.loads(path.read_text())

DOCS=['README.md','docs/MODELS.md','docs/COMPONENTS.md','docs/EXPERIMENTS.md','docs/DEPLOYMENT.md','inventory/README.md','v1/PLAN.md']

def verify(root):
    manifest=read(root/'models/manifest.json')
    runtime_dir=root/'runtime/cadence-996d7ffdd43f7def';runtime=read(runtime_dir/'manifest.json')
    errors=[];checks=[]
    def check(ok,message):
        if not ok:errors.append(message)
        return bool(ok)
    for entry in manifest['models']:
        path=root/entry['local_path']
        try:
            data=path.read_bytes();body=json.loads(data)
            snapshot=body['snapshot'] if isinstance(body,dict) and 'snapshot' in body else data.decode()
            checkpoint=hashlib.sha256(snapshot.encode()).hexdigest()
            expected=entry.get('bundle_sha256',entry.get('file_sha256'))
            okay=check(sha(path)==expected and checkpoint==entry['checkpoint_sha256'],'model identity: '+str(path))
            implementation=json.loads(snapshot)['implementation']
            impl_ok=check(len(implementation)==7 and all(runtime['files'].get(k)==v for k,v in implementation.items()),'implementation: '+str(path))
            for evidence in entry.get('evidence',[]):check(sha(root/evidence['path'])==evidence['sha256'],'evidence changed: '+evidence['path'])
            checks.append({'path':entry['local_path'],'bytes':len(data),'file_sha256':sha(path),
                           'checkpoint_sha256':checkpoint,'pass':okay,'implementation_pass':impl_ok})
        except Exception as exc:errors.append(str(path)+': '+type(exc).__name__+': '+str(exc))
    for name,expected in runtime['files'].items():check(sha(runtime_dir/'cadence'/name)==expected,'runtime source: '+name)
    for name,entry in runtime.get('extra_files',{}).items():check(sha(runtime_dir/name)==entry['sha256'],'runtime packaging context: '+name)
    check(hashlib.sha256(canonical(runtime['files'])).hexdigest()==runtime['core_set_sha256'],'runtime set digest')
    check(len(runtime['files'])==12,'expected twelve runtime source files')
    check(len(manifest['models'])==14,'expected14 saved Cadence snapshots')
    for name in DOCS:
        path=root/name
        for target in re.findall(r'\]\(([^)]+)\)',path.read_text()):
            if not target.startswith(('https:','http:','#')):check((path.parent/target.split('#')[0]).exists(),'broken documentation link: '+name+' '+target)
    return {'schema':'doom-local-model-verification/3','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'producer_sha256':sha(Path(__file__)),'pass':not errors,'training_run':False,'native_evaluation_run':False,'network_used':False,
      'cadence_snapshots':len(checks),'preserved_bundle_or_snapshot_bytes':sum(x['bytes'] for x in checks),
      'runtime_files':len(runtime['files']),'manifest_sha256':sha(root/'models/manifest.json'),
      'runtime_manifest_sha256':sha(runtime_dir/'manifest.json'),'checks':checks,'errors':errors,
      'scope':'Local saved bytes, snapshot identities, pinned source, evidence hashes and documentation link integrity.'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);ap.add_argument('--out',type=Path);args=ap.parse_args()
    result=verify(args.root.resolve())
    if args.out:args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
    raise SystemExit(0 if result['pass'] else 1)

if __name__=='__main__':main()
