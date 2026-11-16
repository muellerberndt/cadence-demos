"""What the parrot remembers of what it hears, in the library's own memories.

Every voice-like sound the parrot hears (the host's noise filter keeps out hiss, clicks and hums
and takes the background's spectrum out) is told to two stores of the Cadence library:

The ear's unit is the utterance: one word ("apple") or a whole spoken phrase ("what colour is this?"), from
its onset to the quiet after it. A phrase is kept whole, as a parrot takes it.

- **Records** (`cadence.LongTermMemory`): the key is the sound's code (its frames resampled to 24
  and less their mean level, at unit length), the value its frames at their own timing (up to 3 s,
  with its length) for the voice. A sound told again (a write whose key a record holds at cosine `revise`
  or above) rewrites that record in place and deepens it; deep records fade far more slowly and are
  replaced last; a record told once and never again fades. The record's depth is the sound's
  strength: a sound whose record is deep enough is one the parrot can say back. No count of its own
  is kept here: depth and fading are the library's.
- **Synapses** (`cadence.SynapticMemory`): the record's own address as the key (a fixed random direction
  of its slot, through the library's pattern separator: a record's links are its own, however alike two
  sounds are) and a meaning as the value (one
  unit per word the parrot's brain knows: things, colours, shapes, directions, yes and no, the
  question words; and one per question its brain was taught, a sequence of those words such as
  "what colour is this"). This is the sound-to-meaning link: a heard sound reads its record, the
  record's address reads the synapses, and the strongest unit is what the sound stands for. What a
  sound with no link of its own stands for is read from the records it lies nearest (`like`). Read backwards
  (from a word to the records), it gives the sound to say for a word. A link is taught with a lesson
  (`link`): the starting sounds' teaching, or a pistachio (below). Repetition accumulates in the slow,
  consolidated matrix (the library's rule).

**A meaning learned by reward.** A sound whose record reads no meaning strongly is guessed: among the
meanings on offer (the questions about the thing in focus), one is drawn by the links' strengths
(`guess`: flat while nothing is known), and the parrot answers by it. A pistachio links the sound to
the guessed meaning (`link`); no pistachio lowers that guess a little for a while (`doubt`), so the next
try looks elsewhere. A word with no sound of its own is said the same way (`guess_sound`). A link the
parrot used with no pistachio after it moves a little back to what repetition has consolidated
(`fade`): a link made by one lucky pistachio goes again, a link learned over many stays.

**Following a phrase as it is said.** A record can keep where each word of its meaning begins on its
own timeline (`marks`); the host lines the sound coming in up with such records frame by frame, so each
word is known as it is spoken (`host.Follower`).

A word told again must get cleaner with every hearing: the new take is first lined up with the
record frame by frame (the best path between them in time), then the library's record strength
(`LongTermMemory(blend=True)`, cadence 0.100, #336) moves the record toward it by one over one plus its
depth, so a record told n times holds the mean of its n takes.

**Pronunciation by practice** (the songbird's way: an auditory template and practice by hearing
itself). Each word the parrot can say has a motor program of its own, which starts immature: the
remembered word blurred in time and pitch, so it comes out mumbled but recognisable. Each attempt the
voice says what the program holds; the parrot's own ear hears the attempt; the program moves toward the
remembered word by the error, so the mumble sharpens attempt by attempt. Nothing random is added: what
the parrot says is always its own memory of the word, more or less precisely said.
"""
from __future__ import annotations

import base64
from typing import Any

import numpy as np

from cadence import LongTermMemory, PatternSeparator, SynapticMemory
from cadence.senses import Ear

CODE_FRAMES = 16
VALUE_FRAMES = 300  # the longest utterance kept at its own timing (3 s: a word or a whole spoken phrase); a longer one is squeezed to fit
SILENT = float(np.log(1e-6))
PCM_RATE = 8000                  # the heard audio itself, kept at 8 kHz (a telephone's clarity)
PCM_MAX = VALUE_FRAMES * 80      # 3 s of it
FRAMES_WIDTH = VALUE_FRAMES * 40 + 1
FRAME_LOW, FRAME_STEP = -14.0, 0.1  # a saved frame's bands as bytes: from -14 nats (the ear's floor) in steps of 0.1
BANDS = 40
KINDS = ["apple", "ball", "cup", "banana", "block", "duck", "lemon", "pear"]  # the words of a brain that knows only things
LINKED = 0.3  # a record whose strongest link reaches this stands for that meaning
DOUBTED = 0.05  # a record's own link this far below zero speaks against a meaning the records near it agree on
SEPARATE, WINNERS = 4096, 40  # the pattern separator of the links' keys: its code's width, and the units a key keeps (wide enough that some 1,700 records each hold their own links)
FAN_IN = 32  # each of its code's units reads 32 of the key's (the library's sparse projection: a record's cue costs a twentieth of a dense one's, and reads the same)
CLEAR = 0.15  # and stands this far above its next strongest (two meanings read alike: neither is known)
TEMPERATURE = 0.15  # a guess is drawn by exp(link / TEMPERATURE): flat while the links are flat
PISTACHIO = 3.0  # a pistachio's weight as a lesson of the links (a fifth of the way in the consolidated matrix)


