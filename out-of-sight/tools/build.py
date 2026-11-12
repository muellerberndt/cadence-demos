"""Build the page's brain pack: the Cadence wheel, the host and the manifest with SHA-256 sums.

    python tools/build.py --wheel cadence_net-0.98.0-py3-none-any.whl [--module place.npz place.json]

``site/pack/`` then holds the wheel (as released on PyPI; its sum is printed for comparison), the
host's sources under ``py/spacebrain/`` and ``manifest.json``, which the page's worker checks
every file against before it runs anything. ``--module`` adds the trained place module's files
under ``module/``; without it the pack holds no module and the host composes the baseline brain
when the page loads. ``reaches.json`` is written by
``tools/record_scenes.py``; its sum is added here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PACK = HERE / "site" / "pack"
PYODIDE = "314.0.7"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--wheel", required=True, help="the released cadence-net wheel")
    p.add_argument("--module", nargs="*", default=None,
                   help="the trained place module's files (the arrays and the JSON record); none: the baseline is composed on the page")
    p.add_argument("--module-name", default="place")
    p.add_argument("--module-label", default=None, help="what the page calls this file (its badge)")
    p.add_argument("--module-note", default=None, help="one or two sentences on what this file is")
    p.add_argument("--space", default=None,
                   help='settings of cadence.space.Space this module is run with, as JSON, e.g. \'{"course": true}\' (none: the space\'s own)')
    p.add_argument("--wheel-source", default="PyPI")
    a = p.parse_args()
    wheel = Path(a.wheel)
    version = re.match(r"cadence_net-([^-]+)-", wheel.name).group(1)
    for old in PACK.glob("cadence_net-*.whl"):
        if old.name != wheel.name:
            old.unlink()
    if wheel.resolve() != (PACK / wheel.name).resolve():
        shutil.copyfile(wheel, PACK / wheel.name)
    sources = sorted(f.name for f in (PACK / "py" / "spacebrain").glob("*.py"))
    for old in (PACK / "module").glob("*") if (PACK / "module").is_dir() else ():
        old.unlink()
    manifest = {
        "schema": "cadence-out-of-sight-pack/1",
        "packed": time.strftime("%Y-%m-%d"),
        "pyodide": PYODIDE,
        "cadence": version,
        "wheel": wheel.name,
        "wheel_sha256": sha(PACK / wheel.name),
        "wheel_source": a.wheel_source,
        "sources": sources,
        "sources_sha256": {name: sha(PACK / "py" / "spacebrain" / name) for name in sources},
        "config": {},
    }
    if a.module:
        folder = PACK / "module"
        folder.mkdir(exist_ok=True)
        files = []
        for source in a.module:
            shutil.copyfile(source, folder / Path(source).name)
            files.append({"name": Path(source).name, "sha256": sha(folder / Path(source).name),
                          "bytes": (folder / Path(source).name).stat().st_size})
        manifest["module"] = {"name": a.module_name, "label": a.module_label, "note": a.module_note, "files": files}
        if a.space:
            manifest["module"]["space"] = json.loads(a.space)
    else:
        manifest["module"] = None
        manifest["brain_kind"] = "baseline, composed on the page"
    reaches = PACK / "reaches.json"
    if reaches.exists():
        held = json.loads(reaches.read_text())
        manifest["reaches"] = {"file": "reaches.json", "sha256": sha(reaches), "scenes": len(held["reaches"]),
                               "world_sha256": held.get("world_sha256"), "source": held.get("source")}
    (PACK / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
