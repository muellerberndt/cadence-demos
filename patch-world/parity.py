"""Write library reference values for test.js.

    python3 -m pip install cadence-net==0.70.0
    python3 parity.py

Two small brains are built with the population solver of cadence-net 0.70.0:
one whose populations read live states only, and one whose top population is
an observer that also reads exact prediction errors. For each, the library's
energy and analytic derivatives at a fixed state, its settled state, and its
relations after one admitted witness are written to fixtures/. test.js loads
the same graphs into core.js and compares.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import cadence
from cadence.experimental.equilibrium import Cortex, _repair

VERSION = "0.70.0"
SENSES = [1, 0, 0, 1, 0, 1]
TARGET = 0.5
OUT = Path(__file__).resolve().parent / "fixtures" / f"library-{VERSION}.json"


def build(observer):
    cortex = Cortex(seed=5, tolerance=1e-9, parameter_prior=0.3)
    senses = cortex.input("senses", shape=len(SENSES))
    perception = cortex.column("perception", patches=4, inputs=senses)
    middle = cortex.column("middle", patches=3, inputs=(senses, perception))
    if observer:
        policy = cortex.observer("policy", patches=3, inputs=senses, observes=(perception, middle))
    else:
        policy = cortex.column("policy", patches=3, inputs=(senses, perception, middle))
    cortex.output("value", shape=1, reads=policy, indices=(1,))
    return cortex.build()


def case(name, observer):
    brain = build(observer)
    graph, config = brain.graph, brain.config
    weights, biases = list(brain.weights), list(brain.biases)
    reads = [
        [[graph.edges[edge][0], graph.edges[edge][1], weights[edge]] for edge in graph.incoming[patch]]
        for patch in range(graph.n_patches)
    ]
    # A fixed state away from equilibrium, with anchors away from the relations,
    # so every term of the energy and every derivative is exercised.
    state = [0.6 * math.sin(1.0 + 1.7 * i) for i in range(graph.n_patches)]
    probe_biases = [0.05 * math.cos(2.0 + i) for i in range(graph.n_patches)]
    anchor_weights = [0.8 * w for w in weights]
    anchor_biases = [0.0] * graph.n_patches
    probe = _repair.evaluate(
        graph, SENSES, state, weights, probe_biases,
        state_prior=config["state_prior"], anchor_weights=anchor_weights,
        anchor_biases=anchor_biases, parameter_prior=config["parameter_prior"],
    )
    settled = brain.settle({"senses": SENSES})
    assert settled["qualified"], settled["reason"]
    clamp = brain.inspect()["populations"]
    clamp = sum(p["patches"] for p in clamp[:-1]) + 1
    learned = brain.observe({"senses": SENSES}, {"value": [TARGET]})
    assert learned["accepted"] and learned["qualified"], learned["reason"]
    by_patch = lambda values: [[values[edge] for edge in graph.incoming[patch]] for patch in range(graph.n_patches)]
    return {
        "name": name,
        "inputs": len(SENSES),
        "senses": SENSES,
        "edge_kinds": sorted({kind for kind, _, _ in graph.edges}),
        "statePrior": config["state_prior"],
        "parameterPrior": config["parameter_prior"],
        "reads": reads,
        "biases": biases,
        "probe": {
            "state": state,
            "biases": probe_biases,
            "anchorScale": 0.8,
            "energy": probe["energy"],
            "errors": list(probe["errors"]),
            "gradientState": list(probe["gradient_state"]),
            "gradientWeights": by_patch(probe["gradient_weights"]),
            "gradientBiases": list(probe["gradient_biases"]),
        },
        "settled": {
            "state": list(settled["state"]),
            "energy": settled["energy"],
            "stationarity": settled["stationarity"],
            "sweeps": settled["sweeps"],
        },
        "learned": {
            "clamp": clamp,
            "target": TARGET,
            "state": list(learned["state"]),
            "weights": by_patch(learned["weights"]),
            "biases": list(learned["biases"]),
            "energy": learned["energy"],
            "stationarity": learned["stationarity"],
            "sweeps": learned["sweeps"],
        },
    }


def main():
    if cadence.__version__ != VERSION:
        raise SystemExit(f"parity.py needs cadence-net=={VERSION}; found {cadence.__version__}")
    fixture = {
        "library": f"cadence-net=={VERSION}",
        "solver": "cadence.experimental.equilibrium",
        "tolerance": 1e-9,
        "cases": [case("state-coupled", False), case("observer", True)],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(fixture, indent=1, allow_nan=False) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
