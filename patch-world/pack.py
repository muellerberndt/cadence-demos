"""Pack the page's runtime: the released Cadence wheel, the Python sources and the founders.

    python pack.py --founders runs/founders/after [--wheel path/to/cadence_net-0.95.2-py3-none-any.whl]

Writes ``web/pack/``: the ``cadence-net`` wheel (downloaded from PyPI unless ``--wheel`` names a
local copy of the same release), the ``patchworld`` sources the page's workers run in Pyodide,
the founders' brains with ``founders.json`` (their names, genes and files), and
``manifest.json`` with the SHA-256 of every file, which the workers check before anything runs.
The manifest also carries the founders' sizes and one line per receipt in ``evidence/`` for
the page's card. Without ``--founders`` the founders already in ``web/pack/founders`` are
packed again.
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
OUT = HERE / "web" / "pack"
VERSION = "0.95.2"
PYODIDE = "314.0.7"
SOURCES = ["__init__.py", "world.py", "genes.py", "brain.py", "inspect.py", "ecosystem.py", "host.py"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def size_of(path: Path) -> dict:
    from cadence import Brain

    brain = Brain.load(path, backend="cpu")
    c = brain.connectome
    return {"neurons": int(c.n), "synapses": int(c.synapses)}


def readings() -> dict[str, str]:
    """One sentence per receipt, for the page's card."""
    ev = HERE / "evidence"
    out: dict[str, str] = {}
    f = ev / "controls.json"
    if f.exists():
        s = json.loads(f.read_text())["summary"]
        out["controls"] = (
            f"In a mortal world without births ({len(json.loads(f.read_text())['seeds'])} seeds), "
            f"learners lived {s['live']['mean_age']:.0f} moments on average, their frozen twins "
            f"{s['frozen']['mean_age']:.0f} and random walkers {s['random']['mean_age']:.0f}; "
            f"intake per moment {s['live']['income_per_moment']:.3f}, "
            f"{s['frozen']['income_per_moment']:.3f} and {s['random']['income_per_moment']:.3f}.")
    f = ev / "flip.json"
    if f.exists():
        s = json.loads(f.read_text())["summary"]
        lv, fz, k = s["live"]["acceptance_per_bin"], s["frozen"]["acceptance_per_bin"], s["flip_bin"]
        out["flip"] = (
            f"After the season turned to winter, learners ate {lv[k]:.0%} of the berries they stood on in "
            f"the first 100 moments and {lv[-1]:.0%} in the last 100 (after {lv[k - 1]:.0%} at the end "
            f"of summer); their frozen twins {fz[k]:.0%} and {fz[-1]:.0%}.")
    f = ev / "seasons.json"
    if f.exists():
        s = json.loads(f.read_text())["summary"]
        lw = [x for x, n in zip(s["live"], s["seasons"]) if n == "winter"]
        out["seasons"] = (
            f"A learner's second winter went better than its first: {lw[0]['first_300_per_100']:.2f} "
            f"then {lw[1]['first_300_per_100']:.2f} berries per 100 moments in the first 300 moments.")
    f = ev / "caches.json"
    if f.exists():
        s = json.loads(f.read_text())["summary"]
        out["caches"] = (
            f"A recall memory did not help find the hidden caches: {s['nuts_per_1000_recall_on']:.2f} "
            f"against {s['nuts_per_1000_recall_off']:.2f} nuts per 1,000 moments ({s['pairs']} pairs).")
    f = ev / "evolution.json"
    if f.exists():
        s = json.loads(f.read_text())["summary"]
        out["evolution"] = (
            f"Evolution raised intake from {s['before']['income_per_moment']:.3f} to "
            f"{s['after']['income_per_moment']:.3f} per moment, at brains costing "
            f"{s['after']['brain_cost_per_moment']:.4f} against {s['before']['brain_cost_per_moment']:.4f}.")
    f = ev / "competition.json"
    if f.exists():
        s = json.loads(f.read_text())["summary"]
        out["competition"] = (
            f"In one world with births, the evolved lineages held {s['evolved_share_of_learners_at_end']:.0%} "
            f"of the learners after 12,000 moments ({s['worlds_evolved_hold_all']} of {s['worlds']} worlds "
            f"all of them, {s['worlds_generation0_hold_all']} none).")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--founders", type=Path, default=OUT / "founders",
                   help="a folder with founders.json and the brains it names")
    p.add_argument("--wheel", type=Path, help=f"a local cadence-net {VERSION} wheel")
    p.add_argument("--out", type=Path, default=OUT)
    a = p.parse_args()
    import cadence

    if cadence.__version__ != VERSION:
        p.error(f"pack with cadence-net {VERSION} installed (found {cadence.__version__})")
    out = a.out
    (out / "py" / "patchworld").mkdir(parents=True, exist_ok=True)
    wheel = out / f"cadence_net-{VERSION}-py3-none-any.whl"
    if a.wheel:
        if a.wheel.name != wheel.name:
            p.error(f"--wheel must be {wheel.name}")
        if a.wheel.resolve() != wheel.resolve():
            shutil.copyfile(a.wheel, wheel)
        wheel_source = "local copy of the released wheel"
    elif wheel.exists():
        wheel_source = "the wheel already in the pack"
    else:
        subprocess.run([sys.executable, "-m", "pip", "download", f"cadence-net=={VERSION}",
                        "--no-deps", "--only-binary=:all:", "--dest", str(out), "--quiet"],
                       check=True)
        wheel_source = "PyPI"
    for name in SOURCES:
        shutil.copyfile(HERE / "patchworld" / name, out / "py" / "patchworld" / name)
    for stale in (out / "py" / "patchworld").glob("*.py"):
        if stale.name not in SOURCES:
            stale.unlink()

    target = out / "founders"
    roster = json.loads((a.founders / "founders.json").read_text())["founders"]
    if a.founders.resolve() != target.resolve():
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        for f in roster:
            shutil.copyfile(a.founders / f["file"], target / f["file"])
    keep = {"name", "file", "genes", "structure", "generation", "lineage", "origin"}
    roster = [{k: v for k, v in f.items() if k in keep} for f in roster]
    (target / "founders.json").write_text(json.dumps({"founders": roster}, indent=1) + "\n")
    founders = []
    for f in roster:
        path = target / f["file"]
        founders.append({"name": f["name"], "file": f["file"], "sha256": sha(path),
                         "bytes": path.stat().st_size, "structure": f.get("structure"),
                         "generation": f.get("generation"), **size_of(path)})
    manifest = {
        "schema": "cadence-patch-world-pack/1",
        "packed": time.strftime("%Y-%m-%d"),
        "pyodide": PYODIDE,
        "cadence": VERSION,
        "wheel": wheel.name,
        "wheel_sha256": sha(wheel),
        "wheel_source": wheel_source,
        "sources": SOURCES,
        "sources_sha256": {n: sha(out / "py" / "patchworld" / n) for n in SOURCES},
        "roster_sha256": sha(target / "founders.json"),
        "founders": founders,
        "readings": readings(),
        "source": "https://github.com/muellerberndt/cadence-demos",
        "license": "GPL-3.0-only",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(json.dumps({"founders": len(founders), "bytes": total, "wheel_source": wheel_source}, indent=1))


if __name__ == "__main__":
    main()
