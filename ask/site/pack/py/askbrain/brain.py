"""The parrot's brain: ``cadence.words.Words`` over a map of the room, and its file.

The brain is the library's: its senses (a map of things with each thing's colour on its own
sheet, ``cadence.space.map.Map(values={"colour": 6})``, and the body: where it perches and which
way it faces) and a lexicon learned from naming (``cadence.words.Lexicon``). Nothing here answers
a question; this file builds the brain, shows it the room through its eyes and keeps its lexicon
in a file.

The file (``cadence-ask-brain/1``, an ``.npz``) holds the lexicon's arrays as the library gives
them (``Lexicon.arrays``: its synapses, the motor's letters, the word forms), its settings, and
the lessons each word has had (``Lexicon.counts``), so a word named again on the page goes on
from its earlier lessons. The map is not kept: a room on the page is new to the brain, and it
learns it by looking.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from . import world

FORMAT = "cadence-ask-brain/1"


def make_map() -> Any:
    """A map of the room that holds nothing: one unit a kind, the colours on its sheet."""
    from cadence.space.map import Map  # opt-in, imported by name

    return Map(world.PLANE, world.CELLS, units=world.KINDS, values={"colour": world.COLOURS},
               seed=0)


def make_brain(**settings: Any) -> Any:
    """A hatchling: a map of the room, the parrot at the middle, and a lexicon that holds no
    word."""
    from cadence.words import Words  # opt-in, imported by name

    return Words(make_map(), **settings)


def moment(brain: Any, things: list[world.Thing], heading: float) -> None:
    """One moment: the parrot faces ``heading`` and its eyes report what they see."""
    brain.body.heading = float(heading)
    brain.look(seen=world.seen(things, heading), lit=world.camera(heading))


def look_around(brain: Any, things: list[world.Thing], heading: float) -> None:
    """A new room: the map is emptied, the parrot looks around in eight moments, an eighth of a
    turn apart, and turns back to ``heading``."""
    brain.map.reset()
    for i in range(8):
        moment(brain, things, heading + i * math.pi / 4)
    moment(brain, things, heading)


def save(brain: Any, path: str | Path, card: dict[str, Any] | None = None) -> Path:
    """The brain's lexicon in a file, with the lessons of each word and a card."""
    lexicon = brain.lexicon
    arrays = dict(lexicon.arrays())
    groups = {",".join(k): v for k, v in lexicon.counts.items()}
    for key, value in groups.items():
        arrays[f"counts:{key}"] = np.asarray(value, dtype=np.int64)
    record = {"format": FORMAT, "lexicon": lexicon.settings, "lessons": int(lexicon.lessons),
              "counts": sorted(groups), "words": {"shares": dict(brain.shares),
                                                  "floor": brain.floor},
              "card": card or {}}
    arrays["record"] = np.array(json.dumps(record))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        np.savez_compressed(f, **arrays)
    return path


def load(path: str | Path) -> tuple[Any, dict[str, Any]]:
    """A brain from its file: the lexicon as it was kept, a map that holds nothing, and the
    file's record."""
    from cadence.words import Lexicon, Words

    with np.load(path, allow_pickle=False) as held:
        record = json.loads(str(held["record"]))
        if record.get("format") != FORMAT:
            raise ValueError(f"a brain file states {FORMAT!r}")
        arrays = {k: held[k] for k in ("efficacy", "letters", "forms")}
        counts = {tuple(k.split(",")): np.asarray(held[f"counts:{k}"], dtype=np.int64)
                  for k in record["counts"]}
    lexicon = Lexicon.from_arrays(record["lexicon"], arrays)
    lexicon.counts = {k: v.copy() for k, v in counts.items()}
    lexicon.lessons = int(record.get("lessons", 0))
    told = record.get("words") or {}
    brain = Words(make_map(), lexicon=lexicon, shares=dict(told.get("shares") or {}) or None,
                  floor=float(told.get("floor", 0.05)))
    return brain, record
