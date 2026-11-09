"""Pack the browser edition's runtime: the released cadence-net wheel and arcade_brain.py, with the
manifest whose SHA-256 the brain worker checks before anything runs.

    python pack.py            # writes web/pack/
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "web" / "pack"
VERSION = "0.95.2"
PYODIDE = "314.0.7"
SOURCES = ["arcade_brain.py"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    wheel = OUT / f"cadence_net-{VERSION}-py3-none-any.whl"
    keep = wheel.read_bytes() if wheel.exists() else None
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "py").mkdir(parents=True)
    if keep:
        wheel.write_bytes(keep)
    else:
        subprocess.run([sys.executable, "-m", "pip", "download", f"cadence-net=={VERSION}", "--no-deps",
                        "--only-binary", ":all:", "-d", str(OUT), "-q"], check=True)
    for name in SOURCES:
        shutil.copy(HERE / name, OUT / "py" / name)
    manifest = {
        "schema": "cadence-arcade-pack/1",
        "pyodide": PYODIDE,
        "cadence": VERSION,
        "wheel": wheel.name, "wheel_sha256": sha(wheel),
        "sources": SOURCES, "sources_sha256": {n: sha(OUT / "py" / n) for n in SOURCES},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
