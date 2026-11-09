"""Pack the page's runtime: the released Cadence wheel, the brain and the host sources.

    python pack.py --brain path/to/policy.npz --receipt path/to/receipt.json

Writes ``web/pack/``: the ``cadence-net`` wheel (downloaded from PyPI unless ``--wheel`` names
a local copy of the same release), the Python sources the page's worker runs in Pyodide, the
brain checkpoint, a copy of its training receipt keeping only the fields the model card reads,
and ``manifest.json`` with the SHA-256 of every file, which the worker checks before it runs
anything. The brain's size is read from the checkpoint itself, and the receipt must describe
a brain of that size. Without ``--brain`` and ``--receipt`` the brain and receipt already in
``web/pack/`` are packed again.
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
SOURCES = ["__init__.py", "game.py", "host.py", "search.py"]

ARGS = ("arm", "modules", "seed", "every_row", "batch", "lessons", "own_every", "own_games",
        "first_games", "first_weight", "eval_every", "games_every", "games", "first_eval", "apical",
        "relative", "nudged_steps", "nudged_fixed", "precision", "planes", "verdict", "target",
        "soft", "tactics_weight", "tactics_share", "terminal_share", "slip_weight", "eta_scale",
        "patience_on", "anneal", "anneal_factor")
CURVE = ("lesson", "pool", "taught_share", "seconds", "optimal", "blunder", "blunder_not_lost",
         "keep_not_lost", "illegal", "wins_now", "blocks", "verdict")
GAMES = ("lesson", "strength", "games", "win", "draw", "loss", "blunder_free_games",
         "blunder_rate")
FIRST = ("lesson", "chooser", "policy_first", "strength", "games", "win", "draw", "loss",
         "blunder_free_games")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt_summary(raw: dict) -> dict:
    """The receipt's numbers, without file paths or settings the model card does not use."""
    out: dict = {}
    args = raw.get("args", {})
    out["args"] = {k: args[k] for k in ARGS if k in args}
    for key in ("size", "pool_start", "refused", "seconds"):
        if key in raw:
            out[key] = raw[key]
    curve = []
    for row in raw.get("curve", []):
        kept = {k: row[k] for k in CURVE if k in row}
        # per game phase: top-level entries in a training receipt, "phases" in a packed one
        phases = row.get("phases") if isinstance(row.get("phases"), dict) else row
        kept["phases"] = {k: {m: v[m] for m in ("optimal", "blunder", "n")}
                          for k, v in phases.items()
                          if isinstance(v, dict) and {"optimal", "blunder", "n"} <= set(v)}
        curve.append(kept)
    out["curve"] = curve
    out["games"] = [{k: row[k] for k in GAMES if k in row} for row in raw.get("games", [])]
    out["first"] = [{k: row[k] for k in FIRST if k in row} for row in raw.get("first", [])]
    for key in ("best", "anneals", "lineage", "readings"):
        if key in raw:
            out[key] = raw[key]
    return out


def brain_size(path: Path) -> dict:
    from cadence import Brain

    brain = Brain.load(path, backend="cpu")
    c = brain.brain.connectome
    described = brain.describe().get("layout", {})
    return {"neurons": int(c.n), "synapses": int(c.synapses),
            "populations": {k: len(v) for k, v in c.populations.items()},
            "modules": described.get("modules"), "inputs": len(brain.sensory_index),
            "motor": len(brain.learner.output_index)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--brain", type=Path, default=OUT / "brain.npz", help="the brain checkpoint")
    p.add_argument("--receipt", type=Path, default=OUT / "receipt.json",
                   help="its training receipt")
    p.add_argument("--wheel", type=Path, help=f"a local cadence-net {VERSION} wheel")
    p.add_argument("--out", type=Path, default=OUT, help="where to write the pack (default web/pack)")
    a = p.parse_args()
    out = a.out
    for path in (a.brain, a.receipt):
        if not path.exists():
            p.error(f"{path} does not exist")
    import cadence

    if cadence.__version__ != VERSION:
        p.error(f"pack with cadence-net {VERSION} installed (found {cadence.__version__})")
    (out / "py" / "connect4").mkdir(parents=True, exist_ok=True)

    size = brain_size(a.brain)
    summary = receipt_summary(json.loads(a.receipt.read_text()))
    stated = summary.get("size", {})
    if stated and (stated.get("neurons"), stated.get("synapses")) != (size["neurons"], size["synapses"]):
        p.error(f"the receipt describes {stated}, the brain has {size['neurons']} neurons and "
                f"{size['synapses']} synapses")

    wheel = out / f"cadence_net-{VERSION}-py3-none-any.whl"
    if a.wheel:
        if a.wheel.name != wheel.name:
            p.error(f"--wheel must be {wheel.name}")
        if a.wheel.resolve() != wheel.resolve():
            shutil.copyfile(a.wheel, wheel)
        wheel_source = "local copy of the released wheel"
    else:
        subprocess.run([sys.executable, "-m", "pip", "download", f"cadence-net=={VERSION}",
                        "--no-deps", "--only-binary=:all:", "--dest", str(out), "--quiet"],
                       check=True)
        wheel_source = "PyPI"
    for stale in out.glob("cadence_net-*.whl"):
        if stale != wheel:
            stale.unlink()
    for name in SOURCES:
        shutil.copyfile(HERE / "connect4" / name, out / "py" / "connect4" / name)
    if a.brain.resolve() != (out / "brain.npz").resolve():
        shutil.copyfile(a.brain, out / "brain.npz")
    (out / "receipt.json").write_text(json.dumps(summary, indent=1) + "\n")

    manifest = {
        "schema": "cadence-connect-four-pack/1",
        "packed": time.strftime("%Y-%m-%d"),
        "pyodide": PYODIDE,
        "cadence": VERSION,
        "wheel": wheel.name,
        "wheel_sha256": sha(wheel),
        "wheel_source": wheel_source,
        "sources": SOURCES,
        "sources_sha256": {name: sha(out / "py" / "connect4" / name) for name in SOURCES},
        "brain": "brain.npz",
        "brain_sha256": sha(out / "brain.npz"),
        "brain_bytes": (out / "brain.npz").stat().st_size,
        "brain_size": size,
        "receipt": "receipt.json",
        "receipt_sha256": sha(out / "receipt.json"),
        "training": summary,
        "source": "https://github.com/muellerberndt/cadence",
        "license": "GPL-3.0-only",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    last = summary["curve"][-1] if summary["curve"] else {}
    where = out.resolve()
    print(json.dumps({"pack": str(where.relative_to(HERE)) if where.is_relative_to(HERE) else where.name,
                      "cadence": VERSION, "wheel_source": wheel_source, "brain": size,
                      "lessons": last.get("lesson"), "held_out_optimal": last.get("optimal"),
                      "bytes": sum(f.stat().st_size for f in out.rglob("*") if f.is_file())},
                     indent=1))


if __name__ == "__main__":
    main()
