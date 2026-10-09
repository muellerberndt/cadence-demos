"""Pack the Showcase League for the page: ../.venv/bin/python pack.py [--robots 6]

Writes ``public/pack/``: the released Cadence wheel (from PyPI, hashed), the arena's Python
sources and the browser host, the brains of the best robots of ``../league-evolved`` (their
trained checkpoints, the lives that continue in the page), and a manifest naming it all.
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
REPO = HERE.parent
PYODIDE = "314.0.7"
CADENCE = "0.79.0"
# the ring stage of a life in the page: calm unless surprised, no wider exploration, a sharp
# sampling temperature, and the memory of the nursery's income forgotten on entering the ring
STAGE = {"need": 0.0, "heat": 0.0, "temperature": 0.2, "reset": True}
SOURCES = ["__init__.py", "parts.py", "world.py", "senses.py", "brain.py", "controls.py", "pool.py", "royale.py", "nursery.py", "probe.py"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--league", default=str(REPO / "league-evolved"))
    p.add_argument("--robots", type=int, default=6)
    p.add_argument("--out", default=str(HERE / "public" / "pack"))
    a = p.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "py" / "arena").mkdir(parents=True)
    (out / "brains").mkdir()
    subprocess.run(
        [sys.executable, "-m", "pip", "download", f"cadence-net=={CADENCE}", "--no-deps", "--only-binary", ":all:", "-d", str(out), "-q"],
        check=True,
    )
    wheel = next(out.glob(f"cadence_net-{CADENCE}-py3-none-any.whl"))
    sources_sha = {}
    for name in SOURCES:
        src = REPO / "arena" / name
        shutil.copy(src, out / "py" / "arena" / name)
        sources_sha[name] = sha(src)
    shutil.copy(HERE / "py" / "host.py", out / "py" / "host.py")
    league = json.loads((Path(a.league) / "league.json").read_text())
    robots = sorted(league["robots"].items(), key=lambda kv: -kv[1]["elo"])[: a.robots]
    roster = []
    for name, e in robots:
        brain = Path(a.league) / "brains" / f"{name}.npz"
        shutil.copy(brain, out / "brains" / f"{name}.npz")
        h = e["history"]
        roster.append(
            {
                "name": name,
                "blueprint": e["blueprint"],
                "elo": e["elo"],
                "fights": e["fights"],
                "wins": e["wins"],
                "lineage": e.get("lineage"),
                "parent": e.get("parent"),
                "generation": e.get("generation"),
                "mutations": e.get("mutations", []),
                "moments": e["moments"],
                "owed": e.get("owed"),
                "brain_sha256": sha(brain),
                "history": [{k: r.get(k) for k in ("fight", "place", "dealt", "taken", "elo_after", "aroused_share", "learning_sweeps")} for r in h[-40:]],
            }
        )
    manifest = {
        "schema": "cadence-showcase-pack/1",
        "created": time.strftime("%Y-%m-%d"),
        "pyodide": PYODIDE,
        "cadence": CADENCE,
        "wheel": wheel.name,
        "wheel_sha256": sha(wheel),
        "sources": SOURCES,
        "sources_sha256": sources_sha,
        "host_sha256": sha(HERE / "py" / "host.py"),
        "roster": roster,
        "stage": STAGE,
        "league": {
            "fights": len(league["fights"]),
            "generations": len(league.get("evolution", [])),
            "retired": len(league.get("retired", {})),
            "evolution": [
                {"generation": g["generation"], "lineages": g["lineages"], "podium": [r["name"] for r in g["ranking"][:3]], "seconds": g["seconds"]}
                for g in league.get("evolution", [])
            ],
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"packed {len(roster)} robots: {', '.join(r['name'] for r in roster)}; {size / 1e6:.1f} MB in {out}")


if __name__ == "__main__":
    main()
