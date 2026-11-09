"""Frozen greedy evaluation of saved brains from power-on (the eye from the brain's input count).

    python training/evaluate.py --brains a.brain.npz b.brain.npz --starts 0 7 14 3 10 21 28 35 42 \
        --decisions 1500 --out runs/eval.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from common import Body, eye_of_inputs, frozen_evaluation
from common import summarize


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--brains", nargs="+", required=True)
    p.add_argument("--starts", type=int, nargs="+", default=[0, 7, 14, 3, 10, 21, 28, 35, 42])
    p.add_argument("--decisions", type=int, default=1500)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    from cadence import Brain
    body = Body()
    rows = []
    for path in a.brains:
        t0 = time.time()
        brain = Brain.load(path, backend="cpu")
        eye = eye_of_inputs(len(brain.sensory_index))
        ev = frozen_evaluation(brain, body, a.starts, a.decisions, eye=eye)
        s = summarize(ev)
        s.pop("stream", None)
        row = {"brain": path, "eye": eye, "starts": a.starts, "decisions": a.decisions, **s,
               "games": [{k: g[k] for k in ("noops", "decisions", "furthest_stage", "progress", "lives_lost",
                                            "world_x", "deaths_by_stage", "bat_hp_dealt", "max_wx")}
                         for g in ev["greedy"]],
               "seconds": round(time.time() - t0, 1)}
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("brain", "stage", "past_stairs", "stage3", "stage4", "lives_lost", "seconds")}), flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rows, indent=1, default=float) + "\n")


if __name__ == "__main__":
    main()
