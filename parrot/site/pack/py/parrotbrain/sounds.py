"""What the parrot remembers of what it hears, in the library's own memories.

Every voice-like sound the parrot hears (the host's noise filter keeps out hiss, clicks and hums
and takes the background's spectrum out) is told to two stores of the Cadence library:

- **Records** (`cadence.LongTermMemory`): the key is the sound's code (its frames resampled to 24
  and less their mean level, at unit length), the value its frames at their own timing (up to 1.6 s,
  with its length) for the voice. A sound told again (a write whose key a record holds at cosine `revise`
  or above) rewrites that record in place and deepens it; deep records fade far more slowly and are
  replaced last; a record told once and never again fades. The record's depth is the sound's
  strength: a sound whose record is deep enough is one the parrot can say back. No count of its own
  is kept here: depth and fading are the library's.
- **Synapses** (`cadence.SynapticMemory`): the sound's code as the key and a word as the value (one
  unit per word the parrot's brain knows: things, colours, shapes, directions, yes and no, the
  question words). This is the sound-to-word link: a heard sound reads its record, the record's key
  reads the synapses, and the strongest unit is the word the sound stands for. Read backwards (from
  a word to the records), it gives the sound to say for a word. A link is taught with a lesson
  (`link`): a pistachio after the visitor says a word with a thing in focus, or the starting words'
  teaching. Repetition accumulates in the slow, consolidated matrix (the library's rule).

A word told again must get cleaner with every hearing: the new take is first lined up with the
record frame by frame (the best path between them in time), then the record moves to the running mean
of its hearings. The library's revision takes the newest take whole; its `blend` option (the memory lane,
#336) does the running mean. Until it lands, `_blend_running_mean` below does it here, in one place.

**Pronunciation by practice** (the songbird's way: an auditory template and practice by hearing
itself). Each word the parrot can say has a motor program of its own, which starts immature: the
remembered word blurred in time and pitch, so it comes out mumbled but recognisable. Each attempt the
voice says what the program holds; the parrot's own ear hears the attempt; the program moves toward the
remembered word by the error, so the mumble sharpens attempt by attempt. Nothing random is added: what
the parrot says is always its own memory of the word, more or less precisely said.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from cadence import LongTermMemory, SynapticMemory

CODE_FRAMES = 16
VALUE_FRAMES = 160  # the longest word kept at its own timing (1.6 s); a longer one is squeezed to fit
SILENT = float(np.log(1e-6))
PCM_RATE = 8000                  # the heard audio itself, kept at 8 kHz (a telephone's clarity)
PCM_MAX = VALUE_FRAMES * 80      # 1.6 s of it
FRAMES_WIDTH = VALUE_FRAMES * 40 + 1
BANDS = 40
KINDS = ["apple", "ball", "cup", "banana", "block", "duck", "lemon", "pear"]  # the words of a brain that knows only things
LINKED = 0.3  # a record whose strongest link reaches this stands for that word


def resample(frames: np.ndarray, n: int) -> np.ndarray:
    idx = np.linspace(0, len(frames) - 1, n)
    lo = np.floor(idx).astype(int)
    hi = np.minimum(lo + 1, len(frames) - 1)
    w = (idx - lo)[:, None]
    return frames[lo] * (1 - w) + frames[hi] * w


RANGE = 8.0  # nats below each frame's loudest band that a code keeps (the quieter bands are the room's)
SMOOTH = np.array([1.0, 2.0, 3.0, 2.0, 1.0]) / 9.0  # across neighbouring bands: a voice a semitone higher reads alike


def to_pcm8k(pcm: np.ndarray | None) -> np.ndarray:
    """The heard 16 kHz samples at 8 kHz (each pair averaged), at most 1.6 s."""
    if pcm is None or len(pcm) < 2:
        return np.zeros(0)
    x = np.asarray(pcm, np.float64)
    x = x[: len(x) // 2 * 2].reshape(-1, 2).mean(axis=1)
    return x[:PCM_MAX]


def pack(frames: np.ndarray, pcm8k: np.ndarray | None = None) -> np.ndarray:
    """A record's value: the frames at their own timing (squeezed only past 1.6 s), padded with
    silence, and their count; then the heard audio itself (8 kHz) and its length."""
    f = frames.astype(np.float64)
    if len(f) > VALUE_FRAMES:
        f = resample(f, VALUE_FRAMES)
    out = np.full((VALUE_FRAMES, BANDS), SILENT)
    out[: len(f)] = f
    a = np.zeros(PCM_MAX)
    n = 0 if pcm8k is None else min(len(pcm8k), PCM_MAX)
    if n:
        a[:n] = pcm8k[:n]
    return np.concatenate([out.ravel(), [len(f)], a, [n]])


def unpack(v: np.ndarray) -> np.ndarray:
    n = int(min(VALUE_FRAMES, max(2, round(float(v[FRAMES_WIDTH - 1])))))
    return v[: FRAMES_WIDTH - 1].reshape(VALUE_FRAMES, BANDS)[:n].copy()


def unpack_pcm(v: np.ndarray) -> np.ndarray:
    n = int(round(float(v[-1])))
    return v[FRAMES_WIDTH: FRAMES_WIDTH + n].copy()


def blur(f: np.ndarray, passes: int) -> np.ndarray:
    """Smoothing across neighbouring frames and bands: a mumbled version of the same sound."""
    g = f.astype(np.float64).copy()
    for _ in range(passes):
        g = 0.5 * g + 0.25 * (np.roll(g, 1, axis=1) + np.roll(g, -1, axis=1))
        g[:, 0], g[:, -1] = f[:, 0], f[:, -1]
        h = g.copy()
        h[1:-1] = 0.5 * g[1:-1] + 0.25 * (g[:-2] + g[2:])
        g = h
    return g


def align(take: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """The take laid on the reference's timeline: the cheapest path between them (dynamic time
    warping on the frames' distance), each reference frame given the mean of the take's frames the
    path pairs with it. A take said faster or slower lines up sound for sound."""
    a, b = ref.astype(np.float64), take.astype(np.float64)
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).mean(axis=2))
    n, m = d.shape
    c = np.full((n + 1, m + 1), np.inf); c[0, 0] = 0.0
    for i in range(1, n + 1):
        row, prev = c[i], c[i - 1]
        for j in range(1, m + 1):
            row[j] = d[i - 1, j - 1] + min(prev[j - 1], prev[j], row[j - 1])
    i, j, pairs = n, m, []
    while i > 0 and j > 0:
        pairs.append((i - 1, j - 1))
        k = int(np.argmin([c[i - 1, j - 1], c[i - 1, j], c[i, j - 1]]))
        i, j = (i - 1, j - 1) if k == 0 else (i - 1, j) if k == 1 else (i, j - 1)
    out, cnt = np.zeros_like(a), np.zeros(n)
    for i, j in pairs:
        out[i] += b[j]; cnt[i] += 1
    return out / np.maximum(cnt, 1)[:, None]


SAME_WORD = 0.22  # the time-aligned distance (relative to the words' own spread) under which a take is a word the parrot knows: one voice's takes of a word read 0.14 at most, other words 0.25 at least


def shape(frames: np.ndarray) -> np.ndarray:
    """What makes a word that word: its loud core, each band within RANGE of the frame's loudest, less
    each band's mean over the word (the voice's and the room's average colour out, its changes kept)."""
    f = frames.astype(np.float64)
    e = np.log(np.exp(f).sum(axis=1))
    on = np.flatnonzero(e > e.max() - 6.0)
    if len(on) >= 2:
        f = f[on[0]: on[-1] + 1]
    f = np.maximum(f, f.max(axis=1, keepdims=True) - RANGE)
    f = f - f.mean(axis=0, keepdims=True)
    k = np.ones(3) / 3.0  # neighbouring bands read alike: a word said a little higher is the same word
    return np.stack([np.convolve(np.pad(row, 1, mode="edge"), k, "valid") for row in f])


