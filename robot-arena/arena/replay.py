"""Replay files and the isometric viewer page: one HTML file per fight, data inlined."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEMPLATE = Path(__file__).resolve().parent.parent / "viewer" / "arena.html"
MARK = "/*REPLAY*/null"


def save_replay(replay: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(replay, separators=(",", ":")))
    return path


def render_html(replay: dict[str, Any], template: Path = TEMPLATE) -> str:
    page = template.read_text()
    if MARK not in page:
        raise ValueError(f"the viewer template has no {MARK!r} placeholder")
    data = json.dumps(replay, separators=(",", ":")).replace("</", "<\\/")
    return page.replace(MARK, data, 1)


def render_file(replay_path: str | Path, out: str | Path | None = None) -> Path:
    replay_path = Path(replay_path)
    replay = json.loads(replay_path.read_text())
    out = Path(out) if out else replay_path.with_suffix(".html")
    out.write_text(render_html(replay))
    return out
