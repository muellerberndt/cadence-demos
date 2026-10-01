"""Check the signal probe by direct four-patch energy derivatives, without repair."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import readback_signal_probe as collector


def verify(root):
    protocol = json.loads((root / "protocol.json").read_text())
    result = json.loads((root / "result.json").read_text())
    assert result["sources_unchanged"] and result["all_queries_qualified"]
    assert result["protocol_sha256"] == collector.sha(root / "protocol.json")
    assert protocol["collector_sha256"] == collector.sha(Path(collector.__file__))
    expected = {
        (seed, alpha, tuple(history), condition)
        for seed in protocol["seeds"]
        for alpha in protocol["state_priors"]
        for history in protocol["histories"]
        for condition in protocol["conditions"]
    }
    seen, max_gradient, max_difference = set(), 0.0, 0.0
    for row in result["rows"]:
        key = row["seed"], row["state_prior"], tuple(row["history"]), row["condition"]
        assert key in expected and key not in seen
        seen.add(key)
        model = collector.brain(row["seed"], row["state_prior"])
        assert list(model.graph.residual_order) == [0, 1, 2, 3]
        weights = dict(zip(model.graph.edges, model.weights, strict=True))
        x, history, alpha = row["state"], row["history"], row["state_prior"]
        assert all(abs(value) < 1.0 for value in x)
        p = [
            math.tanh(math.fsum(weights["input", i, j] * history[i] for i in (0, 1)))
            for j in (0, 1)
        ]
        e = [x[j] - p[j] for j in (0, 1)]
        for j in (2, 3):
            activation = math.fsum(
                [weights["state", i, j] * x[i] for i in (0, 1)]
                + [weights["residual", i, j] * e[i] for i in (0, 1)]
            )
            p.append(math.tanh(activation))
            e.append(x[j] - p[j])
        gradients = [
            alpha * x[i]
            + e[i]
            - math.fsum(
                e[j]
                * (1 - p[j] ** 2)
                * (weights["state", i, j] + weights["residual", i, j])
                for j in (2, 3)
            )
            for i in (0, 1)
        ] + [alpha * x[j] + e[j] for j in (2, 3)]
        if row["condition"] == "past_observation_clamped":
            assert x[:2] == row["actual_past"]
            gradients = gradients[2:]
        difference = max(
            abs(a - b)
            for a, b in zip(p + e, row["predictions"] + row["errors"], strict=True)
        )
        assert difference <= 1e-14
        max_difference = max(max_difference, difference)
        max_gradient = max(max_gradient, max(map(abs, gradients)))
        assert max(map(abs, gradients)) <= 1.0001 * protocol["tolerance"]
        assert row["qualified"] and row["snapshot_pure"]
    assert seen == expected and len(seen) == 160
    return {
        "verified": True,
        "queries_checked": len(seen),
        "maximum_free_coordinate_gradient": max_gradient,
        "maximum_prediction_error_recomputation_difference": max_difference,
        "collector_sha256": protocol["collector_sha256"],
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "result_sha256": collector.sha(root / "result.json"),
        "scope": "Direct tanh predictions, errors and analytic eligible-coordinate energy derivatives; no solver call, learning or task advantage claim",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.root), indent=2))
