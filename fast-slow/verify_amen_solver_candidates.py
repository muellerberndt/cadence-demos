"""Requalify every experimental proposal with the frozen scalar energy, no learning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import amen_architecture_calibrate as A
import numpy as np
from cadence import Brain, _repair


def require(value, message):
    if not value:
        raise ValueError(message)


def projected(values, gradients, bound, fixed=()):
    return float(
        max(
            (
                abs(v - min(bound, max(-bound, v - g)))
                for i, (v, g) in enumerate(zip(values, gradients, strict=True))
                if i not in fixed
            ),
            default=0.0,
        )
    )


def qualify(brain, examples, point):
    n = brain.graph.n_patches
    batch = len(examples)
    edge_count = len(brain.weights)
    require(point.shape == (batch * n + edge_count + n,), "proposal dimensions")
    require(np.isfinite(point).all(), "nonfinite proposal")
    state, weights, biases = (
        point[: batch * n],
        point[batch * n : batch * n + edge_count],
        point[-n:],
    )
    inputs, fixed = [], {}
    for row, (v, t) in enumerate(examples):
        flat, clamps = brain._arguments(v, t)
        inputs.extend(flat)
        fixed.update({row * n + i: y for i, y in clamps.items()})
    require(all(state[i] == v for i, v in fixed.items()), "changed actual clamp")
    require(np.max(np.abs(state)) <= brain.config["state_bound"], "state outside box")
    require(
        np.max(np.abs(point[batch * n :])) <= brain.config["parameter_bound"],
        "parameter outside box",
    )
    result = _repair._evaluate_batch(
        brain.graph,
        tuple(inputs),
        tuple(state),
        tuple(weights),
        tuple(biases),
        brain.config["state_prior"],
        brain.weights,
        brain.biases,
        brain.config["parameter_prior"],
        batch_size=batch,
    )
    components = [
        projected(
            state, result["gradient_state_unscaled"], brain.config["state_bound"], fixed
        ),
        projected(weights, result["gradient_weights"], brain.config["parameter_bound"]),
        projected(biases, result["gradient_biases"], brain.config["parameter_bound"]),
    ]
    return {
        "energy": float(result["energy"]),
        "stationarity": max(components),
        "components_state_weights_biases": components,
        "qualified": max(components) <= 1e-6,
    }


def inventory(execution):
    require(len(execution) == 2, "two candidate outcomes required")
    require(
        [r["method"] for r in execution] == ["diagonal_spectral", "gauss_newton_cg"],
        "candidate inventory/order",
    )


def verify(root, out):
    p = A.read(out / "protocol.json")
    sources = {**p["sources"], **p["artifacts"]}
    require(all(A.sha(k) == v for k, v in sources.items()), "source/artifact drift")
    runtime = A.read(root / "runtime600/protocol.json")
    old = A.read(runtime["prior_protocol"])
    require(
        A.sha(runtime["prior_protocol"]) == runtime["prior_sha256"],
        "parent protocol drift",
    )
    base = Path(old["base"])
    require(
        all(
            A.sha(base / "data" / name) == pin for name, pin in old["data_pins"].items()
        ),
        "row data drift",
    )
    _, T = A.modules(Path(old["app"]))
    arrays = tuple(
        np.load(base / "data" / f"{name}.npy", mmap_mode="r")
        for name in ("history", "clock", "wake", "targets", "origin")
    )
    examples = [T.example(arrays, i, 8) for i in old["indices"]]
    initial_text = (root / "runtime600/plain/initial.json").read_text()
    brain = Brain.from_snapshot(initial_text)
    require(brain.inspect()["admissions"] == 0, "founder admission cursor")
    require(
        (len(examples), brain.graph.n_patches, brain.graph.n_inputs, len(brain.weights))
        == (32, 135, 585, 47735),
        "exact frozen dimensions",
    )
    execution = A.read(out / "execution.json")
    inventory(execution)
    summaries = []
    for outer in execution:
        case = out / outer["method"]
        if not (case / "report.json").exists():
            require(
                outer.get("status") in ("outer_timeout", "launch_error")
                or outer.get("exit_code") != 0,
                "unexplained missing candidate",
            )
            summaries.append(
                {
                    "method": outer["method"],
                    "status": outer.get("status", "process_error"),
                    "qualified": False,
                    "missing_report": True,
                }
            )
            continue
        r = A.read(case / "report.json")
        require(
            r["method"] == outer["method"] and r["public_admissions"] == 0,
            "candidate identity/admission claim",
        )
        require(
            r["protocol_sha256"] == A.sha(out / "protocol.json"), "protocol identity"
        )
        lines = (
            (case / "iterations.jsonl").read_text().splitlines()
            if (case / "iterations.jsonl").exists()
            else []
        )
        trace = [json.loads(line) for line in lines]
        require(
            [a["iteration"] for a in trace] == list(range(len(trace))),
            "iteration custody",
        )
        require(r["completed_iterations"] == len(trace), "iteration count")
        require(
            all(b["energy"] <= a["energy"] + 1e-13 for a, b in zip(trace, trace[1:])),
            "accepted energy increased",
        )
        require(
            all(a["accepted"] for a in trace[:-1]),
            "continuation after line-search refusal",
        )
        qualified = False
        actual = None
        if (case / "candidate.npy").exists():
            require(
                A.sha(case / "candidate.npy") == r["candidate_sha256"], "candidate hash"
            )
            actual = qualify(brain, examples, np.load(case / "candidate.npy"))
            require(
                actual["energy"] == r["reference_energy"], "reference energy mismatch"
            )
            require(
                abs(actual["stationarity"] - r["reference_stationarity"]) <= 1e-14,
                "reference stationarity mismatch",
            )
            qualified = (
                actual["qualified"]
                and r["sources_and_artifacts_unchanged"]
                and outer.get("exit_code") == 0
                and outer.get("status") not in ("outer_timeout", "launch_error")
            )
            require(qualified == r["qualified"], "false candidate qualification")
        else:
            require(not r["qualified"], "missing final point promoted")
        validation = (
            A.read(case / "validation.json")
            if (case / "validation.json").exists()
            else None
        )
        if qualified:
            require(
                validation is not None
                and [v["point"] for v in validation] == p["validation_points"],
                "missing prerequisite equation checks",
            )
            require(
                r["unknown_incomplete_evaluations"] == 0,
                "unaccounted interrupted evaluation",
            )
            require(r["seconds"] <= p["outer_seconds"], "over-budget result promoted")
        summaries.append(
            {
                **r,
                "independent_reference": actual,
                "verified_candidate_qualified": qualified,
                "accepted_steps": sum(a["accepted"] for a in trace),
                "backtracks": sum(a["backtracks"] for a in trace),
                "cg_iterations": sum(a["cg_iterations"] for a in trace),
                "validation": validation,
            }
        )
    require(brain.snapshot() == initial_text, "verification mutated public founder")
    require(
        all(A.sha(k) == v for k, v in sources.items()), "post-verification source drift"
    )
    baseline = A.read(root / "runtime600/plain/discarded-admission-result.json")
    recovered = []
    if "prior_failed_attempt" in p:
        failed = Path(p["prior_failed_attempt"])
        failed_execution = A.read(failed / "execution.json")
        inventory(failed_execution)
        require(
            all(r.get("exit_code") == 1 for r in failed_execution),
            "original failure census",
        )
        for method in ("diagonal_spectral", "gauss_newton_cg"):
            case = failed / method
            original_point = np.load(case / "candidate.npy")
            actual = qualify(brain, examples, original_point)
            original_trace = (case / "iterations.jsonl").read_text()
            repeated_path = out / method / "iterations.jsonl"
            repeated_trace = (
                repeated_path.read_text() if repeated_path.exists() else None
            )
            repeated_point = out / method / "candidate.npy"
            recovered.append(
                {
                    "method": method,
                    "original_attempt_status": "failed_final_json_serialization",
                    "raw_endpoint_sha256": A.sha(case / "candidate.npy"),
                    "independent_reference": actual,
                    "endpoint_bytes_equal_repeat": (
                        A.sha(case / "candidate.npy") == A.sha(repeated_point)
                        if repeated_point.exists()
                        else None
                    ),
                    "iteration_ledger_exact_equal_repeat": original_trace
                    == repeated_trace,
                    "wall_time_recovered": False,
                    "public_admissions": 0,
                }
            )
    value = {
        "schema": "amen-solver-verification/1",
        "verified": True,
        "verifier_sha256": A.sha(__file__),
        "protocol_sha256": A.sha(out / "protocol.json"),
        "public_admissions": 0,
        "source_bound_cases": 2,
        "qualified_candidates": sum(
            r["verified_candidate_qualified"]
            for r in summaries
            if "verified_candidate_qualified" in r
        ),
        "candidate_results": summaries,
        "original_failed_attempt_descriptive_recovery": recovered,
        "native_baseline": {
            "seconds": baseline["seconds"],
            "sweeps": baseline["result"]["sweeps"],
            "work": baseline["result"]["work"],
            "energy": baseline["result"]["energy"],
            "stationarity": baseline["result"]["stationarity"],
        },
        "scope": "Raw experimental numerical proposals only, independently requalified against frozen scalar energy and original anchors/clamps. No solver trajectory replay or Brain admission. NumPy dense BLAS1 versus native sparse Torch4 conflates kernel and iteration wall-time changes; report each separately. One batch/graph, no observer contact, task accuracy or music claim.",
    }
    A.write(out / "verification.json", value)
    print(
        json.dumps(
            {
                "qualified_candidates": value["qualified_candidates"],
                "sha256": A.sha(out / "verification.json"),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    verify(a.root.resolve(), a.out.resolve())
