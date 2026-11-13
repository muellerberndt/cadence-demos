"""Raise the page's brain with a scripted teacher, read it on rooms it never saw, keep it in the pack.

    PYTHONPATH=<the wheel, unpacked> python tools/raise_brain.py [--seed 1] [--out site/pack/brain/parrot.npz]

The teacher follows the words chamber of the library (``benchmarks/words``, cadence#326), with the
English words of ``askbrain/world.py`` in place of nonce words:

1. **Naming.** In each of 40 rooms of the eight named kinds (no kind in its unseen colour), the parrot
   looks around, and the teacher names 15 things: each time the parrot turns to a drawn heading,
   attends to a thing (in view or held out of it) and hears one word: its kind's, its colour's or
   its place's around the parrot (at rates .5, .25, .25).
2. **Practice.** In each of 24 rooms of three things of kinds 0 to 3 (ball, cup, box, book), the
   teacher asks 10 questions and says the answer: where a thing is, its colour, what has a colour,
   what is at a place around the parrot, a kind not in the room, a word never taught. Kinds 4 to 7
   (shoe, key, apple, lamp) are named and never asked about.

The brain is then kept (``--out``): the page's brain. Its readings, which teach it nothing, are read
after it is kept, on a copy's lexicon where they teach (new words):

3. **The test.** 30 fresh rooms of the named kinds, every question form; 16 rooms with a thing in its
   kind's unseen colour.
4. **New words.** Each kind never named (kettle, drum, vase, clock) is shown and named three times;
   then 16 fresh rooms ask where it is and its colour.
5. **The lexicon at zero.** The same questions of step 3 by kind, to the same map and body with the
   lexicon's synapses at zero.

Writes ``evidence/raised-<date>-<time>-<commit>.json``: every reading with its count, the brain's
learned parameters and multiply-accumulates, the seconds, and the brain file's SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "site" / "pack" / "py"))

from askbrain import brain as parrot  # noqa: E402
from askbrain import world  # noqa: E402

SETTINGS = {"naming_rooms": 40, "namings": 15, "practice_rooms": 24, "asked": 10,
            "test_rooms": 30, "unseen_rooms": 16, "new_rooms": 16}


def unseen_colours(rng: np.random.Generator) -> dict[int, int]:
    """Each named kind's colour that no room of naming or practice holds."""
    return {k: int(rng.integers(world.COLOURS)) for k in range(world.TRAINED)}


def naming_word(r: world.Room, t: world.Thing, rng: np.random.Generator) -> str:
    u = rng.random()
    if u < world.NAMING[0]:
        return world.KIND_WORDS[t.kind]
    if u < world.NAMING[0] + world.NAMING[1]:
        return world.COLOUR_WORDS[t.colour]
    return world.PLACE_WORDS[world.place_of(r.heading, t.place)]


def room_questions(r: world.Room, rng: np.random.Generator, *, absent: list[int],
                   foils: list[int]) -> list[world.Question]:
    out: list[world.Question] = []
    for t in r.things:
        out += [world.ask_where(r, t.kind), world.ask_colour(r, t.kind, rng)]
    colours = sorted({t.colour for t in r.things})
    out.append(world.ask_by_colour(r, int(rng.choice(colours))))
    out += [world.ask_by_place(r, p) for p in range(len(world.PLACE_WORDS))]
    gone = [k for k in absent if k not in r.kinds()]
    if gone:
        k = int(rng.choice(gone))
        out += [world.ask_where(r, k), world.ask_colour(r, k, rng)]
    if foils:
        f = int(rng.choice(foils))
        out += [world.ask_where(r, -(f + 1)), world.ask_colour(r, -(f + 1), rng)]
    return out


def gate_of(q: world.Question) -> str:
    if q.form in ("where", "colour") and q.about in ("in_view", "out_of_view"):
        return "W1_named_only" if q.kind is not None and q.kind >= 4 else "W1_practised"
    if q.about == "foil":
        return "W4_never_taught"
    if q.about == "absent" and q.form in ("where", "colour"):
        return "W4_never_seen"
    return "W5_by_colour" if q.form == "by_colour" else "W5_by_place"


