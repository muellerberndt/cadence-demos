"""The newborn's repertoire: African Grey calls cut from a licensed recording, in the ear's format.

    python tools/make_calls.py [--cache DIR]

Source: "Psittacus erithacus making some noise.ogg" by Amada44, Wikimedia Commons, CC BY 3.0
(https://commons.wikimedia.org/wiki/File:Psittacus_erithacus_making_some_noise.ogg). The tool
downloads it (checking Commons' SHA-1), decodes it to 16 kHz mono with ffmpeg, computes the ear's
log-mel frames (the library's front end: 25 ms Hann frames every 10 ms, 512-point spectrum, 40 mel
bands, natural log of the power plus 1e-6), cuts it into calls where the sound rises above its
background (onset to offset, 0.15 to 1.5 s), keeps up to ten varied calls, and writes
pack/calls.json: each call's frames and its measured traits. The parrot says them through its own
voice, so what it says and what it hears share one format.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np

SITE = Path(__file__).resolve().parents[1]
URL = "https://upload.wikimedia.org/wikipedia/commons/c/c3/Psittacus_erithacus_making_some_noise.ogg"
SHA1 = "536bd991cb9bbfd85febd7315571c848b22253e5"
PAGE = "https://commons.wikimedia.org/wiki/File:Psittacus_erithacus_making_some_noise.ogg"


def mel_bank(mels=40, rate=16000, fft=512):
    mel = lambda hz: 2595.0 * np.log10(1.0 + hz / 700.0)
    edges = 700.0 * (10 ** (np.linspace(mel(0.0), mel(rate / 2), mels + 2) / 2595.0) - 1.0)
    bins = np.fft.rfftfreq(fft, 1.0 / rate)
    bank = np.zeros((mels, len(bins)))
    for m in range(mels):
        lo, mid, hi = edges[m], edges[m + 1], edges[m + 2]
        bank[m] = np.clip(np.minimum((bins - lo) / max(mid - lo, 1e-9), (hi - bins) / max(hi - mid, 1e-9)), 0.0, None)
    return bank


def log_mel(x, frame=400, hop=160, fft=512):
    if len(x) < frame:
        x = np.pad(x, (0, frame - len(x)))
    count = 1 + (len(x) - frame) // hop
    idx = np.arange(frame)[None, :] + hop * np.arange(count)[:, None]
    power = np.abs(np.fft.rfft(x[idx] * np.hanning(frame)[None, :], fft)) ** 2
    return np.log(power @ mel_bank().T + 1e-6)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", type=Path, default=SITE / ".asset-cache")
    args = ap.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    src = args.cache / "grey_parrot_noise.ogg"
    if not src.exists():
        with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "cadence-demos-asset-fetch/1"}), timeout=120) as r:
            src.write_bytes(r.read())
    data = src.read_bytes()
    if hashlib.sha1(data).hexdigest() != SHA1:
        raise SystemExit("SHA-1 mismatch")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).astype(np.float64)
    x = x / max(1e-6, np.abs(x).max()) * 0.7
    F = log_mel(x)
    energy = np.log(np.exp(F).sum(1))
    floor = np.percentile(energy, 20)
    on = energy > floor + 4.0
    # onset to offset, with gaps under 60 ms closed
    calls, i = [], 0
    while i < len(on):
        if not on[i]:
            i += 1; continue
        j = i
        while j < len(on) and (on[j] or on[j:j + 6].any()):
            j += 1
        if 15 <= j - i <= 150:
            calls.append((i, j))
        i = j + 1
    def traits(a, b):
        f = F[a:b]
        p = np.exp(f)
        flat = float(np.exp(np.log(p + 1e-12).mean(1)).mean() / (p.mean(1).mean() + 1e-12))  # spectral flatness: low is tonal
        centre = float((p * np.arange(40)).sum() / p.sum())
        e = np.log(p.sum(1))
        bursts = int(((e[1:] > e.mean()) & (e[:-1] <= e.mean())).sum())
        dur = (b - a) / 100
        tag = "whistle" if flat < 0.08 else ("chatter" if bursts >= 4 else ("squawk" if centre > 18 else "call"))
        return {"duration_s": round(dur, 2), "flatness": round(flat, 3), "centre_band": round(centre, 1), "bursts": bursts, "tag": tag}
    def audio(a, b):  # the call's own sound (16 kHz), 30 ms either side, faded in and out over 10 ms
        lo, hi = max(0, a * 160 - 480), min(len(x), b * 160 + 480)
        y = x[lo:hi].copy(); ramp = np.linspace(0, 1, 160)
        y[:160] *= ramp; y[-160:] *= ramp[::-1]
        return np.round(y, 4).tolist()
    rows = [dict(start_s=round(a / 100, 2), **traits(a, b), frames=np.round(F[a:b], 3).tolist(), pcm=audio(a, b), pcm_rate=16000) for a, b in calls]
    # up to ten, varied: by tag first, then by duration
    keep, seen = [], {}
    for r in sorted(rows, key=lambda r: -r["duration_s"]):
        if seen.get(r["tag"], 0) < 3 and len(keep) < 10:
            keep.append(r); seen[r["tag"]] = seen.get(r["tag"], 0) + 1
    for k, r in enumerate(keep):
        r["id"] = f"grey-{k + 1}"
    out = {"source": {"title": "Psittacus erithacus making some noise", "author": "Amada44", "licence": "CC BY 3.0",
                      "licence_url": "https://creativecommons.org/licenses/by/3.0/", "page": PAGE, "file": URL, "sha1": SHA1,
                      "changes": "cut into calls; each call kept as its own sound (16 kHz) and as the ear's log-mel frames (40 bands, 10 ms)"},
           "format": "pcm: the call's sound at pcm_rate; frames: log-mel, 40 bands, 100 frames a second (cadence.speech.frontend.log_mel at its defaults)",
           "calls": keep}
    (SITE / "pack" / "calls.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"{len(calls)} calls found, {len(keep)} kept:", [(r["id"], r["tag"], r["duration_s"]) for r in keep])
    return 0


if __name__ == "__main__":
    sys.exit(main())
