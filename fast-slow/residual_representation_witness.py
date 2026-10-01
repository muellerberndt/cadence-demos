"""Constructive representation witness, not a trained capability result.

On the v=0 slice of x=tanh(u)+delta, y=tanh(v+delta), a two-patch
error-reading head can reproduce six physical outcomes with six engineered
parameters. The matched ordinary head cannot fit all six within .03.
The inequality below bounds its WHOLE parameter class, not a failed optimizer.
This is reuse of a predictor's nonlinear computation, not iterative memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from cadence._repair import settle

import cadence
from cadence import Cortex

ALPHA, DELTA, STEP, EPSILON = 0.01, 0.06, 0.6, 0.03
QUALIFICATION_TOLERANCE = 1e-6


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def certificate():
    """A linear functional annihilates every ordinary head's drive.

    At exact equilibrium z=atanh((1+alpha)*h)=a*v+b*x+c*u+b0.
    For u=0,s,2s and offset=+delta,-delta, let Ai average the two drives
    and k=tanh(2s)-2tanh(s). Then
    A2-2A1+A0-k*(z0plus-z0minus)/(2*delta)=0.
    The desired outcomes instead make this functional equal -k*q/d,
    where q=atanh((1+alpha)*tanh(delta)). If every output error were <=epsilon,
    the mean-value theorem would bound its magnitude by ||L||1*M*epsilon.
    Here M bounds the inverse-output derivative over that entire error band.
    For numerical qualification, enlarge epsilon by tau/(1+alpha), since
    |(1+alpha)*h-tanh(z)|<=tau. Outputs within epsilon of these targets
    are far from either state bound, so projected qualification implies this
    raw-gradient bound. The strict inequality survives that allowance.
    """
    k = math.tanh(2 * STEP) - 2 * math.tanh(STEP)
    coefficients = [0.5 - k / (2 * DELTA), 0.5 + k / (2 * DELTA), -1, -1, 0.5, 0.5]
    target = math.tanh(DELTA)
    q = math.atanh((1 + ALPHA) * target)
    rows = [
        {
            "u": u,
            "v": 0.0,
            "delta": delta,
            "x": math.tanh(u) + delta,
            "y": math.tanh(delta),
        }
        for u in (0.0, STEP, 2 * STEP)
        for delta in (DELTA, -DELTA)
    ]
    annihilation = [
        sum(c * value(r) for c, r in zip(coefficients, rows, strict=True))
        for value in (lambda r: r["v"], lambda r: r["x"], lambda r: r["u"], lambda _: 1)
    ]
    desired_functional = abs(
        sum(
            c * math.copysign(q, r["delta"])
            for c, r in zip(coefficients, rows, strict=True)
        )
    )
    effective_epsilon = EPSILON + QUALIFICATION_TOLERANCE / (1 + ALPHA)
    output_band = (1 + ALPHA) * (target + effective_epsilon)
    assert output_band < 1
    derivative_bound = (1 + ALPHA) / (1 - output_band**2)
    maximum_if_all_errors_small = (
        sum(map(abs, coefficients)) * derivative_bound * effective_epsilon
    )
    assert max(map(abs, annihilation)) < 1e-14
    assert desired_functional - maximum_if_all_errors_small > 0.01
    return {
        "rows": rows,
        "coefficients": coefficients,
        "annihilation": annihilation,
        "ordinary_hypothesis": "h=tanh(a*v+b*x+c*u+d)/(1+alpha), arbitrary finite coefficients; P parameters cannot change clamped x",
        "qualification_tolerance": QUALIFICATION_TOLERANCE,
        "effective_output_error_allowance": effective_epsilon,
        "inverse_derivative_bound": derivative_bound,
        "desired_functional": desired_functional,
        "maximum_if_all_errors_at_most_epsilon": maximum_if_all_errors_small,
        "strict_margin": desired_functional - maximum_if_all_errors_small,
        "ordinary_max_absolute_error_strictly_exceeds": EPSILON,
        "observer_error_weight": q / DELTA,
        "limits": "Analytic mean-value argument; numeric margins evaluated in float64, not formal interval arithmetic. Applies to free interior H; any H at state bound1 already misses target by much more than .03.",
    }


def public_graph(observer):
    c = Cortex(seed=0, state_prior=ALPHA, tolerance=1e-12)
    u, v = c.input("u", shape=1), c.input("v", shape=1)
    p = c.column("P", patches=1, inputs=u)
    h = (
        c.observer("H", patches=1, inputs=v, observes=p)
        if observer
        else c.column("H", patches=1, inputs=(v, p, u))
    )
    c.output("past", shape=1, reads=p)
    c.output("future", shape=1, reads=h)
    brain = c.build()
    assert brain.graph.edges == (
        ("input", 0, 0),
        ("input", 1, 1),
        ("state", 0, 1),
        ("residual", 0, 1) if observer else ("input", 0, 1),
    )
    assert len(brain.weights) + len(brain.biases) == 6
    return brain.graph


def engineered_query(graph, error_weight, row):
    # Fixed private-kernel fixture. No public Brain history/admission is forged.
    return settle(
        graph,
        [row["u"], row["v"]],
        [0.0, 0.0],
        [1.0, 1.0, 0.0, error_weight],
        [0.0, 0.0],
        clamps={0: row["x"]},
        state_prior=ALPHA,
        tolerance=1e-12,
        budget=2048,
    )


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    result = certificate()
    graph, ordinary_graph = public_graph(True), public_graph(False)
    records = []
    for row in result["rows"]:
        answer = engineered_query(graph, result["observer_error_weight"], row)
        assert answer["qualified"]
        error = abs(answer["state"][1] - row["y"])
        assert error < 1e-10
        records.append({"body": row, "answer": answer, "absolute_error": error})
    package = Path(cadence.__file__).resolve().parent
    receipt = {
        "schema": "residual-representation-witness/1",
        "alpha": ALPHA,
        "parameters": 6,
        "trained": False,
        "certificate": result,
        "queries": records,
        "engineered_fixture": {
            "weights": [1.0, 1.0, 0.0, result["observer_error_weight"]],
            "biases": [0.0, 0.0],
            "observer_edges": graph.edges,
            "ordinary_edges": ordinary_graph.edges,
            "custody": "Explicit private-kernel fixed coefficients; public builder verifies both topology classes. No learned snapshot or admitted history is claimed.",
        },
        "sources": {
            str(p.resolve()): sha(p)
            for p in [Path(__file__), *sorted(package.rglob("*.py"))]
        },
        "scope": "A fixed-topology representation advantage on six physical body cases. Ordinary H signals are(v,x,u); observer H signals are(v,x,eP). P is input-only and actually clamped. Ordinary P's two parameters serve the clean-prediction task but cannot influence H under this boundary; observer reuses them through eP. This is not superiority over every ordinary six-parameter topology or different observation interface. No acquired advantage, generalization, temporal memory, coupled-iteration benefit or efficiency claim.",
    }
    (out / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {
                "ordinary_max_error_exceeds": EPSILON,
                "observer_max_error": max(r["absolute_error"] for r in records),
                "strict_margin": result["strict_margin"],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    run(parser.parse_args().out)
