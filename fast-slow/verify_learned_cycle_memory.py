"""Replay every private-kernel admission and chronological query from paired seeds.

Independent body/control scheduling, scalar energy/derivatives, custody and task
gates supplement exact source-bound numerical replay. No new learning experiment
is performed: replay must reproduce every previously retained call exactly.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import time
from collections import Counter
from pathlib import Path

import learned_cycle_memory as frozen
import verify_self_correction as common
from cadence._repair import Graph, settle

PIN = "4bbdf01af5d389fa92f69933ba24ffcb2f49bd91fd5ecdf3da5c2c65eb2f0a8f"
SEEDS = (149, 151, 157, 163, 167)
ARMS = ("cycle", "flat", "history")
REGIMES = ((0.9, 0.6), (0.98, 0.6), (0.98, 0.8))
CONFIG = {
    "state_prior": 0.01,
    "parameter_prior": 0.1,
    "tolerance": 1e-10,
    "budget": 2048,
    "state_bound": 1.0,
    "parameter_bound": 4.0,
    "step": 1.0,
    "backtracks": 32,
}
require, same, read, sha = common.require, common.same, common.read, common.sha


def digest(value):
    return frozen.custody.digest(frozen.custody.encoded(value))


def inputs(arm, cue, bit):
    values = (float(cue), float(abs(cue)))
    return (*values, float(bit)) if arm == "history" else values


def graph(arm):
    edge = (
        ("state", 0, 0)
        if arm == "cycle"
        else ("input", 2 if arm == "history" else 1, 0)
    )
    return Graph(3 if arm == "history" else 2, 1, (("input", 0, 0), edge))


def schedule(tape, regime):
    write, hold = REGIMES[regime]
    plan = [
        {"identity": f"batch{i}", "kind": "training", "rows": rows}
        for i, rows in enumerate(tape)
    ]

    def query(identity, cue, bit, target, scored=True):
        plan.append(
            {
                "identity": identity,
                "kind": "query",
                "cue": cue,
                "bit": bit,
                "target": target,
                "scored": scored,
            }
        )

    def reset(identity, source):
        plan.append({"identity": identity, "kind": "reset", "source": source})

    query("cold-neutral", 0, 0, 0)
    for sign in (-1, 1):
        reset(f"fresh-trial:{sign}", "zero")
        query(f"write:{sign}", sign, sign, sign * write)
        for delay in (1, 8, 128):
            reset(f"fork-qualified-write:{sign}:delay{delay}", f"write:{sign}")
            for step in range(1, delay + 1):
                query(f"hold:{sign}:{delay}:{step}", 0, sign, sign * hold)
        reset(f"overwrite-start:{sign}", "current")
        query(f"overwrite:{sign}", -sign, -sign, -sign * write)
        for step in range(1, 129):
            query(f"overwritten-hold:{sign}:{step}", 0, -sign, -sign * hold)
        reset(f"state-only-erasure:{sign}", "zero")
        query(f"erased-state-history-retained:{sign}", 0, -sign, -sign * hold, False)
        reset(f"full-body-history-state-reset:{sign}", "zero")
        query(f"full-reset-neutral:{sign}", 0, 0, 0)
    return plan


def bit_gate(rows, complete):
    if not complete or len(rows) != 539:
        return False
    scored = [r for r in rows if r["scored"]]
    bits, neutral = (
        [r for r in scored if r["expected"] != 0],
        [r for r in scored if r["expected"] == 0],
    )
    return (
        bool(bits)
        and bool(neutral)
        and all(r["state"] * math.copysign(1, r["expected"]) >= 0.25 for r in bits)
        and all(abs(r["state"]) <= 0.05 for r in neutral)
    )


def projected(value, gradient, bound):
    return abs(
        min(gradient, value + bound) if gradient >= 0 else max(gradient, value - bound)
    )


def scalar_audit(arm, values, old_weights, old_biases, result, learning):
    states = result["state"]
    weights, biases = result["weights"], result["biases"]
    width = 3 if arm == "history" else 2
    errors, predictions, energies, gw, gb = [], [], [], [[], []], []
    for i, x in enumerate(states):
        cue = values[i * width]
        feature = (
            x if arm == "cycle" else values[i * width + (2 if arm == "history" else 1)]
        )
        p = math.tanh(math.fsum((biases[0], weights[0] * cue, weights[1] * feature)))
        e, d = x - p, 1 - p * p
        predictions.append(p)
        errors.append(e)
        energies.append(0.5 * e * e + 0.005 * x * x)
        gw[0].append(-e * d * cue)
        gw[1].append(-e * d * feature)
        gb.append(-e * d)
    energy = math.fsum(energies) / len(states)
    if learning:
        deltas = [
            a - b
            for a, b in zip(
                [*weights, *biases], [*old_weights, *old_biases], strict=True
            )
        ]
        energy += 0.05 * math.fsum(d * d for d in deltas)
        gradients = [
            math.fsum(v) / len(states) + 0.1 * d
            for v, d in zip([*gw, gb], deltas, strict=True)
        ]
        stationarity = max(
            projected(v, g, 4.0)
            for v, g in zip([*weights, *biases], gradients, strict=True)
        )
    else:
        x, p, e = states[0], predictions[0], errors[0]
        gradient = (
            0.01 * x + e * (1 - weights[1] * (1 - p * p))
            if arm == "cycle"
            else 0.01 * x + e
        )
        stationarity = projected(x, gradient, 1.0)
    require(abs(energy - result["energy"]) <= 2e-13, "independent scalar energy")
    require(
        max(abs(a - b) for a, b in zip(predictions, result["predictions"], strict=True))
        <= 1e-14,
        "independent prediction",
    )
    require(
        max(abs(a - b) for a, b in zip(errors, result["errors"], strict=True)) <= 1e-14,
        "independent residual",
    )
    require(
        abs(stationarity - result["stationarity"]) <= 2e-13,
        "independent projected derivative",
    )
    return abs(stationarity - result["stationarity"])


def sources_and_artifacts(root):
    p = read(root / "protocol.json")
    require(
        sha(Path(frozen.__file__)) == PIN and p["schema"] == "learned-private-cycle/1",
        "collector pin/schema",
    )
    identities = dict(p["sources"])
    names = [n for n in identities if Path(n).name == "learned_cycle_memory.py"]
    require(
        len(names) == 1 and identities.pop(names[0]) == PIN,
        "collector source inventory",
    )
    common.source_check({"sources": identities})
    same(p["seeds"], SEEDS, "seed inventory")
    same(p["arms"], ARMS, "arm inventory")
    same(p["regimes"], REGIMES, "regimes")
    same(p["config"], CONFIG, "repair law")
    for name, field in (
        ("tape", "tape_sha256"),
        ("founders", "founders_sha256"),
        ("threshold", "threshold_sha256"),
    ):
        require(sha(root / f"{name}.json") == p[field], f"{name} hash")
    tape, founders = read(root / "tape.json"), read(root / "founders.json")
    same(tape, frozen.tape(), "deterministic common tape")
    require(len(tape) == 64, "batch count")
    for i, rows in enumerate(tape):
        require(
            len(rows) == 16 and sum(r["body_bit"] for r in rows) == 0, "balanced batch"
        )
        for j, (cue, blank) in enumerate(zip(rows[::2], rows[1::2], strict=True)):
            identity = f"batch{i}:episode{j}"
            require(
                cue["episode"] == blank["episode"] == identity
                and cue["tick"] == 0
                and blank["tick"] == 1,
                "episode chronology",
            )
            require(
                cue["cue"] == cue["body_bit"] == blank["body_bit"]
                and cue["cue"] in (-1, 1)
                and blank["cue"] == 0,
                "causal history",
            )
            require(cue["phase"] == "write" and blank["phase"] == "hold", "body phase")
    require(set(founders) == {str(s) for s in SEEDS}, "founder inventory")
    for seed in SEEDS:
        same(founders[str(seed)], frozen.initial(seed), "paired random founder")
        require(
            len(founders[str(seed)]) == 3
            and all(abs(v) <= 0.1 for v in founders[str(seed)]),
            "unengineered gain range",
        )
    threshold = read(root / "threshold.json")
    same(threshold, frozen.threshold(), "saddle diagnostic")
    return p, tape, founders


def verify_arm(
    root, seed, regime, arm, tape, founder, execution, source_identity, deadline
):
    folder = root / f"regime{regime}-{arm}-seed{seed}"
    if execution["status"] == "not_started_deadline":
        require(
            not folder.exists()
            and execution["complete"] is False
            and execution["bit_memory_gate"] is False,
            "unstarted outcome",
        )
        return {
            "seed": seed,
            "regime": regime,
            "arm": arm,
            "status": execution["status"],
            "complete": False,
            "bit_memory_gate": False,
        }
    report = read(folder / "result.json")
    same(report, execution, "campaign/arm receipt")
    lines = (folder / "calls.jsonl").read_text().splitlines()
    journal = [json.loads(line) for line in lines]
    require(
        report["journal"]
        == {
            "bytes": (folder / "calls.jsonl").stat().st_size,
            "sha256": sha(folder / "calls.jsonl"),
        },
        "journal pin",
    )
    plan = schedule(tape, regime)
    require(len(journal) <= len(plan), "extra operations")
    g = graph(arm)
    weights, biases, state = tuple(founder[:2]), (founder[2],), (0.0,)
    accepted, returned, training_calls, query_calls = 0, 0, 0, 0
    work, written, query_rows = Counter(), {}, []
    max_scalar_gap = 0.0
    trained = None
    last_returned = None

    def snapshot():
        return {
            "graph": dataclasses.asdict(g),
            "config": CONFIG,
            "weights": weights,
            "biases": biases,
            "state": state,
            "admissions": accepted,
            "source_identity_sha256": source_identity,
        }

    for index, record in enumerate(journal):
        require(time.monotonic() < deadline, "full replay exceeded120 seconds")
        op = plan[index]
        require(record["identity"] == op["identity"], "chronological identity")
        if op["kind"] == "reset":
            target = (
                0
                if op["source"] == "zero"
                else state[0]
                if op["source"] == "current"
                else written[op["source"]]
            )
            same(
                record,
                {
                    "identity": op["identity"],
                    "state_intervention": True,
                    "from": state,
                    "to": [target],
                },
                "only declared native-state resets",
            )
            state = (target,)
            continue
        learning = op["kind"] == "training"
        if learning:
            values = tuple(
                v for r in op["rows"] for v in inputs(arm, r["cue"], r["body_bit"])
            )
            clamps = {
                str(i): r["body_bit"]
                * REGIMES[regime][0 if r["phase"] == "write" else 1]
                for i, r in enumerate(op["rows"])
            }
            initial_state = (0.0,) * 16
            batch_size = 16
        else:
            values = inputs(arm, op["cue"], op["bit"])
            clamps = {}
            initial_state = state
            batch_size = 1
        same(
            record["before"], snapshot(), "retained state/parameters/admission custody"
        )
        same(record["inputs"], values, "actual body input boundary")
        same(record["clamps"], clamps, "actual teaching targets/no query clamp")
        same(
            record["initial_state"],
            initial_state,
            "zero private rows/free native state",
        )
        require(
            record["learn"] is learning
            and record["batch_size"] == batch_size
            and record["source"] == ("witness" if learning else "free-query"),
            "call kind/provenance",
        )
        require(
            record["status"] == "returned"
            and math.isfinite(record["seconds"])
            and record["seconds"] >= 0,
            "returned call",
        )
        before_weights, before_biases = weights, biases
        result = settle(
            g,
            values,
            initial_state,
            weights,
            biases,
            clamps={int(k): v for k, v in clamps.items()},
            learn=learning,
            _batch_size=batch_size,
            **CONFIG,
        )
        same(
            {k: v for k, v in result.items() if k != "energy_history"},
            record["result"],
            "exact numerical replay",
        )
        require(
            record["energy_history_sha256"] == digest(result["energy_history"])
            and record["energy_history_length"] == len(result["energy_history"]),
            "descent history replay",
        )
        max_scalar_gap = max(
            max_scalar_gap,
            scalar_audit(arm, values, before_weights, before_biases, result, learning),
        )
        returned += 1
        work.update(result["work"])
        last_returned = record
        if learning:
            training_calls += 1
            if result["qualified"]:
                weights, biases = tuple(result["weights"]), tuple(result["biases"])
                accepted += 1
        else:
            query_calls += 1
            require(
                result["weights"] == weights and result["biases"] == biases,
                "frozen evaluation parameters",
            )
            if result["qualified"]:
                state = tuple(result["state"])
        require(
            record["retained_sha256"] == digest(snapshot()), "commit/refusal custody"
        )
        if not result["qualified"]:
            require(index == len(journal) - 1, "continued after refusal")
            continue
        if learning and accepted == 64:
            trained = snapshot()
            same(
                read(folder / "trained.json"),
                trained,
                "learned checkpoint fromzero live state",
            )
        if not learning:
            row = {
                "identity": op["identity"],
                "cue": op["cue"],
                "body_bit": op["bit"],
                "state": state[0],
                "expected": op["target"],
                "absolute_error": abs(state[0] - op["target"]),
                "scored": op["scored"],
                "qualified": True,
                "work": result["work"],
            }
            query_rows.append(row)
            if op["identity"].startswith("write:"):
                written[op["identity"]] = state[0]
    current = read(folder / "current-call.json")
    unknown = False
    if current["status"] == "returned":
        same(current, last_returned, "current receipt")
    else:
        require(len(journal) < len(plan), "pending after full sequence")
        op = plan[len(journal)]
        require(
            op["kind"] != "reset" and current["identity"] == op["identity"],
            "pending call identity",
        )
        same(current["before"], snapshot(), "interrupted before state")
        require(
            current["status"] in ("started", "interrupted", "not_started_deadline"),
            "pending status",
        )
        unknown = current["status"] in ("started", "interrupted")
        if current["status"] == "interrupted":
            require(current["unknown_work"] is True, "interrupted unknown work")
            same(current["restored"], snapshot(), "interrupted rollback")
    same(read(folder / "last-completed.json"), snapshot(), "final native state/custody")
    require(report["final_snapshot_sha256"] == digest(snapshot()), "final snapshot pin")
    same(read(folder / "queries.json"), query_rows, "all chronological query metrics")
    complete = (
        report["status"] == "complete"
        and accepted == 64
        and len(query_rows) == 539
        and not unknown
    )
    require(not complete or len(journal) == 617, "complete operation inventory")
    require(report["status"] in ("complete", "timeout", "error"), "reported status")
    require(
        report["complete"] is complete and report["unknown_work"] is unknown,
        "numerical completion",
    )
    passed = bit_gate(query_rows, complete)
    require(report["bit_memory_gate"] is passed, "task gate promotion")
    require(
        report["accepted_admissions"] == accepted
        and report["returned_calls"] == returned
        and report["queries"] == len(query_rows),
        "call/admission counts",
    )
    same(report["work"], dict(work), "all returned work")
    same(report["initial_parameters"], founder, "initial paired parameters")
    same(
        report["trained_parameters"],
        [*trained["weights"], *trained["biases"]] if trained else None,
        "actually acquired parameters",
    )
    scored = [q for q in query_rows if q["scored"]]
    bits = [q for q in scored if q["expected"] != 0]
    mae = sum(q["absolute_error"] for q in scored) / len(scored) if scored else None
    signed = min(
        (q["state"] * math.copysign(1, q["expected"]) for q in bits), default=None
    )
    require(
        report["free_target_mae"] == mae
        and report["minimum_signed_response"] == signed,
        "reported free task metrics",
    )
    same(
        report["erasure_diagnostics"],
        [q for q in query_rows if not q["scored"]],
        "unscored state-erasure controls",
    )
    require(report["sources_unchanged"] is True, "source drift")
    if complete:
        require(report["seconds"] <= 20, "completed arm exceeded allowance")
    per_phase = {}
    for name, prefix in (
        ("write", "write:"),
        ("hold", "hold:"),
        ("overwrite", "overwrite:"),
        ("overwritten_hold", "overwritten-hold:"),
        ("reset", "full-reset-neutral:"),
    ):
        selected = [q for q in query_rows if q["identity"].startswith(prefix)]
        per_phase[name] = {
            "count": len(selected),
            "mae": sum(q["absolute_error"] for q in selected) / len(selected)
            if selected
            else None,
            "minimum_signed_response": min(
                (
                    q["state"] * math.copysign(1, q["expected"])
                    for q in selected
                    if q["expected"] != 0
                ),
                default=None,
            ),
        }
    return {
        "seed": seed,
        "regime": regime,
        "arm": arm,
        "status": report["status"],
        "complete": complete,
        "bit_memory_gate": passed,
        "training_calls_replayed": training_calls,
        "free_calls_replayed": query_calls,
        "native_resets_verified": sum(
            r.get("state_intervention", False) for r in journal
        ),
        "accepted_admissions": accepted,
        "trained_parameters": report["trained_parameters"],
        "free_target_mae": mae,
        "minimum_signed_response": signed,
        "phases": per_phase,
        "erasure_diagnostics": report["erasure_diagnostics"],
        "returned_work": dict(work),
        "max_independent_stationarity_difference": max_scalar_gap,
    }


def conclusions(cases):
    result = []
    for regime in range(3):
        rows = [c for c in cases if c["regime"] == regime]
        eligible = len(rows) == 15 and all(c["complete"] for c in rows)
        result.append(
            {
                "regime": regime,
                "eligible": eligible,
                "cycle_and_history_all_five_pass": eligible
                and all(c["bit_memory_gate"] for c in rows if c["arm"] != "flat"),
                "by_arm_pass_counts": {
                    a: sum(c["bit_memory_gate"] for c in rows if c["arm"] == a)
                    for a in ARMS
                },
            }
        )
    return result


def verify(root):
    started = time.monotonic()
    protocol, tape, founders = sources_and_artifacts(root)
    executions = read(root / "execution.json")
    planned = [(s, r, a) for s in SEEDS for r in range(3) for a in ARMS]
    same(
        [(e["seed"], e["regime"], e["arm"]) for e in executions],
        planned,
        "all45 planned outcomes",
    )
    summary = read(root / "summary.json")
    same(summary["outcomes"], executions, "summary outcome inventory")
    source_identity = digest(protocol["sources"])
    cases = []
    for (seed, regime, arm), execution in zip(planned, executions, strict=True):
        cases.append(
            verify_arm(
                root,
                seed,
                regime,
                arm,
                tape,
                founders[str(seed)],
                execution,
                source_identity,
                started + 120,
            )
        )
    conclusion = conclusions(cases)
    same(summary["conclusions"], conclusion, "regime gate promotion")
    require(summary["planned_arms"] == 45, "planned count")
    return {
        "valid": True,
        "protocol_sha256": sha(root / "protocol.json"),
        "verifier_sha256": sha(Path(__file__)),
        "helper_sha256": sha(Path(common.__file__)),
        "collector_sha256": PIN,
        "cases": cases,
        "conclusions": conclusion,
        "totals": {
            "planned_arms": 45,
            "statuses": dict(Counter(c["status"] for c in cases)),
            **{
                k: sum(c.get(k, 0) for c in cases)
                for k in (
                    "training_calls_replayed",
                    "free_calls_replayed",
                    "native_resets_verified",
                    "accepted_admissions",
                )
            },
        },
        "seconds": time.monotonic() - started,
        "limits": "Full exact numerical replay uses the same pinned kernel, supplemented by independent scalar energy/derivative and body/custody/control checks. Supervised attractor acquisition, not learned temporal credit, public builder support, observer advantage, or planning. History control has one extra external memory scalar.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.root.resolve())
    with args.out.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {k: result[k] for k in ("valid", "totals", "conclusions", "seconds")}
        )
    )
