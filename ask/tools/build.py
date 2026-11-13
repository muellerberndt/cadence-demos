"""Write the page's pack manifest: the wheel, the host's sources and the brain file, with SHA-256.

    python tools/build.py --commit f8c23b21

``site/pack/`` holds the wheel of one commit of the library in a folder named by the commit
(``tools/build_wheel.py``), the host's sources under ``py/askbrain/``, the brain under ``brain/``
(``tools/raise_brain.py``) and ``manifest.json``, which the page's worker checks every file
against before it runs anything. Wheel folders of other commits are left as they are; the
manifest names one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PACK = HERE / "site" / "pack"
PYODIDE = "314.0.7"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--commit", required=True, help="the wheel's folder: the commit, 8 characters")
    p.add_argument("--brain", default="parrot.npz")
    p.add_argument("--release", action="store_true", help="the wheel is a released one")
    a = p.parse_args()
    folder = PACK / a.commit
    wheels = sorted(folder.glob("cadence_net-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"{folder} holds {len(wheels)} wheels: build one (tools/build_wheel.py)")
    wheel = wheels[0]
    version = re.match(r"cadence_net-([^-]+)-", wheel.name).group(1)
    commit = (folder / "COMMIT").read_text().split() if (folder / "COMMIT").exists() else [a.commit]
    sources = sorted(f.name for f in (PACK / "py" / "askbrain").glob("*.py"))
    brain = PACK / "brain" / a.brain
    raised = sorted((HERE / "evidence").glob("raised-*.json"))
    readings = None
    for path in reversed(raised):
        record = json.loads(path.read_text())
        if record.get("brain_sha256") == sha(brain):
            readings = path.name
            break
    manifest = {
        "schema": "cadence-ask-pack/1",
        "packed": time.strftime("%Y-%m-%d"),
        "pyodide": PYODIDE,
        "cadence": version,
        "build": "release" if a.release else "development",
        "commit": commit[0],
        "branch": commit[1] if len(commit) > 1 else None,
        "wheel": f"{a.commit}/{wheel.name}",
        "wheel_sha256": sha(wheel),
        "sources": sources,
        "sources_sha256": {name: sha(PACK / "py" / "askbrain" / name) for name in sources},
        "brain": {"file": brain.name, "sha256": sha(brain), "bytes": brain.stat().st_size,
                  "readings": readings},
    }
    (PACK / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