def ablate(brain: Any) -> Any:
    """The same map and body, with the lexicon's synapses at zero."""
    from cadence.words import Lexicon, Words

    arrays = brain.lexicon.arrays()
    arrays["efficacy"] = np.zeros_like(arrays["efficacy"])
    return Words(brain.map, lexicon=Lexicon.from_arrays(brain.lexicon.settings, arrays),
                 body=brain.body)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=HERE / "site" / "pack" / "brain" / "parrot.npz")
    ap.add_argument("--evidence", type=Path, default=HERE / "evidence")
    a = ap.parse_args()
    import cadence

    began = time.time()
    seconds: dict[str, float] = {}
    rng = np.random.default_rng(np.random.SeedSequence([a.seed, 326, 7]))
    unseen = unseen_colours(rng)
    named = list(range(world.TRAINED))
    brain = parrot.make_brain()

    # 1. naming
    for _ in range(SETTINGS["naming_rooms"]):
        r = world.room(rng, named, int(rng.integers(4, 7)), avoid=unseen)
        parrot.look_around(brain, r.things, r.heading)
        for _ in range(SETTINGS["namings"]):
            r.heading = float(rng.uniform(-math.pi, math.pi))
            parrot.moment(brain, r.things, r.heading)
            t = r.things[int(rng.integers(len(r.things)))]
            brain.name(naming_word(r, t, rng), t.place)
    seconds["naming"] = time.time() - began

    # 2. practice: kinds 0 to 3 only
    t0 = time.time()
    practised = list(range(4))
    for _ in range(SETTINGS["practice_rooms"]):
        r = world.room(rng, practised, 3, avoid=unseen)
        parrot.look_around(brain, r.things, r.heading)
        asked = room_questions(r, rng, absent=practised, foils=list(range(6)))
        for i in rng.permutation(len(asked))[: SETTINGS["asked"]]:
            q = asked[int(i)]
            brain.practice(q.text, q.answer if len(q.answer) > 1 else q.answer[0])
    seconds["practice"] = time.time() - t0
    lessons = {"naming_and_practice": int(brain.lexicon.lessons),
               "words": list(brain.lexicon.forms)}
    raised_macs = int(brain.lexicon.work["macs"])
    card = {"seed": a.seed, "cadence": cadence.__version__, "settings": SETTINGS,
            "teacher": "tools/raise_brain.py", "raised": time.strftime("%Y-%m-%d %H:%M")}
    path = parrot.save(brain, a.out, card)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    # 3. the test, nothing taught
    t0 = time.time()
    readings: dict[str, list[bool]] = {}
    record: list[dict[str, Any]] = []
    ablated = ablate(brain)

    def asked(gate: str, q: world.Question) -> None:
        said = brain.ask(q.text)
        ok = world.right(q, said)
        readings.setdefault(gate, []).append(ok)
        if gate.startswith("W1"):
            readings.setdefault("W6_ablated", []).append(world.right(q, ablated.ask(q.text)))
            if q.about == "out_of_view":
                readings.setdefault("W4_out_of_view", []).append(ok)
        if not ok:
            record.append({"gate": gate, "question": q.text, "answer": q.answer, "said": said})

    for _ in range(SETTINGS["test_rooms"]):
        r = world.room(rng, named, int(rng.integers(4, 7)), avoid=unseen)
        parrot.look_around(brain, r.things, r.heading)
        for q in room_questions(r, rng, absent=named, foils=list(range(6, 12))):
            asked(gate_of(q), q)
    for _ in range(SETTINGS["unseen_rooms"]):
        k = int(rng.choice(named))
        r = world.room(rng, [j for j in named if j != k], int(rng.integers(3, 6)), avoid=unseen)
        r.things.append(world.Thing(k, unseen[k], world.free_place(rng, r.things)))
        parrot.look_around(brain, r.things, r.heading)
        asked("W3_colour", world.ask_colour(r, k, rng))
        asked("W3_where", world.ask_where(r, k))
        asked("W3_by_colour", world.ask_by_colour(r, unseen[k]))
    seconds["test"] = time.time() - t0

    # 4. new words, three namings each
    t0 = time.time()
    new = list(range(world.TRAINED, world.KINDS))
    for n in new:
        r = world.room(rng, named, 3, avoid=unseen)
        r.things.append(world.Thing(n, int(rng.integers(world.COLOURS)),
                                    world.free_place(rng, r.things)))
        parrot.look_around(brain, r.things, r.heading)
        for _ in range(3):
            brain.name(world.KIND_WORDS[n], r.things[-1].place)
    for _ in range(SETTINGS["new_rooms"]):
        r = world.room(rng, named + new, int(rng.integers(4, 7)), avoid=unseen)
        if not set(new) & set(r.kinds()):
            r.things.append(world.Thing(int(rng.choice(new)), int(rng.integers(world.COLOURS)),
                                        world.free_place(rng, r.things)))
        parrot.look_around(brain, r.things, r.heading)
        for t in r.things:
            if t.kind in new:
                asked("W2_where", world.ask_where(r, t.kind))
                asked("W2_colour", world.ask_colour(r, t.kind, rng))
    seconds["new_words"] = time.time() - t0

    def pool(*names: str) -> dict[str, Any]:
        oks = [ok for n in names for ok in readings.get(n, [])]
        return {"rate": float(np.mean(oks)) if oks else None, "n": len(oks)}

    out = {
        "what": "the page's brain raised by the scripted teacher and read on rooms it never saw",
        "cadence": cadence.__version__, "seed": a.seed, "settings": SETTINGS,
        "brain_file": str(path.relative_to(HERE)), "brain_sha256": digest,
        "lessons": lessons, "unseen_colours": {world.KIND_WORDS[k]: world.COLOUR_WORDS[c]
                                               for k, c in unseen.items()},
        "readings": {g: {"rate": float(np.mean(v)), "n": len(v)} for g, v in sorted(readings.items())},
        "pools": {"W1": pool("W1_practised", "W1_named_only"), "W2": pool("W2_where", "W2_colour"),
                  "W3": pool("W3_colour", "W3_by_colour"), "W5": pool("W5_by_colour", "W5_by_place")},
        "parameters": int(brain.lexicon.connectome.synapses // 2),
        "macs": {"lexicon_raising": raised_macs, "lexicon_all": int(brain.lexicon.work["macs"]),
                 "map_synapses": int(brain.map.connectome.synapses), "map_work": dict(brain.map.work)},
        "seconds": {k: round(v, 1) for k, v in seconds.items()},
        "wrong": record[:40],
        "when": time.strftime("%Y-%m-%d %H:%M"),
    }
    a.evidence.mkdir(parents=True, exist_ok=True)
    commit = cadence.__version__.split(".")[-1]
    target = a.evidence / f"raised-{time.strftime('%Y%m%d-%H%M')}-{commit}.json"
    target.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("readings", "pools", "parameters", "seconds")}, indent=1))
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
