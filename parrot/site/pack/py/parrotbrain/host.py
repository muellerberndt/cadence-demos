"""The page's placeholder brain host: the joint and eye interface of the parrot page, with a
hand-written controller in place of a brain, so the page runs end to end until the composed brain's
host takes its place in the pack (INTERFACES P6). Nothing here is learned.

Interface (the composed brain's host keeps it):
  describe()                      -> {name, placeholder, joints, eye, rate_hz, populations, groups, neurons}
  step(meta, arrays) -> {group_activity, readout, focus, voice?}, buffers "activity", "targets"[, "voice"]
  reset(), silence(group, on)

`arrays` holds `left` and `right`, each eye's image (uint8, rows top-down, (h, w, 3), column 0 at
the eye's rear edge), `proprio` (the joints' angles then speeds on [-1, 1]), and the moment's sound:
`audio` (1,600 samples at 16 kHz) and `mel` (ten log-mel frames of 40 bands, frame-major).
`meta` holds `t`, `reward`, `voice_ok` (the page may play sound) and `cue` (the head-frame azimuth
and elevation of a thing the visitor clicked, which draws the focus there).

The placeholder is a newborn, and a hand-written stand-in for what the composed brain learns: it
hears (its ear populations follow the sound's bands); a drive to call rises with quiet time (a call
every two to six seconds or so), faster when a new thing appears or the visitor has just spoken,
and when it is high the parrot calls, never over its own sound, picking from its repertoire
(African Grey calls from a licensed recording, `calls.json`, and its own babble: a random contour
or a replay of a heard snippet), favouring calls a pistachio followed. It cuts what it hears into
sounds (onset to offset) and keeps only voice-like ones (not a fan's steady hiss, not a click, not a
long steady hum), with the background's spectrum taken out. What it hears is told to the library's own memories
(`sounds.py`): each sound is a record in `cadence.LongTermMemory` (told again, a record is
rewritten and deepened; deep records fade far more slowly), and a `cadence.SynapticMemory` links the
sound to the thing in focus. A record deep enough is a sound the parrot can say back ("learned from
you"), the deeper the more often and the more faithfully. The drive and the choice of call are the
placeholder's hand-written stand-in; the composed brain learns them from the pistachio.

The placeholder looks at what stands out: in each eye, the pixels whose colour differs most from
the eye's own mean colour. It looks as a parrot does: its head still, then a quick turn toward the
strongest spot (or elsewhere), a hold of one to three seconds, now and then a slow tilt of the head. Its "distance" units are a stand-in for the units a real brain learns: a population
tuned to the apparent size of what it looks at (a thing near looks large), so the page's tuning
curve, its question mark and its silence switch run end to end; the composed brain names its own.
"""
from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from .sounds import BANDS, KINDS, PISTACHIO, RANGE as BAND_RANGE, VALUE_FRAMES, SoundMemory, warp_row
from .sounds import _COSINES as COSINES

JOINTS = ["head_yaw", "head_pitch", "head_roll", "neck_pitch", "beak_open", "wing_l", "wing_r",
          "grip_l", "grip_r", "leg_l", "leg_r"]
RANGE = {"head_yaw": (-75.0, 75.0), "head_pitch": (-25.0, 35.0), "head_roll": (-20.0, 20.0)}
DISTANCE_UNITS = 12
END_QUIET = 30   # frames of quiet that end an utterance (0.3 s: the pauses inside a spoken phrase are shorter)
ONSET, STAY = 2.5, 1.5  # nats above the room's level at which an utterance begins, and above which it goes on (11 dB and 6.5 dB: a voice 10 dB above a room's noise is heard whole; with 4.0 for both, short words in a room at 20 dB were cut to their peaks and left out as clicks)
OWN_TAIL = 3     # moments after its own voice in which a sound counts as its own (the room's echo of it)
VOICED = 0.15    # the least share of an utterance's loud frames that repeat at a voice's pitch (speech reads 0.19 to 1, also in a noisy room; a cough, a breath, typing, a fan read 0)


def voiced(pcm: np.ndarray, rate: int = 16000, n: int = 512, hop: int = 160) -> float:
    """The share of a sound's loud frames that are voiced: frames (32 ms, one every 10 ms) whose samples repeat
    at a pitch period between 80 and 400 Hz (the peak of the frame's autocorrelation there, against its
    value at no lag, above 0.45). A voice is voiced through its vowels; a cough, a breath, a hiss, a tap is not."""
    x = np.asarray(pcm, np.float64)
    if len(x) < n:
        return 0.0
    k = 1 + (len(x) - n) // hop
    w = np.hanning(n)
    X = x[np.arange(n)[None, :] + hop * np.arange(k)[:, None]] * w
    ac = np.fft.irfft(np.abs(np.fft.rfft(X, 2 * n, axis=1)) ** 2, axis=1)[:, :n]
    wac = np.fft.irfft(np.abs(np.fft.rfft(w, 2 * n)) ** 2)[:n]
    a, b = int(rate / 400.0), int(rate / 80.0)
    peak = (ac[:, a:b] / wac[a:b]).max(axis=1) / (ac[:, 0] / wac[0] + 1e-12)
    loud = ac[:, 0] > 0.03 * ac[:, 0].max()
    return float(np.mean(peak[loud] > 0.45)) if loud.any() else 0.0


FOLLOW = "terms-mean"  # what the follower compares: "bands", "terms", or "terms-mean" (the terms less their mean so far)


def follow_feature(frames: np.ndarray) -> np.ndarray:
    """The frames of a sound as the follower compares them, each made from the sound up to that frame alone (it
    works as the sound comes in): each band within the code's range of the frame's loudest; of those the smooth
    shape across the bands (the first cosine terms, as the matcher's `shape`); less each term's mean over the
    frames so far (the voice's and the room's colour out, as far as it is known by then)."""
    f = np.atleast_2d(np.asarray(frames, np.float64))
    f = np.maximum(f, f.max(axis=1, keepdims=True) - BAND_RANGE)
    if FOLLOW == "bands":
        f = f - f.mean(axis=1, keepdims=True)
        g = np.pad(f, ((0, 0), (1, 1)), mode="edge")
        return (g[:, :-2] + g[:, 1:-1] + g[:, 2:]) / 3.0
    c = f @ COSINES.T
    if FOLLOW == "terms-mean":
        c = c - np.cumsum(c, axis=0) / np.arange(1, len(c) + 1)[:, None]
    return c