def distance(a: np.ndarray, b: np.ndarray) -> float:
    """How far two takes are once lined up sound for sound (dynamic time warping over their shapes),
    relative to how much the words themselves vary: a take said faster, slower or louder is near its
    word; another word is far."""
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).mean(axis=2))
    n, m = d.shape
    c = np.full((n + 1, m + 1), np.inf); c[0, 0] = 0.0
    for i in range(1, n + 1):
        row, prev, di = c[i], c[i - 1], d[i - 1]
        for j in range(1, m + 1):
            row[j] = di[j - 1] + min(prev[j - 1], prev[j], row[j - 1])
    spread = 0.5 * (float(np.sqrt((a ** 2).mean())) + float(np.sqrt((b ** 2).mean())))
    return float(c[n, m] / (n + m)) / max(spread, 1e-9)


N_FFT, HOP_A = 256, 64  # the audio's spectra: 32 ms windows every 8 ms at 8 kHz


def _stft(x: np.ndarray) -> np.ndarray:
    w = np.hanning(N_FFT)
    x = np.pad(x.astype(np.float64), (N_FFT // 2, N_FFT // 2))
    n = 1 + max(0, (len(x) - N_FFT) // HOP_A)
    idx = np.arange(N_FFT)[None, :] + HOP_A * np.arange(n)[:, None]
    return np.fft.rfft(x[idx] * w, axis=1)


def _istft(spec: np.ndarray, length: int) -> np.ndarray:
    w = np.hanning(N_FFT)
    frames = np.fft.irfft(spec, n=N_FFT, axis=1) * w
    out = np.zeros(HOP_A * (len(frames) - 1) + N_FFT); norm = np.zeros_like(out)
    for i, f in enumerate(frames):
        out[i * HOP_A: i * HOP_A + N_FFT] += f; norm[i * HOP_A: i * HOP_A + N_FFT] += w * w
    out = out / np.maximum(norm, 1e-6)
    return out[N_FFT // 2: N_FFT // 2 + length]


def blend_audio(kept: np.ndarray, take: np.ndarray, n: int) -> np.ndarray:
    """The word's sound told again: the new take lined up with the kept sound (time warping on their
    spectra), the spectra mixed as a running mean (the new take weighs 1/n), and the sound made anew
    with the kept sound's timing and phase, refined over a few passes so it stays one voice. Each
    hearing moves the kept sound a little toward the new take: a mix of the versions it heard."""
    if not len(kept) or not len(take):
        return kept if len(kept) else take
    A, B = _stft(kept), _stft(take)
    la, lb = np.log(np.abs(A) + 1e-6), np.log(np.abs(B) + 1e-6)
    la_c, lb_c = la - la.mean(axis=0), lb - lb.mean(axis=0)
    d = np.sqrt(((la_c[:, None, :] - lb_c[None, :, :]) ** 2).mean(axis=2))
    na, nb = d.shape
    c = np.full((na + 1, nb + 1), np.inf); c[0, 0] = 0.0
    for i in range(1, na + 1):
        row, prev, di = c[i], c[i - 1], d[i - 1]
        for j in range(1, nb + 1):
            row[j] = di[j - 1] + min(prev[j - 1], prev[j], row[j - 1])
    i, j, pairs = na, nb, []
    while i > 0 and j > 0:
        pairs.append((i - 1, j - 1))
        k = int(np.argmin([c[i - 1, j - 1], c[i - 1, j], c[i, j - 1]]))
        i, j = (i - 1, j - 1) if k == 0 else (i - 1, j) if k == 1 else (i, j - 1)
    mb, cnt = np.zeros(A.shape), np.zeros(na)
    for i, j in pairs:
        mb[i] += np.abs(B[j]); cnt[i] += 1
    mb /= np.maximum(cnt, 1)[:, None]
    mb *= np.sqrt((np.abs(A) ** 2).sum() / max(float((mb ** 2).sum()), 1e-12))  # at the kept sound's loudness
    mag = np.abs(A) + (mb - np.abs(A)) / max(n, 1)
    spec = mag * np.exp(1j * np.angle(A))
    y = _istft(spec, len(kept))
    for _ in range(4):  # a few passes so the phases agree with the mixed spectra
        spec = mag * np.exp(1j * np.angle(_stft(y)[: len(mag)]))
        y = _istft(spec, len(kept))
    peak = max(float(np.abs(y).max()), 1e-9)
    return (y * min(1.0, float(np.abs(kept).max()) / peak)).astype(np.float64)


def code(frames: np.ndarray) -> np.ndarray:
    """A sound's key: each band kept within RANGE of its frame's loudest (what lies below is the
    room's noise, not the word), smoothed across neighbouring bands and frames (so a take a little
    higher, faster or louder reads alike), resampled to 16 frames, less its mean level, at unit
    length. Takes of one word read a cosine of 0.76 to 0.98 (mean 0.92) with tempo +-15 %, pitch
    +-1 semitone, level +-6 dB and room noise; another word reads 0.31 at most (tests/test_words.py)."""
    f = frames.astype(np.float64)
    e = np.log(np.exp(f).sum(axis=1))  # the word's loud core: its soft start and end are kept for the voice, not the key
    on = np.flatnonzero(e > e.max() - 6.0)
    if len(on) >= 2:
        f = f[on[0]: on[-1] + 1]
    f = np.maximum(f, f.max(axis=1, keepdims=True) - RANGE)
    f = np.stack([np.convolve(np.pad(row, 2, mode="edge"), SMOOTH, "valid") for row in f])
    r = resample(f, CODE_FRAMES)
    r = 0.25 * np.roll(r, 1, axis=0) + 0.5 * r + 0.25 * np.roll(r, -1, axis=0)
    r = r - r.mean()
    n = float(np.linalg.norm(r))
    return (r / n if n > 0 else r).ravel()


class SoundMemory:
    LEVEL = 2.5  # a record this deep is a sound the parrot can say back

    def __init__(self, revise: float = 0.85, capacity: int = 128, words: list[str] | None = None):
        self.words = list(words or KINDS)
        # a write is the record "told again" only with that record's own key: the parrot decides that a
        # take is a word it knows by lining it up against the words it has (`same_word`)
        self.records = LongTermMemory(width=CODE_FRAMES * BANDS, value_width=FRAMES_WIDTH + PCM_MAX + 1, capacity=capacity,
                                      cosine=True, revise=0.9999, temperature=0.08, candidates=0,
                                      hold=36000.0, idle=40.0, depth=2.0)
        self.synapses = SynapticMemory(pre=np.arange(CODE_FRAMES * BANDS), post=np.arange(len(self.words)), rule="delta",
                                       decay=0.9, consolidation=0.05)
        self.synapses.reset(1)
        self.last_read: dict[str, Any] | None = None
        self.last_write: dict[str, Any] | None = None
        self.heard = np.zeros(capacity, int)        # hearings a record holds (the running mean's weight)
        self.programs: dict[int, dict[str, Any]] = {}  # each word's motor program and its attempts
        self.last_distance: float | None = None
        self.typical = np.full(capacity, -1.0)  # how typical the kept take of each record is (its code's cosine with the record's key)
        self.rng = np.random.default_rng(31)

    def hear(self, frames: np.ndarray, pcm: np.ndarray | None = None) -> dict[str, Any]:
        """Tell the stores a heard sound: read with its code (the attention over the records), then
        write it (a new record, or one told again). The word it stands for is its record's link
        (`word_of`)."""
        key = code(frames)
        read = self.records.read(key)
        self.last_read = {"slots": read.slots.tolist(), "weights": np.round(read.weights[0], 4).tolist(),
                          "cue": self.thumb(key)} if len(read.slots) else {"slots": [], "weights": [], "cue": self.thumb(key)}
        cos, before = None, {}
        if self.records.count:
            k = self.records.keys[: self.records.count]
            sims = k @ key / np.maximum(np.linalg.norm(k, axis=1), 1e-12)
            cos = float(np.max(sims))
            # the record this word would revise, as it stands before the write replaces it
            before = {int(np.argmax(sims)): self.records.values[int(np.argmax(sims))].copy()}
        take = to_pcm8k(pcm)
        value = pack(frames, take)
        known, self.last_distance = self.same_word(frames, key)
        slot, revised = self.records.write(self.records.keys[known].copy() if known is not None else key, value)
        if not revised:
            self.heard[slot] = 0
            self.programs.pop(slot, None)
            self.typical[slot] = -1.0
        self._blend_running_mean(slot, frames, revised, before.get(int(slot)))
        self._mix_audio(slot, take, revised, before.get(int(slot)))
        self.last_write = {"slot": int(slot), "revised": bool(revised), "best_cosine": None if cos is None else round(cos, 3), "distance": self.last_distance,
                           "heard": int(self.heard[slot])}
        return {"read": self.last_read, "write": self.last_write}

    def _blend_running_mean(self, slot: int, frames: np.ndarray, revised: bool, previous: np.ndarray | None) -> None:
        """STAND-IN for the library's `blend` option (#336): the record told again moves to the running
        mean of its hearings, so the stored form gets cleaner with every repetition. The library's
        write took the newest take whole; this replaces the slot's value and key with the mean."""
        r = self.records
        n = int(self.heard[slot]) + 1
        self.heard[slot] = n
        if not revised or n == 1 or previous is None:
            return
        old = unpack(previous)  # the mean so far (the write put the newest take in its place)
        new = align(frames, old)
        mean = old + (new - old) / n
        r.values[slot] = pack(mean, unpack_pcm(r.values[slot]))
        key = code(self.frames_of_value(r.values[slot]))
        r.keys[slot] = key
        if r.cosine:
            r.norms[slot] = float(np.linalg.norm(key))

    def _mix_audio(self, slot: int, take: np.ndarray, revised: bool, previous: np.ndarray | None) -> None:
        """The record's sound: a first hearing keeps its take; a word told again keeps a mix of the
        sound it had and the new take (`blend_audio`), so it never repeats one recording exactly."""
        if not revised or previous is None:
            return
        kept = unpack_pcm(previous)
        mixed = blend_audio(kept, take, int(self.heard[slot])) if len(take) else kept
        self.records.values[slot] = pack(unpack(self.records.values[slot]), mixed)

    def _keep_typical_take(self, slot: int, frames: np.ndarray, take: np.ndarray, previous: np.ndarray | None) -> None:
        """The audio the record keeps: of all takes heard, the one most like the record (its code
        nearest the record's key), so the word it says back is a real, clear take of it."""
        r = self.records
        score = float(code(frames) @ r.keys[slot]) / max(float(np.linalg.norm(r.keys[slot])), 1e-12)
        if len(take) and score >= self.typical[slot]:
            self.typical[slot] = score
            return  # the write holds this take's audio
        if previous is not None and len(unpack_pcm(previous)):
            r.values[slot] = pack(unpack(r.values[slot]), unpack_pcm(previous))  # the earlier, more typical take stays

    def same_word(self, frames: np.ndarray, key: np.ndarray) -> tuple[int | None, float | None]:
        """The word the parrot knows that this take is, if any: of the records whose keys are nearest
        (up to six), the one nearest once lined up in time, if under SAME_WORD."""
        r = self.records
        if not r.count:
            return None, None
        k = r.keys[: r.count]
        near = np.argsort(-(k @ key) / np.maximum(np.linalg.norm(k, axis=1), 1e-12))[:6]
        mine = shape(frames)
        best, bd = None, np.inf
        for s in near:
            d = distance(mine, shape(self.template(int(s))))
            if d < bd:
                best, bd = int(s), d
        return (best if bd < SAME_WORD else None), round(float(bd), 3)

    def reads(self) -> np.ndarray:
        """Every record's key read through the synapses (the links read forwards): records x words."""
        n = self.records.count
        if not n:
            return np.zeros((0, len(self.words)))
        k = self.records.keys[:n].astype(np.float64)
        return (k / np.maximum(np.linalg.norm(k, axis=1, keepdims=True), 1e-12)) @ self.synapses.strength[0]

    def word_of(self, slot: int, reads: np.ndarray | None = None) -> tuple[str | None, float]:
        """The word a record stands for: the strongest word unit its key reads, if it reaches LINKED."""
        if not 0 <= slot < self.records.count:
            return None, 0.0
        v = (self.reads() if reads is None else reads)[slot]
        j = int(np.argmax(v))
        return (self.words[j] if v[j] >= LINKED else None), round(float(v[j]), 3)

    def recall(self, word: str | None, reads: np.ndarray | None = None) -> tuple[int | None, float]:
        """The word recalls its sound (the link read backwards, from the word to the records): of the
        records it can say whose sound stands for this word, the one heard most (the deepest)."""
        if word not in self.words:
            return None, 0.0
        r = self.reads() if reads is None else reads
        best, top = None, (-1.0, 0.0)
        for s in self.sayable():
            w, link = self.word_of(s, r)
            if w == word and (float(self.records.deep[s]), link) > top:
                best, top = s, (float(self.records.deep[s]), link)
        return best, top[1]

    def link(self, slot: int, word: str | None, amount: float = 1.0) -> None:
        """A lesson: the record's sound and the word linked (one delta step of the synapses from the
        sound's code to the word's unit, as large as the lesson's amount)."""
        if word not in self.words or not 0 <= slot < self.records.count:
            return
        k = self.records.keys[slot].astype(np.float64)
        onehot = np.zeros(len(self.words)); onehot[self.words.index(word)] = 1.0
        self.synapses.observe((k / max(float(np.linalg.norm(k)), 1e-12))[None, :], onehot[None, :], salience=np.array([max(0.0, amount)]))

    reward_link = link

    def pcm_of(self, slot: int) -> np.ndarray:
        """The word's audio as the record keeps it (8 kHz): what the parrot says back."""
        return unpack_pcm(self.records.values[slot]).astype(np.float32)

    def template(self, slot: int) -> np.ndarray:
        """The word as remembered: the record's frames at their own timing."""
        return unpack(self.records.values[slot])

    IMMATURE = 4   # blur passes of a first attempt: a little mumbled, still clearly the same word (6 and more lose it)
    RATE = 0.3     # the share of the heard error each attempt corrects

    def program(self, slot: int) -> dict[str, Any]:
        """The word's motor program: immature at first (the remembered word, blurred)."""
        t = self.template(slot)
        prog = self.programs.get(slot)
        if prog is None or prog["P"].shape != t.shape:
            prog = {"P": blur(t, self.IMMATURE), "matches": [] if prog is None else prog["matches"], "attempts": 0 if prog is None else prog["attempts"]}
            self.programs[slot] = prog
        return prog

    @staticmethod
    def match(a: np.ndarray, b: np.ndarray) -> float:
        """How well a said word agrees with the remembered one: the cosine of their frames (every band
        and frame, within RANGE of each frame's loudest, less the mean level), 0 to 1."""
        def fine(f: np.ndarray) -> np.ndarray:
            f = np.maximum(f.astype(np.float64), f.max(axis=1, keepdims=True) - RANGE)
            r = f - f.mean()
            return (r / max(float(np.linalg.norm(r)), 1e-12)).ravel()
        return float(max(0.0, fine(a) @ fine(b))) if a.shape == b.shape else 0.0

    def practice(self, slot: int) -> tuple[np.ndarray, float]:
        """One attempt at a word: the voice says what the program holds, the parrot's own ear hears
        it, and the program moves toward the remembered word by the error."""
        prog, t = self.program(slot), self.template(slot)
        said = prog["P"].copy()
        heard = said  # its own voice, through its own ear
        m = self.match(heard, t)
        prog["P"] = prog["P"] + self.RATE * (t - heard)
        prog["matches"].append(m)
        prog["attempts"] += 1
        return said.astype(np.float32), m

    def pronunciation(self, slot: int) -> np.ndarray:
        """What the parrot says for a word now: its program, at the word's own timing."""
        return self.program(slot)["P"].astype(np.float32)

    def moment(self) -> None:
        self.records.moment()

    def frames_of(self, slot: int) -> np.ndarray:
        return self.template(slot).astype(np.float32)

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
            prog = self.programs.get(s)
            rows.append({"slot": s, "deep": round(float(r.deep[s]), 3), "faded": round(float(r.faded[s]), 2), "heard": int(self.heard[s]),
                         "match": None if not prog or not prog["matches"] else round(prog["matches"][-1], 3),
                         "recent": round(float(r.recent[s]), 4), "thumb": self.thumb(r.keys[s]), "frames": int(round(r.values[s][-1])),
                         "slow": slow, "fast": fast})
        return {"records": rows, "things": self.words, "level": self.LEVEL, "revise": r.revise,
                "read": self.last_read, "write": self.last_write}

    def save(self) -> dict[str, Any]:
        r = self.records
        return {"records": [{"value": np.round(r.values[s], 4).tolist(), "deep": float(r.deep[s]), "heard": int(self.heard[s]), "typical": float(self.typical[s]),
                             "program": None if s not in self.programs else np.round(self.programs[s]["P"], 3).tolist(),
                             "matches": [] if s not in self.programs else [round(m, 3) for m in self.programs[s]["matches"][-20:]]} for s in range(r.count)],
                "words": self.words, "consolidated": np.round(self.synapses.consolidated, 5).tolist()}

    def load(self, saved: dict[str, Any]) -> None:
        for rec in saved.get("records", []):
            v = np.asarray(rec["value"], np.float64)
            if v.shape != (FRAMES_WIDTH + PCM_MAX + 1,):
                continue  # kept by an older page in another format
            frames = self.frames_of_value(v)
            slot, _ = self.records.write(code(frames), v)
            self.records.deep[slot] = float(rec.get("deep", 1.0))
            self.heard[slot] = int(rec.get("heard", 1))
            self.typical[slot] = float(rec.get("typical", -1.0))
            if rec.get("program") is not None:
                self.programs[slot] = {"P": np.asarray(rec["program"], np.float64).reshape(-1, BANDS),
                                       "matches": list(rec.get("matches", [])), "attempts": len(rec.get("matches", []))}
        c = saved.get("consolidated")
        if c is not None and saved.get("words", KINDS) == self.words and np.asarray(c).shape == self.synapses.consolidated.shape:
            self.synapses.consolidated = np.asarray(c, np.float64)
            self.synapses.reset(1)

    @staticmethod
    def frames_of_value(v: np.ndarray) -> np.ndarray:
        return unpack(v)

    def clear(self) -> None:
        self.__init__(self.records.revise, self.records.capacity, self.words)
