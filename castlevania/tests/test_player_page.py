"""The player page (player/) is a folder a static host serves by itself: every file it loads lies
inside it, its copies of the web page's renderer and style match the originals, and every file the
pack's manifest names matches its SHA-256. No ROM and no browser needed."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "player"
PACK = PLAYER / "pack"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_copies_match_the_web_page():
    for name in ("brain.js", "style.css"):
        assert (PLAYER / name).read_bytes() == (ROOT / "web" / name).read_bytes(), name


def test_every_file_the_page_loads_is_inside_the_folder():
    for page in ("index.html", "help.html"):
        html = (PLAYER / page).read_text()
        for ref in re.findall(r'(?:src|href)="([^"#?]+)"', html):
            if ref.startswith(("http://", "https://", "mailto:")) or ref in ("./",):
                continue
            target = (PLAYER / ref).resolve()
            assert PLAYER.resolve() in target.parents, (page, ref)
            assert target.exists(), (page, ref)


def test_the_manifest_names_files_inside_the_pack_with_their_hashes():
    m = json.loads((PACK / "manifest.json").read_text())
    assert sha(PACK / m["wheel"]) == m["wheel_sha256"]
    for name in m["sources"]:
        assert sha(PACK / "py" / "simon" / name) == m["sources_sha256"][name]
    for key in ("brain", "trace", "video", "highlights"):
        path = (PACK / m[key]["file"]).resolve()
        assert PACK.resolve() in path.parents, key
        assert sha(path) == m[key]["sha256"], key
    assert (PACK / m["highlights"]["poster"]).exists()


def test_the_pack_holds_the_shipped_brain_and_the_recorded_videos():
    m = json.loads((PACK / "manifest.json").read_text())
    assert sha(PACK / m["brain"]["file"]) == sha(ROOT / "brain" / "brain.npz")
    assert sha(PACK / m["video"]["file"]) == sha(ROOT / "docs" / "castlevania-game.mp4")
    assert sha(PACK / m["highlights"]["file"]) == sha(ROOT / "docs" / "castlevania-highlights.mp4")
