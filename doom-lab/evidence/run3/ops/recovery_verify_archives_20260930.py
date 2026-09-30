"""Read-only recovery audit; emits JSON to stdout and writes no remote files."""
from pathlib import Path
import hashlib,json,time,signal
signal.alarm(180)
BASE=Path('/home/ec2-user/doom-v3-20260929')
EXPECTED={'archive_sha256': ['b907800d1f042f4d72d615406c2e1d59124d8be291fa27e4f96714608c8ded88', '6dc46525a7cb7a6faf27cb54a30ea40abb7e83c65cc8e79b9e347a166f075711', '676d806f7eea9abe3161ee495daa454a8bd7b903c43ac54d09ba1ceb942e3ad4', '5b6b987834f7516a85cdf65d7271df26759fd7e6944d1e4166f70355bf363eb6', 'b97604b7c5902ae5d22559f5c75155a86053ae0d32f98d1639ed04b13f11a610', '96c9d7300ebb3469dbe24ac7c522699ad15822e96bc4ad98195fbe555d252b2e'], 'models': [{'name': 'ad9', 'path': 'runs/practice_horizon_01/h144/exports/h144_update4/bundle.json', 'checkpoint': 'ad9b330cd1c1c582a0bb135956f87a9f8e4c0f106d80c35bb60b39c0328ef2cc', 'file_sha256': '844503dcdce34a253dcb3ba2689b7cd042a338b5bfd381684dfcf5ffc3237dd9'}, {'name': '9b97', 'path': 'runs/replay_ratio_01/life1_old24/exports/h144_update4/bundle.json', 'checkpoint': '9b97de044740965b8cc103b38e04e0042301896466ccb5dd08f24023c362be07', 'file_sha256': '05845dcb33e286669e40b3ff4a34cfebccf920531dfa0fec8c7fa189bc64bf3f'}, {'name': 'native_blend_eta0', 'path': 'runs/native_blend_02/eta0/bundle.json', 'checkpoint': '0c071bf858f75d7d6c6f4f58a60a8c7a37559b1d1201501d8b5e687de7a9f3d9', 'file_sha256': '3b9751010c6804ab6a2f547ac8d50e4ef305b0511e147a68fc04438aa6c14053'}, {'name': 'native_blend_eta01', 'path': 'runs/native_blend_02/eta01/bundle.json', 'checkpoint': 'b703737a9198bde311e05417add2afeef3c12f076c96d3c93b3b0073c378e61a', 'file_sha256': 'f647e25eceb744f84abd5212bdd72bead9630824827dee28a9307885279ff4dd'}, {'name': 'native_blend_eta025', 'path': 'runs/native_blend_02/eta025/bundle.json', 'checkpoint': '19f2a151a1cfa8b14abc2e875c6301a68eed8041fef7d40de7d1499815ac5fb3', 'file_sha256': '7bfc10c4709387d6b7d4215d36794dada0fc2f4d25be8b2a27e327e9c3254ab0'}, {'name': 'native_blend_eta1', 'path': 'runs/native_blend_02/eta1/bundle.json', 'checkpoint': '00ab8c64026501c8fb276b7d25ab832ea5528e511d6c0762063d0df4abcfc153', 'file_sha256': '5896ab172bbe631777b823a2c23db1053a69a4799a5fb7a83a8ce752bfe5efcd'}], 'native_blend_receipt_sha256': '876c8f1ec383c937bb60cc966a5599f480ca852ba7ea1be5679bfcb4821d56b4'}
started=time.monotonic()
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()
archives=[];models=[];errors=[]
for i,expected in enumerate(EXPECTED['archive_sha256'],1):
 try:
  receipt=BASE/'receipts'/f'gpu_durable_{i:02d}_verified.json';saved=json.loads(receipt.read_text())
  archive=BASE/'receipts'/f'gpu_durable_{i:02d}.tar.gz';folder=BASE/f'gpu_archive_{i:02d}'
  manifest=folder/f'durable_{i:02d}_manifest.json';meta=json.loads(manifest.read_text())
  actual=sha(archive);assert actual==expected==saved['archive_sha256']
  assert archive.stat().st_size==saved['archive_bytes'] and sha(manifest)==saved['manifest_sha256']
  checked=0;size=0;bad=[]
  for row in meta['files']:
   path=folder/row['path']
   if not path.is_file() or path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:bad.append(row['path'])
   checked+=1;size+=row['bytes']
  assert checked==saved['verified_files']
  if bad:errors.append({'archive':i,'mismatched_files':bad})
  archives.append(dict(number=i,passed=not bad,archive_sha256=actual,archive_bytes=archive.stat().st_size,manifest_sha256=sha(manifest),saved_verification_sha256=sha(receipt),files_checked=checked,file_bytes_checked=size,mismatched_files=bad))
 except Exception as exc:errors.append({'archive':i,'error':repr(exc)})
for expected in EXPECTED['models']:
 try:
  path=BASE/expected['path'];actual=sha(path);bundle=json.loads(path.read_text())
  snapshot=hashlib.sha256(bundle['snapshot'].encode()).hexdigest()
  assert actual==expected['file_sha256'] and snapshot==expected['checkpoint']==bundle['hashes']['checkpoint_sha256']
  models.append(dict(name=expected['name'],path=str(path),passed=True,file_sha256=actual,checkpoint_sha256=snapshot,bytes=path.stat().st_size))
 except Exception as exc:errors.append({'model':expected['name'],'error':repr(exc)})
blend_receipt=BASE/'runs/native_blend_02/receipt.json'
blend_receipt_match=sha(blend_receipt)==EXPECTED['native_blend_receipt_sha256']
if not blend_receipt_match:errors.append({'native_blend_receipt':'differs from saved local receipt'})
result=dict(schema='doom-recovery-durable-audit/1',created_unix=time.time(),host='CPU1 recovery 3.93.54.244',passed=not errors and len(archives)==6 and len(models)==len(EXPECTED['models']),archives=archives,models=models,errors=errors,seconds=time.monotonic()-started,native_blend_saved_receipt_match=blend_receipt_match,causal_probe=dict(cpu1_run_exists=(BASE/'runs/small_batch64_causal_01').exists(),scope='Probe was targeted atCPU2, so CPU1absence alone is not execution proof. Tool receipt shows sourceSCP succeeded but following remoteunittest was rejected beforeexecution by quota/autoreview; subsequent launch call was neverreached. Parent separately reported noCPU2run directory. No causalresults claimed.'),scope='Read-only hashes against saved DATA_CATALOGUE archive identities, archived per-file manifests, prior verification receipts, and saved selected-bundle hashes. No training, native evaluation, service launch, model change, or remote file write.')
print(json.dumps(result,sort_keys=True,indent=2))