def resample(frames: np.ndarray, n: int) -> np.ndarray:
    idx = np.linspace(0, len(frames) - 1, n)
    lo = np.floor(idx).astype(int)
    hi = np.minimum(lo + 1, len(frames) - 1)
    w = (idx - lo)[:, None]
    return frames[lo] * (1 - w) + frames[hi] * w


RANGE = 8.0  # nats below each frame's loudest band that a code keeps (the quieter bands are the room's)
SMOOTH = np.array([1.0, 2.0, 3.0, 2.0, 1.0]) / 9.0  # across neighbouring bands: a voice a semitone higher reads alike


def to_pcm8k(pcm: np.ndarray | None) -> np.ndarray:
    """The heard 16 kHz samples at 8 kHz (each pair averaged), at most 3 s."""
    if pcm is None or len(pcm) < 2:
        return np.zeros(0)
    x = np.asarray(pcm, np.float64)
    x = x[: len(x) // 2 * 2].reshape(-1, 2).mean(axis=1)
    return x[:PCM_MAX]


def pack(frames: np.ndarray) -> np.ndarray:
    """A record's value: the frames at their own timing (squeezed only past 3 s), padded with
    silence, and their count. (The heard audio is kept beside the records, `SoundMemory.audio`: only
    the sounds the parrot can say need it, and most records are sounds heard once.)"""
    f = frames.astype(np.float64)
    if len(f) > VALUE_FRAMES:
        f = resample(f, VALUE_FRAMES)
    out = np.full((VALUE_FRAMES, BANDS), SILENT)
    out[: len(f)] = f
    return np.concatenate([out.ravel(), [len(f)]])


def unpack(v: np.ndarray) -> np.ndarray:
    n = int(min(VALUE_FRAMES, max(2, round(float(v[FRAMES_WIDTH - 1])))))
    return v[: FRAMES_WIDTH - 1].reshape(VALUE_FRAMES, BANDS)[:n].astype(np.float64)


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


def pairwise(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The root-mean-square distance between every frame of `a` and every frame of `b`."""
    aa, bb = (a * a).sum(axis=1)[:, None], (b * b).sum(axis=1)[None, :]
    return np.sqrt(np.maximum(aa + bb - 2.0 * (a @ b.T), 0.0) / a.shape[1])


def warp_row(prev: np.ndarray, d: np.ndarray) -> np.ndarray:
    """One more row of the time-warping table: `prev` the row before (its first entry the border), `d` this
    frame's distance to each reference frame (the last axis; any leading axes are warped side by side).
    cost[j] = d[j] + min(prev[j-1], prev[j], cost[j-1]); the run along the row is the running minimum of
    (a - D) plus D, with D the summed distances along the row."""
    a = d + np.minimum(prev[..., :-1], prev[..., 1:])
    D = np.cumsum(d, axis=-1)
    row = np.empty_like(prev)
    row[..., 0] = np.inf
    row[..., 1:] = D + np.minimum.accumulate(a - D, axis=-1)
    return row


def warp(d: np.ndarray) -> np.ndarray:
    """The time-warping table of a distance matrix (rows: one sound's frames; columns: the other's)."""
    n, m = d.shape
    c = np.full((n + 1, m + 1), np.inf); c[0, 0] = 0.0
    for i in range(1, n + 1):
        c[i] = warp_row(c[i - 1], d[i - 1])
    return c


def warp_path(c: np.ndarray) -> list:
    """The cheapest path through a time-warping table, from its end to its start: (row, column) pairs."""
    i, j, pairs = c.shape[0] - 1, c.shape[1] - 1, []
    while i > 0 and j > 0:
        pairs.append((i - 1, j - 1))
        k = int(np.argmin([c[i - 1, j - 1], c[i - 1, j], c[i, j - 1]]))
        i, j = (i - 1, j - 1) if k == 0 else (i - 1, j) if k == 1 else (i, j - 1)
    return pairs


def align(take: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """The take laid on the reference's timeline: the cheapest path between them (dynamic time
    warping on the frames' distance), each reference frame given the mean of the take's frames the
    path pairs with it. A take said faster or slower lines up sound for sound."""
    a, b = ref.astype(np.float64), take.astype(np.float64)
    n = len(a)
    pairs = warp_path(warp(pairwise(a, b)))
    out, cnt = np.zeros_like(a), np.zeros(n)
    for i, j in pairs:
        out[i] += b[j]; cnt[i] += 1
    return out / np.maximum(cnt, 1)[:, None]


NEAR = 5  # the records nearest a take (lined up in time) that are kept as what it sounds like
SAME_WORD = 0.28  # the time-aligned distance (relative to the sounds' own spread) under which a take is told again as the record nearest it (measured on 295 takes of 45 words and phrases by five voices: over half of one voice's takes of an utterance fall under it, five of 6,607 pairs of different utterances do)
YOUNG, SAME_YOUNG, APART = 6, 0.42, 1.15  # a record heard fewer than YOUNG times is a sound in the learning: a take within SAME_YOUNG of it is told again as it, where the next record lies APART times farther (a sound said three times is one record; a record heard often takes only takes close to it)
LIKE_WITHIN = 0.55  # a sound within this of its nearest record can be taken for what the records near it stand for
LIKE_SOFT = 0.08  # among the nearest records, one this share farther than the nearest counts a third as much
AGREED, AGREED_CLEAR = 0.6, 0.35  # the records near a sound agree on a meaning: its share of their links, and its lead over the next
VOICES = 2  # and at least this many of them stand for it (one record alike in sound is no agreement: a visitor's "what colour" lay within reach of their own "white")
LENGTHS = 1.7  # a take is lined up only with records no more than this many times longer or shorter
TERMS = 13  # the smooth shape of a frame's bands: its first cosine terms (the resonances of the mouth, without the voice's pitch lines)
_COSINES = np.cos(np.pi / BANDS * (np.arange(BANDS)[None, :] + 0.5) * np.arange(1, TERMS + 1)[:, None])


def shape(frames: np.ndarray) -> np.ndarray:
    """What makes an utterance that utterance, for lining two takes up: its loud core; each frame's bands
    within RANGE of the frame's loudest; of those the smooth shape across the bands (the first TERMS cosine
    terms: where the mouth's resonances lie, without the pitch lines or the level of the voice); less each
    term's mean over the utterance (the voice's and the room's average colour out, its changes kept)."""
    f = frames.astype(np.float64)
    e = np.log(np.exp(f).sum(axis=1))
    on = np.flatnonzero(e > e.max() - 6.0)
    if len(on) >= 2:
        f = f[on[0]: on[-1] + 1]
    f = np.maximum(f, f.max(axis=1, keepdims=True) - RANGE)
    c = f @ _COSINES.T
    return c - c.mean(axis=0, keepdims=True)


FIRST_PASS, BRIEF = 96, 16  # of many records, the 96 nearest by their shapes squeezed to 16 frames are lined up in time


def brief(sh: np.ndarray) -> np.ndarray:
    """An utterance's shape squeezed to BRIEF frames, at unit loudness: the first pass of the search."""
    b = resample(sh, BRIEF)
    return (b / max(float(np.sqrt((b ** 2).mean())), 1e-9)).ravel()


def distance(a: np.ndarray, b: np.ndarray) -> float:
    """How far two takes are once lined up sound for sound (dynamic time warping over their shapes),
    relative to how much the words themselves vary: a take said faster, slower or louder is near its
    word; another word is far."""
    n, m = len(a), len(b)
    c = warp(pairwise(a, b))
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
    na = len(la_c)
    pairs = warp_path(warp(pairwise(la_c, lb_c)))
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


_EAR = Ear(frames=CODE_FRAMES, bands=BANDS, range=RANGE)  # the library's ear (cadence.senses, 0.101): resampled, clamped, centred, unit length


def code(frames: np.ndarray) -> np.ndarray:
    """A sound's key: the word's loud core (its soft start and end are kept for the voice, not the key),
    smoothed across neighbouring bands (a take a semitone higher reads alike), then the library's ear's
    code (`cadence.senses.Ear`: resampled to 16 frames, each band kept within RANGE of its frame's
    loudest, less its mean level, at unit length), smoothed across neighbouring frames. Takes of one
    word read a cosine of 0.76 to 0.98 (mean 0.92) with tempo +-15 %, pitch +-1 semitone, level +-6 dB
    and room noise; another word reads 0.31 at most (tests/test_words.py)."""
    f = frames.astype(np.float64)
    e = np.log(np.exp(f).sum(axis=1))
    on = np.flatnonzero(e > e.max() - 6.0)
    if len(on) >= 2:
        f = f[on[0]: on[-1] + 1]
    f = np.maximum(f, f.max(axis=1, keepdims=True) - RANGE)
    g = np.pad(f, ((0, 0), (2, 2)), mode="edge")
    f = sum(SMOOTH[k] * g[:, k: k + f.shape[1]] for k in range(len(SMOOTH)))
    r = _EAR.code(f)[0].reshape(CODE_FRAMES, BANDS)
    r = 0.25 * np.roll(r, 1, axis=0) + 0.5 * r + 0.25 * np.roll(r, -1, axis=0)
    r = r - r.mean()
    n = float(np.linalg.norm(r))
    return (r / n if n > 0 else r).ravel()


class SoundMemory:
    LEVEL = 2.5  # a record this deep is a sound the parrot can say back

    def __init__(self, revise: float = 0.85, capacity: int = 256, words: list[str] | None = None):
        self.words = list(words or KINDS)
        # a write is the record "told again" only with that record's own key: the parrot decides that a
        # take is a word it knows by lining it up against the words it has (`same_word`)
        self.records = LongTermMemory(width=CODE_FRAMES * BANDS, value_width=FRAMES_WIDTH, capacity=capacity,
                                      cosine=True, revise=0.9999, temperature=0.08, candidates=0,
                                      hold=36000.0, idle=40.0, depth=2.0, dtype=np.float32, blend=True)
        self.audio: dict[int, np.ndarray] = {}  # each record's heard audio (8 kHz), for the records that keep it
        # (a lesson's fresh part keeps 0.97 through each later lesson: a meaning one pistachio taught lasts through
        # some thirty more lessons, and repetition consolidates it)
        # The links' key is the record's own address (`address`: a fixed random direction of its slot), through
        # a pattern separator (the library's: a wide random code, its strongest few units kept), so a lesson on
        # one record leaves every other record's links as they were, however alike their sounds: with the
        # sound's code as the key, one visitor's "apple" read "red" at .3 and more after a pistachio for their
        # "red". What sounds alike is found by lining sounds up (`like`).
        self.synapses = SynapticMemory(pre=np.arange(CODE_FRAMES * BANDS), post=np.arange(len(self.words)), rule="delta",
                                       decay=0.97, consolidation=0.05,
                                       separator=PatternSeparator(inputs=CODE_FRAMES * BANDS, expansion=SEPARATE, winners=WINNERS, seed=31, fan_in=FAN_IN))
        self.synapses.reset(1)
        self.last_read: dict[str, Any] | None = None
        self.last_write: dict[str, Any] | None = None
        self.heard = np.zeros(capacity, int)        # hearings a record holds (the running mean's weight)
        self.programs: dict[int, dict[str, Any]] = {}  # each word's motor program and its attempts
        self.last_distance: float | None = None
        self.typical = np.full(capacity, -1.0)  # how typical the kept take of each record is (its code's cosine with the record's key)
        self.marks: dict[int, list] = {}  # where each word of a record's meaning begins on its timeline: [[frame, word], ...]
        self.born = np.zeros(capacity, int)  # how many records each slot has held (a slot's new record is another sound)
        self._shapes: dict[int, tuple] = {}  # each record's shape, kept until the record changes
        self._briefs: dict[int, np.ndarray] = {}  # each record's shape squeezed to BRIEF frames (the first pass of `distances`)
        self.near: list = []  # the records nearest the sound last heard, lined up in time: [(slot, distance), ...]
        self._cues: dict[int, tuple] = {}  # each record's cue for the links (its key through the separator: its winners and their values), kept until the record changes
        self._reads: np.ndarray | None = None  # every record's links as read, kept until a record or a link changes
        self._stale: set = set()  # the records heard since the links were read, the links unchanged
        self._meanings: list | None = None
        self._view: list | None = None  # each record's picture and links as the page draws them
        self.rng = np.random.default_rng(31)

    def hear(self, frames: np.ndarray, pcm: np.ndarray | None = None) -> dict[str, Any]:
        """Tell the stores a heard sound: read with its code (the attention over the records), then
        write it (a new record, or one told again). The word it stands for is its record's link
        (`word_of`)."""
        key = code(frames)
        read = self.records.read(key)
        self.last_read = {"slots": read.slots.tolist(), "weights": np.round(read.weights[0], 4).tolist(),
                          "cue": self.thumb(key)} if len(read.slots) else {"slots": [], "weights": [], "cue": self.thumb(key)}
        cos = None
        if self.records.count:
            k = self.records.keys[: self.records.count]
            cos = float(np.max(k @ key / np.maximum(np.linalg.norm(k, axis=1), 1e-12)))
        take = to_pcm8k(pcm)
        known, self.last_distance = self.same_word(frames, key)
        before_audio = self.audio.get(int(known)) if known is not None else None
        if known is not None:
            # a take told again: laid on its record's timeline, and the library's record strength
            # (`blend`, cadence#336) moves the record toward it, so the record holds the mean of its takes
            slot, revised = self.records.write(key, pack(align(frames, self.template(known))), recognised=int(known))
        else:
            slot, revised = self.records.write(key, pack(frames), recognised=-1)
        if not revised:
            self.heard[slot] = 0
            self.born[slot] += 1
            self.programs.pop(slot, None)
            self.marks.pop(slot, None)
            self.typical[slot] = -1.0
        self.heard[slot] += 1
        self.audio[int(slot)] = take  # (a sound told again: the take, mixed below with what it had)
        self._mix_audio(slot, take, revised, before_audio)
        self._record_changed(slot)
        self.last_write = {"slot": int(slot), "revised": bool(revised), "best_cosine": None if cos is None else round(cos, 3), "distance": self.last_distance,
                           "heard": int(self.heard[slot])}
        return {"read": self.last_read, "write": self.last_write}

    def _mix_audio(self, slot: int, take: np.ndarray, revised: bool, previous: np.ndarray | None) -> None:
        """The record's sound: a first hearing keeps its take; a word told again keeps a mix of the
        sound it had and the new take (`blend_audio`), so it never repeats one recording exactly.
        `previous`: the audio the record held before."""
        if not revised or previous is None:
            return
        kept = previous
        mixed = blend_audio(kept, take, int(self.heard[slot])) if len(take) and len(kept) else (kept if len(kept) else take)
        self.audio[int(slot)] = np.asarray(mixed, np.float64)[:PCM_MAX]

    def same_word(self, frames: np.ndarray, key: np.ndarray) -> tuple[int | None, float | None]:
        """The utterance the parrot knows that this take is, if any: of its records (those of a like length),
        the one nearest once lined up in time, if under SAME_WORD; or a record in the learning (heard fewer than
        YOUNG times) under SAME_YOUNG, where every record that stands for another meaning lies APART times
        farther (a visitor's "what is this" is not told again as their own "what colour" record). The nearest
        few are kept as what the take sounds like (`near`)."""
        self.near = []
        if not self.records.count:
            return None, None
        slots, d = self.distances(shape(frames))
        if not len(slots):
            return None, None
        order = np.argsort(d)[:NEAR]
        self.near = [(int(slots[i]), round(float(d[i]), 3)) for i in order]
        best, bd = self.near[0]
        if bd < SAME_WORD:
            return best, bd
        mine = self.word_of(best)[0]
        other = [d for s_, d in self.near[1:] if (w := self.word_of(s_)[0]) is not None and w != mine]  # the nearest record that stands for another meaning
        nxt = other[0] if other else np.inf
        if self.heard[best] < YOUNG and bd < SAME_YOUNG and nxt >= APART * bd:
            return best, bd
        return None, bd

    def distances(self, mine: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """How far a take's shape is from the records of a like length, each lined up in time (the records
        warped side by side, a row of the table a frame of the take): the records' slots and distances. Of
        many records, the FIRST_PASS nearest by their shapes squeezed to BRIEF frames are lined up."""
        r, n = self.records, len(mine)
        lens = {}
        for s in range(r.count):
            kept = self._shapes.get(s)
            if kept is None or kept[0] != (int(self.born[s]), int(self.heard[s])):
                kept = ((int(self.born[s]), int(self.heard[s])), shape(self.template(s)))
                self._shapes[s] = kept
                self._briefs[s] = brief(kept[1])
            if n <= LENGTHS * len(kept[1]) and len(kept[1]) <= LENGTHS * n:
                lens[s] = len(kept[1])
        if not lens:
            return np.zeros(0, int), np.zeros(0)
        if len(lens) > FIRST_PASS:  # a first pass: the records nearest by their brief shapes
            cand = np.array(sorted(lens))
            far = np.sqrt(((np.stack([self._briefs[int(s)] for s in cand]) - brief(mine)[None, :]) ** 2).mean(axis=1))
            lens = {int(s): lens[int(s)] for s in cand[np.argsort(far)[:FIRST_PASS]]}
        slots = np.array(sorted(lens)); ln = np.array([lens[int(s)] for s in slots]); m = int(ln.max())
        T = np.zeros((len(slots), m, mine.shape[1]))
        for i, s in enumerate(slots):
            T[i, : ln[i]] = self._shapes[int(s)][1]
        TT, past = (T ** 2).sum(axis=2), np.arange(m)[None, :] >= ln[:, None]
        row = np.full((len(slots), m + 1), np.inf); row[:, 0] = 0.0
        xx = (mine * mine).sum(axis=1)
        for i in range(n):
            d = np.sqrt(np.maximum(TT + xx[i] - 2.0 * (T @ mine[i]), 0.0) / mine.shape[1])
            d[past] = 1e6
            row = warp_row(row, d)
        spread = 0.5 * (float(np.sqrt((mine ** 2).mean())) + np.sqrt(TT.sum(axis=1) / (ln * mine.shape[1])))
        return slots, row[np.arange(len(slots)), ln] / (n + ln) / np.maximum(spread, 1e-9)

    def reads(self) -> np.ndarray:
        """Every record's key read through the synapses (the links read forwards): records x words."""
        n = self.records.count
        if not n:
            return np.zeros((0, len(self.words)))
        if self._reads is None or len(self._reads) != n or self._stale:  # kept until a record or a link changes (`_changed`)
            stale = [s for s in range(n) if (kept := self._cues.get(s)) is None or kept[0] != (int(self.born[s]), int(self.heard[s]))]
            for at in range(0, len(stale), 64):  # (the cues of the records that have none, a block at a time)
                block = stale[at: at + 64]
                for s, c in zip(block, self.cue(np.stack([self.address(s) for s in block]))):
                    top = np.sort(np.argsort(c)[-WINNERS:])  # a cue is its separator's winners: kept as those units and their values
                    self._cues[s] = ((int(self.born[s]), int(self.heard[s])), top, c[top])
            if self._reads is None or len(self._reads) > n:
                self._reads = self.through(self.synapses.strength[0], range(n))
            else:  # a record heard, the links as they were: its row alone (and a new record's)
                rows = sorted({s for s in self._stale if s < n} | set(range(len(self._reads), n)))
                self._reads = np.concatenate([self._reads, np.zeros((n - len(self._reads), len(self.words)))])
                self._reads[rows] = self.through(self.synapses.strength[0], rows)
            self._stale = set()
        return self._reads

    def through(self, weights: np.ndarray, slots) -> np.ndarray:
        """The records' cues (their winners and values) through a matrix of the links: one row a record."""
        slots = list(slots)
        if not slots:
            return np.zeros((0, weights.shape[1]))
        idx = np.stack([self._cues[s][1] for s in slots]); val = np.stack([self._cues[s][2] for s in slots])
        out = np.empty((len(slots), weights.shape[1]))
        for at in range(0, len(slots), 256):
            out[at: at + 256] = np.einsum("nk,nkm->nm", val[at: at + 256], weights[idx[at: at + 256]])
        return out

    def _changed(self) -> None:
        """A link changed: every record's links are read anew at the next read."""
        self._reads = self._meanings = self._view = None
        self._stale = set()

    def _record_changed(self, slot: int) -> None:
        """A record was heard (written or told again), the links as they were: its row is read anew."""
        self._meanings = self._view = None
        self._stale.add(int(slot))

    def meanings(self) -> list:
        """What each record stands for, by its own links (kept with the reads): (meaning or None, link)."""
        r = self.reads()
        if self._meanings is None or len(self._meanings) != len(r):
            if not len(r):
                self._meanings = []
                return self._meanings
            top = r.argmax(axis=1); rows = np.arange(len(r)); best = r[rows, top]
            rest = r.copy(); rest[rows, top] = -np.inf
            second = rest.max(axis=1) if r.shape[1] > 1 else np.zeros(len(r))
            self._meanings = [((self.words[int(j)] if b >= LINKED and b - c >= CLEAR else None), round(float(b), 3)) for j, b, c in zip(top, best, second)]
        return self._meanings

    def address(self, slot: int) -> np.ndarray:
        """A record's own address for its links: a fixed random direction of its slot and of the count of
        records the slot has held (another record in the slot has another address, and none of its links)."""
        return np.random.default_rng([31, int(slot), int(self.born[slot])]).normal(size=CODE_FRAMES * BANDS)

    def cue(self, keys: np.ndarray) -> np.ndarray:
        """The synapses' own cue for keys: each through the pattern separator, at unit length."""
        k = np.atleast_2d(np.asarray(keys, np.float64))
        c = self.synapses.separator.code(k / np.maximum(np.linalg.norm(k, axis=1, keepdims=True), 1e-12))
        return c / np.maximum(np.linalg.norm(c, axis=1, keepdims=True), 1e-12)

    def word_of(self, slot: int, reads: np.ndarray | None = None) -> tuple[str | None, float]:
        """What a record stands for (a word, or a question: a sequence of words): the strongest unit its key
        reads, if it reaches LINKED and stands CLEAR of the next."""
        if not 0 <= slot < self.records.count:
            return None, 0.0
        if reads is None or reads is self._reads:
            return self.meanings()[slot]
        v = reads[slot]
        j = int(np.argmax(v))
        rest = float(np.max(np.delete(v, j))) if len(v) > 1 else 0.0
        return (self.words[j] if v[j] >= LINKED and v[j] - rest >= CLEAR else None), round(float(v[j]), 3)

    def like(self, near: list | None, reads: np.ndarray, but: int = -1) -> np.ndarray | None:
        """What the records nearest a sound stand for: their links, each record counted by how near it is
        against the nearest (LIKE_SOFT)."""
        near = [(s, d) for s, d in (near or []) if s != but and 0 <= s < len(reads)]
        if not near:
            return None
        d0 = max(min(d for _, d in near), 1e-6)
        w = np.array([np.exp(-(d - d0) / (LIKE_SOFT * d0)) for _, d in near])
        return (w[:, None] * np.clip(reads[[s for s, _ in near]], -1.0, 1.0)).sum(axis=0) / w.sum()  # (a doubted link, below zero, speaks against its meaning)

    def taken_for(self, own: np.ndarray, near: list | None, reads: np.ndarray, but: int = -1) -> tuple[str | None, float]:
        """What a sound is taken for: the meaning its own links read (strong, and clear of the next); without
        one, the meaning the records nearest it agree on (VOICES of them at least), where it lies within
        LIKE_WITHIN of the nearest."""
        j = int(np.argmax(own))
        rest = float(np.max(np.delete(own, j))) if len(own) > 1 else 0.0
        if own[j] >= LINKED and own[j] - rest >= CLEAR:
            return self.words[j], round(float(own[j]), 3)
        like = self.like(near, reads, but)
        if like is not None and min(d for s, d in near if s != but) < LIKE_WITHIN:
            k = int(np.argmax(like))
            voices = sum(1 for s, d in near if s != but and 0 <= s < len(reads) and d < LIKE_WITHIN and reads[s][k] >= LINKED)
            if like[k] >= AGREED and like[k] - float(np.max(np.delete(like, k))) >= AGREED_CLEAR and voices >= VOICES and own[k] > -DOUBTED:
                return self.words[k], round(float(like[k]), 3)
        return None, round(float(own[j]), 3)

    def meaning(self, slot: int) -> tuple[str | None, float]:
        """What the sound just heard (its record `slot`) is taken for (`taken_for`, with the records it was
        nearest when heard)."""
        if not 0 <= slot < self.records.count:
            return None, 0.0
        r = self.reads()
        return self.taken_for(r[slot], self.near, r, but=slot)

    def guess(self, slot: int, offered: list[str], near: list | None = None) -> tuple[str | None, float]:
        """A meaning for a sound that reads none strongly: one of those on offer, or one a sound like it stands
        for, drawn by the links' strengths (exp(link / TEMPERATURE): flat while nothing is known); and the
        chance it was drawn with. `near`: the records the sound is nearest (slot, distance): what each stands
        for counts by how near it is against the nearest (`like`)."""
        if not 0 <= slot < self.records.count:
            return None, 0.0
        r = self.reads()
        z = r[slot].copy()
        idx = [self.words.index(m) for m in offered if m in self.words]
        like = self.like(near, r, but=slot)
        if like is not None:
            z = z + like
            idx = sorted(set(idx) | {int(j) for j in np.flatnonzero(like >= LINKED)})
        if not idx:
            return None, 0.0
        z = z[idx] / TEMPERATURE
        p = np.exp(z - z.max()); p /= p.sum()
        k = int(self.rng.choice(len(idx), p=p))
        return self.words[idx[k]], round(float(p[k]), 3)

    def guess_sound(self, word: str, but: int = -1) -> tuple[int | None, float]:
        """A sound to say for a word that recalls none: one of the sounds it can say (`but` the sound it is
        answering), drawn by each sound's link to the word less its strongest link to anything else (a sound
        that stands for another meaning, or lies close to a record that does, is an unlikely name for this one)."""
        slots = [s for s in self.sayable() if s != but]
        if word not in self.words or not slots:
            return None, 0.0
        r, j = self.reads(), self.words.index(word)
        z = []
        for s in slots:
            other = max(0.0, float(np.max(np.delete(r[s], j))))
            if other < LINKED:  # a sound with no meaning of its own: what the record it lies nearest stands for (another take of a word it knows is that word)
                at, d = self.distances(shape(self.template(s)))
                near = sorted(((int(a), float(x)) for a, x in zip(at, d) if int(a) != s), key=lambda n: n[1])[:1]
                if near and near[0][1] < SAME_YOUNG:
                    other = max(other, float(np.max(np.delete(np.clip(r[near[0][0]], 0.0, 1.0), j))))
            z.append((r[s][j] - other) / TEMPERATURE)
        z = np.array(z)
        p = np.exp(z - z.max()); p /= p.sum()
        k = int(self.rng.choice(len(slots), p=p))
        return int(slots[k]), round(float(p[k]), 3)

    def _toward(self, slot: int, word: str, target: float, amount: float = 0.0) -> None:
        """One link's lesson alone (the other meanings are no teaching targets): its read moves to `target`."""
        k = self.address(slot)
        value, seen = np.zeros(len(self.words)), np.zeros(len(self.words), bool)
        j = self.words.index(word); value[j], seen[j] = target, True
        self.synapses.observe((k / max(float(np.linalg.norm(k)), 1e-12))[None, :], value[None, :], value_mask=seen[None, :], salience=np.array([max(0.0, amount)]))
        self._changed()

    def reward(self, slot: int, word: str | None, amount: float = PISTACHIO) -> None:
        """A pistachio's lesson: the record's link to this meaning grows, and that link alone (its other links
        are no teaching targets, so the sounds near it keep their own meanings: with every link taught at
        once, ten pistachios for "where is the ball" took "where is the cup" from .97 to .6)."""
        if word in self.words and 0 <= slot < self.records.count:
            self._toward(slot, word, 1.0, amount)

    def doubt(self, slot: int, word: str | None, by: float = 0.2, near: list | None = None) -> None:
        """A meaning no pistachio followed (a guess, or what the sounds like it stand for): the record's own link
        a little lower for a while, so the next guess looks elsewhere; where the meaning came from the records
        near it (`near`: those it was nearest when heard), the record's own link falls `by` below what they
        say, so that their vote stops naming it for this sound."""
        if word in self.words and 0 <= slot < self.records.count:
            r, j = self.reads(), self.words.index(word)
            like = self.like(near, r, but=slot) if near else None
            said = 0.0 if like is None else max(0.0, float(like[j]))
            self._toward(slot, word, max(-1.0, min(float(r[slot][j]), -said) - by))

    def fade(self, slot: int, word: str | None, keep: float = 0.6) -> None:
        """A link used with no pistachio after it: its fresh part shrinks to `keep` of itself (the link moves
        toward what repetition has consolidated); a link the consolidated matrix holds stays."""
        if word not in self.words or not 0 <= slot < self.records.count:
            return
        self.reads()
        j = self.words.index(word)
        slow, now = float(self.through(self.synapses.consolidated[:, j: j + 1], [slot])[0, 0]), float(self.through(self.synapses.strength[0][:, j: j + 1], [slot])[0, 0])
        if now > slow:
            self._toward(slot, word, slow + keep * (now - slow))

    def recall(self, word: str | None, reads: np.ndarray | None = None) -> tuple[int | None, float]:
        """The word recalls its sound (the link read backwards, from the word to the records): of the
        records it can say whose sound stands for this word, the one heard most (the deepest)."""
        if word not in self.words:
            return None, 0.0
        m = self.meanings() if reads is None or reads is self._reads else [self.word_of(s, reads) for s in range(self.records.count)]
        best, top = None, (-1.0, 0.0)
        for s in self.sayable():
            w, link = m[s]
            if w == word and (float(self.records.deep[s]), link) > top:
                best, top = s, (float(self.records.deep[s]), link)
        return best, top[1]

    def link(self, slot: int, word: str | None, amount: float = 1.0) -> None:
        """A lesson: the record and the word linked (one delta step of the synapses from the record's
        address to the word's unit, as large as the lesson's amount)."""
        if word not in self.words or not 0 <= slot < self.records.count:
            return
        k = self.address(slot)
        onehot = np.zeros(len(self.words)); onehot[self.words.index(word)] = 1.0
        self.synapses.observe((k / max(float(np.linalg.norm(k)), 1e-12))[None, :], onehot[None, :], salience=np.array([max(0.0, amount)]))
        self._changed()

    reward_link = link

    def pcm_of(self, slot: int) -> np.ndarray:
        """The word's audio as the record keeps it (8 kHz): what the parrot says back."""
        return np.asarray(self.audio.get(int(slot), np.zeros(0)), np.float32)

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
        return np.flatnonzero(self.records.deep[: self.records.count] >= self.LEVEL).tolist()

    @staticmethod
    def thumb(key: np.ndarray) -> list:
        """A small picture of a code: 24 frames by 20 bands, 0 to 255."""
        r = key.reshape(CODE_FRAMES, BANDS)
        r = 0.5 * (r[:, 0::2] + r[:, 1::2])
        lo, hi = float(r.min()), float(r.max())
        return np.round(255 * (r - lo) / max(hi - lo, 1e-9)).astype(int).ravel().tolist()

    def links(self, slot: int) -> tuple[list, list]:
        """The synapses' read of a record's code: the consolidated part and the fading residual."""
        self.reads()
        slow = self.through(self.synapses.consolidated, [slot])[0]
        fast = self.through(self.synapses.strength[0], [slot])[0] - slow
        return np.round(slow, 4).tolist(), np.round(fast, 4).tolist()

    def view(self) -> dict[str, Any]:
        """What the page draws: every record (depth, how faded, recent use, its picture) and the
        synapses from each record's sound to each meaning (kept until a record or a link changes)."""
        r = self.records
        reads = self.reads()
        if self._view is None or len(self._view) != r.count:
            slow = self.through(self.synapses.consolidated, range(r.count))
            self._view = [{"slot": s, "thumb": self.thumb(r.keys[s]), "frames": len(self.audio.get(s, ())),
                           "slow": np.round(slow[s], 4).tolist(), "fast": np.round(reads[s] - slow[s], 4).tolist()} for s in range(r.count)]
        rows = []
        for s in range(r.count):
            prog = self.programs.get(s)
            rows.append({**self._view[s], "deep": round(float(r.deep[s]), 3), "faded": round(float(r.faded[s]), 2), "heard": int(self.heard[s]),
                         "match": None if not prog or not prog["matches"] else round(prog["matches"][-1], 3), "recent": round(float(r.recent[s]), 4)})
        return {"records": rows, "things": self.words, "level": self.LEVEL, "revise": r.revise,
                "read": self.last_read, "write": self.last_write}

    def save(self, compact: bool = False) -> dict[str, Any]:
        """Every record with its frames, audio, depth, hearings and marks, and the links' consolidated part.
        `compact`: the frames as bytes (FRAME_STEP nats a step) and the audio as 16-bit samples, in base64
        (format 3, the starting memory's file); else as lists of numbers (format 2)."""
        r = self.records
        rows = []
        for s in range(r.count):
            f, a = unpack(r.values[s]), np.asarray(self.audio.get(s, np.zeros(0)), np.float64)
            row = {"deep": float(r.deep[s]), "heard": int(self.heard[s]), "typical": float(self.typical[s]), "marks": self.marks.get(s),
                   "program": None if s not in self.programs else np.round(self.programs[s]["P"], 3).tolist(),
                   "matches": [] if s not in self.programs else [round(m, 3) for m in self.programs[s]["matches"][-20:]]}
            if compact:
                row["f8"] = base64.b64encode(np.clip(np.round((f - FRAME_LOW) / FRAME_STEP), 0, 255).astype(np.uint8).tobytes()).decode()
                row["a16"] = base64.b64encode(np.clip(np.round(a * 32767), -32767, 32767).astype("<i2").tobytes()).decode() if len(a) else ""
            else:
                row["frames"], row["pcm"] = np.round(f, 3).tolist(), np.round(a, 4).tolist()
            rows.append(row)
        return {"format": 3 if compact else 2, "records": rows, "words": self.words, "consolidated": np.round(self.synapses.consolidated, 5).tolist()}

    @staticmethod
    def _frames_audio(rec: dict) -> tuple[np.ndarray | None, np.ndarray]:
        """A saved record's frames and audio, in either format."""
        if "f8" in rec:
            f = np.frombuffer(base64.b64decode(rec["f8"]), np.uint8).astype(np.float64) * FRAME_STEP + FRAME_LOW
            a = np.frombuffer(base64.b64decode(rec["a16"]), "<i2").astype(np.float64) / 32767 if rec.get("a16") else np.zeros(0)
            return f.reshape(-1, BANDS), a
        if "frames" in rec:
            return np.asarray(rec["frames"], np.float64).reshape(-1, BANDS), np.asarray(rec.get("pcm") or [], np.float64)
        return None, np.zeros(0)  # kept by an older page in another format

    def load(self, saved: dict[str, Any]) -> None:
        """A saved memory's records written (into an empty memory in one pass, the library's `fill`), their
        links' consolidated part, and each record's shape and cue made ready before the first sound."""
        got = []
        for rec in saved.get("records", []):
            frames, audio = self._frames_audio(rec)
            if frames is None or not 2 <= len(frames) <= VALUE_FRAMES:
                continue
            got.append((rec, frames, audio))
        if not got:
            return
        keys = np.stack([code(f) for _, f, _ in got])
        values = np.stack([pack(f) for _, f, _ in got])
        if self.records.count == 0 and len(got) <= self.records.capacity:
            slots = [int(x) for x in self.records.fill(keys, values)]
        else:
            slots = [self.records.write(k, v)[0] for k, v in zip(keys, values)]
        for slot, (rec, frames, audio) in zip(slots, got):
            self.born[slot] += 1
            if len(audio):
                self.audio[slot] = audio[:PCM_MAX]
            if rec.get("marks"):
                self.marks[slot] = [[int(f), str(w)] for f, w in rec["marks"]]
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
        self._changed()
        for slot in range(self.records.count):  # each record's shape, ready before the first sound is heard
            self._shapes[slot] = ((int(self.born[slot]), int(self.heard[slot])), shape(self.template(slot)))
            self._briefs[slot] = brief(self._shapes[slot][1])
        self.reads()

    @staticmethod
    def frames_of_value(v: np.ndarray) -> np.ndarray:
        return unpack(v)

    def clear(self) -> None:
        born = self.born
        self.__init__(self.records.revise, self.records.capacity, self.words)
        self.born = born + 1  # every slot's next record is another sound
