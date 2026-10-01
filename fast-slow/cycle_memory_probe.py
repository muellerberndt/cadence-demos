"""Frozen private-kernel state-cycle diagnostic; no learning or public API claim.

Freeze before run. Engineered fixed gains are candidate genes, not learned
memory. Every gain/control is retained. This uses the same patch energy;
state cycles are presently unavailable through the public Cortex builder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

from cadence._repair import Graph, evaluate, settle

import cadence

GAINS = (0.0, 0.5, 1.0, 1.25, 1.5, 2.0, 3.0)
CUES = (-1.0, 1.0)
DELAYS = (1, 8, 128)
ALPHA = 0.01
BUDGET = 2048
TOLERANCE = 1e-10


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)


def read(path):
    return json.loads(path.read_text())


def sources():
    package = Path(cadence.__file__).resolve().parent
    return {
        str(p.resolve()): sha(p)
        for p in sorted([*package.rglob("*.py"), Path(__file__)])
    }


def freeze(root):
    root.mkdir(parents=True, exist_ok=False)
    write(
        root / "protocol.json",
        {
            "schema": "private-cycle-memory-probe/1",
            "sources": sources(),
            "gains": GAINS,
            "cue_weight": 2.0,
            "bias": 0.0,
            "cues": CUES,
            "blank_delays": DELAYS,
            "state_prior": ALPHA,
            "tolerance": TOLERANCE,
            "budget": BUDGET,
            "deadline_seconds": 60,
            "cases": [{"gain": g, "cue": u} for g in GAINS for u in CUES],
            "law": "p=tanh(2*u+g*x); E=(x-p)^2/2+0.01*x^2/2; parameters never change.",
            "controls": "For each gain: cold neutral from zero. Each signed cue starts at zero; separate blank sequences1,8,128 restart from the same written state. From the128-blank state give the opposite cue and128 blanks. Reset state to zero then query neutral. Every call freshly qualifies and is retained.",
            "derivatives": "Compare scalar energy and all state/weight/bias derivatives against explicit equations and centered finite differences. Repeat independent three-patch observed-only/teacher-clamped equations with frozen weights.",
            "scope": "Private Graph state cycles, no builder modification, no training, no observer-advantage or planning claim. Engineered genes are not learned retention. Positive-state energy at neutral input is above zero-state energy; any persistent branch is a local metastable equilibrium, not the global minimum.",
        },
    )


def scalar_energy(u, x, cue_weight, gain, bias, alpha=ALPHA):
    prediction = math.tanh(cue_weight * u + gain * x + bias)
    return 0.5 * ((x - prediction) ** 2 + alpha * x * x)


def scalar_audit(u, x, cue_weight, gain, bias):
    prediction = math.tanh(cue_weight * u + gain * x + bias)
    error, d = x - prediction, 1 - prediction**2
    gradients = (
        error * (1 - gain * d) + ALPHA * x,
        -error * d * u,
        -error * d * x,
        -error * d,
    )
    values = [x, cue_weight, gain, bias]
    numerical = []
    for i in range(4):
        upper, lower = list(values), list(values)
        upper[i] += 1e-6
        lower[i] -= 1e-6
        numerical.append((scalar_energy(u, *upper) - scalar_energy(u, *lower)) / 2e-6)
    gap = max(abs(a - b) for a, b in zip(gradients, numerical, strict=True))
    if gap > 5e-8:
        raise AssertionError(("independent finite difference", gap))
    hessian = (1 - gain * d) ** 2 + 2 * error * gain * gain * prediction * d + ALPHA
    return {
        "energy": scalar_energy(u, *values),
        "predictions": [prediction],
        "errors": [error],
        "gradient_state": [gradients[0]],
        "gradient_weights": list(gradients[1:3]),
        "gradient_biases": [gradients[3]],
        "finite_difference_max_abs_error": gap,
        "scalar_state_hessian": hessian,
    }


def check_close(actual, expected, label, tolerance=2e-13):
    if len(actual) != len(expected) or any(
        abs(a - b) > tolerance for a, b in zip(actual, expected, strict=True)
    ):
        raise AssertionError(label)


def teacher_audit():
    graph = Graph(
        2,
        3,
        (
            ("input", 0, 0),
            ("state", 0, 1),
            ("input", 1, 2),
            ("state", 1, 2),
            ("residual", 1, 2),
        ),
    )
    weights, biases = (1.0, 2.0, 1.0, 0.0, 1.0), (0.0, 0.0, 0.0)

    def energy(state, w, b):
        m, x, h = state
        pm = math.tanh(b[0])
        pp = math.tanh(b[1] + w[1] * m)
        ep = x - pp
        ph = math.tanh(b[2] + w[3] * x + w[4] * ep)
        return 0.5 * (
            (m - pm) ** 2 + ep**2 + (h - ph) ** 2 + ALPHA * (m * m + x * x + h * h)
        )

    rows = []
    for label, clamps in (
        ("prior", {}),
        ("observed", {1: 0.1}),
        ("teacher", {1: 0.1, 2: 0.4}),
    ):
        result = settle(
            graph,
            (0.0, 0.0),
            (0.0, 0.0, 0.0),
            weights,
            biases,
            clamps=clamps,
            state_prior=ALPHA,
            tolerance=TOLERANCE,
            budget=BUDGET,
        )
        analytical = evaluate(
            graph, (0.0, 0.0), result["state"], weights, biases, state_prior=ALPHA
        )
        check_close(
            [result["energy"]],
            [energy(result["state"], weights, biases)],
            "three-patch energy",
        )
        groups = [list(result["state"]), list(weights), list(biases)]
        gaps = []
        for j, key in enumerate(
            ("gradient_state", "gradient_weights", "gradient_biases")
        ):
            for i, derivative in enumerate(analytical[key]):
                upper, lower = [list(v) for v in groups], [list(v) for v in groups]
                upper[j][i] += 1e-6
                lower[j][i] -= 1e-6
                numerical = (energy(*upper) - energy(*lower)) / 2e-6
                gaps.append(abs(derivative - numerical))
        if max(gaps) > 5e-8:
            raise AssertionError("three-patch finite differences")
        rows.append(
            {
                "label": label,
                "clamps": clamps,
                **result,
                "finite_difference_max_abs_error": max(gaps),
            }
        )
    return {
        "equations": "pM=0; pP=tanh(2*m); eP=x-pP; pH=tanh(eP); E=sum(e²)/2+.01*sum(state²)/2. Teacher H is a hypothetical clamp, never a forecast score.",
        "weights": weights,
        "biases": biases,
        "cases": rows,
    }


def run(root):
    protocol = read(root / "protocol.json")
    if protocol["sources"] != sources():
        raise ValueError("frozen sources differ")
    expected_design = {
        "gains": list(GAINS),
        "cues": list(CUES),
        "blank_delays": list(DELAYS),
        "cue_weight": 2.0,
        "bias": 0.0,
        "state_prior": ALPHA,
        "tolerance": TOLERANCE,
        "budget": BUDGET,
        "deadline_seconds": 60,
        "cases": [{"gain": g, "cue": u} for g in GAINS for u in CUES],
    }
    if any(protocol[key] != value for key, value in expected_design.items()):
        raise ValueError("frozen design differs")
    if (root / "calls.jsonl").exists() or (root / "receipt.json").exists():
        raise ValueError("preserve the previous diagnostic")
    started = time.monotonic()
    graph = Graph(1, 1, (("input", 0, 0), ("state", 0, 0)))
    cases, cold, work, calls = [], [], Counter(), 0
    unqualified, worst_fd = 0, 0.0

    def call(gain, cue, state, identity):
        nonlocal calls, unqualified, worst_fd
        if time.monotonic() - started > 60:
            raise TimeoutError("diagnostic deadline")
        weights, biases = (2.0, gain), (0.0,)
        result = settle(
            graph,
            (cue,),
            (state,),
            weights,
            biases,
            learn=False,
            state_prior=ALPHA,
            tolerance=TOLERANCE,
            budget=BUDGET,
        )
        if result["weights"] != weights or result["biases"] != biases:
            raise AssertionError("fixed parameters changed")
        audit = scalar_audit(cue, result["state"][0], *weights, biases[0])
        raw = evaluate(
            graph, (cue,), result["state"], weights, biases, state_prior=ALPHA
        )
        check_close([result["energy"]], [audit["energy"]], "scalar energy")
        for key in (
            "predictions",
            "errors",
            "gradient_state",
            "gradient_weights",
            "gradient_biases",
        ):
            check_close(raw[key], audit[key], key)
        worst_fd = max(worst_fd, audit["finite_difference_max_abs_error"])
        calls += 1
        unqualified += not result["qualified"]
        work.update(result["work"])
        record = {
            "identity": identity,
            "gain": gain,
            "input": cue,
            "initial_state": state,
            **result,
            "continued_state": result["state"][0] if result["qualified"] else state,
            "independent_audit": audit,
        }
        with (root / "calls.jsonl").open("a") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def blanks(gain, state, duration, identity):
        first = None
        count = 0
        for tick in range(duration):
            result = call(gain, 0.0, state, [*identity, tick + 1])
            if first is None:
                first = result["continued_state"]
            state = result["continued_state"]
            count += result["qualified"]
        return {
            "duration": duration,
            "first_state": first,
            "final_state": state,
            "qualified_calls": count,
            "last_stationarity": result["stationarity"],
            "last_sweeps": result["sweeps"],
            "energy": result["energy"],
            "state_hessian": result["independent_audit"]["scalar_state_hessian"],
        }

    failure = None
    try:
        teacher = teacher_audit()
        for gain in GAINS:
            zero = call(gain, 0.0, 0.0, ["cold", gain])
            cold.append(
                {
                    "gain": gain,
                    "state": zero["state"][0],
                    "qualified": zero["qualified"],
                }
            )
            for cue in CUES:
                written = call(gain, cue, 0.0, ["write", gain, cue])
                row = {
                    "gain": gain,
                    "cue": cue,
                    "written_state": written["state"][0],
                    "write_qualified": written["qualified"],
                    "blank_controls": [],
                }
                cases.append(row)
                for duration in DELAYS:
                    row["blank_controls"].append(
                        blanks(
                            gain,
                            written["continued_state"],
                            duration,
                            ["blank", gain, cue, duration],
                        )
                    )
                opposite = call(
                    gain,
                    -cue,
                    row["blank_controls"][-1]["final_state"],
                    ["opposite", gain, cue],
                )
                row["opposite_written_state"] = opposite["state"][0]
                row["opposite_qualified"] = opposite["qualified"]
                row["opposite_blank128"] = blanks(
                    gain,
                    opposite["continued_state"],
                    128,
                    ["opposite-blank", gain, cue],
                )
                reset = call(gain, 0.0, 0.0, ["reset", gain, cue])
                row["reset_state"] = reset["state"][0]
                row["reset_qualified"] = reset["qualified"]
    except Exception as exc:  # noqa: BLE001 - Preserve failed diagnostic outcomes.
        failure = repr(exc)
        teacher = locals().get("teacher", None)
    if time.monotonic() - started > 60:
        failure = failure or "diagnostic deadline during bookkeeping"
    unchanged = protocol["sources"] == sources()
    teacher_work = Counter()
    for item in teacher["cases"] if teacher else ():
        teacher_work.update(item["work"])
    expected = [{"gain": g, "cue": u} for g in GAINS for u in CUES]
    for item in expected:
        actual = next(
            (r for r in cases if r["gain"] == item["gain"] and r["cue"] == item["cue"]),
            None,
        )
        item["status"] = (
            "complete"
            if actual and "reset_state" in actual
            else "partial"
            if actual
            else "not_started"
        )
    result = {
        "schema": "private-cycle-memory-receipt/1",
        "status": "complete" if failure is None and unchanged else "incomplete",
        "failure": failure,
        "sources_unchanged": unchanged,
        "protocol_sha256": sha(root / "protocol.json"),
        "collector_sha256": sha(Path(__file__)),
        "calls_sha256": sha(root / "calls.jsonl")
        if (root / "calls.jsonl").exists()
        else None,
        "planned_cases": 14,
        "outcomes": expected,
        "cases": cases,
        "cold": cold,
        "scalar_calls": calls,
        "teacher_calls": len(teacher["cases"]) if teacher else 0,
        "total_calls": calls + (len(teacher["cases"]) if teacher else 0),
        "scalar_unqualified_calls": unqualified,
        "teacher_unqualified_calls": sum(not r["qualified"] for r in teacher["cases"])
        if teacher
        else 0,
        "unqualified_calls": unqualified
        + (sum(not r["qualified"] for r in teacher["cases"]) if teacher else 0),
        "scalar_work": dict(work),
        "teacher_work": dict(teacher_work),
        "worst_scalar_finite_difference_abs_error": worst_fd,
        "teacher_clamp_derivative_audit": teacher,
        "seconds": time.monotonic() - started,
        "scope": protocol["scope"],
    }
    write(root / "receipt.json", result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "status",
                    "total_calls",
                    "unqualified_calls",
                    "worst_scalar_finite_difference_abs_error",
                    "seconds",
                )
            }
        )
    )
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.root.resolve())
    else:
        raise SystemExit(run(args.root.resolve()))
