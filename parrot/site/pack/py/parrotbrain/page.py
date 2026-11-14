"""The page's host for the composed parrot brain: `cadence.parrot.host.Host` (the parrot-brain
lane's: two eyes rendered from the scene, the Wulst's units, the reach learned from head turns,
the kinds, the focus and the map of things) with the page's hearing layer beside it (the
placeholder host's ear: the noise filter, the sounds kept in the library's LongTermMemory and
SynapticMemory, the calls and the drive to call). The composed brain's eyes, joints, focus and
distance are its own; the hearing layer only hears and calls.

The whole brain (`config["whole"]`: the association, the ear, the voice and the dopamine) is the
lane's; its moment costs seconds in Python, so the page runs the first brain (`whole` False) until
it is light enough, and says so.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from cadence.parrot.host import Host as Composed

from .host import Host as Hearing

EAR = ("ear", "fieldl", "ncm", "voice")


class Host:
    def __init__(self, config: dict[str, Any]):
        self.brain = Composed({"files": config.get("files"), "whole": config.get("whole", False), "learn": bool(config.get("learn", False)),
                               **({"genes": config["genes"]} if config.get("genes") else {})})
        self.hearing = Hearing({"eye": {"w": 16, "h": 8}, "files": config.get("files"), "revise": config.get("revise", 0.7)})
        self.blank = np.zeros(16 * 8 * 3, np.uint8)
        d = self.brain.describe()
        self.base = int(d["neurons"])
        self.ear = []
        start = self.base
        for p in self.hearing.populations:
            if p["name"] in EAR:
                self.ear.append((p, {**p, "start": start}))
                start += p["size"]
        self.neurons = start
        self.buffers: dict[str, Any] = {}

    def describe(self) -> dict[str, Any]:
        d = self.brain.describe()
        h = self.hearing.describe()
        d.update(populations=d["populations"] + [q for _, q in self.ear], neurons=self.neurons,
                 repertoire=h["repertoire"], calls_credit=h["calls_credit"], whole=self.brain.whole is not None,
                 title=d["title"] + (" (the first brain; the whole brain's moment is too slow for the page)" if self.brain.whole is None else ""))
        return d

    def step(self, meta: dict[str, Any], arrays: dict[str, np.ndarray]) -> dict[str, Any]:
        audio = arrays.get("audio")
        out = self.brain.step({**meta, "show_eyes": True}, {} if audio is None else {"audio": audio})
        heard = self.hearing.step({k: meta.get(k) for k in ("t", "reward", "voice_ok", "things", "focus_kind")},
                                  {"left": self.blank, "right": self.blank, "proprio": np.zeros(22, np.float32),
                                   "mel": arrays.get("mel", np.zeros(0, np.float32)), "pcm": arrays.get("pcm")})
        activity = np.zeros(self.neurons, np.float32)
        activity[: self.base] = self.brain.buffers["activity"]
        ha = self.hearing.buffers["activity"]
        for p, q in self.ear:
            activity[q["start"]: q["start"] + q["size"]] = ha[p["start"]: p["start"] + p["size"]]
        self.buffers = {**self.brain.buffers, "activity": activity}
        names = list(out["buffers"])
        if "voice" in self.hearing.buffers and "voice" in heard["buffers"]:
            self.buffers["voice"] = self.hearing.buffers["voice"]
            names.append("voice")
            if "voice_pcm" in heard["buffers"]:
                self.buffers["voice_pcm"] = self.hearing.buffers["voice_pcm"]
                names.append("voice_pcm")
        lessons = int(getattr(getattr(self.brain.parrot, "distance", None), "lessons", 0) or 0)
        out.update(voice_rate=heard.get("voice_rate", 8000), knows=heard.get("knows", []), recalled=heard.get("recalled"), buffers=names, lessons=lessons, words=len(self.hearing.mem.sayable()), drive=heard["drive"], said_sound=heard["said"], heard_sound=heard["heard_sound"],
                   memory=heard["memory"], repertoire=heard["repertoire"], heard=heard["heard"], paid_sounds=heard["paid"])
        return out

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        cmd = message.get("command")
        if cmd in ("remember", "forget", "memory", "repertoire", "debug", "sound"):
            return self.hearing.handle(message)
        if cmd == "describe":
            return self.describe()
        if cmd == "reset":
            self.hearing.handle(message)
        return self.brain.handle(message)
