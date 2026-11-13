"""The page's host for the parrot's brain, run natively on the pack's own wheel and brain file:
the same files the worker runs in Pyodide.

    python -m pytest tests/test_host.py      # from ask/; node runs the page's rule for the eyes

The wheel named in ``site/pack/manifest.json`` is unpacked into a temporary folder and imported
from there, so the test reads the library the page runs.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
PACK = HERE / "site" / "pack"
MANIFEST = json.loads((PACK / "manifest.json").read_text())
_WHEEL = Path(tempfile.mkdtemp(prefix="ask-wheel-"))
with zipfile.ZipFile(PACK / MANIFEST["wheel"]) as archive:
    archive.extractall(_WHEEL)
sys.path.insert(0, str(_WHEEL))
sys.path.insert(0, str(PACK / "py"))
warnings.simplefilter("ignore")

from askbrain import world  # noqa: E402
from askbrain.host import Host  # noqa: E402

BRAIN = PACK / "brain" / MANIFEST["brain"]["file"]


def at(deg: float, r: float) -> list[float]:
    return [r * math.cos(math.radians(deg)), r * math.sin(math.radians(deg))]


# the page's first room (room.js firstRoom): kind, colour, place
FIRST = [[0, 0, *at(14, 1.25)], [3, 0, *at(178, 1.3)], [1, 1, *at(96, 1.15)],
         [6, 2, *at(-80, 1.2)], [8, 3, *at(128, 1.5)]]


@pytest.fixture()
def host() -> Host:
    h = Host({"brain": str(BRAIN)})
    h.handle({"command": "room", "things": FIRST, "heading": 0.0})
    return h


def test_the_pack_is_what_the_manifest_says() -> None:
    def sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    assert sha(PACK / MANIFEST["wheel"]) == MANIFEST["wheel_sha256"]
    assert sha(BRAIN) == MANIFEST["brain"]["sha256"]
    for name in MANIFEST["sources"]:
        assert sha(PACK / "py" / "askbrain" / name) == MANIFEST["sources_sha256"][name]
    import cadence

    assert cadence.__version__ == MANIFEST["cadence"]


def test_questions_both_ways_and_from_memory(host: Host) -> None:
    ask = lambda q: host.handle({"command": "ask", "question": q})["said"]  # noqa: E731
    assert ask("where is the ball?") == ["front"]
    assert ask("what colour is the cup?") == ["blue"]
    assert ask("what color is the cup?") == ["blue"]
    assert sorted(ask("what is red?")) == ["ball", "book"]
    # the book lies in the blind spot: the map holds it
    assert not world.in_view(0.0, FIRST[1][2:])[0]
    assert ask("what is behind you?") == ["book"]
    assert ask("where is the zebra?") == ["i do not know"]
    assert ask("where is the kettle?") == ["i do not know"]  # never named


def test_a_story_records_and_leaves_the_brain_as_it_was(host: Host) -> None:
    out = host.handle({"command": "ask", "question": "what is red?"})
    assert out["about"][0] == "colour" and out["about"][1] == 0
    assert [c["call"] for c in out["map_calls"]][0] == "where_is_value"
    assert len(out["hear"]["sweeps"]) == host.brain.lexicon.steps
    assert [s["word"] for s in out["spoken"]] == out["said"]
    for s in out["spoken"]:
        assert len(s["concept"]) == host.brain.lexicon.concepts
        assert s["letters"]
    # the wrappers are gone: the instance's methods are the class's again
    assert "say" not in host.brain.lexicon.__dict__
    for name in ("where_is", "where_is_value", "what_is_at", "values_at"):
        assert name not in host.brain.map.__dict__
    # recording changed nothing the brain computes: the same question gives the same words
    assert host.handle({"command": "ask", "question": "what is red?"})["said"] == out["said"]


def test_a_new_word_in_three_namings(host: Host) -> None:
    kettle = FIRST[4]
    heading = math.atan2(kettle[3], kettle[2])
    host.handle({"command": "moment", "things": FIRST, "heading": heading})
    for n in (1, 2, 3):
        out = host.handle({"command": "name", "word": "kettle", "at": kettle[2:]})
        assert out["lessons"] == n and out["changed"]
    host.handle({"command": "moment", "things": FIRST, "heading": 0.0})
    ask = lambda q: host.handle({"command": "ask", "question": q})["said"]  # noqa: E731
    assert ask("where is the kettle?") == ["left"]
    assert ask("what colour is the kettle?") == ["yellow"]
    assert ask("what is yellow?") == ["kettle"]
    # a known word named again goes on from its earlier lessons (the file keeps them)
    unit = host.brain.lexicon.unit("ball")
    assert host.brain.lexicon.counts[tuple(host.brain.shares)][unit] > 10


def test_a_pistachio_and_a_told_answer(host: Host) -> None:
    assert "refused" in host.handle({"command": "pistachio"})
    host.handle({"command": "ask", "question": "where is the ball?"})
    out = host.handle({"command": "pistachio"})
    assert out["how"] == "reward" and 0.0 < out["dopamine"] < 1.0 and out["changed"]
    # the same answer rewarded again surprises the parrot less
    host.handle({"command": "ask", "question": "where is the ball?"})
    assert host.handle({"command": "pistachio"})["dopamine"] < out["dopamine"]
    host.handle({"command": "ask", "question": "what colour is the ball?"})
    out = host.handle({"command": "tell", "answer": "red"})
    assert out["how"] == "practice" and out["changed"]


def test_reset_forgets_the_words_taught_on_the_page(host: Host) -> None:
    host.handle({"command": "name", "word": "zorp", "at": FIRST[0][2:]})
    assert "zorp" in host.brain.lexicon.forms
    out = host.handle({"command": "reset"})
    assert "zorp" not in out["words"]


def test_no_ears() -> None:
    assert "refused" in Host({"brain": str(BRAIN)}).handle({"command": "hear", "samples": []})


@pytest.mark.skipif(shutil.which("node") is None, reason="node runs the page's rule for the eyes")
def test_the_page_and_the_host_share_the_eyes() -> None:
    """``inView`` and ``placeOf`` of room.js against ``in_view`` and ``place_of`` of world.py."""
    rng = np.random.default_rng(0)
    points = rng.uniform(-2, 2, size=(300, 2)).tolist()
    headings = rng.uniform(-math.pi, math.pi, size=6).tolist()
    script = (f"import {{ inView, placeOf }} from '{(HERE / 'site' / 'room.js').as_uri()}';"
              f"const P = {json.dumps(points)}, H = {json.dumps(headings)};"
              "console.log(JSON.stringify(H.map((h) => P.map(([x, y]) => [inView(h, x, y), placeOf(h, x, y)]))));")
    out = json.loads(subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True,
                                    text=True, check=True).stdout)
    for h, row in zip(headings, out, strict=True):
        for p, (seen, place) in zip(points, row, strict=True):
            assert seen == bool(world.in_view(h, p)[0])
            assert place == world.place_of(h, p)
