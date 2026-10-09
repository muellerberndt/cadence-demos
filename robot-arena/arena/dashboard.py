"""The Cadence Showcase League page: the ladder, Elo over fights, each robot's tactics over
its fights (damage, hits, time in the burn, distance, arousal, learning) and every fight's
replay, rendered from ``league.json`` into one HTML file with the data inlined."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .league import League

TEMPLATE = Path(__file__).resolve().parent.parent / "viewer" / "league.html"
MARK = "/*LEAGUE*/null"
KEEP = ("fight", "place", "score", "elo_after", "dealt", "taken", "burn", "hits", "moments",
        "moments_outside", "travelled_m", "aroused_share", "learning_sweeps", "sweeps_per_moment",
        "refused", "alive", "died_at")


def _nursery_reports(league: League, name: str) -> dict[str, Any]:
    """The nursery totals of the robot and of its controls, from the saved reports."""
    out: dict[str, Any] = {}
    folder = league.root / "reports"
    for policy in ("brain", "random", "frozen"):
        path = folder / f"nursery-{name}-{policy}.json"
        if path.exists():
            r = json.loads(path.read_text())
            out[policy] = {
                "progress_m": round(r["total"]["progress_m"], 1),
                "kills": r["total"]["kills"],
                "dealt": round(r["total"]["dealt"], 0),
                "second_half_progress_m": r["second_half"].get("progress_m"),
                "blocks": [b["progress_m"] for b in r["blocks"]],
                "moments": r["moments"],
                "moments_per_second": round(r["moments_per_second"], 0),
                "calm_share": round(1 - r["second_half"].get("aroused_share", 1.0), 2) if policy == "brain" else None,
            }
    return out


def dashboard_data(league: League) -> dict[str, Any]:
    data = league.data
    robots = {}
    for name, e in data["robots"].items():
        robots[name] = {
            "policy": e["policy"],
            "chassis": e["blueprint"]["chassis"],
            "parts": e["blueprint"]["parts"],
            "genes": e["blueprint"].get("genes", {}),
            "elo": e["elo"],
            "fights": e["fights"],
            "wins": e["wins"],
            "moments": e["moments"],
            "nursery": e.get("nursery"),
            "raised": _nursery_reports(league, name),
            "lineage": e.get("lineage"),
            "history": [{k: h.get(k) for k in KEEP} for h in e["history"]],
        }
    fights = [
        {
            "id": f["id"], "seed": f["seed"], "moments": f["moments"], "seconds": f.get("seconds"),
            "when": f.get("when"), "page": f.get("page"),
            "results": [{"name": r["name"], "place": r["place"], "hp": r["hp"], "dealt": r["dealt"]} for r in f["results"]],
        }
        for f in data["fights"]
    ]
    simulated = sum(f["moments"] for f in data["fights"]) * 0.05
    wall = sum(f.get("seconds") or 0.0 for f in data["fights"])
    return {
        "title": "Cadence Showcase League",
        "cadence": data.get("cadence"),
        "created": data.get("created"),
        "robots": robots,
        "fights": fights,
        "retired": {n: {"elo": e["elo"], "fights": e["fights"], "retired_in": e.get("retired_in")} for n, e in data.get("retired", {}).items()},
        "evolution": data.get("evolution", []),
        "simulated_seconds": round(simulated, 1),
        "wall_seconds": round(wall, 1),
    }


def render_dashboard(league: League, out: str | Path | None = None) -> Path:
    page = TEMPLATE.read_text()
    if MARK not in page:
        raise ValueError(f"the league template has no {MARK!r} placeholder")
    payload = json.dumps(dashboard_data(league), separators=(",", ":")).replace("</", "<\\/")
    out = Path(out) if out else league.root / "index.html"
    out.write_text(page.replace(MARK, payload, 1))
    return out
