"""Write the brain pack's manifest (site/pack/manifest.json): the host's sources, any brain files and
any wheel, each with its SHA-256, which the page's worker checks before it runs anything.

    python tools/build_pack.py [--package parrotbrain] [--wheel FILE] [--cadence VERSION] [--file NAME ...] [--brain TEXT]
                               [--trained DIR --trained-source TEXT ...]

The pack ships the placeholder host by default (pack/py/parrotbrain, NumPy only). The composed
brain's host replaces it: its package under pack/py/<package>/, its files (weights, settings) in
pack/, its wheel in pack/, then this tool again.

`--trained DIR` (a folder in pack/ holding `brain.npz`, `brain.records.npz`, `spec.json`, `version.json`
and, where the meaning lane exports it, `probes.json`) adds a brain trained tonight
(`parrotbrain.trained`) under the key DIR: its files are `host_files[DIR]`, which the worker loads
only when that brain is chosen. Repeat it for several; the first is the page's `trained` entry.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parents[1] / "pack"
PYODIDE = "314.0.7"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--package", default="parrotbrain")
    ap.add_argument("--wheel")
    ap.add_argument("--cadence")
    ap.add_argument("--file", action="append", default=[], help="a brain file in pack/ the host reads")
    ap.add_argument("--brain", default="composed: cadence.parrot (the parrot-brain lane), with the page's hearing layer; placeholder: a hand-written controller")
    ap.add_argument("--wheel-source", default="")
    ap.add_argument("--trained", action="append", default=[], help="a folder in pack/ with a trained brain's files (repeatable)")
    ap.add_argument("--trained-source", action="append", default=[], help="where each trained brain's files come from, in order")
    args = ap.parse_args()
    src = PACK / "py" / args.package
    sources = sorted(p.name for p in src.glob("*.py"))
    manifest = {
        "schema": "cadence-parrot-pack/1",
        "packed": datetime.date.today().isoformat(),
        "pyodide": PYODIDE,
        "packages": ["numpy"],
        "package": args.package,
        "brain": args.brain,
        "sources": sources,
        "sources_sha256": {n: sha(src / n) for n in sources},
        "files": {n: sha(PACK / n) for n in args.file},
        "config": {"eye": {"w": 64, "h": 32, "field": 87.5, "vfield": 60, "fovea": 0.4, "axis": 75},
                   "whole": "page", "genes": {"map_cells": 32}},  # the whole brain's page preset: 36 ms a moment in Pyodide (#332 E6)
        "hosts": {"composed": "parrotbrain.page", "placeholder": "parrotbrain.host"},
    }
    if args.trained:
        manifest["host_files"], manifest["trained_versions"], manifest["trained_sources"] = {}, {}, {}
        for k, folder in enumerate(args.trained):
            names = [f"{folder}/{n}" for n in ("brain.npz", "brain.records.npz", "spec.json", "version.json", "probes.json")
                     if n != "probes.json" or (PACK / folder / n).exists()]  # the probes where the lane exports them
            manifest["hosts"][folder] = f"{args.package}.trained"
            manifest["host_files"][folder] = {n: sha(PACK / n) for n in names}
            manifest["trained_versions"][folder] = json.loads((PACK / folder / "version.json").read_text())
            manifest["trained_sources"][folder] = args.trained_source[k] if k < len(args.trained_source) else ""
        manifest["trained_version"] = manifest["trained_versions"][args.trained[0]]
    if args.wheel:
        manifest.update({"wheel": args.wheel, "wheel_sha256": sha(PACK / args.wheel), "cadence": args.cadence, "wheel_source": args.wheel_source})
    (PACK / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"pack: {len(sources)} sources, {len(args.file)} files" + (f", wheel {args.wheel}" if args.wheel else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
