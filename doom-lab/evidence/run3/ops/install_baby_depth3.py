"""One-time private AWS Lab import; no actor activation or learning command."""
from pathlib import Path
import json
import urllib.request
from v3.brain import load_bundle, write_bundle
from v3.interface import canonical, digest
from v3.practice import attach_seed_replay, seed_replay_from_dataset
from v3.runtime import prepare_staging_bundle, validate_deployment

APP = Path.cwd()
BASE = APP.parents[1]
source = BASE/'runs/baby_bootstrap_02/small_depth3_centered_seed0/checkpoints/doom_baby_small_depth3_centered_seed0_epoch002_307604135121.json'
_, bundle = load_bundle(source, device='python')
screen = json.loads((BASE/'runs/baby_screen_02/summary.json').read_text())
row, = [r for r in screen['candidates'] if r['candidate'] == 'small_depth3_centered_seed0']
assert row['checkpoint_sha256'] == bundle['hashes']['checkpoint_sha256']
assert row['status'] == 'complete' and row['evaluation']['all_scheduled_accounted']
bundle = attach_seed_replay(bundle, seed_replay_from_dataset(BASE/'datasets/baby_bootstrap_02', bundle))
bundle = prepare_staging_bundle(bundle, 'basic', source_platform=json.loads((APP/'source_platform.json').read_text()))
evidence = {k: row[k] for k in ('candidate', 'checkpoint_sha256', 'evaluation')}
bundle['metadata'].update(label='Basic acquisition; navigation unacquired (4/4 dev Basic, 0/4 navigation)',
    development_screen=evidence, development_screen_sha256=digest(canonical(evidence)),
    ability_scope='Experimental Basic acquisition; four development episodes, not independent confirmation. Navigation unacquired; general Doom competence unmeasured.')
validate_deployment(bundle)
target = APP/'deployments/depth3_seed0_epoch002.json'
if target.exists():
    raise FileExistsError(target)
write_bundle(target, bundle)
request = urllib.request.Request('http://127.0.0.1:8667/import?name=baby-small-depth3-seed0-epoch002',
    data=json.dumps(bundle).encode(), headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(request, timeout=30) as response:
    result = json.load(response)
assert result.get('ok'), result
receipt = {'schema':'doom-v3-baby-founder-install/1', 'source':str(source), 'prepared_bundle':str(target),
    'registry_id':result['id'], 'checkpoint_sha256':bundle['hashes']['checkpoint_sha256'],
    'genome':bundle['genome'], 'seed_replay_rows':len(bundle['metadata']['seed_replay']),
    'seed_replay_sha256':bundle['metadata']['seed_replay_sha256'],
    'development_screen_sha256':bundle['metadata']['development_screen_sha256'],
    'development_screen':evidence, 'deployment_validation':bundle['metadata']['deployment_validation'],
    'activated':False, 'learning_enabled':False}
(APP/'deployments/depth3_seed0_epoch002_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
