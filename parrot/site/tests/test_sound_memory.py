"""What the parrot remembers of heard sounds (the host's noise filter, then the library's
LongTermMemory and SynapticMemory, pack/py/parrotbrain/sounds.py), on synthesised audio.

    python parrot/site/tests/test_sound_memory.py

1. A word (a voiced, Apfel-like sound with a bright noise burst) said ten times over a steady
   background noise, while the parrot's focus is on the apple, gives exactly one record, deep
   enough to say back, whose code matches the clean word's (cosine above 0.8), and a synapse from
   that record's sound to the apple brighter than to any other thing.
2. Noise alone for 30 s, a fan-like hiss with clicks and a long steady hum, writes no record.
3. A word heard once is a shallow record that fades: after three minutes of quiet it is not deep
   enough to say and its fading has grown.
It also reads the cosine between takes of the word (what `revise` is set from).
The frames come from the library's front end formula (log-mel, 40 bands, 10 ms), ten a moment.
"""
from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE / "pack" / "py"))
_WHEEL = tempfile.mkdtemp(prefix="parrot-wheel-")  # the wheel the page ships, unpacked
zipfile.ZipFile(next((SITE / "pack").glob("cadence_net-*.whl"))).extractall(_WHEEL)
sys.path.insert(0, _WHEEL)
from parrotbrain.host import Host  # noqa: E402
from parrotbrain.sounds import code  # noqa: E402

RATE = 16000


def mel_bank(mels=40, rate=RATE, fft=512):
    mel = lambda hz: 2595.0 * np.log10(1.0 + hz / 700.0)
    edges = 700.0 * (10 ** (np.linspace(mel(0.0), mel(rate / 2), mels + 2) / 2595.0) - 1.0)
    bins = np.fft.rfftfreq(fft, 1.0 / rate)
    bank = np.zeros((mels, len(bins)))
    for m in range(mels):
        lo, mid, hi = edges[m], edges[m + 1], edges[m + 2]
        bank[m] = np.clip(np.minimum((bins - lo) / max(mid - lo, 1e-9), (hi - bins) / max(hi - mid, 1e-9)), 0.0, None)
    return bank


BANK = mel_bank()


def log_mel(x, frame=400, hop=160, fft=512):
    count = 1 + (len(x) - frame) // hop
    idx = np.arange(frame)[None, :] + hop * np.arange(count)[:, None]
    power = np.abs(np.fft.rfft(x[idx] * np.hanning(frame)[None, :], fft)) ** 2
    return np.log(power @ BANK.T + 1e-6)


def formant_voice(dur, f0, formants, rng, amp=0.25):
    t = np.arange(int(dur * RATE)) / RATE
    x = np.zeros_like(t)
    for h in range(1, int(4000 / f0)):
        f = h * f0
        g = sum(np.exp(-((f - fc) / bw) ** 2) for fc, bw in formants)
        x += g * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) / h ** 0.3
    env = np.sin(np.pi * np.linspace(0, 1, len(t))) ** 0.5
    return amp * x * env / max(1e-9, np.abs(x).max())


def word(rng):
    f0 = 170 * rng.uniform(0.95, 1.05)
    a = formant_voice(0.20, f0, [(700, 150), (1200, 200)], rng)
    burst = 0.08 * rng.standard_normal(int(0.06 * RATE)) * np.hanning(int(0.06 * RATE))
    burst = np.convolve(burst, [1, -0.9], mode="same")  # bright, like p and f
    e = formant_voice(0.15, f0 * 1.05, [(500, 120), (1800, 250)], rng)
    l = formant_voice(0.10, f0 * 0.97, [(400, 100), (1000, 200)], rng)
    return np.concatenate([a, burst, e, l])


def background(n, rng, level=0.006):
    w = rng.standard_normal(n)
    return level * np.convolve(w, np.ones(3) / 3, mode="same")  # a steady fan-like hiss


