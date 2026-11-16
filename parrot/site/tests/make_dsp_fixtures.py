"""Clips and their log-mel frames from the library's speech front end, for the page's parity test.

    python tests/make_dsp_fixtures.py --frontend <path to cadence/speech/frontend.py>

Writes tests/fixtures/dsp_clips.json: 20 fixed clips (tones, chirps, noise, clicks, silence, a
voiced vowel-like buzz), 0.25 s each at 16 kHz, and log_mel's frames of each.
"""
import argparse, importlib.util, json, sys
from pathlib import Path
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--frontend", required=True)
args = ap.parse_args()
spec = importlib.util.spec_from_file_location("frontend", args.frontend)
fe = importlib.util.module_from_spec(spec); sys.modules["frontend"] = fe; spec.loader.exec_module(fe)
rng = np.random.default_rng(332)
t = np.arange(4000) / 16000.0
clips = []
for k in range(20):
    kind = k % 6
    if kind == 0: x = 0.3 * np.sin(2 * np.pi * (200 + 300 * k) * t)
    elif kind == 1: x = 0.4 * np.sin(2 * np.pi * (150 * t + 3000 * t * t))
    elif kind == 2: x = 0.1 * rng.standard_normal(len(t))
    elif kind == 3: x = np.zeros(len(t)); x[rng.integers(0, len(t), 12)] = rng.uniform(-0.8, 0.8, 12)
    elif kind == 4: x = np.zeros(len(t)) + (1e-4 * rng.standard_normal(len(t)) if k > 10 else 0.0)
    else:
        f0 = 120 + 40 * k
        x = sum((0.5 / h) * np.sin(2 * np.pi * h * f0 * t) * np.exp(-((h * f0 - 700) / 600.0) ** 2) for h in range(1, 30))
    x = np.clip(x, -1, 1).astype(np.float32).astype(np.float64)
    clips.append({"samples": [round(float(v), 7) for v in x], "frames": np.round(fe.log_mel(x), 7).tolist()})
out = Path(__file__).resolve().parent / "fixtures" / "dsp_clips.json"
out.write_text(json.dumps({"source": "cadence.speech.frontend.log_mel at its defaults", "clips": clips}))
print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")
