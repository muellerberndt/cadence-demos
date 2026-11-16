"""A laptop's microphone in a room, for the page's checks: a clean take band-limited to 100 Hz to 7 kHz, a mild
room reverberation, background noise at a chosen level below the speech, the level moved; and sounds that are
no speech (a cough, a breath, typing, a click, a door, a chair's scrape, a fan, a hum, a phone's ring, a clap).
All at 16 kHz, made from random numbers and sines alone."""
import numpy as np

SR = 16000


def _band(x, lo=100.0, hi=7000.0):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    g = 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-6)) ** 4) / np.sqrt(1 + (f / hi) ** 8)
    return np.fft.irfft(X * g, len(x)).astype(np.float32)


def _room(rng, rt60=0.25, wet=0.25):
    n = int(rt60 * SR); t = np.arange(n) / SR
    h = rng.normal(size=n) * np.exp(-6.9 * t / rt60); h[: int(0.004 * SR)] = 0
    h = wet * h / np.sqrt((h ** 2).sum()); h[0] = 1.0
    return h.astype(np.float32)


def noise_like(n, rng):
    """A room's background: a fan-like hiss, stronger in the low bands, with a low hum."""
    w = rng.normal(size=n + 2); X = np.fft.rfft(w); f = np.fft.rfftfreq(len(w), 1 / SR)
    x = np.fft.irfft(X / np.maximum(f, 40.0) ** 0.6, len(w))[:n]
    x += 0.3 * np.std(x) * np.sin(2 * np.pi * 120 * np.arange(n) / SR)
    return (x / (np.std(x) + 1e-9)).astype(np.float32)


def speech_level(x):
    e = np.convolve(np.asarray(x, np.float64) ** 2, np.ones(400) / 400, mode="same")
    return float(np.sqrt(np.mean(e[e > 0.1 * e.max()]))) if e.max() > 0 else 1e-3


def laptop(x, rng, snr_db=20.0, gain_db=0.0, noise=None, level=None):
    """A clean take as a laptop's microphone hears it. `level`: the speech level the noise is set against (the
    take's own loud part by default)."""
    y = _band(np.asarray(x, np.float32))
    y = np.convolve(y, _room(rng))[: len(y)].astype(np.float32)
    nz = noise_like(len(y), rng) if noise is None else noise[: len(y)]
    y = y + nz * (speech_level(y) if level is None else level) / (10 ** (snr_db / 20))
    return np.clip(y * 10 ** (gain_db / 20), -1, 1).astype(np.float32)


def _noise(n, rng, lo=None, hi=None):
    x = rng.normal(size=n)
    if lo or hi:
        X = np.fft.rfft(x); f = np.fft.rfftfreq(n, 1 / SR); g = np.ones_like(f)
        if lo: g *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-6)) ** 6)
        if hi: g *= 1 / np.sqrt(1 + (f / hi) ** 6)
        x = np.fft.irfft(X * g, n)
    return x / (np.std(x) + 1e-9)


def cough(rng):
    out = []
    for _ in range(2):
        n = int(rng.uniform(0.12, 0.22) * SR); t = np.arange(n) / SR
        env = np.minimum(t / 0.008, 1) * np.exp(-t / rng.uniform(0.04, 0.08))
        x = _noise(n, rng, 300, 5000) * env
        if rng.random() < 0.5:  # a short voiced tail
            x += 0.3 * env * np.sign(np.sin(2 * np.pi * rng.uniform(90, 160) * t)) * (t > 0.04)
        out += [x, np.zeros(int(rng.uniform(0.05, 0.12) * SR))]
    return np.concatenate(out) * 0.4


def breath(rng):
    n = int(rng.uniform(0.4, 0.8) * SR); t = np.arange(n) / n
    return _noise(n, rng, 500, 6000) * np.sin(np.pi * t) ** 2 * 0.15


def typing(rng):
    x = np.zeros(int(1.2 * SR))
    for _ in range(6):
        at = int(rng.uniform(0, 1.1) * SR); n = int(0.012 * SR)
        x[at: at + n] += _noise(n, rng, 1500) * np.exp(-np.arange(n) / (0.003 * SR)) * rng.uniform(0.2, 0.5)
    return x


def click(rng):
    n = int(0.006 * SR)
    return np.concatenate([_noise(n, rng, 2000) * np.exp(-np.arange(n) / (0.001 * SR)) * 0.6, np.zeros(SR // 10)])


def door(rng):
    n = int(0.25 * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 70 * t) * np.exp(-t / 0.05) + 0.3 * _noise(n, rng, None, 800) * np.exp(-t / 0.03)) * 0.6


def scrape(rng):
    n = int(0.5 * SR); t = np.arange(n) / n
    return _noise(n, rng, 800, 3500) * np.sin(np.pi * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 23 * t)) * 0.3


def fan(rng):
    n = int(2.5 * SR)
    return _noise(n, rng, None, 3000) * np.minimum(np.arange(n) / (0.2 * SR), 1) * 0.12


def hum(rng):
    n = int(2.0 * SR); t = np.arange(n) / SR
    return sum(np.sin(2 * np.pi * 120 * k * t) / k for k in (1, 2, 3, 5)) * np.minimum(t / 0.1, 1) * 0.1


def ring(rng):
    n = int(0.6 * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 1318 * t) + np.sin(2 * np.pi * 1568 * t)) * (np.sin(2 * np.pi * 12 * t) > 0) * 0.2


def clap(rng):
    n = int(0.05 * SR)
    return np.concatenate([_noise(n, rng, 800, 6000) * np.exp(-np.arange(n) / (0.008 * SR)) * 0.7, np.zeros(SR // 10)])


NOT_SPEECH = {"cough": cough, "breath": breath, "typing": typing, "click": click, "door": door, "scrape": scrape, "fan": fan, "hum": hum, "ring": ring, "clap": clap}
