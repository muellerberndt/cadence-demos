"""Fitted input standardization (external preprocessing, per BOOTSTRAP.md).

Doom retinas are heavily correlated; per-coordinate centering/scaling
conditions the settling problem. Statistics are fitted on bootstrap
examples only, saved beside the checkpoint, and applied identically in
training, evaluation, DAgger and the live server. This is disclosed
preprocessing, not a representation learned by Cadence.
"""

from __future__ import annotations

import json
import os

import numpy as np

CLIP = 3.0
SCALE = 0.2  # keeps standardized values within [-0.6, 0.6]


def fit(periphery: np.ndarray, fovea: np.ndarray) -> dict:
    out = {"clip": CLIP, "scale": SCALE}
    for name, arr in (("periphery", periphery), ("fovea", fovea)):
        a = arr.astype(np.float64)
        out[name] = {
            "mean": a.mean(axis=0).tolist(),
            "std": (a.std(axis=0) + 1e-3).tolist(),
        }
    return out


def apply(norms: dict, periphery: np.ndarray, fovea: np.ndarray):
    """Accepts one frame (any shape) or a batch (N, D); returns flat/(N, D)."""
    result = []
    for name, arr in (("periphery", periphery), ("fovea", fovea)):
        mean = np.asarray(norms[name]["mean"])
        arr = np.asarray(arr, np.float64)
        single = arr.size == mean.size
        a = arr.reshape(-1, mean.size) - mean
        a /= np.asarray(norms[name]["std"])
        np.clip(a, -norms["clip"], norms["clip"], out=a)
        a *= norms["scale"]
        result.append(a[0] if single else a)
    return result[0], result[1]


def save(norms: dict, path: str):
    with open(path, "w") as f:
        json.dump(norms, f)


def load(path: str) -> dict:
    return json.load(open(path))


def sibling_path(checkpoint_path: str) -> str:
    base = checkpoint_path
    for suffix in (".json.gz", ".gz", ".json"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base + ".norms.json"


def ensure_live_norms(path="data/live_norms.json",
                      corpus_path="data/corpus1/witnesses.npz") -> dict:
    """The live server's canonical transform, created from the corpus once."""
    if os.path.exists(path):
        return load(path)
    corpus = np.load(corpus_path)
    norms = fit(corpus["periphery"], corpus["fovea"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    save(norms, path)
    return norms
