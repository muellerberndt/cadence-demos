"""Prepare isolated AWS staging data; never start a server or select the winner."""
import json
from pathlib import Path
from dataclasses import asdict

from v3.brain import load_bundle, write_bundle
from v3.interface import canonical, digest
from v3.lab_deployment import initialize
from v3.practice import PracticeConfig, atomic_json
from v3.practice_protocol import make_package, unpack_package
from v3.runtime import prepare_staging_bundle, validate_deployment

BASE = Path('/home/ec2-user/doom-v3-20260929')
APP = BASE/'lab/baby_02'
FOUNDER = BASE/'lab/baby_01/data/models/v3/baby-small-depth3-seed0-epoch002/bundle.json'
CANDIDATE = BASE/'runs/practice_horizon_01/h144/exports/h144_update4/bundle.json'


def main():
    manifest = json.loads((APP/'source_manifest.json').read_text())
    for name, receipt in manifest['files'].items():
        if digest((APP/name).read_bytes()) != receipt['sha256']:
            raise ValueError('Staging source differs from manifest: '+name)
    _, founder = load_bundle(FOUNDER, device='python')
    _, active = load_bundle(CANDIDATE, device='python')
    if founder['hashes']['checkpoint_sha256'] != '3076041351210d5818df542b23c167278a76ce59d7ceae531b52e05398f80ad8':
        raise ValueError('Unexpected retention founder')
    if active['hashes']['checkpoint_sha256'] != 'ad9b330cd1c1c582a0bb135956f87a9f8e4c0f106d80c35bb60b39c0328ef2cc':
        raise ValueError('Unexpected candidate')
    config = PracticeConfig(gate_tasks=('basic',), feedback_horizon_tics=144,
        feedback_workers=20, gate_workers=4, max_journal_bytes=512*1024**2)
    packaged = make_package(active, founder, active, config=config, wave_name='browser_h144_01')
    packaged = prepare_staging_bundle(packaged, 'basic', source_platform=founder['metadata']['source_platform'])
    validate_deployment(packaged)
    resolved = unpack_package(packaged)
    initialization = initialize(FOUNDER, root=APP, task='basic',
        source_platform=founder['metadata']['source_platform'],
        doom_wad='/home/ec2-user/payload/doom/wads/doom1.wad')
    path = APP/'prepared/h144_update4_practice.json'
    write_bundle(path, packaged)
    atomic_json(APP/'prepared/practice_config.json', asdict(config))
    receipt = {'schema': 'doom-protocol-stage-preparation/1', 'source_manifest_sha256': digest((APP/'source_manifest.json').read_bytes()),
        'package_path': str(path), 'package_file_sha256': digest(path.read_bytes()), 'package_bytes': path.stat().st_size,
        'wave_sha256': resolved['wave_sha256'], 'native_protocol': resolved['protocol'],
        'retention_founder': founder['hashes']['checkpoint_sha256'], 'initial_actor': active['hashes']['checkpoint_sha256'],
        'continuation_actor': resolved['continuation']['hashes']['checkpoint_sha256'],
        'seed_replay_sha256': founder['metadata']['seed_replay_sha256'], 'practice_config': asdict(config),
        'initialization': initialization, 'selected_candidate': False, 'learning_enabled': False,
        'server_started': False, 'intended_staging_port': 8668}
    atomic_json(APP/'prepared/receipt.json', receipt)
    print(canonical(receipt))


if __name__ == '__main__': main()
