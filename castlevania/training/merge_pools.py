"""Merge per-game harvest parts (``harvest.py --part train`` / ``--part val`` run once per idle
offset and epsilon into ``<out>/parts/<name>/``) into one ``practice.pkl`` and one
``validation.npz`` in ``<out>``.

    python training/merge_pools.py runs/pool
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np


def main() -> None:
    out = Path(sys.argv[1])
    practice, summary = [], {"train_parts": [], "val_parts": []}
    for part in sorted(p for p in (out / "parts").glob("train_*") if p.is_dir()):
        with open(part / "practice.pkl", "rb") as handle:
            states = pickle.load(handle)
        practice += states
        summary["train_parts"].append({"part": part.name, "states": len(states)})
    with open(out / "practice.pkl", "wb") as handle:
        pickle.dump(practice, handle, protocol=pickle.HIGHEST_PROTOCOL)
    vals = [np.load(p / "validation.npz") for p in sorted(p for p in (out / "parts").glob("val_*") if p.is_dir())]
    names = sorted(set().union(*[set(v.files) for v in vals]) - {"x", "y"})
    merged = {"x": np.concatenate([v["x"] for v in vals]), "y": np.concatenate([v["y"] for v in vals])}
    for n in names:
        merged[n] = np.concatenate([v[n] if n in v.files else np.zeros(len(v["y"]), bool) for v in vals])
    np.savez_compressed(out / "validation.npz", **merged)
    counts: dict[str, int] = {}
    for s in practice:
        for tag in s["tags"] + [f'stage{s["stage"]}']:
            counts[tag] = counts.get(tag, 0) + 1
    summary.update(states=len(practice), tags=counts, validation_rows=int(len(merged["y"])))
    (out / "merge.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({"states": len(practice), "validation_rows": int(len(merged["y"]))}))


if __name__ == "__main__":
    main()
