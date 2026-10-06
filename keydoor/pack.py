"""Pack a raised creature for the page.

    .venv/bin/python pack.py --run runs/d5-s5

Writes ``web/pack/``: the brain as saved mid-life, the Cadence wheel it lives on (the released
wheel of the running version from PyPI, checked by SHA-256, or ``--wheel`` for a local build
during development), the Python sources the page's worker runs in Pyodide, and a manifest
naming all of them with their hashes. The page loads nothing else besides Pyodide and numpy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYODIDE = "314.0.7"
SOURCES = ["__init__.py", "world.py", "host.py"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--run", required=True, help="a raise_creature.py output folder")
    p.add_argument("--out", default=str(HERE / "web" / "pack"))
    p.add_argument("--wheel", default=None, help="a local wheel instead of the released one")
    a = p.parse_args()

    import cadence

    run = Path(a.run)
    meta = json.loads((run / "run.json").read_text())
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "py" / "keydoor").mkdir(parents=True)
    shutil.copy(run / "brain.npz", out / "brain.npz")
    version = cadence.__version__
    if a.wheel:
        wheel = out / Path(a.wheel).name
        shutil.copy(a.wheel, wheel)
        source = "local build"
    else:
        subprocess.run([sys.executable, "-m", "pip", "download", f"cadence-net=={version}", "--no-deps",
                        "--only-binary", ":all:", "-d", str(out), "-q"], check=True)
        wheel = next(out.glob(f"cadence_net-{version}-py3-none-any.whl"))
        source = "PyPI"
    for name in SOURCES:
        shutil.copy(HERE / "keydoor" / name, out / "py" / "keydoor" / name)
    manifest = {
        "schema": "cadence-keydoor-pack/1",
        "created": time.strftime("%Y-%m-%d"),
        "pyodide": PYODIDE,
        "cadence": version,
        "wheel": wheel.name,
        "wheel_sha256": sha(wheel),
        "wheel_source": source,
        "sources": SOURCES,
        "sources_sha256": {name: sha(out / "py" / "keydoor" / name) for name in SOURCES},
        "brain": "brain.npz",
        "brain_sha256": sha(out / "brain.npz"),
        "delay": meta["delay"],
        "seed": meta["seed"],
        "raised_trips": meta["trips"],
        "raised": {k: meta[k] for k in ("fed_last_50", "wrong_last_50", "aroused_last_half", "lag", "cuts")},
        "run": run.name,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps({k: manifest[k] for k in ("cadence", "wheel", "wheel_source", "delay", "seed", "raised_trips", "raised")}, indent=1))


if __name__ == "__main__":
    main()