class Follower:
    """Follows an utterance as it is said. The records that keep their words' marks (those heard often enough
    to say back) are lined up with the
    sound coming in, one frame at a time (time warping, every record side by side, the end left open): each
    record's cheapest place so far says how far along it the sound is. The records that fit about as well as
    the best are asked which words the sound has passed (a word counts once most of it is behind: words that
    begin alike part ways by then); where they all name the same words so far, those words are known, each
    as it is spoken. Nothing is decided here about the utterance's meaning: that is its record's
    link, read when the utterance ends."""
    MARGIN = 1.25   # records whose cost is within this factor of the best are asked
    INTO = 3        # frames past a word's mark, at least, before the word counts as heard
    SHARE = 0.6     # and this share of the first word's own length (words that begin alike part ways by then)
    NEXT = 0.3      # the share of a later word's length (the sound's place in the record is settled by then)

    def __init__(self, mem: SoundMemory):
        self.mem = mem
        self.sig: tuple | None = None
        self.slots: list[int] = []
        self.row = None
        self.said: list[str] = []
        self.at: list[int] = []

    def _templates(self) -> None:
        deep = self.mem.records.deep  # it follows along the sounds it knows well (heard often enough to say back)
        slots = sorted(s for s in self.mem.marks if s < self.mem.records.count and self.mem.marks[s] and deep[s] >= self.mem.LEVEL)
        sig = (tuple(slots), tuple(int(self.mem.heard[s]) for s in slots))
        if sig == self.sig:
            return
        self.sig, self.slots = sig, slots
        if not slots:
            return
        feats = [follow_feature(self.mem.template(s)) for s in slots]
        self.lens = np.array([len(f) for f in feats])
        m = int(self.lens.max())
        self.T = np.zeros((len(slots), m, feats[0].shape[1]), np.float32)
        for i, f in enumerate(feats):
            self.T[i, : len(f)] = f
        self.TT = (self.T ** 2).sum(axis=2)
        self.past = np.arange(m)[None, :] >= self.lens[:, None]  # columns past each record's end
        self.steps = np.arange(1, m + 1)[None, :]
        self.words = [[w for _, w in self.mem.marks[s]] for s in slots]
        self.starts = [np.array([f for f, _ in self.mem.marks[s]]) for s in slots]
        # the place in each record from which each of its words counts as heard
        self.known = [st + np.maximum(self.INTO, np.where(np.arange(len(st)) == 0, self.SHARE, self.NEXT) * (np.append(st[1:], n) - st)) for st, n in zip(self.starts, self.lens)]

    def start(self) -> None:
        self._templates()
        self.said, self.at, self.i = [], [], 0
        self.row = None
        self.sum = None  # the sum of the utterance's terms so far (for their mean so far)
        if self.slots:
            self.row = np.full((len(self.slots), self.T.shape[1] + 1), np.inf, np.float32)
            self.row[:, 0] = 0.0

    def _feature(self, f: np.ndarray) -> np.ndarray:
        """One frame of the utterance coming in, as `follow_feature` makes a record's frames."""
        f = np.asarray(f, np.float64)
        f = np.maximum(f, f.max() - BAND_RANGE)
        if FOLLOW == "bands":
            f = f - f.mean()
            g = np.pad(f, 1, mode="edge")
            return (g[:-2] + g[1:-1] + g[2:]) / 3.0
        c = COSINES @ f
        if FOLLOW == "terms-mean":
            self.sum = c.copy() if self.sum is None else self.sum + c
            c = c - self.sum / (self.i + 1)
        return c

    def frame(self, f: np.ndarray) -> list[dict]:
        """One more frame of the utterance; the words that became known with it."""
        if self.row is None:
            return []
        x = self._feature(f).astype(np.float32)
        d = np.sqrt(np.maximum(self.TT + float(x @ x) - 2.0 * (self.T @ x), 0.0) / len(x))
        d[self.past] = 1e6
        self.row = warp_row(self.row, d)
        self.i += 1
        if self.i < 12:  # the first tenth of a second says little
            return []
        score = self.row[:, 1:] / (self.i + self.steps)
        score[self.past] = np.inf
        col = np.argmin(score, axis=1)
        best = score[np.arange(len(col)), col]
        top = float(best.min())
        if not np.isfinite(top):
            return []
        runs = []
        for k in np.flatnonzero(best <= top * self.MARGIN):
            n = int(np.sum(self.known[k] <= col[k]))  # the words heard so far in this record
            runs.append(self.words[k][:n])
        agreed = runs[0][: min(len(r) for r in runs)]
        for r in runs[1:]:
            for j, w in enumerate(agreed):
                if r[j] != w:
                    agreed = agreed[:j]
                    break
        new = []
        if len(agreed) > len(self.said) and agreed[: len(self.said)] == self.said:
            for w in agreed[len(self.said):]:
                new.append({"word": w, "index": len(self.said), "frame": self.i})
                self.said.append(w); self.at.append(self.i)
        return new


def _unit(name: str, value: float) -> float:
    lo, hi = RANGE[name]
    return float(2.0 * (value - lo) / (hi - lo) - 1.0)


def _value(name: str, unit: float) -> float:
    lo, hi = RANGE[name]
    return float(lo + (unit + 1.0) / 2.0 * (hi - lo))


