"""Check discarded timing/profile custody and independently requalify the batch."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import amen_architecture_calibrate as A
import numpy as np

from cadence import Brain, _repair


def check(x, message):
    if not x:
        raise ValueError(message)


def verify(root):
    p = A.read(root / "runtime600/protocol.json")
    old = A.read(Path(p["prior_protocol"]))
    check(all(A.sha(k) == v for k, v in p["sources"].items()), "sources changed")
    records = {
        k: A.read(root / f"runtime600/{k}/report.json") for k in ("plain", "profiled")
    }
    left, right = [r["calls"][-1]["result"] for r in records.values()]
    check(left == right, "profile altered numeric result")
    finaltext = (root / "runtime600/plain/discarded-final.json").read_text()
    check(
        finaltext == (root / "runtime600/profiled/discarded-final.json").read_text(),
        "profile snapshot differs",
    )
    brain = Brain.from_snapshot(finaltext)
    initial = Brain.from_snapshot((root / "runtime600/plain/initial.json").read_text())
    check(
        brain.snapshot() == finaltext and brain.state == initial.state,
        "snapshot custody",
    )
    check(
        brain.inspect()["admissions"] == 1 and initial.inspect()["admissions"] == 0,
        "admission cursor",
    )
    _, T = A.modules(Path(old["app"]))
    base = Path(old["base"])
    rows = tuple(
        np.load(base / "data" / f"{n}.npy", mmap_mode="r")
        for n in ("history", "clock", "wake", "targets", "origin")
    )
    inputs = []
    fixed = {}
    width = brain.graph.n_patches
    for row, i in enumerate(old["indices"]):
        v, t = T.example(rows, i, 8)
        flat, clamps = brain._arguments(v, t)
        inputs.extend(flat)
        fixed.update({row * width + j: value for j, value in clamps.items()})
    state = tuple(v for r in left["states"] for v in r)
    check(all(state[i] == v for i, v in fixed.items()), "actual witness clamps")
    evaluated = _repair._evaluate_batch(
        brain.graph,
        tuple(inputs),
        state,
        brain.weights,
        brain.biases,
        brain.config["state_prior"],
        initial.weights,
        initial.biases,
        brain.config["parameter_prior"],
        batch_size=32,
    )
    pieces = []
    for values, gradients, bound, mask in [
        (state, evaluated["gradient_state_unscaled"], 1, set(fixed)),
        (brain.weights, evaluated["gradient_weights"], 4, set()),
        (brain.biases, evaluated["gradient_biases"], 4, set()),
    ]:
        pieces.append(
            max(
                (
                    abs(x - min(bound, max(-bound, x - g)))
                    for i, (x, g) in enumerate(zip(values, gradients, strict=True))
                    if i not in mask
                ),
                default=0,
            )
        )
    residual = max(pieces)
    check(
        abs(residual - left["stationarity"]) < 1e-12 and residual <= 1e-6,
        "independent projected qualification",
    )
    check(evaluated["energy"] == left["energy"], "reference energy")
    for field in ("predictions", "errors"):
        check(
            list(evaluated[field]) == [v for row in left[field] for v in row],
            f"reference {field}",
        )
    params = hashlib.sha256(
        json.dumps(
            {"weights": list(brain.weights), "biases": list(brain.biases)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    check(params == left["parameters_sha256"], "parameter hash")
    failed = []
    for w in (64, 256):
        r = A.read(root / f"timing/ordinary{w}/report.json")
        check(
            not r["timing_usable"]
            and r["accepted_admissions"] == 0
            and r["calls"][-1]["unknown_solver_work"],
            "censored probes preserved",
        )
        failed.append(
            {
                "width": w,
                "status": r["status"],
                "seconds": r["seconds"],
                "admission_unknown_seconds": r["calls"][-1]["seconds"],
            }
        )
    hidden = A.read(root / "hidden-clamp-diagnostic/receipt.json")
    check(
        hidden["status"] == "complete"
        and hidden["qualified_queries"] == 8
        and hidden["admissions"] == 0
        and hidden["snapshot_unchanged"]
        and hidden["sources_unchanged"],
        "hidden audit custody",
    )
    profile = A.read(root / "runtime600/profiled/profile-summary.json")
    summary = {
        "schema": "amen-runtime-verification/1",
        "verified": True,
        "verifier_sha256": A.sha(__file__),
        "source_protocol_sha256": A.sha(root / "runtime600/protocol.json"),
        "plain_profile_all_result_fields_identical": True,
        "plain_profile_snapshots_identical": True,
        "reference_energy": evaluated["energy"],
        "reference_projected_stationarity": residual,
        "projected_components_state_weights_biases": pieces,
        "numerical_learning_replay": False,
        "discarded_admissions": 2,
        "earlier_censored_probes": failed,
        "work": left["work"],
        "execution": left["execution"],
        "sweeps": left["sweeps"],
        "timing": {
            k: {
                "whole_seconds": r["seconds"],
                "admission_seconds": r["calls"][-1]["seconds"],
            }
            for k, r in records.items()
        },
        "profile": profile,
        "hidden_clamp": hidden,
        "scope": "Same qualified public first-batch calls with and without profiling, exact result/snapshot parity plus frozen reference energy/gradient requalification and independent projected-gradient arithmetic. Earlier capped calls retained with unknown work. All brains discarded; no routine/musical/acquisition success claim.",
    }
    A.write(root / "runtime-verification.json", summary)
    print(A.sha(root / "runtime-verification.json"), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    a = p.parse_args()
    verify(a.root.resolve())
