"""Archive a closed AWS training wave with per-file identities; no cloud calls."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import time


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--wave', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--extra', action='append', default=[])
    args = parser.parse_args()
    root = args.root.resolve()
    if any('/' in value or value in ('', '.', '..') for value in
           (args.wave, args.source, args.name)):
        raise ValueError('Simple directory names required')
    receipt = root / 'runs' / args.wave / 'receipt.json'
    if not receipt.is_file():
        raise ValueError('Training wave has not closed')
    outcome = json.loads(receipt.read_text())
    if outcome.get('status') not in ('complete', 'failed', 'wall_cap'):
        raise ValueError('Training wave receipt is not terminal')
    archive = root / (args.name + '.tar.gz')
    manifest_path = root / (args.name + '_manifest.json')
    result_path = root / (args.name + '_receipt.json')
    if any(p.exists() for p in (archive, manifest_path, result_path)):
        raise FileExistsError('Archive names cannot be reused')
    paths = []
    for name in ['runs/' + args.wave, args.source, *args.extra]:
        path = (root / name).resolve()
        path.relative_to(root)
        if not path.exists():
            raise FileNotFoundError(path)
        paths.extend(path.rglob('*') if path.is_dir() else [path])
    files = sorted(set(path for path in paths if path.is_file()
                       and '__pycache__' not in path.parts))
    rows = [dict(path=str(path.relative_to(root)), bytes=path.stat().st_size,
                 sha256=sha(path)) for path in files]
    manifest = dict(schema='doom-gpu-file-manifest/1', created_unix=time.time(),
                    wave=args.wave, files=rows,
                    dependencies='Common Cadence core and bootstrap dataset are in durable_01')
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(manifest_path, arcname=manifest_path.name)
        for row in rows:
            tar.add(root / row['path'], arcname=row['path'], recursive=False)
    for row in rows:
        path = root / row['path']
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('Source changed during archive: ' + row['path'])
    result = dict(schema='doom-gpu-wave-archive/1', created_unix=time.time(),
                  archive=str(archive), archive_bytes=archive.stat().st_size,
                  archive_sha256=sha(archive), files=len(rows),
                  file_bytes=sum(row['bytes'] for row in rows),
                  manifest_sha256=sha(manifest_path))
    result_path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
