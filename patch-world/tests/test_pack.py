import hashlib
import json
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parent.parent / "web" / "pack"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.skipif(not (PACK / "manifest.json").exists(), reason="no pack")
def test_manifest_matches_every_packed_file():
    m = json.loads((PACK / "manifest.json").read_text())
    assert m["schema"] == "cadence-patch-world-pack/1" and m["cadence"] == "0.95.2"
    assert sha(PACK / m["wheel"]) == m["wheel_sha256"]
    for name, digest in m["sources_sha256"].items():
        packed = PACK / "py" / "patchworld" / name
        assert sha(packed) == digest
        source = PACK.parent.parent / "patchworld" / name
        assert packed.read_bytes() == source.read_bytes(), f"{name}: run pack.py again"
    assert sha(PACK / "founders" / "founders.json") == m["roster_sha256"]
    for f in m["founders"]:
        assert sha(PACK / "founders" / f["file"]) == f["sha256"]
