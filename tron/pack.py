"""Pack one brain for the play page: web/pack/<slot>/ holds the cadence-net wheel, the full-field
host sources, the brain, its meta and (optionally) the deep-layer introspection.

    python pack.py --slot deep --brain brains/deep.npz --meta brains/deep.json
    python pack.py --slot flat --brain brains/flat.npz --meta brains/flat.json

The page loads web/pack/<slot>/manifest.json for the brain the visitor picks (`?brain=flat` or
`?brain=deep`, the switch in the header). The manifest names every file with its SHA-256; the
worker checks each file before it runs anything.

The meta is a small JSON: `name`, `title`, `tagline`, `sense: "field"`, `cadence`, `layout`,
`settle_from_rest`, `reading` (the strength the README quotes). `--introspect auto` (the
default) runs scripts/introspect.py on the brain with this interpreter (a few minutes): what each
layer computes and what some neurons are for, which the brain view draws; `--introspect PATH`
takes an existing file; `--introspect none` leaves it out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYODIDE = "314.0.7"
VERSION = "0.95.2"
SOURCES = ["__init__.py", "world.py", "field.py", "fieldhost.py", "bots.py", "mcts.py"]
KEEP = ("name", "title", "tagline", "sense", "size", "cadence", "play", "reading", "layout", "settle_from_rest")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wheel_for(out: Path, wheel: str | None) -> Path:
    target = out / f"cadence_net-{VERSION}-py3-none-any.whl"
    if wheel:
        shutil.copy(wheel, target)
        return target
    for other in (ROOT / "web" / "pack").glob(f"*/{target.name}"):
        if other.parent != out:
            shutil.copy(other, target)
            return target
    subprocess.run([sys.executable, "-m", "pip", "download", f"cadence-net=={VERSION}", "--no-deps",
                    "--only-binary", ":all:", "-d", str(out), "-q"], check=True)
    return target


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True, choices=["flat", "deep"])
    ap.add_argument("--brain", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--wheel", help="a local cadence-net wheel of the pinned version")
    ap.add_argument("--introspect", default="auto", help="auto | none | path to an introspect.json")
    ap.add_argument("--positions", type=int, default=5000, help="for --introspect auto")
    ap.add_argument("--workers", type=int, default=4, help="for --introspect auto")
    a = ap.parse_args()
    meta = json.loads(Path(a.meta).read_text())
    if meta.get("sense") != "field":
        raise SystemExit("the play page hosts full-field brains (meta sense 'field')")
    if meta.get("cadence") != VERSION:
        raise SystemExit(f"the meta names cadence {meta.get('cadence')}, the page runs {VERSION}")
    out = ROOT / "web" / "pack" / a.slot
    staging = out.with_name(out.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    (staging / "py" / "tron").mkdir(parents=True)
    (staging / "brain").mkdir()
    wheel = wheel_for(staging, a.wheel)
    for name in SOURCES:
        shutil.copy(ROOT / "tron" / name, staging / "py" / "tron" / name)
    shutil.copy(a.brain, staging / "brain" / "brain.npz")
    intro = None
    if a.introspect != "none":
        target = staging / "brain" / "introspect.json"
        if a.introspect == "auto":
            env = {**os.environ, "PYTHONPATH": str(ROOT),
                   "TRON_SETTLE_FROM_REST": "1" if meta.get("settle_from_rest") else "0"}
            subprocess.run([sys.executable, str(ROOT / "scripts" / "introspect.py"),
                            "--brain", str(staging / "brain" / "brain.npz"), "--meta", a.meta,
                            "--out", str(target), "--positions", str(a.positions),
                            "--workers", str(a.workers)], check=True, env=env, stdout=subprocess.DEVNULL)
        else:
            src = Path(a.introspect)
            shutil.copy(src, target)
            if (src.parent / "ROLES.md").exists():
                shutil.copy(src.parent / "ROLES.md", staging / "brain" / "ROLES.md")
        intro = "brain/introspect.json"
    slim = {k: meta[k] for k in KEEP if k in meta}
    slim["games"] = 0
    (staging / "brain" / "meta.json").write_text(json.dumps(slim, indent=1, ensure_ascii=False))
    manifest = {
        "schema": "cadence-tron-play/1",
        "created": time.strftime("%Y-%m-%d"),
        "pyodide": PYODIDE,
        "cadence": VERSION,
        "slot": a.slot,
        "wheel": wheel.name, "wheel_sha256": sha(wheel),
        "host": "tron.fieldhost:FieldHost",
        "sources": SOURCES, "sources_sha256": {n: sha(staging / "py" / "tron" / n) for n in SOURCES},
        "brain": {"id": meta["name"], "title": meta.get("title", meta["name"]), "file": "brain/brain.npz",
                  "sha256": sha(staging / "brain" / "brain.npz"), "meta": "brain/meta.json",
                  "meta_sha256": sha(staging / "brain" / "meta.json"),
                  **({"introspect": intro, "introspect_sha256": sha(staging / intro)} if intro else {})},
    }
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=1))
    shutil.rmtree(out, ignore_errors=True)
    staging.rename(out)
    sizes = {p.relative_to(out).as_posix(): p.stat().st_size for p in sorted(out.rglob("*")) if p.is_file()}
    print(json.dumps({"slot": a.slot, "brain": meta["name"], "bytes": sum(sizes.values()), "files": sizes}, indent=1))


if __name__ == "__main__":
    main()
