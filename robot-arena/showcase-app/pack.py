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
sys.path.insert(0, str(REPO))
from arena.brain import PAGE_STAGE as STAGE  # noqa: E402  the ring stage of a life in the page
SOURCES = ["__init__.py", "parts.py", "world.py", "senses.py", "brain.py", "controls.py", "pool.py", "royale.py", "nursery.py", "probe.py"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--league", default=str(REPO / "league-live"))
    p.add_argument("--robots", type=int, default=6)
    p.add_argument("--out", default=str(HERE / "public" / "pack"))
    p.add_argument("--no-licence", action="store_true", help="skip the driving test of the roster (quick packs)")
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
    if not a.no_licence:
        # the driving test of every brain as it is packed: the page shows the state it arrived in
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor

        from arena.evolve import _licence_job

        jobs = [(r["blueprint"], str(Path(a.league) / "brains" / f"{r['name']}.npz")) for r in roster]
        with ProcessPoolExecutor(max_workers=min(6, len(jobs)), mp_context=multiprocessing.get_context("spawn")) as pool:
            tests = list(pool.map(_licence_job, jobs))
        for r, t in zip(roster, tests, strict=True):
            r["licence"] = {k: t[k] for k in ("licence", "passes", "approach", "escape", "closing_outside", "engage_dealt",
                                             "engage_taken", "chase", "facing", "spin", "stall", "kills")}
            r["licence"]["marks"] = "".join("+" if v else "-" for v in t["passed"].values())
            r["licence"]["tests"] = list(t["passed"].keys())
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
    plain = lambda o: o.item() if hasattr(o, "item") else str(o)  # numpy scalars from the driving test
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, default=plain))
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"packed {len(roster)} robots: {', '.join(r['name'] + (f" ({r['licence']['passes']}/{len(r['licence']['tests'])} passes, {r['licence']['licence']:+.2f})" if 'licence' in r else '') for r in roster)}; {size / 1e6:.1f} MB in {out}")


if __name__ == "__main__":
    main()
