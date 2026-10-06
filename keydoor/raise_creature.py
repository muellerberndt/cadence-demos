"""Raise a creature for the page: one continuing life through rule A of the frozen key-door
protocol, saved mid-life.

    .venv/bin/python raise_creature.py --seed 5 --delay 5 --trips 500 --out runs/d5-s5

Writes ``brain.npz`` (the brain with any outcome it awaits) and ``run.json`` (the life's
readings: fed share, wrong interactions and arousal over the last 50 trips, the lag, the work,
the Cadence version). The creature is saved at the end of a trip, with the door's outcome
pending, exactly as the page will resume it. Nothing of rule B is lived here: the key moves
only when the page's visitor moves it.
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path

import numpy as np

from keydoor.host import Host
from keydoor.world import CHEST


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--seed", type=int, default=5)
    p.add_argument("--delay", type=int, default=5)
    p.add_argument("--trips", type=int, default=500)
    p.add_argument("--out", default="runs/raised")
    a = p.parse_args()
    warnings.simplefilter("ignore")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    host = Host(None, a.delay, a.seed, keyed=CHEST)
    began = time.time()
    result = host.run(trips=a.trips, limit=a.trips * 14 + 100)
    rows = result["rows"]
    fed = [r["fed"] for r in rows if not r["cut"]]
    window = 20
    lag = next((k for k in range(len(fed) - window + 1) if np.mean(fed[k:k + window]) >= 0.9), None)
    path = out / "brain.npz"
    host.brain.save(str(path))
    status = host.status()
    run = {
        "seed": a.seed,
        "delay": a.delay,
        "trips": a.trips,
        "keyed": "chest",
        "fed_last_50": float(np.mean(fed[-50:])),
        "wrong_last_50": float(np.mean([r["wrongs"] for r in rows if not r["cut"]][-50:])),
        "aroused_last_half": float(np.mean([r["aroused"] for r in rows[len(rows) // 2:]])),
        "lag": lag,
        "cuts": sum(r["cut"] for r in rows),
        "work": status["work"],
        "describe": host.describe(),
        "seconds": round(time.time() - began, 1),
        "saved_with_outcome_pending": host.world.pending is not None,
    }
    (out / "run.json").write_text(json.dumps(run, indent=1))
    print(json.dumps({k: run[k] for k in ("fed_last_50", "wrong_last_50", "aroused_last_half", "lag", "seconds")}))


if __name__ == "__main__":
    main()