class Host:
    def __init__(self, config: dict[str, Any]):
        eye = config.get("eye", {})
        self.w, self.h = int(eye.get("w", 64)), int(eye.get("h", 32))
        self.field = math.radians(float(eye.get("field", 87.5)))
        self.vfield = math.radians(float(eye.get("vfield", 60.0)))
        self.fovea = float(eye.get("fovea", 0.4))
        self.axis = math.radians(float(eye.get("axis", 75.0)))
        t = 2.0 * (np.arange(self.w) + 0.5) / self.w - 1.0
        self.az = self.field * t * (self.fovea + (1.0 - self.fovea) * np.abs(t))  # toward the beak
        r = 1.0 - 2.0 * (np.arange(self.h) + 0.5) / self.h
        self.el = self.vfield * r * (self.fovea + (1.0 - self.fovea) * np.abs(r))
        self.silenced: set[str] = set()
        self.buffers: dict[str, Any] = {}
        pops = [("retina_l", "Left eye's retina", self.w * self.h // 4, "retina"),
                ("retina_r", "Right eye's retina", self.w * self.h // 4, "retina"),
                ("salience", "What stands out", 2 * 16, "tectum"),
                ("distance", "Distance units", DISTANCE_UNITS, "distance"),
                ("motor", "Motor: the joints' targets", len(JOINTS), "motor"),
                ("ear", "Ear: the sound's 40 bands", 40, "ear"),
                ("fieldl", "Field L", 40, "fieldl"),
                ("ncm", "NCM and CM: heard sound, held", 40, "ncm"),
                ("voice", "Voice: the bands it says", 40, "voice")]
        self.populations = []
        start = 0
        for name, title, size, region in pops:
            self.populations.append({"name": name, "title": title, "start": start, "size": size, "region": region})
            start += size
        self.neurons = start
        self.pop = {p["name"]: p for p in self.populations}
        self.preferred = np.geomspace(0.012, 0.25, DISTANCE_UNITS)  # apparent sizes (fractions of a field) each unit prefers
        self.revise = float(config.get("revise", 0.7))
        self.words = list(config.get("words") or KINDS)  # what its sounds can stand for (the trained brain's vocabulary, and its questions)
        self.offer = list(config.get("offer") or [])  # the questions about the thing in focus, on offer when a sound's meaning is guessed
        self.mode = None  # "listen": it attends to the visitor and says back what it hears; "curious": it looks about, listens for questions and says words
        self.focus_kind = None
        self.reset()
        self.load_calls(config.get("files"))

    def reset(self) -> dict[str, Any]:
        self.t = 0
        self.rng = np.random.default_rng(7)
        self.target = {"head_yaw": 0.0, "head_pitch": 0.0, "head_roll": 0.0}
        self.hold_until = 10
        self.tilt = None  # a slow tilt in progress: (start roll, end roll, first moment, moments)
        self.focus = None  # where the last turn went: {"az", "el"} in the head's frame at that moment
        self.heard = np.full((0, 40), math.log(1e-6), np.float32)  # the last 8 s of heard frames
        self.held = np.zeros(40, np.float32)
        self.saying = 0
        self.drive = 0.6
        self.running = math.log(1e-6)  # the ear's running level, which a sudden sound breaks
        self.quiet_for = 0
        self.pre: list = []      # the last 80 ms before a sound's onset (its soft start: an h, an f)
        self.spoiled = False     # the visitor's sound overlapped the parrot's own: only a fragment was heard
        self.since_loud = 99     # frames since the last loud one
        self.startled = -100
        self.last_match = None
        self.things = None
        self.sound = []          # frames of the sound being heard
        self.sound_pcm: list = []  # and the audio itself, 160 samples a frame
        self.pre_pcm: list = []
        self.say_pcm = None      # the audio of the word being said
        self.say_rate = 8000
        self.events: list = []   # the last sounds heard and what became of each (the page's sound report)
        self.quiet = 0           # quiet frames since it ended
        self.floor = math.log(1e-6)
        self.levels = np.zeros(300)  # the last three seconds' frame energies
        self.level_at = 0
        self.mem = SoundMemory(revise=self.revise, words=self.words)
        self.follower = Follower(self.mem)
        self.spotted: list = []  # the words known in the utterance being heard, each as it was spoken
        self.echo = None         # in "listen": the sound just heard, to say back (slot, moment)
        self.view_due = None     # the moment the memory's picture goes to the page after a change (a large reply, kept out of the moment a sound is answered in)
        self.exchange = None     # a sound heard and answered: what a pistachio pays (the sound, its meaning, the sounds said)
        self.unpaid = None       # a word said by itself for the thing in focus, while no pistachio has come (slot, word, moment)
        self.heard_event = None
        self.gap = 0
        self.noise = np.full(40, math.log(1e-6) + 4.0, np.float64)  # the background's spectrum, per band (log)
        self.last_said = None    # (id, moment)
        return {"ok": True}

    # --- the repertoire ------------------------------------------------------------------------
    def load_calls(self, files: str | None) -> None:
        self.repertoire = []
        self.paid = {}
        self.credit = None
        try:
            with open(f"{files}/calls.json") as fh:
                data = json.load(fh)
            for c in data["calls"]:
                self.repertoire.append({"id": c["id"], "tag": c["tag"], "source": "recording", "frames": np.asarray(c["frames"], np.float32),
                                        "pcm": np.asarray(c.get("pcm", []), np.float32), "pcm_rate": int(c.get("pcm_rate", 16000))})
            self.credit = data.get("source")
        except (OSError, KeyError, ValueError, TypeError):
            pass
        self.repertoire.append({"id": "babble", "tag": "babble", "source": "newborn", "frames": None})

    def voice_like(self, frames: np.ndarray, pcm: np.ndarray | None = None) -> tuple[bool, str]:
        """Whether a heard sound is voice-like: not too short (a click, under 120 ms), not a steady tone (a
        hum: its bands barely change from frame to frame), with power where a voice's first resonance lies (not
        a high tone alone, not a thump under 150 Hz alone), and voiced in part (`voiced`: a cough, a breath,
        a hiss or typing has no pitch); without the audio itself, not a steady broadband hiss (a flat
        spectrum)."""
        n = len(frames)
        e = np.log(np.exp(frames.astype(np.float64)).sum(axis=1))
        if n < 12 or int(np.sum(e > self.floor + STAY)) < 12:  # under 120 ms of sound above the room: a pop or a click, not a word
            return False, "click"
        if n > VALUE_FRAMES + 30:
            return False, "too long"
        p = np.exp(frames[:, 2:38].astype(np.float64))
        mean = p.mean(axis=0)
        flatness = float(np.exp(np.log(mean + 1e-12).mean()) / (mean.mean() + 1e-12))
        flux = float(np.abs(np.diff(frames, axis=0)).mean()) if n > 1 else 0.0
        if flux < 0.35:
            return False, "hum"
        loud = p[e > e.max() - 3.5] if n else p
        if loud[:, 1:12].sum() < 0.08 * loud.sum():  # nothing between 200 Hz and 1 kHz, where a voice's first resonance lies (speech holds .17 to .9 of its power there; a phone's ring .005)
            return False, "tone"
        full = np.exp(frames[e > e.max() - 3.5].astype(np.float64))
        if full[:, :3].sum() > 0.7 * full.sum():  # nearly all of it under 150 Hz (speech: .6 at most; a door's thump .9)
            return False, "thump"
        if pcm is not None and len(pcm) >= 512:
            if voiced(pcm) < VOICED:
                return False, "noise"
        elif flatness > 0.55:
            return False, "hiss"
        return True, "voice"

    def clean(self, frames: np.ndarray) -> np.ndarray:
        """The background's spectrum taken out of a sound's frames (power subtraction, kept above a
        fifth of the frame's own power, so soft consonants stay)."""
        p = np.exp(frames.astype(np.float64))
        q = np.maximum(p - np.exp(self.noise)[None, :], 0.2 * p)
        return np.log(q + 1e-6).astype(np.float32)

    def hear_sound(self, frames: np.ndarray, pcm: np.ndarray | None = None) -> dict | None:
        """A voice-like sound the visitor made, cleaned of the background, told to the memories; the
        word it stands for is its record's link. Heard with a thing in focus, it waits for a pistachio
        that links it to that thing."""
        ok, _ = self.voice_like(frames, pcm)
        if not ok:
            return None
        cleaned = self.clean(frames)
        # what stands above the background once its spectrum is out (a sound the background has
        # taken in, such as a hum going on, stands at or below it)
        excess = float(np.percentile(np.log(np.exp(cleaned.astype(np.float64)).sum(axis=1)), 75) - np.log(np.exp(self.noise).sum()))  # its louder part (its soft start and end are kept too)
        if excess < 1.5:
            return None
        self.heard_event = self.mem.hear(cleaned, pcm)
        slot = self.heard_event["write"]["slot"]
        if slot in self.mem.sayable():  # a word it knows, heard again: it rehearses it inwardly once
            self.mem.practice(slot)
        word, link = self.mem.meaning(slot)  # its own link, or what the records it sounds like agree on
        out = {"id": f"you-{slot}", "slot": slot, "deep": round(float(self.mem.records.deep[slot]), 2), "known": bool(self.heard_event["write"]["revised"]),
               "word": word, "link": link, "frames": int(len(frames)), "spotted": [w for w in self.follower.said if w != "<this>" or self.focus_kind in self.words]}
        focus = self.focus_kind if self.focus_kind in self.words else None
        if word is None and self.mode == "curious" and focus and self.offer:
            # no meaning it knows: it guesses one of the questions about the thing in focus
            out["guess"], out["chance"] = self.mem.guess(slot, self.offer, self.mem.near)
        meaning = word or out.get("guess")
        if meaning and ("<this>" not in meaning or focus):
            out["words"] = meaning.replace("<this>", focus or "").split()
        return out

    def _named(self, words: list) -> list:
        """The follower's words with "<this>" as the name of the thing in focus (none in focus: left out)."""
        focus = self.focus_kind if self.focus_kind in self.words else None
        return [{**w, "word": focus if w["word"] == "<this>" else w["word"]} for w in words if w["word"] != "<this>" or focus]

    # --- an exchange: a sound heard, its meaning, the sounds said in answer; a pistachio pays all of it ----------
    def open_exchange(self, slot: int, meaning: str | None, guessed: bool) -> None:
        self.close_exchange()
        if meaning in self.words and 0 <= slot < self.mem.records.count:
            self.exchange = {"slot": int(slot), "meaning": meaning, "guessed": bool(guessed), "answers": [], "t": self.t}

    def sound_for(self, word: str) -> dict | None:
        """The sound to say for a word: the record the word recalls; without one, a sound it can say, guessed."""
        slot, link = self.mem.recall(word)
        guessed = False
        if slot is None:
            slot, link = self.mem.guess_sound(word, but=self.exchange["slot"] if self.exchange is not None else -1)
            guessed = slot is not None
        if slot is None:
            return None
        if self.exchange is not None:
            self.exchange["answers"].append({"word": word, "slot": int(slot), "guessed": guessed})
        return {"id": f"you-{slot}", "slot": int(slot), "link": link, "guessed": guessed}

    def reward_exchange(self, amount: float = PISTACHIO) -> dict | None:
        """A pistachio for the answer: the sound heard is linked to the meaning it was taken for, and each
        word said to the sound it was said with."""
        x, self.exchange = self.exchange, None
        if x is None:
            return None
        self.mem.reward(x["slot"], x["meaning"], amount)
        for a in x["answers"]:
            self.mem.reward(a["slot"], a["word"], amount)
        return {"slot": x["slot"], "meaning": x["meaning"], "guessed": x["guessed"], "link": self.mem.word_of(x["slot"])[1],
                "answers": [{**a, "link": self.mem.word_of(a["slot"])[1]} for a in x["answers"]]}

    def close_exchange(self) -> None:
        """The exchange ends with no pistachio: a guess is doubted for a while, a link used fades a little
        toward what repetition has consolidated."""
        x, self.exchange = self.exchange, None
        if x is None:
            return
        # (where the meaning and a sound were both guesses the blame is shared: each is doubted half as much)
        both = x["guessed"] and any(a["guessed"] for a in x["answers"])
        if x["guessed"]:
            self.mem.doubt(x["slot"], x["meaning"], 0.1 if both else 0.2)
        else:
            self.mem.fade(x["slot"], x["meaning"])
        for a in x["answers"]:
            if a["guessed"]:
                self.mem.doubt(a["slot"], a["word"], 0.1 if both else 0.2)
            else:
                self.mem.fade(a["slot"], a["word"])

    def you_sounds(self) -> list:
        """Records deep enough to say back: the repertoire's sounds learned from the visitor."""
        out = []
        for slot in self.mem.sayable():
            prog = self.mem.programs.get(slot)
            out.append({"id": f"you-{slot}", "tag": "learned from you", "source": "you", "slot": slot,
                        "frames": self.mem.frames_of(slot), "deep": float(self.mem.records.deep[slot]),
                        "heard": int(self.mem.heard[slot]), "program": self.mem.pronunciation(slot),
                        "matches": [] if prog is None else prog["matches"][-20:]})
        return out

    def remember(self, saved: dict) -> dict[str, Any]:
        self.mem.load(saved or {})
        self._sayable_sig = tuple(self.mem.sayable())
        return {"repertoire": self.repertoire_list(), "memory": self.mem.view()}

    def forget(self) -> dict[str, Any]:
        self.mem.clear()
        return {"repertoire": self.repertoire_list(), "memory": self.mem.view()}

    def knows(self) -> list:
        """What it knows: each kind of thing and the word it recalls for it (the link's strength)."""
        m, deep, best = self.mem.meanings(), self.mem.records.deep, {}
        for s in self.mem.sayable():  # of the sounds it can say that stand for a word, the deepest
            w, link = m[s]
            if w and " " not in w and (float(deep[s]), link) > best.get(w, (-1.0, 0.0, 0))[:2]:  # (a question is something it hears, no word to say)
                best[w] = (float(deep[s]), link, s)
        return [{"kind": w, "id": f"you-{best[w][2]}", "slot": int(best[w][2]), "link": round(best[w][1], 3)} for w in self.words if w in best]

    def mem_recalled(self) -> dict | None:
        slot, link = self.mem.recall(self.focus_kind)
        return None if slot is None else {"kind": self.focus_kind, "id": f"you-{slot}", "slot": int(slot), "link": round(link, 3)}

    def choose(self) -> dict:
        m = self.mem.meanings()
        words = [w for w in self.you_sounds() if " " not in (m[w["slot"]][0] or "")]  # its words; a question it keeps for hearing
        options = self.repertoire + words
        slot, link = self.mem.recall(self.focus_kind)  # the focused thing recalls its word
        self.recalled = None if slot is None else {"kind": self.focus_kind, "slot": int(slot), "id": f"you-{slot}", "link": round(link, 3)}
        def weight(r):  # learned words by depth, pistachio-paid sounds more often; calls fewer once it has words
            w = (1.0 + 2.0 * self.paid.get(r["id"], 0.0))
            if "deep" in r:
                w *= 1.0 + 0.5 * r["deep"]
                if slot is not None and r["slot"] == slot:
                    w *= 1.0 + 40.0 * link  # the word the focused thing recalls comes to mind first
                return w
            return w * (0.2 if r["id"] == "babble" else 1.0) * (0.3 if words else 1.0)
        w = np.array([weight(r) for r in options])
        return options[int(self.rng.choice(len(w), p=w / w.sum()))]

    def say(self, pick: dict) -> np.ndarray:
        """The frames it says: a sound it learned comes out the more faithfully the stronger it is."""
        if pick["frames"] is None:
            return self.babble()
        if pick.get("source") == "you":  # a learned word: one attempt of practice, said from its motor program
            frames, m = self.mem.practice(pick["slot"])
            self.say_pcm = self.mem.pcm_of(pick["slot"])  # the word as it heard it: the audio its memory keeps
            self.say_rate = 8000
            self.last_match = m
            return frames
        if pick.get("source") == "recording" and len(pick.get("pcm", [])):  # an African Grey's own call, as recorded
            self.say_pcm, self.say_rate = pick["pcm"], pick["pcm_rate"]
        f = pick["frames"].copy()
        if "deep" in pick:
            blur = 1.0 / (1.0 + pick["deep"])
            soft = 0.5 * f + 0.25 * (np.roll(f, 1, axis=1) + np.roll(f, -1, axis=1))
            soft = 0.5 * soft + 0.25 * (np.roll(soft, 1, axis=0) + np.roll(soft, -1, axis=0))
            f = (1 - blur) * f + blur * soft
        return f.astype(np.float32)

    def repertoire_list(self, slots: list | None = None) -> list:
        """The sounds it can make, for the page (each with its audio); `slots`: those records alone (the sounds
        that changed: the page keeps the others, and their audio is not sent again)."""
        out = []
        for r in ([s for s in self.you_sounds() if s["slot"] in slots] if slots is not None else self.repertoire + self.you_sounds()):
            row = {"id": r["id"], "tag": r["tag"], "source": r["source"], "paid": round(self.paid.get(r["id"], 0.0), 2),
                   **({"pcm": np.round(r["pcm"], 4).tolist(), "pcm_rate": r["pcm_rate"]} if r.get("source") == "recording" and len(r.get("pcm", [])) else {}),
                   "frames": None if r["frames"] is None else r["frames"].ravel().round(2).tolist()}
            if "deep" in r:
                row.update(deep=round(r["deep"], 2), slot=r["slot"], heard=r["heard"], matches=[round(m, 3) for m in r["matches"]],
                           program=r["program"].ravel().round(2).tolist(), pcm=np.round(self.mem.pcm_of(r["slot"]), 4).tolist())
            out.append(row)
        return out

    def _view(self, changed: bool) -> dict | None:
        """The memory's picture for the page: a large reply, sent two and a half seconds after a change (once
        the sound is said back or answered) and every five seconds for the fading."""
        if changed:
            self.view_due = self.t + 25
        if self.t % 50 == 0 or (self.view_due is not None and self.t >= self.view_due):
            self.view_due = None
            return self.mem.view()
        return None

    def _repertoire_changed(self, learned: dict | None, call: dict | None) -> list | None:
        """The records whose sound the page needs (again): a sound it can say that was heard this moment (told
        again, its audio is another mix), and the sounds it can say since this moment. None: nothing changed."""
        if learned is None and call is None:
            return None
        sig = tuple(self.mem.sayable())
        before = set(getattr(self, "_sayable_sig", None) or ())
        self._sayable_sig = sig
        changed = set(sig) - before
        if learned is not None and learned["slot"] in sig:
            changed.add(learned["slot"])
        return sorted(changed) if changed or before - set(sig) else None

    def describe(self) -> dict[str, Any]:
        return {
            "name": "placeholder", "placeholder": True, "newborn": True,
            "title": "Placeholder brain: a newborn, a hand-written controller",
            "joints": JOINTS, "eye": {"w": self.w, "h": self.h}, "rate_hz": 10,
            "populations": self.populations, "neurons": self.neurons, "synapses": 0,
            "repertoire": self.repertoire_list(), "calls_credit": self.credit,
            "groups": [{
                "name": "distance", "title": "Distance units (placeholder)",
                "explain": ("Stand-ins for the units the parrot's brain learns for distance. Here each unit is "
                            "tuned by hand to how large the thing in view looks: a thing near looks large. "
                            "The composed brain names its own units here, with what they learned."),
                "units": list(range(self.pop["distance"]["start"], self.pop["distance"]["start"] + DISTANCE_UNITS)),
                "variable": "distance", "unit": "m", "range": [0.1, 0.8],
            }],
        }

    def silence(self, group: str, on: bool) -> dict[str, Any]:
        (self.silenced.add if on else self.silenced.discard)(group)
        return {"silenced": sorted(self.silenced)}

    def _salience(self, img: np.ndarray) -> np.ndarray:
        x = img.astype(np.float32) / 255.0
        mean = x.reshape(-1, 3).mean(axis=0)
        d = np.sqrt(((x - mean) ** 2).sum(axis=2))
        sat = x.max(axis=2) - x.min(axis=2)
        return d * (0.5 + sat)

    def babble(self) -> np.ndarray:
        """A newborn's sound: a short run of frames, a replay of something heard or a random contour."""
        rng = self.rng
        floor = math.log(1e-6)
        loud = np.flatnonzero(self.heard.max(axis=1) > floor + 9.0) if len(self.heard) else np.array([], int)
        if len(loud) > 20 and rng.random() < 0.5:
            start = int(rng.choice(loud)); n = int(rng.integers(25, 70))
            seg = self.heard[max(0, start - 10): start - 10 + n].copy()
            shift = int(rng.integers(-3, 4))
            seg = np.roll(seg, shift, axis=1)
            seg = 0.5 * seg + 0.25 * (np.roll(seg, 1, axis=1) + np.roll(seg, -1, axis=1))
            return seg.astype(np.float32)
        n = int(rng.integers(25, 80))
        t = np.arange(n) / n
        frames = np.full((n, 40), floor + 2.0, np.float32)
        bands = np.arange(40)[None, :]
        env = np.sin(np.pi * t) ** 0.6 * rng.uniform(0.7, 1.0)
        for _ in range(int(rng.integers(1, 4))):
            c0, c1 = rng.uniform(8, 34, 2)
            wob = rng.uniform(0, 3) * np.sin(2 * np.pi * rng.uniform(2, 7) * t + rng.uniform(0, 6))
            centre = (c0 + (c1 - c0) * t + wob)[:, None]
            frames = np.logaddexp(frames, (floor + 14.0 * env[:, None]) - 0.5 * ((bands - centre) / rng.uniform(0.8, 2.0)) ** 2)
        return frames.astype(np.float32)

    def step(self, meta: dict[str, Any], arrays: dict[str, np.ndarray]) -> dict[str, Any]:
        self.t += 1
        if meta.get("mode") != self.mode:  # another way of attending: the drive to call begins low (it listens first)
            self.drive = min(self.drive, 0.3)
        self.mode = meta.get("mode")
        if meta.get("own_voice"):  # the page is playing its voice (an answer said with a kept sound): what the ear hears at that moment is its own
            self.saying = max(self.saying, OWN_TAIL)
        left, right = arrays["left"], arrays["right"]
        proprio = arrays.get("proprio", np.zeros(22, np.float32))
        L = left.reshape(self.h, self.w, 3)
        R = right.reshape(self.h, self.w, 3)
        floor = math.log(1e-6)
        mel = arrays.get("mel")
        frames = mel.reshape(-1, 40) if mel is not None and mel.size % 40 == 0 and mel.size else np.full((10, 40), floor, np.float32)
        pcm = arrays.get("pcm")
        chunks = pcm.reshape(-1, 160) if pcm is not None and pcm.size == len(frames) * 160 else [None] * len(frames)
        self.heard = np.concatenate([self.heard, frames])[-800:]
        sl, sr = self._salience(L), self._salience(R)
        yaw = _value("head_yaw", float(proprio[0]))
        pitch = _value("head_pitch", float(proprio[1]))
        # the strongest spot in either eye, and where it lies from the beak (left of the beak positive)
        best = None
        for name, s in (("left", sl), ("right", sr)):
            k = int(np.argmax(s))
            row, col = divmod(k, self.w)
            if best is None or s[row, col] > best[0]:
                side = 1.0 if name == "left" else -1.0
                az_head = side * (self.axis - self.az[col])  # 0 at the beak, + to the parrot's left
                best = (float(s[row, col]), name, row, col, math.degrees(az_head), math.degrees(self.el[row]), s)
        strength, eye, row, col, az, el, smap = best
        # How a parrot looks: the head still, then a quick turn to something (a head saccade; the page
        # moves the joint there in about 0.2 s), a hold of one to three seconds, now and then a slow
        # tilt to look with one eye. The targets change only at a decision, never each moment.
        cue = meta.get("cue")
        if cue is not None:  # the visitor clicked a thing: the focus goes there at once
            self.target["head_yaw"] = float(np.clip(yaw + float(cue["az"]), -75.0, 75.0))
            self.target["head_pitch"] = float(np.clip(pitch + 0.8 * float(cue["el"]), -25.0, 35.0))
            self.focus = {"az": float(cue["az"]), "el": float(cue["el"]), "why": "you pointed at it"}
            self.hold_until = self.t + int(self.rng.integers(20, 31))
        elif self.t >= self.hold_until:
            if strength > 0.35 and self.rng.random() < 0.8:
                # bring the thing to the middle of the eye that sees it (a parrot looks with one eye)
                turn = az - math.copysign(55.0, az) if abs(az) > 55.0 else az * 0.5
                self.target["head_yaw"] = float(np.clip(yaw + turn, -75.0, 75.0))
                self.target["head_pitch"] = float(np.clip(pitch + 0.6 * el, -25.0, 35.0))
                self.focus = {"az": az, "el": el, "why": "it stood out most"}
            else:
                self.target["head_yaw"] = float(np.clip(yaw + self.rng.choice([-1, 1]) * self.rng.uniform(30, 70), -75.0, 75.0))
                self.target["head_pitch"] = float(self.rng.uniform(-15, 10))
                self.focus = None
            if self.rng.random() < 0.3:
                end = float(self.rng.choice([-1, 1]) * self.rng.uniform(10, 18))
                self.tilt = (self.target["head_roll"], end, self.t, int(self.rng.integers(10, 16)))
            elif self.target["head_roll"] != 0.0 and self.rng.random() < 0.5:
                self.tilt = (self.target["head_roll"], 0.0, self.t, 8)
            self.hold_until = self.t + int(self.rng.integers(10, 31))
        if self.tilt is not None:  # a slow tilt: the target eases over a second or so
            a, b, t0, n = self.tilt
            x = min(1.0, (self.t - t0) / n)
            self.target["head_roll"] = a + (b - a) * (x * x * (3 - 2 * x))
            if x >= 1.0:
                self.tilt = None
        mask = smap > 0.5 * strength
        apparent = float(mask.sum()) / (self.w * self.h) if strength > 0.35 else 0.0
        # the distance units: tuned to apparent size (log), silent when nothing is in view
        if apparent > 0 and "distance" not in self.silenced:
            dist_units = np.exp(-0.5 * ((np.log(apparent) - np.log(self.preferred)) / 0.35) ** 2).astype(np.float32)
        else:
            dist_units = np.zeros(DISTANCE_UNITS, np.float32)
        if dist_units.sum() > 0.05:
            # the stand-in's own reading of distance: a thing of about 8 cm that looks this large
            est = float(np.sum(dist_units * self.preferred) / dist_units.sum())
            width = math.sqrt(est * 4.0 * self.field * self.vfield)  # the angle it spans, radians
            readout = {"distance": round(float(np.clip(0.08 / (width + 1e-6), 0.05, 2.0)), 3), "eye": eye}
        else:
            readout = {"distance": None, "eye": eye}
        targets = np.full(len(JOINTS), np.nan, np.float32)
        targets[0] = _unit("head_yaw", self.target["head_yaw"])
        targets[1] = _unit("head_pitch", self.target["head_pitch"])
        targets[2] = _unit("head_roll", self.target["head_roll"])
        activity = np.zeros(self.neurons, np.float32)
        lum_l = (L.astype(np.float32).mean(axis=2) / 255.0).reshape(self.h // 2, 2, self.w // 2, 2).mean(axis=(1, 3))
        lum_r = (R.astype(np.float32).mean(axis=2) / 255.0).reshape(self.h // 2, 2, self.w // 2, 2).mean(axis=(1, 3))
        p = self.pop
        activity[p["retina_l"]["start"]:p["retina_l"]["start"] + p["retina_l"]["size"]] = lum_l.ravel()
        activity[p["retina_r"]["start"]:p["retina_r"]["start"] + p["retina_r"]["size"]] = lum_r.ravel()
        sal = np.concatenate([sl.reshape(self.h, 16, self.w // 16).max(axis=(0, 2)), sr.reshape(self.h, 16, self.w // 16).max(axis=(0, 2))])
        activity[p["salience"]["start"]:p["salience"]["start"] + 32] = np.clip(sal / 1.2, 0, 1)
        activity[p["distance"]["start"]:p["distance"]["start"] + DISTANCE_UNITS] = dist_units
        activity[p["motor"]["start"]:p["motor"]["start"] + len(JOINTS)] = np.nan_to_num((targets + 1) / 2, nan=0.5)
        # hearing: the ear follows the bands, Field L their change, NCM holds what was heard
        last = frames[-1]
        ear = np.clip((last - floor) / 18.0, 0, 1)
        change = np.clip(np.abs(frames[-1] - frames[0]) / 6.0, 0, 1)
        self.held = (0.85 * self.held + 0.15 * ear).astype(np.float32)
        # sounds the visitor makes: onset to offset, from the frames' total energy (not while it calls)
        learned, ended, startle = None, False, False
        heard_list = []  # every sound heard this moment, in order (a long moment can end several)
        spotted = []     # the words that became known this moment, in the utterance being heard
        for f, chunk in zip(frames, chunks):
            e = float(np.log(np.exp(f.astype(np.float64)).sum()))
            # a sudden sound: a loud onset after quiet that the ear's running level did not predict
            if self.saying <= 0 and e - self.running > 5.0 and self.quiet_for > 30 and self.t - self.startled > 20:
                startle = True; self.startled = self.t
            self.quiet_for = self.quiet_for + 1 if e < self.running + 2.0 else 0
            self.running += 0.05 * (e - self.running)
            # the background's level: a low percentile of the last three seconds' frames
            self.levels[self.level_at % len(self.levels)] = e; self.level_at += 1
            seen = self.levels[: min(self.level_at, len(self.levels))]
            self.floor = float(np.percentile(seen, 10)) if len(seen) >= 20 else max(self.floor, e)
            if e < self.floor + STAY:
                self.noise = np.logaddexp(self.noise + math.log(0.97), f.astype(np.float64) + math.log(0.03))
            loud = e > self.floor + (STAY if self.sound else ONSET)
            self.since_loud = 0 if loud else self.since_loud + 1
            if loud and self.saying > 0:
                self.spoiled = True  # the visitor spoke while the parrot was making a sound
            elif self.since_loud >= 25 and not self.sound:
                self.spoiled = False
            if loud and self.saying <= 0:
                if not self.sound:
                    self.sound = list(self.pre)  # the word's soft start, heard just before its onset
                    self.sound_pcm = list(self.pre_pcm)
                    self.follower.start()
                    self.gap = 0
                    for g in self.sound:
                        self.follower.frame(self.clean(g[None, :])[0])
                self.gap = max(self.gap, self.quiet)  # the longest quiet inside the utterance so far
                self.sound.append(f); self.sound_pcm.append(chunk); self.quiet = 0
                spotted += self._named(self.follower.frame(self.clean(f[None, :])[0]))
                if len(self.sound) > VALUE_FRAMES + 100:  # a sound that never ends is the background
                    self.sound = []; self.sound_pcm = []
                    self.noise = f.astype(np.float64).copy()
            elif self.sound:
                # the quiet inside a word (the closure of a p, a t) belongs to it; the word ends after
                # a quarter second of quiet, keeping its last 60 ms (its soft end)
                self.sound.append(f); self.sound_pcm.append(chunk); self.quiet += 1
                if self.quiet <= 8:
                    spotted += self._named(self.follower.frame(self.clean(f[None, :])[0]))
                if self.quiet >= END_QUIET:
                    keep = len(self.sound) - self.quiet + 6
                    heard = np.asarray(self.sound[:keep], np.float32)
                    parts = self.sound_pcm[:keep]
                    heard_pcm = np.concatenate(parts) if parts and all(c is not None for c in parts) else None
                    ok, why = self.voice_like(heard, heard_pcm)
                    got = None
                    if ok and not self.spoiled:  # a fragment heard over its own voice is not learned
                        got = self.hear_sound(heard, heard_pcm)
                        learned = got or learned
                        if got:
                            heard_list.append(got)
                            if self.mode == "listen":  # it says back what it heard
                                self.echo = (got["slot"], self.t + 1)
                        ended = True
                    e_h = np.log(np.exp(heard.astype(np.float64)).sum(axis=1))
                    self.events = (self.events + [{"t": self.t, "frames": len(heard), "loud": int(np.sum(e_h > self.floor + STAY)), "kind": why, "gap": int(self.gap), "start": int(self.level_at - len(self.sound)),
                                                   "spoiled": bool(self.spoiled), "audio": 0 if heard_pcm is None else int(len(heard_pcm)),
                                                   "kept": got is not None, "write": None if got is None else self.heard_event["write"]}])[-40:]
                    self.sound = []; self.sound_pcm = []; self.quiet = 0; self.spoiled = False
            self.pre = (self.pre + [f])[-8:]
            self.pre_pcm = (self.pre_pcm + [chunk])[-8:]
        self.mem.moment()
        self.focus_kind = meta.get("focus_kind")
        # the drive to call: quiet time (about a call every two to six seconds), more when a new
        # thing appears or the visitor has just spoken; a call spends it; never over its own sound
        count = meta.get("things")
        if count is not None and self.things is not None and count > self.things:
            self.drive += 0.45
        self.things = count if count is not None else self.things
        # (in "curious" it listens for questions: the drive rises at half the pace, a word by itself every eight seconds or so)
        self.drive += (0.5 if self.mode == "curious" else 1.0) * float(self.rng.uniform(0.012, 0.04)) + (0.4 if ended and self.mode != "curious" else 0.0)
        if self.mode == "listen" or (self.mode == "curious" and (ended or self.sound)):
            self.drive = min(self.drive, 0.5)  # while it listens to the visitor (and for a few seconds after a sound) it says nothing by itself
        self.drive = min(self.drive, 1.5)
        reward = float(meta.get("reward") or 0.0)
        linked = None
        if reward > 0 and self.exchange is not None:  # a pistachio for its answer
            linked = self.reward_exchange(PISTACHIO * reward)
        elif reward > 0 and self.last_said and self.t - self.last_said[1] < 80:
            self.paid[self.last_said[0]] = self.paid.get(self.last_said[0], 0.0) + reward
            # a word it said by itself with a thing in focus: the sound and the thing's word are linked
            if self.last_said[0].startswith("you-") and self.last_said[2] in self.words and not self.last_said[3]:
                slot = int(self.last_said[0][4:])
                self.mem.reward(slot, self.last_said[2], PISTACHIO * reward)
                linked = {"slot": slot, "meaning": self.last_said[2], "guessed": False, "link": self.mem.word_of(slot)[1], "answers": []}
            self.unpaid = None
            self.last_said = None
        if self.unpaid and self.t - self.unpaid[2] >= 80:  # the word the thing recalled, said, and no pistachio came
            self.mem.fade(self.unpaid[0], self.unpaid[1])
            self.unpaid = None
        if self.exchange is not None and self.t - self.exchange["t"] >= 150:  # an answer no pistachio followed
            self.close_exchange()
        voice, call = None, None
        free = meta.get("voice_ok") and self.saying <= 0 and not self.sound
        if self.echo and (self.mode != "listen" or self.t - self.echo[1] > 30):
            self.echo = None
        if free and self.echo and self.t >= self.echo[1] and self.echo[0] < self.mem.records.count:
            slot, self.echo = self.echo[0], None
            pick = {"id": f"you-{slot}", "tag": "said back", "source": "you", "slot": slot, "frames": self.mem.frames_of(slot)}
            voice = self.say(pick)
            call = {"id": pick["id"], "tag": pick["tag"], "source": "you", "echo": True, "word": self.mem.word_of(slot)[0]}
            self.last_said = (pick["id"], self.t, self.focus_kind, True)
            self.saying = int(math.ceil(len(voice) / 10)) + 2
            call["match"] = round(self.last_match or 0.0, 3)
            self.last_match = None
        elif free and self.mode != "listen" and self.drive >= 1.0 and not meta.get("hold"):
            pick = self.choose()
            voice = self.say(pick)
            call = {"id": pick["id"], "tag": pick["tag"], "source": pick["source"]}
            if pick.get("source") == "you":
                call["word"] = self.mem.word_of(pick["slot"])[0]
                if self.recalled and self.recalled["slot"] == pick["slot"]:
                    self.unpaid = (pick["slot"], self.recalled["kind"], self.t)
            self.last_said = (pick["id"], self.t, self.focus_kind, False)
            self.saying = int(math.ceil(len(voice) / 10)) + 2
            # saying relaxes its boredom, a word said well the most
            relief = 0.4 + 0.5 * (self.last_match or 0.0) if pick.get("source") == "you" else 0.6
            self.drive = max(0.0, self.drive - relief - 0.2)
            call["match"] = None if pick.get("source") != "you" else round(self.last_match or 0.0, 3)
            self.last_match = None
        said = np.zeros(40, np.float32)
        if self.saying > 0:
            self.saying -= 1
            said = np.clip(self.rng.random(40).astype(np.float32) * 0.6, 0, 1) if self.saying > 1 else said
        activity[p["ear"]["start"]:p["ear"]["start"] + 40] = ear
        activity[p["fieldl"]["start"]:p["fieldl"]["start"] + 40] = change * ear
        activity[p["ncm"]["start"]:p["ncm"]["start"] + 40] = self.held
        activity[p["voice"]["start"]:p["voice"]["start"] + 40] = said
        self.buffers = {"activity": activity, "targets": targets}
        names = ["activity", "targets"]
        if voice is not None:
            self.buffers["voice"] = voice.ravel()
            if self.say_pcm is not None and len(self.say_pcm):
                self.buffers["voice_pcm"] = self.say_pcm
                names.append("voice_pcm")
                self.voice_rate = self.say_rate
            self.say_pcm = None
            names.append("voice")
        changed = self._repertoire_changed(learned, call)  # the sounds whose audio the page needs
        return {"buffers": names, "group_activity": {"distance": dist_units.tolist()}, "readout": readout,
                "looked": {"eye": eye, "row": row, "col": col, "strength": round(strength, 3)},
                "focus": self.focus, "heard": bool(ear.max() > 0.35), "newborn": True,
                "drive": round(min(1.0, self.drive), 3), "said": call, "saying": self.saying > 0, "heard_sound": learned, "heard_sounds": heard_list, "startle": startle,
                "spotted": spotted, "hearing": bool(self.sound) and not self.spoiled, "recalled": self.mem_recalled(), "voice_rate": getattr(self, "voice_rate", 8000), "knows": self.knows(),
                "words": len(self.mem.sayable()),
                "memory": self._view(learned is not None or linked is not None),
                "repertoire": None if changed is None else self.repertoire_list(changed), "sayable": None if changed is None else [f"you-{s}" for s in self._sayable_sig],
                "paid": {k: round(v, 2) for k, v in self.paid.items() if v}, "linked": linked}

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        cmd = message.get("command")
        if cmd == "describe":
            return self.describe()
        if cmd == "reset":
            return self.reset()
        if cmd == "silence":
            return self.silence(str(message.get("group")), bool(message.get("on")))
        if cmd == "remember":
            return self.remember(message.get("saved") or {})
        if cmd == "memory":
            return {"memory": self.mem.view(), "saved": self.mem.save()}
        if cmd == "forget":
            return self.forget()
        if cmd == "debug":
            r = self.mem.records
            return {"floor": self.floor, "events": self.events, "records": [{"slot": s, "heard": int(self.mem.heard[s]), "deep": float(r.deep[s]),
                    "frames": self.mem.frames_of(s).round(2).tolist(), "audio": self.mem.pcm_of(s).round(4).tolist()} for s in range(r.count)]}
        if cmd == "repertoire":
            return {"repertoire": self.repertoire_list()}
        if cmd == "sound":  # one kept sound's audio (8 kHz), for a word the page links to it
            slot = int(message.get("slot", -1))
            if not 0 <= slot < self.mem.records.count:
                return {"pcm": [], "rate": 8000}
            return {"pcm": np.round(self.mem.pcm_of(slot), 4).tolist(), "rate": 8000}
        raise ValueError(f"unknown command {cmd!r}")
