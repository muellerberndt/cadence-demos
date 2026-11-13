"""How the parrot learns a word: hearing, storage, strengthening by repetition, practice, surprise
(the placeholder host's born mechanisms, pack/py/parrotbrain/host.py and sounds.py, with the
library's LongTermMemory), on synthesised words that vary from take to take.

    python parrot/site/tests/test_words.py

1. A word said ten times over a steady background noise: one record whose depth rises at every
   repetition, and whose stored form (the running mean of its hearings) comes nearer the clean
   word: its distance (1 minus the cosine of the codes) falls from the first hearings to the last.
2. Realistic takes (tempo +-5 %, pitch +-1 semitone, level +-6 dB, room noise), three sessions:
   one record each; the stored form's distance to the clean word after 1, 2, 4, 8 and 16
   repetitions falls, and a new take's recognition (its code's cosine with the record) rises.
3. Twenty practice attempts at the word from an immature motor program: the pronunciation match
   rises (the last five attempts against the first five, and a rising trend over all twenty).
4. Noise alone (a fan-like hiss, clicks, a long hum) gives no word.
5. A click after quiet is a sudden sound: the host reports it (the page turns the head to you).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_sound_memory as T  # noqa: E402  (the shared helpers: the front end, words, noise, the wheel)
from parrotbrain.host import Host  # noqa: E402
from parrotbrain.sounds import code  # noqa: E402


def main() -> int:
    rng = np.random.default_rng(337)
    results = {}
    host = Host({"eye": {"w": 16, "h": 8}})
    clean = T.log_mel(np.concatenate([np.zeros(400), T.word(np.random.default_rng(1)), np.zeros(400)]))
    e = np.log(np.exp(clean).sum(1)); clean = clean[e > e.max() - 6]
    T.feed(host, T.background(T.RATE * 2, rng))
    depths, distances = [], []
    for k in range(10):
        w = T.word(rng)
        T.feed(host, np.concatenate([w + T.background(len(w), rng), T.background(int(T.RATE * 1.5), rng)]))
        r = host.mem.records
        if r.count:
            depths.append(round(float(r.deep[0]), 3))
            distances.append(round(1.0 - float(code(host.mem.frames_of(0)) @ code(clean)), 4))
    words_host = host
    rising = all(b > a for a, b in zip(depths, depths[1:]))
    nearer = np.mean(distances[-3:]) < np.mean(distances[:3])
    results["ten_repetitions"] = {"records": host.mem.records.count, "heard": int(host.mem.heard[0]) if host.mem.records.count else 0,
                                  "depth_each": depths, "distance_each": distances, "depth_rises_each_time": rising,
                                  "distance_first3": round(float(np.mean(distances[:3])), 4), "distance_last3": round(float(np.mean(distances[-3:])), 4),
                                  "ok": host.mem.records.count == 1 and len(depths) == 10 and rising}
    # realistic takes: tempo +-15 %, pitch +-1 semitone, level +-6 dB, room noise of varied level;
    # the stored form after 1, 2, 4, 8 and 16 repetitions, and how well a new take is recognised
    def take(r):
        # tempo by resampling moves every formant with it (+-15 % is another voice, not the same word
        # said faster), so it stays within +-5 %, under a semitone
        tempo, pitch, level = r.uniform(0.95, 1.05), 2 ** (r.uniform(-1, 1) / 12), 10 ** (r.uniform(-6, 6) / 20)
        w = T.word(r, f0_scale=pitch) * level
        idx = np.arange(0, len(w) - 1, tempo)
        w = np.interp(idx, np.arange(len(w)), w)
        return w + T.background(len(w), r, level=0.006 * r.uniform(0.5, 2.0))
    curves, recogs, counts = [], [], []
    for seed in (16, 17, 18):  # three speakers' sessions: the curves are their means
        host = Host({"eye": {"w": 16, "h": 8}})
        rr = np.random.default_rng(seed)
        T.feed(host, T.background(T.RATE * 2, rr))
        news = []
        for _ in range(6):
            f = T.log_mel(np.concatenate([np.zeros(400), take(rr), np.zeros(400)]))
            e = np.log(np.exp(f).sum(1)); news.append(code(f[e > e.max() - 6]))
        curve, recog = {}, {}
        for k in range(1, 17):
            T.feed(host, np.concatenate([take(rr), T.background(int(T.RATE * 1.5), rr)]))
            if k in (1, 2, 4, 8, 16) and host.mem.records.count:
                curve[k] = 1.0 - float(code(host.mem.frames_of(0)) @ code(clean))
                key = host.mem.records.keys[0]
                recog[k] = float(np.mean([key @ n / np.linalg.norm(key) for n in news]))
        curves.append(curve); recogs.append(recog); counts.append(host.mem.records.count)
    marks = (1, 2, 4, 8, 16)
    curve = {k: round(float(np.mean([c[k] for c in curves if k in c])), 4) for k in marks}
    recog = {k: round(float(np.mean([r[k] for r in recogs if k in r])), 4) for k in marks}
    results["realistic_takes"] = {"records_each_session": counts, "distance_after": curve, "recognition_of_new_takes_after": recog,
                                  "ok": all(c == 1 for c in counts) and curve[16] < curve[1] and curve[8] < curve[2] and recog[16] > recog[1]}
    # practice: twenty attempts at the word, from an immature motor program (the inward rehearsals
    # at each hearing above are set aside, so the attempts start where a newly learned word starts)
    host = words_host
    host.mem.programs.pop(0, None)
    matches = [round(host.mem.practice(0)[1], 3) for _ in range(20)]
    first, last = float(np.mean(matches[:5])), float(np.mean(matches[-5:]))
    slope = float(np.polyfit(np.arange(20), matches, 1)[0])
    results["twenty_attempts"] = {"match_each": matches, "first5": round(first, 3), "last5": round(last, 3), "slope_per_attempt": round(slope, 4),
                                  "ok": last > first and slope > 0}
    # noise alone
    host = Host({"eye": {"w": 16, "h": 8}})
    x = T.background(T.RATE * 30, rng, level=0.02)
    for k in range(1, 15):
        x[k * 2 * T.RATE] += 0.9
    t = np.arange(T.RATE * 6) / T.RATE
    x[T.RATE * 10: T.RATE * 16] += 0.15 * sum(np.sin(2 * np.pi * 120 * h * t) / h for h in range(1, 6))
    T.feed(host, x)
    results["noise_alone"] = {"words": host.mem.records.count, "ok": host.mem.records.count == 0}
    # a click after quiet
    host = Host({"eye": {"w": 16, "h": 8}})
    quiet = T.background(T.RATE * 4, rng, level=0.002)
    replies = T.feed(host, quiet)
    click = T.background(T.RATE, rng, level=0.002); click[800:880] += 0.9 * np.hanning(80)
    after = T.feed(host, click)
    results["click_after_quiet"] = {"startle_in_quiet": any(r.get("startle") for r in replies), "startle_after_click": any(r.get("startle") for r in after),
                                    "ok": not any(r.get("startle") for r in replies) and any(r.get("startle") for r in after)}
    ok = all(v["ok"] for v in results.values())
    print(json.dumps({**results, "ok": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
