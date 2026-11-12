"""Build the page's pack: the Cadence wheel, the map file, the host and the manifest with SHA-256 sums.

    python tools/build.py --wheel cadence_net-0.99.0-py3-none-any.whl --map page-map.npz \\
        --label "The what-where map" --note "One or two sentences on what this file is." --wheel-source "PyPI"

``site/pack/`` then holds the wheel, the map file under ``map/`` (format ``cadence-space-map/1``:
the map's settings, its kinds' codes and an empty carried state), the host's sources under
``py/spacebrain/`` and ``manifest.json``, which the page's worker checks every file against
before it runs anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PACK = HERE / "site" / "pack"
PYODIDE = "314.0.7"
KINDS = {"hand": 0, "own": 1, "apple": 2, "bread": 3}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--wheel", required=True, help="the cadence-net wheel that holds cadence.space.map")
    p.add_argument("--map", required=True, help="the map file (cadence-space-map/1)")
    p.add_argument("--label", default="The what-where map", help="what the page calls the map")
    p.add_argument("--note", default="", help="one or two sentences on what this map file is")
    p.add_argument("--wheel-source", default="PyPI")
    p.add_argument("--map-source", default="", help="where the map file comes from")
    a = p.parse_args()
    wheel = Path(a.wheel)
    version = re.match(r"cadence_net-([^-]+)-", wheel.name).group(1)
    with zipfile.ZipFile(wheel) as archive:
        if "cadence/space/map.py" not in archive.namelist():
            raise SystemExit(f"{wheel.name} holds no cadence.space.map")
    for old in PACK.glob("cadence_net-*.whl"):
        if old.name != wheel.name:
            old.unlink()
    if wheel.resolve() != (PACK / wheel.name).resolve():
        shutil.copyfile(wheel, PACK / wheel.name)
    folder = PACK / "map"
    folder.mkdir(exist_ok=True)
    for old in folder.glob("*"):
        if old.name != Path(a.map).name:
            old.unlink()
    target = folder / Path(a.map).name
    if Path(a.map).resolve() != target.resolve():
        shutil.copyfile(a.map, target)
    sources = sorted(f.name for f in (PACK / "py" / "spacebrain").glob("*.py"))
    manifest = {
        "schema": "cadence-out-of-sight-pack/2",
        "packed": time.strftime("%Y-%m-%d"),
        "pyodide": PYODIDE,
        "cadence": version,
        "wheel": wheel.name,
        "wheel_sha256": sha(PACK / wheel.name),
        "wheel_source": a.wheel_source,
        "sources": sources,
        "sources_sha256": {name: sha(PACK / "py" / "spacebrain" / name) for name in sources},
        "map": {"file": target.name, "sha256": sha(target), "bytes": target.stat().st_size, "label": a.label,
                "note": a.note, "source": a.map_source, "kinds": KINDS},
    }
    (PACK / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
