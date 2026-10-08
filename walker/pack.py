"""Pack the walkers for the page.

    .venv/bin/python walker/pack.py

Writes ``walker/web/pack/``: the released Cadence wheel the walkers live on (the wheel of the
running version from PyPI, checked by SHA-256), the Python sources the page's worker runs in
Pyodide, and a manifest naming them with their hashes and the chamber's operating point. The
page loads nothing else besides Pyodide and numpy. No brain is packed: every walker is born in
the page.
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
    p.add_argument("--out", default=str(HERE / "web" / "pack"))
    p.add_argument("--wheel", default=None, help="a local wheel instead of the released one")
    a = p.parse_args()

    import cadence

    sys.path.insert(0, str(HERE))
    from walker.host import AROUSAL, POINT

    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "py" / "walker").mkdir(parents=True)
    version = cadence.__version__
    if a.wheel:
        wheel = out / Path(a.wheel).name
        shutil.copy(a.wheel, wheel)
        source = "local build"
    else:
        subprocess.run(
            [sys.executable, "-m", "pip", "download", f"cadence-net=={version}", "--no-deps",
             "--only-binary", ":all:", "-d", str(out), "-q"],
            check=True,
        )
        wheel = next(out.glob(f"cadence_net-{version}-py3-none-any.whl"))
        source = "PyPI"
    for name in SOURCES:
        shutil.copy(HERE / "walker" / name, out / "py" / "walker" / name)
    manifest = {
        "schema": "cadence-walker-pack/1",
        "created": time.strftime("%Y-%m-%d"),
        "pyodide": PYODIDE,
        "cadence": version,
        "wheel": wheel.name,
        "wheel_sha256": sha(wheel),
        "wheel_source": source,
        "sources": SOURCES,
        "sources_sha256": {name: sha(out / "py" / "walker" / name) for name in SOURCES},
        "point": POINT,
        "arousal": AROUSAL,
        "protocol": "cadence benchmarks/rhythm/protocol-reward-2.json, the live and nocopy arms",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps({k: manifest[k] for k in ("cadence", "wheel", "wheel_source", "point")}, indent=1))


if __name__ == "__main__":
    main()
