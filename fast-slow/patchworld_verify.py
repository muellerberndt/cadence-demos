"""Independent frozen-input, query and original-body replay; no learning replay.

All fifteen outcomes remain visible. A successful receipt establishes source/data
custody, public admission records, heldout behavior and native execution, not
reward discovery, survival, browser migration or capacity-matched advantage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from collections import Counter
from pathlib import Path

import patchworld_bootstrap as p

from cadence import Brain

PIN = "45a414bce89c83a246b31b0a85554048359ee41d0f5b0ed217a4542802518c2f"
SEEDS = (211, 223, 227, 229, 233)
ARMS = ("flat", "composed", "observer")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def same(a, b, context="value"):
    if isinstance(a, dict) and isinstance(b, dict):
        require(a.keys() == b.keys(), context + " keys")
        for key in a:
            same(a[key], b[key], context + "." + key)
    elif isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        require(len(a) == len(b), context + " length")
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            same(x, y, context + "." + str(i))
    elif isinstance(a, float) or isinstance(b, float):
        require(math.isclose(a, b, rel_tol=1e-11, abs_tol=1e-12), context)
    else:
        require(a == b, context)


def digest(snapshot):
    return hashlib.sha256(snapshot.encode()).hexdigest()


def lines(path):
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


def targets(food):
    return [
        math.tanh(1.2 * sum(food[i] for i in sector) - food[4])
        for sector in ((0, 1, 2), (2, 5, 8), (6, 7, 8), (0, 3, 6))
    ] + [math.tanh(4 * food[4] - 0.2), -0.4]


def tape(n, seed):
    rng, result = random.Random(seed), []
    for i in range(n):
        maximum = 8 if i % 3 == 0 else 2
        food = [
            (rng.randrange(maximum + 1) if rng.random() < 0.45 else 0) / 8
            for _ in range(9)
        ]
        result.append([{"food": food}, {"action": targets(food)}])
    return result


def acquisition_gate(status, admissions, after, native):
    return (
        status == "complete"
        and admissions == 120
        and after.get("qualified") == 48
        and after.get("agreement", 0) >= 0.9
        and native.get("refused") == 0
    )


def replay_query(brain, row, method="settle"):
    require(row["before_sha256"] == digest(brain.snapshot()), "query input custody")
    before = brain.snapshot()
    result = getattr(brain, method)(row["inputs"])
    same(result, row["result"], "replayed query")
    require(row["after_sha256"] == digest(brain.snapshot()), "query output custody")
    if method == "settle":
        require(brain.snapshot() == before, "pure query mutated")
    return result


def metrics(rows, examples):
    details, qualified, correct = [], 0, 0
    for row, (inputs, expected) in zip(rows, examples, strict=True):
        same(row["inputs"], inputs, "query row")
        result = row["result"]
        chosen = max(range(6), key=result["outputs"]["action"].__getitem__)
        ok = (
            result["qualified"]
            and expected["action"][chosen] >= max(expected["action"]) - 1e-12
        )
        qualified += result["qualified"]
        correct += ok
        details.append(
            {
                "inputs": inputs,
                "expected": expected,
                "chosen": chosen,
                "qualified": result["qualified"],
                "correct": ok,
            }
        )
    return {
        "rows": len(rows),
        "qualified": qualified,
        "correct": correct,
        "agreement": correct / len(rows),
        "details": details,
    }


def verify_arm(root, core, data, seed, arm):
    folder = root / f"{arm}-seed{seed}"
    require((folder / "result.json").exists(), "missing planned outcome")
    report = p.read(folder / "result.json")
    require((report["seed"], report["arm"]) == (seed, arm), "outcome identity")
    initial = (folder / "initial.json").read_text()
    brain = p.make(arm, seed)
    require(brain.snapshot() == initial, "public seeded founder")
    expected_size = {"flat": (6, 54), "composed": (8, 84), "observer": (8, 96)}[arm]
    require(
        (brain.graph.n_patches, len(brain.graph.edges)) == expected_size,
        "topology counts",
    )
    require(
        arm != "flat" or all(e[0] == "input" for e in brain.graph.edges),
        "actual flat input-only contacts",
    )
    rows = lines(folder / "calls.jsonl")
    require(all(r["status"] == "returned" for r in rows), "returned call journal")
    work, kinds = Counter(), {}
    for row in rows:
        work.update(row["result"]["work"])
        kinds.setdefault(row["kind"], Counter()).update(row["result"]["work"])
        if row["kind"] == "admission":
            require(
                not row["result"]["accepted"] or row["result"]["qualified"],
                "unqualified admission accepted",
            )
    admissions = sum(r["kind"] == "admission" and r["result"]["accepted"] for r in rows)
    same(report["work"], dict(work), "total returned work")
    same(
        report["work_by_kind"],
        {k: dict(v) for k, v in kinds.items()},
        "phase returned work",
    )
    require(
        report["calls"] == len(rows) and report["accepted_admissions"] == admissions,
        "returned counts",
    )
    same(
        report["qualified_acquisition_and_body_gate"],
        acquisition_gate(
            report["status"],
            admissions,
            report["phases"].get("after", {}),
            report["phases"].get("learned_live", {}),
        ),
        "gate recomputation",
    )

    # The first three phases and exposure order must form a prefix even if capped.
    plan = [("query", ex[0]) for ex in data["heldout"]]
    for epoch in range(20):
        order = list(range(96))
        random.Random(seed + epoch).shuffle(order)
        for start in range(0, 96, 16):
            plan.append(
                ("admission", [data["train"][i] for i in order[start : start + 16]])
            )
    plan.extend(("query", ex[0]) for ex in data["development"])
    plan.extend(("query", ex[0]) for ex in data["heldout"])
    prior = digest(initial)
    for row, (kind, inputs) in zip(rows, plan):
        require(
            row["kind"] == kind and row["before_sha256"] == prior,
            "training/query chronological custody",
        )
        same(row["inputs"], inputs, "frozen training exposure")
        require(row["targets"] is None, "unexpected auxiliary targets")
        if kind == "query" or not row["result"].get("accepted", True):
            require(row["after_sha256"] == prior, "pure/refused call changed snapshot")
        prior = row["after_sha256"]
    for row in rows[:48]:
        replay_query(brain, row)
    if len(rows) >= 48:
        same(
            metrics(rows[:48], data["heldout"]),
            report["phases"]["before"],
            "newborn metrics",
        )
    if report["status"] != "complete":
        require(
            not report["qualified_acquisition_and_body_gate"], "incomplete promotion"
        )
        return {
            "seed": seed,
            "arm": arm,
            "status": report["status"],
            "accepted_admissions": admissions,
            "gate": False,
            "returned_calls": len(rows),
            "work": dict(work),
            "body_replay_complete": False,
            "unknown_work": report["unknown_work"],
        }

    require(
        len(rows) >= len(plan) and admissions == 120, "complete acquisition inventory"
    )
    trained = (folder / "trained.json").read_text()
    same(
        p.read(folder / "current-call.json"),
        rows[-1],
        "no unknown terminal solver work",
    )
    require(digest(trained) == prior, "trained final custody")
    brain = Brain.from_snapshot(trained)
    require(brain.snapshot() == trained, "source-bound trained reload")
    for row in rows[168:240]:
        replay_query(brain, row)
    same(
        metrics(rows[168:192], data["development"]),
        report["phases"]["development"],
        "development metrics",
    )
    same(
        metrics(rows[192:240], data["heldout"]),
        report["phases"]["after"],
        "heldout metrics",
    )
    native_cursor = 240
    body_calls = 0
    body_summaries = {}
    for name, snapshot in (
        ("learned", trained),
        ("untrained", initial),
        ("random", None),
        ("reflex", None),
    ):
        if snapshot is not None:
            brain = Brain.from_snapshot(snapshot)
        journal = lines(folder / f"body-{name}.jsonl")
        same(
            p.read(folder / f"body-{name}.current.json"),
            journal[-1],
            "no unknown terminal body operation",
        )
        require(
            journal and journal[0]["request"]["op"] == "init", "body initialization"
        )
        body = p.Body(core, 1000 + seed, brain if snapshot is not None else None)
        try:
            same(body.initial, journal[0]["response"], "original body seeded initial")
            expect_init = {
                "op": "init",
                "seed": 1000 + seed,
                "patches": brain.graph.n_patches if snapshot else 0,
                "connections": len(brain.graph.edges) if snapshot else 0,
            }
            same(journal[0]["request"], expect_init, "native structural metabolism")
            frames, refused, observation = [], 0, None
            rng = random.Random(2000 + seed)
            for row in journal[1:]:
                request = row["request"]
                result = body.request(request)
                same(result, row["response"], "original physics replay")
                body_calls += 1
                if request["op"] == "sense":
                    require(observation is None, "unconsumed body observation")
                    observation = result if result["alive"] else None
                    continue
                require(
                    request["op"] == "step" and observation is not None,
                    "causal body action",
                )
                inputs = {"food": [x / 8 for x in observation["food"]]}
                if snapshot is not None:
                    call = rows[native_cursor]
                    native_cursor += 1
                    require(call["kind"] == "live", "native brain call kind")
                    same(
                        call["inputs"], inputs, "actor receives only current nine foods"
                    )
                    query = replay_query(brain, call, "step")
                    qualified = query["qualified"]
                    action = (
                        max(range(6), key=query["outputs"]["action"].__getitem__)
                        if qualified
                        else 5
                    )
                    sweeps = query["sweeps"]
                    refused += not qualified
                else:
                    qualified, sweeps = True, 0
                    action = (
                        rng.randrange(6)
                        if name == "random"
                        else max(range(6), key=targets(inputs["food"]).__getitem__)
                    )
                same(
                    request,
                    {
                        "op": "step",
                        "tick": observation["tick"],
                        "action": action,
                        "qualified": qualified,
                        "sweeps": sweeps,
                    },
                    "executed action and native compute charge",
                )
                require(
                    result["before"]["mass"]
                    == result["after"]["mass"]
                    == body.initial["initial_mass"],
                    "mass conservation",
                )
                require(result["births"] == 0, "single-organism control")
                frames.append({"observation": observation, "executed": result})
                observation = None
            same(
                frames, lines(folder / f"live-{name}.jsonl"), "native trajectory detail"
            )
            summary = {
                "initial": body.initial,
                "ticks": len(frames),
                "requested": 96,
                "refused": refused,
                "terminal": bool(frames and not frames[-1]["executed"]["alive"]),
                "last": frames[-1]["executed"] if frames else None,
            }
            same(summary, report["phases"][name + "_live"], "native summary")
            require(
                0 < len(frames) <= 96 and (len(frames) == 96 or summary["terminal"]),
                "complete native horizon or natural death",
            )
            body_summaries[name] = {
                k: summary[k] for k in ("ticks", "refused", "terminal")
            }
            body_summaries[name]["eats"] = summary["last"]["eats"]
            body_summaries[name]["final_energy"] = summary["last"]["after"]["energy"]
        finally:
            body.close()
    require(native_cursor == len(rows), "no hidden extra solver calls")
    require(
        (folder / "latest.json").read_text() == brain.snapshot(),
        "last preserved live state",
    )
    require(
        report["sources_unchanged"] and not report["unknown_work"],
        "complete unchanged sources and known work",
    )
    train_inputs = {tuple(ex[0]["food"]) for ex in data["train"]}
    novel = [
        i
        for i, ex in enumerate(data["heldout"])
        if tuple(ex[0]["food"]) not in train_inputs
    ]
    novel_metrics = metrics(
        [rows[192 + i] for i in novel], [data["heldout"][i] for i in novel]
    )
    return {
        "seed": seed,
        "arm": arm,
        "status": "complete",
        "gate": report["qualified_acquisition_and_body_gate"],
        "accepted_admissions": admissions,
        "before_agreement": report["phases"]["before"]["agreement"],
        "heldout_agreement": report["phases"]["after"]["agreement"],
        "novel_heldout_rows": len(novel),
        "novel_heldout_agreement": novel_metrics["agreement"],
        "novel_heldout_is_descriptive_only": True,
        "returned_calls": len(rows),
        "work": dict(work),
        "work_by_kind": report["work_by_kind"],
        "seconds": report["seconds"],
        "python_process_cpu_seconds_excludes_node": report["cpu_seconds"],
        "native": body_summaries,
        "body_replayed_calls": body_calls,
        "body_replay_complete": True,
        "unknown_work": False,
    }


def verify(root, core):
    started = time.monotonic()
    require(p.sha(Path(p.__file__)) == PIN, "frozen collector pin")
    protocol = p.bound_inputs(root, core)
    same(protocol["seeds"], SEEDS, "five seeds")
    same(protocol["arms"], ARMS, "three arms")
    data = p.read(root / "data.json")
    expected = {
        name: tape(n, seed)
        for name, n, seed in (
            ("train", 96, 641),
            ("development", 24, 643),
            ("heldout", 48, 647),
        )
    }
    same(data, expected, "independent data/teacher generation")
    summary = p.read(root / "summary.json")
    require(
        summary["all_planned_retained"] and len(summary["outcomes"]) == 15,
        "all15 retained",
    )
    require(
        {(r["seed"], r["arm"]) for r in summary["outcomes"]}
        == {(s, a) for s in SEEDS for a in ARMS},
        "unique planned cases",
    )
    for report in summary["outcomes"]:
        same(
            report,
            p.read(root / f"{report['arm']}-seed{report['seed']}" / "result.json"),
            "summary exact outcomes",
        )
    cases = [verify_arm(root, core, data, seed, arm) for seed in SEEDS for arm in ARMS]
    p.bound_inputs(root, core)
    return {
        "valid": True,
        "collector_sha256": PIN,
        "verifier_sha256": p.sha(Path(__file__)),
        "protocol_sha256": p.sha(root / "protocol.json"),
        "source_node_data_pins": True,
        "all_planned_outcomes": 15,
        "completed": sum(c["status"] == "complete" for c in cases),
        "passing": sum(c["gate"] for c in cases),
        "cases": cases,
        "full_learning_replay": False,
        "complete_arm_queries_and_native_physics_replayed": True,
        "all_mass_checks": True,
        "split_overlap": {
            "heldout_rows_also_in_training": 8,
            "heldout_novel_rows": 40,
            "development_rows_also_in_training": 3,
            "original_gate_unchanged": True,
        },
        "limitations": [
            "No numerical learning replay; admissions and snapshot custody checked.",
            "Collector startup failure may abort summary; verifier requires every planned outcome.",
            "Collector interruption during bookkeeping can leave started intent with unknown work; verifier rejects complete outcomes with pending intent.",
            "Native metabolism uses the original bounded stochastic per-tick charge; it is not a full CPU-cost model.",
            "Native death is an outcome, not a survival success; the frozen gate only requires qualification and conserved mass.",
        ],
        "scope": protocol["scope"],
        "seconds": time.monotonic() - started,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--core", type=Path, required=True)
    args = parser.parse_args()
    receipt = verify(args.root.resolve(), args.core.resolve())
    p.write(args.root / "verification.json", receipt)
    print(
        json.dumps(
            {
                k: receipt[k]
                for k in (
                    "valid",
                    "all_planned_outcomes",
                    "completed",
                    "passing",
                    "seconds",
                )
            }
        )
    )
