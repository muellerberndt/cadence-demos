"""Measure retained-state repair without relaxing whole-brain qualification.

This is an untrained numerical control, not evidence of learned routine,
attention, outcome valuation or useful reflection. Frozen observer interventions
are diagnostic counterexamples only and never admitted as global actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from cadence import Brain, Cortex
from cadence import _repair
from cadence.brain import IMPLEMENTATION


def layout(seed, kind):
    cortex = Cortex(seed=seed, tolerance=1e-7, settle_budget=4096)
    senses = cortex.input("senses", shape=4)
    base = cortex.column("routine", patches=14 if kind == "flat" else 8, inputs=senses)
    if kind == "recursive":
        observer = cortex.observer("context", patches=4, observes=base)
        cortex.observer("reflection", patches=2, observes=(base, observer))
    cortex.output("action", shape=2, reads=base)
    return cortex.build()


def diagnostic(result):
    return {
        key: result[key]
        for key in (
            "qualified",
            "sweeps",
            "stationarity",
            "prediction_residual",
            "work",
        )
    }


def run():
    cases = []
    initial = (0.2, -0.3, 0.1, 0.4)
    for seed in (2, 7, 11, 19, 29):
        for kind in ("flat", "recursive"):
            founder = layout(seed, kind)
            for scenario in ("constant", "smooth", "disturbed"):
                warm = Brain.from_snapshot(founder.snapshot())
                first = warm.step({"senses": initial})
                assert first["qualified"]
                rows = []
                for tick in range(32):
                    change = (
                        0.0
                        if scenario == "constant"
                        else 0.05 * math.sin((tick + 1) / 8)
                        if scenario == "smooth"
                        else (0.7 if tick >= 16 else 0.0)
                    )
                    values = tuple(v + change for v in initial)
                    cold_result = founder.settle({"senses": values})
                    warm_result = warm.step({"senses": values})
                    assert cold_result["qualified"] and warm_result["qualified"]
                    rows.append(
                        {
                            "tick": tick,
                            "inputs": values,
                            "cold": diagnostic(cold_result),
                            "retained": diagnostic(warm_result),
                            "max_output_difference": max(
                                abs(a - b)
                                for a, b in zip(
                                    cold_result["outputs"]["action"],
                                    warm_result["outputs"]["action"],
                                    strict=True,
                                )
                            ),
                        }
                    )
                if scenario == "constant":
                    assert all(row["retained"]["sweeps"] == 0 for row in rows)
                cases.append(
                    {
                        "seed": seed,
                        "kind": kind,
                        "scenario": scenario,
                        "patches": warm.graph.n_patches,
                        "edges": len(warm.graph.edges),
                        "initial": diagnostic(first),
                        "rows": rows,
                    }
                )
    counterexamples = []
    for seed in (2, 7, 11, 19, 29):
        brain = layout(seed, "recursive")
        before = brain.step({"senses": initial})
        assert before["qualified"]
        changed = (0.9, 0.4, 0.8, 1.1)
        conditional = brain.settle(
            {"senses": changed},
            interventions={
                "context": brain.state[8:12],
                "reflection": brain.state[12:],
            },
        )
        assert conditional["qualified"]
        global_check = _repair.settle(
            brain.graph,
            changed,
            conditional["state"],
            brain.weights,
            brain.biases,
            budget=0,
            tolerance=brain.config["tolerance"],
            state_prior=brain.config["state_prior"],
        )
        assert not global_check["qualified"]
        repaired = brain.step({"senses": changed})
        repeated = brain.step({"senses": changed})
        assert repaired["qualified"] and repeated["qualified"]
        assert repeated["sweeps"] == 0
        counterexamples.append(
            {
                "seed": seed,
                "conditional": diagnostic(conditional),
                "unclamped_global_check": diagnostic(global_check),
                "full_repair": diagnostic(repaired),
                "after_restoration": diagnostic(repeated),
            }
        )
    return {
        "protocol": "untrained retained-state control; 14 patches in both layouts",
        "implementation": dict(IMPLEMENTATION),
        "collector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cases": cases,
        "frozen_observer_counterexamples": counterexamples,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"cases": len(report["cases"]), "counterexamples": 5}))
