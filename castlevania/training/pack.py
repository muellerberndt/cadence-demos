"""Pack a raised brain for the page: its optimizer history (the moments a further lesson would
read) is dropped, nothing the brain plays from changes, and ``evidence/receipt.json`` names the
file by SHA-256 beside its readings.

    python training/pack.py --brain runs/a/d300000.brain.npz --readings runs/eval.json \
        --run runs/a/result.json --out brain/brain.npz
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

HISTORY = ("velocity", "second_moment", "velocity_bias", "second_moment_bias")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--brain", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("brain/brain.npz"))
    p.add_argument("--readings", type=Path, default=None, help="evaluate.py's output for this brain")
    p.add_argument("--run", type=Path, default=None, help="the run's result.json")
    p.add_argument("--receipt", type=Path, default=Path("evidence/receipt.json"))
    p.add_argument("--notes", type=Path, default=None, help="a JSON object merged into the receipt")
    a = p.parse_args()
    data = dict(np.load(a.brain, allow_pickle=False))
    for key in HISTORY:
        if key in data:
            data[key] = np.zeros_like(data[key])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out, **data)
    from cadence import Brain
    import cadence
    brain = Brain.load(a.out, backend="cpu")
    layout = brain.describe().get("layout", {})
    receipt = {
        "brain": {"file": str(a.out), "sha256": hashlib.sha256(a.out.read_bytes()).hexdigest(),
                  "bytes": a.out.stat().st_size, "source_sha256": hashlib.sha256(a.brain.read_bytes()).hexdigest(),
                  "cadence": cadence.__version__, "inputs": layout.get("inputs"), "modules": layout.get("modules"),
                  "neurons": layout.get("neurons"), "synapses": layout.get("synapses"),
                  "learner": {k: getattr(brain.learner.config, k) for k in brain.learner.config.__slots__
                              if isinstance(getattr(brain.learner.config, k), (int, float, bool))}},
    }
    if a.readings is not None:
        receipt["readings"] = json.loads(a.readings.read_text())
    if a.run is not None:
        run = json.loads(a.run.read_text())
        receipt["run"] = {"config": run.get("config"), "counters": run.get("counters"),
                          "seconds": run.get("seconds"), "library": run.get("library"),
                          "evaluations": [{k: e.get(k) for k in ("decision", "stage", "past_stairs", "stage3",
                                                                   "stage4", "lives_lost", "progress")}
                                          | {"predict": (e.get("predict") or {}).get("agreement")}
                                          for e in run.get("evaluations", [])]}
    if a.notes is not None:
        receipt.update(json.loads(a.notes.read_text()))
    a.receipt.parent.mkdir(parents=True, exist_ok=True)
    a.receipt.write_text(json.dumps(receipt, indent=1, default=float) + "\n")
    print(json.dumps(receipt["brain"], indent=1))


if __name__ == "__main__":
    main()
