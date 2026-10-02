"""Record reference values from the Python edition for web/parity.mjs.

Run from rover-lab/ in an environment with cadence-net==0.70.0:

    python web/tools/make_parity_fixture.py

Writes web/fixtures/parity.json: the wiring and birth weights of both brain
layouts, isolated solver calls, and whole automatic lives (every command,
forecast and hit of every model) without wall-clock fields.

The solver calls are recorded twice. `solver` uses the library as released.
`solver_exact` replaces the two operations the solver takes from the C library
(tanh, and pow for squaring a prediction) with plain arithmetic, so that the
JavaScript edition, given the same formula, must reproduce every recorded
value bit for bit.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import cadence  # noqa: E402
from cadence.experimental.equilibrium import _repair  # noqa: E402
from models import make_model  # noqa: E402
from rover import ACTIONS, PROTOCOL, Life, body_motion, route, summarize  # noqa: E402

def arithmetic_tanh(x):
    """tanh from additions, multiplications and divisions only, the same on every IEEE-754 machine."""
    a = abs(x)
    if a > 20.0:
        return 1.0 if x > 0 else -1.0
    y = 2.0 * a / 1024.0
    term = total = 1.0
    for k in range(1, 14):
        term = term * y / k
        total += term
    for _ in range(10):
        total = total * total
    result = (total - 1.0) / (total + 1.0)
    return result if x >= 0 else -result


class Prediction(float):
    """A float whose square is one multiplication instead of the C library's pow."""

    def __pow__(self, exponent):
        if exponent != 2:
            raise ValueError("the solver only squares predictions")
        return float(self) * float(self)


class ArithmeticMath:
    """The math module with tanh replaced, for the bit-exact section of the fixture."""

    @staticmethod
    def tanh(x):
        return Prediction(arithmetic_tanh(x))

    def __getattr__(self, name):
        return getattr(math, name)


TIMING = ("latencies_p95_ms", "command_ages_p95_ms", "queue_delays_p95_ms", "deadline_misses")


def births():
    records = []
    for kind in ("coupled", "observer"):
        for seed in (0, 17, 29, 101, 2**31 - 1):
            brain = make_model(kind, seed).brain
            records.append({"kind": kind, "seed": seed, "edges": [list(edge) for edge in brain.graph.edges],
                            "residual_order": list(brain.graph.residual_order), "weights": list(brain.weights)})
    return records


def solver_calls(count):
    """Each kind of call on a brain with some experience, with its full result."""
    records = []
    for kind in ("coupled", "observer"):
        model = make_model(kind, 17)
        calls = []
        for index in range(count):
            action = ACTIONS[(index * 5) % len(ACTIONS)]
            motion = body_motion(action, 0.35 if (index // 20) % 2 else 1.0)
            result = model.brain.observe({"motors": action}, {"motion_readout": motion}, source="witness")
            calls.append({"call": "observe", "action": action, "motion": motion})
            calls[-1].update({key: result[key] for key in ("qualified", "sweeps", "reason", "energy", "stationarity")})
            calls[-1].update(state=list(result["state"]), weights=list(result["weights"]), biases=list(result["biases"]),
                             errors=list(result["errors"]))
            probe = ACTIONS[(index * 7 + 3) % len(ACTIONS)]
            for call in ("settle", "step"):
                result = getattr(model.brain, call)({"motors": probe})
                calls.append({"call": call, "action": probe, "state": list(result["state"]),
                              "errors": list(result["errors"]),
                              **{key: result[key] for key in ("qualified", "sweeps", "reason", "energy", "stationarity")}})
        records.append({"kind": kind, "seed": 17, "calls": calls})
    return records


def life(seed, observers=False):
    world = Life(seed, observers=observers)
    bootstrap = {kind: {key: value for key, value in row.items() if key != "seconds"}
                 for kind, row in world.bootstrap.items()}
    while world.step < sum(length for _, length in PROTOCOL["phases"]):
        world.tick()
    rows = {}
    for row in world.rows:
        rows.setdefault(row["model"], []).append(
            [ACTIONS.index(row["action"]), *(round(value, 12) for value in row["prediction"]), int(row["hit"])])
    metrics = {kind: {phase: {key: value for key, value in values.items() if key not in TIMING}
                      for phase, values in summarize(arm["metrics"]).items()}
               for kind, arm in world.arms.items()}
    final = {kind: {"state": list(arm["model"].brain.state), "weights": list(arm["model"].brain.weights),
                    "biases": list(arm["model"].brain.biases), "pose": arm["pose"]}
             for kind, arm in world.arms.items() if hasattr(arm["model"], "brain")}
    return {"seed": seed, "observers": observers, "targets": world.targets[:16],
            "bootstrap_schedule": world.bootstrap_schedule, "bootstrap": bootstrap, "rows": rows,
            "metrics": metrics, "final": final, "events": world.events}


def main():
    library_math = _repair.math
    _repair.math = ArithmeticMath()
    try:
        exact = solver_calls(120)
    finally:
        _repair.math = library_math
    fixture = {"cadence": cadence.__version__, "python": sys.version.split()[0], "protocol": PROTOCOL,
               "actions": ACTIONS, "route_17": route(17)[:8], "births": births(), "solver_exact": exact,
               "solver": solver_calls(40), "lives": [life(17, observers=True), life(29)]}
    path = HERE.parent / "fixtures" / "parity.json"
    path.write_text(json.dumps(fixture, separators=(",", ":"), allow_nan=False) + "\n")
    print(f"wrote {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
