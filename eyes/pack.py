"""Pack a raised eye for the page.

    .venv/bin/python pack.py --run runs/eye-s1

Writes ``web/pack/``: the brain, the released Cadence wheel it was raised on (from PyPI, checked
by SHA-256), the Python sources the page's workers run in Pyodide, the brain view's atlas and a
manifest naming all of them with their hashes. The page loads nothing else besides Pyodide.

The brain is saved with its answer tolerance set to ``--tolerance`` (the learner's residual
tolerance). At 0.03 a moving frame settles in one 32-sweep chunk instead of about two at the
raised 0.003, so the brain answers twice as often while you drag; the README gives the measured
trade-off.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYODIDE = "314.0.7"
SOURCES = ["__init__.py", "world.py", "shapes.py", "life.py", "eyes.py", "fovea.py", "eye_host.py"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--run", required=True, help="a raise_eye.py output folder")
    p.add_argument("--brain", default="brain.npz")
    p.add_argument("--out", default=str(HERE / "web" / "pack"))
    p.add_argument("--width", type=int, default=160)
    p.add_argument("--height", type=int, default=100)
    p.add_argument("--tolerance", type=float, default=0.03)
    a = p.parse_args()

    import cadence
    from cadence import Brain

    from tracker.view import atlas_for, layout

    run = Path(a.run)
    meta = json.loads((run / "run.json").read_text())
    fovea = meta["fovea"]
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "py" / "tracker").mkdir(parents=True)

    brain_path = out / "brain.npz"
    raised = Brain.load(run / a.brain)
    raised_tolerance = raised.learner.config.tolerance
    raised.learner.config = replace(raised.learner.config, tolerance=a.tolerance)
    raised.basal_ganglia.learner.config = raised.learner.config
    raised.save(brain_path)
    version = cadence.__version__
    subprocess.run([sys.executable, "-m", "pip", "download", f"cadence-net=={version}", "--no-deps",
                    "--only-binary", ":all:", "-d", str(out), "-q"], check=True)
    wheel = next(out.glob(f"cadence_net-{version}-py3-none-any.whl"))
    for name in SOURCES:
        shutil.copy(HERE / "tracker" / name, out / "py" / "tracker" / name)

    brain = Brain.load(brain_path)
    lay = layout(brain, fovea["bins"], meta["anatomy"])
    (out / "atlas.json").write_text(json.dumps({"atlas": atlas_for(brain, lay), "layout": lay}))
    manifest = {
        "schema": "cadence-eyes-pack/1",
        "created": time.strftime("%Y-%m-%d"),
        "pyodide": PYODIDE,
        "cadence": version,
        "wheel": wheel.name,
        "wheel_sha256": sha(wheel),
        "sources": SOURCES,
        "sources_sha256": {n: sha(out / "py" / "tracker" / n) for n in SOURCES},
        "brain": brain_path.name,
        "brain_sha256": sha(brain_path),
        "atlas": "atlas.json",
        "run": run.name,
        "phase": "bootstrap",
        "eye": "fovea",
        "window": 0,
        "bins": fovea["bins"],
        "fovea": {k: fovea[k] for k in ("receptors", "inner", "reach", "bins", "change_gain")},
        "width": a.width,
        "height": a.height,
        "tolerance": brain.learner.config.tolerance,
        "raised_tolerance": raised_tolerance,
        "neurons": int(brain.connectome.n),
        "synapses": int(brain.connectome.synapses),
        "trained_shapes": list(fovea["kinds"]),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps({k: manifest[k] for k in ("cadence", "wheel_sha256", "neurons", "synapses",
                                               "tolerance")}, indent=1))


if __name__ == "__main__":
    main()
