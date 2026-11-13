"""The room of the page and the teacher's words: the world the parrot lives in, and nothing of its
brain.

A room is a plane of 4 m by 4 m with the parrot on its perch at the middle. A thing is a kind, a
colour and a place, at least 0.6 m from the perch and 0.45 m from any other thing. The parrot's
eyes sit on the sides of its head: each sees a wide fan to its side (from 10 degrees across the
line of its beak to 150 degrees back), and the two fans overlap in front, so it sees everything
but a blind spot of 60 degrees behind it. Its eyes report each thing they see: its kind, its
colour and its place (the eyes' report, the program's step; the retina that finds things in an
image is a later step). The same rule is ``inView`` in the page's ``room.js``.

The words are the teacher's: English words a teacher says while it shows things and answers
questions. The brain gets them as letters; no word is wired to a concept anywhere in the brain's
path. Kinds 8 to 11 are never named: the page's visitor names them. This follows the words chamber
of the library (``benchmarks/words``), whose words are nonce words drawn for each founder.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

PLANE = (-2.0, 2.0, -2.0, 2.0)
CELLS = (32, 32)
EYE = math.radians(70.0)  # each eye looks out this far to its side of the beak's line
FIELD = math.radians(80.0)  # each eye sees this far either side of where it looks
VIEW = EYE + FIELD  # together the eyes see this far either side of the beak: 150 degrees
TRAINED, NEW, COLOURS = 8, 4, 6
KINDS = TRAINED + NEW
KIND_WORDS = ("ball", "cup", "box", "book", "shoe", "key", "apple", "lamp",
              "kettle", "drum", "vase", "clock")  # 8 to 11: never named by the teacher
COLOUR_WORDS = ("red", "blue", "green", "yellow", "white", "black")
PLACE_WORDS = ("front", "right", "behind", "left")
NONE_WORD = "i do not know"
# words never taught, heard in practice ("where is the zebra?" "i do not know") and in the test
FOILS = ("zebra", "piano", "rocket", "tiger", "spoon", "chair",
         "violin", "lizard", "bucket", "candle", "pillow", "wagon")
NAMING = (0.5, 0.25, 0.25)  # the teacher names a thing's kind, colour or place at these rates


@dataclass
class Thing:
    kind: int
    colour: int
    place: np.ndarray


@dataclass
class Room:
    things: list[Thing]
    heading: float = 0.0  # where the parrot faces, radians from the x axis
    extra: dict[str, Any] = field(default_factory=dict)

    def kinds(self) -> list[int]:
        return [t.kind for t in self.things]


def free_place(rng: np.random.Generator, things: list[Thing]) -> np.ndarray:
    for _ in range(1000):
        r, a = rng.uniform(0.6, 1.8), rng.uniform(-math.pi, math.pi)
        p = np.array([r * math.cos(a), r * math.sin(a)])
        if all(np.linalg.norm(p - t.place) >= 0.45 for t in things):
            return p
    raise RuntimeError("no free place in the room")


def room(rng: np.random.Generator, kinds: list[int], count: int, *,
         avoid: dict[int, int] | None = None) -> Room:
    """A room of ``count`` things of distinct kinds drawn from ``kinds``, each in a drawn colour,
    never a kind's colour in ``avoid``."""
    chosen = [int(k) for k in rng.choice(kinds, size=count, replace=False)]
    things: list[Thing] = []
    for kind in chosen:
        options = [c for c in range(COLOURS) if not (avoid and avoid.get(kind) == c)]
        things.append(Thing(kind, int(rng.choice(options)), free_place(rng, things)))
    return Room(things, heading=float(rng.uniform(-math.pi, math.pi)))


def in_view(heading: float, points: Any) -> np.ndarray:
    """Which places the parrot's eyes see from the room's middle, facing ``heading``: a place in
    either eye's fan (the fans meet in front; behind them is the blind spot)."""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    a = np.angle(np.exp(1j * (np.arctan2(p[:, 1], p[:, 0]) - heading)))
    return np.asarray(np.abs(a) <= VIEW)


def camera(heading: float) -> Any:
    """The eyes' sight as the map takes it: a function of places."""
    return lambda points: in_view(heading, points)


def seen(things: list[Thing], heading: float) -> list[tuple[int, np.ndarray, dict[str, int]]]:
    """What the eyes report facing ``heading``: each thing in view, its kind, place, colour."""
    return [(t.kind, np.asarray(t.place, dtype=np.float64).copy(), {"colour": t.colour})
            for t in things if in_view(heading, t.place)[0]]


def place_of(heading: float, point: Any) -> int:
    """The place around the parrot of a point: 0 in front, 1 to the right, 2 behind, 3 left."""
    point = np.asarray(point, dtype=np.float64).reshape(2)
    a = float(np.angle(np.exp(1j * (math.atan2(point[1], point[0]) - heading))))
    return int(((-a + math.pi / 4) % (2 * math.pi)) // (math.pi / 2))


# -- the teacher's questions, with the right answer as the teacher knows it


@dataclass
class Question:
    text: str
    form: str  # where, colour, by_colour, by_place
    answer: list[str]  # one word a thing, or the word for nothing found
    about: str  # in_view, out_of_view, absent, foil, several
    kind: int | None = None


def colour_word(rng: np.random.Generator | None) -> str:
    """The teacher says "colour" or "color", both spellings, drawn."""
    return "color" if rng is not None and rng.random() < 0.5 else "colour"


def ask_where(r: Room, kind: int, word: str | None = None) -> Question:
    word = word or (KIND_WORDS[kind] if kind >= 0 else FOILS[-kind - 1])
    text = f"where is the {word}"
    things = [t for t in r.things if t.kind == kind]
    if not things:
        return Question(text, "where", [NONE_WORD], "absent" if kind >= 0 else "foil", kind)
    t = things[0]
    return Question(text, "where", [PLACE_WORDS[place_of(r.heading, t.place)]],
                    "in_view" if in_view(r.heading, t.place)[0] else "out_of_view", kind)


def ask_colour(r: Room, kind: int, rng: np.random.Generator | None = None,
               word: str | None = None) -> Question:
    word = word or (KIND_WORDS[kind] if kind >= 0 else FOILS[-kind - 1])
    text = f"what {colour_word(rng)} is the {word}"
    things = [t for t in r.things if t.kind == kind]
    if not things:
        return Question(text, "colour", [NONE_WORD], "absent" if kind >= 0 else "foil", kind)
    t = things[0]
    return Question(text, "colour", [COLOUR_WORDS[t.colour]],
                    "in_view" if in_view(r.heading, t.place)[0] else "out_of_view", kind)


def ask_by_colour(r: Room, colour: int) -> Question:
    things = [t for t in r.things if t.colour == colour]
    answer = sorted(KIND_WORDS[t.kind] for t in things) or [NONE_WORD]
    return Question(f"what is {COLOUR_WORDS[colour]}", "by_colour", answer,
                    "several" if things else "absent")


BY_PLACE = ("what is in front of you", "what is right of you", "what is behind you",
            "what is left of you")


def ask_by_place(r: Room, place: int) -> Question:
    things = [t for t in r.things if place_of(r.heading, t.place) == place]
    answer = sorted(KIND_WORDS[t.kind] for t in things) or [NONE_WORD]
    return Question(BY_PLACE[place], "by_place", answer, "several" if things else "absent")


def right(question: Question, said: list[str]) -> bool:
    """An answer is right where the words said are the answer's words, as a set, one a thing."""
    return sorted(set(said)) == sorted(set(question.answer)) and len(said) == len(
        question.answer)
