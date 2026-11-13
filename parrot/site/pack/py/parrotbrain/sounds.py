"""What the parrot remembers of what it hears, in the library's own memories.

Every voice-like sound the parrot hears (the host's noise filter keeps out hiss, clicks and hums
and takes the background's spectrum out) is told to two stores of the Cadence library:

- **Records** (`cadence.LongTermMemory`): the key is the sound's code (its frames resampled to 24
  and less their mean level, at unit length), the value its frames (resampled to 48, with its
  length) for the voice. A sound told again (a write whose key a record holds at cosine `revise`
  or above) rewrites that record in place and deepens it; deep records fade far more slowly and are
  replaced last; a record told once and never again fades. The record's depth is the sound's
  strength: a sound whose record is deep enough is one the parrot can say back. No count of its own
  is kept here: depth and fading are the library's.
- **Synapses** (`cadence.SynapticMemory`): the sound's code as the key and the thing the parrot is
  focused on as the value (one unit per kind of thing). Repetition accumulates in the slow,
  consolidated matrix (the library's rule), so "Apfel" said while it looks at the apple links the
  sound to the apple.

Two behaviours belong to the library, not here: a revision takes the newest take's key and value
(it does not average the takes), and a record's depth does not weigh the read. Options for both are
the library lane's to add; the page draws what the stores hold.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from cadence import LongTermMemory, SynapticMemory

CODE_FRAMES = 24
VALUE_FRAMES = 48
BANDS = 40
KINDS = ["apple", "ball", "cup", "banana", "block", "duck", "lemon", "pear"]


def resample(frames: np.ndarray, n: int) -> np.ndarray:
    idx = np.linspace(0, len(frames) - 1, n)
    lo = np.floor(idx).astype(int)
    hi = np.minimum(lo + 1, len(frames) - 1)
    w = (idx - lo)[:, None]
    return frames[lo] * (1 - w) + frames[hi] * w


def code(frames: np.ndarray) -> np.ndarray:
    """A sound's key: its frames at 24, less their mean level, at unit length."""
    r = resample(frames.astype(np.float64), CODE_FRAMES)
    r = r - r.mean()
    n = float(np.linalg.norm(r))
    return (r / n if n > 0 else r).ravel()


class SoundMemory:
    LEVEL = 2.5  # a record this deep is a sound the parrot can say back

    def __init__(self, revise: float = 0.85, capacity: int = 48):
        self.records = LongTermMemory(width=CODE_FRAMES * BANDS, value_width=VALUE_FRAMES * BANDS + 1, capacity=capacity,
                                      cosine=True, revise=revise, temperature=0.08, candidates=0,
                                      hold=36000.0, idle=40.0, depth=2.0)
        self.synapses = SynapticMemory(pre=np.arange(CODE_FRAMES * BANDS), post=np.arange(len(KINDS)), rule="delta",
                                       decay=0.9, consolidation=0.05)
        self.synapses.reset(1)
        self.last_read: dict[str, Any] | None = None
        self.last_write: dict[str, Any] | None = None

    def hear(self, frames: np.ndarray, focus_kind: str | None) -> dict[str, Any]:
        """Tell the stores a heard sound: read with its code (the attention over the records), then
        write it (a new record, or one told again), and link it to the focused thing."""
        key = code(frames)
        read = self.records.read(key)
        self.last_read = {"slots": read.slots.tolist(), "weights": np.round(read.weights[0], 4).tolist(),
                          "cue": self.thumb(key)} if len(read.slots) else {"slots": [], "weights": [], "cue": self.thumb(key)}
        cos = None
        if self.records.count:
            k = self.records.keys[: self.records.count]
            cos = float(np.max(k @ key / np.maximum(np.linalg.norm(k, axis=1), 1e-12)))
        value = np.concatenate([resample(frames.astype(np.float64), VALUE_FRAMES).ravel(), [len(frames)]])
        slot, revised = self.records.write(key, value)
        self.last_write = {"slot": int(slot), "revised": bool(revised), "best_cosine": None if cos is None else round(cos, 3)}
        if focus_kind in KINDS:
            onehot = np.zeros(len(KINDS)); onehot[KINDS.index(focus_kind)] = 1.0
            self.synapses.observe(key[None, :], onehot[None, :])
        return {"read": self.last_read, "write": self.last_write}

    def moment(self) -> None:
        self.records.moment()

    def frames_of(self, slot: int) -> np.ndarray:
        v = self.records.values[slot]
        n = max(2, int(round(v[-1])))
        return resample(v[:-1].reshape(VALUE_FRAMES, BANDS), n).astype(np.float32)

    def sayable(self) -> list[int]:
        return [s for s in range(self.records.count) if self.records.deep[s] >= self.LEVEL]

    @staticmethod
    def thumb(key: np.ndarray) -> list:
        """A small picture of a code: 24 frames by 20 bands, 0 to 255."""
        r = key.reshape(CODE_FRAMES, BANDS)
        r = 0.5 * (r[:, 0::2] + r[:, 1::2])
        lo, hi = float(r.min()), float(r.max())
        return np.round(255 * (r - lo) / max(hi - lo, 1e-9)).astype(int).ravel().tolist()

    def links(self, slot: int) -> tuple[list, list]:
        """The synapses' read of a record's code: the consolidated part and the fading residual."""
        key = self.records.keys[slot].astype(np.float64)
        n = float(np.linalg.norm(key))
        unit = key / n if n > 0 else key
        slow = unit @ self.synapses.consolidated
        fast = unit @ (self.synapses.strength[0] - self.synapses.consolidated)
        return np.round(slow, 4).tolist(), np.round(fast, 4).tolist()

    def view(self) -> dict[str, Any]:
        """What the page draws: every record (depth, how faded, recent use, its picture) and the
        synapses from each record's sound to each kind of thing."""
        r = self.records
        rows = []
        for s in range(r.count):
            slow, fast = self.links(s)
            rows.append({"slot": s, "deep": round(float(r.deep[s]), 3), "faded": round(float(r.faded[s]), 2),
                         "recent": round(float(r.recent[s]), 4), "thumb": self.thumb(r.keys[s]), "frames": int(round(r.values[s][-1])),
                         "slow": slow, "fast": fast})
        return {"records": rows, "things": KINDS, "level": self.LEVEL, "revise": r.revise,
                "read": self.last_read, "write": self.last_write}

    def save(self) -> dict[str, Any]:
        r = self.records
        return {"records": [{"value": np.round(r.values[s], 3).tolist(), "deep": float(r.deep[s])} for s in range(r.count)],
                "consolidated": np.round(self.synapses.consolidated, 5).tolist()}

    def load(self, saved: dict[str, Any]) -> None:
        for rec in saved.get("records", []):
            v = np.asarray(rec["value"], np.float64)
            frames = self.frames_of_value(v)
            slot, _ = self.records.write(code(frames), v)
            self.records.deep[slot] = float(rec.get("deep", 1.0))
        c = saved.get("consolidated")
        if c is not None and np.asarray(c).shape == self.synapses.consolidated.shape:
            self.synapses.consolidated = np.asarray(c, np.float64)
            self.synapses.reset(1)

    @staticmethod
    def frames_of_value(v: np.ndarray) -> np.ndarray:
        n = max(2, int(round(v[-1])))
        return resample(v[:-1].reshape(VALUE_FRAMES, BANDS), n)

    def clear(self) -> None:
        self.__init__(self.records.revise, self.records.capacity)
