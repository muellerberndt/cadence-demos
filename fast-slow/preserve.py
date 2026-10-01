"""Archive and hash-check a completed isolated experiment workspace on AWS."""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def sha(value):
    return hashlib.sha256(value).hexdigest()


def preserve(root, output):
    if output.exists() or root in output.parents:
        raise ValueError("new archive must be outside the experiment directory")
    rows = []
    for path in sorted(root.rglob("*")):
        if any(
            part in {"__pycache__", ".pytest_cache", ".ruff_cache"}
            for part in path.parts
        ):
            continue
        if path.is_symlink():
            raise ValueError(f"unexpected symbolic link: {path}")
        if path.is_file():
            data = path.read_bytes()
            rows.append(
                {
                    "path": str(path.relative_to(root)),
                    "bytes": len(data),
                    "sha256": sha(data),
                }
            )
    manifest = root / "preservation-manifest.json"
    with manifest.open("x") as handle:
        json.dump(rows, handle, indent=2)
        handle.write("\n")
    with tarfile.open(output, "x:gz") as archive:
        for row in rows:
            archive.add(root / row["path"], arcname=row["path"], recursive=False)
        archive.add(manifest, arcname=manifest.name, recursive=False)
    wanted = {row["path"]: row for row in rows}
    seen = set()
    with tarfile.open(output, "r:gz") as archive:
        for member in archive:
            assert member.isfile()
            data = archive.extractfile(member).read()
            if member.name == manifest.name:
                assert data == manifest.read_bytes()
            else:
                assert len(data) == wanted[member.name]["bytes"]
                assert sha(data) == wanted[member.name]["sha256"]
                seen.add(member.name)
    assert seen == wanted.keys()
    return {
        "archive": str(output),
        "bytes": output.stat().st_size,
        "sha256": sha(output.read_bytes()),
        "source_files": len(rows),
        "source_bytes": sum(r["bytes"] for r in rows),
        "manifest_sha256": sha(manifest.read_bytes()),
        "every_member_verified": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = preserve(args.root.resolve(), args.out.resolve())
    with args.receipt.open("x") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps(result, indent=2))