def feed(host, x, focus=None):
    """Ten frames a moment into the host; returns the moments' replies."""
    frames = log_mel(x).astype(np.float32)
    eye = np.zeros(host.w * host.h * 3, np.uint8)
    out = []
    for i in range(0, len(frames) - 9, 10):
        out.append(host.step({"voice_ok": False, "focus_kind": focus}, {"left": eye, "right": eye, "proprio": np.zeros(22, np.float32), "mel": frames[i:i + 10].ravel()}))
    return out


def word_code(x):
    f = log_mel(np.concatenate([np.zeros(400), x, np.zeros(400)]))
    e = np.log(np.exp(f).sum(1))
    return code(f[e > e.max() - 6])


def main() -> int:
    results = {}
    rng = np.random.default_rng(326)
    # the cosine between takes of one word, and between the word and other sounds
    takes = [word_code(word(np.random.default_rng(k))) for k in range(6)]
    same = [float(takes[i] @ takes[j]) for i in range(6) for j in range(i + 1, 6)]
    other = word_code(formant_voice(0.45, 230, [(300, 100), (2300, 300)], np.random.default_rng(9)))
    results["takes_cosine"] = {"same_word_min": round(min(same), 3), "same_word_mean": round(float(np.mean(same)), 3),
                               "other_sound": round(float(max(t @ other for t in takes)), 3)}
    # 1. a word said ten times over background noise, the focus on the apple
    host = Host({"eye": {"w": 16, "h": 8}})
    parts = [background(RATE * 2, rng)]
    clean = word_code(word(np.random.default_rng(1)))
    for _ in range(10):
        w = word(rng)
        parts.append(np.concatenate([w + background(len(w), rng), background(int(RATE * 1.5), rng)]))
    feed(host, np.concatenate(parts), focus="apple")
    r = host.mem.records
    view = host.mem.view()
    ok1 = r.count == 1
    detail = {"records": r.count, "writes": r.writes}
    if r.count:
        s0 = 0
        cos = float(r.keys[s0] @ clean / np.linalg.norm(r.keys[s0]))
        slow = view["records"][s0]["slow"]
        detail.update(deep=round(float(r.deep[s0]), 2), sayable=s0 in host.mem.sayable(), code_cosine=round(cos, 3),
                      apple_synapse=round(slow[0], 3), other_synapses_max=round(max(slow[1:]), 3))
        ok1 = ok1 and s0 in host.mem.sayable() and cos > 0.8 and slow[0] > max(slow[1:]) and slow[0] > 0.2
    results["word_ten_times"] = {**detail, "ok": bool(ok1)}
    # 2. noise alone: hiss, clicks, a long steady hum
    host = Host({"eye": {"w": 16, "h": 8}})
    x = background(RATE * 30, rng, level=0.02)
    for k in range(1, 15):
        x[k * 2 * RATE] += 0.9  # a click every two seconds
    t = np.arange(RATE * 6) / RATE
    x[RATE * 10: RATE * 16] += 0.15 * sum(np.sin(2 * np.pi * 120 * h * t) / h for h in range(1, 6))
    feed(host, x)
    results["noise_alone"] = {"records": host.mem.records.count, "ok": host.mem.records.count == 0}
    # 3. a word heard once fades
    host = Host({"eye": {"w": 16, "h": 8}})
    feed(host, np.concatenate([background(RATE, rng), word(rng) + background(int(0.51 * RATE), rng), background(RATE * 2, rng)]))
    r = host.mem.records
    after = {"records": r.count, "deep": round(float(r.deep[0]), 2) if r.count else None, "faded": round(float(r.faded[0]), 1) if r.count else None}
    feed(host, background(RATE * 180, rng))
    later = {"deep": round(float(r.deep[0]), 2) if r.count else None, "faded": round(float(r.faded[0]), 1) if r.count else None, "sayable": bool(host.mem.sayable())}
    results["once_fades"] = {"after_hearing": after, "after_3_min": later,
                             "ok": r.count == 1 and not later["sayable"] and later["faded"] > after["faded"] + 100}
    ok = all(v.get("ok", True) for v in results.values())
    print(json.dumps({**results, "ok": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
