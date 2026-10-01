"""Paired tiny-graph overhead controls for the exact query optimization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from query_cache import call, load_baseline, sha, sources, summarize, unchanged, write

from cadence import _repair


def run(args):
    import cadence

    args.out.mkdir(exist_ok=False)
    source_hashes = sources(cadence, Path(__file__), args.baseline)
    cases = []
    for name, inputs, patches, edges in (
        ("bias_only", 0, 1, ()),
        ("one_edge", 1, 1, (("input", 0, 0),)),
        (
            "tiny_recursive",
            1,
            2,
            (("input", 0, 0), ("state", 0, 1), ("residual", 0, 1)),
        ),
    ):
        cases.append((name, _repair.Graph(inputs, patches, edges)))
    protocol = {
        "sources": source_hashes,
        "repeats": 1000,
        "warmup": 50,
        "modes": ["cold", "live"],
        "inputs": "constant 0.3; cold resets zero, live retains qualified state",
        "ordering": "alternate baseline/candidate by repetition parity",
        "scope": "tiny-graph overhead control, no learning or capability claim",
    }
    write(args.out / "protocol.json", protocol)
    modules = {"baseline": load_baseline(args.baseline), "candidate": _repair}
    summaries = []
    with (args.out / "pairs.jsonl").open("w") as ledger:
        for name, graph in cases:
            graphs = {
                arm: module.Graph(graph.n_inputs, graph.n_patches, graph.edges)
                for arm, module in modules.items()
            }
            fixture = {
                "weights": [0.25] * len(graph.edges),
                "biases": [0.1] * graph.n_patches,
            }
            row = {"inputs": [0.3] * graph.n_inputs}
            rows = []
            for mode in protocol["modes"]:
                states = {arm: [0.0] * graph.n_patches for arm in modules}
                for index in range(-protocol["warmup"], protocol["repeats"]):
                    diagnostics, semantics = {}, {}
                    order = list(modules)
                    if index % 2:
                        order.reverse()
                    for arm in order:
                        state = (
                            [0.0] * graph.n_patches if mode == "cold" else states[arm]
                        )
                        result, semantics[arm], diagnostics[arm] = call(
                            modules[arm],
                            graphs[arm],
                            row,
                            state,
                            fixture,
                            {},
                        )
                        assert result is not None and result["qualified"]
                        states[arm] = result["state"]
                    assert semantics["baseline"] == semantics["candidate"]
                    if index >= 0:
                        record = dict(
                            name=name, mode=mode, index=index, exact=True, **diagnostics
                        )
                        ledger.write(json.dumps(record) + "\n")
                        rows.append(record)
            summaries.append({"name": name, "summary": summarize(rows)})
    assert unchanged(source_hashes)
    write(
        args.out / "report.json",
        {
            "status": "complete",
            "sources_unchanged": True,
            "protocol_sha256": sha(args.out / "protocol.json"),
            "ledger_sha256": sha(args.out / "pairs.jsonl"),
            "cases": summaries,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    run(parser.parse_args())
