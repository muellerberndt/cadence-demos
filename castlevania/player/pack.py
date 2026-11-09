"""Pack the player page (player/pack/): the trace of the recorded run, the released cadence-net
wheel and the demo's Python sources for live mode, and a manifest naming every file with its
SHA-256. The brain and the game video stay where they are (../brain/, ../docs/); the manifest
points at them.

    python player/pack.py --trace runs/trace42.json.gz
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
ROOT = HERE.parent
PYODIDE = "314.0.7"
SOURCES = ["__init__.py", "pad.py", "eye.py", "player.py"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--trace", type=Path, required=True, help="record.py --trace output")
    p.add_argument("--video", default="../../docs/castlevania-game.mp4", help="the game video, relative to pack/")
    p.add_argument("--cadence", default="0.95.2")
    a = p.parse_args()
    out = HERE / "pack"
    (out / "py" / "simon").mkdir(parents=True, exist_ok=True)
    wheel = out / f"cadence_net-{a.cadence}-py3-none-any.whl"
    if not wheel.exists():
        subprocess.run([sys.executable, "-m", "pip", "download", f"cadence-net=={a.cadence}", "--no-deps",
                        "--only-binary", ":all:", "-d", str(out), "-q"], check=True)
    for name in SOURCES:
        shutil.copy(ROOT / "simon" / name, out / "py" / "simon" / name)
    shutil.copy(a.trace, out / "trace.json.gz")
    brain = ROOT / "brain" / "brain.npz"
    manifest = {
        "schema": "cadence-castlevania-player/1", "created": time.strftime("%Y-%m-%d"),
        "pyodide": PYODIDE, "cadence": a.cadence, "wheel": wheel.name, "wheel_sha256": sha(wheel),
        "sources": SOURCES, "sources_sha256": {n: sha(out / "py" / "simon" / n) for n in SOURCES},
        "brain": {"file": "../../brain/brain.npz", "sha256": sha(brain)},
        "trace": {"file": "trace.json.gz", "sha256": sha(out / "trace.json.gz")},
        "video": {"file": a.video},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    sizes = {f.relative_to(out).as_posix(): f.stat().st_size for f in sorted(out.rglob("*")) if f.is_file()}
    print(json.dumps({"bytes": sum(sizes.values()), "files": sizes}, indent=1))


if __name__ == "__main__":
    main()
