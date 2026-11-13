"""The page's host for the parrot's brain: ``cadence.words.Words`` behind the page's messages.

The brain answers with the library's own calls: ``Words.ask`` for a question, ``Words.name`` for a
naming, ``Words.look`` for what the eyes report, ``Words.practice`` for a right answer told. The
host records what those calls did, for the brain view: which words were heard, the concepts they
settled on, each question the map was asked and what it found, and each word the motor said.
Recording changes nothing the brain computes: the calls are the library's, made once, and the
settles drawn sweep by sweep are settles of the same synapses from rest, run again for the
drawing.

Messages (JSON objects with a ``command``):

- ``describe``: the brain as the pack holds it: the lexicon's concept groups, its words, the
  map's plane and cells, the card of the file.
- ``room``: ``{"things": [[kind, colour, x, y], ...], "heading": h}``: a new room; the map is
  emptied and the parrot looks around (eight moments) and turns back to ``heading``.
- ``moment``: the same fields: one moment; the eyes report the things in view.
- ``ask``: ``{"question": text}``: the answer and its story.
- ``name``: ``{"word": text, "at": [x, y]}``: a naming of the thing at ``at``.
- ``pistachio``: a reward for the latest answer. Through ``Words.reward`` where the brain has a
  reward path; a brain without one takes the answer it gave as the answer told
  (``Words.practice``), and the reply says which (``how``).
- ``tell``: ``{"answer": text}``: the right answer to the latest question (``Words.practice``).
- ``reset``: the brain as the pack holds it (the words taught on the page are forgotten).
- ``hear``: ``{"samples": [...], "rate": hz}``: a question asked aloud. Refused by a brain with no
  ears (cadence#329).

Every reply carries the map's inventory and, in the buffers ``potential``, ``clock`` and
``synapses``, the map's carried state and the lexicon's synapses, for the drawing.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from . import brain as parrot
from . import world


class Host:
    """The parrot's brain, answering the page's requests."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})
        self.path = self.config.get("brain")
        self.buffers: dict[str, np.ndarray] = {}
        self.things: list[world.Thing] = []
        self.heading = 0.0
        self.asked: dict[str, Any] | None = None  # the latest question and its answer
        began = time.perf_counter()
        self._load()
        self.load_ms = (time.perf_counter() - began) * 1000.0

    def _load(self) -> None:
        if self.path:
            self.brain, self.record = parrot.load(self.path)
        else:
            self.brain, self.record = parrot.make_brain(), {"card": {}}
        self.asked = None

    # -- what the page is given

    def _synapses(self) -> np.ndarray:
        """The efficacy of each word's synapse onto each concept, ``(words, concepts)``."""
        lex = self.brain.lexicon
        eff = np.asarray(lex.graph.efficacy, dtype=np.float64)
        pre = np.asarray(lex.connectome.pre)
        post = np.asarray(lex.connectome.post)
        words = len(lex.forms)
        out = np.zeros((words, lex.concepts))
        forward = pre < words  # word neurons are numbered first; their synapses onto concepts
        out[pre[forward], post[forward] - lex.capacity] = eff[forward]
        return out

    def _state(self) -> dict[str, Any]:
        m = self.brain.map
        self.buffers["potential"] = np.asarray(m.potential, dtype=np.float64).ravel().copy()
        self.buffers["clock"] = np.asarray(m.clock, dtype=np.float64).ravel().copy()
        self.buffers["synapses"] = self._synapses().ravel()
        things = []
        for t in m.things():
            things.append({"kind": int(t["kind"]), "state": t["state"],
                           "place": None if t["place"] is None else [float(v) for v in t["place"]],
                           "colour": (t.get("values") or {}).get("colour")})
        return {"things": things, "words": list(self.brain.lexicon.forms),
                "heading": self.brain.body.heading,
                "buffers": ["potential", "clock", "synapses"]}

    def _scene(self, message: dict[str, Any]) -> None:
        self.things = [world.Thing(int(k), int(c), np.array([float(x), float(y)]))
                       for k, c, x, y in message.get("things", [])]
        self.heading = float(message.get("heading", self.heading))

    def _seen(self) -> list[int]:
        """The things the eyes report this moment, as numbers into the page's list."""
        return [i for i, t in enumerate(self.things) if world.in_view(self.heading, t.place)[0]]

    def _changed(self, before: np.ndarray, most: int = 60) -> list[list[float]]:
        """The synapses a lesson changed: ``[word, concept, change]``, the largest first, down to
        a fiftieth of the largest."""
        after = self._synapses()
        rows = min(len(before), len(after))
        delta = np.zeros_like(after)
        delta[:rows] = after[:rows] - before[:rows]
        delta[rows:] = after[rows:]
        flat = np.argsort(-np.abs(delta).ravel())[:most]
        least = 0.02 * float(np.abs(delta).max()) if delta.size else 0.0
        out = []
        for i in flat:
            u, c = divmod(int(i), after.shape[1])
            if abs(delta[u, c]) > max(least, 1e-9):
                out.append([u, c, float(delta[u, c])])
        return out

    # -- the requests

    def describe(self) -> dict[str, Any]:
        lex, m = self.brain.lexicon, self.brain.map
        groups = {k: [s.start, s.stop] for k, s in lex.groups.items()}
        return {"groups": groups, "concepts": lex.concepts, "capacity": lex.capacity,
                "answers": list(self.brain.answers), "steps": lex.steps,
                "plane": list(m.plane), "cells": list(m.cells),
                "width": int(m.width), "units": int(m.units),
                "values": {k: [s.start, s.stop] for k, s in m.values.items()},
                "kinds": list(world.KIND_WORDS), "colours": list(world.COLOUR_WORDS),
                "places": list(world.PLACE_WORDS), "view": world.VIEW,
                "card": self.record.get("card", {}), "lessons": int(lex.lessons),
                "parameters": int(lex.connectome.synapses // 2),
                "map_neurons": int(m.neurons), "map_synapses": int(m.connectome.synapses),
                "reward_path": hasattr(self.brain, "reward"),
                "load_ms": round(self.load_ms, 1), **self._state()}

    def room(self, message: dict[str, Any]) -> dict[str, Any]:
        self._scene(message)
        parrot.look_around(self.brain, self.things, self.heading)
        return {"seen": self._seen(), **self._state()}

    def moment(self, message: dict[str, Any]) -> dict[str, Any]:
        self._scene(message)
        parrot.moment(self.brain, self.things, self.heading)
        return {"seen": self._seen(), **self._state()}

    def name(self, message: dict[str, Any]) -> dict[str, Any]:
        word = " ".join(str(message.get("word", "")).lower().split())
        at = np.asarray(message["at"], dtype=np.float64).reshape(2)
        before = self._synapses()
        error = self.brain.name(word, at)
        unit = self.brain.lexicon.unit(word)
        counts = self.brain.lexicon.counts.get(tuple(self.brain.shares))
        lessons = int(counts[unit]) if unit is not None and counts is not None else 0
        return {"word": word, "unit": unit, "lessons": lessons,
                "error": None if not np.isfinite(error) else float(error),
                "changed": self._changed(before), **self._state()}

    def ask(self, message: dict[str, Any]) -> dict[str, Any]:
        question = str(message.get("question", ""))
        story = Story(self.brain)
        began = time.perf_counter()
        with story:
            said = self.brain.ask(question)
        ms = (time.perf_counter() - began) * 1000.0
        self.asked = {"question": question, "said": list(said)}
        return {"question": question, "said": said, "ms": round(ms, 1),
                **story.told(question), **self._state()}

    def pistachio(self, message: dict[str, Any]) -> dict[str, Any]:
        if self.asked is None:
            return {"refused": "Ask the parrot something first.", **self._state()}
        before = self._synapses()
        dopamine = None
        if hasattr(self.brain, "reward"):
            how = "reward"
            dopamine = float(self.brain.reward(float(message.get("amount", 1.0))))
        else:
            how = "practice"
            said = self.asked["said"]
            self.brain.practice(self.asked["question"], said if len(said) > 1 else said[0])
        return {"how": how, "dopamine": dopamine, "changed": self._changed(before),
                **self.asked, **self._state()}

    def tell(self, message: dict[str, Any]) -> dict[str, Any]:
        if self.asked is None:
            return {"refused": "Ask the parrot something first.", **self._state()}
        answer = [" ".join(a.lower().split()) for a in str(message.get("answer", "")).split(",")]
        answer = [a for a in answer if a]
        if not answer:
            return {"refused": "Type the right answer.", **self._state()}
        before = self._synapses()
        self.brain.practice(self.asked["question"], answer if len(answer) > 1 else answer[0])
        return {"how": "practice", "answer": answer, "changed": self._changed(before),
                **self.asked, **self._state()}

    def reset(self) -> dict[str, Any]:
        self._load()
        return self.describe()

    def hear(self, message: dict[str, Any]) -> dict[str, Any]:
        return {"refused": "This brain has no ears: a question asked aloud enters it in the "
                           "ears' step (cadence#329)."}

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        command = message.get("command")
        self.buffers = {}
        calls = {"describe": lambda: self.describe(), "room": lambda: self.room(message),
                 "moment": lambda: self.moment(message), "ask": lambda: self.ask(message),
                 "name": lambda: self.name(message), "pistachio": lambda: self.pistachio(message),
                 "tell": lambda: self.tell(message), "reset": lambda: self.reset(),
                 "hear": lambda: self.hear(message)}
        if command not in calls:
            raise ValueError(f"no command {command!r}")
        return calls[command]()


class Story:
    """What one question did in the brain, recorded around the library's own calls: the map's
    questions and the motor's words. Inside ``with``, the map's question methods and the
    lexicon's ``say`` are wrapped on the instance; on leaving they are the class's again."""

    MAP = ("where_is", "where_is_value", "what_is_at", "values_at")

    def __init__(self, brain: Any) -> None:
        self.brain = brain
        self.calls: list[dict[str, Any]] = []
        self.spoken: list[dict[str, Any]] = []

    def __enter__(self) -> Story:
        m, lex = self.brain.map, self.brain.lexicon
        for name in self.MAP:
            setattr(m, name, self._map_call(name, getattr(m, name)))
        say = lex.say

        def said(concept: Any, *args: Any, **kwargs: Any) -> Any:
            word = say(concept, *args, **kwargs)
            if isinstance(concept, tuple):
                concept = lex.index(*concept)
            vector = (np.eye(lex.concepts)[int(concept)] if isinstance(concept, (int, np.integer))
                      else np.asarray(concept, dtype=np.float64).reshape(lex.concepts))
            self.spoken.append({"concept": vector, "word": word})
            return word

        lex.say = said
        return self

    def __exit__(self, *exc: Any) -> None:
        for name in self.MAP:
            self.brain.map.__dict__.pop(name, None)
        self.brain.lexicon.__dict__.pop("say", None)

    def _map_call(self, name: str, call: Any) -> Any:
        def recorded(*args: Any, **kwargs: Any) -> Any:
            out = call(*args, **kwargs)
            entry: dict[str, Any] = {"call": name}
            if name == "where_is":
                entry["kind"] = int(args[0])
            elif name == "where_is_value":
                entry["group"], entry["value"] = str(args[0]), int(args[1])
            else:
                place = args[0] if args else kwargs.get("place")
                entry["place"] = None if place is None else [float(v) for v in np.ravel(place)]
                if kwargs.get("cells") is not None:
                    entry["cells"] = int(np.asarray(kwargs["cells"], dtype=bool).sum())
            if name in ("where_is", "where_is_value"):
                entry["found"] = np.asarray(out, dtype=np.float64).reshape(-1, 2).tolist()
            elif name == "what_is_at":
                entry["found"] = None if out is None else int(out)
            else:
                entry["found"] = {k: (None if v is None else int(v)) for k, v in out.items()}
            self.calls.append(entry)
            return out
        return recorded

    def _sweeps(self, drive: np.ndarray, part: np.ndarray) -> list[list[float]]:
        """A settle of the lexicon from rest on ``drive``, sweep by sweep, read on ``part``: the
        same synapses and the same sweeps as the brain's settle, run again for the drawing."""
        lex = self.brain.lexicon
        state = lex.graph.settle_batch(drive[None, :], steps=lex.steps, tolerance=None,
                                       trajectory=True)
        rows = np.asarray(state.trajectory, dtype=np.float64).reshape(-1, lex.neurons)
        return np.round(rows[:, part], 4).tolist()

    def told(self, question: str) -> dict[str, Any]:
        brain, lex = self.brain, self.brain.lexicon
        heard = brain.last.get("heard")
        words = brain._words(question)
        drive = np.zeros(lex.neurons)
        entries = []
        for w in words:
            unit = lex.unit(w)
            entries.append({"form": w, "unit": unit})
            if unit is not None:
                drive[lex.word[unit]] = lex.drive
        about = None
        if heard is not None and heard.about is not None:
            about = [heard.about[0], int(np.argmax(heard.about[1]))]
        hear = {"words": entries, "sweeps": self._sweeps(drive, lex.concept),
                "concepts": None if heard is None else np.round(heard.concepts, 4).tolist(),
                "reads": {} if heard is None else {g: round(float(v), 4)
                                                   for g, v in heard.reads.items()}}
        entered = lex.word[: len(lex.forms)]
        spoken = []
        for item in self.spoken:
            vector = np.asarray(item["concept"], dtype=np.float64)
            drive = np.zeros(lex.neurons)
            drive[lex.concept] = lex.drive * vector
            unit = lex.unit(item["word"]) if item["word"] else None
            letters = [int(c) for c in lex.letters[unit].argmax(axis=1)] if unit is not None else []
            spoken.append({"concept": np.round(vector, 4).tolist(), "word": item["word"],
                           "unit": unit, "sweeps": self._sweeps(drive, entered),
                           "letters": letters})
        places = [[float(v) for v in np.ravel(p)] for p, _ in brain.last.get("things", [])]
        return {"hear": hear, "about": about, "map_calls": self.calls, "places": places,
                "spoken": spoken}
