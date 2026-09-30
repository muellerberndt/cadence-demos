"""Load only the exact Cadence sources that own the preserved Doom checkpoints."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

CORE_SET_SHA256 = '996d7ffdd43f7deffae20272ea35948f2704a7aa2c466d2c5a90905b438deefb'
RUNTIME = Path(__file__).resolve().parents[1]/'runtime'/('cadence-'+CORE_SET_SHA256[:16])


def verify_source(root, manifest):
    root = Path(root).resolve()
    if manifest.get('schema') != 'cadence-pinned-runtime/1' or manifest.get('core_set_sha256') != CORE_SET_SHA256:
        raise ValueError('Unrecognized pinned Cadence runtime manifest')
    files = manifest['files']
    canonical = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
    if hashlib.sha256(canonical).hexdigest() != CORE_SET_SHA256:
        raise ValueError('Pinned Cadence source set digest differs')
    if set(p.name for p in (root/'cadence').glob('*.py')) != set(files):
        raise ValueError('Pinned Cadence source set has missing or extra modules')
    for name, expected in files.items():
        if '/' in name or hashlib.sha256((root/'cadence'/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Pinned Cadence source changed: '+name)
    return root


def load():
    manifest = json.loads((RUNTIME/'manifest.json').read_text())
    root = verify_source(os.environ.get('CADENCE_SRC', RUNTIME), manifest)
    loaded = sys.modules.get('cadence')
    if loaded is not None and Path(loaded.__file__).resolve().parent != root/'cadence':
        raise RuntimeError('A different Cadence package was already imported; start a clean v1 process')
    sys.path.insert(0, str(root))
    import cadence
    if Path(cadence.__file__).resolve().parent != root/'cadence':
        raise RuntimeError('Cadence import escaped the pinned runtime')
    return root
