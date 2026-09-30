"""New immutable wave/source directory; old every-action wave is untouched."""
from pathlib import Path
import json
import os
import subprocess
import time

from v3.brain import load_bundle, write_bundle
from v3.interface import canonical, digest
from v3.lab_deployment import initialize
from v3.practice import PracticeConfig, atomic_json
from v3.practice_protocol import make_package, unpack_package
from v3.runtime import validate_deployment

BASE=Path('/home/ec2-user/doom-v3-20260929')
APP=BASE/'lab/baby_03'
OLD=BASE/'lab/baby_02'


def main():
    manifest=json.loads((APP/'source_manifest.json').read_text())
    assert all(digest((APP/name).read_bytes())==v['sha256'] for name,v in manifest['files'].items())
    source=OLD/'prepared/h144_update4_confirmed_practice.json'
    assert digest(source.read_bytes())=='fb43a6bdf087777e616c2dd018bdd1f16a4d326c695f1daa4606a8a254562685'
    _,active=load_bundle(source,device='python')
    founder=active['metadata']['practice_package']['founder']
    assert active['hashes']['checkpoint_sha256'].startswith('ad9b330cd1c1')
    config=PracticeConfig(gate_tasks=('basic',),feedback_horizon_tics=144,
        feedback_workers=20,gate_workers=4,max_journal_bytes=512*1024**2)
    packed=make_package(active,founder,active,config=config,
                        wave_name='browser_h144_stride32_01',collection_stride=32)
    validate_deployment(packed)
    # Neutral startup scaffold and separately selectable original founder.
    founder_path=APP/'prepared/founder.json';write_bundle(founder_path,founder)
    initialize(founder_path,root=APP,source_platform=founder['metadata']['source_platform'],
               doom_wad='/home/ec2-user/payload/doom/wads/doom1.wad')
    target=APP/'data/models/v3/confirmed-h144-ad9-stride32/bundle.json';write_bundle(target,packed)
    receipt={'schema':'doom-stride-stage-preparation/1','unix':time.time(),'app':str(APP),
        'old_wave_preserved':str(OLD),'source_manifest_sha256':digest((APP/'source_manifest.json').read_bytes()),
        'bundle':str(target),'bundle_file_sha256':digest(target.read_bytes()),
        'wave_sha256':unpack_package(packed)['wave_sha256'],
        'checkpoint_sha256':packed['hashes']['checkpoint_sha256'],
        'collection':unpack_package(packed)['experience_collection'],
        'native_contract':unpack_package(packed)['protocol']['native_contract'],
        'retention_founder_checkpoint_sha256':founder['hashes']['checkpoint_sha256'],
        'initial_mode':'idle','learning_enabled':False}
    atomic_json(APP/'qa/preparation.json',receipt)
    env={**os.environ,'DOOM_LAB_PORT':'8668','DOOM_LAB_ENABLE_V3':'1','DOOM_LAB_V3_PRACTICE':'1',
         'DOOM_FEEDBACK_WORKERS':'20','DOOM_PRACTICE_GATE_WORKERS':'4'}
    with (APP/'qa/staging.log').open('ab') as log:
        process=subprocess.Popen(['timeout','-k','30s','900s','/home/ec2-user/venv/bin/python','-u','server.py'],
            cwd=APP,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    receipt['staging_pid']=process.pid
    atomic_json(APP/'qa/preparation.json',receipt)
    print(canonical(receipt))


if __name__=='__main__':main()
