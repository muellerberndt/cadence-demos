"""Preserve quiescent recovery artifacts on AWS with a checked file manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import time


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--include', action='append', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if Path(args.name).name != args.name or args.name in ('', '.', '..'):
        raise ValueError('Simple archive name required')
    archive = root / 'receipts' / (args.name + '.tar.gz')
    manifest = archive.with_name(args.name + '_manifest.json')
    receipt = archive.with_name(args.name + '_receipt.json')
    if any(p.exists() for p in (archive, manifest, receipt)):
        raise FileExistsError('Existing recovery evidence must not be overwritten')
    files = set()
    for name in args.include:
        path = (root / name).resolve()
        path.relative_to(root)
        if not path.exists():
            raise FileNotFoundError(path)
        for file in path.rglob('*') if path.is_dir() else [path]:
            if file.is_file() and '__pycache__' not in file.parts:
                file.resolve().relative_to(root)
                files.add(file)
    if not files:
        raise ValueError('Empty recovery set')
    rows = [dict(path=str(p.relative_to(root)), bytes=p.stat().st_size,
                 sha256=sha(p)) for p in sorted(files)]
    manifest.write_text(json.dumps(dict(schema='doom-recovery-file-manifest/1',
        created_unix=time.time(), files=rows), indent=2) + '\n')
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(manifest, arcname=manifest.name)
        for row in rows:
            tar.add(root / row['path'], arcname=row['path'], recursive=False)
    for row in rows:
        path = root / row['path']
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('Source changed during archive: ' + row['path'])
    result = dict(schema='doom-recovery-archive/1', created_unix=time.time(),
        archive=str(archive), archive_bytes=archive.stat().st_size,
        archive_sha256=sha(archive), files=len(rows),
        file_bytes=sum(r['bytes'] for r in rows), manifest_sha256=sha(manifest),
        included=args.include, training=False, deployment=False)
    receipt.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
